"""D1-gated escalation: store every detected alert, notify only what D1 flags.

The sidecar is not an agent loop. D1 (existing :8083 /v1/systemone) is an
*advisory* gate on the desktop notification only — it never authorizes tools,
launches models, or starts schedulers. Every detected alert is stored in the
sidecar DB so the Pi orchestrator can read the error and reason via the alerts
feed, regardless of the notification decision. If D1 is unavailable, a
critical-severity floor still notifies (fail safe).
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from .event_stream import MonitorEvent

_ALERT_KINDS = {"journal_alert", "network_alert", "resource_alert"}


@dataclass(frozen=True)
class Escalation:
    event_id: str
    source: str
    severity: str
    reason: str
    repeat_count: int
    observed_at: str


class EscalationRouter:
    def __init__(self, models, store, *, notifier=None, threshold=0.6,
                 cooldown_seconds=300, max_reason=400):
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be 0-1")
        self.models = models
        self.store = store
        self.notifier = notifier
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_reason = max_reason
        self._last: dict[str, float] = {}

    def _fingerprint(self, event: MonitorEvent) -> str:
        return f"{event.source}:{event.kind}:{event.message[:80]}"

    async def escalate(self, event: MonitorEvent) -> dict:
        fp = self._fingerprint(event)
        now = time.monotonic()
        last = self._last.get(fp)
        if last is not None and (now - last) < self.cooldown_seconds:
            return {"stored": False, "notified": False, "reason": "cooldown"}
        self._last[fp] = now
        # Always store so the orchestrator can see the error + reason.
        reason = f"[{event.severity}] {event.message}"[: self.max_reason]
        kind = event.kind if event.kind in _ALERT_KINDS else "alert"
        stored = self.store.record({
            "source": event.source,
            "kind": kind,
            "time_ms": int(time.time() * 1000),
            "message": reason,
            "event_key": fp[:160],
        })
        decision = await self._gate(event, reason)
        notified = False
        if decision.get("notify_recommended") and self.notifier is not None:
            notified = await self.notifier.notify(
                f"{event.source}: {event.severity}", event.message[:200], severity=event.severity)
        return {"stored": bool(stored.get("stored")), "notified": notified,
                "d1_score": decision.get("score"), "d1_fallback": bool(decision.get("fallback"))}

    async def _gate(self, event: MonitorEvent, reason: str) -> dict:
        state = {"source": event.source, "kind": event.kind,
                 "severity": event.severity, "message": reason[:600]}
        try:
            return await self.models.decide_alert(state, threshold=self.threshold)
        except Exception:
            # D1 unavailable: fail safe — still surface criticals, skip the rest.
            return {"notify_recommended": event.severity == "critical",
                    "score": None, "fallback": True}
