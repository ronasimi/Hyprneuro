#!/usr/bin/env python3
"""Offline disposable-fixture rehearsal ONLY. No production/activation mode.

Requests and marker are explicit, canonical private files beneath a fresh
hn-memory-fixture-* directory. This is not a same-UID sandbox or evidence of
production quiescence. No service, settings restoration or downgrade is exposed.
"""
from collections import Counter
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import argparse
import importlib
import json
import os
import re
import sqlite3
import stat
import struct
import subprocess
import sys
import time

CODE = Path(__file__).resolve().parents[1]
CODE_FILES = ("scripts/memory_migration_candidate.py", "python/src/hyprneuro/application.py",
              "python/src/hyprneuro/sidecar_store.py")
SUFFIXES = ("", "-wal", "-shm", "-journal")
MAX_BYTES = 32 * 1024 * 1024
MAX_ROWS = 20_000


class Refused(RuntimeError):
    pass


class Budget:
    def __init__(self):
        self.end = time.monotonic() + 15

    def remaining(self):
        left = self.end - time.monotonic()
        if left <= 0:
            raise Refused("fixture operation deadline exceeded; preserve partial artifacts")
        return left


def digest(path):
    if path.stat().st_size > MAX_BYTES:
        raise Refused("fixture file exceeds size bound")
    return sha256(path.read_bytes()).hexdigest()


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_file(path):
    with path.open("rb") as stream:
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        os.fchmod(stream.fileno(), 0o600)
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(path.parent)


def regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > MAX_BYTES):
        raise Refused("private single-link regular fixture file required")
    return path


def fixture_root(root):
    root = Path(root)
    if (not root.is_absolute() or root != root.resolve()
            or not re.fullmatch(r"hn-memory-fixture-[A-Za-z0-9_-]{8,64}", root.name)):
        raise Refused("explicit canonical disposable fixture root required")
    for directory in (root, *root.parents):
        info = directory.lstat()
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid not in (0, os.getuid())
                or (info.st_mode & 0o022 and not info.st_mode & 0o1000)):
            raise Refused("untrusted fixture ancestry")
    if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
        raise Refused("private owned fixture root required")
    marker = regular(root / "fixture.json")
    value = json.loads(marker.read_text())
    if (not isinstance(value, dict) or set(value) != {"schema", "disposable"}
            or value["schema"] != "hyprneuro.memory-disposable/1" or value["disposable"] is not True):
        raise Refused("explicit disposable fixture marker required")
    # Never follow a link in the operation tree, including preexisting artifacts.
    for index, path in enumerate(root.rglob("*")):
        if index >= 64:
            raise Refused("fixture artifact-count bound exceeded")
        if path.is_symlink():
            raise Refused("fixture aliases are not permitted")
        if path.is_dir():
            if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
                raise Refused("private owned fixture directories required")
        else:
            regular(path)
    return root


def source_identity():
    """Exact checkout identity, not caller-selected executable/import paths."""
    commit = subprocess.check_output(["/usr/bin/git", "-C", str(CODE), "rev-parse", "HEAD"],
                                     text=True, timeout=3, env={"GIT_CONFIG_NOSYSTEM": "1",
                                     "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_OPTIONAL_LOCKS": "0"}).strip()
    return {"commit": commit, "files": {name: digest(CODE / name) for name in CODE_FILES}}


def store_module():
    sys.path.insert(0, str(CODE / "python/src"))
    module = importlib.import_module("hyprneuro.sidecar_store")
    if Path(module.__file__).resolve() != CODE / "python/src/hyprneuro/sidecar_store.py":
        raise Refused("unexpected memory source origin")
    app = importlib.import_module("hyprneuro.application")
    if Path(app.__file__).resolve() != CODE / "python/src/hyprneuro/application.py":
        raise Refused("unexpected application source origin")
    return module


