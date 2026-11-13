"""Synthetic async lock/admission integration. No capture, model or service calls."""
import asyncio
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from hyprneuro.recall import CaptureCandidate, CapturePolicy, ScreenWatcher, PNG_MAGIC, GrimWindowCapture
from hyprneuro.recall_events import D1CaptureSource
from hyprneuro.session_lock import LoginSessionGuard
from hyprneuro.recall_transport import RecallModels
from hyprneuro.model_dispatch import ScheduledModels
from hyprneuro.sidecar import serve, SidecarServer
from hyprneuro.sidecar_sources import HyprlandSource
from hyprneuro.sidecar_store import SidecarStore
from test_recall_pipeline import FakeDesktop, FakeModels, FakeGrabber, FakeProcess

EVENT = CaptureCandidate('hyprland', 'activewindowv2')


def snapshot(session='c17', **changes):
    return dict(Id=session, User=str(os.getuid()), Active='yes', LockedHint='no',
                Remote='no', Type='wayland', Class='user', Seat='seat0', Leader='42', **changes)


class GuardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.guard = LoginSessionGuard(session='c17', proc_root=Path(self.tmp.name))
        self.guard._snapshot = AsyncMock(return_value=snapshot())

    def tearDown(self):
        self.tmp.cleanup()

    def process(self, name='hyprlock', session='c17', sid=42):
        path = Path(self.tmp.name) / '123'
        path.mkdir(exist_ok=True)
        (path / 'comm').write_text(name + '\n')
        (path / 'cgroup').write_text(f'0::/user.slice/session-{session}.scope\n' if session else '0::/user.slice/app.slice\n')
        (path / 'stat').write_text(f'123 (a locker name) S 1 1 {sid} 0 0')
        return path

    async def test_already_locked_startup_and_missing_signal(self):
        self.assertFalse(await self.guard.unlocked())
        for changes in ({'LockedHint': 'yes'}, {'LockedHint': ''}, {'Active': 'no'},
                        {'User': str(os.getuid()+1)}, {'Remote': 'yes'}, {'Type': 'tty'},
                        {'Seat': ''}, {'Id': 'another'}, {'Leader': '0'}, {'Class': 'greeter'}):
            self.guard._snapshot.return_value = {**snapshot(), **changes}
            self.assertFalse(await self.guard.reconcile(), changes)
            self.assertFalse(await self.guard.unlocked())

    async def test_locker_overrides_false_logind_hint_and_truncated_comm(self):
        for name in ('hyprlock', 'swaylock', 'swaylock-effects'[:15], 'betterlockscreen'[:15]):
            self.process(name)
            self.assertFalse(await self.guard.reconcile(), name)

    async def test_same_uid_other_verified_session_not_our_locker(self):
        self.process(session='other', sid=100)
        self.assertTrue(await self.guard.reconcile())
        self.process(session=None, sid=100)
        self.assertFalse(await self.guard.reconcile())

    async def test_other_uid_locker_does_not_pause_local_session(self):
        self.process()
        self.guard.uid = os.getuid()+1
        self.guard._snapshot.return_value = {**snapshot(), 'User': str(self.guard.uid)}
        self.assertTrue(await self.guard.reconcile())

    async def test_non_locker_substring_is_not_evidence(self):
        self.process(name='not-hyprlock')
        self.assertTrue(await self.guard.reconcile())

    async def test_procfs_unknown_and_bounded_scan_fail_closed(self):
        self.guard.proc_root = Path(self.tmp.name) / 'missing'
        self.assertFalse(await self.guard.reconcile())
        self.guard.proc_root = Path(self.tmp.name)
        self.process()
        with patch('hyprneuro.session_lock.time.monotonic', side_effect=[0, 1]):
            self.assertFalse(self.guard._no_locker(42))

    async def test_invalid_session_no_subprocess_and_query_failure(self):
        for session in ('', '../2', 'bad session'):
            self.guard.session = session
            self.assertFalse(await self.guard.reconcile())
        self.guard._snapshot.assert_not_called()
        self.guard.session = 'c17'
        self.guard._snapshot.side_effect = OSError('logind disconnected')
        self.assertFalse(await self.guard.reconcile())

    async def test_hook_target_validation_unlock_requires_verification(self):
        self.assertTrue(await self.guard.reconcile())
        self.assertFalse(self.guard.session_lock_event('2', True))
        self.assertTrue(await self.guard.unlocked())
        self.guard.session_lock_event('c17', True)
        self.assertFalse(await self.guard.reconcile())  # LockedHint=no cannot override explicit locker
        self.guard.session_lock_event('c17', False)
        self.assertFalse(await self.guard.unlocked())
        self.assertTrue(await self.guard.reconcile())
        self.guard.session_lock_event('c17', None)
        self.assertFalse(await self.guard.reconcile())

    async def test_expiry_has_no_frame_subprocess(self):
        self.assertTrue(await self.guard.reconcile())
        self.guard._snapshot.reset_mock()
        for _ in range(100):
            self.assertTrue(await self.guard.unlocked())
        self.guard._snapshot.assert_not_called()
        self.guard._expires = 0
        self.assertFalse(await self.guard.unlocked())

    async def test_notification_races_verification_cannot_unlock(self):
        async def racing():
            self.guard.session_lock_event('c17', True)
            return snapshot()
        self.guard._snapshot.side_effect = racing
        self.assertFalse(await self.guard.reconcile())
        self.assertFalse(await self.guard.unlocked())

    async def test_properties_changed_real_packet_shape_and_session_path(self):
        self.guard._path = '/org/freedesktop/login1/session/c17'
        packet = dict(path=self.guard._path, interface='org.freedesktop.DBus.Properties',
            member='PropertiesChanged', payload={'type': 'sa{sv}as', 'data': [
                'org.freedesktop.login1.Session', {'LockedHint': {'type': 'b', 'data': True}}, []]})
        await self.guard.reconcile()
        self.guard.properties_changed({**packet, 'path': '/org/freedesktop/login1/session/_2'})
        self.assertTrue(await self.guard.unlocked())
        self.guard.properties_changed(packet)
        self.assertFalse(await self.guard.unlocked())

    async def test_monitor_disconnect_and_cleanup(self):
        self.guard._command = AsyncMock(return_value=json.dumps({'type': 'o', 'data': ['/org/freedesktop/login1/session/c17']}))
        proc = FakeProcess([])
        proc.stdout = asyncio.StreamReader()
        proc.stdout.feed_eof()
        await self.guard.reconcile()
        with patch('hyprneuro.session_lock.asyncio.create_subprocess_exec', AsyncMock(return_value=proc)) as execute:
            await self.guard._monitor()
        self.assertFalse(await self.guard.unlocked())
        self.assertIn("path='/org/freedesktop/login1/session/c17'", ' '.join(execute.call_args.args))
        proc.returncode = None
        proc.stdout = asyncio.StreamReader()
        with patch('hyprneuro.session_lock.asyncio.create_subprocess_exec', AsyncMock(return_value=proc)):
            task = asyncio.create_task(self.guard._monitor())
            await asyncio.sleep(.01)
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), .5)
        self.assertTrue(proc.killed)

    async def test_command_timeout_kills_child(self):
        proc = FakeProcess([])
        proc.returncode = None
        proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        with patch('hyprneuro.session_lock.asyncio.create_subprocess_exec', AsyncMock(return_value=proc)):
            with self.assertRaises(asyncio.TimeoutError):
                await self.guard._command('fixture')
        self.assertTrue(proc.killed)


class PauseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.guard = LoginSessionGuard(session='c17', proc_root=Path(self.tmp.name))
        self.guard._snapshot = AsyncMock(return_value=snapshot())
        self.store = SidecarStore(':memory:')
        self.models = FakeModels()
        self.scheduled = ScheduledModels(self.models)
        self.grabber = FakeGrabber()
        self.watcher = ScreenWatcher(FakeDesktop(), self.scheduled, self.store,
            CapturePolicy(enabled=True, check_unlocked=self.guard.unlocked, min_interval_seconds=.5),
            self.grabber, session_guard=self.guard)
        self.source = D1CaptureSource(self.watcher, debounce_seconds=.01)
        await self.guard.reconcile()

    async def asyncTearDown(self):
        await self.scheduled.stop()
        self.assertFalse(self.watcher._tasks)
        self.store.close()
        self.tmp.cleanup()

    def lock(self):
        self.guard.session_lock_event('c17', True)

    async def unlock(self):
        self.guard.session_lock_event('c17', False)
        self.assertTrue(await self.guard.reconcile())

    async def blocked_stage(self, stage, *, late=False):
        entered = asyncio.Event()
        cancelled = asyncio.Event()
        if stage == 'capture':
            original = self.grabber.grab
            target, method = self.grabber, 'grab'
        elif stage == 'D1':
            original = self.models.decide_capture
            target, method = self.models, 'decide_capture'
        else:
            original = self.models.vision
            target, method = self.models, 'vision'
        async def blocked(*args):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                if not late:
                    raise
                # Deliberately cancellation-resistant backend completing after unlock.
                await self.unlock()
                return await original(*args)
        setattr(target, method, blocked)
        task = asyncio.create_task(self.watcher.consider_event(EVENT))
        await asyncio.wait_for(entered.wait(), .5)
        self.lock()
        result = await asyncio.wait_for(task, .5)
        await asyncio.wait_for(cancelled.wait(), .5)
        self.assertFalse(result['captured'])
        self.assertFalse(self.store.search(source='omni'))
        self.assertLessEqual(len(self.models.visions), 1)
        if stage == 'D1':
            self.assertEqual(self.grabber.grabs, 0)
        setattr(target, method, original)
        return result

    async def test_lock_during_D1(self):
        await self.blocked_stage('D1')
        await self.unlock()
        self.assertTrue((await self.watcher.consider_event(EVENT))['captured'])  # lane survives

    async def test_lock_during_capture(self):
        await self.blocked_stage('capture')

    async def test_lock_during_omni(self):
        await self.blocked_stage('Omni')
        await self.unlock()
        self.assertTrue((await self.watcher.consider_event(EVENT))['captured'])

    async def test_late_D1_generation_after_unlock(self):
        await self.blocked_stage('D1', late=True)

    async def test_late_capture_after_unlock(self):
        await self.blocked_stage('capture', late=True)

    async def test_late_omni_result_after_unlock(self):
        await self.blocked_stage('Omni', late=True)

    async def test_lock_during_visual_D1(self):
        entered = asyncio.Event()
        async def visual(*args):
            entered.set()
            await asyncio.Event().wait()
        self.watcher.capture_policy.visual_d1 = True
        with patch('hyprneuro.d1_visual.decide_visual', visual):
            task = asyncio.create_task(self.watcher.consider_event(EVENT))
            await asyncio.wait_for(entered.wait(), .5)
            self.lock()
            self.assertFalse((await asyncio.wait_for(task, .5))['captured'])
        self.assertFalse(self.models.visions)

    def test_candidate_mailbox_cannot_be_unbounded(self):
        for bound in (0, -1, 65, True):
            with self.assertRaises(ValueError):
                D1CaptureSource(self.watcher, max_queue=bound)

    async def test_pause_idempotent_queue_dropped_metadata_still_stored(self):
        await self.source.on_candidate(EVENT)
        self.lock()
        generation = self.watcher._generation
        self.lock()
        self.assertEqual(self.watcher._generation, generation)
        self.assertTrue(self.source.queue.empty())
        for _ in range(25):
            await self.source.on_candidate(EVENT)
        self.assertTrue(self.source.queue.empty())
        metadata = HyprlandSource(self.store)
        await metadata.on_event('activewindowv2', 'kitty,metadata-not-a-screenshot')
        task = asyncio.create_task(metadata.flush())
        try:
            await asyncio.wait_for(metadata.queue.join(), .5)
            self.assertTrue(self.store.search(query='metadata', source='hyprland'))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertFalse(self.models.decisions)
        self.assertFalse(self.models.visions)

    async def test_debounce_old_generation_no_unlockburst_fresh_only(self):
        run = asyncio.create_task(self.source.run())
        try:
            await self.source.on_candidate(EVENT)
            await asyncio.sleep(.002)
            self.lock()
            await self.source.on_candidate(EVENT)
            await self.unlock()
            await asyncio.wait_for(self.source.queue.join(), .5)
            self.assertFalse(self.models.decisions)
            await self.source.on_candidate(EVENT)
            await asyncio.wait_for(self.source.queue.join(), .5)
            self.assertEqual(len(self.models.decisions), 1)
        finally:
            run.cancel()
            await asyncio.wait_for(asyncio.gather(run, return_exceptions=True), .5)

    async def test_already_locked_no_D1_or_foreground(self):
        self.lock()
        self.assertFalse((await self.watcher.consider_event(EVENT))['captured'])
        with self.assertRaises(PermissionError):
            await self.watcher.observe_requested(EVENT)
        self.assertEqual(self.grabber.grabs, 0)
        self.assertFalse(self.models.decisions)

    async def test_capture_disabled_never_activated_by_unlock(self):
        self.watcher.capture_policy.enabled = False
        self.lock()
        await self.unlock()
        await self.source.on_candidate(EVENT)
        self.assertTrue(self.source.queue.empty())
        self.assertEqual((await self.watcher.consider_event(EVENT))['reason'], 'capture_disabled')
        with self.assertRaises(PermissionError):
            await self.watcher.observe_requested(EVENT)
        self.assertFalse(self.models.decisions)

    async def test_unknown_disconnect_and_verification_failure_cancel_work(self):
        entered = asyncio.Event()
        async def blocked(_):
            entered.set()
            await asyncio.Event().wait()
        self.models.decide_capture = blocked
        task = asyncio.create_task(self.watcher.consider_event(EVENT))
        await entered.wait()
        self.guard._snapshot.side_effect = OSError('disconnected')
        self.assertFalse(await self.guard.reconcile())
        self.assertFalse((await asyncio.wait_for(task, .5))['captured'])
        self.guard.session_lock_event('c17', False)
        self.assertFalse(await self.guard.reconcile())
        self.assertIsNone(self.watcher.visual_epoch)

    async def test_foreground_lock_during_omni_is_revoked(self):
        entered = asyncio.Event()
        async def blocked(*args):
            entered.set()
            await asyncio.Event().wait()
        self.models.vision = blocked
        task = asyncio.create_task(self.watcher.observe_requested(EVENT))
        await asyncio.wait_for(entered.wait(), .5)
        self.lock()
        with self.assertRaises(PermissionError):
            await asyncio.wait_for(task, .5)
        self.assertFalse(self.store.search(source='omni'))

    async def test_foreground_lock_during_focus_query_cannot_resume_old_request(self):
        entered = asyncio.Event()
        async def blocked(_):
            entered.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await self.unlock()
                return dict(FakeDesktop().window)
        self.watcher.desktop.query = blocked
        task = asyncio.create_task(self.watcher.observe_requested(EVENT))
        await asyncio.wait_for(entered.wait(), .5)
        self.lock()
        with self.assertRaises(PermissionError):
            await asyncio.wait_for(task, .5)
        self.assertEqual(self.grabber.grabs, 0)

    async def test_pending_lane_work_cannot_admit_after_pause_and_unlock(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def occupied():
            entered.set()
            await release.wait()
        lane = self.scheduled.decision_lane
        busy = lane.submit(occupied, foreground=True)
        await entered.wait()
        task = asyncio.create_task(self.watcher.consider_event(EVENT))
        await asyncio.sleep(.01)
        self.lock()
        await self.unlock()
        release.set()
        await busy
        self.assertFalse((await asyncio.wait_for(task, .5))['captured'])
        await asyncio.sleep(.01)
        self.assertFalse(self.models.decisions)
        self.assertTrue((await self.watcher.consider_event(EVENT))['captured'])

    async def test_expired_verification_at_lane_admission_drops_D1(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def occupied():
            entered.set()
            await release.wait()
        busy = self.scheduled.decision_lane.submit(occupied, foreground=True)
        await entered.wait()
        task = asyncio.create_task(self.watcher.consider_event(EVENT))
        await asyncio.sleep(.01)
        self.guard._expires = 0  # stalled reconciler, no new lock signal
        release.set()
        await busy
        self.assertFalse((await asyncio.wait_for(task, .5))['captured'])
        self.assertFalse(self.models.decisions)
        self.assertIsNone(self.watcher.visual_epoch)

    async def test_grim_cancel_closes_process(self):
        proc = FakeProcess([])
        proc.returncode = None
        proc.stdout = asyncio.StreamReader()
        with patch('hyprneuro.recall.asyncio.create_subprocess_exec', AsyncMock(return_value=proc)):
            task = asyncio.create_task(GrimWindowCapture().grab({'at': [0, 0], 'size': [10, 10]}))
            await asyncio.sleep(.01)
            task.cancel()
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), .5)
        self.assertTrue(proc.killed)


class WiredTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_socket_hook_and_compositor_intake_metadata_independence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            guard = LoginSessionGuard(session='c17', proc_root=root, interval=.1)
            guard._snapshot = AsyncMock(return_value={**snapshot(), 'LockedHint': 'yes'})
            async def monitor():
                await asyncio.Event().wait()
            guard._monitor = monitor
            events = asyncio.Queue()
            class Desktop(FakeDesktop):
                async def events(self, callback):
                    while True:
                        event = await events.get()
                        try:
                            await callback(*event)
                        finally:
                            events.task_done()
            models = FakeModels()
            stop = asyncio.Event()
            sock = root / 'runtime' / 'sidecar.sock'
            async def rpc(request):
                reader, writer = await asyncio.open_unix_connection(sock)
                try:
                    writer.write(json.dumps(request).encode()+b'\n')
                    await writer.drain()
                    return json.loads(await reader.readline())
                finally:
                    writer.close()
                    await writer.wait_closed()
            with patch('hyprneuro.recall.LoginSessionGuard', return_value=guard):
                task = asyncio.create_task(serve(allow_ingest=True, watch_hyprland=True,
                    allow_capture=True, desktop=Desktop(), models=models, grabber=FakeGrabber(),
                    socket_path=sock, db_path=root/'db'/'obs.db', shutdown=stop))
                try:
                    for _ in range(100):
                        if sock.exists() and guard._snapshot.called:
                            break
                        await asyncio.sleep(.005)
                    await events.put(('activewindowv2', 'locked-title-metadata'))
                    await events.join()
                    await asyncio.sleep(.03)
                    self.assertFalse(models.decisions)
                    response = await rpc({'action': 'session_lock', 'session': 'wrong', 'locked': False})
                    self.assertFalse(response['ok'])
                    for locked in (True, None, False):
                        response = await rpc({'action': 'session_lock', 'session': 'c17', 'locked': locked})
                        self.assertTrue(response['ok'])
                        self.assertEqual(response['result']['schema'], 'hyprneuro.session-lock/1')
                        self.assertTrue(response['result']['paused'])
                    self.assertFalse(models.decisions)  # false event didn't grant
                    guard._snapshot.return_value = snapshot()
                    await guard.reconcile()
                    await asyncio.sleep(.3)
                    self.assertFalse(models.decisions)  # no backlog/unlock-generated capture
                    await events.put(('activewindowv2', 'fresh-title'))
                    await events.join()
                    for _ in range(100):
                        if len(models.visions) == 2:
                            break
                        await asyncio.sleep(.01)
                    self.assertEqual(len(models.visions), 2)
                    response = await rpc({'action': 'search', 'query': 'locked-title', 'source': 'hyprland'})
                    self.assertTrue(response['result'])
                finally:
                    stop.set()
                    await asyncio.wait_for(task, 1)

    async def test_capture_off_rpc_cannot_enable_guard_or_capture(self):
        store = SidecarStore(':memory:')
        try:
            server = SidecarServer(store)
            with self.assertRaises(PermissionError):
                await server.dispatch_async({'action': 'session_lock', 'session': 'c17', 'locked': False})
            for invalid in ('no', 0, 1, [], {}):
                with self.assertRaises(ValueError):
                    await server.dispatch_async({'action': 'session_lock', 'session': 'c17', 'locked': invalid})
            self.assertIsNone(server.watcher)
        finally:
            store.close()

    async def test_real_async_http_omni_closed_on_lock_and_no_second_request(self):
        await self.http_pause('omni')

    async def test_real_async_http_D1_closed_on_lock(self):
        await self.http_pause('D1')

    async def http_pause(self, stage):
        entered, disconnected = asyncio.Event(), asyncio.Event()
        requests = []
        handlers = set()
        async def http(reader, writer):
            handlers.add(asyncio.current_task())
            try:
                header = await reader.readuntil(b'\r\n\r\n')
                length = int(next(l.split(b':', 1)[1] for l in header.split(b'\r\n') if l.lower().startswith(b'content-length:')))
                body = json.loads(await reader.readexactly(length))
                requests.append(body)
                if 'questions' in body and stage != 'D1':
                    raw = b'{"answers":{"capture":{"noul":0.99}}}'
                    writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw)
                    await writer.drain()
                else:
                    entered.set()
                    await reader.read()
                    disconnected.set()
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(asyncio.current_task())
        server = await asyncio.start_server(http, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        models = ScheduledModels(RecallModels(SimpleNamespace(decision_port=port, omni_port=port, model_timeout=2)))
        store = SidecarStore(':memory:')
        watcher = ScreenWatcher(FakeDesktop(), models, store,
            CapturePolicy(enabled=True, check_unlocked=AsyncMock(return_value=True)), FakeGrabber())
        task = asyncio.create_task(watcher.consider_event(EVENT))
        try:
            await asyncio.wait_for(entered.wait(), 1)
            watcher.pause()
            self.assertFalse((await asyncio.wait_for(task, .5))['captured'])
            await asyncio.wait_for(disconnected.wait(), .5)
            self.assertEqual(len(requests), 2 if stage == 'omni' else 1)
            self.assertFalse(store.search(source='omni'))
            if watcher._tasks:
                await asyncio.wait_for(asyncio.gather(*watcher._tasks, return_exceptions=True), .5)
            self.assertFalse(watcher._tasks)
        finally:
            await models.stop()
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.wait_for(asyncio.gather(*handlers), .5)
            store.close()


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def response(self, raw):
        async def fixture(reader, writer):
            try:
                await reader.readuntil(b'\r\n\r\n')
                writer.write(raw)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
        server = await asyncio.start_server(fixture, '127.0.0.1', 0)
        port = server.sockets[0].getsockname()[1]
        try:
            model = RecallModels(SimpleNamespace(decision_port=port, model_timeout=1))
            return await model.call('decision', '/fixture')
        finally:
            server.close()
            await server.wait_closed()

    async def test_chunked_and_connection_close_responses(self):
        raw = b'{"answers":{}}'
        self.assertEqual(await self.response(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n'
            + f'{len(raw):x}'.encode() + b'\r\n' + raw + b'\r\n0\r\n\r\n'), {'answers': {}})
        self.assertEqual(await self.response(b'HTTP/1.1 200 OK\r\n\r\n' + raw), {'answers': {}})

    async def test_bad_status_oversized_and_incomplete_rejected(self):
        from hyprneuro.models import ModelError
        for raw in (b'HTTP/1.1 503 Failed\r\nContent-Length: 2\r\n\r\n{}',
                    b'HTTP/1.1 200 OK\r\nContent-Length: 8388609\r\n\r\n',
                    b'HTTP/1.1 200 OK\r\nContent-Length: 8\r\n\r\n{}',
                    b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n800001\r\n'):
            with self.assertRaises(ModelError):
                await self.response(raw)
