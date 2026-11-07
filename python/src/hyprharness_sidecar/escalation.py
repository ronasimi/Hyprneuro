"""Unwired D1 -> pi-durable main-model escalation boundary.

d1 remains on the existing Vulkan llama.cpp decision service (port 8083).
No automatic inference, notification or privileged action is started here.
"""
from dataclasses import dataclass
from .event_stream import MonitorEvent


@dataclass(frozen=True)
class Escalation:
    event_id: str
    source: str
    severity: str
    reason: str
    repeat_count: int
    observed_at: str


class EscalationRouter:
    def __init__(self, models, durable, store):
        self.models = models
        self.durable = durable       # Existing Pi Durable, not a new agent loop
        self.store = store

    async def classify(self, event: MonitorEvent):
        # TODO(d1): Define a strict /v1/systemone monitor schema:
        # escalation decision, severity, confidence, short reason.
        # Respect configured watched events; never let a model authorize tools.
        # Keep context bounded for d1's 1K window; deterministic critical fallback.
        raise NotImplementedError("D1 event classification is not wired")

    async def escalate(self, event: MonitorEvent):
        # TODO(durable): idempotency key + time snapshot + redacted event data.
        # Submit through Broker's existing durable admission/permission path;
        # never launch an inherited/default model or another scheduler.
        # TODO(notification): notify-send and open/raise managed GTK UI only
        # AFTER durable job admission. Add repeat rate-limiting and cooldown.
        raise NotImplementedError("Durable escalation is not wired")
