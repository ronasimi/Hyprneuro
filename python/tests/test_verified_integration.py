"""Integrated prompt/event/privacy boundary; disposable sockets, no live models."""
import asyncio
import base64
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hyprneuro.agent import DEFAULT_SYSTEM
from hyprneuro.sidecar import SidecarServer, serve
from hyprneuro.sidecar_client import request
from hyprneuro.sidecar_store import SidecarStore


class VerifiedIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_skill_snapshot_without_ingest_capture_or_execution_grants(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SidecarStore(Path(directory) / 'db')
            self.addCleanup(store.close)
            server = SidecarServer(store, assistant_enabled=True)
            server.skills.register({'app_id': 'kitty', 'body': 'APP_REFERENCE'})
            server.app_skill_context.activate('kitty')
            context = server.dispatch({'action': 'app_context'})
            self.assertEqual(context['active_skill']['skill']['body'], 'APP_REFERENCE')
            self.assertFalse(context['active_skill']['execution_permission'])
            health = server.dispatch({'action': 'health'})
            for key in ('ingest_enabled', 'capture_enabled', 'on_demand_enabled',
                        'browser_enabled', 'models_invoked'):
                self.assertFalse(health[key])
            self.assertEqual(health['collectors'], {})
            self.assertEqual(server.broker.list(), [])
            self.assertIsNone(server.watcher)
            self.assertIsNone(server.desktop_controller)
            with self.assertRaises(PermissionError):
                await server.dispatch_async({'action': 'omni_observe', 'purpose': 'both'})
            with self.assertRaises(PermissionError):
                server.dispatch({'action': 'record', 'event': {}})

    async def test_shared_focus_to_actual_chat_ipc_preserves_prompt_and_native_wav(self):
        class Desktop:
            callback = None
            readers = 0
            app = 'kitty'

            async def query(self, name):
                return {'class': self.app, 'address': '0x1', 'workspace': {'id': 1}}

            async def events(self, callback):
                self.readers += 1
                self.callback = callback
                await asyncio.Event().wait()

        prompts = []

        async def stream(messages, **kwargs):
            prompts.append(messages)
            yield {'type': 'delta', 'channel': 'answer', 'text': 'fixture'}

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills = root / 'skills'
            skills.mkdir()
            for app, body in (('kitty', 'OLD_SKILL'), ('thunar', 'CURRENT_SKILL')):
                (skills / f'{app}.json').write_text(json.dumps({'app_id': app, 'body': body}))
            socket = root / 'runtime' / 'sidecar.sock'
            desktop = Desktop()
            stop = asyncio.Event()
            # Existing focus intake requires metadata-ingest consent, NOT Recall capture.
            task = asyncio.create_task(serve(
                allow_ingest=True, watch_hyprland=True, assistant_enabled=True,
                skills_dir=skills, desktop=desktop, socket_path=socket,
                db_path=root / 'state' / 'db', shutdown=stop))
            try:
                for _ in range(100):
                    if desktop.callback:
                        break
                    await asyncio.sleep(.01)
                self.assertIsNotNone(desktop.callback)
                desktop.app = 'thunar'
                await desktop.callback('activewindowv2', '0x1')
                for _ in range(100):
                    context = await request({'action': 'app_context'}, socket_path=socket)
                    if context['active_skill']['app_id'] == 'thunar':
                        break
                    await asyncio.sleep(.01)
                self.assertEqual(context['active_skill']['app_id'], 'thunar')
                self.assertEqual(desktop.readers, 1)
                context['active_skill'] = {'body': 'CLIENT_FORGED_SKILL'}
                data = struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', 84, b'WAVE', b'fmt ',
                                   16, 1, 1, 24000, 48000, 2, 16, b'data', 48) + bytes(48)
                encoded = base64.b64encode(data).decode()

                async def chat(media):
                    reader, writer = await asyncio.open_unix_connection(socket)
                    try:
                        writer.write(json.dumps({'action': 'agent_chat', 'message': 'test',
                                                 'context': context, 'media': media}).encode() + b'\n')
                        await writer.drain()
                        return [json.loads(line) for line in (await asyncio.wait_for(reader.read(), 3)).splitlines()]
                    finally:
                        writer.close()
                        await writer.wait_closed()

                with patch('hyprneuro.agent.stream_chat', stream):
                    frames = await chat({'mime': 'audio/wav', 'data': encoded})
                    self.assertEqual(frames[-1]['type'], 'done')
                    system = prompts[0][0]['content']
                    self.assertTrue(system.startswith(DEFAULT_SYSTEM))
                    self.assertEqual(system.count('CURRENT_SKILL'), 1)
                    self.assertNotIn('OLD_SKILL', system)
                    self.assertNotIn('CLIENT_FORGED_SKILL', system)
                    self.assertIn('"execution_permission": false', system)
                    self.assertEqual(prompts[0][-1]['content'][1], {
                        'type': 'input_audio', 'input_audio': {'data': encoded, 'format': 'wav'}})
                    self.assertEqual(base64.b64decode(encoded), data)
                    for media in ({'mime': 'video/mp4', 'data': encoded},
                                  {'mime': 'audio/wav', 'data': 'invalid'}):
                        self.assertEqual((await chat(media))[0]['type'], 'error')
                    self.assertEqual(len(prompts), 1)  # rejected media never reaches inference
                health = await request({'action': 'health'}, socket_path=socket)
                self.assertFalse(health['capture_enabled'])
                self.assertFalse(health['on_demand_enabled'])
                self.assertNotIn('capture', health['collectors'])
                with self.assertRaisesRegex(RuntimeError, 'observations are disabled'):
                    await request({'action': 'omni_observe', 'purpose': 'both'}, socket_path=socket)
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)
            self.assertFalse(socket.exists())
