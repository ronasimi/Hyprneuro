"""Unit tests for telemetry + adaptive residency / idle compaction (Phase 8)."""
import tempfile
import time
import unittest

from hyprneuro.application import AppRegistry
from hyprneuro.telemetry import IdleCompactor, Telemetry
from hyprneuro.sidecar_store import SidecarStore
from pathlib import Path


def _registry(n=6):
    reg = AppRegistry(max_recent=8)
    for i in range(n):
        reg.on_focus({"address": f"0x{i:08x}", "class": f"app{i}", "title": "t",
                      "workspace": {"id": 1}}, now_ms=1000 + i * 1000)
    return reg


class TelemetryTests(unittest.TestCase):
    def test_bump_and_snapshot(self):
        t = Telemetry()
        t.bump("ipc_requests", 3)
        t.bump("skill_load")
        snap = t.snapshot()
        self.assertEqual(snap["counters"]["ipc_requests"], 3)
        self.assertEqual(snap["counters"]["skill_load"], 1)
        self.assertEqual(snap["counters"]["focus_events"], 0)
        self.assertIn("uptime_ms", snap)
        self.assertIn("idle_ms", snap)

    def test_unknown_counter_ignored(self):
        t = Telemetry()
        t.bump("not_a_real_counter")  # no-op, no key created
        self.assertNotIn("not_a_real_counter", t.snapshot()["counters"])

    def test_idle_ms_reflects_activity(self):
        t = Telemetry()
        t.bump("ipc_requests")
        self.assertLess(t.idle_ms(), 100)


class IdleCompactorTests(unittest.TestCase):
    def test_noop_while_active(self):
        reg = _registry(6)
        store = None
        comp = IdleCompactor(reg, store, idle_ms=60_000)
        t = Telemetry()
        t.bump("ipc_requests")  # just active
        r = comp.compact(t)
        self.assertFalse(r["compacted"])
        self.assertEqual(r["reason"], "active")
        self.assertEqual(len(reg.recent), 6)  # untouched

    def test_compacts_when_idle(self):
        reg = _registry(6)
        comp = IdleCompactor(reg, None, idle_ms=60_000, registry_idle_recent=2)
        t = Telemetry()
        # Simulate 70s of inactivity.
        now = int(time.time() * 1000) + 70_000
        r = comp.compact(t, now_ms=now)
        self.assertTrue(r["compacted"])
        self.assertEqual(r["reason"], "idle")
        self.assertEqual(len(reg.recent), 2)  # trimmed to idle footprint
        self.assertEqual(r["details"]["registry_recent_before"], 6)
        self.assertEqual(r["details"]["registry_recent_after"], 2)
        self.assertEqual(comp.compactions, 1)

    def test_ttl_bounds(self):
        with self.assertRaises(ValueError):
            IdleCompactor(None, None, idle_ms=100)  # < 1s
        with self.assertRaises(ValueError):
            IdleCompactor(None, None, registry_idle_recent=9)


class StoreCompactionTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.path = Path(self._tmpdir) / "s.db"
        self.store = SidecarStore(self.path)

    def tearDown(self):
        self.store.close()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_app_memory_trim(self):
        for i in range(20):
            self.store.app_memory_remember("app", f"k{i}", "{}", app_id="chrome")
        self.assertEqual(len(self.store.app_memory_recall("app", limit=50)), 20)
        evicted = self.store.app_memory_trim(keep=10)
        self.assertEqual(evicted, 10)
        remaining = self.store.app_memory_recall("app", limit=50)
        self.assertEqual(len(remaining), 10)
        # Trimming again with everything under the cap evicts nothing.
        self.assertEqual(self.store.app_memory_trim(keep=10), 0)

    def test_size_probe(self):
        self.store.app_memory_remember("app", "k", "{}", app_id="chrome")
        self.store.task_create("goal")
        size = self.store.size()
        self.assertGreaterEqual(size["app_memory"], 1)
        self.assertGreaterEqual(size["tasks"], 1)
        for table in ("observations", "skill_manifests", "authorizations"):
            self.assertIn(table, size)


if __name__ == "__main__":
    unittest.main()
