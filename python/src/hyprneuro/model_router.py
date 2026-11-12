"""Deterministic hybrid model router (section F).

Routes a task to the correct local LFM endpoint using deterministic rules
first. D1 (decision) is used ONLY when a classification is explicitly
requested; it is never invoked "just in case". Omni is used only for
genuinely multimodal tasks. Ordinary reasoning/coding/tool tasks go to text.

This module decides routing and builds bounded, structured handoffs between
models (which use independent KV caches). It performs no inference itself.
"""
from __future__ import annotations

from typing import Any

ROLES = frozenset({"text", "omni", "decision"})
TASK_KINDS = frozenset({"chat", "code", "tool", "vision", "classify", "general"})

# Handoff payload bounds: keep cross-model handoffs compact so each model's
# independent KV cache is not inflated by the other model's full context.
MAX_HANDOFF_CHARS = 4000


def _b64(value: str, limit: int) -> str:
    return value[:limit]


class ModelRouter:
    """Deterministic routing + bounded structured handoffs."""

    def route(self, task_kind: str, *, has_multimodal: bool = False,
              needs_classification: bool = False) -> str:
        """Return the target role for a task. Deterministic, no inference."""
        if task_kind not in TASK_KINDS:
            raise ValueError(f"task_kind must be one of {sorted(TASK_KINDS)}")
        if not isinstance(has_multimodal, bool) or not isinstance(needs_classification, bool):
            raise ValueError("has_multimodal/needs_classification must be booleans")
        # Classification is the most specific: a D1 decision is requested.
        if task_kind == "classify" or needs_classification:
            return "decision"
        # Multimodal content requires the Omni model.
        if task_kind == "vision" or has_multimodal:
            return "omni"
        # Everything else is ordinary reasoning/coding/tool work on text.
        return "text"

    def handoff(self, from_role: str, to_role: str, payload: dict) -> dict:
        """Build a bounded, structured handoff between two model roles.

        Only the fields the target model can act on are carried. The full
        source context is NOT forwarded — each model keeps its own KV cache.
        """
        if from_role not in ROLES or to_role not in ROLES:
            raise ValueError(f"roles must be in {sorted(ROLES)}")
        if from_role == to_role:
            return {"handoff": False, "reason": "same_role", "to": to_role}
        if not isinstance(payload, dict):
            raise ValueError("handoff payload must be an object")
        summary = str(payload.get("summary") or "")[:800]
        focus = str(payload.get("focus") or "")[:400]
        app_id = _b64(str(payload.get("app_id") or ""), 120)
        task_id = _b64(str(payload.get("task_id") or ""), 128)
        # Carry at most a small, explicit evidence excerpt (never screenshots).
        evidence = _b64(str(payload.get("evidence") or ""), 1200)
        handoff = {
            "schema": "hyprneuro.handoff/1",
            "from": from_role,
            "to": to_role,
            "task_id": task_id or None,
            "app_id": app_id or None,
            "summary": summary,
            "focus": focus,
            "evidence": evidence,
            "untrusted": True,
            "note": "Structured handoff only; target model keeps its own KV cache.",
        }
        import json
        encoded = json.dumps(handoff, ensure_ascii=False)
        if len(encoded) > MAX_HANDOFF_CHARS:
            # Truncate the largest free-text field to stay within the bound.
            handoff["evidence"] = _b64(evidence, 400)
        return {"handoff": True, **handoff}

    def decision_required(self, task_kind: str, *, has_multimodal: bool = False) -> bool:
        """True only when a D1 classification is genuinely required.

        Used by callers to avoid invoking the decision endpoint unnecessarily.
        """
        return self.route(task_kind, has_multimodal=has_multimodal) == "decision"
