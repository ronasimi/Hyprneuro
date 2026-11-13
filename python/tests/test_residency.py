import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hyprneuro.residency import State, Admission, Coordinator, ResidencyError, ROLES, identity
from hyprneuro import agent
from hyprneuro.models import Models


class FakeServices:
    def __init__(self, active=('text', 'decision')):
        self.generation = 0
        self.events = []
        self.failure = None
        self.cancel = None
        self.current = self.rows(active)

    def rows(self, active):
        return {r: {'ActiveState': 'active' if r in active else 'inactive',
                    'MainPID': str(self.generation + 1) if r in active else '0'} for r in ROLES}

    def preflight(self):
        if self.failure == 'preflight':
            raise ResidencyError('preflight')
        return {'launcher': 'unchanged'}

    def snapshot(self):
        return json.loads(json.dumps(self.current))

    def active(self, snapshot):
        return {r for r, v in snapshot.items() if v['ActiveState'] == 'active'}

    def ready(self, role):
        if self.failure == 'ready-' + role:
            return False
        if self.cancel == 'ready':
            self.cancellation.set()
        return True

    def verify_hermes(self, snapshot):
        if self.failure == 'identity':
            raise ResidencyError('model identity')

    def launch(self, *args):
        self.events.append(args)
        if self.failure == 'launch-' + '-'.join(args):
            raise ResidencyError('launcher failed')
        current = self.active(self.current)
        if args == ('moe',):
            current = {'moe'}
        elif args == ('stop', 'moe'):
            current.discard('moe')
        else:
            current.add(args[1])
        self.generation += 1
        self.current = self.rows(current)
        if self.cancel == args:
            self.cancellation.set()


class ResidencyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'residency'
        self.services = FakeServices()
        self.coordinator = Coordinator(self.root, services=self.services)
        self.coordinator.initialize(cooperation_confirmed=True)
        self.count = []

    def tearDown(self):
        self.tmp.cleanup()

    def handoff(self, **kw):
        return self.coordinator.handoff(task_id='task', approve=lambda _: True,
                checkpoint=lambda: self.count.append('checkpoint'),
                release_lease=lambda: self.count.append('release'), timeout=.08, **kw)

    def test_exact_subset_and_admission(self):
        with self.handoff() as token:
            self.assertEqual(self.count, ['checkpoint', 'release'])
            self.assertEqual(self.services.events, [('moe',)])
            for role in ('text', 'omni', 'decision'):
                with self.assertRaises(ResidencyError):
                    with Admission(self.root, services=self.services).enter(role):
                        self.fail('ordinary admitted during Hermes')
            with self.assertRaises(ResidencyError):
                with Admission(self.root, services=self.services).enter('hermes', token='invalid'):
                    self.fail('invalid token')
            with Admission(self.root, services=self.services).enter('hermes', token=token):
                pass
        self.assertEqual(self.services.events, [('moe',), ('stop', 'moe'), ('start', 'decision'), ('start', 'text')])
        self.assertEqual(self.services.active(self.services.current), {'text', 'decision'})
        self.assertEqual(self.coordinator.state.read()['phase'], 'idle')

    def test_approval_denial_and_stale_state(self):
        with self.assertRaises(ResidencyError):
            with self.coordinator.handoff(task_id='task', approve=lambda _: 'approved', checkpoint=lambda: None, release_lease=lambda: None):
                self.fail('string approval')
        self.assertFalse(self.services.events)
        self.services.current = self.services.rows({'omni'})
        with self.assertRaises(ResidencyError):
            with self.handoff():
                self.fail('external switch')
        self.assertFalse(self.services.events)

    def test_no_takeover_existing_hermes_or_unknown_transaction(self):
        self.services.current = self.services.rows({'moe'})
        with self.assertRaises(ResidencyError):
            self.coordinator.initialize(cooperation_confirmed=True)
        self.assertFalse(self.services.events)
        self.coordinator.checkpoint('launching')
        with self.assertRaises(ResidencyError):
            self.coordinator.initialize(cooperation_confirmed=True)

    def test_failure_every_phase(self):
        for failure in ('preflight', 'launch-moe', 'ready-moe', 'identity', 'launch-stop-moe', 'launch-start-decision', 'ready-text'):
            with self.subTest(failure=failure):
                services = FakeServices()
                directory = self.root / failure
                c = Coordinator(directory, services=services)
                c.initialize(cooperation_confirmed=True)
                services.failure = failure
                with self.assertRaises(ResidencyError):
                    with c.handoff(task_id='task', approve=lambda _: True, checkpoint=lambda: None,
                                   release_lease=lambda: None, timeout=.03):
                        pass
                state = c.state.read()
                if state['phase'] == 'idle':
                    self.assertEqual(services.active(services.current), {'text', 'decision'})
                else:
                    self.assertEqual(state['phase'], 'blocked')
                    with self.assertRaises(ResidencyError):
                        with Admission(directory, services=services).enter('text'):
                            self.fail('failed restore admitted')

    def test_checkpoint_lease_failure_no_switch(self):
        def fail():
            raise ResidencyError('invalid lease token')
        for field in ('checkpoint', 'release_lease'):
            kwargs = dict(task_id='task', approve=lambda _: True, checkpoint=lambda: None, release_lease=lambda: None)
            kwargs[field] = fail
            with self.assertRaises(ResidencyError):
                with self.coordinator.handoff(**kwargs):
                    pass
            self.assertFalse(self.services.events)
            self.assertEqual(self.coordinator.state.read()['phase'], 'idle')

    def test_cancel_before_drain_after_launch_and_inference(self):
        for phase in ('before', ('moe',), 'inference'):
            services = FakeServices()
            cancel = threading.Event()
            services.cancellation = cancel
            services.cancel = phase
            directory = self.root / str(phase)
            c = Coordinator(directory, services=services)
            c.initialize(cooperation_confirmed=True)
            if phase == 'before':
                cancel.set()
            with self.assertRaises(ResidencyError):
                with c.handoff(task_id='task', approve=lambda _: True, checkpoint=lambda: None,
                               release_lease=lambda: None, cancel=cancel, timeout=.04):
                    raise ResidencyError('Pi cancelled')
            self.assertEqual(c.state.read()['phase'], 'idle')
            self.assertEqual(services.active(services.current), {'text', 'decision'})

    def test_external_change_during_hermes_blocks_automatic_restore(self):
        with self.assertRaises(ResidencyError):
            with self.handoff():
                self.services.generation += 1
                self.services.current = self.services.rows({'moe'})
        self.assertEqual(self.coordinator.state.read()['phase'], 'blocked')
        self.assertEqual(self.services.events, [('moe',)])

    def test_process_lock_real_crossprocess_and_crash_release(self):
        code = 'from hyprneuro.residency import State; import sys,time; s=State(sys.argv[1]);\nwith s.lock("inference.lock",exclusive=False):\n print("held",flush=True); time.sleep(5)'
        proc = subprocess.Popen([sys.executable, '-c', code, str(self.root)], stdout=subprocess.PIPE,
                                text=True, env={**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1] / 'src')})
        try:
            self.assertEqual(proc.stdout.readline().strip(), 'held')
            with self.assertRaises(ResidencyError):
                with self.handoff():
                    pass
            self.assertFalse(self.services.events)
        finally:
            proc.kill()
            proc.wait(timeout=2)
            proc.stdout.close()
        with self.handoff():
            pass

    def test_reentrant_transactions_fail_without_lock_leak(self):
        with self.handoff():
            with self.assertRaises(ResidencyError):
                with self.handoff():
                    self.fail('nested transaction')
        with self.handoff():
            pass

    def test_cli_host_frames_and_disconnect_restore(self):
        code = 'import hyprneuro.residency as r; from test_residency import FakeServices; r.Services=FakeServices; r.main()'
        env = {**os.environ, 'HYPRNEURO_RESIDENCY_DIR': str(self.root),
               'PYTHONPATH': os.pathsep.join((str(Path(__file__).parents[1] / 'src'), str(Path(__file__).parent)))}
        proc = subprocess.Popen([sys.executable, '-c', code, 'handoff'], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            def send(value):
                proc.stdin.write(json.dumps(value) + '\n')
                proc.stdin.flush()
            send({'task_id': 'task'})
            for kind in ('handoff_approval', 'checkpoint', 'release_lease'):
                self.assertEqual(json.loads(proc.stdout.readline())['type'], kind)
                send({'ok': True})
            packet = json.loads(proc.stdout.readline())
            self.assertEqual(packet['type'], 'hermes_ready')
            self.assertEqual(len(packet['token']), 64)
            # Host death/EOF is cancellation, not successful task completion.
            proc.stdin.close()
            self.assertNotEqual(proc.wait(timeout=3), 0)
            self.assertEqual(self.coordinator.state.read()['phase'], 'idle')
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=2)
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                stream.close()


class HTTPAdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_http_all_roles_background_and_explanation_use_sync_gate(self):
        events = []
        @contextmanager
        def gate(role):
            events.append(('enter', role))
            try:
                yield
            finally:
                events.append(('exit', role))
        model = Models(type('Config', (), {})())
        def actual(role, *args):
            events.append(('http', role))
            if role == 'decision':
                return {'choices': [{'message': {'content': 'explained'}}]}
            return {}
        with patch('hyprneuro.residency.inference_admission', gate), patch.object(model, '_http_call', actual):
            for role in ('text', 'omni', 'decision'):
                await model.call(role, '/v1/test', {})
            await model.explain_alert({'kind': 'test'})
        self.assertEqual(events, [x for r in ('text', 'omni', 'decision', 'decision') for x in [('enter', r), ('http', r), ('exit', r)]])

    async def test_stream_gate_release_failure_and_cancel(self):
        events = []
        @contextmanager
        def gate(role):
            events.append('enter')
            try:
                yield
            finally:
                events.append('exit')
        async def stream(*args, **kwargs):
            events.append('http')
            yield {'type': 'delta', 'text': 'test'}
            raise ValueError('broken stream')
        with patch('hyprneuro.residency.inference_admission', gate), patch.object(agent, '_stream_chat_http', stream):
            with self.assertRaises(ValueError):
                _ = [e async for e in agent.stream_chat([])]
        self.assertEqual(events, ['enter', 'http', 'exit'])
        started = asyncio.Event()
        async def stalled(*args, **kwargs):
            started.set()
            await asyncio.sleep(10)
            yield {}
        with patch('hyprneuro.residency.inference_admission', gate), patch.object(agent, '_stream_chat_http', stalled):
            async def collect():
                return [e async for e in agent.stream_chat([])]
            task = asyncio.create_task(collect())
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(events[-2:], ['enter', 'exit'])


    async def test_async_health_gated_and_model_cancel_keeps_actual_http_admitted(self):
        events = []
        @contextmanager
        def denied(role):
            events.append(role)
            raise ResidencyError('draining')
            yield
        with patch('hyprneuro.residency.inference_admission', denied), patch.object(agent, '_health_http') as http:
            self.assertFalse(await agent.health('omni'))
            http.assert_not_called()
        self.assertEqual(events, ['omni'])
        entered = threading.Event()
        finish = threading.Event()
        exited = threading.Event()
        @contextmanager
        def gate(role):
            entered.set()
            try:
                yield
            finally:
                exited.set()
        model = Models(type('Config', (), {})())
        def actual(*args):
            finish.wait(timeout=1)
            return {}
        with patch('hyprneuro.residency.inference_admission', gate), patch.object(model, '_http_call', actual):
            task = asyncio.create_task(model.call('decision', '/v1/systemone', {}))
            await asyncio.to_thread(entered.wait, 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertFalse(exited.is_set())
            finish.set()
            self.assertTrue(await asyncio.to_thread(exited.wait, 1))
