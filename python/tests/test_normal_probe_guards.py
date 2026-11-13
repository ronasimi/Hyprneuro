"""Offline refusal checks: never invoke a model or open an evidence workspace."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class NormalProbeGuards(unittest.TestCase):
    def test_python_probe_refuses_missing_consent_or_owner_admission_override(self):
        self.check_guards(sys.executable, 'normal_stack_probe.py', 'BLOCKED:')

    @unittest.skipUnless(shutil.which('node'), 'node unavailable')
    def test_native_probe_refuses_missing_consent_or_owner_admission_override(self):
        self.check_guards('node', 'normal_d1_probe.mjs', 'Explicit isolated normal-only')

    def check_guards(self, executable, script, marker):
        cases = ({}, {'HYPRNEURO_NORMAL_PROBE':'1', 'HYPRNEURO_RESIDENCY_DIR':'/unapproved'},
                 {'HYPRNEURO_NORMAL_PROBE':'1', 'HYPRNEURO_PI_OWNER_ENABLE':'1'})
        for flags in cases:
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as d:
                workspace = Path(d)/'must-not-exist'
                result = subprocess.run([executable,str(ROOT/'scripts'/script),str(workspace)],
                    env={'PATH':os.environ['PATH'], **flags}, capture_output=True, text=True, timeout=5)
                self.assertNotEqual(result.returncode,0)
                self.assertIn(marker,result.stderr)
                self.assertEqual(result.stdout,'')
                self.assertFalse(workspace.exists())
