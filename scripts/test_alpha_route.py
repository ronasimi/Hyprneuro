#!/usr/bin/env python3
"""Private flow test: the REAL PiOwnerClient transport against a fake owner,
proving the native GUI prompt-path protocol (chat op + chat_admission + result)
and the trusted-consent deny before any human opt-in.

No live owner, no model, no network, no pyc. Stdlib only. The fake owner
implements exactly the wire protocol the real pi_owner_service host speaks
(nonce -> HMAC MAC -> ready -> ops), so this exercises the actual client code
path, not a toy. Every connect/call/close is bounded with asyncio.wait_for so a
protocol mismatch surfaces as a timeout, never a hung loop.
"""
import asyncio
import hashlib
import hmac
import json
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'python' / 'src'))

from hyprneuro.pi_owner_client import PiOwnerClient  # noqa: E402

SCHEMA = 'hyprneuro.pi-owner/1'
BOUND = 8  # seconds: every private connect/call/close is bounded


class FakeOwner:
    """Minimal unix-socket server speaking the pi-owner/1 wire protocol."""

    def __init__(self, root):
        self.root = Path(root)
        os.chmod(str(self.root), 0o700)  # mkdtemp already created it
        self.key = b'\x01' * 32
        for name in ('chat.key', 'control.key'):
            (self.root / name).write_bytes(self.key)
            (self.root / name).chmod(0o600)
        self.sock = self.root / 'owner.sock'
        if self.sock.exists():
            self.sock.unlink()
        self.server = None
        self.consents = []
        self.chats = []

    async def serve(self):
        self.server = await asyncio.wait_for(
            asyncio.start_unix_server(self._handle, path=str(self.sock)), BOUND)
        os.chmod(str(self.sock), 0o600)

    async def _handle(self, reader, writer):
        try:
            nonce = os.urandom(32)
            writer.write(nonce)
            await writer.drain()
            header = await reader.readexactly(33)
            role = b'chat' if header[:1] == b'T' else b'control'
            expected = hmac.new(self.key, nonce + role, hashlib.sha256).digest()
            if header[1:] != expected:
                return  # authentication failure: drop
            writer.write((json.dumps({'type': 'ready', 'schema': SCHEMA}) + '\n').encode())
            await writer.drain()
            while line := await reader.readline():
                if not line:
                    break
                packet = json.loads(line)
                op, rid = packet.get('op'), packet.get('id')
                if op == 'chat':
                    gen = str(uuid.uuid4())
                    self.chats.append(packet.get('text'))
                    writer.write((json.dumps({'type': 'event', 'id': rid,
                                               'event': {'type': 'chat_admission', 'generation': gen}})
                                  + '\n').encode())
                    await writer.drain()
                    writer.write((json.dumps({'type': 'result', 'id': rid,
                                              'result': {'text': 'FAKE_OWNER_OK',
                                                         'settled': True, 'generation': gen}})
                                  + '\n').encode())
                elif op == 'status':
                    writer.write((json.dumps({'type': 'result', 'id': rid,
                                              'result': {'authorization_profile': None}})
                                  + '\n').encode())
                elif op == 'consent':
                    self.consents.append(packet)
                    writer.write((json.dumps({'type': 'result', 'id': rid,
                                              'result': {'accepted': bool(packet.get('allowed'))}})
                                  + '\n').encode())
                else:
                    writer.write((json.dumps({'type': 'result', 'id': rid, 'result': {}})
                                  + '\n').encode())
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
            except Exception:
                pass

    async def close(self):
        if self.server is not None:
            self.server.close()
            await asyncio.wait_for(self.server.wait_closed(), BOUND)


async def _close(client):
    # close() (not just disconnect()) awaits the cancelled read_task so the
    # IsolatedAsyncioTestCase loop can shut down without hanging.
    try:
        await asyncio.wait_for(client.close(), BOUND)
    except (TimeoutError, ConnectionError):
        client.disconnect()


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def _mkroot(self):
        return Path(tempfile.mkdtemp(prefix='hn-alpha-route-'))

    async def test_chat_prompt_path_protocol(self):
        # The REAL client speaks the native prompt path: chat op -> admission
        # event -> settled result, all over the actual transport code.
        root = self._mkroot()
        owner = FakeOwner(root)
        await owner.serve()
        client = None
        try:
            client = await asyncio.wait_for(PiOwnerClient.connect(root), BOUND)
            result = await asyncio.wait_for(client.call('chat', text='hello native owner'), BOUND)
            self.assertEqual(result.get('text'), 'FAKE_OWNER_OK')
            self.assertTrue(result.get('settled'))
            generations = []
            while not client.events.empty():
                p = client.events.get_nowait()
                if p.get('event', {}).get('type') == 'chat_admission':
                    generations.append(p['event']['generation'])
            self.assertEqual(len(generations), 1)
            self.assertEqual(len(owner.chats), 1)
        finally:
            if client is not None:
                await _close(client)
            await owner.close()

    async def test_consent_denied_on_untrusted_channel_before_optin(self):
        # No human opt-in: the consent mutation is refused on the untrusted
        # chat channel (PermissionError) before it can reach the owner.
        root = self._mkroot()
        owner = FakeOwner(root)
        await owner.serve()
        client = None
        try:
            client = await asyncio.wait_for(PiOwnerClient.connect(root), BOUND)  # untrusted chat
            with self.assertRaises(PermissionError):
                await asyncio.wait_for(client.call('consent', answer_id='a1', allowed=False), BOUND)
            self.assertEqual(owner.consents, [])  # nothing reached the owner
        finally:
            if client is not None:
                await _close(client)
            await owner.close()

    async def test_consent_accepted_on_trusted_channel(self):
        # The genuine opt-in path: on the trusted control channel the consent
        # op is delivered to the owner (the fake records the human answer).
        root = self._mkroot()
        owner = FakeOwner(root)
        await owner.serve()
        client = None
        try:
            client = await asyncio.wait_for(PiOwnerClient.connect(root, trusted=True), BOUND)
            result = await asyncio.wait_for(client.call('consent', answer_id='a1', allowed=True), BOUND)
            self.assertTrue(result.get('accepted'))
            self.assertEqual(len(owner.consents), 1)
        finally:
            if client is not None:
                await _close(client)
            await owner.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
