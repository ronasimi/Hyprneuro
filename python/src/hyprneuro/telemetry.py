"""Telemetry + adaptive residency / idle compaction (Phase 8).

`Telemetry` keeps lightweight counters for the assistant surface and a compact
snapshot for the `telemetry` IPC action. `IdleCompactor` performs bounded
compaction only when the system has been idle: it trims the app registry to a
smaller "idle" footprint and evicts the oldest app-scoped memory rows, so an
idle sidecar stays within a small memory budget and does no heavy work while
active.

Both are model-free and allocation-cheap; they never touch inference.
"""
from __future__ import annotations

import time
from typing import Any

# Counter names the assistant surface increments.
COUNTERS = (
    "focus_events", "ipc_requests", "skill_discover", "skill_load", "skill_propose",
    "skill_approve", "skill_retire", "memory_remember", "memory_recall", "memory_promote",
    "task_create", "task_update", "auth_create", "auth_check", "auth_expand", "auth_revoke",
    "route", "handoff", "lease_acquire", "desktop_actions",
)


def _now_ms() -> int:
    return int(time.time() * 1000)


class Telemetry:
    """Lightweight counters + a bounded snapshot. Thread-safe enough for the
    single asyncio loop the sidecar runs on."""

    def __init__(self):
        self.counts: dict[str, int] = {name: 0 for name in COUNTERS}
        self.last_activity_ms = _now_ms()
        self.started_ms = _now_ms()

    def bump(self, name: str, n: int = 1) -> None:
        if name in self.counts:
            self.counts[name] += n
        self.last_activity_ms = _now_ms()

    def idle_ms(self, now_ms: int | None = None) -> int:
        return (now_ms or _now_ms()) - self.last_activity_ms

    def snapshot(self, store: Any | None = None) -> dict:
        now = _now_ms()
        out = {
            "schema": "hyprneuro.telemetry/1",
            "uptime_ms": now - self.started_ms,
            "idle_ms": now - self.last_activity_ms,
            "counters": dict(self.counts),
        }
        if store is not None:
            try:
                out["store"] = store.size()
            except (AttributeError, OSError):
                pass
        return out


class IdleCompactor:
    """Compacts assistant state only after an idle window.

    `idle_ms` is the inactivity threshold. `registry_idle_recent` is how many
    recent apps to keep while idle (focused is always kept). `app_memory_keep`
    is the cap on app-scoped memory rows retained.
    """

    def __init__(self, registry=None, store=None, *, idle_ms: int = 60_000,
                 registry_idle_recent: int = 2, app_memory_keep: int = 64):
        if not 1000 <= idle_ms <= 3_600_000:
            raise ValueError("idle_ms must be 1s..1h")
        if not 0 <= registry_idle_recent <= 4:
            raise ValueError("registry_idle_recent must be 0..4")
        if not 8 <= app_memory_keep <= 1024:
            raise ValueError("app_memory_keep must be 8..1024")
        self.registry = registry
        self.store = store
        self.idle_ms = idle_ms
        self.registry_idle_recent = registry_idle_recent
        self.app_memory_keep = app_memory_keep
        self.last_compact_ms = 0
        self.compactions = 0

    def should_compact(self, telemetry: Telemetry, now_ms: int | None = None) -> bool:
        return telemetry.idle_ms(now_ms) >= self.idle_ms

    def compact(self, telemetry: Telemetry, now_ms: int | None = None) -> dict:
        now = now_ms or _now_ms()
        if not self.should_compact(telemetry, now):
            return {"compacted": False, "reason": "active", "idle_ms": telemetry.idle_ms(now)}
        details: dict[str, Any] = {}
        if self.registry is not None and hasattr(self.registry, "trim_to"):
            details["registry_recent_before"] = len(self.registry.recent)
            self.registry.trim_to(self.registry_idle_recent)
            details["registry_recent_after"] = len(self.registry.recent)
        if self.store is not None and hasattr(self.store, "app_memory_trim"):
            details["app_memory_evicted"] = self.store.app_memory_trim(self.app_memory_keep)
        self.last_compact_ms = now
        self.compactions += 1
        return {"compacted": True, "reason": "idle", "idle_ms": telemetry.idle_ms(now),
                "details": details, "compactions": self.compactions}
