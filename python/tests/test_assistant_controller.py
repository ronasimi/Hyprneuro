"""Unit tests for the hotkey-activated assistant controller + CLI (Phase 6)."""
import asyncio
import unittest

from hyprneuro.assistant_controller import AssistantController
from hyprneuro.assistant_cli import build_parser


class FakeSidecar:
    """Minimal in-memory stand-in for the sidecar assistant IPC."""

    def __init__(self):
        self.tasks = {
            "1": {"id": "1", "goal": "summarize", "scope": "task", "state": "running"},
            "2": {"id": "2", "goal": "draft email", "scope": "app", "state": "done"},
        }
        self.auth = []
        self.lease_active = False
        self.calls = []

    async def __call__(self, payload, **_):
        self.calls.append(payload)
        action = payload["action"]
        if action == "app_context":
            return {"schema": "hyprneuro.app-context/1", "focused": {"app_id": "kitty"}}
        if action == "task_list":
            return {"schema": "hyprneuro.tasks/1", "tasks": list(self.tasks.values())}
        if action == "task_get":
            return dict(self.tasks[payload["id"]])
        if action == "task_update":
            self.tasks[payload["id"]]["state"] = payload["state"]
            return dict(self.tasks[payload["id"]])
        if action == "auth_expand":
            self.auth.append(payload)
            return {"allowed": True, "reason": "ok"}
        if action == "telemetry":
            return {"schema": "hyprneuro.telemetry/1", "counters": {}, "store": {}}
        if action == "lease_emergency_stop":
            self.lease_active = False
            return {"stopped": True}
        raise ValueError(f"unexpected action {action}")


class AssistantControllerTests(unittest.IsolatedAsyncioTestCase):
    def _c(self):
        fake = FakeSidecar()
        return AssistantController(fake, poll_interval_s=0.01), fake

    async def test_status_snapshot(self):
        c, fake = self._c()
        await c.select_task("1")
        s = await c.status()
        self.assertEqual(s["schema"], "hyprneuro.assistant/1")
        self.assertEqual(s["focused"]["app_id"], "kitty")
        self.assertEqual(s["active_task"]["id"], "1")
        self.assertEqual(len(s["tasks"]), 2)
        self.assertIn("telemetry", s)

    async def test_select_task(self):
        c, fake = self._c()
        task = await c.select_task("2")
        self.assertEqual(task["id"], "2")
        with self.assertRaises(ValueError):
            await c.select_task("")

    async def test_approval_flow(self):
        c, fake = self._c()
        a = await c.request_approval("1", "desktop_control", "need focus")
        self.assertEqual(a["status"], "pending")
        # Pending shows in status.
        self.assertEqual(len((await c.status())["pending_approvals"]), 1)
        approved = await c.approve(a["id"])
        self.assertEqual(approved["status"], "approved")
        self.assertTrue(any("desktop_control" in x.get("ops", []) and x.get("approved")
                            for x in fake.auth))
        # Double-resolve is refused.
        with self.assertRaises(RuntimeError):
            await c.approve(a["id"])

    async def test_deny(self):
        c, fake = self._c()
        a = await c.request_approval("1", "delete")
        self.assertEqual((await c.deny(a["id"]))["status"], "denied")

    async def test_stream_until_terminal(self):
        c, fake = self._c()
        updates = []
        # Task 2 is already done -> stream returns immediately.
        final = await c.stream("2", updates.append, max_polls=10)
        self.assertEqual(final["state"], "done")
        self.assertEqual(len(updates), 1)

    async def test_stream_polls_until_state_change(self):
        c, fake = self._c()
        updates = []
        # Task 1 is running; flip it to done after a moment, bounded.
        async def flip():
            await asyncio.sleep(0.02)
            fake.tasks["1"]["state"] = "done"
        asyncio.create_task(flip())
        final = await c.stream("1", updates.append, max_polls=100)
        self.assertEqual(final["state"], "done")
        self.assertGreaterEqual(len(updates), 2)  # running -> done

    async def test_pause_resume(self):
        c, fake = self._c()
        await c.pause("1")
        self.assertEqual(fake.tasks["1"]["state"], "paused")
        await c.resume("1")
        self.assertEqual(fake.tasks["1"]["state"], "running")

    async def test_emergency_stop(self):
        c, fake = self._c()
        await c.select_task("1")
        fake.lease_active = True
        r = await c.emergency_stop()
        self.assertTrue(r["stopped"])
        self.assertEqual(fake.tasks["1"]["state"], "paused")


class CliParserTests(unittest.TestCase):
    def test_status_and_stop(self):
        args = build_parser().parse_args(["status"])
        self.assertEqual(args.cmd, "status")
        args = build_parser().parse_args(["stop"])
        self.assertEqual(args.cmd, "stop")

    def test_stream_with_max_polls(self):
        args = build_parser().parse_args(["stream", "3", "--max-polls", "50"])
        self.assertEqual(args.cmd, "stream")
        self.assertEqual(args.id, "3")
        self.assertEqual(args.max_polls, 50)

    def test_request_approval(self):
        args = build_parser().parse_args(["request-approval", "t1", "desktop_control", "reason"])
        self.assertEqual(args.cmd, "request-approval")
        self.assertEqual(args.op, "desktop_control")
        self.assertEqual(args.reason, "reason")


if __name__ == "__main__":
    unittest.main()
