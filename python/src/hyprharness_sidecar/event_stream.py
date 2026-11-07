"""Journal + network intake for the alerting path. Passive, bounded, no sudo.

Journal: ``journalctl --follow -o json`` at a configurable priority floor.
Network: passive /sys/class/net operstate + packet-error counter deltas.
No shell=True, no sudo, no active scanning, no private-file ingestion.
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

Deliver = Callable[["MonitorEvent"], Awaitable[None]]

# syslog priority -> sidecar severity (0-2 emergency/alert/critical, 3 error, 4 warning)
_PRIORITY_SEVERITY = {0: "critical", 1: "critical", 2: "critical", 3: "error", 4: "warning"}


@dataclass(frozen=True)
class MonitorEvent:
    source: str               # journal, resource, network, hyprland
    kind: str
    message: str              # bounded local-only evidence
    severity: str             # info/warning/error/critical
    observed_at: str          # UTC ISO-8601
    repeat_count: int = 1
    attributes: dict[str, Any] = field(default_factory=dict)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    return " ".join(str(text).split())


class EventIntake:
    def __init__(self, *, journal_priority: int = 4, max_message: int = 500):
        if not (0 <= journal_priority <= 7):
            raise ValueError("journal_priority must be 0-7")
        self.journal_priority = journal_priority
        self.max_message = max_message

    # -- journal ----------------------------------------------------------
    async def follow_journal(self, deliver: Deliver):
        proc = await asyncio.create_subprocess_exec(
            "journalctl", "--follow", "-o", f"json-priority={self.journal_priority}",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                event = self._journal_event(line)
                if event is not None:
                    await deliver(event)
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    def _journal_event(self, line: bytes) -> "MonitorEvent | None":
        try:
            data = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            return None
        message = _clean(data.get("MESSAGE", ""))[: self.max_message]
        if not message:
            return None
        try:
            priority = int(data.get("PRIORITY", 6) or 6)
        except (TypeError, ValueError):
            priority = 6
        severity = _PRIORITY_SEVERITY.get(priority, "info")
        source = data.get("SYSLOG_IDENTIFIER") or data.get("_SYSTEMD_UNIT") or "journal"
        return MonitorEvent(source="journal", kind="journal_alert", message=message,
                            severity=severity, observed_at=_utcnow(),
                            attributes={"identifier": str(source)[:120], "priority": priority})

    # -- network ----------------------------------------------------------
    async def network_alerts(self, deliver: Deliver, *, interval: float = 5.0):
        prev_state: dict[str, str] = {}
        prev_errors: dict[str, int] = {}
        while True:
            for iface in _net_interfaces():
                if iface == "lo":
                    continue
                state, total_err = _iface_state(iface)
                if state is None:
                    continue
                for event in self._network_events(iface, state, total_err,
                                                  prev_state.get(iface), prev_errors.get(iface)):
                    await deliver(event)
                prev_state[iface] = state
                prev_errors[iface] = total_err
            await asyncio.sleep(interval)

    def _network_events(self, iface, state, total_err, old_state, old_err):
        """Pure per-snapshot decision: emit on down-transition or error-counter jump."""
        events = []
        if old_state is not None and state == "down" and old_state != "down":
            events.append(MonitorEvent(source="network", kind="network_alert",
                message=f"Interface {iface} went down", severity="error",
                observed_at=_utcnow(), attributes={"interface": iface}))
        if old_err is not None and total_err > old_err:
            events.append(MonitorEvent(source="network", kind="network_alert",
                message=f"Interface {iface}: {total_err - old_err} new packet error(s)",
                severity="warning", observed_at=_utcnow(), attributes={"interface": iface}))
        return events

    # -- resource (future) ------------------------------------------------
    async def resource_alerts(self, deliver: Deliver):
        raise NotImplementedError("Resource alert intake is not wired")


def _net_interfaces():
    try:
        return [p.name for p in Path("/sys/class/net").iterdir()]
    except OSError:
        return []


def _iface_state(iface):
    base = Path("/sys/class/net") / iface
    try:
        state = (base / "operstate").read_text().strip()
        rx = int((base / "statistics" / "rx_errors").read_text())
        tx = int((base / "statistics" / "tx_errors").read_text())
        return state, rx + tx
    except (OSError, ValueError):
        return None, 0
