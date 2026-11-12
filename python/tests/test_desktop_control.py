"""Unit tests for computer-use safety primitives (Phase 5).

These verify the gating order: authorization -> lease -> focus -> action.
A FakeDesktop records actions so no real compositor is touched.
"""
import asyncio
import time
import unittest

from hyprneuro.authorization import PermissionBroker
from hyprneuro.desktop_control import (
    DesktopController, FocusValidator, LeaseManager,
)


class FakeDesktop:
    def __init__(self, window=None, action_error=None):
        self._window = window
        self._action_error = action_error
        self.actions = []
        self.queries = 0

    async def query(self, name):
        self.queries += 1
        if name != "activewindow":
            raise ValueError("unknown")
        return self._window

    async def action(self, op, value=None):
        if self._action_error:
            raise self._action_error
        self.actions.append((op, value))
        return {"ok": True, "operation": op, "value": value}


WIN = {"address": "0xabc", "class": "kitty", "title": "Test", "visible": True,
       "workspace": {"id": 1}}


class LeaseManagerTests(unittest.TestCase):
    def test_acquire_and_is_held(self):
        lm = LeaseManager()
        lease = lm.acquire("t1")
        self.assertTrue(lease.token)
        self.assertTrue(lm.is_held("t1", lease.token))
        self.assertFalse(lm.is_held("t2", lease.token))
        self.assertFalse(lm.is_held("t1", "wrong-token"))

    def test_exclusive(self):
        lm = LeaseManager()
        lm.acquire("t1")
        with self.assertRaises(RuntimeError):
            lm.acquire("t2")  # second lease while one is active

    def test_release_allows_next(self):
        lm = LeaseManager()
        l1 = lm.acquire("t1")
        self.assertTrue(lm.release("t1", l1.token))
        l2 = lm.acquire("t2")  # now possible
        self.assertTrue(lm.is_held("t2", l2.token))

    def test_expiry(self):
        lm = LeaseManager()
        lease = lm.acquire("t1", ttl_ms=1)
        time.sleep(0.01)
        self.assertFalse(lm.is_held("t1", lease.token))
        self.assertIsNone(lm.active())
        # Expired lease is dropped; a new one can be acquired.
        lm2_lease = lm.acquire("t1")
        self.assertTrue(lm2_lease.token)

    def test_renew_extends(self):
        lm = LeaseManager()
        lease = lm.acquire("t1", ttl_ms=100)
        before = lease.expires_ms
        lm.renew("t1", lease.token, ttl_ms=5000)
        self.assertGreater(lease.expires_ms, before)

    def test_pause_resume(self):
        lm = LeaseManager()
        lease = lm.acquire("t1")
        self.assertTrue(lm.pause("t1", lease.token))
        self.assertTrue(lm.is_paused("t1", lease.token))
        self.assertTrue(lm.resume("t1", lease.token))
        self.assertFalse(lm.is_paused("t1", lease.token))

    def test_release_requires_token(self):
        lm = LeaseManager()
        lm.acquire("t1")
        self.assertFalse(lm.release("t1", "wrong"))

    def test_ttl_bounds(self):
        lm = LeaseManager()
        with self.assertRaises(ValueError):
            lm.acquire("t1", ttl_ms=0)
        with self.assertRaises(ValueError):
            lm.acquire("t1", ttl_ms=999_999)

    def test_force_release(self):
        lm = LeaseManager()
        lm.acquire("t1")
        self.assertTrue(lm.force_release())
        self.assertIsNone(lm.active())
        self.assertFalse(lm.force_release())  # nothing to release


