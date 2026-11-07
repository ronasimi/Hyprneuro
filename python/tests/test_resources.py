import asyncio
import unittest
from unittest.mock import patch
from hyprneuro.event_stream import ResourceAlerts, EventIntake
from hyprneuro.sidecar import serve


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
        rows = []
        async def deliver(event):
            rows.append(event)
        with patch('hyprneuro.monitor.Monitor.run', run), patch('hyprneuro.event_stream.time.monotonic', side_effect=[0, 31]):
            await EventIntake().resource_alerts(deliver)
        self.assertEqual(len(rows), 1)
