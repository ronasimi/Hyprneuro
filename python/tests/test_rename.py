"""Hyprneuro naming and legacy-data compatibility; isolated from live state."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from unittest.mock import patch

from hyprneuro.browser_ingest import HOST_NAME, token_path
from hyprneuro.chrome_host import expected_origin, expected_origin_file, install
from hyprneuro.config import Config, state_dir
from hyprneuro.sidecar import paths, serve
from hyprneuro.sidecar_client import request
from hyprneuro.sidecar_store import SidecarStore

ROOT = Path(__file__).resolve().parents[2]


class RenameTests(unittest.TestCase):
    def test_package_and_entry_point_names(self):
        metadata = tomllib.loads((ROOT / 'python/pyproject.toml').read_text())
        self.assertEqual(metadata['project']['name'], 'hyprneuro')
        self.assertEqual(metadata['project']['scripts'], {
            'hyprneuro': 'hyprneuro.sidecar:main',
            'hyprneuro-chrome-host': 'hyprneuro.chrome_host:main',
            'hyprneuro-assistant': 'hyprneuro.assistant_cli:main',
        })
        package = json.loads((ROOT / 'package.json').read_text())
        self.assertEqual(package['name'], 'hyprneuro')
        for resource in package['pi']['extensions']:
            extension = ROOT / resource
            self.assertTrue(extension.is_file())
            self.assertIn('"hyprharness", "sidecar.sock"', extension.read_text())
        cli = subprocess.run([sys.executable, '-m', 'hyprneuro', '--help'],
                             capture_output=True, text=True, timeout=10)
        self.assertEqual(cli.returncode, 0, cli.stderr)
        self.assertIn('Hyprneuro', cli.stdout)

    def test_legacy_paths_and_model_config_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(root / 'runtime'),
                                         'XDG_STATE_HOME': str(root / 'state'),
                                         'XDG_CONFIG_HOME': str(root / 'config')}):
                self.assertEqual(paths(), (root / 'runtime/hyprharness/sidecar.sock',
                    root / 'state/hyprharness/sidecar/observations.sqlite3'))
                self.assertEqual(state_dir(), root / 'state/hyprharness')
                self.assertEqual(token_path(), root / 'runtime/hyprharness/chrome-ingest.token')
                self.assertEqual(expected_origin_file(), root / 'config/hyprharness/chrome_extension_id')
                config = root / 'config/hyprharness/config.toml'
                config.parent.mkdir(parents=True)
                config.write_text('decision_port = 9093\n')
                self.assertEqual(Config.load().decision_port, 9093)
                self.assertFalse((root / 'config/hyprneuro').exists())

    def test_default_state_path_still_uses_legacy_home(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'HOME': directory, 'XDG_RUNTIME_DIR': directory}, clear=True):
                self.assertEqual(paths()[1], Path(directory) /
                    '.local/state/hyprharness/sidecar/observations.sqlite3')

    def test_missing_runtime_still_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'XDG_RUNTIME_DIR'):
                paths()
            with self.assertRaisesRegex(RuntimeError, 'XDG_RUNTIME_DIR'):
                token_path()

    def test_chrome_registration_keeps_protocol_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            exe = base / 'hyprneuro-chrome-host'
            exe.touch()
            env = {'XDG_CONFIG_HOME': directory}
            with patch.dict(os.environ, env):
                manifest_path = install('a' * 32, 'chromium', executable=str(exe))
                self.assertEqual(HOST_NAME, 'org.ronasimi.hyprharness')
                self.assertEqual(manifest_path.name, 'org.ronasimi.hyprharness.json')
                manifest = json.loads(manifest_path.read_text())
                self.assertEqual(manifest['name'], HOST_NAME)
                self.assertEqual(manifest['path'], str(exe))
                self.assertIn('Hyprneuro', manifest['description'])
                self.assertEqual(expected_origin(), 'chrome-extension://' + 'a' * 32 + '/')
                with self.assertRaises(PermissionError):
                    install('b' * 32, 'chromium', executable=str(exe))
                install('b' * 32, 'chromium', executable=str(exe), replace=True)
                self.assertEqual(expected_origin(), 'chrome-extension://' + 'b' * 32 + '/')
            js = (ROOT / 'integrations/chrome/extension/background.js').read_text()
            self.assertIn('"' + HOST_NAME + '"', js)


class LegacyDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_rpc_reopens_legacy_records_without_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(root / 'runtime'),
                                         'XDG_STATE_HOME': str(root / 'state')}):
                socket, database = paths()
                # Seed the unchanged legacy on-disk schema before starting the new service.
                store = SidecarStore(database)
                url = 'https://example.test/legacy?private=token#saved'
                saved = store.record({'source': 'chrome', 'kind': 'tab_activated',
                    'time_ms': int(time.time() * 1000), 'title': 'Legacy observation',
                    'url': url}, _trusted_browser=True)
                store.close()
                stop = asyncio.Event()
                task = asyncio.create_task(serve(shutdown=stop))
                try:
                    for _ in range(100):
                        if task.done():
                            await task
                        if socket.exists():
                            break
                        await asyncio.sleep(0.01)
                    self.assertTrue(socket.exists())
                    health = await request({'action': 'health'})
                    self.assertEqual(health['service'], 'hyprneuro')
                    self.assertFalse(health['ingest_enabled'])
                    rows = await request({'action': 'search', 'query': 'Legacy'})
                    self.assertEqual([row['id'] for row in rows], [saved['id']])
                    self.assertTrue(rows[0]['url_verified'])
                    self.assertEqual((await request({'action': 'page_url', 'id': saved['id']}))['url'], url)
                    with self.assertRaisesRegex(RuntimeError, 'already running'):
                        await serve(shutdown=asyncio.Event())
                    self.assertEqual((await request({'action': 'health'}))['service'], 'hyprneuro')
                    self.assertFalse((root / 'state/hyprneuro').exists())
                finally:
                    stop.set()
                    await asyncio.wait_for(task, 3)
                self.assertTrue(database.exists())
                self.assertFalse(socket.exists())
