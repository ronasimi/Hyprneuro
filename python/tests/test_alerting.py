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

from hyprharness_sidecar.sidecar_store import SidecarStore
from hyprharness_sidecar.event_stream import EventIntake, MonitorEvent
from hyprharness_sidecar.escalation import EscalationRouter
from hyprharness_sidecar.notify import Notifier
from hyprharness_sidecar.models import Models, ModelError

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
        # argv = [binary, -a, app, -u, urgency, summary, body]
        self.assertEqual(captured["argv"][4], "critical")   # urgency for critical
        self.assertLessEqual(len(captured["argv"][5]), 120)  # summary bounded
        self.assertLessEqual(len(captured["argv"][6]), 300)  # body bounded


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

    async def test_cooldown_suppresses_repeat(self):
        router = EscalationRouter(_FakeModels(score=0.9), self.store, notifier=self.notifier,
                                  cooldown_seconds=300)
        await router.escalate(self._event())
        out = await router.escalate(self._event())
        self.assertEqual(out.get("reason"), "cooldown")
        self.assertEqual(len(self.notifier.sent), 1)


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


if __name__ == "__main__":
    unittest.main()
