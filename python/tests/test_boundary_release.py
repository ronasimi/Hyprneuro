"""Private filesystem fixture tests; never calls production units or model code."""
import importlib.util
import pathlib
import tempfile
import time
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('boundary_release',pathlib.Path(__file__).resolve().parents[2]/'scripts/boundary_release.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class Files(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name).resolve()
        self.source=self.root/'source';b.write_new(self.source,b'new')
        self.target=self.root/'target'
    def entry(self,before=None):
        return dict(destination=str(self.target),source=b.pin(self.source),before=before,mode=0o500,operation_id='fixture')
    def test_new_install_and_no_replay(self):
        b.replace_target(self.entry());self.assertEqual(self.target.read_bytes(),b'new')
        with self.assertRaises(ValueError):b.replace_target(self.entry())
    def test_exact_replacement(self):
        b.write_new(self.target,b'old');old=b.pin(self.target)
        b.replace_target(self.entry(old));self.assertEqual(self.target.read_bytes(),b'new')
    def test_unknown_replacement_refused(self):
        b.write_new(self.target,b'old');old=b.pin(self.target)
        self.target.chmod(0o600);self.target.write_bytes(b'changed')
        with self.assertRaises(ValueError):b.replace_target(self.entry(old))
        self.assertEqual(self.target.read_bytes(),b'changed')
    def test_symlink_refused(self):
        self.target.symlink_to(self.source)
        with self.assertRaises(ValueError):b.replace_target(self.entry())
    def test_hardlink_refused(self):
        self.target.hardlink_to(self.source)
        with self.assertRaises(ValueError):b.pin(self.source)
    def test_source_loss_refused(self):
        entry=self.entry();self.source.unlink()
        with self.assertRaises(FileNotFoundError):b.replace_target(entry)
        self.assertFalse(self.target.exists())
    def test_partial_install_preserved_not_rolled_back(self):
        b.replace_target(self.entry());second=self.root/'second';b.write_new(second,b'unknown')
        entry=self.entry();entry['destination']=str(second)
        with self.assertRaises(ValueError):b.replace_target(entry)
        self.assertEqual(self.target.read_bytes(),b'new');self.assertEqual(second.read_bytes(),b'unknown')
    def test_expired_deadline_no_subprocess(self):
        with patch.object(b.subprocess,'run') as run:
            with self.assertRaises(TimeoutError):b.command(['/usr/bin/false'],time.monotonic()-1)
            run.assert_not_called()

if __name__=='__main__':unittest.main()