def family(path):
    result = {}
    for suffix in SUFFIXES:
        file = Path(str(path) + suffix)
        if file.exists() or file.is_symlink():
            regular(file)
            # SHM is transient reader coordination, not authoritative data.
            result[suffix] = digest(file) if suffix != "-shm" else "present"
        else:
            result[suffix] = None
    return result


def request_paths(root, request, phase):
    root = fixture_root(root)
    if (set(request) != {"schema", "database", "settings", "source", "quiescence"}
            or request["schema"] != "hyprneuro.memory-fixture-request/1"):
        raise Refused("unsupported fixture request schema")
    names = [request["database"], request["settings"]]
    if (any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", n)
            or n.casefold().endswith(SUFFIXES[1:]) for n in names)
            or len({n.casefold() for n in names + ["fixture.json", "request.json", "operation", "replacement.sqlite3"]}) != 6):
        raise Refused("distinct fixture-local input filenames required")
    db, settings = (regular(root / name) for name in names)
    if request["source"] != source_identity():
        raise Refused("source commit/blob identity mismatch")
    q = request["quiescence"]
    expected = {"schema", "phase", "writers_closed", "old_owner_scopes", "new_owner_scopes",
                "database_family", "settings_sha256"}
    if (not isinstance(q, dict) or set(q) != expected
            or q["schema"] != "hyprneuro.memory-fixture-quiescence/1" or q["phase"] != phase
            or q["writers_closed"] is not True
            or any(not isinstance(q[n], list) or not 1 <= len(q[n]) <= 32
                   or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in q[n])
                   for n in ("old_owner_scopes", "new_owner_scopes"))):
        raise Refused("fresh phase-specific closed fixture-writer attestation required")
    if family(db) != q["database_family"] or digest(settings) != q["settings_sha256"]:
        raise Refused("stale fixture quiescence attestation")
    if phase != "recovery" and q["database_family"]["-journal"] is not None:
        raise Refused("journal-bearing fixture requires separate classification")
    return root, db, settings


def typed_rows(rows):
    encoded = []
    for row in rows:
        values = []
        for value in row:
            if value is None:
                values.append(["null"])
            elif isinstance(value, bytes):
                values.append(["blob", value.hex()])
            elif isinstance(value, str):
                values.append(["text", value])
            elif isinstance(value, int):
                values.append(["integer", str(value)])
            elif isinstance(value, float):
                values.append(["real", struct.pack(">d", value).hex()])
            else:
                raise Refused("unsupported SQLite value type")
        data = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
        if len(data) > 1024 * 1024 or len(encoded) >= MAX_ROWS:
            raise Refused("fixture row bound exceeded")
        encoded.append(data)
    out = sha256()
    for row in sorted(encoded):
        out.update(len(row).to_bytes(8, "big"))
        out.update(row)
    return {"count": len(encoded), "sha256": out.hexdigest()}


def readonly(path, budget):
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=0)
    try:
        db.execute("PRAGMA query_only=ON")
        db.set_progress_handler(lambda: int(time.monotonic() >= budget.end), 1000)
        db.create_function("public_url", 1, store_module().public_url, deterministic=True)
        return db
    except BaseException:
        db.close()
        raise


