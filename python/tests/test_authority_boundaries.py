"""P1 regressions: disposable real broker and typed adapter; no desktop IPC."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.authorization import PermissionBroker
from hyprneuro.desktop import Hyprland
from hyprneuro.desktop_control import DesktopController, LeaseManager
from hyprneuro.sidecar import SidecarServer
from hyprneuro.sidecar_store import SidecarStore

WIN = {"address": "0xabc", "class": "kitty", "visible": True}


class PublicGrantTests(unittest.TestCase):
    def test_model_approved_true_cannot_create_any_scope(self):
        with tempfile.TemporaryDirectory() as root:
            store = SidecarStore(Path(root) / "fixture.sqlite")
            try:
                server = SidecarServer(store, assistant_enabled=True)
                for ops in (["read"], ["write", "execute"], ["desktop_control"]):
                    with self.subTest(ops=ops), self.assertRaises(PermissionError):
                        server.dispatch({"action": "auth_create", "task_id": "model",
                                         "ops": ops, "approved": True})
                    self.assertEqual(store.auth_list(), [])
            finally:
                store.close()

    def test_model_approved_true_cannot_expand_existing_scope(self):
        with tempfile.TemporaryDirectory() as root:
            store = SidecarStore(Path(root) / "fixture.sqlite")
            try:
                # Synthetic pre-existing host scope; not a public grant.
                store.auth_upsert({"task_id": "owner", "app_id": "kitty",
                                   "file_prefix": "/fixture", "ops": ["read"],
                                   "approved": False, "status": "active"})
                server = SidecarServer(store, assistant_enabled=True)
                before = store.auth_get("owner")
                with self.assertRaises(PermissionError):
                    server.dispatch({"action": "auth_expand", "task_id": "owner",
                                     "ops": ["read", "write", "delete"], "approved": True})
                self.assertEqual(store.auth_get("owner"), before)
            finally:
                store.close()


class TypedDesktop(Hyprland):
    """Keep production action/dispatch logic; replace read IPC and wire only."""
    def __init__(self):
        self.window = dict(WIN)
        self.hook = None
        self.focus_queries = 0
        self.writes = []
        self.closed = False
        self.response = b"ok"

    def directory(self):
        return Path("/fixture")

    async def query(self, name, *, deadline=None):
        barrier = name
        if name == "activewindow":
            self.focus_queries += 1
            barrier = "focus" if self.focus_queries == 1 else "final_focus"
        if self.hook:
            await self.hook(barrier)
        return {"tag": "v0.57.3"} if name == "version" else dict(self.window)

    def _request(self, command, *, deadline=None):
        # Baseline adapter dispatch path; never a real socket.
        self.writes.append(command.encode())
        return "ok"

    async def connect(self, *args, **kwargs):
        if self.hook:
            await self.hook("connect")
        return self, self

    def write(self, value):
        self.writes.append(value)

    async def drain(self):
        pass

    async def read(self, size):
        response, self.response = self.response, b""
        return response

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


class BaselineDesktopTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_target_cannot_dispatch(self):
        desktop = TypedDesktop()
        broker = PermissionBroker()
        # Seed fixture to isolate desktop checks from grant API change.
        from hyprneuro.authorization import AuthorizationScope
        broker._scopes["owner"] = AuthorizationScope("owner", ops=frozenset({"desktop_control"}), approved=True)
        leases = LeaseManager()
        lease = leases.acquire("owner")
        controller = DesktopController(desktop, broker, leases)
        with patch("hyprneuro.desktop.asyncio.open_unix_connection", desktop.connect):
            result = await controller.perform("owner", lease.token, "toggle_float")
        self.assertFalse(result["ok"])
        self.assertEqual(desktop.writes, [])

    async def test_revoke_during_each_existing_await_cannot_dispatch(self):
        for barrier in ("focus", "version"):
            with self.subTest(barrier=barrier):
                desktop = TypedDesktop()
                broker = PermissionBroker()
                from hyprneuro.authorization import AuthorizationScope
                broker._scopes["owner"] = AuthorizationScope("owner", app_id="kitty", ops=frozenset({"desktop_control"}), approved=True)
                leases = LeaseManager()
                lease = leases.acquire("owner")
                async def hook(at):
                    if at == barrier:
                        broker.revoke("owner")
                desktop.hook = hook
                controller = DesktopController(desktop, broker, leases)
                with patch("hyprneuro.desktop.asyncio.open_unix_connection", desktop.connect):
                    result = await controller.perform("owner", lease.token, "toggle_float", expected_window=WIN)
                self.assertFalse(result["ok"])
                self.assertEqual(desktop.writes, [])


class TrustedGrantTests(unittest.TestCase):
    def test_json_or_boolean_cannot_be_the_host_capability(self):
        for value in (True, False, "token", 42, {}, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                PermissionBroker(grant_capability=value)

    def test_host_capability_preserves_exact_read_and_trusted_expansion(self):
        with tempfile.TemporaryDirectory() as root:
            store = SidecarStore(Path(root) / "fixture.sqlite")
            cap = object()  # owned by fixture host, never RPC data
            try:
                broker = PermissionBroker(store, grant_capability=cap)
                broker.authorize("owner", app_id="kitty", file_prefix="/fixture",
                                 ops=("read",), grant_capability=cap)
                self.assertTrue(broker.check("owner", "read", app_id="kitty", path="/fixture/exact.txt")["allowed"])
                for app in (None, "other"):
                    self.assertFalse(broker.check("owner", "read", app_id=app, path="/fixture/exact.txt")["allowed"])
                self.assertFalse(broker.check("owner", "read", app_id="kitty", path="/other/file")["allowed"])
                self.assertFalse(broker.check("owner", "write", app_id="kitty", path="/fixture/exact.txt")["allowed"])
                before = store.auth_get("owner")
                for wrong in (None, True, "owner", {}, object()):
                    with self.subTest(wrong=type(wrong).__name__):
                        with self.assertRaisesRegex(PermissionError, "Trusted grant capability required"):
                            broker.expand("owner", ops=("read", "delete"), approved=True, grant_capability=wrong)
                        with self.assertRaises(PermissionError):
                            broker.authorize("owner", ops=("write",), approved=True, grant_capability=wrong)
                        self.assertEqual(store.auth_get("owner"), before)
                broker.expand("owner", ops=("read", "delete"), approved=True, grant_capability=cap)
                self.assertTrue(broker.check("owner", "delete", app_id="kitty", path="/fixture/exact.txt")["allowed"])
                # A fresh inspection-only broker can revoke but cannot regrant.
                observer = PermissionBroker(store)
                observer.revoke("owner")
                with self.assertRaises(PermissionError):
                    observer.authorize("owner", ops=("read",), approved=True, grant_capability=cap)
                self.assertFalse(broker.check("owner", "read", app_id="kitty")["allowed"])
            finally:
                store.close()


class FinalDispatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SidecarStore(Path(self.tmp.name) / "fixture.sqlite")
        self.cap = object()
        self.broker = PermissionBroker(self.store, grant_capability=self.cap)
        self.broker.authorize("owner", app_id="kitty", ops=("desktop_control",),
                              approved=True, grant_capability=self.cap)
        self.desktop = TypedDesktop()
        self.leases = LeaseManager()
        self.lease = self.leases.acquire("owner")
        self.controller = DesktopController(self.desktop, self.broker, self.leases)
        self.transport = patch("hyprneuro.desktop.asyncio.open_unix_connection", self.desktop.connect)
        self.transport.start()

    async def asyncTearDown(self):
        self.transport.stop()
        self.store.close()
        self.tmp.cleanup()

    async def perform(self, expected=WIN, op="toggle_float", value=None):
        return await self.controller.perform("owner", self.lease.token, op, value, expected_window=expected)

    async def test_success_uses_typed_wire_and_final_focus(self):
        result = await self.perform()
        self.assertTrue(result["ok"])
        self.assertEqual(self.desktop.writes, [b'dispatch hl.dsp.window.float({ action = "toggle" })'])
        self.assertEqual(self.desktop.focus_queries, 2)
        self.assertTrue(self.desktop.closed)

    async def test_mandatory_target_app_and_matching_broker_scope(self):
        for expected in (None, {}, {"address": "0xabc"}, {"class": "kitty"}, dict(WIN, **{"class": "other"})):
            with self.subTest(expected=expected):
                self.assertFalse((await self.perform(expected))["ok"])
                self.assertEqual(self.desktop.writes, [])

    async def test_every_await_rechecks_authority(self):
        for barrier in ("focus", "version", "connect", "final_focus"):
            for change in ("revoke", "expire", "pause", "release", "emergency_stop"):
                with self.subTest(barrier=barrier, change=change):
                    self.broker.authorize("owner", app_id="kitty", ops=("desktop_control",),
                                          approved=True, grant_capability=self.cap)
                    self.leases.force_release()
                    self.lease = self.leases.acquire("owner")
                    self.desktop.focus_queries = 0
                    self.desktop.closed = False
                    entered, proceed = asyncio.Event(), asyncio.Event()
                    async def hook(at):
                        if at == barrier:
                            entered.set()
                            await proceed.wait()
                    self.desktop.hook = hook
                    task = asyncio.create_task(self.perform())
                    await asyncio.wait_for(entered.wait(), 1)
                    if change == "revoke":
                        self.broker.revoke("owner")
                    elif change == "expire":
                        self.lease.expires_ms = 0
                    elif change == "pause":
                        self.leases.pause("owner", self.lease.token)
                    elif change == "release":
                        self.leases.release("owner", self.lease.token)
                    else:
                        self.leases.force_release()
                    proceed.set()
                    self.assertFalse((await asyncio.wait_for(task, 1))["ok"])
                    self.assertEqual(self.desktop.writes, [])
                    self.assertEqual(self.controller.actions, 0)

    async def test_focus_change_at_each_await_denies(self):
        for barrier in ("focus", "version", "connect", "final_focus"):
            for field, value in (("address", "0xdef"), ("class", "other"), ("visible", False)):
                with self.subTest(barrier=barrier, field=field):
                    self.desktop.window = dict(WIN)
                    self.desktop.focus_queries = 0
                    async def hook(at):
                        if at == barrier:
                            self.desktop.window[field] = value
                    self.desktop.hook = hook
                    self.assertFalse((await self.perform())["ok"])
                    self.assertEqual(self.desktop.writes, [])

    async def test_cancel_and_release_while_pending_never_mutates(self):
        for barrier in ("focus", "version", "connect", "final_focus"):
            with self.subTest(barrier=barrier):
                self.leases.force_release()
                self.lease = self.leases.acquire("owner")
                self.desktop.focus_queries = 0
                entered = asyncio.Event()
                async def hook(at):
                    if at == barrier:
                        entered.set()
                        await asyncio.Event().wait()
                self.desktop.hook = hook
                task = asyncio.create_task(self.perform())
                await asyncio.wait_for(entered.wait(), 1)
                task.cancel()
                self.leases.force_release()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                self.assertEqual(self.desktop.writes, [])
                self.assertEqual(self.controller.actions, 0)

    async def test_cancellation_requested_at_final_return_is_fenced(self):
        async def hook(at):
            if at == "final_focus":
                asyncio.current_task().cancel()
        self.desktop.hook = hook
        task = asyncio.create_task(self.perform())
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.desktop.writes, [])

    async def test_invalid_model_lua_shell_or_dispatch_values_never_sent(self):
        for op, value in (("exec", "touch /fixture/bad"), ("toggle_float;exec bad", None),
                          ("workspace", "1;exec bad"), ("focus_direction", "left\";bad")):
            with self.subTest(op=op, value=value):
                self.assertFalse((await self.perform(op=op, value=value))["ok"])
                self.assertEqual(self.desktop.writes, [])

    async def test_adapter_cannot_mutate_without_final_gate(self):
        with self.assertRaises(PermissionError):
            await self.desktop.action("toggle_float")
        self.assertEqual(self.desktop.writes, [])


class UnixTypedAdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_adapter_over_disposable_unix_compositor_fixture(self):
        import json
        with tempfile.TemporaryDirectory() as root:
            commands = []
            version = "v0.57.3"
            response = b"ok"
            async def handle(reader, writer):
                try:
                    command = (await reader.read(4096)).decode()
                    if command == "j/version":
                        value = json.dumps({"tag": version}).encode()
                    elif command == "j/activewindow":
                        value = json.dumps(WIN).encode()
                    else:
                        commands.append(command)
                        value = response
                    writer.write(value)
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()
            class FixtureHyprland(Hyprland):
                def directory(self):
                    return Path(root)
            server = await asyncio.start_unix_server(handle, path=str(Path(root) / ".socket.sock"))
            async with server:
                cap = object()
                broker = PermissionBroker(grant_capability=cap)
                broker.authorize("owner", app_id="kitty", ops=("desktop_control",), approved=True, grant_capability=cap)
                leases = LeaseManager()
                lease = leases.acquire("owner")
                controller = DesktopController(FixtureHyprland(), broker, leases)
                result = await controller.perform("owner", lease.token, "move_workspace", 2, expected_window=WIN)
                self.assertTrue(result["ok"])
                self.assertEqual(commands, ['dispatch hl.dsp.window.move({ workspace = 2 })'])
                version = "v0.58.0"
                self.assertFalse((await controller.perform("owner", lease.token, "toggle_float", expected_window=WIN))["ok"])
                self.assertEqual(len(commands), 1)
                version, response = "v0.57.3", b"invalid action"
                result = await controller.perform("owner", lease.token, "toggle_split", expected_window=WIN)
                self.assertFalse(result["ok"])
                self.assertIn("rejected", result["reason"])
                self.assertEqual(len(commands), 2)
                self.assertEqual(controller.actions, 1)
