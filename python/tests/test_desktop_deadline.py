"""One total desktop lifetime, including read-only executor and socket waits."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from hyprneuro.authorization import PermissionBroker
from hyprneuro.desktop import Hyprland
from hyprneuro.desktop_control import DesktopController, LeaseManager
from test_authority_boundaries import TypedDesktop, WIN


class WaitingDesktop(TypedDesktop):
    async def drain(self):
        if self.hook:
            await self.hook("drain")

    async def read(self, size):
        if self.hook:
            await self.hook("response")
        return await super().read(size)

    async def wait_closed(self):
        if self.hook:
            await self.hook("close")


def controller(desktop):
    cap = object()
    broker = PermissionBroker(grant_capability=cap)
    broker.authorize("fixture", app_id="kitty", ops=("desktop_control",),
                     approved=True, grant_capability=cap)
    leases = LeaseManager()
    lease = leases.acquire("fixture")
    return DesktopController(desktop, broker, leases), leases, lease


class OperationDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_includes_every_await_and_cleanup(self):
        for barrier in ("focus", "version", "connect", "final_focus", "drain", "response", "close"):
            with self.subTest(barrier=barrier):
                desktop = WaitingDesktop()
                entered = asyncio.Event()
                async def hook(at):
                    if at == barrier:
                        entered.set()
                        await asyncio.Event().wait()
                desktop.hook = hook
                control, _, lease = controller(desktop)
                with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.04), \
                     patch("hyprneuro.desktop.asyncio.open_unix_connection", desktop.connect):
                    task = asyncio.create_task(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN))
                    try:
                        await asyncio.wait_for(entered.wait(), 0.2)
                        done, _ = await asyncio.wait({task}, timeout=0.2)
                        self.assertIn(task, done, "operation admission did not start the total deadline")
                        result = await task
                        self.assertEqual(result, {"ok": False, "stage": "timeout", "reason": "desktop_deadline_exceeded"})
                        self.assertEqual(len(desktop.writes), int(barrier in ("drain", "response", "close")))
                        self.assertEqual(control.actions, 0)
                    finally:
                        if not task.done():
                            task.cancel()
                        await asyncio.gather(task, return_exceptions=True)

    async def test_one_budget_is_not_reset_between_focus_and_version(self):
        desktop = WaitingDesktop()
        deadlines = []
        original = desktop.query
        async def query(name, *, deadline=None):
            deadlines.append(deadline)
            await asyncio.sleep(0.03)
            return await original(name, deadline=deadline)
        desktop.query = query
        control, _, lease = controller(desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.05), \
             patch("hyprneuro.desktop.asyncio.open_unix_connection", desktop.connect):
            result = await control.perform("fixture", lease.token, "toggle_float", expected_window=WIN)
        self.assertEqual(result["stage"], "timeout")
        self.assertEqual(len(deadlines), 2)
        self.assertEqual(deadlines[0], deadlines[1])
        self.assertEqual(desktop.writes, [])

    async def test_deadline_is_checked_synchronously_at_final_dispatch(self):
        desktop = WaitingDesktop()
        async def hook(at):
            if at == "final_focus":
                # Simulate a synchronous reader finishing too late, before the
                # event loop has delivered its timeout cancellation callback.
                time.sleep(0.06)
        desktop.hook = hook
        control, _, lease = controller(desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.04), \
             patch("hyprneuro.desktop.asyncio.open_unix_connection", desktop.connect):
            result = await control.perform("fixture", lease.token, "toggle_float", expected_window=WIN)
        self.assertEqual(result["stage"], "timeout")
        self.assertEqual(desktop.writes, [])


class UnixReadDeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.stop = asyncio.Event()
        self.entered = asyncio.Event()
        self.finished = threading.Event()
        self.commands = []
        self.handlers = set()
        self.trickle = "j/activewindow"
        self.trickle_count = 0
        self.stall = False
        self.unhandled = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: self.unhandled.append(context))
        owner = self
        class FixtureHyprland(Hyprland):
            def directory(self):
                return owner.root

            def _request(self, command, *, deadline=None):
                try:
                    return super()._request(command, deadline=deadline)
                finally:
                    if command == owner.trickle:
                        owner.finished.set()
        self.desktop = FixtureHyprland()
        self.server = await asyncio.start_unix_server(self.handle, path=str(self.root / ".socket.sock"))

    async def asyncTearDown(self):
        self.stop.set()
        self.server.close()
        await self.server.wait_closed()
        if self.handlers:
            await asyncio.wait_for(asyncio.gather(*list(self.handlers)), 1)
        await asyncio.sleep(0)
        self.assertEqual(self.unhandled, [])
        self.tmp.cleanup()

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            command = (await reader.read(4096)).decode()
            self.commands.append(command)
            if command == self.trickle or (self.trickle == "dispatch" and command.startswith("dispatch ")):
                self.entered.set()
                if self.stall:
                    await self.stop.wait()
                    return
                while not self.stop.is_set():
                    writer.write(b" ")
                    await writer.drain()
                    self.trickle_count += 1
                    try:
                        await asyncio.wait_for(self.stop.wait(), 0.01)
                    except TimeoutError:
                        pass
            else:
                writer.write(json.dumps({"tag": "v0.57.3"} if command == "j/version" else WIN).encode())
                await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
            self.handlers.discard(task)

    async def wait_for_worker_exit(self):
        for _ in range(100):
            if self.finished.is_set():
                return
            await asyncio.sleep(0.002)
        self.fail("read-only worker outlived its total deadline")

    async def test_initial_focus_slow_trickle_is_total_bounded_no_mutation(self):
        control, _, lease = controller(self.desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.06):
            result = await asyncio.wait_for(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN), 0.4)
        self.assertEqual(result["stage"], "timeout")
        await self.wait_for_worker_exit()
        self.assertGreater(self.trickle_count, 1)
        self.assertEqual(self.commands, ["j/activewindow"])
        self.assertEqual(control.actions, 0)

    async def test_version_slow_trickle_is_total_bounded_no_mutation(self):
        self.trickle = "j/version"
        control, _, lease = controller(self.desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.06):
            result = await asyncio.wait_for(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN), 0.4)
        self.assertEqual(result["stage"], "timeout")
        await self.wait_for_worker_exit()
        self.assertEqual(self.commands, ["j/activewindow", "j/version"])
        self.assertEqual(control.actions, 0)

    async def test_cancel_during_initial_focus_and_version_keeps_worker_bounded(self):
        for phase in ("j/activewindow", "j/version"):
            with self.subTest(phase=phase):
                self.trickle = phase
                self.commands.clear()
                self.finished.clear()
                self.entered.clear()
                control, leases, lease = controller(self.desktop)
                with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.06):
                    task = asyncio.create_task(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN))
                    await asyncio.wait_for(self.entered.wait(), 0.3)
                    task.cancel()
                    leases.force_release()
                    with self.assertRaises(asyncio.CancelledError):
                        await task
                    await self.wait_for_worker_exit()
                self.assertFalse(any(command.startswith("dispatch ") for command in self.commands))
                self.assertEqual(control.actions, 0)

    async def test_mutation_response_trickle_times_out_without_replay(self):
        self.trickle = "dispatch"
        control, _, lease = controller(self.desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.06):
            result = await asyncio.wait_for(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN), 0.4)
        self.assertEqual(result["stage"], "timeout")
        self.assertEqual(len([c for c in self.commands if c.startswith("dispatch ")]), 1)
        self.assertEqual(control.actions, 0)  # unknown result, not success

    async def test_standalone_query_default_is_total_bounded(self):
        with patch("hyprneuro.desktop.IPC_TIMEOUT_SECONDS", 0.06):
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(self.desktop.query("activewindow"), 0.4)
        await self.wait_for_worker_exit()
        self.assertEqual(self.commands, ["j/activewindow"])

    async def test_executor_queue_wait_uses_query_admission_deadline(self):
        loop = asyncio.get_running_loop()
        pool = ThreadPoolExecutor(max_workers=1)
        loop.set_default_executor(pool)
        started, release = threading.Event(), threading.Event()
        def occupy_worker():
            started.set()
            release.wait(1)
        blocker = loop.run_in_executor(None, occupy_worker)
        try:
            for _ in range(100):
                if started.is_set():
                    break
                await asyncio.sleep(0.002)
            self.assertTrue(started.is_set())
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(self.desktop.query("activewindow", deadline=time.monotonic() + 0.04), 0.3)
            self.assertEqual(self.commands, [])
        finally:
            release.set()
            await blocker
            await loop.run_in_executor(None, lambda: None)  # drain queued work
        self.assertEqual(self.commands, [])

    async def test_expired_worker_start_never_opens_socket(self):
        with patch("hyprneuro.desktop.socket.socket") as socket:
            with self.assertRaises(TimeoutError):
                self.desktop._request("j/activewindow", deadline=time.monotonic() - 1)
            socket.assert_not_called()

    async def test_stalled_read_exits_after_total_socket_timeout(self):
        self.stall = True
        control, _, lease = controller(self.desktop)
        with patch("hyprneuro.desktop_control.IPC_TIMEOUT_SECONDS", 0.04):
            result = await asyncio.wait_for(control.perform("fixture", lease.token, "toggle_float", expected_window=WIN), 0.3)
        self.assertEqual(result["stage"], "timeout")
        await self.wait_for_worker_exit()
        self.assertEqual(self.commands, ["j/activewindow"])
