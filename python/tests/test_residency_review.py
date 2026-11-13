"""Six independent review regressions; all services/model transports are fakes."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro import agent
from hyprneuro.residency import Coordinator, HERMES, ManualSwitch, ResidencyError, Services
from hyprneuro.sidecar import SidecarServer
from test_residency import FakeServices


class LaunchOwnershipTests(unittest.TestCase):
    def test_uncertain_launch_never_stops_adopted_generation(self):
        class Uncertain(FakeServices):
            def launch(self, *args):
                super().launch(*args)
                if args == ('moe',):
                    self.generation += 1  # externally replaced generation before uncertain return
                    self.current = self.rows({'moe'})
                    raise ResidencyError('control outcome unknown')
        with tempfile.TemporaryDirectory() as tmp:
            backend = Uncertain()
            owner = Coordinator(Path(tmp) / 'root', services=backend)
            owner.initialize(cooperation_confirmed=True)
            with self.assertRaisesRegex(ResidencyError, 'ownership unknown'):
                with owner.handoff(task_id='task', approve=lambda _: True, checkpoint=lambda: None, release_lease=lambda: None):
                    self.fail('uncertain launch admitted')
            self.assertEqual(backend.events, [('moe',)])
            self.assertEqual(owner.state.read()['phase'], 'blocked')
            self.assertEqual(backend.active(backend.current), {'moe'})

    def test_effective_loaded_properties_not_dropin_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            backend = Services(home)
            for name, text in (('.bin/lfm', '#!/bin/sh\n'),
                    ('.config/systemd/user/lfm@.service', '[Service]\n'),
                    ('.config/systemd/user/lfm@moe.service.d/10-exclusive.conf',
                     '# lfm@text.service lfm@omni.service lfm@decision.service Restart=no\n')):
                path = home / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            backend.launcher.chmod(0o700)
            model = home / HERMES
            model.touch()
            selected = home / 'state/lfm/moe-model'
            selected.parent.mkdir(parents=True)
            selected.write_text(str(model))
            good = 'Conflicts=lfm@text.service lfm@omni.service lfm@decision.service\nRestart=no\nNeedDaemonReload=no\n'
            with patch.dict(os.environ, {'XDG_STATE_HOME': str(home / 'state'), 'LFM_MOE_MODEL': ''}):
                for output in ('Conflicts=\nRestart=no\nNeedDaemonReload=no\n',
                               good.replace('Restart=no', 'Restart=always'),
                               good.replace('NeedDaemonReload=no', 'NeedDaemonReload=yes')):
                    with self.subTest(output=output), patch.object(backend, 'command', return_value=output):
                        with self.assertRaisesRegex(ResidencyError, 'Effective loaded'):
                            backend.preflight()
                with patch.object(backend, 'command', return_value=good) as command:
                    backend.preflight()
                    self.assertIn('--property=Conflicts,Restart,NeedDaemonReload', command.call_args.args[0])

    def test_cli_connected_manual_handoff_does_not_expire_at_one_hour(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'root'
            backend = FakeServices()
            owner = Coordinator(root, services=backend)
            owner.initialize(cooperation_confirmed=True)
            code = '''import hyprneuro.residency as r
from test_residency import FakeServices
r.Services=FakeServices
real_clock=r.time.monotonic
real_select=r.select.select
elapsed=[0]
def clock(): return real_clock()+elapsed[0]
def select(*args):
    if r.State(r.os.environ['HYPRNEURO_RESIDENCY_DIR']).read().get('phase')=='hermes' and not elapsed[0]:
        elapsed[0]=7201
        print('{"type":"idle_over_hour"}',flush=True)
        return ([],[],[])
    return real_select(*args)
r.time.monotonic=clock
r.select.select=select
r.main()
'''
            env = {**os.environ, 'HYPRNEURO_RESIDENCY_DIR': str(root),
                   'PYTHONPATH': os.pathsep.join((str(Path(__file__).parents[1] / 'src'), str(Path(__file__).parent)))}
            p = subprocess.Popen([sys.executable, '-c', code, 'handoff'], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            try:
                def send(value):
                    p.stdin.write(json.dumps(value) + '\n')
                    p.stdin.flush()
                send({'task_id': 'task'})
                for kind in ('handoff_approval', 'checkpoint', 'release_lease'):
                    self.assertEqual(json.loads(p.stdout.readline())['type'], kind)
                    send({'ok': True})
                self.assertEqual(json.loads(p.stdout.readline())['type'], 'hermes_ready')
                self.assertEqual(json.loads(p.stdout.readline())['type'], 'idle_over_hour')
                self.assertIsNone(p.poll())
                send({'finish': True})
                self.assertTrue(json.loads(p.stdout.readline())['restored'])
                self.assertEqual(p.wait(timeout=2), 0)
            finally:
                if p.poll() is None:
                    p.kill()
                    p.wait(timeout=2)
                for stream in (p.stdin, p.stdout, p.stderr):
                    stream.close()


class AsyncReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_off_awaits_internal_transition_not_long_lived_host_handler(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = FakeServices()
            root = Path(tmp) / 'root'
            Coordinator(root, services=backend).initialize(cooperation_confirmed=True)
            owner = await ManualSwitch.create(root, services=backend)
            approved = asyncio.Event()
            respond = asyncio.Event()
            unrelated = asyncio.Event()
            async def approve(_):
                approved.set()
                await respond.wait()
                return True
            async def noop():
                pass
            async def long_lived_handler():
                try:
                    await owner.on(task_id='task', approve=approve, checkpoint=noop, release_lease=noop)
                except ResidencyError:
                    pass
                await unrelated.wait()
            handler = asyncio.create_task(long_lived_handler())
            await approved.wait()
            off = asyncio.create_task(owner.off())
            await asyncio.sleep(.01)
            respond.set()
            try:
                self.assertEqual((await asyncio.wait_for(off, 1))['state'], 'off')
                self.assertFalse(handler.done())
            finally:
                unrelated.set()
                await handler

    async def test_outer_close_and_consumer_disconnect_await_http_cleanup_before_unlock(self):
        for consumer in ('outer-close', 'sidecar-writer-failure'):
            with self.subTest(consumer=consumer):
                order = []
                @contextmanager
                def gate(_):
                    order.append('admit')
                    try:
                        yield
                    finally:
                        order.append('unlock')
                async def stream(*args, **kwargs):
                    try:
                        yield {'type': 'delta', 'channel': 'answer', 'text': 'one'}
                        await asyncio.Event().wait()
                    finally:
                        order.append('http-close-start')
                        await asyncio.sleep(.02)
                        order.append('http-close-finished')
                with patch('hyprneuro.residency.inference_admission', gate), patch.object(agent, '_stream_chat_http', stream):
                    if consumer == 'outer-close':
                        outer = agent.stream_chat([])
                        await anext(outer)
                        await outer.aclose()
                    else:
                        server = SidecarServer(None)
                        async def write(_writer, frame):
                            if frame['type'] == 'delta':
                                raise OSError('client disconnected')
                        with patch.object(server, '_write_frame', write):
                            await server._stream_agent_chat(None, {'message': 'hello'})
                self.assertEqual(order, ['admit', 'http-close-start', 'http-close-finished', 'unlock'])
