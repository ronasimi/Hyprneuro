from dataclasses import asdict, fields, replace
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.settings import Settings
from hyprneuro.sidecar import build_parser, resolve_settings
from hyprneuro.tui import App, render, safe_text, settings_rows


class SettingsTests(unittest.TestCase):
    def test_atomic_private_save_validation_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'private/settings.json'
            Settings(alert_journal=True).save(path)
            self.assertTrue(Settings.load(path).alert_journal)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            self.assertEqual(list(path.parent.glob('.settings-*')), [])
            with self.assertRaisesRegex(ValueError, 'allow_ingest'):
                Settings.load(path).validate(prerequisites=True)
            with patch('os.replace', side_effect=OSError('failed')):
                with self.assertRaises(OSError):
                    Settings(allow_ingest=True).save(path)
            self.assertTrue(Settings.load(path).alert_journal)
            self.assertEqual(list(path.parent.glob('.settings-*')), [])
            link = path.parent/'link'
            link.symlink_to(path)
            with self.assertRaisesRegex(ValueError, 'Unsafe'):
                Settings().save(link)
            path.write_text('{"unexpected":true}')
            with self.assertRaises(ValueError):
                Settings.load(path)
        for kw in ({'allow_ingest':1}, {'retention_days':float('nan')}, {'embeddings_url':'x\x1b'}, {'excluded_apps':['']}):
            with self.assertRaises(ValueError):
                Settings(**kw).validate()

    def test_explicit_cli_overrides_saved_and_legacy_shorthand(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'settings.json'
            Settings(allow_ingest=True, alert_journal=True, retention_enabled=True).save(path)
            parser = build_parser()
            args = parser.parse_args(['serve','--config',str(path),'--no-alert-journal','--no-allow-ingest'])
            self.assertFalse(resolve_settings(args).allow_ingest)
            args = parser.parse_args(['serve','--no-settings','--allow-ingest','--alert','--no-notifications','--retention-days','0'])
            settings = resolve_settings(args)
            self.assertTrue(settings.alert_journal and settings.alert_network)
            self.assertFalse(settings.notifications or settings.retention_enabled)
            self.assertFalse(resolve_settings(parser.parse_args(['serve','--no-settings'])).allow_ingest)
            with self.assertRaisesRegex(ValueError,'requires watch_hyprland'):
                resolve_settings(parser.parse_args(['serve','--no-settings','--allow-ingest','--allow-capture']))
            with self.assertRaisesRegex(ValueError, 'embeddings'):
                resolve_settings(parser.parse_args(['serve','--no-settings','--semantic-enabled']))


class TuiTests(unittest.TestCase):
    def test_renderer_inert_control_codes_bounds_and_settings_truth(self):
        payload = '\x1b[2J\x1b]52;c;clipboard\x07\u009b31m\u202eevil\nline'
        lines = render('alerts', [payload]*10000, width=30, height=8, message=payload)
        self.assertLessEqual(len(lines), 8)
        self.assertTrue(all(len(line) <= 30 for line in lines))
        self.assertNotIn('\x1b', ''.join(lines))
        self.assertNotIn('\u009b', safe_text(payload))
        self.assertNotIn('\u202e', safe_text(payload))
        rows = settings_rows(Settings(allow_ingest=True), Settings(), {})
        self.assertIn('unsaved', rows[0])
        self.assertIn('unknown', rows[0])
        self.assertIn('restart/CLI override', settings_rows(Settings(),Settings(),{'allow_ingest':True})[0])
        self.assertIn('active=saved', settings_rows(Settings(),Settings(),asdict(Settings()))[0])

    def test_app_offline_settings_toggles_all_features_no_prerequisite_autogrants(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'settings.json'
            calls=[]
            def rpc(packet):
                calls.append(packet)
                raise OSError('offline')
            app = App(path, rpc)
            app.switch('settings')
            for i, f in enumerate(fields(Settings)):
                if f.type is bool:
                    app.selected = i
                    app.toggle()
                    self.assertTrue(getattr(app.draft, f.name))
            app.draft = Settings(allow_capture=True)
            app.save()
            self.assertTrue(Settings.load(path).allow_capture)
            self.assertFalse(Settings.load(path).allow_ingest)
            self.assertIn('Startup will refuse', app.message)
            self.assertTrue(all(c['action']=='health' for c in calls))
            Settings().save(path)
            with self.assertRaisesRegex(ValueError,'changed on disk'):
                app.save()

    def test_bounded_pagination_details_and_no_alert_management(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls=[]
            def rpc(packet):
                calls.append(packet)
                if packet['action']=='health': return {'active_settings':asdict(Settings())}
                if packet['action']=='details': return {'id':1,'message':'untrusted'}
                return [{'id':1,'source':'journal','time_ms':1,'message':'x'}]
            app = App(Path(tmp)/'settings.json',rpc)
            app.page(10000)
            self.assertEqual(app.offset,1000)
            app.open_record()
            self.assertEqual(app.view,'details')
            self.assertEqual(app.detail['message'],'untrusted')
            app.switch('alerts')
            self.assertEqual(calls[-1]['action'],'alerts')
            self.assertTrue(all(c['action'] in ('health','search','alerts','details') for c in calls))

    def test_noninteractive_cli_refuses_without_starting_service(self):
        env = {**os.environ, 'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
        result = subprocess.run([sys.executable,'-m','hyprneuro','tui'], env=env, capture_output=True,text=True,timeout=5)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('requires an interactive terminal',result.stderr)

    @unittest.skipUnless(os.name == 'posix', 'PTY/curses smoke requires POSIX')
    def test_curses_pty_smoke_offline_settings_and_quit(self):
        import fcntl
        import pty
        import select
        import struct
        import termios
        import time
        with tempfile.TemporaryDirectory() as tmp:
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 24, 120, 0, 0))
            env = {**os.environ, 'TERM':'xterm', 'XDG_RUNTIME_DIR':tmp,
                   'XDG_CONFIG_HOME':tmp, 'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
            proc = subprocess.Popen([sys.executable,'-m','hyprneuro','tui'], stdin=slave, stdout=slave, stderr=slave, env=env)
            os.close(slave)
            output = bytearray()
            try:
                deadline = time.monotonic()+5
                while b'Hyprneuro' not in output and time.monotonic()<deadline:
                    if select.select([master],[],[],.1)[0]:
                        output.extend(os.read(master,65536))
                self.assertIn(b'Hyprneuro',output)
                os.write(master,b'6q')
                self.assertEqual(proc.wait(timeout=5),0)
                self.assertFalse((Path(tmp)/'hyprneuro/settings.json').exists())
                self.assertFalse((Path(tmp)/'hyprharness/sidecar.sock').exists())
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
                os.close(master)
