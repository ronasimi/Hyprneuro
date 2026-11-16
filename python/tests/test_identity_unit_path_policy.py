"""Schema3 integration: SYNTHETIC manager metadata, actual private process cohort.
Zero unit starts, grants, authorization calls or production writes.
"""
import copy
from pathlib import Path
from unittest.mock import patch
import unittest
import test_identity_observer as legacy
sha=legacy.sha
from hyprneuro import identity_unit_path as paths, identity_observer as observer, trusted_control

class BindingPolicy(unittest.IsolatedAsyncioTestCase):
    freeze=legacy.ObserverTests.freeze
    metadata=legacy.ObserverTests.metadata
    asyncTearDown=legacy.ObserverTests.asyncTearDown
    async def asyncSetUp(self):
        await legacy.ObserverTests.asyncSetUp(self)
        self.canonical=self.root/'dotfiles/systemd/user';self.canonical.mkdir(parents=True)
        self.logical=self.root/'config/systemd/user';self.logical.parent.parent.mkdir();self.logical.parent.symlink_to(self.canonical.parent)
        for key,value in [('LOGICAL_ROOT',self.logical),('CANONICAL_ROOT',self.canonical)]:
            p=patch.object(paths,key,value);p.start();self.addCleanup(p.stop)
        self.document['schema']=paths.SCHEMA;table={}
        for role,spec in self.specs.items():
            previous=Path(spec['fragments'][0]);target=self.canonical/spec['name'];previous.rename(target)
            raw=self.logical/spec['name'];spec['fragments']=[str(raw)]
            del self.document['files'][str(previous)];self.document['files'][str(target)]=sha(target)
            table[role]=[dict(logical=str(raw),canonical=str(target),target=paths._stamp(target),chain=[paths._parents(raw),paths._parents(target)])]
        self.document['unit_path_bindings']=table;self.freeze()
    async def test_positive_combined_actual_processes(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        with patch.object(trusted_control,'metadata',side_effect=self.metadata):
            cohort=await observer.SnapshotCollector(policy).observe('decision')
        self.assertEqual(set(cohort),{'ui','child','owner'})
        self.assertTrue(all('start' not in call for call in self.calls))
    async def test_changed_alias_after_metadata_await(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        async def changed(*args):
            value=await self.metadata(*args)
            self.logical.parent.unlink();self.logical.parent.symlink_to(self.canonical.parent)
            return value
        with patch.object(trusted_control,'metadata',side_effect=changed):
            with self.assertRaises(PermissionError):await observer.read_service(policy,'ui')
    async def test_unapproved_manager_spelling_same_target(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        async def changed(*args):
            raw=await self.metadata(*args)
            return raw.replace('FragmentPath='+str(self.logical),'FragmentPath='+str(self.canonical))
        with patch.object(trusted_control,'metadata',side_effect=changed):
            with self.assertRaises(PermissionError):await observer.read_service(policy,'ui')
    async def test_duplicate_canonical_object_rejected(self):
        self.specs['helper']['name']=self.specs['ui']['name']
        self.document['unit_path_bindings']['helper']=copy.deepcopy(self.document['unit_path_bindings']['ui'])
        self.freeze()
        with self.assertRaises(PermissionError):observer.ObserverPolicy(self.bootstrap)
    async def test_missing_role_binding_rejected(self):
        del self.document['unit_path_bindings']['helper'];self.freeze()
        with self.assertRaises(PermissionError):observer.ObserverPolicy(self.bootstrap)
    async def test_final_synchronous_fence_alias_loss(self):
        policy=observer.ObserverPolicy(self.bootstrap);self.logical.parent.unlink()
        with self.assertRaises((PermissionError,FileNotFoundError)):policy.revalidate_configuration()
    async def test_schema2_does_not_silently_accept_new_table(self):
        self.document['schema']='hyprneuro.identity-boundary/2';self.freeze()
        with self.assertRaises(PermissionError):observer.ObserverPolicy(self.bootstrap)

if __name__=='__main__':unittest.main()