def inventory(path, budget):
    regular(path)
    module = store_module()
    with closing(readonly(path, budget)) as db:
        budget.remaining()
        version = module._store_version(db)
        if version is None:
            raise Refused("empty/unversioned fixture database")
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)] or db.execute("PRAGMA foreign_key_check").fetchall():
            raise Refused("fixture integrity/foreign-key check failed")
        schema = db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
        tables, memory = {}, []
        for kind, name, table, sql in schema:
            if kind != "table":
                continue
            budget.remaining()
            quoted = '"' + name.replace('"', '""') + '"'
            rows = db.execute(f"SELECT * FROM {quoted}").fetchmany(MAX_ROWS + 1)
            if name.casefold() == "app_memory":
                memory = rows
                continue
            if name.casefold() == "sidecar_meta":
                rows = [(k, "4" if k == "schema_version" else v) for k, v in rows]
            tables[name] = typed_rows(rows)
        original, derived = [], []
        for row in memory:
            original.append(row[:7])
            scope, key, _, task, app, project, _ = row[:7]
            try:
                owner = module.memory_owner(scope, task_id=task, app_id=app, project_id=project)
                module._validate_scope_key(scope, key)
                legacy = 0
            except (ValueError, TypeError):
                owner, legacy = "", 1
            derived.append((*row[:7], owner, legacy))
        actual = memory if version == "4" else derived
        fts = []
        for term, in db.execute("SELECT term FROM search_vocab ORDER BY term LIMIT 32"):
            phrase = '"' + term.replace('"', '""') + '"'
            for name in ("observations_fts", "search_fts"):
                ids = db.execute(f"SELECT rowid FROM {name} WHERE {name} MATCH ? ORDER BY rowid", (phrase,)).fetchall()
                fts.append((name, term, json.dumps(ids)))
        if version == "4":
            columns = [(r[2], r[3]) for r in db.execute("PRAGMA index_xinfo(app_memory_scope_time)") if r[5]]
            if columns != [("scope", 0), ("legacy_unscoped", 0), ("owner_id", 0), ("updated_ms", 1)]:
                raise Refused("unexpected v4 memory recall index")
        return {"version": version,
                "schema": typed_rows([row for row in schema if row[2].casefold() != "app_memory"]),
                "tables": tables, "memory_original": typed_rows(original), "memory_identity": typed_rows(actual),
                "identity_derivable": typed_rows(actual) == typed_rows(derived), "fts": typed_rows(fts),
                "v3_duplicate_keys": sum(n - 1 for n in Counter((r[0], r[1]) for r in original).values() if n > 1)}


def snapshot(source, destination, budget):
    with destination.open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
    with closing(readonly(source, budget)) as src, closing(sqlite3.connect(destination, timeout=0)) as dst:
        src.backup(dst, pages=128, progress=lambda *_: budget.remaining(), sleep=0.01)
        # A backup can inherit a WAL-mode header. Normalize ONLY the fresh
        # destination so later read-only verification cannot create sidecars.
        if dst.execute("PRAGMA journal_mode=DELETE").fetchone() != ("delete",):
            raise Refused("cannot make private snapshot self-contained")
    regular(destination)
    sync_file(destination)
    if any(Path(str(destination) + suffix).exists() for suffix in SUFFIXES[1:]):
        raise Refused("snapshot must be self-contained, without sidecars")


def same_data(left, right):
    return all(left[key] == right[key] for key in ("schema", "tables", "memory_original", "memory_identity", "fts"))


def load_state(root):
    record = json.loads(regular(root / "operation/state.json").read_text())
    base = {"phase", "source", "database", "settings", "baseline_family", "settings_sha256"}
    complete = base | {"baseline", "candidate", "artifacts"}
    if not isinstance(record, dict):
        raise Refused("unrecognized fixture operation state")
    phase = record.get("phase")
    if ((phase == "prepare_intent" and set(record) != base)
            or (phase in ("prepared", "replacement_intent", "replaced_unstarted", "activation_possible")
                and (set(record) != complete or not isinstance(record["artifacts"], dict) or set(record["artifacts"]) != {
                    "baseline.sqlite3", "candidate.sqlite3", "migration-backup.sqlite3"}))
            or phase not in ("prepare_intent", "prepared", "replacement_intent", "replaced_unstarted", "activation_possible")):
        raise Refused("unrecognized fixture operation state/artifact map")
    return record


def state(root, value):
    temporary = root / "operation/state.next.json"
    write_json(temporary, value)
    os.replace(temporary, root / "operation/state.json")
    fsync_directory(root / "operation")


