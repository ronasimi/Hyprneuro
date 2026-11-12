"""Computer-use safety primitives (Phase 5).

The safety model for desktop automation, in order:

  1. Task authorization  — the permission broker must allow `desktop_control`
     for the task (which requires an explicit recorded approval).
  2. Exclusive lease     — at most ONE desktop-control lease exists at a time;
     it is time-bounded and can be paused (on user intervention) and resumed.
  3. Focus validation    — the target window's identity must still match
     immediately before the action (focus can change at any time).
  4. Bounded action      — one small, validated operation.
  5. Release / renew     — the lease is released or renewed, never leaked.

The lease is deliberately **in-memory only**: a process crash or restart clears
it, which is fail-closed (no stale lease can grant control after a restart).

Unattended GUI testing must target disposable test applications. Nothing here
takes control of the user's desktop by itself — every action is gated by all
three checks above.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from typing import Any

DEFAULT_TTL_MS = 10_000
MAX_TTL_MS = 120_000


def _now_ms() -> int:
    return int(time.time() * 1000)


@dataclass
class DesktopLease:
    task_id: str
    token: str
    acquired_ms: int
    expires_ms: int
    paused: bool = False

    def expired(self, now_ms: int | None = None) -> bool:
        return (now_ms or _now_ms()) >= self.expires_ms

    def compact(self) -> dict:
        return {"task_id": self.task_id, "token": self.token,
                "acquired_ms": self.acquired_ms, "expires_ms": self.expires_ms,
                "paused": self.paused}


class LeaseManager:
    """Exclusive, time-bounded, pausable desktop-control lease."""

    def __init__(self):
        self._lease: DesktopLease | None = None

    def acquire(self, task_id: str, *, ttl_ms: int = DEFAULT_TTL_MS) -> DesktopLease:
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            raise ValueError("Invalid task_id")
        if not 1 <= ttl_ms <= MAX_TTL_MS:
            raise ValueError(f"ttl_ms must be 1..{MAX_TTL_MS}")
        if self._lease is not None and not self._lease.expired():
            raise RuntimeError("Desktop control already leased to another task")
        now = _now_ms()
        lease = DesktopLease(task_id=task_id, token=secrets.token_hex(16),
                             acquired_ms=now, expires_ms=now + ttl_ms)
        self._lease = lease
        return lease

    def _require(self, task_id: str, token: str) -> DesktopLease:
        lease = self._lease
        if lease is None or lease.task_id != task_id or lease.token != token:
            raise PermissionError("Invalid or missing desktop-control lease")
        if lease.expired():
            self._lease = None  # drop the expired lease
            raise PermissionError("Desktop-control lease expired")
        return lease

    def is_held(self, task_id: str, token: str) -> bool:
        lease = self._lease
        if lease is None or lease.task_id != task_id or lease.token != token:
            return False
        if lease.expired():
            self._lease = None
            return False
        return True

    def active(self) -> DesktopLease | None:
        if self._lease is not None and self._lease.expired():
            self._lease = None
        return self._lease

    def release(self, task_id: str, token: str) -> bool:
        if self.is_held(task_id, token):
            self._lease = None
            return True
        return False

    def renew(self, task_id: str, token: str, *, ttl_ms: int = DEFAULT_TTL_MS) -> DesktopLease:
        lease = self._require(task_id, token)
        if not 1 <= ttl_ms <= MAX_TTL_MS:
            raise ValueError(f"ttl_ms must be 1..{MAX_TTL_MS}")
        lease.expires_ms = _now_ms() + ttl_ms
        return lease

    def pause(self, task_id: str, token: str) -> bool:
        lease = self._require(task_id, token)
        lease.paused = True
        return True

    def resume(self, task_id: str, token: str) -> bool:
        lease = self._require(task_id, token)
        lease.paused = False
        return True

    def is_paused(self, task_id: str, token: str) -> bool:
        if not self.is_held(task_id, token):
            return False
        return self._lease.paused

    def force_release(self) -> bool:
        """Emergency stop: clear any lease unconditionally."""
        if self._lease is not None:
            self._lease = None
            return True
        return False


class FocusValidator:
    """Validate that a target window is still the focused, valid window."""

    async def validate(self, desktop, expected: dict) -> dict:
        """Check the live focused window against `expected` (address/class).

        `expected` must carry an `address`; `class` is also checked when given.
        Returns {valid, reason, window}. Never raises on a mismatch.
        """
        if not isinstance(expected, dict) or not expected.get("address"):
            return {"valid": False, "reason": "no_expected_window"}
        try:
            window = await desktop.query("activewindow")
        except (OSError, ValueError, RuntimeError):
            return {"valid": False, "reason": "compositor_unavailable"}
        if not window or not window.get("address"):
            return {"valid": False, "reason": "no_focused_window"}
        if window.get("address") != expected.get("address"):
            return {"valid": False, "reason": "window_changed", "window": _safe_window(window)}
        if expected.get("class") and str(window.get("class") or "") != str(expected.get("class")):
            return {"valid": False, "reason": "class_mismatch", "window": _safe_window(window)}
        if not window.get("visible", True):
            return {"valid": False, "reason": "window_not_visible", "window": _safe_window(window)}
        return {"valid": True, "reason": "ok", "window": _safe_window(window)}


def _safe_window(window: dict) -> dict:
    """Bounded window metadata for logging (no full title secrets)."""
    return {"address": window.get("address"), "class": window.get("class"),
            "title": str(window.get("title") or "")[:80],
            "workspace": (window.get("workspace") or {}).get("id")}


class DesktopController:
    """Gates every desktop action behind authorization + lease + focus.

    `desktop` is the Hyprland adapter (real or fake). `broker` is the
    PermissionBroker. `lease_manager` is the LeaseManager. `focus_validator`
    is optional; when present, an `expected_window` must be supplied for
    actions and validated immediately before execution.
    """

    def __init__(self, desktop, broker, lease_manager, focus_validator=None):
        self.desktop = desktop
        self.broker = broker
        self.leases = lease_manager
        self.focus = focus_validator or FocusValidator()
        self.actions = 0

    async def perform(self, task_id: str, token: str, op: str, value=None,
                      *, expected_window: dict | None = None) -> dict:
        # 1. Authorization: desktop_control must be allowed for this task.
        auth = self.broker.check(task_id, "desktop_control")
        if not auth["allowed"]:
            return {"ok": False, "stage": "authorization", "reason": auth["reason"]}
        # 2. Lease: an active, valid, non-paused lease for this task.
        if not self.leases.is_held(task_id, token):
            return {"ok": False, "stage": "lease", "reason": "no_active_lease"}
        if self.leases.is_paused(task_id, token):
            return {"ok": False, "stage": "lease", "reason": "lease_paused"}
        # 3. Focus validation (when an expected window is provided).
        if expected_window is not None:
            fv = await self.focus.validate(self.desktop, expected_window)
            if not fv["valid"]:
                return {"ok": False, "stage": "focus", "reason": fv["reason"],
                        "window": fv.get("window")}
        # 4. Bounded action.
        try:
            result = await self.desktop.action(op, value)
        except (OSError, ValueError, RuntimeError) as exc:
            return {"ok": False, "stage": "action", "reason": str(exc)[:200]}
        self.actions += 1
        return {"ok": True, "stage": "done", "result": result, "actions": self.actions}
