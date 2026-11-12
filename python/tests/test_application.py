"""Unit tests for the application-aware context backbone (model-free)."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from hyprneuro.application import (
    AppProfile, AppRegistry, AppWatcher, SkillIndex, TieredMemory, normalize_app_id,
)

NOW = int(time.time() * 1000)


def window(class_name="google-chrome", title="Tab", address="0x1", workspace=1, pid=100):
    return {"address": address, "class": class_name, "title": title,
            "workspace": {"id": workspace}, "pid": pid}


class NormalizeAppIdTests(unittest.TestCase):
    def test_lowercases_and_strips(self):
        self.assertEqual(normalize_app_id("Google-Chrome"), "google-chrome")
        self.assertEqual(normalize_app_id("  Thunar "), "thunar")

    def test_rejects_empty_and_unsafe(self):
        for bad in ("", "   ", "a/b", "has space", "\u00e9moji", "x" * 200, "-lead", ".dot"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                normalize_app_id(bad)


class AppRegistryTests(unittest.TestCase):
    def test_focus_updates_focused_and_lru(self):
        reg = AppRegistry(max_recent=5, debounce_ms=0)
        r1 = reg.on_focus(window("google-chrome", address="0x1"), NOW)
        self.assertTrue(r1["changed"])
        self.assertEqual(reg.focused.app_id, "google-chrome")
        self.assertEqual(len(reg.recent), 1)

    def test_lru_eviction_and_order(self):
        reg = AppRegistry(max_recent=3, debounce_ms=0)
        for i, cls in enumerate(["a-app", "b-app", "c-app", "d-app"]):
            reg.on_focus(window(cls, address=f"0x{i}"), NOW + i * 1000)
        self.assertEqual(len(reg.recent), 3)
        # "a-app" evicted, order is recency (b,c,d)
        self.assertEqual(list(reg.recent), ["b-app", "c-app", "d-app"])
        self.assertIsNone(reg.get("a-app"))
        self.assertEqual(reg.focused.app_id, "d-app")

    def test_refocus_bumps_count_and_position(self):
        reg = AppRegistry(max_recent=5, debounce_ms=0)
        reg.on_focus(window("a-app", address="0x1"), NOW)
        reg.on_focus(window("b-app", address="0x2"), NOW + 1000)
        reg.on_focus(window("a-app", address="0x1"), NOW + 2000)
        self.assertEqual(reg.recent["a-app"].focus_count, 2)
        self.assertEqual(list(reg.recent)[-1], "a-app")  # moved to most-recent

    def test_debounce_suppresses_rapid_same_window(self):
        reg = AppRegistry(max_recent=5, debounce_ms=1000)
        first = reg.on_focus(window("a-app", address="0x1"), NOW)
        second = reg.on_focus(window("a-app", address="0x1"), NOW + 100)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(second["reason"], "debounced")
        self.assertEqual(reg.recent["a-app"].focus_count, 1)  # not double-counted

    def test_debounce_allows_distinct_window(self):
        reg = AppRegistry(max_recent=5, debounce_ms=1000)
        reg.on_focus(window("a-app", address="0x1"), NOW)
        r = reg.on_focus(window("b-app", address="0x2"), NOW + 100)
        self.assertTrue(r["changed"])  # different address is never debounced

    def test_context_is_compact_and_bounded(self):
        reg = AppRegistry(max_recent=5, debounce_ms=0)
        for i in range(5):
            reg.on_focus(window(f"app{i}", title="T" * 300, address=f"0x{i}"), NOW + i)
        ctx = reg.context(role="text")
        self.assertEqual(ctx["schema"], "hyprneuro.app-context/1")
        self.assertTrue(ctx["untrusted"])
        self.assertEqual(len(ctx["recent"]), 5)
        self.assertEqual(ctx["focused"]["app_id"], "app4")
        self.assertLessEqual(len(json.dumps(ctx)), 3000)
        # Titles are truncated, secrets not leaked in full
        self.assertLessEqual(len(ctx["focused"]["title"]), 80)

    def test_rejects_bad_shape(self):
        reg = AppRegistry()
        with self.assertRaises(ValueError):
            reg.on_focus({"class": "google-chrome"})  # no address
        with self.assertRaises(ValueError):
            reg.on_focus({"address": "0x1"})  # no class
        with self.assertRaises(ValueError):
            reg.context(role="decision")

    def test_invalid_params(self):
        with self.assertRaises(ValueError):
            AppRegistry(max_recent=0)
        with self.assertRaises(ValueError):
            AppRegistry(debounce_ms=-1)


class SkillIndexTests(unittest.TestCase):
    def _skill(self, app_id="google-chrome", body="Use chrome tools", version="1.2"):
        return {"app_id": app_id, "name": "Chrome", "description": "Browser control",
                "version": version, "tags": ["browser"], "body": body,
                "tools_schema": {"type": "object"}}

    def test_discover_compact_and_load_full(self):
        idx = SkillIndex()
        idx.register(self._skill())
        manifests = idx.discover(["google-chrome", "unknown-app"])
        self.assertEqual(len(manifests), 1)
        self.assertEqual(manifests[0]["app_id"], "google-chrome")
        self.assertEqual(manifests[0]["version"], "1.2")
        self.assertNotIn("body", manifests[0])  # body is not in the compact manifest
        full = idx.load("google-chrome")
        self.assertEqual(full["body"], "Use chrome tools")
        self.assertIn("tools_schema", full)
        self.assertEqual(idx.load("nope"), None)

    def test_discover_dedupes_and_orders(self):
        idx = SkillIndex()
        idx.register(self._skill("a-app"))
        idx.register(self._skill("b-app"))
        out = idx.discover(["b-app", "a-app", "b-app"])
        self.assertEqual([m["app_id"] for m in out], ["b-app", "a-app"])

    def test_from_directory(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "chrome.json").write_text(json.dumps(self._skill()))
            (root / "broken.json").write_text("{ not json")
            idx = SkillIndex.from_directory(root)
        self.assertEqual(idx.app_ids(), ["google-chrome"])

    def test_ignores_symlinks_and_oversize(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real = root / "real.json"
            real.write_text(json.dumps(self._skill()))
            link = root / "link.json"
            link.symlink_to(real)
            big = root / "big.json"
            big.write_text("x" * 300_000)
            idx = SkillIndex.from_directory(root)
        # Symlink is ignored (real.json also has the manifest, so it loads once).
        self.assertIn("google-chrome", idx.app_ids())

    def test_body_and_value_limits(self):
        idx = SkillIndex()
        idx.register(self._skill(body="B" * 20000))
        self.assertLessEqual(len(idx.load("google-chrome")["body"]), 8192)


class TieredMemoryTests(unittest.TestCase):
    def setUp(self):
        self.mem = TieredMemory()  # in-memory backend

    def test_remember_and_recall_scoped(self):
        self.mem.remember("app", "pref.theme", "dark", app_id="google-chrome")
        self.mem.remember("global", "unit", "metric")
        self.mem.remember("task", "step", 3, task_id="t1")
        self.assertEqual(self.mem.get("app", "pref.theme"), "dark")
        self.assertEqual(len(self.mem.recall("global")), 1)
        self.assertEqual(len(self.mem.recall("app", app_id="google-chrome")), 1)
        self.assertEqual(self.mem.recall("app", app_id="other-app"), [])
        self.assertEqual(len(self.mem.recall("task", task_id="t1")), 1)
        self.assertEqual(self.mem.recall("task", task_id="t2"), [])

    def test_scope_and_key_validation(self):
        with self.assertRaises(ValueError):
            self.mem.remember("bogus", "k", 1)
        with self.assertRaises(ValueError):
            self.mem.remember("global", "bad key!", 1)
        with self.assertRaises(ValueError):
            self.mem.recall("global", limit=0)

    def test_value_size_limit(self):
        with self.assertRaises(ValueError):
            self.mem.remember("global", "big", "x" * 20_000)

    def test_promote_requires_approval(self):
        self.mem.remember("app", "pref.theme", "dark", app_id="google-chrome")
        denied = self.mem.promote("pref.theme", "app", "global", approved=False)
        self.assertFalse(denied["promoted"])
        self.assertIsNone(self.mem.get("global", "pref.theme"))
        with self.assertRaises(ValueError):
            self.mem.promote("pref.theme", "app", "global", approved=None)
        with self.assertRaises(ValueError):
            self.mem.promote("pref.theme", "app", "app", approved=True)
        with self.assertRaises(LookupError):
            self.mem.promote("missing", "app", "global", approved=True)
        ok = self.mem.promote("pref.theme", "app", "global", approved=True)
        self.assertTrue(ok["stored"])
        self.assertEqual(self.mem.get("global", "pref.theme"), "dark")

    def test_remember_overwrites_and_orders(self):
        self.mem.remember("global", "a", 1)
        time.sleep(0.01)
        self.mem.remember("global", "b", 2)
        self.mem.remember("global", "a", 99)
        self.assertEqual(self.mem.get("global", "a"), 99)
        self.assertEqual([r["key"] for r in self.mem.recall("global")], ["a", "b"])


class AppWatcherTests(unittest.IsolatedAsyncioTestCase):
    class FakeDesktop:
        def __init__(self, window):
            self._window = window
            self.queries = 0

        async def query(self, name):
            self.queries += 1
            if name != "activewindow":
                raise ValueError("unknown")
            return self._window

    async def test_initial_resolve_seeds_registry(self):
        desktop = self.FakeDesktop(window("thunar", address="0x9"))
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(desktop, reg, min_resolve_interval_ms=0)
        self.assertIsNone(reg.focused)  # empty before seeding
        await watcher.initial_resolve()
        self.assertEqual(reg.focused.app_id, "thunar")
        self.assertEqual(watcher.resolves, 1)

    async def test_initial_resolve_swallows_errors(self):
        class ErrDesktop:
            async def query(self, name):
                raise OSError("no compositor")
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(ErrDesktop(), reg, min_resolve_interval_ms=0)
        await watcher.initial_resolve()  # must not raise
        self.assertEqual(watcher.errors, 1)
        self.assertIsNone(reg.focused)

    async def test_resolves_focus_on_event(self):
        desktop = self.FakeDesktop(window("google-chrome", address="0x1"))
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(desktop, reg, min_resolve_interval_ms=0)
        await watcher.on_event("activewindowv2", "0x1")
        self.assertEqual(reg.focused.app_id, "google-chrome")
        self.assertEqual(watcher.resolves, 1)

    async def test_ignores_non_focus_events(self):
        desktop = self.FakeDesktop(window("google-chrome", address="0x1"))
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(desktop, reg, min_resolve_interval_ms=0)
        await watcher.on_event("workspacev2", "2")
        self.assertIsNone(reg.focused)
        self.assertEqual(desktop.queries, 0)

    async def test_coalesces_rapid_events(self):
        desktop = self.FakeDesktop(window("google-chrome", address="0x1"))
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(desktop, reg, min_resolve_interval_ms=5000)
        for _ in range(5):
            await watcher.on_event("activewindowv2", "0x1")
        self.assertEqual(desktop.queries, 1)  # only one resolve

    async def test_swallows_query_errors(self):
        class ErrDesktop:
            async def query(self, name):
                raise OSError("no compositor")
        reg = AppRegistry(debounce_ms=0)
        watcher = AppWatcher(ErrDesktop(), reg, min_resolve_interval_ms=0)
        await watcher.on_event("activewindowv2", "0x1")  # must not raise
        self.assertEqual(watcher.errors, 1)
        self.assertIsNone(reg.focused)


if __name__ == "__main__":
    unittest.main()
