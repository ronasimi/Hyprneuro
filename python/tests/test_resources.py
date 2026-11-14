import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch
from hyprneuro.event_stream import ResourceAlerts, EventIntake
from hyprneuro.monitor import Monitor
from hyprneuro.sidecar import SidecarServer, serve


class ResourceTests(unittest.TestCase):
    def test_duration_hysteresis_and_missing_metric(self):
        d = ResourceAlerts(duration=10)
        def sample(value, now):
            return d.events({'cpu_percent': {'cpu': value}}, now=now)
        self.assertEqual(sample(95, 0), [])
        self.assertEqual(sample(95, 9), [])
        self.assertEqual(len(sample(95, 10)), 1)
        self.assertEqual(sample(80, 11), [])
        self.assertEqual(sample(95, 30), [])
        self.assertEqual(sample(70, 31), [])
        self.assertEqual(sample(95, 32), [])
        self.assertEqual(len(sample(95, 42)), 1)
        d.events({}, now=43)
        self.assertEqual(sample(95, 44), [])

    def test_real_metrics_only(self):
        snap = {'memory_kib': {'MemTotal': 100, 'MemAvailable': 2},
                'disk_used_percent': {'/': 99},
                'pressure': {'io': 'some avg10=40.00 avg60=0.00 total=500', 'cpu': 'malformed'},
                'temperatures_millicelsius': {'sensor': 90000},
                'gpu': {'card0': {'gpu_busy_percent': 99}, 'card1': {'mem_info_vram_used': 100000}}}
        rows = ResourceAlerts(duration=0).events(snap, now=0)
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(r.source == 'resource' for r in rows))
        self.assertFalse(any('card1' in r.message for r in rows))


class ResourceIntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_requires_optin_and_uses_monitor_run(self):
        with self.assertRaisesRegex(ValueError, 'requires explicit'):
            await serve(alert_resources=True)
        async def run(monitor, on_sample):
            await on_sample({'cpu_percent': {'cpu': 99}})
            await on_sample({'cpu_percent': {'cpu': 99}})
            self.assertEqual(intake.resource_status['samples'], 2)
            self.assertEqual(intake.resource_status['cpu_pct'], 99)
            self.assertIsNone(intake.resource_status['ram_pct'])
            self.assertIsNone(intake.resource_status['root_disk_pct'])
            self.assertIsInstance(intake.resource_status['observed_at_ms'], int)
        rows = []
        async def deliver(event):
            rows.append(event)
        with patch('hyprneuro.monitor.Monitor.run', run), patch('hyprneuro.event_stream.time.monotonic', side_effect=[0, 31]):
            intake = EventIntake()
            await intake.resource_alerts(deliver)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(intake.resource_snapshot)
        self.assertIsNone(intake.monitor)
        self.assertEqual(intake.resource_status, {'samples': 0, 'observed_at_ms': None})


class CachedMonitoringTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.intake = EventIntake()
        self.server = SidecarServer(Mock(search=Mock(return_value=[])), resources_enabled=True)
        self.server.event_intake = self.intake
        self.server.active_settings = {"alert_resources": True}
        # Existing endpoint readiness remains separate; never contact a model here.
        health = patch.object(self.server, "_model_health",
                              new_callable=AsyncMock, return_value={"text": False, "omni": True})
        self.health = health.start()
        self.addCleanup(health.stop)

    async def rpc(self):
        return await self.server.dispatch_async({"action": "monitoring", "limit": 5})

    async def test_multiple_rpcs_use_cache_without_sleep_sampling_or_kernel_reads(self):
        self.intake.resource_snapshot = {
            "cpu_percent": {"cpu": 12.345},
            "memory_kib": {"MemTotal": 8192, "MemAvailable": 2048},
            "model_processes": {"text": {"available": True, "rss_kib": 1234}}}
        with patch.object(Monitor, "sample", side_effect=AssertionError("RPC sampled")), \
             patch("builtins.open", side_effect=AssertionError("RPC kernel read")), \
             patch("pathlib.Path.open", side_effect=AssertionError("RPC kernel read")), \
             patch("time.sleep", side_effect=AssertionError("RPC blocking sleep")), \
             patch("asyncio.sleep", side_effect=AssertionError("RPC sleep")):
            for _ in range(5):
                result = await self.rpc()
                self.assertEqual(result["schema"], "hyprneuro.monitoring/1")
                self.assertEqual(result["cpu_pct"], 12.3)
                self.assertEqual(result["ram"], {"total_mb": 8, "used_mb": 6, "pct": 75.0})
                self.assertEqual(result["models"], {"text": False, "omni": True})
        self.assertEqual(self.health.await_count, 5)

    async def test_startup_disabled_and_missing_cpu_are_null_not_zero(self):
        result = await self.rpc()
        self.assertIsNone(result["cpu_pct"])
        self.assertIsNone(result["ram"])
        self.intake.resource_snapshot = {"cpu_percent": {}, "memory_kib": {}}
        self.assertIsNone((await self.rpc())["cpu_pct"])
        self.intake.resource_snapshot = {"cpu_percent": {"cpu": 0},
            "memory_kib": {"MemTotal": 2048, "MemAvailable": 2048}}
        self.assertEqual((await self.rpc())["cpu_pct"], 0)
        self.assertEqual((await self.rpc())["ram"]["used_mb"], 0)
        self.server.active_settings["alert_resources"] = False
        result = await self.rpc()
        self.assertIsNone(result["cpu_pct"])
        self.assertIsNone(result["ram"])
        self.server.active_settings["alert_resources"] = True
        self.server.resources_enabled = False
        self.assertIsNone((await self.rpc())["cpu_pct"])
        self.assertIsNone((await self.rpc())["ram"])

    async def test_invalid_ram_is_unknown_in_rpc_status_and_alerts(self):
        cases = ({}, {"MemTotal": 100}, {"MemAvailable": 0},
                 {"MemTotal": 0, "MemAvailable": 0},
                 {"MemTotal": -1, "MemAvailable": 0},
                 {"MemTotal": 100, "MemAvailable": -1},
                 {"MemTotal": 100, "MemAvailable": 101},
                 {"MemTotal": "100", "MemAvailable": 0},
                 {"MemTotal": 100, "MemAvailable": None})
        async def run(monitor, on_sample):
            for memory in cases:
                with self.subTest(memory=memory):
                    snapshot = {"memory_kib": memory}
                    await on_sample(snapshot)
                    self.assertIs(self.intake.resource_snapshot, snapshot)
                    self.assertIsNone(self.intake.resource_status["ram_pct"])
                    self.assertIsNone((await self.rpc())["ram"])
                    self.assertEqual(ResourceAlerts(duration=0).events(snapshot, now=0), [])
            snapshot = {"memory_kib": {"MemTotal": 2048, "MemAvailable": 0}}
            await on_sample(snapshot)
            self.assertEqual(self.intake.resource_status["ram_pct"], 100)
            self.assertEqual((await self.rpc())["ram"],
                             {"total_mb": 2, "used_mb": 2, "pct": 100.0})
        with patch.object(Monitor, "run", run):
            await self.intake.resource_alerts(AsyncMock())

    async def test_one_sampler_shared_snapshot_published_before_slow_alert_and_cancel_cleanup(self):
        first = {"cpu_percent": {}, "memory_kib": {"MemTotal": 8192, "MemAvailable": 4096}}
        second = {"cpu_percent": {"cpu": 99},
                  "memory_kib": {"MemTotal": 8192, "MemAvailable": 2048}}
        between_ticks, next_tick, delivering = asyncio.Event(), asyncio.Event(), asyncio.Event()
        detector = ResourceAlerts(duration=0)
        async def tick(_):
            between_ticks.set()
            await next_tick.wait()
        async def deliver(event):
            self.assertIs(self.intake.resource_snapshot, second)
            self.assertEqual(self.intake.resource_status["samples"], 2)
            delivering.set()
            await asyncio.Event().wait()  # Cancel while alert delivery applies backpressure.
        with patch("hyprneuro.monitor.Monitor", wraps=Monitor) as constructor, \
             patch.object(Monitor, "sample", side_effect=[first, second]) as sample, \
             patch("hyprneuro.monitor.asyncio.sleep", tick), \
             patch("hyprneuro.event_stream.ResourceAlerts", return_value=detector), \
             patch.object(detector, "events", wraps=detector.events) as events:
            task = asyncio.create_task(self.intake.resource_alerts(deliver))
            try:
                await asyncio.wait_for(between_ticks.wait(), 1)
                monitor = self.intake.monitor
                for _ in range(3):
                    self.assertIsNone((await self.rpc())["cpu_pct"])
                self.assertEqual(sample.call_count, 1)
                self.assertIs(events.call_args.args[0], first)
                next_tick.set()
                await asyncio.wait_for(delivering.wait(), 1)
                self.assertIs(self.intake.monitor, monitor)
                self.assertIs(events.call_args.args[0], second)
                for _ in range(3):
                    result = await self.rpc()
                    self.assertEqual(result["cpu_pct"], 99)
                    self.assertEqual(result["ram"]["pct"], 75)
                self.assertEqual(sample.call_count, 2)
                constructor.assert_called_once_with()
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertIsNone(self.intake.monitor)
        self.assertIsNone(self.intake.resource_snapshot)
        self.assertEqual(self.intake.resource_status, {"samples": 0, "observed_at_ms": None})
        self.assertIsNone((await self.rpc())["cpu_pct"])
        self.assertIsNone((await self.rpc())["ram"])

    async def test_normal_stop_failure_and_restart_clear_cache(self):
        monitors = []
        async def run(monitor, on_sample):
            monitors.append(monitor)
            self.assertIsNone(self.intake.resource_snapshot)
            await on_sample({"cpu_percent": {"cpu": 50}})
            self.assertEqual((await self.rpc())["cpu_pct"], 50)
            if len(monitors) == 2:
                raise RuntimeError("synthetic collector failure")
        with patch.object(Monitor, "run", run):
            await self.intake.resource_alerts(AsyncMock())
            self.assertIsNone(self.intake.resource_snapshot)
            self.assertIsNone((await self.rpc())["cpu_pct"])
            with self.assertRaisesRegex(RuntimeError, "synthetic collector failure"):
                await self.intake.resource_alerts(AsyncMock())
        self.assertIsNot(monitors[0], monitors[1])
        self.assertIsNone(self.intake.monitor)
        self.assertIsNone(self.intake.resource_snapshot)
        self.assertIsNone((await self.rpc())["cpu_pct"])

    async def test_delivery_failure_keeps_cache_until_next_sample_replaces_it(self):
        high = {"cpu_percent": {"cpu": 99}}
        missing = {"cpu_percent": {}, "memory_kib": {}}
        sampled, resume = asyncio.Queue(), asyncio.Queue()
        async def tick(_):
            await sampled.put(None)
            await resume.get()
        with patch.object(Monitor, "sample", side_effect=[high, missing]), \
             patch("hyprneuro.monitor.asyncio.sleep", tick), \
             patch("hyprneuro.event_stream.ResourceAlerts", return_value=ResourceAlerts(duration=0)):
            deliver = AsyncMock(side_effect=OSError("synthetic alert delivery failure"))
            task = asyncio.create_task(self.intake.resource_alerts(deliver))
            try:
                await asyncio.wait_for(sampled.get(), 1)
                self.assertEqual(self.intake.monitor.delivery_failures, 1)
                deliver.assert_awaited_once()
                self.assertIs(self.intake.resource_snapshot, high)
                self.assertEqual((await self.rpc())["cpu_pct"], 99)
                resume.put_nowait(None)
                await asyncio.wait_for(sampled.get(), 1)
                self.assertIs(self.intake.resource_snapshot, missing)
                self.assertIsNone(self.intake.resource_status["cpu_pct"])
                self.assertIsNone((await self.rpc())["cpu_pct"])
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        self.assertIsNone(self.intake.resource_snapshot)
