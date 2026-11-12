"""Model-free cache, shared-intake, and real sidecar prompt/IPC integration."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hyprneuro.app_events import AppSkillContext, SharedApplicationEvents
from hyprneuro.application import AppRegistry, AppWatcher, SkillIndex
from hyprneuro.sidecar import SidecarServer, serve
from hyprneuro.sidecar_client import request
from hyprneuro.sidecar_store import SidecarStore


def skill(app_id="kitty", body="REFERENCE_BODY", version="1", **kwargs):
    return dict(app_id=app_id, name=app_id, body=body, version=version,
                tools_schema={"type": "object"}, **kwargs)


def window(app="kitty", title="PRIVATE_TITLE", address="0x1"):
    return {"class": app, "title": title, "address": address, "workspace": {"id": 1}}


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.skills = SkillIndex()
        self.skills.register(skill())
        self.skills.register(skill("thunar", "FILE_BODY"))
        self.context = AppSkillContext(self.skills, max_cached=2)

    def test_counts_reuse_normalization_and_read_only_snapshots(self):
        with patch.object(self.skills, "load", wraps=self.skills.load) as load:
            self.context.activate(" Kitty ")
            for _ in range(50):
                self.context.activate("kitty")
                self.context.snapshot()
                self.context.prompt_block()
            self.context.activate("thunar")
            self.context.activate("kitty")
            self.assertEqual(load.call_count, 2)
        self.assertEqual((self.context.loads, self.context.hits), (2, 1))
        snap = self.context.snapshot()
        snap["skill"]["tools_schema"]["type"] = "MUTATED"
        loaded = self.skills.load("kitty")
        loaded["tools_schema"]["type"] = "MUTATED"
        self.assertEqual(self.context.snapshot()["skill"]["tools_schema"]["type"], "object")
        self.assertEqual(self.skills.load("kitty")["tools_schema"]["type"], "object")
        self.assertFalse(self.context.snapshot()["execution_permission"])

    def test_content_version_and_lifecycle_immediately_replace(self):
        self.context.activate("kitty")
        first = self.context.snapshot()["revision"]
        self.skills.register(skill())  # identical registration is not a change
        self.assertEqual(self.context.loads, 1)
        self.skills.register(skill(body="CHANGED"))
        second = self.context.snapshot()["revision"]
        self.assertNotEqual(first, second)
        self.assertIn("CHANGED", self.context.prompt_block())
        self.assertNotIn("REFERENCE_BODY", self.context.prompt_block())
        self.skills.register(skill(body="CHANGED", version="2"))
        self.assertNotEqual(second, self.context.snapshot()["revision"])
        self.assertEqual(len(self.context.cache), 1)
        self.skills.retire("kitty")
        self.assertIsNone(self.context.snapshot())
        self.assertEqual(self.context.prompt_block(), "")
        self.assertEqual(len(self.context.cache), 0)
        self.skills.propose("kitty", instructions="DRAFT")
        self.assertIsNone(self.context.snapshot())
        with self.assertRaises(PermissionError):
            self.skills.approve("kitty", validated="yes")
        self.skills.approve("kitty", validated=True)
        self.assertIn("DRAFT", self.context.prompt_block())
        self.assertEqual(self.context.loads, 4)

    def test_inactive_invalidation_and_lru_bounds(self):
        self.context.activate("kitty")
        self.context.activate("thunar")
        self.skills.register(skill(body="NEW_INACTIVE"))
        self.assertEqual(self.context.snapshot()["app_id"], "thunar")
        self.context.activate("kitty")
        self.assertIn("NEW_INACTIVE", self.context.prompt_block())
        for i in range(20):
            self.skills.register(skill(f"app{i}"))
            self.context.activate(f"app{i}")
            self.assertLessEqual(len(self.context.cache), 2)
        loads = self.context.loads
        self.context.activate("kitty")
        self.assertEqual(self.context.loads, loads + 1)

    def test_missing_malformed_and_oversize_fail_closed(self):
        self.context.activate("missing")
        self.assertIsNone(self.context.snapshot())
        self.context.activate("kitty")
        for bad in ({"status": "approved"}, {"body": {}}, {"tools_schema": "bad"},
                    {"tools_schema": {"big": "x" * 4096}}, {"tags": "bad"}):
            data = skill()
            data.update(bad)
            with self.assertRaises(ValueError):
                self.skills.register(data)
            self.assertIsNone(self.context.snapshot())
            self.assertEqual(self.context.prompt_block(), "")
            self.skills.register(skill())
        self.skills.register(skill(body="\u2603" * 8192))
        self.assertEqual(self.context.prompt_block(), "")  # bounded JSON, not truncation

    def test_directory_refresh_modification_missing_malformed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kitty.json"
            path.write_text(json.dumps(skill()))
            index = SkillIndex.from_directory(directory)
            context = AppSkillContext(index)
            context.activate("kitty")
            path.write_text(json.dumps(skill(body="DISK_CHANGED")))
            self.assertIn("REFERENCE_BODY", context.prompt_block())
            index.refresh_directory()
            self.assertIn("DISK_CHANGED", context.prompt_block())
            self.assertEqual(context.loads, 2)
            index.refresh_directory()
            self.assertEqual(context.loads, 2)
            path.write_text('{ malformed')
            index.refresh_directory()
            self.assertIsNone(context.snapshot())
            path.write_text(json.dumps(skill()))
            index.refresh_directory()
            self.assertIsNotNone(context.snapshot())
            path.unlink()
            index.refresh_directory()
            self.assertIsNone(context.snapshot())

    def test_bad_bounds(self):
        for n in (0, 65, True):
            with self.assertRaises(ValueError):
                AppSkillContext(self.skills, max_cached=n)


class WatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_initial_same_app_titles_and_identity_change_same_address(self):
        class Desktop:
            value = window()
            async def query(self, name):
                if isinstance(self.value, Exception):
                    raise self.value
                return self.value
        desktop = Desktop()
        index = SkillIndex()
        index.register(skill())
        index.register(skill("thunar", "FILE_BODY"))
        context = AppSkillContext(index)
        registry = AppRegistry(debounce_ms=5000)
        watcher = AppWatcher(desktop, registry, context=context, min_resolve_interval_ms=0)
        await watcher.initial_resolve()
        for i in range(10):
            desktop.value = window("KITTY", title=f"title{i}", address=f"0x{i}")
            await watcher.on_event("activewindowv2", f"0x{i}")
            await watcher.on_event("windowtitlev2", "title")
            await watcher.on_event("keypress", "secret")
        self.assertEqual(context.loads, 1)
        self.assertNotIn("title", context.prompt_block())
        desktop.value = window("thunar", address="0x9")  # same address as last event
        await watcher.on_event("activewindowv2", "0x9")
        self.assertEqual(context.loads, 2)
        self.assertEqual(context.snapshot()["app_id"], "thunar")
        desktop.value = {}
        await watcher.on_event("activewindowv2", "")
        self.assertIsNone(context.snapshot())
        desktop.value = {"address": "0x9", "class": "bad/id"}
        await watcher.on_event("activewindowv2", "0x9")
        self.assertIsNone(context.snapshot())
        desktop.value = window()
        await watcher.on_event("activewindowv2", "0x1")
        self.assertIsNotNone(context.snapshot())
        desktop.value = OSError("compositor unavailable")
        await watcher.on_event("activewindowv2", "0x1")
        self.assertIsNone(context.snapshot())
        self.assertIsNone(registry.focused)


class IntakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_overflow_slow_and_failed_subscribers_are_independent(self):
        shared = SharedApplicationEvents()
        received = []
        blocked = asyncio.Event()
        async def slow(*item):
            await blocked.wait()
        async def broken(*item):
            raise RuntimeError("subscriber failure")
        async def healthy(*item):
            received.append(item)
        slow_sub = shared.subscribe(slow, max_queue=1)
        bad_sub = shared.subscribe(broken, max_queue=1)
        good_sub = shared.subscribe(healthy, max_queue=1)
        tasks = [asyncio.create_task(s.run()) for s in shared.subscribers]
        try:
            await shared.on_event("windowtitlev2", "SECRET")
            await shared.on_event("keypress", "SECRET")
            self.assertTrue(all(s.queue.empty() for s in shared.subscribers))
            for i in range(10):
                await shared.on_event("activewindowv2", str(i))
            self.assertTrue(all(s.queue.qsize() <= 1 for s in shared.subscribers))
            await asyncio.wait_for(good_sub.queue.join(), 1)
            await asyncio.wait_for(bad_sub.queue.join(), 1)
            self.assertEqual(received, [("activewindowv2", "9")])
            self.assertEqual(good_sub.dropped, 9)
            self.assertEqual(bad_sub.errors, 1)
            self.assertFalse(tasks[0].done())
            await shared.on_event("workspacev2", "2")
            await asyncio.wait_for(good_sub.queue.join(), 1)
            self.assertEqual(len(received), 2)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        self.assertEqual(slow_sub.queue.qsize(), 1)

    async def test_latest_focus_survives_other_events_and_coalesces(self):
        shared = SharedApplicationEvents()
        received = []
        async def callback(*item):
            received.append(item)
        sub = shared.subscribe(callback, max_queue=1, coalesce_seconds=0.01,
                               kinds={"activewindowv2"})
        task = asyncio.create_task(sub.run())
        try:
            await shared.on_event("activewindowv2", "old")
            await asyncio.sleep(0)
            await shared.on_event("activewindowv2", "latest")
            await shared.on_event("workspacev2", "2")
            await asyncio.wait_for(sub.queue.join(), 1)
            self.assertEqual(received, [("activewindowv2", "latest")])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


class PromptIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_sidecar_prompt_snapshot_once_no_loads_or_permission(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SidecarStore(Path(directory) / "db")
            self.addCleanup(store.close)
            server = SidecarServer(store, assistant_enabled=True)
            server.skills.register(skill(body="BODY_ONCE"))
            server.app_skill_context.activate("kitty")
            prompts = []
            async def stream(messages, **kwargs):
                prompts.append(messages)
                yield {"type": "delta", "channel": "answer", "text": "ok"}
            async def frame(*args):
                pass
            client_context = server._assistant({"action": "app_context"})
            with patch("hyprneuro.agent.stream_chat", stream), patch.object(server, "_write_frame", frame), \
                    patch.object(server.skills, "load", side_effect=AssertionError("prompt reload")), \
                    patch.object(Path, "read_text", side_effect=AssertionError("prompt disk read")):
                for _ in range(3):
                    await server._stream_agent_chat(None, {"message": "Hello", "context": client_context,
                                                          "history": [{"role": "assistant", "content": "old"}]})
            for messages in prompts:
                system = messages[0]["content"]
                self.assertEqual(system.count("BODY_ONCE"), 1)
                self.assertIn("untrusted reference data", system)
                self.assertIn('"execution_permission": false', system)
                self.assertEqual(len(messages), 3)
                self.assertEqual(messages[1]["content"], "old")
            self.assertEqual(server.broker.list(), [])
            self.assertIsNone(server.watcher)
            self.assertFalse(server.capture_enabled)
            server._assistant({"action": "skill_retire", "app_id": "kitty"})
            self.assertIsNone(server._assistant({"action": "app_context"})["active_skill"])


class ServiceIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_intake_seed_switch_refresh_and_capture_disabled(self):
        class Desktop:
            value = window()
            readers = 0
            callback = None
            async def query(self, name):
                return self.value
            async def events(self, callback):
                self.readers += 1
                self.callback = callback
                await asyncio.Event().wait()
        desktop = Desktop()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            skills_dir = root / "skills"
            skills_dir.mkdir()
            path = skills_dir / "kitty.json"
            path.write_text(json.dumps(skill()))
            socket = root / "r" / "sidecar.sock"
            stop = asyncio.Event()
            models = AsyncMock()
            grabber = AsyncMock()
            task = asyncio.create_task(serve(allow_ingest=True, watch_hyprland=True,
                                            models=models, grabber=grabber,
                                            assistant_enabled=True, skills_dir=skills_dir,
                                            socket_path=socket, db_path=root / "s" / "db",
                                            desktop=desktop, shutdown=stop))
            try:
                for _ in range(100):
                    if desktop.callback:
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(desktop.readers, 1)
                context = await request({"action": "app_context"}, socket_path=socket)
                self.assertEqual(context["active_skill"]["app_id"], "kitty")
                path.write_text(json.dumps(skill(body="REFRESHED")))
                await request({"action": "skill_refresh"}, socket_path=socket)
                context = await request({"action": "app_context"}, socket_path=socket)
                self.assertEqual(context["active_skill"]["skill"]["body"], "REFRESHED")
                with self.assertRaisesRegex(RuntimeError, "Invalid skill_refresh"):
                    await request({"action": "skill_refresh", "path": "/tmp"}, socket_path=socket)
                desktop.value = window("missing")
                await desktop.callback("activewindowv2", "0x1")
                for _ in range(100):
                    context = await request({"action": "app_context"}, socket_path=socket)
                    if context["focused"]["app_id"] == "missing":
                        break
                    await asyncio.sleep(0.01)
                self.assertEqual(context["focused"]["app_id"], "missing")
                self.assertIsNone(context["active_skill"])
                self.assertEqual(desktop.readers, 1)
                health = await request({"action": "health"}, socket_path=socket)
                self.assertFalse(health["capture_enabled"])
                self.assertFalse(health["on_demand_enabled"])
                self.assertNotIn("capture", health["collectors"])
                with self.assertRaisesRegex(RuntimeError, "observations are disabled"):
                    await request({"action": "omni_observe", "purpose": "both"}, socket_path=socket)
                self.assertEqual(models.mock_calls, [])
                self.assertEqual(grabber.mock_calls, [])
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)
            self.assertFalse(socket.exists())
            self.assertFalse(any(t.get_name().startswith("hyprland") for t in asyncio.all_tasks()))

    async def test_assistant_without_watch_does_not_start_intake(self):
        class Desktop:
            async def events(self, callback):
                raise AssertionError("unexpected event intake")
            async def query(self, name):
                raise AssertionError("unexpected query")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket = root / "r" / "sidecar.sock"
            stop = asyncio.Event()
            task = asyncio.create_task(serve(assistant_enabled=True, desktop=Desktop(),
                                            socket_path=socket, db_path=root / "s" / "db", shutdown=stop))
            try:
                for _ in range(100):
                    if socket.exists():
                        break
                    await asyncio.sleep(0.01)
                context = await request({"action": "app_context"}, socket_path=socket)
                self.assertIsNone(context["active_skill"])
                self.assertIsNone(context["focused"])
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)
