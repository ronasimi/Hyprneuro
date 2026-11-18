"""Private, bounded tests for the native alpha profile root (prepare_alpha_profile).

Stdlib unittest only (no new framework). Every test uses a private tmp root and
never writes to prod. The real native loaders (identity_root.load_launch_root,
identity_bootstrap) are exercised, not toy fixtures. The guard_root one-shot and
the full manager-context owner launch are reported as permission-pending (they
require the systemd manager namespace/units/credential, not a private leaf).
"""
import asyncio
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'scripts'))
sys.path.insert(0, str(REPO / 'python' / 'src'))
import prepare_alpha_profile as pap
import boundary_release as b
from hyprneuro import identity_root as ir
from hyprneuro import identity_bootstrap as ib
from hyprneuro import identity_unit_path as up


def _snapshot(path):
    out = {}
    for root, _dirs, files in os.walk(path):
        for name in files:
            p = Path(root) / name
            try:
                st = p.lstat()
                out[str(p)] = (st.st_ino, st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return out


class AlphaProfileTests(unittest.TestCase):
    def _mkroot(self):
        return Path(tempfile.mkdtemp(prefix='hn-alpha-test-')) / 'prof'

    def test_native_root_loads_and_schemas(self):
        prof = self._mkroot()
        try:
            info = pap.prepare_profile(prof)
            root = Path(info['root_record'])
            self.assertTrue(root.is_file())
            # Real DAG load passes.
            ir.load_launch_root(root, info['root_sha256'], info['generation'])
            # Native schemas are the production ones (not a toy).
            ctx = __import__('json').loads((root.parent / 'context.json').read_text())
            self.assertEqual(ctx['schema'], ib.CONTEXT_SCHEMA)
            man = __import__('json').loads((root.parent / 'manifest.json').read_text())
            self.assertEqual(man['schema'], up.SCHEMA)
            rec = __import__('json').loads(root.read_text())
            self.assertEqual(rec['schema'], ir.ROOT_SCHEMA)
            # bootstrap.env carries the exact manifest digest line.
            env = (root.parent / 'bootstrap.env').read_text()
            self.assertEqual(env, ib.DIGEST_VARIABLE + '=' + b.digest(root.parent / 'manifest.json') + '\n')
        finally:
            import shutil
            shutil.rmtree(prof.parent, ignore_errors=True)

    def test_second_attempt_denied(self):
        prof = self._mkroot()
        try:
            pap.prepare_profile(prof)
            with self.assertRaises(ValueError):
                pap.prepare_profile(prof)
        finally:
            import shutil
            shutil.rmtree(prof.parent, ignore_errors=True)

    def test_no_writes_outside_profile(self):
        base = Path(tempfile.mkdtemp(prefix='hn-alpha-out-'))
        prof = base / 'prof'
        sentinel = base / 'sentinel.txt'
        sentinel.write_text('x')
        before = _snapshot(base)
        try:
            pap.prepare_profile(prof)
            after = _snapshot(base)
            # No NEW file may appear outside prof/ (the sentinel is untouched).
            outside_new = [p for p in after if p not in before and not p.startswith(str(prof) + os.sep)]
            self.assertEqual(outside_new, [])
            self.assertEqual(after[str(sentinel)], before[str(sentinel)])
        finally:
            import shutil
            shutil.rmtree(base, ignore_errors=True)

    def test_symlink_source_not_followed(self):
        # A symlink inside the managed source pointing outside must not be
        # catalogued (rglob skips symlinks) and must not escape the profile.
        prof = self._mkroot()
        try:
            info = pap.prepare_profile(prof)
            man = __import__('json').loads((Path(info['manifest']) ).read_text())
            for path in man['files']:
                self.assertFalse(Path(path).is_symlink())
        finally:
            import shutil
            shutil.rmtree(prof.parent, ignore_errors=True)

    def test_descriptor_source_host_discovery(self):
        # P0 regression: descriptor.source must be the repo root so that
        # source/extensions/pi-owner/host.mjs exists (the owner execve target) and
        # PYTHONPATH=source/python/src resolves; the manifest catalog is python/src.
        prof = self._mkroot()
        try:
            info = pap.prepare_profile(prof)
            import json
            desc = json.loads((Path(info['owner']) / 'owner.json').read_text())
            host = Path(desc['source']) / 'extensions' / 'pi-owner' / 'host.mjs'
            self.assertTrue(host.is_file(), 'host.mjs missing under descriptor.source')
            self.assertEqual(b.digest(host), '187842d11e92841aadee7cce981ad044590c6388650bf52703a24fd24894d5db')
            self.assertTrue((Path(desc['source']) / 'python' / 'src').is_dir())
            # manifest catalog is still the python/src tree (unchanged by the fix)
            man = json.loads((Path(info['manifest'])).read_text())
            self.assertTrue(any(k.startswith(str(REPO / 'python' / 'src')) for k in man['files']))
        finally:
            import shutil
            shutil.rmtree(prof.parent, ignore_errors=True)

    def test_guard_root_one_shot_is_manager_scoped(self):
        """guard_root requires the manager namespace/units/credential; it is not
        a private leaf. Assert the source documents that contract (honest gap)."""
        src = (REPO / 'python' / 'src' / 'hyprneuro' / 'identity_root.py').read_text()
        self.assertIn('MAIN-only prestart validation and exclusive credential provisioning', src)
        self.assertIn('check_namespace', src)


if __name__ == '__main__':
    unittest.main()
