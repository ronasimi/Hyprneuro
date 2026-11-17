#!/usr/bin/env python3
"""
Continuation ops W4: START ONLY (watch4 + start4 phases).
Minimal clone of W3 ops with:
- New one-shot markers: watch4, start4, ready
- 4-unit closed table (service + socket)
- Prospective postwrite context file for DB/settings pre-start baseline
- Safe closed enum stage (assign BEFORE predicate, no parse exceptions)
- All W3/W2/04 markers retained (no delete/replay)

Phases: watch4 → start4
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time
import uuid
from enum import Enum
from pathlib import Path

# --- Pinned imports from frozen 04 modules ---
OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
sys.path.insert(0, str(OPS_DIR))

import boundary_release as b
from boundary_release_ops import (
    load,
    check_material,
    effective,
    screen_lock_state,
    watch_decision,
    validate_start_receipt,
    full_identity,
    wait_broker_listener,
    recheck_broker_listener,
    wait_app_active,
    contain,
)

# --- Pinned import from frozen v5 (stable ExecStart preserve) ---
V5_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5')
sys.path.insert(0, str(V5_DIR))
from continuation_ops import preserve_continuation, _safe_exception_label, SAFE_EXCEPTION_CLASSES


# --- W4 marker names (new, one-shot, NOT reuse old) ---

WATCH4_READY = 'continuation.watch4.ready'
START4_STARTED = 'continuation.start4.started'
START4_COMPLETED = 'continuation.start4.completed'
START4_READY_EVENT = 'continuation.start4.ready'


# --- 4-unit closed table ---

ALL_UNITS = (
    'hyprneuro.service',
    'hyprneuro-ui.service',
    'hyprneuro-pi-identity.service',
    'hyprneuro-pi-identity.socket',
)

# APP_UNITS from 04 module (the two services that get started)
APP_UNITS = b.APP_UNITS  # ('hyprneuro.service', 'hyprneuro-ui.service')


# --- Safe closed enum stage ---

class W4Stage(str, Enum):
    PROVISION_MARKER = 'PROVISION_MARKER'
    WATCH_READY_PARSE = 'WATCH_READY_PARSE'
    WATCH_READY_OP = 'WATCH_READY_OP'
    WATCH_READY_TOKEN = 'WATCH_READY_TOKEN'
    WATCH_READY_PID = 'WATCH_READY_PID'
    WATCH_READY_UID = 'WATCH_READY_UID'
    WATCH_READY_START = 'WATCH_READY_START'
    PRESERVE = 'PRESERVE'
    MATERIAL = 'MATERIAL'
    EFFECTIVE = 'EFFECTIVE'
    RESTART = 'RESTART'
    LOCK = 'LOCK'
    BROKER_START = 'BROKER_START'
    LISTENER = 'LISTENER'
    UI_START = 'UI_START'
    IDENTITY = 'IDENTITY'
    COMPLETED = 'COMPLETED'
    CONTEXT = 'CONTEXT'


def _stage_failure(stage: W4Stage, label: str) -> ValueError:
    return ValueError(f'{stage.value}: {label}')


def _op_dir(op: dict) -> Path:
    return Path(op['bundle']) / 'operation'


# --- Context file validation ---

CONTEXT_SCHEMA = 'hyprneuro.boundary-postwrite-context/1'
CONTEXT_MAX_SIZE = 65536


def validate_context_file(path: Path) -> dict:
    """Validate prospective postwrite context file. STRICT. Fail-closed.
    Returns parsed context dict on success. Raises on any violation.
    """
    stage = W4Stage.CONTEXT

    # File safety checks (same-FD, no TOCTOU)
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise _stage_failure(stage, 'context not regular file')
        if info.st_uid != os.getuid():
            raise _stage_failure(stage, 'context UID mismatch')
        if info.st_mode & 0o077:
            raise _stage_failure(stage, 'context not private mode')
        if info.st_nlink != 1:
            raise _stage_failure(stage, 'context nlink != 1')
        if info.st_size > CONTEXT_MAX_SIZE:
            raise _stage_failure(stage, 'context size exceeded')

        raw = os.read(fd, CONTEXT_MAX_SIZE + 1)
        if len(raw) > CONTEXT_MAX_SIZE:
            raise _stage_failure(stage, 'context read overflow')

        # Re-stat same FD to detect race
        info2 = os.fstat(fd)
        if (info2.st_dev, info2.st_ino, info2.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise _stage_failure(stage, 'context changed during read')
    finally:
        os.close(fd)

    # Parse JSON
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _stage_failure(stage, 'context not valid JSON')

    if not isinstance(data, dict):
        raise _stage_failure(stage, 'context not a dict')

    # Schema
    if data.get('schema') != CONTEXT_SCHEMA:
        raise _stage_failure(stage, 'context schema mismatch')

    # Required fields
    required = {'schema', 'ts_utc', 'ancestry', 'database_no_SQL', 'settings'}
    if not required.issubset(data.keys()):
        raise _stage_failure(stage, 'context missing required fields')

    # Ancestry must bind original OP/GEN
    ancestry = data['ancestry']
    if not isinstance(ancestry, dict):
        raise _stage_failure(stage, 'ancestry not dict')
    for key in ('original_operation_sha', 'original_generation', 'failed_execution', 'prior_successful_execution'):
        if key not in ancestry:
            raise _stage_failure(stage, f'ancestry missing {key}')

    # database_no_SQL must be dict
    db = data['database_no_SQL']
    if not isinstance(db, dict):
        raise _stage_failure(stage, 'database_no_SQL not dict')

    # settings must be dict with path
    settings = data['settings']
    if not isinstance(settings, dict) or 'path' not in settings:
        raise _stage_failure(stage, 'settings malformed')

    return data


def _verify_file_metadata(path: Path, expected: dict, label: str, stage: W4Stage) -> None:
    """Verify file metadata with same-FD identity check.
    Checks ALL declared fields: dev, inode, uid, mode (S_IMODE), size, SHA.
    Same-FD: open, fstat, read, fstat again, compare identity before/after.
    """
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        # Check all declared metadata
        if 'dev' in expected and before.st_dev != expected['dev']:
            raise _stage_failure(stage, f'{label} dev mismatch')
        if 'inode' in expected and before.st_ino != expected['inode']:
            raise _stage_failure(stage, f'{label} inode mismatch')
        if 'uid' in expected and before.st_uid != expected['uid']:
            raise _stage_failure(stage, f'{label} uid mismatch')
        if 'mode' in expected and (before.st_mode & 0o7777) != expected['mode']:
            raise _stage_failure(stage, f'{label} mode mismatch')
        if 'size' in expected and before.st_size != expected['size']:
            raise _stage_failure(stage, f'{label} size mismatch')

        # Read full file for SHA (bounded)
        chunks = []
        total = 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 64 * 1024 * 1024:
                raise _stage_failure(stage, f'{label} size budget exceeded')
            chunks.append(chunk)
        raw = b''.join(chunks)

        # Same-FD identity after read
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_uid, s.st_mode, s.st_nlink)
        if identity(before) != identity(after):
            raise _stage_failure(stage, f'{label} changed during read')

        # SHA check
        if 'sha256' in expected:
            actual_sha = hashlib.sha256(raw).hexdigest()
            if actual_sha != expected['sha256']:
                raise _stage_failure(stage, f'{label} SHA mismatch')
    finally:
        os.close(fd)


def check_context_prestart(op: dict, deadline: float, context_path: Path) -> None:
    """Pre-start DB/settings check. Context file is REQUIRED.
    If missing/invalid → REJECT. NO fallback to 04 baseline.
    """
    stage = W4Stage.CONTEXT

    if context_path is None:
        raise _stage_failure(stage, 'context file path is None (required)')
    if not context_path.exists():
        raise _stage_failure(stage, 'context file missing (required, no fallback)')

    ctx = validate_context_file(context_path)

    # DB checks from context (ALL declared metadata, same-FD identity)
    for name, value in ctx['database_no_SQL'].items():
        p = Path(name)
        if value is None:
            # WAL/SHM must be absent
            if p.exists():
                raise _stage_failure(W4Stage.PRESERVE, f'DB companion {p.name} appeared before start')
        else:
            if not p.exists():
                raise _stage_failure(W4Stage.PRESERVE, f'DB {p.name} missing')
            _verify_file_metadata(p, value, f'DB {p.name}', W4Stage.PRESERVE)

    # Settings check from context (ALL declared metadata, same-FD identity)
    s = ctx['settings']
    sp = Path(s['path'])
    if not sp.exists():
        raise _stage_failure(W4Stage.PRESERVE, 'settings file missing')
    _verify_file_metadata(sp, s, 'settings', W4Stage.PRESERVE)

    # Root/model/source guards still from 04 bundle (unchanged)
    # These are checked by check_material(op, True) called separately.


def check_context_runtime(op: dict, deadline: float, context_path: Path) -> None:
    """Runtime (watch loop) checks.
    DB writes EXPECTED — never reapply cold DB fingerprint.
    Model/runtime/root/source guards strict (unchanged from 04).
    """
    # Non-full preserve: checks models + runtime pins only (NOT DB/settings)
    preserve_continuation(op, deadline, full=False)


# --- Phase: watch4 ---

def phase_watch4(op: dict, literal: str, deadline: float, run_token: str,
                 context_path: Path) -> None:
    """Watch4: check_material → preserve → stopped → screen_lock → watch4.ready
    → loop: check_material → preserve(non-full) → Restart → screen_lock
    → watch4_decision (reads start4 markers) → bounded contain"""
    directory = _op_dir(op)
    stage = W4Stage.PROVISION_MARKER

    check_material(op, True)
    check_context_prestart(op, deadline, context_path)
    for unit in APP_UNITS:
        b.stopped(unit, deadline)
    screen_lock_state(directory, deadline)

    # Write watch4.ready with run_token (new marker, NOT old watch.ready)
    proc = Path('/proc/self')
    b.write_new(
        directory / WATCH4_READY,
        b.encoded(dict(
            schema='hyprneuro.boundary-watch4-ready/1',
            operation_sha256=literal,
            run_token=run_token,
            pid=os.getpid(),
            start=proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
        ))
    )

    transient_started_at = None
    while time.monotonic() < deadline:
        check_material(op, True)
        check_context_runtime(op, deadline, context_path)
        for unit in APP_UNITS:
            if b.show(unit, ('Restart',), deadline)['Restart'] != 'no':
                return contain(op)
        lock = screen_lock_state(directory, deadline)
        started = (directory / START4_STARTED).exists()
        completed = (directory / START4_COMPLETED).exists()
        if started and transient_started_at is None:
            transient_started_at = time.monotonic()
        live = {}
        receipt = None
        if completed:
            receipt = validate_start_receipt(
                json.loads(b.file_bytes(directory / START4_COMPLETED)),
                literal, op['generation']
            )
            for unit in APP_UNITS:
                live[unit] = full_identity(unit, deadline)
        watch_decision(receipt, live, lock, started, completed, transient_started_at, time.monotonic())
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return contain(op)


# --- Phase: start4 ---

def phase_start4(op: dict, literal: str, deadline: float, run_token: str,
                 context_path: Path) -> None:
    """Start4: watch4.ready validate (run_token) → preserve → check_material
    → effective → Restart=no → screen_lock → start4.started → broker start
    → broker listener gate → recheck → UI start → full identity → start4.completed"""
    directory = _op_dir(op)
    stage = W4Stage.WATCH_READY_PARSE

    # Validate watch4.ready (new marker, check run_token)
    ready_raw = b.file_bytes(directory / WATCH4_READY)
    ready = json.loads(ready_raw)
    if ready.get('run_token') != run_token:
        raise _stage_failure(W4Stage.WATCH_READY_TOKEN, 'run_token mismatch')
    if ready.get('operation_sha256') != literal:
        raise _stage_failure(W4Stage.WATCH_READY_OP, 'operation SHA mismatch')
    stage = W4Stage.WATCH_READY_PID
    proc = Path('/proc') / str(ready['pid'])
    if not proc.exists():
        raise _stage_failure(W4Stage.WATCH_READY_PID, 'watcher process dead')
    stage = W4Stage.WATCH_READY_START
    if ready.get('start') != proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]:
        raise _stage_failure(W4Stage.WATCH_READY_START, 'watcher start_ticks mismatch')
    stage = W4Stage.WATCH_READY_UID
    if proc.stat().st_uid != os.getuid():
        raise _stage_failure(W4Stage.WATCH_READY_UID, 'watcher UID mismatch')

    stage = W4Stage.PRESERVE
    check_context_prestart(op, deadline, context_path)
    stage = W4Stage.MATERIAL
    check_material(op, True)
    stage = W4Stage.EFFECTIVE
    effective(op, deadline)

    stage = W4Stage.RESTART
    for unit in APP_UNITS:
        if b.stopped(unit, deadline)['Restart'] != 'no':
            raise _stage_failure(W4Stage.RESTART, 'BOTH app Restart=no required')

    stage = W4Stage.LOCK
    screen_lock_state(directory, deadline)

    path = Path('/run/user/1000/hyprharness/grant-control.sock')
    stage = W4Stage.BROKER_START
    b.write_new(directory / START4_STARTED, (literal + '\n').encode())

    b.command(['/usr/bin/systemctl', '--user', 'start', APP_UNITS[0]], deadline)
    stage = W4Stage.LISTENER
    proof = wait_broker_listener(APP_UNITS[0], path, deadline)
    recheck_broker_listener(APP_UNITS[0], proof, deadline)
    stage = W4Stage.UI_START
    b.command(['/usr/bin/systemctl', '--user', 'start', APP_UNITS[1]], deadline)

    stage = W4Stage.IDENTITY
    broker_full = full_identity(APP_UNITS[0], deadline)
    ui_full = wait_app_active(APP_UNITS[1], deadline)
    if broker_full is None:
        raise _stage_failure(W4Stage.IDENTITY, 'Broker not verifiably active')

    stage = W4Stage.COMPLETED
    b.write_new(
        directory / START4_COMPLETED,
        b.encoded(dict(
            schema='hyprneuro.boundary-start-receipt/1',
            operation_sha256=literal,
            generation=op['generation'],
            run_token=run_token,
            broker=broker_full,
            ui=ui_full
        ))
    )


# --- 4-unit receipt (closed table, actual LoadState + MainPID) ---

def unit_evidence_4() -> list:
    """Get actual 4-unit evidence: LoadState + MainPID.
    Service: MainPID from systemctl. Socket: N/A.
    Not found → 'UNKNOWN', never fabricated 0.
    """
    evidence = []
    for unit in ALL_UNITS:
        entry = {'unit': unit}
        try:
            load_state = subprocess.run(
                ['/usr/bin/systemctl', '--user', 'show', '-p', 'LoadState', '--value', unit],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
            entry['LoadState'] = load_state if load_state else 'UNKNOWN'
        except Exception:
            entry['LoadState'] = 'UNKNOWN'

        if unit.endswith('.socket'):
            entry['MainPID'] = 'N/A'
        else:
            try:
                pid = subprocess.run(
                    ['/usr/bin/systemctl', '--user', 'show', '-p', 'MainPID', '--value', unit],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
                entry['MainPID'] = pid if pid and pid != '0' else 'UNKNOWN'
            except Exception:
                entry['MainPID'] = 'UNKNOWN'
        evidence.append(entry)
    return evidence


# --- Main entrypoint ---

def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation ops W4 (START ONLY)')
    parser.add_argument('--operation', type=Path, required=True)
    parser.add_argument('--operation-sha256', required=True)
    parser.add_argument('--phase', choices=('watch4', 'start4', 'contain'), required=True)
    parser.add_argument('--run-token', required=True, help='Fresh run token binding this attempt')
    parser.add_argument('--context', type=Path, required=True,
                        help='Required prospective postwrite context file')
    args = parser.parse_args()

    op = load(args.operation, args.operation_sha256)
    literal = args.operation_sha256
    run_token = args.run_token
    context_path = args.context

    deadline = time.monotonic() + (600 if args.phase == 'watch4' else 180)

    try:
        if args.phase == 'watch4':
            result = phase_watch4(op, literal, deadline, run_token, context_path)
            if result:
                print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
                return
        elif args.phase == 'start4':
            phase_start4(op, literal, deadline, run_token, context_path)
        elif args.phase == 'contain':
            result = contain(op)
            print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
            return
        print(json.dumps({'status': 'PASS', 'phase': args.phase, 'run_token': run_token}, sort_keys=True))
    except Exception as e:
        result = contain(op)
        print(json.dumps({
            'status': 'FAILED_NO_REPLAY',
            'stage': _safe_exception_label(e),
            'exception_class': _safe_exception_label(e),
            'run_token': run_token,
            'containment': result
        }, sort_keys=True))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
