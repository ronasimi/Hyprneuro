"""Task-scoped autonomy: a versioned permission broker.

Authorizes a defined task / application / file scope. Ordinary,
non-privileged operations within scope are permitted; privileged operations
(desktop control, network, scope expansion, root, deletion, external
submissions) ALWAYS require an explicit, recorded human approval.

The broker is state and policy only — it performs no actions and grants no
desktop lease by itself. A desktop-control lease (Phase 5) is a separate,
higher-assurance mechanism that must also be satisfied before GUI automation.

Rules (see docs/ARCHITECTURE.md, section "Task-scoped autonomy"):
  * A scope is created per task with a bounded set of allowed operations.
  * `check` denies unless the scope is active, the operation is allowed, the
    app/path constraints match, and (for privileged ops) the scope was created
    with an explicit approval.
  * Scope expansion is itself a privileged operation and requires approval.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

# Operations that are ordinary and may run without a recorded approval, as long
# as they stay inside the authorized scope.
NORMAL_OPS = frozenset({"read", "write", "execute"})
# Operations that always require an explicit, recorded human approval.
PRIVILEGED_OPS = frozenset({
    "desktop_control", "network", "scope_expand", "root", "delete",
    "submit_external", "install_skill", "promote_memory",
})
ALL_OPS = NORMAL_OPS | PRIVILEGED_OPS

_SCOPES_STATUS = frozenset({"active", "revoked"})


def _now_ms() -> int:
    return int(time.time() * 1000)


def _check_id(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"Invalid {name}")
    if any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError(f"{name} contains control characters")
    return value


def _check_file_prefix(value: str | None) -> str | None:
    prefix = _check_id(value, "file_prefix")
    if prefix is not None:
        # A scope file prefix must be an absolute path with no traversal that
        # escapes it. We normalize to a single leading slash form.
        if not prefix.startswith("/"):
            raise ValueError("file_prefix must be an absolute path")
        if ".." in prefix.split("/"):
            raise ValueError("file_prefix must not contain path traversal")
    return prefix


@dataclass
class AuthorizationScope:
    task_id: str
    app_id: str | None = None
    file_prefix: str | None = None
    ops: frozenset = frozenset(NORMAL_OPS)
    status: str = "active"
    approved: bool = False
    created_ms: int = 0

    def compact(self) -> dict:
        return {"task_id": self.task_id, "app_id": self.app_id,
                "file_prefix": self.file_prefix, "ops": sorted(self.ops),
                "status": self.status, "approved": self.approved}


class PermissionBroker:
    """In-memory (or store-backed) authorization policy for durable tasks.

    The public API is identical for both backends so unit tests can run
    in-memory while the service uses the store.
    """

    def __init__(self, store: Any | None = None):
        self._store = store
        self._scopes: dict[str, AuthorizationScope] = {}

    # -- creation --
    def authorize(self, task_id: str, *, app_id: str | None = None,
                  file_prefix: str | None = None, ops: tuple = NORMAL_OPS,
                  approved: bool = False) -> dict:
        task_id = _check_id(task_id, "task_id")
        if not task_id:
            raise ValueError("task_id is required")
        app_id = _check_id(app_id, "app_id")
        file_prefix = _check_file_prefix(file_prefix)
        if not isinstance(ops, (tuple, list, frozenset, set)) or not ops:
            raise ValueError("ops must be a non-empty set of operations")
        opset = frozenset(ops)
        unknown = opset - ALL_OPS
        if unknown:
            raise ValueError(f"Unknown operations: {sorted(unknown)}")
        if type(approved) is not bool:
            raise ValueError("approved must be a boolean")
        # Privileged ops can only be granted with an explicit approval.
        if opset & PRIVILEGED_OPS and not approved:
            raise PermissionError(
                "Privileged operations require explicit approval: "
                + ", ".join(sorted(opset & PRIVILEGED_OPS)))
        when = _now_ms()
        scope = AuthorizationScope(task_id=task_id, app_id=app_id,
                                   file_prefix=file_prefix, ops=opset,
                                   status="active", approved=approved,
                                   created_ms=when)
        if self._store is not None:
            return self._store.auth_upsert(scope.compact())
        self._scopes[task_id] = scope
        return {"authorized": True, **scope.compact()}

    # -- lookup --
    def _get(self, task_id: str) -> AuthorizationScope | None:
        if self._store is not None:
            row = self._store.auth_get(task_id)
            if row is None:
                return None
            return AuthorizationScope(
                task_id=row["task_id"], app_id=row.get("app_id"),
                file_prefix=row.get("file_prefix"),
                ops=frozenset(row.get("ops") or []),
                status=row.get("status", "active"),
                approved=bool(row.get("approved")),
                created_ms=row.get("created_ms", 0))
        return self._scopes.get(task_id)

    # -- check --
    def check(self, task_id: str, op: str, *, app_id: str | None = None,
              path: str | None = None) -> dict:
        """Decide whether one operation is permitted for a task scope.

        Returns {allowed, reason}. Never raises on a policy denial — denials
        are data, so callers can log and continue.
        """
        if op not in ALL_OPS:
            raise ValueError(f"Unknown operation: {op}")
        scope = self._get(task_id)
        if scope is None:
            return {"allowed": False, "reason": "no_authorization"}
        if scope.status != "active":
            return {"allowed": False, "reason": "scope_revoked"}
        if op not in scope.ops:
            return {"allowed": False, "reason": "operation_not_authorized"}
        if op in PRIVILEGED_OPS and not scope.approved:
            return {"allowed": False, "reason": "requires_approval"}
        # Application constraint: if the scope is bound to an app, the
        # operation must target that app.
        if scope.app_id is not None and app_id is not None and app_id != scope.app_id:
            return {"allowed": False, "reason": "app_out_of_scope"}
        # File constraint: if the scope is bound to a prefix, the path must be
        # inside it (prefix match on the normalized path).
        if scope.file_prefix is not None and path is not None:
            if not _path_within(scope.file_prefix, path):
                return {"allowed": False, "reason": "path_out_of_scope"}
        return {"allowed": True, "reason": "ok"}

    # -- expansion / revocation --
    def expand(self, task_id: str, *, ops: tuple | None = None,
               file_prefix: str | None = None, app_id: str | None = None,
               approved: bool) -> dict:
        """Widen a scope. Expansion is privileged and ALWAYS requires approval."""
        if type(approved) is not bool:
            raise ValueError("scope expansion requires an explicit boolean approval")
        scope = self._get(task_id)
        if scope is None:
            raise LookupError("No authorization scope for task")
        if not approved:
            return {"expanded": False, "reason": "not_approved"}
        new_ops = frozenset(ops) if ops else scope.ops
        if new_ops - ALL_OPS:
            raise ValueError(f"Unknown operations: {sorted(new_ops - ALL_OPS)}")
        new_prefix = _check_file_prefix(file_prefix) if file_prefix is not None else scope.file_prefix
        new_app = _check_id(app_id, "app_id") if app_id is not None else scope.app_id
        if self._store is not None:
            return self._store.auth_upsert({
                "task_id": task_id, "app_id": new_app, "file_prefix": new_prefix,
                "ops": sorted(new_ops), "status": "active", "approved": True,
                "created_ms": scope.created_ms})
        scope.ops = new_ops
        scope.file_prefix = new_prefix
        scope.app_id = new_app
        scope.approved = True
        return {"expanded": True, **scope.compact()}

    def revoke(self, task_id: str) -> dict:
        scope = self._get(task_id)
        if scope is None:
            raise LookupError("No authorization scope for task")
        if self._store is not None:
            return self._store.auth_revoke(task_id)
        scope.status = "revoked"
        return {"revoked": True, "task_id": task_id}

    def list(self) -> list[dict]:
        if self._store is not None:
            return self._store.auth_list()
        return [s.compact() for s in self._scopes.values()]


def _path_within(prefix: str, path: str) -> bool:
    """True if `path` is inside `prefix` (both absolute, no traversal)."""
    if not path.startswith("/"):
        return False
    if ".." in path.split("/"):
        return False
    prefix = prefix.rstrip("/")
    if prefix == "":
        return True
    return path == prefix or path.startswith(prefix + "/")
