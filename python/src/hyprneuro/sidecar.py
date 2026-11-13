"""Independent, optional Hyprneuro observational sidecar.

It provides metadata storage and read-only, bounded context feeds for
LFM3 text and Omni without launching either model or a new Pi agent loop.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import asyncio
import json
import math
from dataclasses import asdict, fields
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import time

from .sidecar_store import SidecarStore

MAX_REQUEST = 10 * 1024 * 1024  # 10 MiB: includes JSON and base64 overhead
MAX_RESPONSE = 262144
RETENTION_INTERVAL_SECONDS = 3600


def paths():
    """Keep legacy paths: the rename must not strand records or live clients."""
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if not runtime or not Path(runtime).is_absolute():
        raise RuntimeError("XDG_RUNTIME_DIR is required")
    root = Path(runtime) / "hyprharness"
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return root / "sidecar.sock", state / "hyprharness" / "sidecar" / "observations.sqlite3"


def ensure_private(path):
    path.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.is_symlink() or path.stat().st_uid != os.getuid():
        raise RuntimeError("Unsafe sidecar directory")
    path.chmod(0o700)


def prune_old(store, days):
    """Delete observations older than the retention window; return deleted count."""
    before_ms = int(time.time() * 1000) - int(days * 86_400_000)
    return store.prune(before_ms=before_ms)["deleted"]


async def run_retention(store, days, *, interval_seconds=RETENTION_INTERVAL_SECONDS):
    """Prune on startup, then on a fixed interval. A failed prune never kills the service."""
    while True:
        try:
            prune_old(store, days)
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval_seconds)


class SidecarServer:
    def __init__(self, store, *, allow_ingest=False, capture_enabled=False,
                 on_demand=False, browser_ingress=None, alert_enabled=False, resources_enabled=False,
                 assistant_enabled=False, assistant_recent_apps=5, assistant_focus_debounce_ms=250,
                 skills_dir=None):
        self.store = store
        self.allow_ingest = allow_ingest
        self.capture_enabled = capture_enabled
        self.on_demand = on_demand
        self.alert_enabled = alert_enabled
        self.resources_enabled = resources_enabled
        self.watcher = None
        self.browser_ingress = browser_ingress
        self.browser_capture_source = None
        self.handlers = set()
        self.embeddings = None
        self.active_settings = {}
        self.settings_file = None
        self.producers = []
        self.event_intake = None
        # Application-aware assistant (opt-in). Model-free focus tracking;
        # metadata + tiered memory live outside the model context by default.
        self.assistant_enabled = assistant_enabled
        self.registry = None
        self.memory = None
        self.skills = None
        self.app_watcher = None
        self.app_skill_context = None
        self.application_events = None
        self.broker = None
        self.router = None
        self.leases = None
        self.desktop_controller = None
        self.compactor = None
        from .telemetry import Telemetry, IdleCompactor
        self.telemetry = Telemetry()
        if assistant_enabled:
            from .application import AppRegistry, SkillIndex, TieredMemory
            from .authorization import PermissionBroker
            from .model_router import ModelRouter
            from .desktop_control import LeaseManager
            self.registry = AppRegistry(max_recent=assistant_recent_apps,
                                        debounce_ms=assistant_focus_debounce_ms)
            self.memory = TieredMemory(store)
            self.skills = SkillIndex.from_directory(skills_dir) if skills_dir else SkillIndex()
            from .app_events import AppSkillContext
            self.app_skill_context = AppSkillContext(self.skills)
            self.broker = PermissionBroker(store)
            self.router = ModelRouter()
            self.leases = LeaseManager()  # in-memory only: fail-closed on restart
            self.compactor = IdleCompactor(self.registry, store)

    def _assistant(self, request):
        """Versioned assistant IPC. All reads are read-only and bounded.

        These actions expose application context, tiered memory, staged skills
        and durable-task state to a Pi Durable adapter. None of them invoke a
        model; inference is a separate, explicitly-authorized decision."""
        if not self.assistant_enabled:
            raise PermissionError("Assistant features are disabled")
        action = request.get("action")
        _COUNTER = {
            "memory_remember": "memory_remember", "memory_recall": "memory_recall",
            "memory_promote": "memory_promote", "skill_discover": "skill_discover",
            "skill_load": "skill_load", "skill_propose": "skill_propose",
            "skill_approve": "skill_approve", "skill_retire": "skill_retire",
            "task_create": "task_create", "task_update": "task_update",
            "auth_create": "auth_create", "auth_check": "auth_check",
            "auth_expand": "auth_expand", "auth_revoke": "auth_revoke",
            "route": "route", "handoff": "handoff", "desktop_action": "desktop_actions",
            "lease_acquire": "lease_acquire",
        }
        if action in _COUNTER:
            self.telemetry.bump(_COUNTER[action])
        if action == "app_context":
            context = self.registry.context(role=request.get("role", "text"))
            context["active_skill"] = self.app_skill_context.snapshot()
            return context
        if action == "memory_remember":
            if set(request) - {"action", "scope", "key", "value", "task_id", "app_id", "project_id"}:
                raise ValueError("Invalid memory_remember request")
            return self.memory.remember(request["scope"], request["key"], request.get("value"),
                                        task_id=request.get("task_id"), app_id=request.get("app_id"),
                                        project_id=request.get("project_id"))
        if action == "memory_recall":
            if set(request) - {"action", "scope", "key", "limit", "task_id", "app_id", "project_id"}:
                raise ValueError("Invalid memory_recall request")
            return self.memory.recall(request["scope"], key=request.get("key"),
                                      limit=request.get("limit", 10), task_id=request.get("task_id"),
                                      app_id=request.get("app_id"), project_id=request.get("project_id"))
        if action == "skill_discover":
            app_ids = request.get("app_ids")
            if app_ids is None:
                app_ids = [self.registry.focused.app_id] if self.registry.focused else []
                app_ids += [p.app_id for p in self.registry.recent.values()]
            if not isinstance(app_ids, (list, tuple)) or len(app_ids) > 16:
                raise ValueError("app_ids must be a list of at most 16")
            return {"schema": "hyprneuro.skills/1", "manifests": self.skills.discover(app_ids)}
        if action == "skill_load":
            if set(request) - {"action", "app_id"}:
                raise ValueError("Invalid skill_load request")
            skill = self.skills.load(request.get("app_id", ""))
            if skill is None:
                raise LookupError("No skill for application")
            return skill
        if action == "skill_refresh":
            if set(request) != {"action"}:
                raise ValueError("Invalid skill_refresh request")
            return self.skills.refresh_directory()
        if action == "skill_list":
            return {"schema": "hyprneuro.skills/1", "app_ids": self.skills.app_ids()}
        if action == "skill_propose":
            if set(request) - {"action", "app_id", "name", "description", "instructions",
                               "tags", "source_task"}:
                raise ValueError("Invalid skill_propose request")
            return self.skills.propose(
                request.get("app_id", ""), name=request.get("name", ""),
                description=request.get("description", ""),
                instructions=request.get("instructions", ""),
                tags=request.get("tags") or (), source_task=request.get("source_task"))
        if action == "skill_approve":
            if set(request) - {"action", "app_id", "validated"}:
                raise ValueError("Invalid skill_approve request")
            return self.skills.approve(request.get("app_id", ""),
                                       validated=request.get("validated", False))
        if action == "skill_retire":
            if set(request) - {"action", "app_id"}:
                raise ValueError("Invalid skill_retire request")
            return self.skills.retire(request.get("app_id", ""))
        if action == "task_create":
            if set(request) - {"action", "goal", "scope", "state"}:
                raise ValueError("Invalid task_create request")
            return self.store.task_create(request["goal"], scope=request.get("scope", "task"),
                                          state=request.get("state"))
        if action == "task_update":
            if set(request) - {"action", "id", "status", "state"}:
                raise ValueError("Invalid task_update request")
            return self.store.task_update(request["id"], status=request.get("status"),
                                          state=request.get("state"))
        if action == "task_get":
            if set(request) - {"action", "id"}:
                raise ValueError("Invalid task_get request")
            return self.store.task_get(request.get("id"))
        if action == "task_list":
            if set(request) - {"action", "status", "limit"}:
                raise ValueError("Invalid task_list request")
            return self.store.task_list(status=request.get("status"), limit=request.get("limit", 20))
        if action == "auth_create":
            if set(request) - {"action", "task_id", "app_id", "file_prefix", "ops", "approved"}:
                raise ValueError("Invalid auth_create request")
            return self.broker.authorize(request["task_id"], app_id=request.get("app_id"),
                                         file_prefix=request.get("file_prefix"),
                                         ops=tuple(request.get("ops") or ("read", "write")),
                                         approved=request.get("approved", False))
        if action == "auth_check":
            if set(request) - {"action", "task_id", "op", "app_id", "path"}:
                raise ValueError("Invalid auth_check request")
            return self.broker.check(request["task_id"], request["op"],
                                     app_id=request.get("app_id"), path=request.get("path"))
        if action == "auth_expand":
            if set(request) - {"action", "task_id", "ops", "file_prefix", "app_id", "approved"}:
                raise ValueError("Invalid auth_expand request")
            return self.broker.expand(request["task_id"], ops=tuple(request.get("ops")) if request.get("ops") else None,
                                      file_prefix=request.get("file_prefix"), app_id=request.get("app_id"),
                                      approved=request.get("approved", False))
        if action == "auth_revoke":
            if set(request) - {"action", "task_id"}:
                raise ValueError("Invalid auth_revoke request")
            return self.broker.revoke(request["task_id"])
        if action == "auth_list":
            return {"schema": "hyprneuro.auth/1", "scopes": self.broker.list()}
        if action == "route":
            if set(request) - {"action", "task_kind", "has_multimodal", "needs_classification"}:
                raise ValueError("Invalid route request")
            role = self.router.route(request["task_kind"],
                                     has_multimodal=request.get("has_multimodal", False),
                                     needs_classification=request.get("needs_classification", False))
            return {"schema": "hyprneuro.route/1", "role": role,
                    "d1_invoked": role == "decision"}
        if action == "handoff":
            if set(request) - {"action", "from_role", "to_role", "payload"}:
                raise ValueError("Invalid handoff request")
            return self.router.handoff(request["from_role"], request["to_role"], request.get("payload") or {})
        if action == "lease_acquire":
            if set(request) - {"action", "task_id", "ttl_ms"}:
                raise ValueError("Invalid lease_acquire request")
            lease = self.leases.acquire(request["task_id"], ttl_ms=request.get("ttl_ms") or 10000)
            return {"schema": "hyprneuro.lease/1", **lease.compact()}
        if action == "lease_release":
            if set(request) - {"action", "task_id", "token"}:
                raise ValueError("Invalid lease_release request")
            return {"released": self.leases.release(request["task_id"], request["token"])}
        if action == "lease_renew":
            if set(request) - {"action", "task_id", "token", "ttl_ms"}:
                raise ValueError("Invalid lease_renew request")
            lease = self.leases.renew(request["task_id"], request["token"],
                                      ttl_ms=request.get("ttl_ms") or 10000)
            return {"schema": "hyprneuro.lease/1", **lease.compact()}
        if action == "lease_pause":
            if set(request) - {"action", "task_id", "token"}:
                raise ValueError("Invalid lease_pause request")
            return {"paused": self.leases.pause(request["task_id"], request["token"])}
        if action == "lease_resume":
            if set(request) - {"action", "task_id", "token"}:
                raise ValueError("Invalid lease_resume request")
            return {"resumed": self.leases.resume(request["task_id"], request["token"])}
        if action == "lease_status":
            lease = self.leases.active()
            return {"schema": "hyprneuro.lease/1", "active": lease.compact() if lease else None}
        if action == "lease_emergency_stop":
            return {"stopped": self.leases.force_release()}
        raise ValueError("Unknown assistant RPC action")

    def dispatch(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected JSON object")
        action = request.get("action")
        self.telemetry.bump("ipc_requests")
        if action == "telemetry":
            return self.telemetry.snapshot(self.store)
        if action == "health":
            state = {"service": "hyprneuro", "ingest_enabled": self.allow_ingest,
                     "capture_enabled": self.capture_enabled,
                     "on_demand_enabled": self.on_demand, "alert_enabled": self.alert_enabled,
                     "resources_enabled": self.resources_enabled}
            if not self.capture_enabled and not self.on_demand and not self.alert_enabled and not self.resources_enabled and self.embeddings is None:
                state["models_invoked"] = False  # No model path can run.
            state["browser_enabled"] = self.browser_ingress is not None
            state["assistant_enabled"] = self.assistant_enabled
            state["assistant_apps"] = (len(self.registry.recent) if self.registry else 0)
            state["journal"] = self.store.journal_status()
            state["active_settings"] = self.active_settings
            state["settings_file"] = self.settings_file
            state["collectors"] = {task.get_name(): ("running" if not task.done() else
                "stopped" if task.cancelled() else "failed" if task.exception() else "finished")
                for task in self.producers}
            state["network_monitor"] = self.event_intake.network_status if self.event_intake and self.active_settings.get("alert_network") else None
            state["resource_monitor"] = self.event_intake.resource_status if self.event_intake and self.active_settings.get("alert_resources") else None
            return state
        if action in ("ui_settings_get", "ui_settings_save"):
            # Only implemented UI preferences and explicit journal consent.
            # Saving never starts a collector, grants prerequisites, changes
            # model configuration or restarts a service.
            from dataclasses import replace
            from .settings import Settings
            if not self.settings_file:
                raise PermissionError("Settings storage disabled by this sidecar")
            saved = Settings.load(self.settings_file)
            editable = ("ui_transcript_size", "ui_autoscroll", "ui_panel_opacity", "alert_journal", "alert_network", "alert_resources")
            if action == "ui_settings_save":
                if set(request) != {"action", "expected", *editable}:
                    raise ValueError("Only implemented appearance and monitoring settings are editable")
                current = {name: getattr(saved, name) for name in editable}
                if request["expected"] != current:
                    raise ValueError("Settings changed on disk; Reload before saving")
                saved = replace(saved, **{name: request[name] for name in editable})
                saved.save(self.settings_file)
            result = {name: getattr(saved, name) for name in editable}
            for name in ("journal", "network", "resources"):
                task = next((t for t in self.producers if t.get_name() == name), None)
                result[name + "_active"] = bool(self.active_settings.get("alert_" + name))
                result[name + "_task"] = ("off" if task is None else "running" if not task.done() else
                    "stopped" if task.cancelled() else "failed" if task.exception() else "finished")
            return result
        if action == "record":
            if not self.allow_ingest:
                raise PermissionError("Sidecar ingest disabled; opt in explicitly")
            return self.store.record(request.get("event"))
        if action in ("search", "context"):
            args = {k: v for k, v in request.items()
                    if k in ("query", "start_ms", "end_ms", "source", "limit", "role", "order", "match", "offset")}
            if action == "search":
                args.pop("role", None)
                return self.store.search(**args)
            for key in ("limit", "order", "match", "offset"):
                args.pop(key, None)
            return self.store.context(**args)
        # Exact URL is a separate read-only lookup. Opening it is NOT an RPC
        # here; the browser opener must go through broker action approval.
        if action == "page_url":
            return self.store.page_url(request.get("id"))
        if action == "alerts":
            return self.store.alerts(limit=request.get("limit", 20), offset=request.get("offset", 0))
        if action == "details":
            return self.store.details(request.get("id"))
        if action in ("app_context", "memory_remember", "memory_recall",
                     "skill_discover", "skill_load", "skill_list", "skill_refresh",
                     "skill_propose", "skill_approve", "skill_retire",
                     "task_create", "task_update", "task_get", "task_list",
                     "auth_create", "auth_check", "auth_expand", "auth_revoke", "auth_list",
                     "route", "handoff",
                     "lease_acquire", "lease_release", "lease_renew", "lease_pause",
                     "lease_resume", "lease_status", "lease_emergency_stop"):
            if not self.assistant_enabled:
                raise PermissionError("Assistant features are disabled")
            return self._assistant(request)
        raise ValueError("Unknown sidecar RPC action")

    async def dispatch_async(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected JSON object")
        if request.get("action") == "search" and request.get("semantic"):
            if self.embeddings is None:
                raise PermissionError("Semantic search disabled; explicitly configure a local embeddings service")
            return await self.embeddings.search(self.store, request)
        if request.get("action") == "browser_record":
            if not self.allow_ingest or self.browser_ingress is None:
                raise PermissionError("Chrome ingestion disabled")
            result, candidate = self.browser_ingress.record(request)
            if candidate is not None and self.browser_capture_source is not None:
                await self.browser_capture_source.on_candidate(candidate)
            return result
        if request.get("action") == "verify_navigation":
            if set(request) != {"action", "id", "since_ms"}:
                raise ValueError("Invalid navigation verification request")
            return self.store.verify_navigation(request["id"], request["since_ms"])
        if request.get("action") == "desktop_action":
            if not self.assistant_enabled:
                raise PermissionError("Assistant features are disabled")
            if self.desktop_controller is None:
                raise PermissionError("Desktop control requires watch_hyprland")
            if set(request) - {"action", "task_id", "token", "op", "value", "expected_window"}:
                raise ValueError("Invalid desktop_action request")
            return await self.desktop_controller.perform(
                request["task_id"], request["token"], request["op"],
                request.get("value"), expected_window=request.get("expected_window"))
        if request.get("action") == "monitoring":
            limit = request.get("limit", 12)
            if not isinstance(limit, int) or not 1 <= limit <= 50:
                raise ValueError("limit must be 1..50")
            return await self._monitoring_snapshot(limit)
        if request.get("action") == "ui_status":
            return {"schema": "hyprneuro.ui_status/1", "pid": os.getpid(),
                    "assistant_enabled": self.assistant_enabled,
                    "models": await self._model_health()}
        if request.get("action") != "omni_observe":
            return self.dispatch(request)
        # The native Pi tool must show user approval for EVERY foreground
        # request. Sidecar also requires a separately enabled session flag.
        # The same-UID broker/socket is not a security boundary against a
        # malicious process running as the same user.
        if not self.on_demand or not self.allow_ingest or self.watcher is None:
            raise PermissionError("On-demand Omni observations are disabled")
        if set(request) != {"action", "purpose"}:
            raise ValueError("Invalid Omni observation request")
        purpose = request["purpose"]
        if purpose not in ("read_text", "describe", "both"):
            raise ValueError("Unknown Omni observation purpose")
        from .recall import CaptureCandidate
        result = await self.watcher.observe_requested(
            CaptureCandidate(source="hyprland", event="pi_request"))
        if not result.get("captured") or not result.get("id"):
            raise RuntimeError("Omni observation produced no record")
        row = self.store.observation(result["id"])
        # Give main Pi a SMALL, explicitly requested excerpt. Background
        # observations never inject text into the Pi session automatically.
        answer = {"id": result["id"], "untrusted": True,
                  "time_ms": row["time_ms"], "app_id": row["app_id"],
                  "title": row["title"], "source": "omni"}
        if purpose in ("read_text", "both"):
            answer["ocr_excerpt"] = row["ocr_text"][:800]
        if purpose in ("describe", "both"):
            answer["description"] = row["description"][:650]
        return answer

    async def _write_frame(self, writer, obj) -> None:
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        writer.write(data + b"\n")
        await writer.drain()

    async def _stream_agent_chat(self, writer, request) -> None:
        """Stream an agent_chat request: delta lines then a done line.

        Model-free framing; the LLM call is delegated to the agent module, which
        reuses the running LFM endpoints. Bounded inputs; no screenshots.
        """
        from . import agent
        from contextlib import aclosing
        message = str(request.get("message") or "")
        if not message.strip():
            await self._write_frame(writer, {"type": "error", "error": "Empty message"})
            return
        context = request.get("context") or {}
        system = agent.DEFAULT_SYSTEM
        if isinstance(context, dict) and context:
            # The server alone supplies the active skill; an app_context IPC
            # snapshot echoed by a client must not duplicate that prompt block.
            context = {k: v for k, v in context.items() if k != "active_skill"}
            system += "\n\nLocal context (untrusted, metadata only): " + json.dumps(context)[:2000]
        history = request.get("history") or []
        if not isinstance(history, list):
            history = []
        history = [{"role": ("user" if str(h.get("role", "user")) == "user" else "assistant"),
                    "content": str(h.get("content", ""))[:4000]}
                   for h in history[-20:] if isinstance(h, dict)]
        # Build the user message, including media if present.
        media = request.get("media")
        if media is not None:
            try:
                from .audio import MAX_AUDIO_BYTES, validate_wav
                if not isinstance(media, dict) or media.get("mime") not in ("image/png", "image/jpeg", "image/webp", "audio/wav"):
                    raise ValueError("Only reviewed static PNG/JPEG/WebP or bounded PCM16 WAV attachments are enabled")
                mime, b64 = media["mime"], media.get("data")
                limit = MAX_AUDIO_BYTES if mime == "audio/wav" else 5 * 1024 * 1024
                if not isinstance(b64, str) or not b64 or len(b64) > 4 * ((limit + 2) // 3):
                    raise ValueError("Invalid or oversized attachment")
                decoded = base64.b64decode(b64, validate=True)
                if mime == "audio/wav":
                    validate_wav(decoded)
                    part = {"type": "input_audio", "input_audio": {"data": b64, "format": "wav"}}
                else:
                    signatures = {"image/png": decoded.startswith(b"\x89PNG\r\n\x1a\n"),
                                  "image/jpeg": decoded.startswith(b"\xff\xd8\xff"),
                                  "image/webp": decoded[:4] == b"RIFF" and decoded[8:12] == b"WEBP"}
                    if not decoded or len(decoded) > limit or not signatures[mime]:
                        raise ValueError("Image bytes do not match the declared type or size limit")
                    part = {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}
            except (ValueError, binascii.Error) as exc:
                await self._write_frame(writer, {"type": "error", "error": str(exc)})
                return
            user_content = [{"type": "text", "text": message[:8000]}, part]
        else:
            user_content = message[:8000]
        # Read the prebuilt server snapshot once. No skill loads or disk I/O
        # on the prompt path, and never persist the block in chat history.
        skill_block = self.app_skill_context.prompt_block() if self.app_skill_context else ""
        messages = ([{"role": "system", "content": system[:4000] + skill_block}] + history +
                    [{"role": "user", "content": user_content}])
        role = "omni" if media is not None else "text"
        answer = []
        stream_bytes = 0
        metrics = {}
        try:
            async with aclosing(agent.stream_chat(
                    messages, role=role,
                    max_tokens=int(request.get("max_tokens") or 1024))) as stream:
                async for delta in stream:
                    if delta.get("type") == "metrics":
                        metrics = {k: v for k, v in delta.items() if k != "type"}
                        continue
                    stream_bytes += len(delta["text"].encode("utf-8"))
                    if stream_bytes > 1024 * 1024:
                        raise ValueError("Chat stream exceeds 1 MiB")
                    if delta["channel"] == "answer":
                        answer.append(delta["text"])
                    await self._write_frame(writer, delta)
            done = {"type": "done", "text": "".join(answer), "role": role}
            if metrics:
                done["metrics"] = metrics
            await self._write_frame(writer, done)
        except (OSError, EOFError, asyncio.TimeoutError, ValueError) as exc:
            await self._write_frame(writer, {"type": "error", "error": str(exc)[:300]})

    @staticmethod
    def _read_cpu_times() -> tuple[int, int]:
        with open("/proc/stat") as fh:
            parts = fh.readline().split()
        vals = [int(x) for x in parts[1:]]
        idle = vals[3] + (vals[4] if len(vals) > 4 else 0)
        return idle, sum(vals)

    async def _model_health(self) -> dict:
        from . import agent
        out = {}
        for role in ("text", "omni"):
            try:
                out[role] = await asyncio.wait_for(agent.health(role), 2)
            except (OSError, asyncio.TimeoutError):
                out[role] = False
        return out

    async def _monitoring_snapshot(self, limit: int) -> dict:
        """Bounded, model-free system + app monitoring snapshot for the UI."""
        # CPU over a short sample.
        cpu_pct = None
        try:
            idle0, total0 = self._read_cpu_times()
            import time as _t
            _t.sleep(0.1)
            idle1, total1 = self._read_cpu_times()
            d_total, d_idle = total1 - total0, idle1 - idle0
            if d_total > 0:
                cpu_pct = round(100.0 * (1.0 - d_idle / d_total), 1)
        except (OSError, ValueError):
            pass
        # RAM from /proc/meminfo.
        ram = None
        try:
            info = {}
            with open("/proc/meminfo") as fh:
                for line in fh:
                    key, _, rest = line.partition(":")
                    info[key.strip()] = int(rest.split()[0])  # kB
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            if total > 0:
                used = total - avail
                ram = {"total_mb": round(total / 1024), "used_mb": round(used / 1024),
                       "pct": round(100.0 * used / total, 1)}
        except (OSError, ValueError, IndexError):
            pass
        # App context (focused + recent) if the assistant layer is active.
        apps = None
        if self.registry is not None:
            try:
                ctx = self.registry.context(role="text")
                apps = {"focused": ctx.get("focused"), "recent": ctx.get("recent", [])[:5]}
            except (ValueError, AttributeError):
                apps = None
        # Recent monitoring observations (bounded, untrusted titles).
        recent = []
        try:
            recent = self.store.search(query="", limit=limit)
        except (OSError, ValueError, TypeError, AttributeError):
            recent = []
        return {"schema": "hyprneuro.monitoring/1", "ts_ms": int(__import__("time").time() * 1000),
                "cpu_pct": cpu_pct, "ram": ram, "apps": apps,
                "models": await self._model_health(),
                "recent_events": recent[:limit]}

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        try:
            try:
                sock = writer.get_extra_info("socket")
                _, uid, _ = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET,
                                                                socket.SO_PEERCRED, 12))
                if uid != os.getuid():
                    raise PermissionError("Wrong peer UID")
                raw = await asyncio.wait_for(reader.readline(), 10)
                if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST:
                    raise ValueError("Invalid or oversized RPC frame")
                request = json.loads(raw)
                if request.get("action") == "agent_chat":
                    await self._stream_agent_chat(writer, request)
                    return  # streaming path wrote its own frames
                response = {"ok": True, "result": await self.dispatch_async(request)}
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                response = {"ok": False, "error": str(exc)}
            try:
                data = json.dumps(response, ensure_ascii=False).encode("utf-8")
                if len(data) > MAX_RESPONSE:
                    data = b'{"ok":false,"error":"Response exceeds limit"}'
                writer.write(data + b"\n")
                await writer.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                self.handlers.discard(task)


async def serve(*, allow_ingest=False, watch_hyprland=False, allow_capture=False,
                allow_on_demand=False, d1_visual=False, allow_browser=False,
                alert=False, alert_journal=False, alert_network=False, alert_resources=False,
                notifications=None, explanation_enabled=False, retention_days=0,
                active_settings=None, settings_file=None,
                semantic_enabled=False, embeddings_url="", embeddings_model="", socket_path=None, db_path=None, shutdown=None,
                desktop=None, models=None, unlock_guard=None, grabber=None,
                excluded_apps=(), excluded_origins=(), browser_token_file=None,
                assistant_enabled=False, assistant_recent_apps=5, assistant_focus_debounce_ms=250,
                skills_dir=None):
    alert_journal = alert or alert_journal
    alert_network = alert or alert_network
    notifications = bool(alert) if notifications is None else notifications
    if not math.isfinite(retention_days) or retention_days < 0:
        raise ValueError("retention_days must be finite and nonnegative")
    if watch_hyprland and not allow_ingest:
        raise ValueError("--watch-hyprland requires explicit --allow-ingest")
    if allow_capture and not (allow_ingest and watch_hyprland):
        raise ValueError("--allow-capture requires --allow-ingest and --watch-hyprland")
    if allow_on_demand and not allow_ingest:
        raise ValueError("--allow-on-demand requires --allow-ingest")
    if d1_visual and not allow_capture:
        raise ValueError("--d1-visual requires --allow-capture")
    if allow_browser and not allow_ingest:
        raise ValueError("--allow-browser requires --allow-ingest")
    if alert_resources and not allow_ingest:
        raise ValueError("--alert-resources requires explicit --allow-ingest")
    if (alert_journal or alert_network) and not allow_ingest:
        raise ValueError("--alert requires explicit --allow-ingest")
    socket_path = Path(socket_path) if socket_path else paths()[0]
    db_path = Path(db_path) if db_path else paths()[1]
    ensure_private(socket_path.parent)
    ensure_private(db_path.parent)
    if socket_path.is_symlink() or (socket_path.exists() and
                                    not stat.S_ISSOCK(socket_path.stat().st_mode)):
        raise RuntimeError("Refusing unsafe sidecar socket")
    if socket_path.exists():
        # A running socket must not be removed by a second instance.
        probe = socket.socket(socket.AF_UNIX)
        probe.settimeout(0.4)
        try:
            probe.connect(str(socket_path))
        except OSError:
            socket_path.unlink()
        else:
            raise RuntimeError("Sidecar already running")
        finally:
            probe.close()
    store = SidecarStore(db_path)
    worker = SidecarServer(store, allow_ingest=allow_ingest,
                           capture_enabled=allow_capture, on_demand=allow_on_demand,
                           alert_enabled=bool(alert_journal or alert_network), resources_enabled=alert_resources,
                           assistant_enabled=assistant_enabled, assistant_recent_apps=assistant_recent_apps,
                           assistant_focus_debounce_ms=assistant_focus_debounce_ms, skills_dir=skills_dir)
    from .settings import Settings
    worker.active_settings = active_settings or asdict(Settings(
        allow_ingest=allow_ingest, watch_hyprland=watch_hyprland, allow_capture=allow_capture,
        allow_on_demand=allow_on_demand, allow_browser=allow_browser, d1_visual=d1_visual,
        alert_journal=alert_journal, alert_network=alert_network, alert_resources=alert_resources,
        notifications=notifications, explanation_enabled=explanation_enabled,
        semantic_enabled=semantic_enabled, embeddings_url=embeddings_url, embeddings_model=embeddings_model,
        retention_enabled=retention_days > 0, retention_days=retention_days,
        excluded_apps=tuple(excluded_apps), excluded_origins=tuple(excluded_origins)))
    worker.settings_file = str(settings_file) if settings_file else None
    server = None
    producers = []
    worker.producers = producers
    source = None
    model_scheduler = None
    browser_token_file = Path(browser_token_file) if browser_token_file else None
    try:
        if semantic_enabled:
            from .semantic import Embeddings
            worker.embeddings = Embeddings(embeddings_url, embeddings_model)
            await worker.embeddings.embed(["Hyprneuro endpoint verification"])
        server = await asyncio.start_unix_server(worker.handle, path=str(socket_path), limit=MAX_REQUEST+1)
        socket_path.chmod(0o600)
        if allow_browser:
            from .browser_ingest import BrowserIngress, create_token, token_path
            if browser_token_file is None:
                browser_token_file = token_path()
            if browser_token_file.parent != socket_path.parent:
                # A test may supply another private runtime path. Production
                # always places the token next to the protected socket.
                ensure_private(browser_token_file.parent)
            token = create_token(browser_token_file)
            worker.browser_ingress = BrowserIngress(store, token=token,
                                                      excluded_origins=excluded_origins)
        if allow_capture or allow_on_demand:
            from .recall import (CapturePolicy, LoginSessionGuard, ScreenWatcher,
                                 DEFAULT_EXCLUDED_APPS)
            from .model_dispatch import ScheduledModels
            if desktop is None:
                from .desktop import Hyprland
                desktop = Hyprland()
            if models is None:
                from .config import Config
                from .models import Models
                models = Models(Config.load())
            model_scheduler = ScheduledModels(models)
            guard = unlock_guard or LoginSessionGuard().unlocked
            apps = DEFAULT_EXCLUDED_APPS | frozenset(str(app).lower() for app in excluded_apps)
            policy = CapturePolicy(enabled=True, check_unlocked=guard,
                                   excluded_app_ids=apps, visual_d1=d1_visual)
            worker.watcher = ScreenWatcher(desktop, model_scheduler, store, policy, grabber)
        if watch_hyprland:
            from .sidecar_sources import HyprlandSource
            if desktop is None:
                from .desktop import Hyprland
                desktop = Hyprland()
            source = HyprlandSource(store)
            from .app_events import SharedApplicationEvents
            shared_events = SharedApplicationEvents()
            worker.application_events = shared_events
            shared_events.subscribe(source.on_event)
            capture_source = None
            if allow_capture:
                from .recall_events import D1CaptureSource
                capture_source = D1CaptureSource(worker.watcher)
                worker.browser_capture_source = capture_source
                shared_events.subscribe(capture_source.on_event)
                producers.append(asyncio.create_task(capture_source.run(), name="capture"))

            app_watcher = None
            if assistant_enabled:
                from .application import AppWatcher
                from .desktop_control import DesktopController
                app_watcher = AppWatcher(desktop, worker.registry,
                                         min_resolve_interval_ms=0, context=worker.app_skill_context)
                worker.app_watcher = app_watcher
                worker.desktop_controller = DesktopController(desktop, worker.broker, worker.leases)
                # Seed the registry with the currently focused window so a
                # change-only event stream does not leave it empty at startup.
                # Seed before consuming queued changes, avoiding a stale seed
                # racing a later focus resolution.
                await app_watcher.initial_resolve()

                async def idle_compaction():
                    # Periodic, bounded: compacts only when idle, no-ops while active.
                    while True:
                        await asyncio.sleep(30)
                        try:
                            worker.compactor.compact(worker.telemetry)
                        except Exception:
                            pass

                producers.append(asyncio.create_task(idle_compaction(), name="idle_compaction"))

            if app_watcher is not None:
                async def focus_event(name, data):
                    await app_watcher.on_event(name, data)
                    worker.telemetry.bump("focus_events")

                shared_events.subscribe(focus_event, max_queue=1, coalesce_seconds=0.15,
                                        kinds={"activewindowv2"})
            producers.extend(asyncio.create_task(sub.run(), name=f"hyprland_subscriber_{i}")
                             for i, sub in enumerate(shared_events.subscribers))
            producers.extend([asyncio.create_task(source.flush(), name="hyprland_store"),
                              asyncio.create_task(shared_events.follow(desktop), name="hyprland")])
        if alert_journal or alert_network or alert_resources:
            from .event_stream import EventIntake
            from .escalation import EscalationRouter
            from .notify import Notifier
            if models is None:
                from .config import Config
                from .models import Models
                models = Models(Config.load())
            router = EscalationRouter(models, store, notifier=Notifier() if notifications else None,
                                      explanation_enabled=explanation_enabled)
            intake = EventIntake(store=store)
            worker.event_intake = intake
            if alert_journal:
                await router.recover()
                producers.append(asyncio.create_task(intake.follow_journal(router.escalate), name="journal"))
            if alert_network:
                producers.append(asyncio.create_task(intake.network_alerts(router.escalate), name="network"))
            if alert_resources:
                producers.append(asyncio.create_task(intake.resource_alerts(router.escalate), name="resources"))
        if retention_days > 0:
            producers.append(asyncio.create_task(run_retention(store, retention_days), name="retention"))
        stop = shutdown or asyncio.Event()
        if shutdown is None:
            loop = asyncio.get_running_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                try:
                    loop.add_signal_handler(sig, stop.set)
                except NotImplementedError:
                    pass
        await stop.wait()
    finally:
        if server:
            server.close()
        for worker_task in producers:
            worker_task.cancel()
        if producers:
            await asyncio.gather(*producers, return_exceptions=True)
        handlers = list(worker.handlers)
        for task in handlers:
            task.cancel()
        if handlers:
            await asyncio.gather(*handlers, return_exceptions=True)
        if server:
            await server.wait_closed()
        if model_scheduler:
            await model_scheduler.stop()
        socket_path.unlink(missing_ok=True)
        if allow_browser and browser_token_file is not None:
            browser_token_file.unlink(missing_ok=True)
        store.close()


def build_parser():
    parser = argparse.ArgumentParser(description="Hyprneuro observational sidecar")
    sub = parser.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("serve", help="Independent user-level JSONL/Unix service")
    cmd.add_argument("--config", help="Private Hyprneuro JSON settings (not legacy model TOML)")
    cmd.add_argument("--no-settings", action="store_true", help="Ignore saved feature settings; all defaults off")
    for name in ("allow_ingest", "watch_hyprland", "allow_capture", "allow_on_demand",
                 "allow_browser", "d1_visual", "alert_journal", "alert_network", "alert_resources",
                 "notifications", "semantic_enabled", "explanation_enabled", "retention_enabled",
                 "assistant_enabled"):
        cmd.add_argument("--" + name.replace("_", "-"), action=argparse.BooleanOptionalAction, default=None,
                         help="Explicit on/off override of saved " + name)
    cmd.add_argument("--assistant-recent-apps", type=int, default=None, dest="assistant_recent_apps",
                     help="LRU size for recent application context (1..16, default 5)")
    cmd.add_argument("--assistant-focus-debounce-ms", type=int, default=None, dest="assistant_focus_debounce_ms",
                     help="Focus debounce window in ms (0..5000, default 250)")
    cmd.add_argument("--skills-dir", default=None, dest="skills_dir",
                     help="Directory of JSON skill manifests for staged just-in-time skills")
    cmd.add_argument("--alert", action=argparse.BooleanOptionalAction, default=None,
                     help="Legacy shorthand: journal + network + notifications; granular flags override")
    cmd.add_argument("--exclude-origin", action="append", default=None, dest="excluded_origins")
    cmd.add_argument("--exclude-app", action="append", default=None, dest="excluded_apps")
    cmd.add_argument("--retention-days", type=float, default=None, metavar="DAYS",
                     help="Explicit deletion window (0 disables); overrides saved retention toggle unless specified")
    cmd.add_argument("--embeddings-url", default=None)
    cmd.add_argument("--embeddings-model", default=None)
    tui = sub.add_parser("tui", help="Manual curses history/search/alerts/status/settings UI")
    tui.add_argument("--config", help="Private Hyprneuro settings path")
    sub.add_parser("health")
    search = sub.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--start-ms", type=int)
    search.add_argument("--end-ms", type=int)
    search.add_argument("--source")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--order", choices=("recent", "relevance"), default="recent")
    search.add_argument("--match", choices=("terms", "phrase", "prefix", "fuzzy"), default="terms")
    search.add_argument("--semantic", action="store_true")
    context = sub.add_parser("context")
    context.add_argument("role", choices=("text", "omni"))
    context.add_argument("--query", default="")
    context.add_argument("--start-ms", type=int)
    context.add_argument("--end-ms", type=int)
    context.add_argument("--source")
    ui = sub.add_parser("ui", help="Control the Hyprneuro overlay (toggle/show/hide)")
    ui.add_argument("ui_command", choices=("toggle", "show", "hide"))
    ui.add_argument("--socket", default=None, help="UI control socket path")
    return parser


def resolve_settings(args):
    from .settings import Settings
    saved = Settings() if args.no_settings else Settings.load(args.config)
    values = asdict(saved)
    for field in fields(Settings):
        value = getattr(args, field.name, None)
        if value is not None:
            values[field.name] = value
    if args.alert is not None:
        for name in ("alert_journal", "alert_network", "notifications"):
            if getattr(args, name) is None:
                values[name] = args.alert
    if args.retention_days is not None and args.retention_enabled is None:
        values["retention_enabled"] = args.retention_days > 0
    return Settings(**values).validate(prerequisites=True)


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "tui":
        from .tui import run
        run(config_path=args.config)
        return
    if args.command == "serve":
        try:
            settings = resolve_settings(args)
        except (ValueError, OSError) as exc:
            parser.error(str(exc))
        values = asdict(settings)
        active = values.copy()
        values.pop("retention_enabled")
        values.pop("ui_transcript_size")  # Applied by GTK, not collector flags.
        values.pop("ui_autoscroll")
        values.pop("ui_panel_opacity")
        if not settings.retention_enabled:
            values["retention_days"] = 0
        from .settings import settings_path
        asyncio.run(serve(**values, active_settings=active,
                          skills_dir=args.skills_dir,
                          settings_file=None if args.no_settings else args.config or settings_path()))
        return
    if args.command == "ui":
        import socket as _socket
        path = args.socket or os.path.join(
            os.environ.get("XDG_RUNTIME_DIR", ""), "hyprneuro", "ui.sock")
        if not os.path.exists(path):
            print(json.dumps({"ok": False,
                "error": f"UI control socket not found at {path} (is the overlay running?)"}))
            return
        sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        try:
            sock.connect(path)
            sock.sendall((args.ui_command + "\n").encode())
            sock.close()
            print(json.dumps({"ok": True, "result": args.ui_command}))
        except OSError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
        return
    from .sidecar_client import request
    query = vars(args).copy()
    query.pop("command")
    query["action"] = args.command
    print(json.dumps(asyncio.run(request(query)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
