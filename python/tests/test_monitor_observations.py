"""Bounded passive observations and deterministic network fault path."""
import asyncio
import unittest
from unittest.mock import patch
from hyprneuro.event_stream import EventIntake


class NetworkObservationTests(unittest.IsolatedAsyncioTestCase):
    async def sample_twice(self, interfaces):
        intake = EventIntake()
        delivered = []
        tick = 0
        def devices():
            nonlocal tick
            tick += 1
            return interfaces
        def state(name):
            return ('up', 0) if tick == 1 else ('down', 2)
        async def deliver(event):
            delivered.append(event)
        with patch('hyprneuro.event_stream._net_interfaces', devices), patch('hyprneuro.event_stream._iface_state', state):
            task = asyncio.create_task(intake.network_alerts(deliver, interval=.001))
            try:
                for _ in range(100):
                    if intake.network_status['samples'] >= 2:
                        break
                    await asyncio.sleep(.001)
                self.assertGreaterEqual(intake.network_status['samples'], 2)
            finally:
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
        return intake.network_status, delivered

    async def test_snapshots_and_faults_are_from_passive_readings(self):
        status, events = await self.sample_twice(['lo', 'test0'])
        self.assertEqual(status['interfaces'], {'test0': {'state': 'down', 'errors': 2}})
        self.assertIsInstance(status['observed_at_ms'], int)
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e.source == 'network' for e in events))
        self.assertIn('went down', events[0].message)
        self.assertIn('2 new packet error', events[1].message)

    async def test_interface_snapshot_is_bounded(self):
        status, _ = await self.sample_twice([f'test{i}' for i in range(100)])
        self.assertEqual(len(status['interfaces']), 64)