def _run_migration(root, request, budget):
    # The only signalled process on timeout is this owned fixture-only child;
    # subprocess.run kills AND waits on timeout. Never signal an app/owner.
    child_request = root / "operation/prepare-request.json"
    write_json(child_request, request)
    subprocess.run([sys.executable, "-W", "error", str(Path(__file__).resolve()),
                    "_migrate-child", str(root)], check=True, timeout=budget.remaining(),
                   env={"PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True)


def prepare(root, request):
    budget = Budget()
    root, db, settings = request_paths(root, request, "prepare")
    before = inventory(db, budget)
    if before["version"] not in ("1", "2", "3"):
        raise Refused("prepare requires a legacy disposable fixture")
    op = root / "operation"
    op.mkdir(mode=0o700)  # Once-only: partial work cannot be adopted or replayed.
    fsync_directory(root)
    record = {"phase": "prepare_intent", "source": request["source"], "database": db.name,
              "settings": settings.name, "baseline_family": family(db), "settings_sha256": digest(settings)}
    state(root, record)
    snapshot(db, op / "baseline.sqlite3", budget)
    snapshot(op / "baseline.sqlite3", op / "candidate.sqlite3", budget)
    _run_migration(root, request, budget)
    for name in ("candidate.sqlite3", "migration-backup.sqlite3"):
        sync_file(op / name)
    candidate = inventory(op / "candidate.sqlite3", budget)
    backup = inventory(op / "migration-backup.sqlite3", budget)
    if (candidate["version"] != "4" or not same_data(before, candidate)
            or backup != before or family(db) != record["baseline_family"]
            or digest(settings) != record["settings_sha256"]):
        raise Refused("migration preservation/source-stability proof failed")
    record.update(phase="prepared", baseline=before, candidate=candidate,
                  artifacts={name: digest(op / name) for name in (
                      "baseline.sqlite3", "candidate.sqlite3", "migration-backup.sqlite3")})
    state(root, record)
    return record


def verify(root, request, *, _budget=None):
    budget = _budget or Budget()
    root, db, settings = request_paths(root, request, "verify")
    record = load_state(root)
    if (record["phase"] != "prepared" or record["source"] != request["source"]
            or record["database"] != db.name or record["settings"] != settings.name):
        raise Refused("no matching prepared fixture operation")
    for name, expected in record["artifacts"].items():
        artifact = regular(root / "operation" / name)
        if any(Path(str(artifact) + suffix).exists() for suffix in SUFFIXES[1:]):
            raise Refused("prepared artifacts must not have SQLite sidecars")
        if digest(artifact) != expected:
            raise Refused("prepared artifact changed")
        expected_inventory = record["candidate"] if name == "candidate.sqlite3" else record["baseline"]
        if inventory(artifact, budget) != expected_inventory:
            raise Refused("prepared artifact inventory drift")
    if (family(db) != record["baseline_family"] or digest(settings) != record["settings_sha256"]
            or inventory(db, budget) != record["baseline"]
            or inventory(root / "operation/candidate.sqlite3", budget) != record["candidate"]):
        raise Refused("late writes or candidate drift; refuse stale baseline")
    return record


def replace_fixture(root, request):
    """Atomic rename rehearsal on the disposable input ONLY; never starts code."""
    budget = Budget()
    root, db, settings = request_paths(root, request, "replace")
    verify(root, {**request, "quiescence": {**request["quiescence"], "phase": "verify"}}, _budget=budget)
    record = load_state(root)
    if any(Path(str(db) + suffix).exists() for suffix in SUFFIXES[1:]):
        raise Refused("fixture replacement refuses every existing SQLite sidecar")
    record["phase"] = "replacement_intent"
    state(root, record)
    stage = root / "replacement.sqlite3"
    snapshot(root / "operation/candidate.sqlite3", stage, budget)
    if inventory(stage, budget) != record["candidate"]:
        raise Refused("replacement stage verification failed")
    os.replace(stage, db)
    fsync_directory(root)
    record["phase"] = "replaced_unstarted"
    state(root, record)
    return record


def mark_fixture_activation(root, request):
    """Persist conservative possible-write fence, not service activation."""
    root, _, _ = request_paths(root, request, "activation")
    record = load_state(root)
    if (record["phase"] != "replaced_unstarted" or record["source"] != request["source"]
            or record["database"] != request["database"] or record["settings"] != request["settings"]):
        raise Refused("fixture activation fence requires a matched replacement")
    record["phase"] = "activation_possible"
    state(root, record)
    return record


def recovery_plan(root, request):
    budget = Budget()
    root, db, settings = request_paths(root, request, "recovery")
    record = load_state(root)
    if (record["source"] != request["source"] or record["database"] != db.name
            or record["settings"] != settings.name):
        raise Refused("recovery source/input identity mismatch")
    recovery = root / "operation/recovery"
    recovery.mkdir(mode=0o700)  # Preserve partial evidence; no automatic retry.
    fsync_directory(recovery.parent)
    raw = recovery / "raw"
    raw.mkdir(mode=0o700)
    hashes = {}
    for suffix in SUFFIXES:
        source = Path(str(db) + suffix)
        if source.exists():
            dest = raw / ("current.sqlite3" + suffix)
            with dest.open("xb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(source.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            hashes[dest.name] = digest(dest)
    fsync_directory(raw)
    with (recovery / "settings-current.json").open("xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(settings.read_bytes())
        stream.flush()
        os.fsync(stream.fileno())
    fsync_directory(recovery)
    snapshot(db, recovery / "authoritative.sqlite3", budget)
    current = inventory(recovery / "authoritative.sqlite3", budget)
    if (family(db) != request["quiescence"]["database_family"]
            or digest(settings) != request["quiescence"]["settings_sha256"]
            or inventory(db, budget) != current):
        raise Refused("fixture changed during preservation; retain raw evidence")
    zero_write = (record["phase"] == "replaced_unstarted" and current == record["candidate"])
    action = "pre_activation_recovery_review_required" if zero_write else "retain_current_forward_repair"
    if current["version"] != "4":
        action = "retain_legacy_manual_review"
    result = {"phase": record["phase"], "automatic_restore": False, "downgrade_permitted": False,
              "action": action,
              "v3_duplicate_keys": current["v3_duplicate_keys"], "identity_derivable": current["identity_derivable"],
              "compatibility": "blocked_duplicate_keys" if current["v3_duplicate_keys"] else "unproved_no_transform",
              "authoritative": current, "snapshot_sha256": digest(recovery / "authoritative.sqlite3"),
              "raw_sha256": hashes, "settings_sha256": digest(recovery / "settings-current.json")}
    write_json(recovery / "plan.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify", "recovery", "replace-fixture", "activation-fence", "_migrate-child"))
    parser.add_argument("fixture_root", type=Path)
    args = parser.parse_args()
    root = fixture_root(args.fixture_root)
    if args.action == "_migrate-child":
        request = json.loads(regular(root / "operation/prepare-request.json").read_text())
        request_paths(root, request, "prepare")
        record = load_state(root)
        if (record["phase"] != "prepare_intent"
                or any(record[name] != request[name] for name in ("source", "database", "settings"))):
            raise Refused("migration child requires matching pending fixture preparation")
        store_module().SidecarStore.migrate_memory(root / "operation/candidate.sqlite3",
                                                   backup_path=root / "operation/migration-backup.sqlite3")
        return
    request = json.loads(regular(root / "request.json").read_text())
    functions = {"prepare": prepare, "verify": verify, "recovery": recovery_plan,
                 "replace-fixture": replace_fixture, "activation-fence": mark_fixture_activation}
    result = functions[args.action](root, request)
    print(json.dumps({"fixture_only": True, "result": result}, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError, KeyError, TypeError):
        print("Fixture operation refused; preserve private artifacts; no retry or production operation.", file=sys.stderr)
        sys.exit(1)
