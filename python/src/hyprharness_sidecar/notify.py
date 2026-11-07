"""Desktop notifications via notify-send. A dead notifier never crashes the service."""
from __future__ import annotations

import asyncio

MAX_SUMMARY = 120
MAX_BODY = 300

_SEVERITY_TO_URGENCY = {
    "info": "low",
    "warning": "normal",
    "error": "critical",
    "critical": "critical",
}


class Notifier:
    """Thin notify-send wrapper: bounded, timed, best-effort, never raises."""

    def __init__(self, app: str = "hyprharness-sidecar", binary: str = "notify-send",
                 timeout: float = 5):
        self.app = app
        self.binary = binary
        self.timeout = timeout

    async def notify(self, summary: str, body: str = "", *, severity: str = "info") -> bool:
        """Send one desktop notification. Returns True on success.

        A notification failure (missing binary, timeout, bus error) must never
        take the sidecar down, so all failures are swallowed and reported False.
        """
        summary = str(summary)[:MAX_SUMMARY]
        body = str(body)[:MAX_BODY]
        urgency = _SEVERITY_TO_URGENCY.get(severity, "normal")
        argv = [self.binary, "-a", self.app, "-u", urgency, summary]
        if body:
            argv.append(body)
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            try:
                await asyncio.wait_for(proc.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return False
            return proc.returncode == 0
        except (OSError, ValueError):
            return False
