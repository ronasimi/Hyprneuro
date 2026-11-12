"""Journal + network intake for the alerting path. Passive, bounded, no sudo.

Journal: ``journalctl --follow -o json`` at a configurable priority floor.
Network: passive /sys/class/net operstate + packet-error counter deltas.
No shell=True, no sudo, no active scanning, no private-file ingestion.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger(__name__)

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
    def __init__(self, *, journal_priority: int = 4, max_message: int = 500,
                 max_line_bytes: int = 65536, reconnect_seconds: float = 1,
                 store=None, catchup_seconds=3600, catchup_records=1000):
        if not (0 <= journal_priority <= 7):
            raise ValueError("journal_priority must be 0-7")
        if not 1 <= max_message <= 4096 or max_line_bytes < 1 or reconnect_seconds <= 0:
            raise ValueError("Invalid journal bounds/reconnect interval")
        if catchup_seconds <= 0 or type(catchup_records) is not int or catchup_records < 1:
            raise ValueError("Invalid catch-up bounds")
        self.store = store
        self.catchup_seconds = catchup_seconds
        self.catchup_records = catchup_records
        self.max_line_bytes = max_line_bytes
        self.reconnect_seconds = reconnect_seconds
        self.oversized = 0
        self.failures = 0
        self.journal_priority = journal_priority
        self.max_message = max_message
        self.network_status = {"samples": 0, "observed_at_ms": None, "interfaces": {}}
        self.resource_status = {"samples": 0, "observed_at_ms": None}

    # -- journal ----------------------------------------------------------
    async def follow_journal(self, deliver: Deliver):
        # Delivery applies backpressure: no unbounded queue behind slow D1 calls.
        # The stream buffer and individual JSON records are independently bounded.
        delay = self.reconnect_seconds
        fallback = False
        tail = False
        while True:
            proc = None
            started = time.monotonic()
            started_ms = int(time.time()*1000)
            try:
                checkpoint = self.store.journal_checkpoint() if self.store else None
                replay = checkpoint is not None and not tail
                tail = False
                options = ["--lines=0"]
                if replay:
                    floor = int((time.time()-self.catchup_seconds)*1000)
                    since = max(checkpoint["time_ms"], floor)
                    options = [f"--since=@{since/1000:.3f}"]
                    if not fallback:
                        options.append("--after-cursor=" + checkpoint["cursor"])
                    if checkpoint["time_ms"] < floor:
                        self.store.journal_gap("Catch-up truncated to configured time window")
                count = 0
                proc = await asyncio.create_subprocess_exec(
                    "journalctl", "--follow", "--output=json",
                    f"--priority={self.journal_priority}", *options, "--no-pager",
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    limit=self.max_line_bytes)
                async for line in self._journal_lines(proc.stdout, report_drops=True):
                    event = self._journal_event(line)
                    if event is not None:
                        try:
                            await deliver(event)
                            if event.attributes.get("cursor"):
                                fallback = False
                            if event.attributes.get("realtime_ms", 0) > started_ms:
                                replay = False  # Live records do not exhaust the catch-up budget.
                        except Exception:
                            self.failures += 1
                            log.exception("Journal alert delivery failed")
                            break  # Do not advance past evidence that failed to commit.
                    count += 1
                    if replay and count >= self.catchup_records:
                        self.store.journal_gap("Catch-up record budget reached; resumed at live tail")
                        tail = True
                        break
                else:
                    # EOF may precede asyncio's child-exit callback. Reap before
                    # inspecting status, or a vacuumed cursor can retry forever.
                    await asyncio.wait_for(proc.wait(), 1)
                if replay and not fallback and proc.returncode not in (None, 0):
                    self.store.journal_gap("Cursor unavailable; bounded timestamp fallback (duplicates possible)")
                    fallback = True
                self.failures += 1
                log.warning("journalctl exited; reconnecting")
            except OSError as exc:
                self.failures += 1
                log.warning("Cannot follow journal: %s", exc)
            finally:
                if proc is not None:
                    if proc.returncode is None:
                        try:
                            proc.kill()
                        except ProcessLookupError:
                            pass
                    await proc.wait()
            if time.monotonic() - started >= 60:
                delay = self.reconnect_seconds
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)

    async def _journal_lines(self, reader, *, report_drops=False):
        """Discard oversized records through their newline, then resume parsing."""
        pending = bytearray()
        dropping = False
        while chunk := await reader.read(8192):
            parts = chunk.split(b"\n")
            for index, part in enumerate(parts):
                complete = index < len(parts) - 1
                if not dropping:
                    if len(pending) + len(part) > self.max_line_bytes:
                        pending.clear()
                        dropping = True
                        self.oversized += 1
                    else:
                        pending.extend(part)
                if complete:
                    if not dropping:
                        yield bytes(pending)
                    elif report_drops:
                        yield b""  # Oversized frames still consume the replay budget.
                    pending.clear()
                    dropping = False
        # An unterminated final record is not a complete journal JSON frame.

    def _journal_event(self, line: bytes) -> "MonitorEvent | None":
        try:
            data = json.loads(line)
        except (ValueError, RecursionError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("MESSAGE"), str):
            return None
        message = _clean(data["MESSAGE"])[: self.max_message]
        if not message:
            return None
        raw_priority = data.get("PRIORITY", 6)
        if type(raw_priority) not in (str, int):
            return None
        try:
            priority = int(raw_priority)
        except ValueError:
            return None
        if not 0 <= priority <= self.journal_priority:
            return None
        severity = _PRIORITY_SEVERITY.get(priority, "info")
        source = data.get("SYSLOG_IDENTIFIER") or data.get("_SYSTEMD_UNIT") or "journal"
        attributes = {"identifier": str(source)[:120], "priority": priority}
        cursor = data.get("__CURSOR")
        realtime = data.get("__REALTIME_TIMESTAMP")
        observed = _utcnow()
        if isinstance(cursor, str) and 0 < len(cursor) <= 2048 and not any(ord(c) < 32 for c in cursor):
            try:
                when = int(realtime)//1000
                if not 0 < when <= int(time.time()*1000)+300000:
                    return None
                observed = datetime.fromtimestamp(when/1000, timezone.utc).isoformat()
                attributes.update(cursor=cursor, realtime_ms=when)
            except (ValueError, TypeError, OverflowError, OSError):
                return None
        return MonitorEvent(source="journal", kind="journal_alert", message=message,
                            severity=severity, observed_at=observed, attributes=attributes)

    # -- network ----------------------------------------------------------
    async def network_alerts(self, deliver: Deliver, *, interval: float = 5.0):
        prev_state: dict[str, str] = {}
        prev_errors: dict[str, int] = {}
        while True:
            interfaces = set(_net_interfaces()[:64])  # bounded passive metadata only
            observed = {}
            prev_state = {k: v for k, v in prev_state.items() if k in interfaces}
            prev_errors = {k: v for k, v in prev_errors.items() if k in interfaces}
            for iface in interfaces:
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
                observed[iface] = {"state": state, "errors": total_err}
            self.network_status = {"samples": self.network_status["samples"] + 1,
                                   "observed_at_ms": int(time.time()*1000), "interfaces": observed}
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

    async def resource_alerts(self, deliver: Deliver):
        from .monitor import Monitor
        detector = ResourceAlerts()
        async def on_sample(snapshot):
            memory = snapshot.get("memory_kib", {})
            total = memory.get("MemTotal", 0)
            self.resource_status = {"samples": self.resource_status["samples"] + 1,
                "observed_at_ms": int(time.time()*1000),
                "cpu_pct": snapshot.get("cpu_percent", {}).get("cpu"),
                "ram_pct": 100*(1-memory["MemAvailable"]/total) if total > 0 and "MemAvailable" in memory else None,
                "root_disk_pct": snapshot.get("disk_used_percent", {}).get("/")}
            for event in detector.events(snapshot, now=time.monotonic()):
                await deliver(event)
        await Monitor().run(on_sample)


class ResourceAlerts:
    """One transition per sustained high episode; reset only below low-water.

    Missing metrics break the duration and discard state. No temperature/GPU
    estimates: only hwmon/DRM readings actually supplied by Monitor are used.
    """
    def __init__(self, duration=30):
        if duration < 0:
            raise ValueError("duration must be nonnegative")
        self.duration = duration
        self.state = {}

    def events(self, snapshot, *, now):
        readings = {}
        def add(key, value, high, low, unit="%"):
            if type(value) in (int, float) and 0 <= value <= 1000:
                readings[key] = (value, high, low, unit)
        add("cpu", snapshot.get("cpu_percent", {}).get("cpu"), 90, 75)
        mem = snapshot.get("memory_kib", {})
        if mem.get("MemTotal", 0) > 0 and "MemAvailable" in mem:
            add("memory", 100*(1-mem["MemAvailable"]/mem["MemTotal"]), 90, 80)
        for path, used in snapshot.get("disk_used_percent", {}).items():
            add("disk:"+path, used, 95, 90)
        for resource, text in snapshot.get("pressure", {}).items():
            # Linux PSI some/avg10: percent of wall time with stalled work.
            for line in text.splitlines():
                if line.startswith("some "):
                    try:
                        avg = float(dict(p.split("=", 1) for p in line.split()[1:])["avg10"])
                        high, low = {"cpu": (50, 20), "memory": (10, 5), "io": (25, 10)}[resource]
                        add("pressure:"+resource, avg, high, low)
                    except (ValueError, KeyError):
                        pass
        for sensor, milli in snapshot.get("temperatures_millicelsius", {}).items():
            if type(milli) in (int, float) and milli > 0:
                add("temperature:"+sensor, milli/1000, 85, 75, "C")
        for device, counters in snapshot.get("gpu", {}).items():
            add("gpu:"+device, counters.get("gpu_busy_percent"), 95, 80)
        self.state = {k: v for k, v in self.state.items() if k in readings}
        events = []
        for key, (value, high, low, unit) in readings.items():
            start, active = self.state.get(key, (None, False))
            if value < low:
                start, active = None, False
            elif not active:
                if value < high:
                    start = None
                else:
                    start = now if start is None else start
                    if now-start >= self.duration:
                        active = True
                        events.append(MonitorEvent("resource", "resource_alert",
                            f"{key}: {value:.1f}{unit} sustained for {self.duration:g}s (high {high}{unit}, reset below {low}{unit})",
                            "warning", _utcnow(), attributes={"metric": key}))
            self.state[key] = start, active
        return events


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
