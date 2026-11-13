"""Real AF_UNIX/HMAC transports, synthetic stalled owner; no GUI/model/service."""
import asyncio
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import tempfile
import time
import unittest
from unittest.mock import patch

from hyprneuro.pi_desktop_bridge import DesktopBridge
from hyprneuro.pi_managed_bridge import ManagedDesktopBridge
from hyprneuro.pi_owner_service import SCHEMA
from hyprneuro.pi_owner_client import PiOwnerClient


class Guard:
    unlocked = True
    async def reconcile(self):
        return self.unlocked


class AuthenticatedStallTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'home/workspace').mkdir(parents=True, mode=0o700)
        (self.root / 'home').chmod(0o700)
        config = dict(schema=SCHEMA, root=str(self.root), source='/reviewed/source',
            node='/usr/bin/node', sdk='/installed/sdk', durable='/installed/durable',
            pi='/installed/pi', read_paths=['fixture.txt'], task_id='stalled-test')
        (self.root / 'owner.json').write_text(json.dumps(config))
        (self.root / 'owner.json').chmod(0o600)
        self.keys = {role: secrets.token_bytes(32) for role in ['chat', 'control']}
        for role, key in self.keys.items():
            (self.root / (role + '.key')).write_bytes(key)
            (self.root / (role + '.key')).chmod(0o600)
        self.packets, self.connections, self.handlers, self.errors, self.calls = [], [], set(), [], []
        self.bridge = None
        self.questions = 0
        self.reply_chat = False
        self.stall_auth = False
        self.guard = Guard()
        self.server = await asyncio.start_unix_server(self.handle, path=str(self.root / 'owner.sock'))

    async def asyncTearDown(self):
        # Force test-peer EOF first, so a regression cannot hang test teardown.
        for connection in self.connections:
            connection['writer'].transport.abort()
        if self.bridge:
            await asyncio.wait_for(self.bridge.close(), 2)
        self.server.close()
        await self.server.wait_closed()
        await asyncio.gather(*self.handlers, return_exceptions=True)
        self.tmp.cleanup()
        self.assertEqual(self.errors, [])

    async def send(self, packet):
        self.packets.append(packet)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        record = dict(writer=writer, eof=asyncio.Event(), role=None)
        self.connections.append(record)
        try:
            nonce = secrets.token_bytes(32)
            writer.write(nonce)
            await writer.drain()
            response = await reader.readexactly(33)
            role = {b'C': 'control', b'T': 'chat'}[response[:1]]
            record['role'] = role
            self.assertTrue(hmac.compare_digest(response[1:], hmac.new(self.keys[role], nonce + role.encode(), hashlib.sha256).digest()))
            if self.stall_auth:
                await reader.read()
                return
            writer.write(b'{"type":"ready","schema":"hyprneuro.pi-owner/1"}\n')
            await writer.drain()
            while line := await reader.readline():
                packet = json.loads(line)
                self.calls.append(packet)
                if packet['op'] == 'status':
                    status = dict(persistent=True, parent_only=True, normal_only=True,
                        tools=['read'], owner_phase='ordinary', state='unavailable',
                        workspace=str(self.root / 'home/workspace'), task_id='stalled-test',
                        app_id='hyprneuro-parent-read', read_paths=[str(self.root / 'home/workspace/fixture.txt')])
                    writer.write((json.dumps(dict(type='result', id=packet['id'], result=status)) + '\n').encode())
                    for index in range(self.questions):
                        event = dict(type='consent', id='synthetic-' + str(index), title='Synthetic read?', detail='Synthetic fixture only')
                        writer.write((json.dumps(dict(type='host_event', event=event)) + '\n').encode())
                    self.questions = 0
                elif packet['op'] == 'chat' and self.reply_chat:
                    writer.write((json.dumps(dict(type='event', id=packet['id'], event=dict(type='delta', channel='answer', text='synthetic'))) + '\n').encode())
                    writer.write((json.dumps(dict(type='result', id=packet['id'], result=dict(settled=True))) + '\n').encode())
                # Otherwise deliberately withhold chat/consent acknowledgements.
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        except Exception as error:
            self.errors.append(type(error).__name__)
        finally:
            record['eof'].set()
            writer.close()
            await writer.wait_closed()
            self.handlers.discard(task)

    async def until(self, predicate, timeout=.6):
        async with asyncio.timeout(timeout):
            while not predicate():
                await asyncio.sleep(.005)

    async def test_whole_chat_deadline_closes_silent_authenticated_owner_no_replay(self):
        self.bridge = DesktopBridge(str(self.root), self.send)
        self.bridge.chat_timeout = .05
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            # External watchdog distinguishes the intended deadline from a hang.
            async with asyncio.timeout(.5):
                await self.bridge.chat('synthetic bounded request')
        self.assertLess(time.monotonic() - started, .3)
        await self.until(lambda: self.connections and self.connections[0]['eof'].is_set())
        self.assertEqual([c['op'] for c in self.calls], ['chat'])
        self.assertIsNone(self.bridge.chat_client)

    async def attach_pending(self):
        self.questions = 3
        self.bridge = ManagedDesktopBridge(self.send, guard=self.guard)
        await self.bridge.attach(str(self.root))
        await self.until(lambda: len(self.bridge.consents) == 3)
        return list(self.bridge.consents.values())

    async def test_lock_drops_chat_and_control_without_consent_ack_and_reports_unavailable(self):
        timers = await self.attach_pending()
        chat = asyncio.create_task(self.bridge.request(dict(op='chat', text='synthetic stalled chat')))
        await self.until(lambda: any(c['op'] == 'chat' for c in self.calls))
        self.guard.unlocked = False
        await self.until(lambda: any(p['type'] == 'unavailable' for p in self.packets))
        await self.until(lambda: all(c['eof'].is_set() for c in self.connections))
        await asyncio.wait_for(asyncio.gather(chat, return_exceptions=True), .3)
        self.assertIsNone(self.bridge.control)
        self.assertIsNone(self.bridge.chat_client)
        self.assertTrue(all(t.done() for t in timers))
        self.assertEqual(self.bridge.consents, {})
        self.assertEqual(sum(c['op'] == 'chat' for c in self.calls), 1)
        self.assertFalse(any(c['op'] in ['consent', 'on', 'off'] for c in self.calls))
        self.assertNotIn('disconnected', [p['type'] for p in self.packets])

    async def test_same_chat_deadline_includes_authentication_before_request(self):
        self.stall_auth = True
        self.bridge = DesktopBridge(str(self.root), self.send, chat_timeout=.05)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(.5):
                await self.bridge.chat('never submitted')
        self.assertLess(time.monotonic() - started, .3)
        await self.until(lambda: self.connections and self.connections[0]['eof'].is_set())
        self.assertEqual(self.calls, [])

    async def test_same_chat_deadline_includes_event_drain_after_result(self):
        self.reply_chat = True
        entered = asyncio.Event()
        async def blocked_send(packet):
            entered.set()
            await asyncio.Event().wait()
        self.bridge = DesktopBridge(str(self.root), blocked_send, chat_timeout=.05)
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            async with asyncio.timeout(.5):
                await self.bridge.chat('synthetic result with blocked UI drain')
        self.assertTrue(entered.is_set())
        self.assertLess(time.monotonic() - started, .3)
        await self.until(lambda: self.connections[0]['eof'].is_set())
        self.assertEqual([c['op'] for c in self.calls], ['chat'])

    async def test_client_close_aborts_real_transport_even_if_wait_closed_stalls(self):
        client = await PiOwnerClient.connect(self.root, trusted=True)
        async def stuck_close():
            await asyncio.Event().wait()
        with patch.object(client.writer, 'wait_closed', stuck_close):
            started = time.monotonic()
            await asyncio.wait_for(client.close(timeout=.05), .3)
            self.assertLess(time.monotonic() - started, .2)
        await self.until(lambda: self.connections[0]['eof'].is_set())
        self.assertTrue(client.read_task.done())
        self.assertEqual(self.calls, [])

    async def test_cancelled_chat_has_one_submission_and_immediate_server_eof(self):
        self.bridge = DesktopBridge(str(self.root), self.send, chat_timeout=.05)
        task = asyncio.create_task(self.bridge.chat('synthetic cancelled request'))
        await self.until(lambda: any(c['op'] == 'chat' for c in self.calls))
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, .3)
        await self.until(lambda: self.connections[0]['eof'].is_set())
        self.assertEqual([c['op'] for c in self.calls], ['chat'])
        self.assertIsNone(self.bridge.chat_client)

    async def test_concurrent_disconnect_and_cancellation_with_multiple_pending_consents(self):
        timers = await self.attach_pending()
        control = self.bridge.control
        stuck = asyncio.Event()
        async def delayed_close():
            stuck.set()
            await asyncio.Event().wait()
        # Exercise cleanup cancellation after synchronous transport revocation,
        # not just cancellation of an already completed disconnect.
        with patch.object(control.writer, 'wait_closed', delayed_close):
            first = asyncio.create_task(self.bridge.detach())
            await asyncio.wait_for(stuck.wait(), .3)
            await self.until(lambda: self.connections[0]['eof'].is_set())
            second = asyncio.create_task(self.bridge.request({'op': 'disconnect'}))
            third = asyncio.create_task(self.bridge.detach())
            first.cancel()
            await asyncio.wait_for(asyncio.gather(first, second, third, return_exceptions=True), .3)
        self.assertIsNone(self.bridge.control)
        self.assertEqual(self.bridge.consents, {})
        self.assertTrue(all(t.done() for t in timers))
        self.assertTrue(control.read_task.done())
        self.assertFalse(any(c['op'] in ['consent', 'chat', 'on', 'off'] for c in self.calls))
        self.assertEqual(self.packets[-1]['type'], 'disconnected')

    async def test_lock_reports_unavailable_while_local_close_completion_is_stalled(self):
        timers = await self.attach_pending()
        control = self.bridge.control
        async def delayed_close():
            await asyncio.Event().wait()
        with patch.object(control.writer, 'wait_closed', delayed_close):
            self.guard.unlocked = False
            await self.until(lambda: any(p['type'] == 'unavailable' for p in self.packets))
            await self.until(lambda: self.connections[0]['eof'].is_set())
            self.assertTrue(self.bridge.failed)
            self.assertIsNone(self.bridge.control)
            # Stop the monitor's now-bounded wait; socket authority is already gone.
            await asyncio.wait_for(self.bridge.detach(), 1.5)
        self.assertTrue(all(t.done() for t in timers))
        self.assertFalse(any(c['op'] in ['consent', 'chat', 'on', 'off'] for c in self.calls))

    async def test_expiring_denial_wait_is_cancelled_on_lock_not_lost_from_timer_tracking(self):
        timers = await self.attach_pending()
        for timer in timers:
            timer.cancel()
        await asyncio.gather(*timers, return_exceptions=True)
        self.bridge.consents.clear()
        original_sleep = asyncio.sleep
        async def shortened_sleep(delay):
            await original_sleep(0 if delay == 110 else delay)
        with patch('hyprneuro.pi_desktop_bridge.asyncio.sleep', shortened_sleep):
            timer = asyncio.create_task(self.bridge.expire('expiring'))
            self.bridge.consents['expiring'] = timer
            await self.until(lambda: any(c['op'] == 'consent' for c in self.calls))
            self.assertIn('expiring', self.bridge.consents)
            self.guard.unlocked = False
            await self.until(lambda: any(p['type'] == 'unavailable' for p in self.packets))
            await self.until(lambda: self.connections[0]['eof'].is_set())
            await self.until(timer.done)
        self.assertEqual(self.bridge.consents, {})
        self.assertFalse(any(c.get('allowed') is True for c in self.calls))
        self.assertEqual(sum(c['op'] == 'consent' for c in self.calls), 1)
