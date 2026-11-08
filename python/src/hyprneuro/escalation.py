"""Store every alert; D1 advises notifications only, never authorizes actions.

D1 scoring supplies no textual reasoning. Optional text generation is separate.
Persist local policy explanations
and actual notification outcomes separately from the original event evidence.
No Pi wake, context injection or Durable workflow; users request inspection.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
import hashlib
import time
from dataclasses import asdict

from .event_stream import MonitorEvent

_ALERT_KINDS = {"journal_alert", "network_alert", "resource_alert"}


class EscalationRouter:
    def __init__(self, models, store, *, notifier=None, threshold=0.6,
                 cooldown_seconds=300, max_reason=400, max_cooldowns=1024, freshness_seconds=120,
                 explanation_enabled=False):
        if not 0 <= threshold <= 1:
            raise ValueError("threshold must be 0-1")
        if cooldown_seconds < 0 or max_cooldowns < 1 or not 1 <= max_reason <= 4096:
            raise ValueError("Invalid cooldown/reason bounds")
        self.explanation_enabled = explanation_enabled
        self.freshness_seconds = freshness_seconds
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

    async def escalate(self, event: MonitorEvent, *, _stored=None) -> dict:
        fp = self._fingerprint(event)
        now = time.monotonic()
        while self._last and now - next(iter(self._last.values())) >= self.cooldown_seconds:
            self._last.popitem(last=False)
        cooling = fp in self._last
        reason = f"[{event.severity}] {event.message}"[:self.max_reason]
        item = {
            "source": event.source,
            "kind": event.kind if event.kind in _ALERT_KINDS else "alert",
            "time_ms": event.attributes.get("realtime_ms", int(time.time() * 1000)),
            "message": reason,
            "event_key": fp,
        }
        journal = bool(event.attributes.get("cursor"))
        if journal:
            item["event_key"] = None  # Journal identity, not message/time deduplication.
        stored = _stored or (self.store.record_journal(item, asdict(event)) if journal else self.store.record(item))
        if stored.get("phase") == "done":
            return {"stored": True, **(self.store.alert_outcome(stored["id"]) or {})}
        previous = self.store.alert_outcome(stored["id"]) if journal else None
        resume_gate = previous and previous.get("d1_status") in ("scored", "unavailable")
        state = {"d1_status": "pending", "d1_score": None,
                 "notify_recommended": None, "d1_fallback": False,
                 "d1_reason": "Awaiting D1 score (no textual reasoning requested).",
                 "notification_status": "pending", "notified": False,
                 "threshold": self.threshold}
        if cooling and not _stored and not stored.get("replayed"):
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
        if resume_gate:
            state.update(previous)
        self.store.update_alert(stored["id"], state)
        try:
            decision = ({"fallback": state["d1_fallback"], "score": state["d1_score"],
                         "notify_recommended": state["notify_recommended"]} if resume_gate
                        else await self._gate(event, reason))
            fallback = bool(decision.get("fallback"))
            recommended = decision["notify_recommended"]
            evaluated_at = state.get("d1_evaluated_at_ms") if resume_gate else None
            state.update(d1_evaluated_at_ms=evaluated_at or int(time.time() * 1000),
                         d1_status="unavailable" if fallback else "scored",
                         d1_score=decision.get("score"), d1_fallback=fallback,
                         notify_recommended=recommended,
                         d1_reason=("D1 unavailable; critical-severity fallback policy."
                                    if fallback else "D1 score compared with threshold; no textual reasoning returned."),
                         notification_status="not_recommended")
            state["notified"] = False
            if recommended:
                state["notification_status"] = "disabled" if self.notifier is None else "pending"
            # Preserve the decision even if the notifier is interrupted.
            self.store.update_alert(stored["id"], state)
            state.setdefault("model_explanation_status", "disabled")
            if self.explanation_enabled and not state.get("model_explanation"):
                try:
                    text = await self.models.explain_alert({"source": event.source,
                        "severity": event.severity, "message": event.message[:500]})
                    if not isinstance(text, str) or not text.strip():
                        raise ValueError("Empty model explanation")
                    state.update(model_explanation_status="generated", model_explanation=text[:500],
                                 model_explanation_label="Actual D1 model explanation (untrusted, not verified)")
                except Exception:
                    state["model_explanation_status"] = "unavailable"
                self.store.update_alert(stored["id"], state)
            if recommended and self.notifier is not None:
                now_ms = int(time.time()*1000)
                age = now_ms - event.attributes.get("realtime_ms", now_ms)
                if age > self.freshness_seconds*1000:
                    state["notification_status"] = "suppressed_stale"
                elif not self.store.reserve_notification(now_ms=now_ms):
                    state["notification_status"] = "suppressed_rate"
                else:
                    await self._notify(event, state)
        except asyncio.CancelledError:
            if state["d1_status"] == "pending":
                state.update(d1_status="cancelled", d1_reason="D1 evaluation cancelled.")
            state["notification_status"] = "cancelled"
            raise
        finally:
            self.store.update_alert(stored["id"], state)
        return {"stored": bool(stored.get("stored")), **state}

    async def recover(self):
        """Bounded batches, no in-memory backlog; stored evidence survives crashes."""
        while batch := self.store.pending_journal():
            for ident, event in batch:
                await self.escalate(MonitorEvent(**event), _stored={"id": ident, "stored": True})
            await asyncio.sleep(0)

    async def _notify(self, event, state):
        try:
            state["notified"] = await self.notifier.notify(
                f"{event.source}: {event.severity}", event.message[:200], severity=event.severity)
        except Exception:
            state["notified"] = False
        state["notification_status"] = "sent" if state["notified"] else "failed"

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