class FocusValidatorTests(unittest.IsolatedAsyncioTestCase):
    async def test_valid_match(self):
        fv = FocusValidator()
        r = await fv.validate(FakeDesktop(WIN), {"address": "0xabc", "class": "kitty"})
        self.assertTrue(r["valid"])
        self.assertEqual(r["reason"], "ok")

    async def test_window_changed(self):
        other = dict(WIN, address="0xdef")
        r = await fv_validate(FakeDesktop(other), {"address": "0xabc"})
        self.assertFalse(r["valid"])
        self.assertEqual(r["reason"], "window_changed")

    async def test_class_mismatch(self):
        other = dict(WIN, **{"class": "google-chrome"})
        r = await fv_validate(FakeDesktop(other), {"address": "0xabc", "class": "kitty"})
        self.assertEqual(r["reason"], "class_mismatch")

    async def test_not_visible(self):
        hidden = dict(WIN, visible=False)
        r = await fv_validate(FakeDesktop(hidden), {"address": "0xabc"})
        self.assertEqual(r["reason"], "window_not_visible")

    async def test_no_expected(self):
        r = await fv_validate(FakeDesktop(WIN), {})
        self.assertEqual(r["reason"], "no_expected_window")

    async def test_compositor_unavailable(self):
        class Err:
            async def query(self, name):
                raise OSError("no compositor")
        r = await fv_validate(Err(), {"address": "0xabc"})
        self.assertEqual(r["reason"], "compositor_unavailable")


async def fv_validate(desktop, expected):
    return await FocusValidator().validate(desktop, expected)


class DesktopControllerTests(unittest.IsolatedAsyncioTestCase):
    def _controller(self, window=WIN, action_error=None):
        desktop = FakeDesktop(window, action_error)
        broker = PermissionBroker()
        broker.authorize("t1", ops=("read", "desktop_control"), approved=True)
        lm = LeaseManager()
        return DesktopController(desktop, broker, lm), desktop, lm

    async def test_full_success(self):
        controller, desktop, lm = self._controller()
        lease = lm.acquire("t1")
        r = await controller.perform("t1", lease.token, "focus_direction", "left",
                                     expected_window={"address": "0xabc", "class": "kitty"})
        self.assertTrue(r["ok"])
        self.assertEqual(r["stage"], "done")
        self.assertEqual(desktop.actions, [("focus_direction", "left")])

    async def test_denied_without_authorization(self):
        controller, desktop, lm = self._controller()
        # A task with no desktop_control authorization.
        lease = lm.acquire("t-noauth")
        r = await controller.perform("t-noauth", lease.token, "focus_direction", "left")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "authorization")
        self.assertEqual(desktop.actions, [])  # no action performed

    async def test_denied_without_lease(self):
        controller, desktop, lm = self._controller()
        r = await controller.perform("t1", "no-lease-token", "focus_direction", "left")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "lease")
        self.assertEqual(desktop.actions, [])

    async def test_denied_when_paused(self):
        controller, desktop, lm = self._controller()
        lease = lm.acquire("t1")
        lm.pause("t1", lease.token)
        r = await controller.perform("t1", lease.token, "focus_direction", "left")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason"], "lease_paused")
        self.assertEqual(desktop.actions, [])

    async def test_denied_when_focus_changes(self):
        other = dict(WIN, address="0xdef")
        controller, desktop, lm = self._controller(window=other)
        lease = lm.acquire("t1")
        r = await controller.perform("t1", lease.token, "focus_direction", "left",
                                     expected_window={"address": "0xabc"})
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "focus")
        self.assertEqual(r["reason"], "window_changed")
        self.assertEqual(desktop.actions, [])

    async def test_action_error_caught(self):
        controller, desktop, lm = self._controller(action_error=RuntimeError("hyprland rejected"))
        lease = lm.acquire("t1")
        r = await controller.perform("t1", lease.token, "focus_direction", "left")
        self.assertFalse(r["ok"])
        self.assertEqual(r["stage"], "action")
        self.assertIn("rejected", r["reason"])

    async def test_unapproved_desktop_control_blocked(self):
        # desktop_control in ops but NOT approved -> broker denies it.
        desktop = FakeDesktop(WIN)
        broker = PermissionBroker()
        with self.assertRaises(PermissionError):
            broker.authorize("t1", ops=("desktop_control",))  # no approval
        # So there's no valid scope; perform must be denied at authorization.
        lm = LeaseManager()
        controller = DesktopController(desktop, broker, lm)
        lease = lm.acquire("t1")
        r = await controller.perform("t1", lease.token, "focus_direction", "left")
        self.assertFalse(r["ok"])
        self.assertEqual(desktop.actions, [])


if __name__ == "__main__":
    unittest.main()
