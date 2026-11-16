"""Private same-UID alias fixtures; no service/helper starts, grants or SQL."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hyprneuro import identity_unit_path as paths

class UnitPaths(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.root.chmod(0o700)
        self.logical=self.root/'config/systemd/user';self.canonical=self.root/'dotfiles/systemd/user'
        self.canonical.mkdir(parents=True);self.logical.parent.parent.mkdir()
        self.logical.parent.symlink_to(self.canonical.parent)
        self.patch1=patch.object(paths,'LOGICAL_ROOT',self.logical);self.patch2=patch.object(paths,'CANONICAL_ROOT',self.canonical)
        self.patch1.start();self.patch2.start();self.addCleanup(self.patch1.stop);self.addCleanup(self.patch2.stop)
        self.target=self.canonical/'hyprneuro-ui.service';self.target.write_bytes(b'fixture');self.target.chmod(0o600)
        self.raw=self.logical/self.target.name;self.sha=hashlib.sha256(self.target.read_bytes()).hexdigest()
        self.catalog={str(self.target):self.sha}
        self.value=dict(logical=str(self.raw),canonical=str(self.target),chain=[paths._parents(self.raw),paths._parents(self.target)],target=paths._stamp(self.target))
    def load(self,value=None):return paths.UnitPathBinding.load(value or self.value,'hyprneuro-ui.service',self.catalog)
    def private_directory_alias_replacement(self,dropin):
        self.canonical.chmod(0o700)
        if dropin:
            directory=self.canonical/'hyprneuro-ui.service.d';directory.mkdir(mode=0o700)
            target=directory/'10-private.conf';target.write_bytes(b'private dropin');target.chmod(0o600)
        else:target=self.target
        logical=self.logical/target.relative_to(self.canonical)
        value=dict(logical=str(logical),canonical=str(target),chain=[paths._parents(logical),paths._parents(target)],target=paths._stamp(target))
        binding=paths.UnitPathBinding.load(value,'hyprneuro-ui.service',{str(target):hashlib.sha256(target.read_bytes()).hexdigest()})
        # Retain the original link inode so the filesystem cannot recycle it.
        alias=self.logical.parent;old_inode=alias.lstat().st_ino
        alias.rename(alias.with_name('retained-original-link'));alias.symlink_to(self.canonical.parent)
        self.assertNotEqual(alias.lstat().st_ino,old_inode)
        with self.assertRaises(PermissionError):binding.check()
        self.assertIn(str(alias),[entry['path'] for entry in json.loads(binding.chain_bytes)[0]])
    def test_private_unit_directory_records_and_fences_alias(self):self.private_directory_alias_replacement(False)
    def test_private_dropin_directory_records_and_fences_alias(self):self.private_directory_alias_replacement(True)
    def test_positive_logical_same_fd(self):self.assertEqual(self.load().read(self.sha)[1],self.target.stat().st_ino)
    def test_positive_canonical(self):
        v=copy.deepcopy(self.value);v['logical']=str(self.target);v['chain']=[paths._parents(self.target)]*2
        self.assertEqual(self.load(v).canonical,str(self.target))
    def test_replaced_link_same_text(self):
        binding=self.load();self.logical.parent.unlink();self.logical.parent.symlink_to(self.canonical.parent)
        with self.assertRaises(PermissionError):binding.check()
    def test_changed_link_redirect(self):
        binding=self.load();other=self.root/'other';other.mkdir();self.logical.parent.unlink();self.logical.parent.symlink_to(other)
        with self.assertRaises((PermissionError,FileNotFoundError)):binding.check()
    def test_target_replacement_same_bytes(self):
        binding=self.load();other=self.canonical/'replacement';other.write_bytes(b'fixture');other.chmod(0o600);os.replace(other,self.target)
        with self.assertRaises(PermissionError):binding.check()
    def test_mode_drift(self):
        binding=self.load();self.target.chmod(0o644)
        with self.assertRaises(PermissionError):binding.check()
    def test_final_symlink(self):
        other=self.canonical/'other';os.rename(self.target,other);self.target.symlink_to(other)
        with self.assertRaises(PermissionError):self.load()
    def test_hardlink(self):
        (self.canonical/'alias').hardlink_to(self.target)
        with self.assertRaises(PermissionError):self.load()
    def test_unknown_root_same_target(self):
        v=copy.deepcopy(self.value);alias=self.root/'unapproved';alias.symlink_to(self.canonical);v['logical']=str(alias/self.target.name)
        with self.assertRaises(PermissionError):self.load(v)
    def test_unknown_unit(self):
        with self.assertRaises(PermissionError):paths.UnitPathBinding.load(self.value,'lfm@text.service',self.catalog)
    def test_relative_link_text_same_target_denied(self):
        self.logical.parent.unlink();self.logical.parent.symlink_to('../dotfiles/systemd')
        with self.assertRaises(PermissionError):self.load()
    def test_parent_inode_replacement_denied(self):
        binding=self.load();old=self.canonical.parent.with_name('old-systemd')
        self.canonical.parent.rename(old);self.canonical.parent.mkdir()
        (old/'user').rename(self.canonical)
        with self.assertRaises(PermissionError):binding.check()
    def test_uid_drift_denied(self):
        binding=self.load();stamp=paths._stamp
        def changed(path):
            result=stamp(path)
            if path==self.target:result['uid']+=1
            return result
        with patch.object(paths,'_stamp',changed):
            with self.assertRaises(PermissionError):binding.check()
    def test_unknown_writable_parent_denied(self):
        binding=self.load();self.canonical.parent.chmod(0o777)
        with self.assertRaises(PermissionError):binding.check()
    def test_wrong_catalog_hash(self):
        with self.assertRaises(PermissionError):self.load().read('0'*64)
    def test_mutation_during_hash(self):
        from hyprneuro import identity_observer
        original=identity_observer.read_catalog_file;binding=self.load()
        def changed(*args,**kwargs):
            result=original(*args,**kwargs);self.target.chmod(0o644);return result
        with patch.object(identity_observer,'read_catalog_file',changed):
            with self.assertRaises(PermissionError):binding.read(self.sha)

if __name__=='__main__':unittest.main()
