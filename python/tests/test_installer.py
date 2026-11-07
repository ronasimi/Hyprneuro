"""Installer smoke: real temporary venvs, mocked installs and systemctl, no network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

INSTALLER = Path(__file__).resolve().parents[2] / "scripts/install.sh"
SETUP = r'''
import json, os, pathlib, subprocess, sys
REAL_PYTHON = REPLACE_PYTHON

def log(args):
    with open(os.environ['CALL_LOG'], 'a') as stream:
        stream.write(json.dumps(args) + '\n')

def make_venv(path):
    root = pathlib.Path(path)
    subprocess.check_call([REAL_PYTHON, '-m', 'venv', '--without-pip', str(root)])
    exe = root / 'bin/hyprneuro'
    exe.write_text('#!' + REAL_PYTHON + '\nimport sys\nassert sys.argv[1:] == ["--help"]\n')
    exe.chmod(0o755)
    site = subprocess.check_output([str(root/'bin/python'), '-c',
        'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip()
    pip = pathlib.Path(site) / 'pip'
    pip.mkdir()
    (pip/'__init__.py').write_text('')
    (pip/'__main__.py').write_text('import json,os,sys\nwith open(os.environ["CALL_LOG"],"a") as f: '
        'f.write(json.dumps(["pip", *sys.argv[1:]])+"\\n")\n')
'''.replace('REPLACE_PYTHON', repr(sys.executable))


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.home = self.root / "home"
        self.home.mkdir()
        self.venv = self.home / 'isolated space % " $ venv'
        self.log = self.root / "calls"
        self.env = {**os.environ, "HOME": str(self.home), "PATH": str(self.bin),
                    "XDG_DATA_HOME": str(self.home / "data"),
                    "XDG_CONFIG_HOME": str(self.home / "config"), "CALL_LOG": str(self.log)}
        # No real uv/systemctl can be reached via PATH.
        for binary in ("dirname", "mkdir"):
            (self.bin / binary).symlink_to(shutil.which(binary))
        self._script("python3", SETUP + '''
log(['python', *sys.argv[1:]])
if sys.argv[1:3] == ['-m', 'venv']:
    make_venv(sys.argv[3])
else:
    os.execv(REAL_PYTHON, [REAL_PYTHON, *sys.argv[1:]])
''')
        self._script("uv", SETUP + '''
log(['uv', *sys.argv[1:]])
if os.environ.get('FAIL_UV') == sys.argv[1]: sys.exit(7)
if sys.argv[1] == 'venv': make_venv(sys.argv[-1])
''')
        for binary in ("systemctl", "grim", "loginctl", "journalctl", "notify-send"):
            self._script(binary, SETUP + '''
log([pathlib.Path(__file__).name, *sys.argv[1:]])
if os.environ.get('FAIL_SYSTEMCTL'): sys.exit(1)
''')

    def _script(self, name, body):
        path = self.bin / name
        path.write_text(f"#!{sys.executable}\n" + body)
        path.chmod(0o755)

    def run_installer(self, *args, **env):
        return subprocess.run(["/bin/bash", str(INSTALLER), "--venv", str(self.venv), *args],
                              env={**self.env, **env}, text=True, capture_output=True, timeout=20)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def unit(self):
        return self.home / "config/systemd/user/hyprneuro.service"

    def test_default_installs_isolated_executable_without_service(self):
        out = self.run_installer()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue((self.venv / "bin/hyprneuro").is_file())
        self.assertFalse(self.unit().exists())
        self.assertFalse(any(call[0] == "systemctl" for call in self.calls()))
        install = next(call for call in self.calls() if call[:3] == ["uv", "pip", "install"])
        self.assertEqual(install[3:5], ["--python", str(self.venv / "bin/python")])
        self.assertNotIn("--system", install)
        self.assertIn(str(self.venv / "bin/hyprneuro"), out.stdout)

    def test_unit_default_is_read_only_without_enable_or_start(self):
        out = self.run_installer("--install-service")
        self.assertEqual(out.returncode, 0, out.stderr)
        unit = self.unit().read_text()
        self.assertNotIn("--allow-ingest", unit)
        self.assertNotIn("--watch-hyprland", unit)
        self.assertIn('isolated space %% \\" $$ venv', unit)
        self.assertEqual([c for c in self.calls() if c[0] == "systemctl"],
                         [["systemctl", "--user", "show-environment"],
                          ["systemctl", "--user", "daemon-reload"]])

    @unittest.skipUnless(shutil.which("systemd-analyze"), "systemd-analyze not installed")
    def test_generated_unit_parses_with_actual_systemd(self):
        out = self.run_installer("--install-service")
        self.assertEqual(out.returncode, 0, out.stderr)
        result = subprocess.run([shutil.which("systemd-analyze"), "--user", "verify", str(self.unit())],
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ExecStart=/usr/bin/env -- ", self.unit().read_text())

    def test_explicit_features_enable_and_start(self):
        out = self.run_installer("--install-service", "--allow-ingest", "--alert",
                                 "--retention-days", "7", "--enable", "--start")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn('"--allow-ingest" "--alert" "--retention-days" "7"', self.unit().read_text())
        self.assertIn(["systemctl", "--user", "enable", "hyprneuro.service"], self.calls())
        self.assertIn(["systemctl", "--user", "restart", "hyprneuro.service"], self.calls())

    def test_invalid_flags_fail_before_install(self):
        for args in (("--alert",), ("--enable",), ("--install-service", "--alert"),
                     ("--install-service", "--retention-days", "nan"),
                     ("--install-service", "--allow-ingest", "--allow-capture"),
                     ("--venv", "relative"), ("--bad-option",), ("--python",)):
            with self.subTest(args=args):
                out = self.run_installer(*args)
                self.assertNotEqual(out.returncode, 0)
                self.assertFalse(self.venv.exists())
                self.assertFalse(self.unit().exists())

    def test_install_failure_never_falls_back_to_system_python(self):
        out = self.run_installer("--install-service", FAIL_UV="pip")
        self.assertNotEqual(out.returncode, 0)
        self.assertFalse(self.unit().exists())
        self.assertFalse(any("pip" in c for c in self.calls() if c[0] == "python"))

    def test_diagnostics_for_missing_prerequisite_and_user_manager(self):
        (self.bin / "notify-send").unlink()
        out = self.run_installer("--install-service", "--allow-ingest", "--alert")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Missing prerequisite: notify-send", out.stderr)
        self.assertFalse(self.venv.exists())
        out = self.run_installer("--install-service", FAIL_SYSTEMCTL="1")
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Cannot contact systemd user manager", out.stderr)
        self.assertFalse(self.unit().exists())

    def test_refuses_non_venv_directory(self):
        self.venv.mkdir()
        out = self.run_installer()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Refusing non-venv directory", out.stderr)

    def test_refuses_existing_venv_with_system_packages(self):
        out = self.run_installer()
        self.assertEqual(out.returncode, 0, out.stderr)
        config = self.venv / "pyvenv.cfg"
        config.write_text(config.read_text().replace("include-system-site-packages = false",
                                                    "include-system-site-packages = true"))
        out = self.run_installer()
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("Refusing venv with system site-packages enabled", out.stderr)

    def test_python_venv_fallback_uses_venv_pip(self):
        (self.bin / "uv").unlink()
        out = self.run_installer()
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(any(c[:2] == ["pip", "install"] for c in self.calls()))
