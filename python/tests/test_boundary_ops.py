"""Private-filesystem install_one failure-injection fixtures.

Exercises the NEW atomic install primitive in a private root only. It never
calls production units, the user manager, models, SQL, or any activation. It
covers: positive new-install, positive exact-replacement, wrong source pin,
cross-filesystem refusal, frozen-inode drift, pre-existing target refusal
(partial replacement), install-object loss, target-object drift, and no-rollback
on a failed replacement.
"""
import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'python/src'))
import boundary_release as b
import boundary_release_ops as ops
from hyprneuro.identity_unit_path import _stamp

def row(target, install, before=None):
    return dict(destination=str(target), install_object=b.pin(install),
                target_identity=_stamp(install), source=b.pin(install),
                before=before, before_identity=None)

class InstallOne(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name).resolve()
        # Mutable fixture files (0o600) so individual cases can mutate them.
        self.install=self.root/'install';b.write_new(self.install,b'payload',0o600)
        self.target=self.root/'target'

    def test_positive_new_install(self):
        ops.install_one(row(self.target,self.install))
        self.assertEqual(self.target.read_bytes(),b'payload')
        self.assertFalse(self.install.exists())  # final single-link, source gone

    def test_positive_exact_replacement(self):
        b.write_new(self.target,b'old');before=b.pin(self.target)
        r=row(self.target,self.install,before)
        r['before_identity']=_stamp(self.target)
        ops.install_one(r)
        self.assertEqual(self.target.read_bytes(),b'payload')
        self.assertFalse(self.install.exists())

    def test_wrong_source_pin_refused(self):
        r=row(self.target,self.install)      # pin of the original bytes
        self.install.write_bytes(b'mutated') # cooperative writer changed it
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_cross_filesystem_refused(self):
        # /run/user/<uid> is a user tmpfs distinct from the private /tmp root.
        runtime=pathlib.Path('/run/user')/str(os.getuid())
        foreign=runtime/('hn-ops-fs-'+str(os.getpid())+'-'+str(id(self)))
        b.write_new(foreign,b'payload');foreign.unlink()
        self.assertNotEqual(foreign.parent.stat().st_dev,self.root.stat().st_dev)
        foreign.write_bytes(b'payload')
        try:
            with self.assertRaises(ValueError):ops.install_one(row(self.target,foreign))
        finally:foreign.unlink(missing_ok=True)
        self.assertFalse(self.target.exists())

    def test_frozen_inode_drift_refused(self):
        r=row(self.target,self.install)
        r['target_identity']={**_stamp(self.install),'inode':_stamp(self.install)['inode']+1}
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_preexisting_target_refused_and_partial_preserved(self):
        b.write_new(self.target,b'preexisting')
        with self.assertRaises(OSError):ops.install_one(row(self.target,self.install))
        # no rollback, no clobber of the unexpected target
        self.assertEqual(self.target.read_bytes(),b'preexisting')

    def test_install_object_loss_refused(self):
        r=row(self.target,self.install);self.install.unlink()
        with self.assertRaises(FileNotFoundError):ops.install_one(r)
        self.assertFalse(self.target.exists())

    def test_replacement_target_drift_no_rollback(self):
        b.write_new(self.target,b'old',0o600);before=b.pin(self.target)
        r=row(self.target,self.install,before);r['before_identity']=_stamp(self.target)
        self.target.write_bytes(b'drifted')  # cooperative writer changed it
        with self.assertRaises(ValueError):ops.install_one(r)
        self.assertEqual(self.target.read_bytes(),b'drifted')
        self.assertTrue(self.install.exists())  # source object preserved, not consumed

class OperationPin(unittest.TestCase):
    def test_wrong_external_operation_literal_refused_before_host(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        bundle=pathlib.Path(tmp.name)/'bundle';bundle.mkdir()
        op=bundle/'operation.json';b.write_new(op,b'{}')
        with self.assertRaises(ValueError):ops.load(op,'0'*64)

if __name__=='__main__':unittest.main()
