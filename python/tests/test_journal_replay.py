import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from hyprneuro.event_stream import EventIntake, MonitorEvent
from hyprneuro.escalation import EscalationRouter
from hyprneuro.sidecar_store import SidecarStore
from test_alerting import _FakeModels, _FakeNotifier, _Process


class ReplayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'log.db'
        self.store = SidecarStore(self.path)
        self.models = _FakeModels()
        self.notifier = _FakeNotifier()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def event(self, cursor='c1', age=0):
        return MonitorEvent('journal', 'journal_alert', 'disk failed', 'critical', 'now',
                            attributes={'cursor': cursor, 'realtime_ms': int(time.time()*1000)-age})

    def router(self):
        return EscalationRouter(self.models, self.store, notifier=self.notifier)

    async def test_restart_identity_does_not_increment_repeat_or_renotify(self):
        await self.router().escalate(self.event())
        self.store.close()
        self.store = SidecarStore(self.path)
        await self.router().escalate(self.event())
        self.assertEqual(self.store.alerts()[0]['repeat_count'], 1)
        self.assertEqual(len(self.notifier.sent), 1)
        self.assertEqual(self.store.journal_checkpoint()['cursor'], 'c1')

    async def test_checkpoint_and_evidence_rollback_together(self):
        self.store.db.execute("CREATE TRIGGER fail_job BEFORE INSERT ON journal_events BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaisesRegex(Exception, 'test'):
            await self.router().escalate(self.event())
        self.assertEqual(self.store.alerts(), [])
        self.assertIsNone(self.store.journal_checkpoint())

    async def test_recovery_after_evidence_and_after_gate(self):
        e = self.event()
        item = {'source': 'journal', 'kind': 'journal_alert', 'message': '[critical] disk failed',
                'time_ms': e.attributes['realtime_ms']}
        result = self.store.record_journal(item, asdict(e))
        self.assertEqual(self.store.journal_status()['pending'], 1)
        await self.router().recover()
        self.assertEqual(self.store.journal_status()['pending'], 0)
        self.assertEqual(len(self.models.calls), 1)
        # Simulate process death after saving the gate, before notification.
        state = self.store.alert_outcome(result['id'])
        state['notification_status'] = 'pending'
        self.store.update_alert(result['id'], state)
        await self.router().recover()
        self.assertEqual(len(self.models.calls), 1)
        self.assertEqual(len(self.notifier.sent), 2)  # explicitly NOT exactly-once

    async def test_stale_and_global_persisted_rate_limits(self):
        await self.router().escalate(self.event(age=180000))
        self.assertEqual(self.store.alerts()[0]['notification_status'], 'suppressed_stale')
        for i in range(4):
            await self.router().escalate(self.event(cursor=f'new{i}'))
        self.assertEqual(len(self.notifier.sent), 3)
        self.assertIn('suppressed_rate', [r['notification_status'] for r in self.store.alerts()])

    async def test_bounded_cursor_fallback_and_subprocess_cleanup(self):
        await self.router().escalate(self.event())
        class DeferredExit(_Process):
            async def wait(self):
                self.returncode = 1
                self.waited = True
                return 1
        failed = DeferredExit(data=b'')  # stdout EOF precedes child-exit callback
        procs = [failed, _Process(data=(json.dumps({
            'MESSAGE':'later', 'PRIORITY':3, '__CURSOR':'c2',
            '__REALTIME_TIMESTAMP':str(int(time.time()*1000000))})+'\n').encode())]
        calls = []
        done = asyncio.Event()
        async def spawn(*args, **kwargs):
            calls.append(args)
            if procs:
                return procs.pop(0)
            done.set()
            await asyncio.Event().wait()
        intake = EventIntake(store=self.store, catchup_records=1, reconnect_seconds=.001)
        with patch('asyncio.create_subprocess_exec', side_effect=spawn):
            task = asyncio.create_task(intake.follow_journal(self.router().escalate))
            await asyncio.wait_for(done.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(failed.waited)
        self.assertFalse(failed.killed)
        self.assertIn('--after-cursor=c1', calls[0])
        self.assertFalse(any(x.startswith('--after-cursor') for x in calls[1]))
        self.assertIn('--lines=0', calls[2])
        self.assertIn('budget', self.store.journal_status()['last_gap']['reason'])
        self.assertEqual(self.store.journal_checkpoint()['cursor'], 'c2')

    async def test_oversized_frames_consume_catchup_budget(self):
        await self.router().escalate(self.event())
        proc = _Process(data=b'x'*1000+b'\n')
        calls = []
        done = asyncio.Event()
        async def spawn(*args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return proc
            done.set()
            await asyncio.Event().wait()
        intake = EventIntake(store=self.store, max_line_bytes=100, catchup_records=1, reconnect_seconds=.001)
        with patch('asyncio.create_subprocess_exec', side_effect=spawn):
            task = asyncio.create_task(intake.follow_journal(self.router().escalate))
            await asyncio.wait_for(done.wait(),1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(intake.oversized,1)
        self.assertIn('budget',self.store.journal_status()['last_gap']['reason'])
        self.assertIn('--lines=0',calls[1])
        self.assertTrue(proc.killed and proc.waited)
