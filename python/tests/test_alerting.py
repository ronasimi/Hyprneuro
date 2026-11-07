"""Tests for the alerting path: notifier, D1 gate, escalation, intake, store feed.

No real notify-send, no journalctl, no network sockets — all external deps are
faked. Verifies store + D1-gate + fail-safe + cooldown + intake parsing.
"""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.event_stream import EventIntake, MonitorEvent
from hyprneuro.escalation import EscalationRouter
from hyprneuro.notify import Notifier
from hyprneuro.models import Models, ModelError

NOW = int(time.time() * 1000)


class _FakeNotifier:
    def __init__(self):
        self.sent = []

    async def notify(self, summary, body="", *, severity="info"):
        self.sent.append((summary, body, severity))
        return True


class _FakeModels:
    def __init__(self, score=0.9, raise_exc=False):
        self.score = score
        self.raise_exc = raise_exc
        self.calls = []

    async def decide_alert(self, alert, threshold=0.6):
        self.calls.append(alert)
        if self.raise_exc:
            raise ModelError("d1 down")
        return {"notify_recommended": self.score >= threshold, "score": self.score}


class NotifierTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_binary_reports_failure_not_raise(self):
        n = Notifier(binary="/nonexistent/notify-send", timeout=2)
        self.assertFalse(await n.notify("summary", "body"))

    async def test_bounds_summary_and_body(self):
        captured = {}

        class _FakeProc:
            returncode = 0

            async def wait(self):
                return 0

            def kill(self):
                pass

        async def fake_exec(*argv, **kw):
            captured["argv"] = argv
            return _FakeProc()

        orig = asyncio.create_subprocess_exec
        asyncio.create_subprocess_exec = fake_exec
        try:
            await Notifier(timeout=2).notify(summary="x" * 500, body="y" * 500,
                                             severity="critical")
        finally:
            asyncio.create_subprocess_exec = orig
        # argv = [binary, -a, app, -u, urgency, --, summary, body]
        self.assertEqual(captured["argv"][4], "critical")   # urgency for critical
        self.assertEqual(captured["argv"][5], "--")
        self.assertLessEqual(len(captured["argv"][6]), 120)  # summary bounded
        self.assertLessEqual(len(captured["argv"][7]), 300)  # body bounded


class DecideAlertTests(unittest.IsolatedAsyncioTestCase):
    async def test_rejects_bad_source_and_metadata(self):
        m = Models.__new__(Models)  # validation path needs no config
        with self.assertRaises(ModelError):
            await m.decide_alert({"source": "bogus", "message": "x"})
        with self.assertRaises(ModelError):
            await m.decide_alert({"source": "journal", "message": ["not-a-string"]})


class EscalationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SidecarStore(Path(self.tmp.name) / "observations.sqlite3")
        self.notifier = _FakeNotifier()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def _event(self, **kw):
        base = dict(source="journal", kind="journal_alert", message="segfault at 0",
                    severity="error", observed_at="2026-11-06T00:00:00+00:00")
        base.update(kw)
        return MonitorEvent(**base)

    async def test_stores_and_notifies_when_d1_recommends(self):
        router = EscalationRouter(_FakeModels(score=0.9), self.store, notifier=self.notifier)
        out = await router.escalate(self._event())
        self.assertTrue(out["stored"])
        self.assertTrue(out["notified"])
        self.assertEqual(len(self.notifier.sent), 1)
        self.assertEqual(len(self.store.alerts()), 1)
        row = self.store.alerts()[0]
        self.assertEqual(row["d1_status"], "scored")
        self.assertEqual(row["d1_score"], 0.9)
        self.assertTrue(row["notify_recommended"])
        self.assertEqual(row["notification_status"], "sent")
        self.store.close()
        self.store = SidecarStore(Path(self.tmp.name) / "observations.sqlite3")
        self.assertEqual(self.store.alerts()[0], row)

    async def test_stores_but_silences_when_d1_declines(self):
        router = EscalationRouter(_FakeModels(score=0.1), self.store, notifier=self.notifier)
        out = await router.escalate(self._event())
        self.assertTrue(out["stored"])
        self.assertFalse(out["notified"])
        self.assertEqual(self.notifier.sent, [])
        self.assertEqual(len(self.store.alerts()), 1)  # still stored for the orchestrator

    async def test_fails_safe_when_d1_down(self):
        router = EscalationRouter(_FakeModels(raise_exc=True), self.store, notifier=self.notifier)
        warn = await router.escalate(self._event(severity="warning", message="warn msg"))
        self.assertFalse(warn["notified"])
        self.assertTrue(warn["d1_fallback"])
        crit = await router.escalate(self._event(severity="critical", message="crit msg"))
        self.assertTrue(crit["notified"])
        self.assertTrue(crit["d1_fallback"])
        self.assertEqual(self.store.alerts()[0]["d1_status"], "unavailable")

    async def test_cooldown_suppresses_repeat(self):
        router = EscalationRouter(_FakeModels(score=0.9), self.store, notifier=self.notifier,
                                  cooldown_seconds=300)
        await router.escalate(self._event())
        out = await router.escalate(self._event())
        self.assertEqual(out.get("reason"), "cooldown")
        self.assertTrue(out["stored"])
        row = self.store.alerts()[0]
        self.assertEqual(row["repeat_count"], 2)
        self.assertEqual(row["d1_status"], "scored")
        self.assertEqual(row["d1_score"], 0.9)
        self.assertIn("d1_evaluated_at_ms", row)
        self.assertEqual(row["notification_status"], "suppressed_cooldown")
        self.assertEqual(len(self.notifier.sent), 1)

    async def test_cooldown_repeat_outside_dedupe_window_still_stored(self):
        models = _FakeModels()
        router = EscalationRouter(models, self.store, notifier=self.notifier)
        now = time.time()
        with patch("hyprneuro.escalation.time.time", return_value=now):
            await router.escalate(self._event())
        with patch("hyprneuro.escalation.time.time", return_value=now + 4):
            out = await router.escalate(self._event())
        self.assertTrue(out["stored"])
        rows = self.store.alerts()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["d1_status"], "cooldown")
        self.assertIsNone(rows[0]["d1_score"])
        self.assertEqual(rows[1]["d1_status"], "scored")
        self.assertEqual(len(models.calls), 1)
        self.assertEqual(len(self.notifier.sent), 1)

    async def test_cooldown_memory_bound_and_expiry(self):
        models = _FakeModels()
        router = EscalationRouter(models, self.store, max_cooldowns=2, cooldown_seconds=10)
        with patch("hyprneuro.escalation.time.monotonic", return_value=10):
            for i in range(5):
                await router.escalate(self._event(message=f"error {i}"))
        self.assertEqual(len(router._last), 2)
        with patch("hyprneuro.escalation.time.monotonic", return_value=21):
            await router.escalate(self._event(message="error 4"))
        self.assertEqual(len(router._last), 1)
        self.assertEqual(len(models.calls), 6)

    async def test_fingerprint_includes_severity_identifier_and_full_message(self):
        router = EscalationRouter(_FakeModels(), self.store)
        events = [self._event(message="x" * 100 + "a"),
                  self._event(message="x" * 100 + "b"),
                  self._event(attributes={"identifier": "a"}),
                  self._event(attributes={"identifier": "b"}),
                  self._event(severity="critical")]
        for event in events:
            self.assertNotEqual((await router.escalate(event))["d1_status"], "cooldown")

    async def test_failed_notification_and_cancelled_gate_are_persisted(self):
        class FailingNotifier:
            async def notify(self, *args, **kwargs):
                raise OSError("bus unavailable")
        router = EscalationRouter(_FakeModels(), self.store, notifier=FailingNotifier())
        await router.escalate(self._event())
        self.assertEqual(self.store.alerts()[0]["notification_status"], "failed")
        entered = asyncio.Event()
        class BlockingModels:
            async def decide_alert(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        router = EscalationRouter(BlockingModels(), self.store)
        task = asyncio.create_task(router.escalate(self._event(message="other failure")))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        row = self.store.alerts()[0]
        self.assertEqual(row["d1_status"], "cancelled")
        self.assertEqual(row["notification_status"], "cancelled")

    async def test_cancelled_notification_preserves_d1_decision(self):
        entered = asyncio.Event()
        class BlockingNotifier:
            async def notify(self, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        router = EscalationRouter(_FakeModels(), self.store, notifier=BlockingNotifier())
        task = asyncio.create_task(router.escalate(self._event()))
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        row = self.store.alerts()[0]
        self.assertEqual(row["d1_status"], "scored")
        self.assertEqual(row["d1_score"], 0.9)
        self.assertEqual(row["notification_status"], "cancelled")


class JournalIntakeTests(unittest.TestCase):
    def test_parses_line_and_maps_severity(self):
        intake = EventIntake()
        line = json.dumps({"MESSAGE": "  segfault   at 0 ", "PRIORITY": "3",
                           "SYSLOG_IDENTIFIER": "myapp"}).encode()
        ev = intake._journal_event(line)
        self.assertEqual(ev.severity, "error")
        self.assertEqual(ev.message, "segfault at 0")
        self.assertEqual(ev.kind, "journal_alert")
        self.assertEqual(ev.attributes["identifier"], "myapp")

    def test_critical_priority_maps_to_critical(self):
        intake = EventIntake()
        ev = intake._journal_event(json.dumps({"MESSAGE": "kernel panic", "PRIORITY": "1"}).encode())
        self.assertEqual(ev.severity, "critical")

    def test_ignores_empty_and_bad(self):
        intake = EventIntake()
        self.assertIsNone(intake._journal_event(b"not json"))
        for value in (None, [], 1, "text", {"MESSAGE": [1, 2]},
                      {"MESSAGE": "debug", "PRIORITY": "7"},
                      {"MESSAGE": "bad", "PRIORITY": -1},
                      {"MESSAGE": "bad", "PRIORITY": float("inf")},
                      {"MESSAGE": "bad", "PRIORITY": True}):
            self.assertIsNone(intake._journal_event(json.dumps(value).encode()))
        self.assertEqual(intake._journal_event(b'{"MESSAGE":"emergency","PRIORITY":0}').severity,
                         "critical")
        self.assertIsNone(intake._journal_event(json.dumps({"MESSAGE": "   "}).encode()))


class NetworkIntakeTests(unittest.TestCase):
    def test_down_transition_and_error_jump(self):
        intake = EventIntake()
        events = intake._network_events("eth0", "down", 0, "up", 0)
        self.assertEqual([e.severity for e in events], ["error"])
        events = intake._network_events("eth0", "up", 5, "up", 0)
        self.assertEqual([e.severity for e in events], ["warning"])
        self.assertIn("5 new packet error", events[0].message)
        self.assertEqual(intake._network_events("eth0", "up", 5, "up", 5), [])
        self.assertEqual(intake._network_events("eth0", "down", 0, None, None), [])  # no baseline


class StoreAlertsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SidecarStore(Path(self.tmp.name) / "observations.sqlite3")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_alerts_returns_severity_and_reason(self):
        self.store.record({"source": "journal", "kind": "journal_alert", "time_ms": NOW,
                           "message": "[error] disk full", "event_key": "k1"})
        self.store.record({"source": "network", "kind": "network_alert", "time_ms": NOW,
                           "message": "[warning] eth0 down", "event_key": "k2"})
        self.store.record({"source": "chrome", "kind": "tab_activated", "time_ms": NOW,
                           "title": "not an alert"})
        rows = self.store.alerts()
        self.assertEqual(len(rows), 2)
        self.assertEqual({r["severity"] for r in rows}, {"error", "warning"})
        self.assertTrue(all(r["reason"] for r in rows))
        self.assertTrue(all(r["source"] in ("journal", "network") for r in rows))
        self.assertTrue(all(r["d1_status"] == "unknown" for r in rows))
        self.assertTrue(all(r["notified"] is None for r in rows))

    def test_additive_schema_upgrade_and_prune_cascades_outcomes(self):
        # Simulate an existing DB from before alert outcomes were introduced.
        self.store.db.execute("DROP TABLE alert_state")
        self.store.close()
        self.store = SidecarStore(Path(self.tmp.name) / "observations.sqlite3")
        result = self.store.record({"source": "journal", "kind": "journal_alert",
                                   "time_ms": NOW - 10000, "message": "[error] failed"})
        self.store.update_alert(result["id"], {"d1_status": "scored", "d1_score": 0.8})
        self.assertEqual(self.store.alert_outcome(result["id"])["d1_score"], 0.8)
        self.store.prune(before_ms=NOW)
        self.assertIsNone(self.store.alert_outcome(result["id"]))


class _Process:
    def __init__(self, *, returncode=None, data=None):
        self.returncode = returncode
        self.killed = False
        self.waited = False
        self.entered = asyncio.Event()
        self.exited = asyncio.Event()
        self.stdout = asyncio.StreamReader() if data is not None else None
        if self.stdout is not None:
            self.stdout.feed_data(data)
            self.stdout.feed_eof()

    async def wait(self):
        self.entered.set()
        if self.returncode is None:
            await self.exited.wait()
        self.waited = True
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9
        self.exited.set()


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def test_notify_timeout_kills_and_reaps(self):
        proc = _Process()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            self.assertFalse(await Notifier(timeout=0.01).notify("--help", "-body"))
        self.assertTrue(proc.killed and proc.waited)

    async def test_notify_cancellation_kills_and_reaps(self):
        proc = _Process()
        with patch("asyncio.create_subprocess_exec", return_value=proc) as spawn:
            task = asyncio.create_task(Notifier().notify("--help", "-body"))
            await proc.entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(spawn.call_args.args[-3:], ("--", "--help", "-body"))
        self.assertTrue(proc.killed and proc.waited)

    async def test_notify_nonzero_exit_and_kill_race(self):
        proc = _Process(returncode=1)
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            self.assertFalse(await Notifier().notify("test"))
        self.assertTrue(proc.waited)
        self.assertFalse(proc.killed)
        class RacedProcess(_Process):
            def kill(self):
                super().kill()
                raise ProcessLookupError()
        proc = RacedProcess()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            self.assertFalse(await Notifier(timeout=0.01).notify("test"))
        self.assertTrue(proc.waited)

    async def test_journal_command_reconnect_failures_and_delivery_failure(self):
        intake = EventIntake(reconnect_seconds=0.001)
        proc = _Process(data=b'{"MESSAGE":"failure","PRIORITY":3}\n')
        spawned = asyncio.Event()
        delivered = []
        calls = []
        async def spawn(*args, **kwargs):
            calls.append((args, kwargs))
            if len(calls) == 1:
                raise FileNotFoundError("journalctl unavailable")
            if len(calls) == 2:
                return proc
            spawned.set()
            await asyncio.Event().wait()
        async def deliver(event):
            delivered.append(event)
            raise RuntimeError("temporary delivery failure")
        with patch("asyncio.create_subprocess_exec", side_effect=spawn):
            task = asyncio.create_task(intake.follow_journal(deliver))
            await asyncio.wait_for(spawned.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertEqual(calls[0][0], ("journalctl", "--follow", "--output=json",
                                      "--priority=4", "--lines=0", "--no-pager"))
        self.assertEqual(calls[0][1]["limit"], intake.max_line_bytes)
        self.assertEqual(len(delivered), 1)
        self.assertTrue(proc.killed and proc.waited)
        self.assertEqual(intake.failures, 3)

    async def test_journal_reconnect_backoff_is_capped(self):
        delays = []
        async def pause(delay):
            delays.append(delay)
            if len(delays) == 7:
                raise asyncio.CancelledError()
        async def spawn(*args, **kwargs):
            return _Process(returncode=1, data=b"")
        with patch("asyncio.create_subprocess_exec", side_effect=spawn), \
             patch("asyncio.sleep", side_effect=pause):
            with self.assertRaises(asyncio.CancelledError):
                await EventIntake().follow_journal(None)
        self.assertEqual(delays, [1, 2, 4, 8, 16, 30, 30])

    async def test_journal_oversized_record_resynchronizes(self):
        intake = EventIntake(max_line_bytes=100)
        reader = asyncio.StreamReader()
        reader.feed_data(b"x" * 20000 + b'\n{"MESSAGE":"valid","PRIORITY":"3"}\n')
        reader.feed_eof()
        lines = [line async for line in intake._journal_lines(reader)]
        self.assertEqual(len(lines), 1)
        self.assertEqual(intake._journal_event(lines[0]).message, "valid")
        self.assertEqual(intake.oversized, 1)

    async def test_journal_cancellation_while_delivering_reaps_child(self):
        proc = _Process(data=b'{"MESSAGE":"failure","PRIORITY":3}\n')
        entered = asyncio.Event()
        async def deliver(event):
            entered.set()
            await asyncio.Event().wait()
        with patch("asyncio.create_subprocess_exec", return_value=proc):
            task = asyncio.create_task(EventIntake().follow_journal(deliver))
            await entered.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertTrue(proc.killed and proc.waited)


class AlertServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_alerts_rpc_and_truthful_health_and_shutdown(self):
        from hyprneuro.sidecar import serve
        from hyprneuro.sidecar_client import request
        emitted = asyncio.Event()
        stopped = asyncio.Event()
        notifier = _FakeNotifier()
        async def journal(intake, deliver):
            try:
                await deliver(MonitorEvent(source="journal", kind="journal_alert",
                    message="disk full", severity="critical", observed_at="now"))
                emitted.set()
                await asyncio.Event().wait()
            finally:
                stopped.set()
        async def network(intake, deliver):
            await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket = root / "runtime/sidecar.sock"
            stop = asyncio.Event()
            with patch.object(EventIntake, "follow_journal", journal), \
                 patch.object(EventIntake, "network_alerts", network), \
                 patch("hyprneuro.notify.Notifier", return_value=notifier):
                task = asyncio.create_task(serve(allow_ingest=True, alert=True,
                    socket_path=socket, db_path=root / "state/log.db", shutdown=stop,
                    models=_FakeModels()))
                try:
                    await asyncio.wait_for(emitted.wait(), 1)
                    health = await request({"action": "health"}, socket_path=socket)
                    self.assertTrue(health["alert_enabled"])
                    self.assertNotIn("models_invoked", health)
                    rows = await request({"action": "alerts"}, socket_path=socket)
                    self.assertEqual(rows[0]["d1_score"], 0.9)
                    self.assertEqual(rows[0]["notification_status"], "sent")
                    self.assertTrue(rows[0]["notify_recommended"])
                    with self.assertRaisesRegex(RuntimeError, "limit must"):
                        await request({"action": "alerts", "limit": 51}, socket_path=socket)
                finally:
                    stop.set()
                    await asyncio.wait_for(task, 1)
            self.assertTrue(stopped.is_set())
            self.assertFalse(socket.exists())

    async def test_alerting_requires_ingest_opt_in(self):
        from hyprneuro.sidecar import serve
        with self.assertRaisesRegex(ValueError, "requires explicit"):
            await serve(alert=True)


if __name__ == "__main__":
    unittest.main()
