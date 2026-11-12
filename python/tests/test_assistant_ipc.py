"""Integration tests: assistant IPC through the live sidecar + store migration.

Uses a FakeDesktop for the model-free focus watcher, so no real compositor,
models, screenshots or network are required.
"""
import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path

from hyprneuro.sidecar import serve
from hyprneuro.sidecar_client import request
from hyprneuro.sidecar_store import SidecarStore

NOW = int(time.time() * 1000)


class FakeDesktop:
    """Serves a fixed activewindow and emits one focus event, then idles."""

    def __init__(self, window):
        self._window = window
        self.queried = 0

    async def query(self, name):
        if name != "activewindow":
            raise ValueError("unknown query")
        self.queried += 1
        return self._window

    async def events(self, callback):
        await callback("activewindowv2", "0x1")
        await asyncio.Event().wait()


class StoreMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SidecarStore(Path(self.tmp.name) / "assistant.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_schema_version_bumped(self):
        row = self.store.db.execute("SELECT value FROM sidecar_meta WHERE key='schema_version'").fetchone()
        self.assertEqual(row[0], "2")

    def test_memory_roundtrip(self):
        self.store.app_memory_remember("app", "pref.theme", json.dumps("dark"), app_id="google-chrome")
        self.store.app_memory_remember("global", "unit", json.dumps("metric"))
        rows = self.store.app_memory_recall("app", app_id="google-chrome")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "dark")
        self.assertEqual(self.store.app_memory_recall("app", app_id="other"), [])
        with self.assertRaises(ValueError):
            self.store.app_memory_remember("bogus", "k", "{}")

    def test_task_lifecycle(self):
        created = self.store.task_create("Summarize the focused page", scope="task",
                                         state={"app_id": "google-chrome"})
        self.assertEqual(created["status"], "active")
        updated = self.store.task_update(created["id"], status="suspended",
                                         state={"app_id": "google-chrome", "step": 1})
        self.assertEqual(updated["status"], "suspended")
        got = self.store.task_get(created["id"])
        self.assertEqual(got["state"]["step"], 1)
        self.assertEqual(len(self.store.task_list(status="suspended")), 1)
        with self.assertRaises(LookupError):
            self.store.task_get(9999)

    def test_skill_upsert_and_get(self):
        manifest = {"app_id": "google-chrome", "name": "Chrome", "description": "Browser",
                    "version": "1", "tags": ["browser"], "body": "instructions", "schema": {}}
        self.store.skill_upsert("google-chrome", json.dumps(manifest))
        full = self.store.skill_get("google-chrome", full=True)
        self.assertEqual(full["body"], "instructions")
        compact = self.store.skill_get("google-chrome", full=False)
        self.assertNotIn("body", compact)
        self.assertEqual([s["app_id"] for s in self.store.skill_list()], ["google-chrome"])


class AssistantDisabledByDefaultTests(unittest.IsolatedAsyncioTestCase):
    async def test_assistant_actions_refused_when_off(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            socket = root / "r" / "sidecar.sock"
            stop = asyncio.Event()
            task = asyncio.create_task(serve(allow_ingest=False, socket_path=socket,
                                             db_path=root / "s" / "db.sqlite3", shutdown=stop))
            try:
                for _ in range(100):
                    if socket.exists():
                        break
                    await asyncio.sleep(0.01)
                health = await request({"action": "health"}, socket_path=socket)
                self.assertFalse(health["assistant_enabled"])
                with self.assertRaisesRegex(RuntimeError, "disabled"):
                    await request({"action": "app_context"}, socket_path=socket)
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)


