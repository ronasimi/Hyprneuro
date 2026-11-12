"""Application-aware context backbone for the Hyprneuro assistant.

This module is deliberately model-free: tracking the focused window and a
small LRU of recent applications performs NO LLM inference. It turns raw
compositor window metadata into a compact, versioned context block that a
durable task can consume, plus a tiered memory and a staged skill index.

Design goals (see docs/ARCHITECTURE.md):
  * Event-driven focus tracking with debouncing, never speculative inference.
  * Focused + recent (LRU) applications, metadata kept out of model context.
  * Staged skills plus approved active-app snapshots (app_events): compact
    discovery and bounded body/schema caching without per-prompt reloads.
  * Tiered durable memory: task / app / project / global, with explicit,
    approval-gated cross-scope promotion.

Nothing here captures screenshots or reads sensitive content.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

# --- Validation helpers (mirror the strictness of sidecar_store) ------------

_APP_ID = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,119}\Z")
_SCOPE = re.compile(r"[a-z][a-z0-9_]{0,63}\Z")
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
SCOPES = frozenset({"task", "app", "project", "global"})


def _now_ms() -> int:
    return int(time.time() * 1000)


def _b64(value: str, limit: int) -> str:
    return value[:limit]


def normalize_app_id(class_name: str) -> str:
    """Map a compositor window class to a stable, lowercase application id.

    Hyprland classes are X11-style (e.g. "google-chrome", "thunar"). We strip
    a leading single character for legacy single-letter WM_CLASS prefixes and
    lowercase for stable LRU keys. Never fabricate an id from a title.
    """
    if not isinstance(class_name, str) or not class_name:
        raise ValueError("Window class is required for application identity")
    raw = class_name.strip().lower()
    if not raw:
        raise ValueError("Window class is empty")
    # A leading single uppercase letter is a common WM_CLASS instance prefix.
    # Keep it (it is part of the identity); only normalize case.
    if len(raw) > 1 and raw[0].isupper():
        raw = raw[0].lower() + raw[1:]
    if not _APP_ID.fullmatch(raw):
        raise ValueError("Window class is not a safe application id")
    return raw


# --- Application profile + registry -----------------------------------------

@dataclass
class AppProfile:
    """Bounded metadata for one known application. No content, no screenshots."""
    app_id: str
    app_class: str
    title: str = ""
    workspace: str = ""
    address: str = ""
    pid: int | None = None
    first_seen_ms: int = 0
    last_focus_ms: int = 0
    focus_count: int = 0

    def compact(self) -> dict:
        """Small, stable block for model context (no full title secrets)."""
        return {
            "app_id": self.app_id,
            "app_class": self.app_class,
            "title": _b64(self.title, 80),
            "workspace": _b64(self.workspace, 32),
            "last_focus_ms": self.last_focus_ms,
            "focus_count": self.focus_count,
        }


class AppRegistry:
    """Focused application plus a bounded LRU of recent applications.

    `on_focus` is the ONLY entry point for compositor events. It is
    synchronous, allocation-cheap, and performs no model calls. Rapid focus
    churn within `debounce_ms` for the same window address only refreshes the
    timestamp; it does not re-key the LRU or emit work.
    """

    def __init__(self, *, max_recent: int = 5, debounce_ms: int = 250):
        if not 1 <= max_recent <= 16:
            raise ValueError("max_recent must be 1..16")
        if not 0 <= debounce_ms <= 5000:
            raise ValueError("debounce_ms must be 0..5000")
        self.max_recent = max_recent
        self.debounce_ms = debounce_ms
        self.focused: AppProfile | None = None
        self.recent: OrderedDict[str, AppProfile] = OrderedDict()
        self._last_address: str = ""
        self._last_change_ms: int = 0

    @staticmethod
    def _window_fields(window: dict) -> tuple[str, str, str, str, int | None]:
        if not isinstance(window, dict):
            raise ValueError("Window must be an object")
        address = str(window.get("address") or "")
        cls = str(window.get("class") or "")
        if not address or not cls:
            raise ValueError("Window must carry address and class")
        title = str(window.get("title") or "")
        workspace = str((window.get("workspace") or {}).get("id", ""))
        pid = window.get("pid")
        pid = pid if type(pid) is int and pid > 0 else None
        return address, cls, title[:300], workspace[:32], pid

    def on_focus(self, window: dict, now_ms: int | None = None) -> dict:
        """Update focused + LRU from one compositor window. Returns a small
        change record; never raises on benign metadata, only on bad shape."""
        now_ms = _now_ms() if now_ms is None else now_ms
        address, cls, title, workspace, pid = self._window_fields(window)
        app_id = normalize_app_id(cls)
        current = self.focused
        same_window = (current is not None and current.address == address
                       and current.app_id == app_id)
        if same_window and (now_ms - self._last_change_ms) < self.debounce_ms:
            # Debounced: same window, rapid churn. Refresh only the timestamp.
            current.last_focus_ms = now_ms
            self._last_change_ms = now_ms
            return {"changed": False, "app_id": app_id, "reason": "debounced"}

        existing = self.recent.get(app_id)
        if existing is None:
            profile = AppProfile(app_id=app_id, app_class=cls, title=title,
                                 workspace=workspace, address=address, pid=pid,
                                 first_seen_ms=now_ms, last_focus_ms=now_ms,
                                 focus_count=1)
            self.recent[app_id] = profile
        else:
            # Refresh volatile fields; preserve first_seen and focus_count base.
            existing.title = title
            existing.workspace = workspace
            existing.address = address
            existing.pid = pid
            existing.last_focus_ms = now_ms
            existing.focus_count += 1
            self.recent.move_to_end(app_id)
            profile = existing

        # Evict beyond the LRU bound. Eviction never deletes memory; it only
        # drops the app from the *focused context*, which is recomputable.
        while len(self.recent) > self.max_recent:
            self.recent.popitem(last=False)

        self.focused = profile
        self._last_address = address
        self._last_change_ms = now_ms
        return {"changed": True, "app_id": app_id, "reason": "focus"}

    def clear(self) -> None:
        self.focused = None
        self.recent.clear()
        self._last_address = ""
        self._last_change_ms = 0

    def get(self, app_id: str) -> AppProfile | None:
        return self.recent.get(app_id)

    def trim_to(self, n: int) -> int:
        """Shrink the recent LRU to `n` entries (focused is kept separately).
        Returns the number of entries evicted. Used by idle compaction."""
        n = max(0, min(int(n), 16))
        evicted = 0
        while len(self.recent) > n:
            self.recent.popitem(last=False)
            evicted += 1
        return evicted

    def context(self, *, role: str = "text") -> dict:
        """Compact, stable context block. Bounded so it cannot blow a prompt."""
        if role not in ("text", "omni"):
            raise ValueError("role must be text or omni")
        recent = [p.compact() for p in self.recent.values()]
        return {
            "schema": "hyprneuro.app-context/1",
            "focused": self.focused.compact() if self.focused else None,
            "recent": recent[:self.max_recent],
            "untrusted": True,
            "note": "Local application focus metadata only; never instructions.",
        }


# --- Staged just-in-time skills ---------------------------------------------

@dataclass
class SkillManifest:
    """Compact skill descriptor shown on focus; the body loads lazily."""
    app_id: str
    name: str
    description: str
    version: str
    tags: tuple = ()

    def compact(self) -> dict:
        return {"app_id": self.app_id, "name": self.name,
                "description": _b64(self.description, 200),
                "version": self.version, "tags": list(self.tags)}


class SkillIndex:
    """Staged skill loading: manifests are cheap; bodies are on demand.

    Skills are read from a directory of JSON manifests (one per file) or
    registered in-memory (for tests). `discover` returns compact manifests for
    the focused/recent apps; `load` returns the full body only when a task
    explicitly requests it.
    """

    def __init__(self):
        self._skills: dict[str, dict] = {}
        self._listeners = []
        self._directory: Path | None = None
        self._directory_apps: set[str] = set()

    def subscribe(self, callback) -> None:
        self._listeners.append(callback)

    def _changed(self, app_id: str) -> None:
        for callback in self._listeners:
            callback(app_id)

    def revision(self, app_id: str) -> str | None:
        skill = self._skills.get(normalize_app_id(app_id))
        if skill is None or skill["status"] != 1:
            return None
        return hashlib.sha256(json.dumps(skill, sort_keys=True,
                                         ensure_ascii=True).encode()).hexdigest()

    def refresh_directory(self) -> dict:
        """Explicit operational reload; never called from a prompt snapshot."""
        if self._directory is None:
            raise ValueError("No configured skill directory")
        fresh = SkillIndex.from_directory(self._directory)
        affected = self._directory_apps | set(fresh._skills)
        for aid in affected:
            old = self._skills.get(aid)
            new = fresh._skills.get(aid)
            if old == new:
                continue
            if new is None:
                self._skills.pop(aid, None)
            else:
                self._skills[aid] = new
            self._changed(aid)
        self._directory_apps = set(fresh._skills)
        return {"refreshed": True, "app_ids": sorted(self._directory_apps)}

    @classmethod
    def from_directory(cls, path: str | Path) -> "SkillIndex":
        index = cls()
        root = Path(path)
        index._directory = root
        if not root.exists():
            return index
        if root.is_file():
            index._load_file(root)
            index._directory_apps = set(index._skills)
            return index
        for entry in sorted(root.glob("*.json")):
            index._load_file(entry)
        index._directory_apps = set(index._skills)
        return index

    def _load_file(self, entry: Path) -> None:
        try:
            if entry.is_symlink() or entry.stat().st_size > 262_144:
                return
            data = json.loads(entry.read_text())
            if isinstance(data, dict):
                self.register(data)
        except (OSError, ValueError, TypeError, RecursionError):
            return

    def register(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise ValueError("Skill manifest must be an object")
        app_id = normalize_app_id(str(data.get("app_id") or ""))
        previous = self._skills.get(app_id)
        try:
            self._register(app_id, data)
        except (ValueError, TypeError, RecursionError):
            self._skills.pop(app_id, None)
            self._changed(app_id)
            raise
        if self._skills[app_id] != previous:
            self._changed(app_id)

    def _register(self, app_id: str, data: dict) -> None:
        status = data.get("status", 1)  # bundled curated seeds stay compatible
        if type(status) is not int or status not in (0, 1, 2):
            raise ValueError("Invalid skill status")
        for key in ("name", "description", "version", "body", "instructions"):
            if key in data and not isinstance(data[key], str):
                raise ValueError("Skill text must be a string")
        if not isinstance(data.get("tags", []), (list, tuple)):
            raise ValueError("Skill tags must be a list")
        name = _b64(str(data.get("name") or app_id), 80)
        description = _b64(str(data.get("description") or ""), 400)
        version = _b64(str(data.get("version") or "0"), 32)
        tags = tuple(_b64(str(t), 40) for t in (data.get("tags") or [])[:16])
        body = str(data.get("body") or data.get("instructions") or "")
        schema = data.get("tools_schema")
        if schema is not None:
            if not isinstance(schema, (dict, list)):
                raise ValueError("Invalid tools schema")
            encoded = json.dumps(schema, allow_nan=False)
            if len(encoded) > 4096:
                raise ValueError("Skill tools schema exceeds 4096 characters")
            schema = json.loads(encoded)
        self._skills[app_id] = {
            "app_id": app_id, "name": name, "description": description,
            "version": version, "tags": tags, "body": body[:8192], "tools_schema": schema,
            "status": status,
        }

    # --- Progressive lifecycle: draft -> approved -> retired ----------------
    # A generated skill starts as a DRAFT (status 0): it is neither discovered
    # nor loadable. It becomes APPROVED (status 1) only after validation +
    # approval. RETIRED (status 2) skills are inert.

    def propose(self, app_id: str, *, name: str = "", description: str = "",
                instructions: str = "", tags: Iterable[str] = (),
                source_task: str | None = None) -> dict:
        """Create a DRAFT skill from a completed task. Not discoverable yet."""
        aid = normalize_app_id(str(app_id))
        if not aid:
            raise ValueError("Invalid app_id")
        self._skills[aid] = {
            "app_id": aid,
            "name": _b64(name or aid, 80),
            "description": _b64(description, 400),
            "version": "0", "tags": tuple(_b64(str(t), 40) for t in list(tags)[:16]),
            "body": str(instructions)[:8192], "tools_schema": None,
            "status": 0,
            "source_task": _b64(source_task or "", 80),
        }
        self._changed(aid)
        return {"app_id": aid, "status": 0}

    def approve(self, app_id: str, *, validated: bool = False) -> dict:
        """Approve a DRAFT skill (requires validation) so it is discoverable."""
        aid = normalize_app_id(str(app_id))
        skill = self._skills.get(aid)
        if skill is None:
            raise KeyError("Unknown skill")
        if validated is not True:
            raise PermissionError("Skill approval requires validation")
        if skill["status"] != 1:
            skill["status"] = 1
            self._changed(aid)
        return {"app_id": aid, "status": 1}

    def retire(self, app_id: str) -> dict:
        aid = normalize_app_id(str(app_id))
        skill = self._skills.get(aid)
        if skill is None:
            raise KeyError("Unknown skill")
        skill["status"] = 2
        self._changed(aid)
        return {"app_id": aid, "status": 2}

    def status_of(self, app_id: str) -> int | None:
        skill = self._skills.get(normalize_app_id(str(app_id)))
        return skill["status"] if skill else None

    def discover(self, app_ids: Iterable[str]) -> list[dict]:
        """Compact manifests for APPROVED skills, in order, deduped."""
        out, seen = [], set()
        for raw in app_ids:
            app_id = normalize_app_id(str(raw))
            if app_id in seen:
                continue
            seen.add(app_id)
            skill = self._skills.get(app_id)
            if skill and skill["status"] == 1:
                out.append(SkillManifest(
                    app_id=skill["app_id"], name=skill["name"],
                    description=skill["description"], version=skill["version"],
                    tags=skill["tags"]).compact())
        return out

    def load(self, app_id: str) -> dict | None:
        """Full skill (manifest + body + schema). Only APPROVED skills load."""
        skill = self._skills.get(normalize_app_id(str(app_id)))
        if skill is None or skill["status"] != 1:
            return None
        return copy.deepcopy({"schema": "hyprneuro.skill/1", **skill})

    def has(self, app_id: str) -> bool:
        return normalize_app_id(str(app_id)) in self._skills

    def app_ids(self) -> list[str]:
        return sorted(self._skills)


# --- Tiered durable memory --------------------------------------------------

@dataclass
class MemoryRecord:
    scope: str
    key: str
    value: Any
    task_id: str | None = None
    app_id: str | None = None
    project_id: str | None = None
    updated_ms: int = 0


def _validate_scope_key(scope: str, key: str) -> None:
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {sorted(SCOPES)}")
    if not _KEY.fullmatch(str(key)):
        raise ValueError("Invalid memory key")


class TieredMemory:
    """Task / app / project / global scoped memory with approval-gated promote.

    Backends: an in-memory dict (default, for unit tests) or a SidecarStore
    (for the IPC service). The public API is identical for both.
    """

    def __init__(self, store: Any | None = None):
        self._store = store
        self._mem: dict[str, dict[str, dict]] = {s: {} for s in SCOPES}

    # -- write --
    def remember(self, scope: str, key: str, value: Any, *,
                 task_id: str | None = None, app_id: str | None = None,
                 project_id: str | None = None) -> dict:
        _validate_scope_key(scope, key)
        encoded = json.dumps(value, ensure_ascii=False, default=str)
        if len(encoded) > 16_384:
            raise ValueError("Memory value exceeds 16 KiB")
        when = _now_ms()
        if self._store is not None:
            return self._store.app_memory_remember(scope, key, encoded,
                                                   task_id=task_id, app_id=app_id,
                                                   project_id=project_id)
        self._mem[scope][key] = {
            "value": value, "task_id": task_id, "app_id": app_id,
            "project_id": project_id, "updated_ms": when,
        }
        return {"stored": True, "scope": scope, "key": key, "updated_ms": when}

    # -- read --
    def recall(self, scope: str, *, key: str | None = None, limit: int = 10,
               task_id: str | None = None, app_id: str | None = None,
               project_id: str | None = None) -> list[dict]:
        if scope not in SCOPES:
            raise ValueError(f"scope must be one of {sorted(SCOPES)}")
        if not 1 <= limit <= 50:
            raise ValueError("limit must be 1..50")
        if self._store is not None:
            rows = self._store.app_memory_recall(scope, key=key, limit=limit,
                                                 task_id=task_id, app_id=app_id,
                                                 project_id=project_id)
            return rows
        bucket = self._mem[scope]
        out = []
        for k, rec in bucket.items():
            if key is not None and k != key:
                continue
            if app_id is not None and rec.get("app_id") != app_id:
                continue
            if task_id is not None and rec.get("task_id") != task_id:
                continue
            if project_id is not None and rec.get("project_id") != project_id:
                continue
            out.append({"scope": scope, "key": k, "value": rec["value"],
                        "updated_ms": rec["updated_ms"]})
        out.sort(key=lambda r: r["updated_ms"], reverse=True)
        return out[:limit]

    def get(self, scope: str, key: str) -> Any | None:
        rows = self.recall(scope, key=key, limit=1)
        return rows[0]["value"] if rows else None

    # -- promotion --
    def promote(self, key: str, from_scope: str, to_scope: str, *, approved: bool) -> dict:
        """Cross-scope promotion ALWAYS requires explicit approval.

        `approved` must be a literal True supplied by the caller after a human
        decision; the memory layer itself never grants promotion.
        """
        if type(approved) is not bool:
            raise ValueError("promotion requires an explicit boolean approval")
        _validate_scope_key(from_scope, key)
        _validate_scope_key(to_scope, key)
        if from_scope == to_scope:
            raise ValueError("from_scope and to_scope must differ")
        value = self.get(from_scope, key)
        if value is None:
            raise LookupError(f"No record {key!r} in {from_scope}")
        if not approved:
            return {"promoted": False, "reason": "not_approved"}
        return self.remember(to_scope, key, value)


# --- Event-driven focus watcher ---------------------------------------------

class AppWatcher:
    """Resolve compositor focus events into registry updates. NO LLM inference.

    On an `activewindowv2` event it performs one bounded `activewindow` query
    to obtain the focused window's class/title/workspace, then updates the
    registry. Rapid churn is coalesced to at most one resolve per debounce
    window. The service runs this watcher on its own latest-wins subscriber
    worker (interval=0 there); no query runs in the socket2 reader callback.

    This is deliberately separate from ScreenWatcher: it never captures
    screenshots and never calls d1/Omni. It only tracks identity.
    """

    def __init__(self, desktop, registry, *, min_resolve_interval_ms=150, context=None):
        self.desktop = desktop
        self.registry = registry
        self.skill_context = context
        if not 0 <= min_resolve_interval_ms <= 5000:
            raise ValueError("min_resolve_interval_ms must be 0..5000")
        self._min_resolve_interval = min_resolve_interval_ms / 1000.0
        self._last_resolve = 0.0
        self.resolves = 0
        self.errors = 0

    async def initial_resolve(self) -> None:
        """Seed the registry with the currently focused window at startup.

        A change-only event stream leaves the registry empty if the focused app
        was already active when the sidecar started; resolve once to seed it.
        """
        try:
            window = await self.desktop.query("activewindow")
        except (OSError, ValueError, RuntimeError):
            self.errors += 1
            if self.skill_context is not None:
                self.skill_context.clear()
            self.registry.focused = None
            return
        if not isinstance(window, dict) or not window.get("address"):
            if self.skill_context is not None:
                self.skill_context.clear()
            self.registry.focused = None
            return
        try:
            self.registry.on_focus(window)
            if self.skill_context is not None:
                self.skill_context.activate(self.registry.focused.app_id)
            self.resolves += 1
        except (ValueError, KeyError, TypeError, AttributeError):
            self.errors += 1
            if self.skill_context is not None:
                self.skill_context.clear()
            self.registry.focused = None

    async def on_event(self, name: str, data: str) -> None:
        """Called from the compositor event loop. Never raises to the caller."""
        if name != "activewindowv2":
            return
        now = time.monotonic()
        if now - self._last_resolve < self._min_resolve_interval:
            return
        self._last_resolve = now
        await self.initial_resolve()
