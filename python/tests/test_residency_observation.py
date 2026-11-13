"""Synthetic-only pause/drop/manual-switch integration; never grim/model/systemctl."""
import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from hyprneuro.residency import Coordinator, ManualSwitch, ResidencyError, observation_epoch
from hyprneuro.model_dispatch import ModelLane
from hyprneuro.models import Models
from hyprneuro.recall import CaptureCandidate, CapturePolicy, ScreenWatcher
from hyprneuro.recall_events import D1CaptureSource
from hyprneuro.sidecar_sources import HyprlandSource
from hyprneuro.sidecar_store import SidecarStore
from test_residency import FakeServices
from test_recall_pipeline import FakeDesktop, FakeModels, FakeGrabber, permit


class ObservationResidencyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / 'coordination'
        self.services = FakeServices(active=('text', 'omni', 'decision'))
        self.c = Coordinator(self.root, services=self.services)
        self.c.initialize(cooperation_confirmed=True)
        self.env = patch.dict('os.environ', {'HYPRNEURO_RESIDENCY_DIR': str(self.root)})
        self.env.start()
        self.backend = patch('hyprneuro.residency.Services', return_value=self.services)
        self.backend.start()
        self.store = SidecarStore(':memory:')
        self.grabber = FakeGrabber()
        self.models = FakeModels()
        self.watcher = ScreenWatcher(FakeDesktop(), self.models, self.store,
            CapturePolicy(enabled=True, check_unlocked=permit, min_interval_seconds=.5), self.grabber)
        self.event = CaptureCandidate('hyprland', 'activewindowv2')

    def tearDown(self):
        self.store.close()
        self.backend.stop()
        self.env.stop()
        self.tmp.cleanup()

    def pause(self):
        self.c.checkpoint('draining', epoch='new-generation')

    def resume(self):
        self.c.checkpoint('idle')

    async def test_candidate_queue_old_during_after_and_metadata_independent(self):
        calls = []
        class Watcher:
            async def consider_event(self, candidate):
                calls.append(candidate.event)
                return {'captured': False}
        source = D1CaptureSource(Watcher(), debounce_seconds=0)
        metadata = HyprlandSource(self.store)
        await source.on_event('activewindowv2', 'old')
        self.pause()
        await source.on_event('workspacev2', 'during')
        await metadata.on_event('workspacev2', 'operational-metadata')
        flush = asyncio.create_task(metadata.flush())
        run = asyncio.create_task(source.run())
        try:
            await asyncio.wait_for(source.queue.join(), 1)
            await asyncio.wait_for(metadata.queue.join(), 1)
            self.assertFalse(calls)
            self.assertTrue(self.store.search(query='operational', source='hyprland'))
            self.resume()
            await source.on_event('workspacev2', 'fresh-after')
            await asyncio.wait_for(source.queue.join(), 1)
            self.assertEqual(calls, ['workspacev2'])
            self.assertEqual(source.dropped, 2)
        finally:
            for task in (flush, run):
                task.cancel()
            await asyncio.gather(flush, run, return_exceptions=True)

    async def test_model_lane_drops_active_old_and_during_even_after_cancelled_handoff(self):
        lane = ModelLane('synthetic')
        started = asyncio.Event()
        calls = []
        async def active():
            started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return 'stale-inflight-result'
        async def queued(name):
            calls.append(name)
            return name
        first = lane.submit(active)
        await asyncio.wait_for(started.wait(), 1)
        old = lane.submit(lambda: queued('old'))
        self.pause()
        during = lane.submit(lambda: queued('during'))
        self.resume()  # even a cancelled, already restored handoff invalidates old work
        try:
            self.assertEqual(await asyncio.wait_for(asyncio.gather(first, old, during), 1), [None, None, None])
            self.assertFalse(calls)
            fresh = lane.submit(lambda: queued('fresh'))
            self.assertEqual(await fresh, 'fresh')
            self.assertEqual(calls, ['fresh'])
            self.assertFalse(lane._pending_background)
        finally:
            await lane.stop()

    async def test_paused_foreground_and_background_cannot_capture(self):
        self.pause()
        result = await self.watcher.consider_event(self.event)
        self.assertEqual(result['reason'], 'residency_paused')
        with self.assertRaises(ResidencyError):
            await self.watcher.observe_requested(self.event)
        self.assertEqual(self.grabber.grabs, 0)
        self.assertFalse(self.models.decisions)
        self.assertFalse(self.models.visions)
        self.assertFalse(self.store.search(source='omni'))

    async def test_generation_changed_during_grab_discards_frame_before_model(self):
        grab = self.grabber.grab
        async def paused_grab(window):
            frame = await grab(window)
            self.pause()
            return frame
        self.grabber.grab = paused_grab
        result = await self.watcher.consider_event(self.event)
        self.assertFalse(result['captured'])
        self.assertEqual(self.grabber.grabs, 1)
        self.assertFalse(self.models.visions)
        self.assertFalse(self.store.search(source='omni'))

    async def test_generation_changed_during_omni_discards_result_without_second_pass(self):
        vision = self.models.vision
        async def paused_vision(png, prompt):
            answer = await vision(png, prompt)
            self.pause()
            return answer
        self.models.vision = paused_vision
        result = await self.watcher.consider_event(self.event)
        self.assertFalse(result['captured'])
        self.assertEqual(len(self.models.visions), 1)
        self.assertFalse(self.store.search(source='omni'))

    async def test_manual_async_on_off_observed_status_exact_subset_no_d1_or_preference(self):
        owner = await ManualSwitch.create(self.root, services=self.services)
        calls = []
        async def approve(detail):
            calls.append('approve')
            self.assertEqual(detail['prior'], ['decision', 'omni', 'text'])
            return True
        async def checkpoint():
            calls.append('checkpoint')
        async def release():
            calls.append('release')
        self.assertEqual((await owner.status())['state'], 'off')
        try:
            on = await owner.on(task_id='manual', approve=approve, checkpoint=checkpoint, release_lease=release)
            self.assertEqual(on['state'], 'on')
            self.assertTrue(on['visual_paused'])
            self.assertIsNotNone(owner.hermes_token)
            self.assertIsNone(observation_epoch())
            again = await owner.on(task_id='manual', approve=approve, checkpoint=checkpoint, release_lease=release)
            self.assertEqual(again['state'], 'on')
            self.assertEqual(calls, ['approve', 'checkpoint', 'release'])
            self.assertFalse(self.models.decisions)
        finally:
            off = await owner.off()
        self.assertEqual(off['state'], 'off')
        self.assertFalse(off['visual_paused'])
        self.assertIsNone(owner.hermes_token)
        self.assertEqual(self.services.active(self.services.current), {'text', 'omni', 'decision'})
        self.assertEqual((await owner.off())['state'], 'off')

    async def test_off_cancels_pending_on_and_reentrant_callback_fails_fast(self):
        owner = await ManualSwitch.create(self.root, services=self.services)
        entered = asyncio.Event()
        respond = asyncio.Event()
        async def approve(detail):
            with self.assertRaises(ResidencyError):
                await owner.off()
            entered.set()
            await respond.wait()
            return True
        async def noop():
            pass
        on = asyncio.create_task(owner.on(task_id='manual', approve=approve, checkpoint=noop, release_lease=noop))
        await asyncio.wait_for(entered.wait(), 1)
        off = asyncio.create_task(owner.off())
        await asyncio.sleep(.01)
        respond.set()
        self.assertEqual((await asyncio.wait_for(off, 1))['state'], 'off')
        await asyncio.gather(on, return_exceptions=True)
        self.assertFalse(self.services.events)
        self.assertEqual(self.c.state.read()['phase'], 'idle')

    async def test_manual_on_drains_actual_d1_http_before_launch(self):
        owner = await ManualSwitch.create(self.root, services=self.services)
        entered = threading.Event()
        finish = threading.Event()
        completed = threading.Event()
        model = Models(type('Config', (), {})())
        def request(*args):
            entered.set()
            finish.wait(timeout=2)
            completed.set()
            return {'answers': {}}
        async def approved(_):
            return True
        async def noop():
            pass
        with patch.object(model, '_http_call', request):
            d1 = asyncio.create_task(model.call('decision', '/v1/systemone', {}))
            self.assertTrue(await asyncio.to_thread(entered.wait, 1))
            on = asyncio.create_task(owner.on(task_id='manual', approve=approved, checkpoint=noop, release_lease=noop))
            try:
                for _ in range(100):
                    if (await owner.status())['phase'] == 'draining':
                        break
                    await asyncio.sleep(.005)
                self.assertEqual((await owner.status())['state'], 'transition')
                self.assertFalse(self.services.events)
                self.assertFalse(completed.is_set())
                finish.set()
                await asyncio.wait_for(d1, 1)
                self.assertEqual((await asyncio.wait_for(on, 1))['state'], 'on')
                self.assertTrue(completed.is_set())
            finally:
                finish.set()
                await asyncio.gather(d1, on, return_exceptions=True)
                await owner.off()

    async def test_cancel_manual_on_during_readiness_restores_and_clears_capability(self):
        owner = await ManualSwitch.create(self.root, services=self.services)
        entered = threading.Event()
        finish = threading.Event()
        ready = self.services.ready
        def blocked(role):
            if role == 'moe':
                entered.set()
                finish.wait(timeout=2)
            return ready(role)
        self.services.ready = blocked
        async def approved(_):
            return True
        async def noop():
            pass
        task = asyncio.create_task(owner.on(task_id='manual', approve=approved, checkpoint=noop, release_lease=noop))
        self.assertTrue(await asyncio.to_thread(entered.wait, 1))
        task.cancel()
        finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        self.assertEqual((await owner.status())['state'], 'off')
        self.assertIsNone(owner.hermes_token)
        self.assertEqual((await owner.off())['state'], 'off')