class AssistantIpcTests(unittest.IsolatedAsyncioTestCase):
    def _skills(self, root):
        skills = root / "skills"
        skills.mkdir()
        (skills / "google-chrome.json").write_text(json.dumps({
            "app_id": "google-chrome", "name": "Chrome", "description": "Browser control",
            "version": "1", "tags": ["browser"], "body": "Use the browser tools.",
            "tools_schema": {"type": "object"}}))
        return str(skills)

    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.socket = root / "runtime" / "sidecar.sock"
        self.db = root / "state" / "assistant.sqlite3"
        self.stop = asyncio.Event()
        self.desktop = FakeDesktop({"address": "0x1", "class": "google-chrome",
                                    "title": "Test tab", "workspace": {"id": 1}, "pid": 42})
        self.service = asyncio.create_task(serve(
            allow_ingest=True, watch_hyprland=True, assistant_enabled=True,
            assistant_recent_apps=5, socket_path=self.socket, db_path=self.db,
            shutdown=self.stop, desktop=self.desktop, skills_dir=self._skills(root)))

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.service, 3)
        self.tmp.cleanup()

    async def _wait_app(self, app_id):
        for _ in range(200):
            ctx = await request({"action": "app_context"}, socket_path=self.socket)
            if ctx["focused"] and ctx["focused"]["app_id"] == app_id:
                return ctx
            await asyncio.sleep(0.02)
        self.fail("app context did not reflect the focused window")

    async def test_app_context_tracks_focus(self):
        ctx = await self._wait_app("google-chrome")
        self.assertEqual(ctx["schema"], "hyprneuro.app-context/1")
        self.assertTrue(ctx["untrusted"])
        self.assertEqual(ctx["focused"]["app_id"], "google-chrome")
        self.assertEqual(ctx["focused"]["workspace"], "1")
        self.assertEqual(len(ctx["recent"]), 1)
        self.assertGreaterEqual(self.desktop.queried, 1)

    async def test_memory_roundtrip_over_ipc(self):
        await request({"action": "memory_remember", "scope": "app", "key": "pref.theme",
                       "value": "dark", "app_id": "google-chrome"}, socket_path=self.socket)
        await request({"action": "memory_remember", "scope": "global", "key": "unit",
                       "value": "metric"}, socket_path=self.socket)
        rows = await request({"action": "memory_recall", "scope": "app",
                              "app_id": "google-chrome"}, socket_path=self.socket)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "dark")
        unit = await request({"action": "memory_recall", "scope": "global", "key": "unit"},
                             socket_path=self.socket)
        self.assertEqual(len(unit), 1)
        self.assertEqual(unit[0]["value"], "metric")
        # App-scoped records are not leaked into a global key lookup.
        self.assertEqual(await request({"action": "memory_recall", "scope": "global",
                                        "key": "pref.theme"}, socket_path=self.socket), [])

    async def test_skill_discover_and_load(self):
        await self._wait_app("google-chrome")
        discovered = await request({"action": "skill_discover"}, socket_path=self.socket)
        self.assertEqual(discovered["schema"], "hyprneuro.skills/1")
        self.assertEqual(len(discovered["manifests"]), 1)
        self.assertEqual(discovered["manifests"][0]["name"], "Chrome")
        self.assertNotIn("body", discovered["manifests"][0])
        loaded = await request({"action": "skill_load", "app_id": "google-chrome"},
                               socket_path=self.socket)
        self.assertEqual(loaded["body"], "Use the browser tools.")
        listed = await request({"action": "skill_list"}, socket_path=self.socket)
        self.assertEqual(listed["app_ids"], ["google-chrome"])
        with self.assertRaisesRegex(RuntimeError, "No skill"):
            await request({"action": "skill_load", "app_id": "unknown-app"}, socket_path=self.socket)

    async def test_task_lifecycle_over_ipc(self):
        created = await request({"action": "task_create", "goal": "Summarize focused page",
                                 "state": {"app_id": "google-chrome"}}, socket_path=self.socket)
        self.assertEqual(created["status"], "active")
        tid = created["id"]
        updated = await request({"action": "task_update", "id": tid, "status": "suspended",
                                 "state": {"app_id": "google-chrome", "step": 1}},
                                socket_path=self.socket)
        self.assertEqual(updated["status"], "suspended")
        got = await request({"action": "task_get", "id": tid}, socket_path=self.socket)
        self.assertEqual(got["state"]["step"], 1)
        listed = await request({"action": "task_list", "status": "suspended"}, socket_path=self.socket)
        self.assertEqual([t["id"] for t in listed], [tid])

    async def test_rejects_malformed_requests(self):
        with self.assertRaisesRegex(RuntimeError, "Invalid"):
            await request({"action": "memory_remember", "scope": "app", "key": "k", "value": 1,
                           "bogus": True}, socket_path=self.socket)
        with self.assertRaisesRegex(RuntimeError, "Invalid"):
            await request({"action": "task_create", "goal": ""}, socket_path=self.socket)


if __name__ == "__main__":
    unittest.main()
