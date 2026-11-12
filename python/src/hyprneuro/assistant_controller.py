"""Hotkey-activated assistant controller (Phase 6).

A model-free high-level facade over the sidecar assistant IPC. This is the
"assistant brain" a native Wayland hotkey UI would drive; it is also exposed
as a CLI so a Hyprland hotkey can invoke it directly (e.g. bind a key to
`hyprneuro-assistant status` or `hyprneuro-assistant stop`).

It composes the already-built primitives:
  - app context (application tracking)
  - durable task state (selection)
  - permission broker (approvals)
  - desktop-control lease (pause / emergency stop)
  - telemetry (status)

Nothing here performs inference; it only reads/writes bounded sidecar state.
`request` is the async sidecar client callable, so the controller is fully
testable against a fake.
"""
from __future__ import annotations

import asyncio
import secrets
from typing import Any, Awaitable, Callable, Iterable

Request = Callable[..., Awaitable[Any]]


class AssistantController:
    def __init__(self, request: Request, *, poll_interval_s: float = 0.5):
        if not 0.01 <= poll_interval_s <= 5.0:
            raise ValueError("poll_interval_s must be 0.01..5.0")
        self._request = request
        self._poll_interval_s = poll_interval_s
        self._pending: dict[str, dict] = {}
        self._active_task: str | None = None

    async def _rpc(self, payload: dict) -> Any:
        return await self._request(payload)

    # --- Context -----------------------------------------------------------
    async def context(self) -> dict:
        return await self._rpc({"action": "app_context"})

    @staticmethod
    def _task_list(out) -> list[dict]:
        # task_list returns a list (or {"tasks": [...]} in some backends).
        if isinstance(out, list):
            return out
        if isinstance(out, dict):
            return out.get("tasks", [])
        return []

    async def status(self) -> dict:
        """Bounded snapshot: focus, active task, tasks, pending approvals, telemetry."""
        ctx = await self.context()
        tasks = self._task_list(await self._rpc({"action": "task_list"}))
        telemetry = await self._rpc({"action": "telemetry"})
        pending = [a for a in self._pending.values() if a["status"] == "pending"]
        active = None
        if self._active_task:
            active = await self._rpc({"action": "task_get", "id": self._active_task})
        return {
            "schema": "hyprneuro.assistant/1",
            "focused": ctx.get("focused"),
            "active_task": active,
            "tasks": tasks,
            "pending_approvals": pending,
            "telemetry": telemetry,
        }

    # --- Task selection ----------------------------------------------------
    async def tasks(self) -> list[dict]:
        return self._task_list(await self._rpc({"action": "task_list"}))

    async def select_task(self, task_id: str) -> dict:
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            raise ValueError("Invalid task_id")
        task = await self._rpc({"action": "task_get", "id": task_id})
        self._active_task = task["id"]
        return task

    # --- Approvals ---------------------------------------------------------
    async def request_approval(self, task_id: str, op: str, reason: str = "") -> dict:
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("Invalid task_id")
        if not isinstance(op, str) or not op or len(op) > 40:
            raise ValueError("Invalid op")
        approval = {
            "id": secrets.token_hex(8), "task_id": task_id, "op": op,
            "reason": str(reason)[:400], "status": "pending",
        }
        self._pending[approval["id"]] = approval
        return dict(approval)

    async def approve(self, approval_id: str) -> dict:
        approval = self._pending.get(approval_id)
        if approval is None:
            raise KeyError("Unknown approval")
        if approval["status"] != "pending":
            raise RuntimeError("Approval already resolved")
        # Grant the op through the permission broker (records the approval).
        await self._rpc({"action": "auth_expand", "task_id": approval["task_id"],
                         "ops": [approval["op"]], "approved": True})
        approval["status"] = "approved"
        return dict(approval)

    async def deny(self, approval_id: str) -> dict:
        approval = self._pending.get(approval_id)
        if approval is None:
            raise KeyError("Unknown approval")
        if approval["status"] != "pending":
            raise RuntimeError("Approval already resolved")
        approval["status"] = "denied"
        return dict(approval)

    # --- Streaming (bounded polling) ---------------------------------------
    async def stream(self, task_id: str, on_update: Callable[[dict], Any],
                     *, max_polls: int = 120) -> dict:
        """Poll a task's state and emit updates until it settles or `max_polls`.

        `on_update` is called with each changed task state (sync or async).
        Bounded: stops at `max_polls` or when the task reaches a terminal state.
        """
        if not 1 <= max_polls <= 1000:
            raise ValueError("max_polls must be 1..1000")
        terminal = {"done", "failed", "cancelled", "blocked"}
        last_state = None
        for _ in range(max_polls):
            task = await self._rpc({"action": "task_get", "id": task_id})
            state = task.get("state")
            if state != last_state:
                result = on_update(task)
                if asyncio.iscoroutine(result):
                    await result
                last_state = state
            if state in terminal:
                return task
            await asyncio.sleep(self._poll_interval_s)
        return task

    # --- Control -----------------------------------------------------------
    async def pause(self, task_id: str) -> dict:
        return await self._rpc({"action": "task_update", "id": task_id, "state": "paused"})

    async def resume(self, task_id: str) -> dict:
        return await self._rpc({"action": "task_update", "id": task_id, "state": "running"})

    async def emergency_stop(self) -> dict:
        """Clear any desktop lease and pause the active task (fail-safe)."""
        stopped = await self._rpc({"action": "lease_emergency_stop"})
        if self._active_task:
            try:
                await self._rpc({"action": "task_update", "id": self._active_task,
                                 "state": "paused"})
            except Exception:
                pass
        return {"stopped": stopped.get("stopped", False), "active_task": self._active_task}
