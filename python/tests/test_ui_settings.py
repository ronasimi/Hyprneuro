"""UI preferences persist without granting or activating any feature consent."""
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.settings import Settings
from hyprneuro.sidecar import serve
from hyprneuro.sidecar_client import request


class UiSettingsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.socket = root/'runtime/sidecar.sock'
        self.config = root/'settings/settings.json'
        self.stop = asyncio.Event()
        self.service = asyncio.create_task(serve(
            socket_path=self.socket, db_path=root/'state/db.sqlite3',
            settings_file=self.config, shutdown=self.stop))
        for _ in range(100):
            if self.socket.exists():
                break
            await asyncio.sleep(.01)

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.service, 3)
        self.tmp.cleanup()

    async def rpc(self, **packet):
        if packet.get('action') == 'ui_settings_save':
            packet.setdefault('ui_panel_opacity', .90)
            packet.setdefault('alert_journal', False)
            packet.setdefault('alert_network', False)
            packet.setdefault('alert_resources', False)
            if isinstance(packet.get('expected'), dict):
                packet['expected'].setdefault('ui_panel_opacity', .90)
                packet['expected'].setdefault('alert_journal', False)
                packet['expected'].setdefault('alert_network', False)
                packet['expected'].setdefault('alert_resources', False)
        return await request(packet, socket_path=self.socket)

    async def test_default_save_reload_and_no_consent_changes(self):
        saved = await self.rpc(action='ui_settings_get')
        self.assertEqual(saved, {'ui_transcript_size': 'restored', 'ui_autoscroll': True, 'ui_panel_opacity': .90, 'alert_journal': False, 'journal_active': False, 'journal_task': 'off', 'alert_network': False, 'network_active': False, 'network_task': 'off', 'alert_resources': False, 'resources_active': False, 'resources_task': 'off'})
        self.assertFalse(self.config.exists())  # reading never writes defaults
        before = await self.rpc(action='health')
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, expected={'ui_transcript_size':'restored','ui_autoscroll':True})
        self.assertEqual(result, {'ui_transcript_size': 'full', 'ui_autoscroll': True, 'ui_panel_opacity': .90, 'alert_journal': False, 'journal_active': False, 'journal_task': 'off', 'alert_network': False, 'network_active': False, 'network_task': 'off', 'alert_resources': False, 'resources_active': False, 'resources_task': 'off'})
        self.assertEqual(await self.rpc(action='ui_settings_get'), result)
        self.assertEqual(json.dumps(asdict(Settings.load(self.config)), sort_keys=True),
                         json.dumps(asdict(Settings(ui_transcript_size='full')), sort_keys=True))
        self.assertEqual(self.config.stat().st_mode & 0o777, 0o600)
        after = await self.rpc(action='health')
        self.assertEqual(before['active_settings'], after['active_settings'])
        self.assertEqual(after['collectors'], {})
        self.assertFalse(after['capture_enabled'])

    async def test_only_valid_appearance_field_is_editable(self):
        for value in ('huge', True, 1, [], None):
            with self.assertRaisesRegex(RuntimeError, 'must be'):
                await self.rpc(action='ui_settings_save', ui_transcript_size=value, ui_autoscroll=True, expected={'ui_transcript_size':'restored','ui_autoscroll':True})
        with self.assertRaisesRegex(RuntimeError, 'Only implemented appearance'):
            await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, expected={'ui_transcript_size':'restored','ui_autoscroll':True}, allow_capture=True)
        self.assertFalse(self.config.exists())

    async def test_conflict_and_failed_write_preserve_saved(self):
        Settings(ui_transcript_size='compact', alert_journal=True).save(self.config)
        original = self.config.read_bytes()
        with self.assertRaisesRegex(RuntimeError, 'Reload'):
            await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, expected={'ui_transcript_size':'restored','ui_autoscroll':True})
        self.assertEqual(self.config.read_bytes(), original)
        with patch('hyprneuro.settings.os.replace', side_effect=OSError('fixture write refusal')):
            with self.assertRaisesRegex(RuntimeError, 'fixture write refusal'):
                await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, alert_journal=True, expected={'ui_transcript_size':'compact','ui_autoscroll':True,'alert_journal':True})
        self.assertEqual(self.config.read_bytes(), original)
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, alert_journal=True, expected={'ui_transcript_size':'compact','ui_autoscroll':True,'alert_journal':True})
        self.assertEqual(result['ui_transcript_size'], 'full')
        self.assertTrue(Settings.load(self.config).alert_journal)  # existing unrelated saved values preserved

    async def test_autoscroll_boolean_persistence_and_validation(self):
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
                                ui_autoscroll=False, expected={'ui_transcript_size':'restored', 'ui_autoscroll':True})
        self.assertFalse(result['ui_autoscroll'])
        self.assertFalse(Settings.load(self.config).ui_autoscroll)
        for value in ('off', 0, None):
            with self.assertRaisesRegex(RuntimeError, 'must be boolean'):
                await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
                               ui_autoscroll=value, expected={k:result[k] for k in ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')})
        self.assertFalse(Settings.load(self.config).ui_autoscroll)

    async def test_journal_draft_save_is_not_activation(self):
        previous = await self.rpc(action='ui_settings_get')
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
            ui_autoscroll=True, alert_journal=True,
            expected={k:previous[k] for k in ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')})
        self.assertTrue(Settings.load(self.config).alert_journal)
        self.assertFalse(Settings.load(self.config).allow_ingest)  # prerequisite never auto-granted
        self.assertTrue(result['alert_journal'])
        self.assertFalse(result['journal_active'])
        self.assertEqual(result['journal_task'], 'off')
        self.assertEqual((await self.rpc(action='health'))['collectors'], {})
        with self.assertRaisesRegex(RuntimeError, 'must be boolean'):
            await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
                ui_autoscroll=True, alert_journal='yes',
                expected={k:result[k] for k in ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')})

    async def test_network_consent_is_independent_and_pending(self):
        previous = await self.rpc(action='ui_settings_get')
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
            ui_autoscroll=True, alert_network=True,
            expected={k:previous[k] for k in ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')})
        self.assertTrue(result['alert_network'])
        self.assertFalse(result['network_active'])
        self.assertEqual(result['network_task'], 'off')
        saved = Settings.load(self.config)
        self.assertFalse(saved.alert_journal or saved.alert_resources or saved.allow_ingest or saved.notifications)
        self.assertEqual((await self.rpc(action='health'))['collectors'], {})

    async def test_resource_consent_is_independent_and_pending(self):
        previous = await self.rpc(action='ui_settings_get')
        result = await self.rpc(action='ui_settings_save', ui_transcript_size='restored',
            ui_autoscroll=True, alert_resources=True,
            expected={k:previous[k] for k in ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')})
        self.assertTrue(result['alert_resources'])
        self.assertFalse(result['resources_active'])
        self.assertEqual(result['resources_task'], 'off')
        saved = Settings.load(self.config)
        self.assertFalse(saved.alert_journal or saved.alert_network or saved.allow_ingest or saved.notifications)
        self.assertEqual((await self.rpc(action='health'))['collectors'], {})

    async def test_unsafe_file_refused(self):
        self.config.parent.mkdir()
        target = self.config.parent/'other.json'
        target.write_text('{}')
        self.config.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            await self.rpc(action='ui_settings_get')
        with self.assertRaisesRegex(RuntimeError, 'Unsafe'):
            await self.rpc(action='ui_settings_save', ui_transcript_size='full', ui_autoscroll=True, expected={'ui_transcript_size':'restored','ui_autoscroll':True})
        self.assertEqual(target.read_text(), '{}')

    async def test_panel_opacity_validation_persistence_and_conflict(self):
        previous = await self.rpc(action='ui_settings_get')
        editable = ('ui_transcript_size','ui_autoscroll','ui_panel_opacity','alert_journal','alert_network','alert_resources')
        args = {k:previous[k] for k in editable}
        expected = args.copy()
        for invalid in (True, False, None, '0.9', .19, 1.01, float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(RuntimeError):
                await self.rpc(action='ui_settings_save', **dict(args, ui_panel_opacity=invalid), expected=expected)
        changed = await self.rpc(action='ui_settings_save', **dict(args, ui_panel_opacity=.85), expected=expected)
        self.assertEqual(changed['ui_panel_opacity'], .85)
        self.assertEqual(Settings.load(self.config).ui_panel_opacity, .85)
        self.assertFalse(Settings.load(self.config).allow_capture)
        with self.assertRaises(RuntimeError):
            await self.rpc(action='ui_settings_save', **args, expected=expected)
        self.assertEqual(Settings.load(self.config).ui_panel_opacity, .85)
