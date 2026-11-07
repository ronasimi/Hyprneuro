"""Store every alert; D1 advises notifications only, never authorizes actions.

D1 supplies a score, not textual reasoning. Persist local policy explanations
and actual notification outcomes separately from the original event evidence.
No Pi wake, context injection or Durable workflow; users request inspection.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import time

from .event_stream import MonitorEvent

_ALERT_KINDS = {"journal_alert", "network_alert", "resource_alert"}


class EscalationRouter:
    def __init__(self, models, store, *, notifier=None, threshold=0.6,
                 cooldown_seconds=300, max_reason=400, max_cooldowns=1024):
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be 0-1")
        if cooldown_seconds < 0 or max_cooldowns < 1 or not 1 <= max_reason <= 4096:
            raise ValueError("Invalid cooldown/reason bounds")
        self.models = models
        self.store = store
        self.notifier = notifier
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self.max_reason = max_reason
        self.max_cooldowns = max_cooldowns
        self._last: OrderedDict[str, float] = OrderedDict()

    def _fingerprint(self, event: MonitorEvent) -> str:
        # Keep identical messages from different units/interfaces independent.
        parts = (event.source, event.kind, event.severity, event.message,
                 str(event.attributes.get("identifier", "")),
                 str(event.attributes.get("interface", "")))
        return hashlib.sha256("\0".join(parts).encode()).hexdigest()

    async def escalate(self, event: MonitorEvent) -> dict:
        fp = self._fingerprint(event)
        now = time.monotonic()
        while self._last and now - next(iter(self._last.values())) >= self.cooldown_seconds:
            self._last.popitem(last=False)
        cooling = fp in self._last
        reason = f"[{event.severity}] {event.message}"[:self.max_reason]
        stored = self.store.record({
            "source": event.source,
            "kind": event.kind if event.kind in _ALERT_KINDS else "alert",
            "time_ms": int(time.time() * 1000),
            "message": reason,
            "event_key": fp,
        })
        state = {"d1_status": "pending", "d1_score": None,
                 "notify_recommended": None, "d1_fallback": False,
                 "d1_reason": "Awaiting D1 score (no textual reasoning requested).",
                 "notification_status": "pending", "notified": False,
                 "threshold": self.threshold}
        if cooling:
            # A deduplicated row keeps its last real D1 evaluation; only the
            # latest notification outcome changes. New rows have no evaluation.
            previous = self.store.alert_outcome(stored["id"])
            if previous:
                state.update(previous)
            else:
                state.update(d1_status="cooldown",
                             d1_reason="Not evaluated: notification cooldown active.")
            state.update(notification_status="suppressed_cooldown", notified=False)
            self.store.update_alert(stored["id"], state)
            return {"stored": True, **state, "reason": "cooldown"}
        self._last[fp] = now
        if len(self._last) > self.max_cooldowns:
            self._last.popitem(last=False)
        self.store.update_alert(stored["id"], state)
        try:
            decision = await self._gate(event, reason)
            fallback = bool(decision.get("fallback"))
            recommended = decision["notify_recommended"]
            state.update(d1_evaluated_at_ms=int(time.time() * 1000),
                         d1_status="unavailable" if fallback else "scored",
                         d1_score=decision.get("score"), d1_fallback=fallback,
                         notify_recommended=recommended,
                         d1_reason=("D1 unavailable; critical-severity fallback policy."
                                    if fallback else "D1 score compared with threshold; no textual reasoning returned."),
                         notification_status="not_recommended")
            if recommended:
                state["notification_status"] = "disabled" if self.notifier is None else "pending"
            # Preserve the decision even if the notifier is interrupted.
            self.store.update_alert(stored["id"], state)
            if recommended and self.notifier is not None:
                try:
                    state["notified"] = await self.notifier.notify(
                        f"{event.source}: {event.severity}", event.message[:200], severity=event.severity)
                except Exception:
                    state["notified"] = False
                state["notification_status"] = "sent" if state["notified"] else "failed"
        except asyncio.CancelledError:
            if state["d1_status"] == "pending":
                state.update(d1_status="cancelled", d1_reason="D1 evaluation cancelled.")
            state["notification_status"] = "cancelled"
            raise
        finally:
            self.store.update_alert(stored["id"], state)
        return {"stored": bool(stored.get("stored")), **state}

    async def _gate(self, event: MonitorEvent, reason: str) -> dict:
        state = {"source": event.source, "kind": event.kind,
                 "severity": event.severity, "message": reason[:600]}
        try:
            decision = await self.models.decide_alert(state, threshold=self.threshold)
            if (type(decision.get("notify_recommended")) is not bool or
                    type(decision.get("score")) not in (float, int) or
                    not 0 <= decision["score"] <= 1):
                raise ValueError("Invalid D1 alert decision")
            return decision
        except Exception:
            return {"notify_recommended": event.severity == "critical",
                    "score": None, "fallback": True}
