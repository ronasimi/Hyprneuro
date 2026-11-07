"""Unwired journal/resource/network intake. No log reader is started."""
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MonitorEvent:
    source: str               # journal, resource, network, hyprland
    kind: str
    message: str              # bounded local-only evidence
    severity: str             # info/warning/error/critical
    observed_at: str          # UTC ISO-8601
    repeat_count: int = 1
    attributes: dict[str, Any] = field(default_factory=dict)


class EventIntake:
    async def follow_journal(self, deliver):
        # TODO: journalctl --follow --output=json with an explicit source scope.
        # TODO: bounded queue, cursor/resume, restart backoff, local redaction.
        # Never shell=True, sudo, or automatically ingest private files.
        raise NotImplementedError("Journal intake is not wired")

    async def resource_alerts(self, deliver):
        # TODO: consume existing Monitor.latest instead of polling /proc twice.
        # TODO: per-metric hysteresis, minimum duration and alert cooldown.
        raise NotImplementedError("Resource alert intake is not wired")

    async def network_alerts(self, deliver):
        # TODO: passive netlink/interface/routing change detection only.
        # Active network scanning always requires independent approval.
        raise NotImplementedError("Network alert intake is not wired")


class DuplicateReducer:
    def accept(self, event: MonitorEvent):
        # TODO: stable source/unit/message fingerprint, ignore timestamps,
        # bounded duplicate window and persistence across broker restarts.
        # Emit immediately on first sight, then aggregate repeat_count.
        raise NotImplementedError("Duplicate reducer is not implemented")
