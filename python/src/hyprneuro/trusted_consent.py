"""Private sidecar consent state; not a public RPC or a human-input transport.

The managed-launch/control verifier must call this only after authenticating its
private channel. Importing this module creates no capability, file or socket.
Journal replay is forensic validation, NEVER restoration of live authority.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import uuid
from dataclasses import dataclass

from .authorization import PermissionBroker
from .identity_session import IdentitySession


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class ConsentDenied(PermissionError):
    """Terminal human denial/expiry, not a transport or mutation result."""


class ConsentJournal:
    MAX_BYTES = 64 * 1024 * 1024
    MAX_RECORD = 4096
    MAX_RECORDS = 100000

    def __init__(self, path):
        self.path = Path(path)
        parent = self.path.parent
        info = parent.lstat()
        if (not self.path.is_absolute() or self.path != self.path.resolve()
                or not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise PermissionError("Private canonical consent directory required")
        self.fd = os.open(self.path, os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.broken = False
        self.records = self.size = 0
        self.previous = "0" * 64
        try:
            info = os.fstat(self.fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600
                    or info.st_size > self.MAX_BYTES):
                raise PermissionError("Unsafe consent journal")
            directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)  # journal directory entry must precede grants
            finally:
                os.close(directory)
            with os.fdopen(os.dup(self.fd), "rb") as stream:
                while raw := stream.readline(self.MAX_RECORD + 1):
                    if (len(raw) > self.MAX_RECORD or not raw.endswith(b"\n")
                            or self.records >= self.MAX_RECORDS):
                        raise ValueError("Consent journal bound/tail; manual review required")
                    record = json.loads(raw)
                    if (set(record) != {"seq", "previous", "event"}
                            or type(record["seq"]) is not int
                            or record["seq"] != self.records + 1
                            or record["previous"] != self.previous
                            or canonical(record).encode() + b"\n" != raw):
                        raise ValueError("Invalid consent journal chain")
                    self.records += 1
                    self.size += len(raw)
                    self.previous = hashlib.sha256(raw).hexdigest()
        except BaseException:
            os.close(self.fd)
            self.fd = None
            raise

    def append(self, event):
        if self.broken or self.fd is None:
            raise PermissionError("Consent audit unavailable")
        raw = (canonical({"seq": self.records + 1, "previous": self.previous,
                          "event": event}) + "\n").encode()
        if (len(raw) > self.MAX_RECORD or self.size + len(raw) > self.MAX_BYTES
                or self.records >= self.MAX_RECORDS):
            self.broken = True
            raise PermissionError("Consent audit bound; manual review required")
        try:
            remaining = memoryview(raw)
            while remaining:
                count = os.write(self.fd, remaining)
                if count <= 0:
                    raise OSError("Incomplete consent audit write")
                remaining = remaining[count:]
            os.fsync(self.fd)
        except BaseException:
            self.broken = True
            raise
        self.records += 1
        self.size += len(raw)
        self.previous = hashlib.sha256(raw).hexdigest()

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


@dataclass
class Registration:
    binding: dict
    live: bool = True
    verification: IdentitySession | None = None


@dataclass(frozen=True)
class Pending:
    registration: str
    kind: str
    scope_json: str
    body_hash: str
    nonce: str
    expires: float


@dataclass
class Mutation:
    registration: str
    request: str
    row: dict
    published: bool = False


class _AuthorizationView:
    """All consumers of the server broker see the same live eligibility filter."""
    def __init__(self, host):
        self.host = host

    def auth_get(self, task_id):
        row = self.host.store.auth_get(task_id)
        return row if self.host.eligible(task_id, row) else None

    def auth_list(self):
        return [dict(row, trusted_eligible=self.host.eligible(row["task_id"], row))
                for row in self.host.store.auth_list()]

    def auth_upsert(self, scope):
        host = self.host
        if host._writing is None:
            raise PermissionError("No trusted mutation boundary")
        request_id, pending = host._writing
        # Match SidecarStore's actual persisted representation, not a timestamp
        # imagined to uniquely identify a write (broker compact may omit it).
        row = dict(scope, created_ms=int(scope.get("created_ms") or 0))
        row["ops"] = sorted(row["ops"])
        row["approved"] = bool(row.get("approved", False))
        host.journal.append({"kind": "mutation_intent", "request": request_id,
                             "registration": pending.registration, "row_hash": fingerprint(row)})
        # Persistence may block across expiry or invalidate the registration.
        # Final synchronous fence: no slot/store mutation before both checks.
        host._registration(pending.registration)
        if time.monotonic() >= pending.expires:
            raise PermissionError('Consent expired during mutation-intent persistence')
        slot = Mutation(pending.registration, request_id, row)
        host.slots[row["task_id"]] = slot  # also tracks a commit with lost result
        return host.store.auth_upsert(row)

    def auth_revoke(self, task_id):
        host = self.host
        slot = host.slots.get(task_id)
        if slot is None:
            reason = "unverified_ownership" if host.store.auth_get(task_id) else "no_authorization"
            return {"revoked": False, "task_id": task_id, "reason": reason}
        return host.release(slot.registration, slot.request)


class TrustedConsent:
    """Host-owned core; private endpoint authentication is a separate prerequisite.

    No constructor/register/decide method is exposed through public dispatch.
    Only the finalizer closure supplies the opaque object to the real broker.
    """
    MAX_REGISTRATIONS = 8
    MAX_PENDING = 8
    MAX_SLOTS = 64
    BINDING_FIELDS = {"owner_root", "owner_pid", "owner_start", "owner_session",
                      "control_generation", "descriptor_sha256", "task_id", "app_id",
                      "workspace", "read_policy_sha256", "ops"}

    def __init__(self, store, journal):
        self.store, self.journal = store, journal
        self.registrations, self.pending, self.slots = {}, {}, {}
        self._writing = None
        cap = object()
        self.broker = PermissionBroker(_AuthorizationView(self), grant_capability=cap)

        def finalize(kind, scope):
            if kind == "grant_create":
                return self.broker.authorize(**scope, grant_capability=cap)
            return self.broker.expand(**scope, grant_capability=cap)
        self._finalize = finalize

    def register(self, binding, *, verification=None):
        if verification is not None:
            if not isinstance(verification, IdentitySession):
                raise PermissionError("Private observer session required")
            verification.enter_operation('register')
        if (set(binding) != self.BINDING_FIELDS or len(canonical(binding)) > 2048
                or len(self.registrations) >= self.MAX_REGISTRATIONS):
            raise ValueError("Invalid or excessive trusted registrations")
        # The transport verifier owns attestation; data here is a bounded copy,
        # never evidence that a public caller supplied a valid PID/path/hash.
        copied = json.loads(canonical(binding))
        identifier = str(uuid.uuid4())
        self.journal.append({"kind": "registration", "registration": identifier,
                             "binding_hash": fingerprint(copied)})
        registration = Registration(copied, verification=verification)
        if verification is not None:
            # Registration persistence may cross proof/session expiry or EOF.
            verification.attach(registration)
        self.registrations[identifier] = registration
        return identifier

    def eligible(self, task_id, row=None):
        slot = self.slots.get(task_id)
        registration = self.registrations.get(slot.registration) if slot else None
        return bool(self.journal.fd is not None and not self.journal.broken and slot and slot.published and registration
                    and registration.live and (registration.verification is None or registration.verification.current())
                    and row is not None and row == slot.row)

    def _registration(self, identifier):
        registration = self.registrations.get(identifier)
        if self.journal.fd is None or self.journal.broken or not registration or not registration.live:
            raise PermissionError("No live trusted registration")
        if registration.verification is not None:
            registration.verification.require_current()
        return registration

    def request(self, registration, kind, scope, *, generation, native_call_id, deadline=None, consent_id=None, arguments_sha256=None):
        current_registration = self._registration(registration)
        if current_registration.verification is not None:
            current_registration.verification.enter_operation('request')
        binding = current_registration.binding
        if (kind not in {"grant_create", "grant_expand", "read_decision"}
                or set(scope) != {"task_id", "app_id", "file_prefix", "ops"}
                or scope["task_id"] != binding["task_id"] or scope["app_id"] != binding["app_id"]
                or scope["file_prefix"] != binding["workspace"]
                or not scope["ops"] or sorted(set(scope["ops"])) != scope["ops"]
                or not set(scope["ops"]) <= set(binding["ops"])
                or not isinstance(generation, str) or not 1 <= len(generation) <= 128
                or not isinstance(native_call_id, str) or not 1 <= len(native_call_id) <= 128
                or len(self.pending) >= self.MAX_PENDING
                or any(p.registration == registration for p in self.pending.values())):
            raise PermissionError("Consent scope/bounds mismatch")
        if consent_id is not None and (not isinstance(consent_id, str) or not 1 <= len(consent_id) <= 80):
            raise PermissionError('Invalid native consent correlation')
        if arguments_sha256 is not None and (not isinstance(arguments_sha256, str) or len(arguments_sha256) != 64
                or any(c not in '0123456789abcdef' for c in arguments_sha256)):
            raise PermissionError('Invalid immutable native argument hash')
        row = self.store.auth_get(scope["task_id"])
        if kind == "grant_create" and row and row["status"] == "active":
            raise PermissionError("Conflicting active scope; no adoption")
        if kind in {"grant_expand", "read_decision"} and (not self.eligible(scope["task_id"], row)
                or self.slots[scope["task_id"]].registration != registration):
            raise PermissionError("Expansion requires live owned provenance")
        if kind != "read_decision" and scope["task_id"] not in self.slots and len(self.slots) >= self.MAX_SLOTS:
            raise PermissionError("Owned mutation index bound")
        identifier, nonce = str(uuid.uuid4()), os.urandom(32).hex()
        expires = min(time.monotonic() + 120, deadline) if deadline is not None else time.monotonic() + 120
        if expires <= time.monotonic():
            raise PermissionError("Consent already expired")
        body = {"binding": binding, "kind": kind, "scope": scope,
                "generation": generation, "native_call_id": native_call_id,
                "consent_id": consent_id, "arguments_sha256": arguments_sha256}
        digest = fingerprint(body)
        self.journal.append({"kind": "request", "request": identifier,
                             "registration": registration, "body_hash": digest,
                             "native_call_id": native_call_id, "consent_id": consent_id, "issued_ms": int(time.time() * 1000)})
        # A successful fsync is not a liveness/expiry fence. Do not publish a
        # pending consent after invalidation or a deadline crossed during I/O.
        self._registration(registration)
        if time.monotonic() >= expires:
            raise PermissionError("Consent expired during request persistence")
        self.pending[identifier] = Pending(registration, kind, canonical(scope), digest, nonce, expires)
        return {"request": identifier, "nonce": nonce, "body_hash": digest}

    def decide(self, registration, request, nonce, body_hash, allowed):
        current_registration = self._registration(registration)
        if current_registration.verification is not None:
            current_registration.verification.enter_operation('decision')
        pending = self.pending.get(request)
        if (pending is None or pending.registration != registration or pending.nonce != nonce
                or pending.body_hash != body_hash or type(allowed) is not bool):
            raise PermissionError("No exact pending consent")
        del self.pending[request]  # consume BEFORE persistence or any mutation
        decision = "timeout" if time.monotonic() >= pending.expires else "allow" if allowed else "deny"
        self.journal.append({"kind": "decision", "request": request,
                             "registration": registration, "decision": decision,
                             "body_hash": body_hash, "decided_ms": int(time.time() * 1000)})
        if decision != "allow":
            raise ConsentDenied("Human consent denied/expired")
        self._registration(registration)
        if time.monotonic() >= pending.expires:
            raise PermissionError("Consent expired during persistence")
        scope = json.loads(pending.scope_json)
        if pending.kind == "read_decision":
            current = self.store.auth_get(scope["task_id"])
            if not self.eligible(scope["task_id"], current) or self.slots[scope["task_id"]].registration != registration:
                raise PermissionError('Read provenance changed before decision')
            self._registration(registration)
            if time.monotonic() >= pending.expires:
                raise PermissionError('Consent expired during read provenance lookup')
            return {"accepted": True, "request": request}
        row = self.store.auth_get(scope["task_id"])
        if pending.kind == "grant_create" and row and row["status"] == "active":
            raise PermissionError("Scope changed before grant")
        if pending.kind == "grant_expand" and not self.eligible(scope["task_id"], row):
            raise PermissionError("Scope provenance changed before expansion")
        self._writing = request, pending
        try:
            self._finalize(pending.kind, dict(scope, approved=pending.kind == "grant_expand"))
            slot = self.slots[scope["task_id"]]
            if self.store.auth_get(scope["task_id"]) != slot.row:
                raise PermissionError("Uncertain broker write; no replay")
            self.journal.append({"kind": "result", "request": request,
                                 "registration": registration, "row_hash": fingerprint(slot.row)})
            # Result fsync and the final store read can both block. Recheck the
            # exact owned row, registration and deadline AFTER those operations.
            # Keep an uncertain committed slot unpublished for owned CAS cleanup;
            # never restore an earlier row or retry the consumed decision.
            current = self.store.auth_get(scope["task_id"])
            self._registration(registration)
            if time.monotonic() >= pending.expires:
                raise PermissionError("Consent expired during result persistence")
            if current != slot.row:
                raise PermissionError("Owned row changed during result persistence")
            slot.published = True  # no I/O/await between final fence and publication
            return {"accepted": True, "request": request}
        finally:
            self._writing = None

    def invalidate(self, registration):
        current = self.registrations.get(registration)
        if current is None:
            raise PermissionError('No owned registration to invalidate')
        current.live = False  # BEFORE cleanup or I/O, even when audit is broken
        if current.verification is not None:
            current.verification.seal()
        for identifier, pending in list(self.pending.items()):
            if pending.registration == registration:
                del self.pending[identifier]
        self.journal.append({"kind": "invalidated", "registration": registration})
        if not any(slot.registration == registration for slot in self.slots.values()):
            self.registrations.pop(registration, None)

    def release(self, registration, request):
        matches = [(task, slot) for task, slot in self.slots.items()
                   if slot.registration == registration and slot.request == request]
        if not matches:
            return {"revoked": False, "reason": "no_owned_mutation"}
        task, slot = matches[0]
        slot.published = False  # immediate check invalidation, independent of DB latency
        row = slot.row
        # Exact live slot + conditional row update. Never a task-ID-only revoke.
        with self.store.db:
            cursor = self.store.db.execute(
                "UPDATE authorizations SET status='revoked' WHERE task_id=? AND app_id IS ? "
                "AND file_prefix IS ? AND ops_json=? AND status=? AND approved=? AND created_ms=?",
                (task, row["app_id"], row["file_prefix"], json.dumps(row["ops"]), row["status"],
                 int(row["approved"]), row["created_ms"]))
        if cursor.rowcount != 1:
            raise PermissionError("Owned row changed; no broad cleanup")
        self.journal.append({"kind": "released", "registration": registration, "request": request})
        del self.slots[task]
        current = self.registrations.get(registration)
        if current and not current.live and not any(slot.registration == registration for slot in self.slots.values()):
            del self.registrations[registration]
        return {"revoked": True, "task_id": task}


class UnverifiedAuthorizationView:
    """Disabled trusted service: legacy/external DB rows are never authority."""
    def __init__(self, store):
        self.store = store

    def auth_get(self, task_id):
        return None

    def auth_list(self):
        return [dict(row, trusted_eligible=False) for row in self.store.auth_list()]

    def auth_upsert(self, scope):
        raise PermissionError('Trusted grant service unavailable')

    def auth_revoke(self, task_id):
        if self.store.auth_get(task_id) is None:
            return {'revoked': False, 'task_id': task_id, 'reason': 'no_authorization'}
        raise PermissionError('No verified ownership; no task-ID-only cleanup')
