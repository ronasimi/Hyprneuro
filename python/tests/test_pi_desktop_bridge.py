"""Real stdio → established authenticated client → mock single owner. No GUI."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.pi_owner_client import PiOwnerClient, MAX_FRAME
from hyprneuro.pi_desktop_bridge import DesktopBridge

REPO = Path(__file__).resolve().parents[2]


class DesktopBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.owner_dir = self.root / 'owner'
        self.log = self.root / 'requests'
        self.owner = await asyncio.create_subprocess_exec(
            'node', str(REPO / 'ui/tests/pi_owner_fixture.mjs'), str(self.owner_dir), str(self.log),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        self.assertEqual(await asyncio.wait_for(self.owner.stdout.readline(), 3), b'ready\n')
        self.bridge = None
        self.packets = []

    async def asyncTearDown(self):
        if self.bridge:
            if self.bridge.returncode is None:
                self.bridge.stdin.close()
            try:
                await asyncio.wait_for(self.bridge.wait(), 4)
            except TimeoutError:
                self.bridge.kill()
                await self.bridge.wait()
            err = await self.bridge.stderr.read()
            self.assertEqual(err, b'')
        if self.owner.returncode is None:
            self.owner.terminate()
        await asyncio.wait_for(self.owner.wait(), 4)
        self.assertEqual(await self.owner.stderr.read(), b'')
        self.tmp.cleanup()

    async def launch(self, **overrides):
        env = dict(os.environ, PYTHONPATH=str(REPO / 'python/src'), HYPRNEURO_PI_UI='1',
                   HYPRNEURO_PI_OWNER_DIR=str(self.owner_dir))
        env.update(overrides)
        self.bridge = await asyncio.create_subprocess_exec(
            '/usr/bin/python3', '-m', 'hyprneuro.pi_desktop_bridge', env=env,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

    async def send(self, op, **fields):
        self.bridge.stdin.write((json.dumps(dict(op=op, **fields), ensure_ascii=False)+'\n').encode())
        await self.bridge.stdin.drain()

    async def until(self, kind, op=None):
        async with asyncio.timeout(5):
            while line := await self.bridge.stdout.readline():
                packet = json.loads(line)
                self.packets.append(packet)
                if (kind is None or packet['type'] == kind) and (op is None or packet.get('op') == op):
                    return packet
        self.fail(f'No {kind}/{op}: {self.packets}')

    async def consent(self):
        packet = await self.until('host_event')
        self.assertEqual(packet['event']['type'], 'consent')
        return packet['event']

    def requests(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    async def test_fresh_consent_denial_on_off_and_no_autoapprove(self):
        await self.launch()
        self.assertEqual((await self.until('status'))['result']['state'], 'off')
        await self.send('on')
        q = await self.consent()
        self.assertIn('fixture-task', q['detail'])
        # Status bypasses the pending transaction. No on result before human answer.
        await self.send('status')
        self.assertEqual((await self.until('status'))['result']['owner_phase'], 'transition')
        self.assertFalse(any(p.get('type') == 'result' and p.get('op') == 'on' for p in self.packets))
        await self.send('consent', answer_id=q['id'], allowed=False)
        await self.until('error', 'on')
        await self.send('status')
        self.assertEqual((await self.until('status'))['result']['state'], 'off')
        await self.send('on')
        q2 = await self.consent()
        self.assertNotEqual(q['id'], q2['id'])
        await self.send('consent', answer_id=q['id'], allowed=True)
        await self.until('error', 'consent')
        await self.send('consent', answer_id=q2['id'], allowed=True)
        self.assertEqual((await self.until('result', 'on'))['result']['state'], 'on')
        await self.send('off')
        self.assertEqual((await self.until('result', 'off'))['result']['state'], 'off')

    async def test_tools_reasoning_untrusted_commands_and_history_owner(self):
        await self.launch()
        await self.until('status')
        await self.send('chat', text='tool')
        q = await self.consent()
        self.assertIn('EXACT fixture content', q['detail'])
        await self.send('consent', answer_id=q['id'], allowed=False)
        self.assertTrue((await self.until('result', 'chat'))['result']['settled'])
        events = [p['event'] for p in self.packets if p['type'] == 'event']
        self.assertTrue(any(e.get('channel') == 'reasoning' for e in events))
        self.assertTrue(any(e['type'] == 'tool_execution_end' and e['isError'] for e in events))
        await self.send('chat', text='injection')
        await self.until('result', 'chat')
        self.assertTrue(any(p.get('event', {}).get('text') == '/moe on' for p in self.packets))
        self.assertFalse(any(r['op'] == 'on' for r in self.requests()))
        # No transcript/history/context/credentials are ever sent by the adapter.
        self.assertEqual([r for r in self.requests() if r['op'] == 'native_prompt'],
                         [{'op': 'native_prompt', 'text': 'tool'}, {'op': 'native_prompt', 'text': 'injection'}])
        await self.send('chat', text='error')
        await self.until('result', 'chat')
        self.assertTrue(any(p.get('event', {}).get('stopReason') == 'error' for p in self.packets))

    async def test_chat_during_pending_on_is_serialized_and_off_cancels(self):
        await self.launch()
        await self.until('status')
        await self.send('on')
        await self.consent()
        await self.send('chat', text='queued')
        await self.send('off')
        # Separate authenticated connections have no response-order guarantee.
        # In particular off may settle before a new chat finishes authentication.
        expected = {('error', 'on'), ('result', 'chat'), ('result', 'off')}
        seen = set()
        while seen != expected:
            packet = await self.until(None)
            key = (packet['type'], packet.get('op'))
            if key in expected:
                seen.add(key)
        self.assertEqual(sum(r['op'] == 'native_prompt' for r in self.requests()), 1)

    async def test_cancel_preserves_control_and_exposes_failed_owner(self):
        await self.launch()
        await self.until('status')
        await self.send('chat', text='slow')
        await self.until('event')
        await self.send('cancel')
        await self.until('error', 'chat')
        await self.send('status')
        self.assertEqual((await self.until('status'))['result']['owner_phase'], 'failed')
        self.assertEqual(sum(r['op'] == 'native_prompt' for r in self.requests()), 1)

    async def test_disconnect_no_replay_or_fallback(self):
        await self.launch()
        await self.until('status')
        await self.send('chat', text='disconnect')
        await self.until('unavailable')
        await asyncio.wait_for(self.bridge.wait(), 4)
        self.assertEqual(sum(r['op'] == 'native_prompt' for r in self.requests()), 1)

    async def test_stale_owner_frame_fields_and_default_disabled(self):
        await self.launch(HYPRNEURO_PI_UI='0')
        self.assertEqual(await asyncio.wait_for(self.bridge.wait(), 3), 2)
        self.assertEqual(await self.bridge.stdout.read(), b'')
        await self.launch()
        await self.until('status')
        (self.owner_dir / 'mode').write_text('stale')
        await self.send('status')
        self.assertEqual((await self.until('status'))['result']['state'], 'failed')
        await self.send('chat', text='x', media={'data': 'never-drop'})
        await self.until('error', 'chat')
        self.assertFalse(any(r['op'] == 'native_prompt' for r in self.requests()))
        self.bridge.stdin.write(b'x' * (MAX_FRAME+2)+b'\n')
        await self.bridge.stdin.drain()
        await self.until('unavailable')
        await asyncio.wait_for(self.bridge.wait(), 3)

    async def test_auth_failure_no_mutation_and_private_credentials(self):
        (self.owner_dir / 'control.key').write_bytes(b'X'*32)
        await self.launch()
        await self.until('unavailable')
        self.assertEqual(self.requests() if self.log.exists() else [], [])
        self.assertNotIn('X'*32, json.dumps(self.packets))
        await asyncio.wait_for(self.bridge.wait(), 3)

    async def test_oversize_host_consent_denied_without_partial_approval(self):
        (self.owner_dir / 'mode').write_text('oversize-consent')
        await self.launch()
        await self.until('status')
        await self.send('on')
        await self.until('notice')
        await self.until('error', 'on')
        self.assertFalse(any(p['type'] == 'host_event' for p in self.packets))
        await self.send('status')
        self.assertEqual((await self.until('status'))['result']['state'], 'off')

    async def test_missing_owner_is_unavailable_never_created(self):
        missing = self.root / 'not-an-owner'
        await self.launch(HYPRNEURO_PI_OWNER_DIR=str(missing))
        await self.until('unavailable')
        await asyncio.wait_for(self.bridge.wait(), 3)
        self.assertFalse(missing.exists())
        self.assertFalse(self.log.exists())

    async def test_cancel_targets_original_connection_not_a_later_chat(self):
        class Client:
            closed = False
            async def close(self):
                self.closed = True
        original, later = Client(), Client()
        packets = []
        async def send(packet):
            packets.append(packet)
        bridge = DesktopBridge(self.owner_dir, send)
        bridge.chat_client = original
        async def deny_pending():
            # An old chat may settle while cancel awaits a consent response.
            bridge.chat_client = later
            await asyncio.sleep(0)
        bridge.deny_pending = deny_pending
        await bridge.request({'op': 'cancel'})
        self.assertTrue(original.closed)
        self.assertFalse(later.closed)
        self.assertEqual(packets[-1]['type'], 'result')

    async def test_utf8_multibyte_text_reaches_native_submission(self):
        await self.launch()
        await self.until('status')
        texts = ['漢' * 11000, '漢' * 16000, '😀' * 8000]
        for text in texts:
            await self.send('chat', text=text)
            self.assertTrue((await self.until('result', 'chat'))['result']['settled'])
        self.assertEqual([r['text'] for r in self.requests() if r['op'] == 'native_prompt'], texts)

    async def test_utf8_frame_exact_limit_includes_newline_and_rejects_before_write(self):
        # Supplementary scalar + escaped controls + ASCII reaches exactly64KiB
        # while remaining below the independent16000 UTF-16-unit owner limit.
        text = '😀' + '\x01' * 10910 + 'abc'
        client = await PiOwnerClient.connect(self.owner_dir)
        try:
            with patch.object(client.writer, 'write', wraps=client.writer.write) as write:
                self.assertTrue((await client.call('chat', text=text))['settled'])
                data = write.call_args.args[0]
                self.assertEqual(len(data), MAX_FRAME)
                self.assertTrue(data.endswith(b'\n'))
                self.assertIn('😀'.encode('utf-8'), data)
                self.assertEqual(json.loads(data)['text'], text)
                writes = write.call_count
                with self.assertRaisesRegex(ValueError, 'frame exceeds bound'):
                    await client.call('chat', text=text + 'x')
                self.assertEqual(write.call_count, writes)
                self.assertEqual(client.pending, {})
            self.assertEqual([r['text'] for r in self.requests() if r['op'] == 'native_prompt'], [text])
        finally:
            await client.close()

    async def test_supplementary_limit_is_owner_utf16_units_not_python_codepoints(self):
        await self.launch()
        await self.until('status')
        text = '😀' * 8001
        self.assertLess(len(text), 16000)
        self.assertEqual(len(text.encode('utf-16-le')) // 2, 16002)
        await self.send('chat', text=text)
        await self.until('error', 'chat')
        self.assertFalse(any(r['op'] == 'native_prompt' for r in self.requests()))
        # Independently confirm the actual JS owner refuses the same bounded
        # byte frame; Python and GTK preflight do not redefine its text limit.
        client = await PiOwnerClient.connect(self.owner_dir)
        try:
            with self.assertRaisesRegex(RuntimeError, 'Bounded text'):
                await client.call('chat', text=text)
        finally:
            await client.close()
        await self.send('chat', text='still usable')
        await self.until('result', 'chat')
        self.assertEqual([r['text'] for r in self.requests() if r['op'] == 'native_prompt'], ['still usable'])

    async def test_adapter_owner_byte_overflow_has_no_native_submission(self):
        await self.launch()
        await self.until('status')
        text = '😀' + '\x01' * 10910 + 'abcx'
        frame = (json.dumps({'op': 'chat', 'id': '0'*32, 'text': text}, ensure_ascii=False)+'\n').encode('utf-8')
        self.assertEqual(len(frame), MAX_FRAME + 1)
        self.assertLess(len(text.encode('utf-16-le')) // 2, 16000)
        # This fits the shorter GTK→adapter envelope, but not adapter→owner.
        await self.send('chat', text=text)
        await self.until('error', 'chat')
        self.assertFalse(any(r['op'] == 'native_prompt' for r in self.requests()))
        await self.send('chat', text='after byte rejection')
        await self.until('result', 'chat')
        self.assertEqual([r['text'] for r in self.requests() if r['op'] == 'native_prompt'], ['after byte rejection'])

    async def test_client_refuses_unsafe_key_and_oversize_request(self):
        key = self.owner_dir / 'control.key'
        key.chmod(0o644)
        with self.assertRaises(PermissionError):
            await PiOwnerClient.connect(self.owner_dir, trusted=True)
        key.chmod(0o600)
        client = await PiOwnerClient.connect(self.owner_dir)
        try:
            with self.assertRaises(ValueError):
                await client.call('chat', text='x'*MAX_FRAME)
            with self.assertRaises(PermissionError):
                await client.call('on')
        finally:
            await client.close()
