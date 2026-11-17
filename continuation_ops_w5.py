#!/usr/bin/env python3
"""
Continuation ops W5: START ONLY (watch5 + start5 phases).
Minimal W4-namespace clone with the APPROVED W5 corrections:
- Fresh W5 marker/event namespace (watch5, start5) — NOT reuse W4/W3 names.
- Prospective postwrite context (W5) binding original op/gen + known-failed W3 state.
- Reuses frozen readonly primitives UNCHANGED (check_material, full_identity, stopped,
  effective, screen_lock_state, preserve_continuation, validate_start_receipt, watch_decision,
  broker/UI start gates, contain).
- Safe closed enum stage. No daemon-reload. No reinstall. No new root. No baseline recapture.
Phases: watch5 -> start5
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from enum import Enum
from pathlib import Path

# --- Pinned imports from frozen 04 modules ---
OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
sys.path.insert(0, str(OPS_DIR))

import boundary_release as b  # noqa: E402
from boundary_release_ops import (  # noqa: E402
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
from continuation_ops import (  # noqa: E402
    preserve_continuation,
    _safe_exception_label,
    SAFE_EXCEPTION_CLASSES,
)

# --- W5 marker names (fresh namespace, one-shot, NOT reuse old) ---

WATCH5_READY = 'continuation.watch5.ready'
START5_STARTED = 'continuation.start5.started'
START5_COMPLETED = 'continuation.start5.completed'
START5_READY_EVENT = 'continuation.start5.ready'


# --- 4-unit closed table ---

ALL_UNITS = (
    'hyprneuro.service',
    'hyprneuro-ui.service',
    'hyprneuro-pi-identity.service',
    'hyprneuro-pi-identity.socket',
)

APP_UNITS = b.APP_UNITS  # ('hyprneuro.service', 'hyprneuro-ui.service')


class W5Stage(str, Enum):
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


def _stage_failure(stage: W5Stage, label: str) -> ValueError:
    return ValueError(f'{stage.value}: {label}')


def _op_dir(op: dict) -> Path:
    return Path(op['bundle']) / 'operation'


# --- Context file validation (W5) ---

CONTEXT_SCHEMA = 'hyprneuro.boundary-postwrite-context/1'
CONTEXT_MAX_SIZE = 65536
W5_ANCESTRY_REQUIRED = (
    'original_operation_sha',
    'original_generation',
    'known_failed_w3_execution',
    'prior_successful_execution',
    'source_context_sha',
)


def validate_context_file_w5(path: Path) -> dict:
    """Validate the W5 prospective postwrite context. STRICT. Fail-closed.
    W5 ancestry must bind original op/gen + known-failed W3 + source ctx (51f...).
    """
    stage = W5Stage.CONTEXT
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
        info2 = os.fstat(fd)
        if (info2.st_dev, info2.st_ino, info2.st_size) != (info.st_dev, info.st_ino, info.st_size):
            raise _stage_failure(stage, 'context changed during read')
    finally:
        os.close(fd)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise _stage_failure(stage, 'context not valid JSON')
    if not isinstance(data, dict):
        raise _stage_failure(stage, 'context not a dict')
    if data.get('schema') != CONTEXT_SCHEMA:
        raise _stage_failure(stage, 'context schema mismatch')

    required = {'schema', 'ts_utc', 'ancestry', 'database_no_SQL', 'settings'}
    if not required.issubset(data.keys()):
        raise _stage_failure(stage, 'context missing required fields')

    ancestry = data['ancestry']
    if not isinstance(ancestry, dict):
        raise _stage_failure(stage, 'ancestry not dict')
    for key in W5_ANCESTRY_REQUIRED:
        if key not in ancestry:
            raise _stage_failure(stage, f'ancestry missing {key}')

    if not isinstance(data['database_no_SQL'], dict):
        raise _stage_failure(stage, 'database_no_SQL not dict')
    settings = data['settings']
    if not isinstance(settings, dict) or 'path' not in settings:
        raise _stage_failure(stage, 'settings malformed')
    return data


def _verify_file_metadata(path: Path, expected: dict, label: str, stage: W5Stage) -> None:
    """Same-FD identity check of all declared metadata (dev/inode/uid/mode/size/SHA)."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
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
        chunks, total = [], 0
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            total += len(chunk)
            if total > 64 * 1024 * 1024:
                raise _stage_failure(stage, f'{label} size budget exceeded')
            chunks.append(chunk)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_uid, s.st_mode, s.st_nlink)
        if ident(before) != ident(after):
            raise _stage_failure(stage, f'{label} changed during read')
        if 'sha256' in expected:
            if hashlib.sha256(raw).hexdigest() != expected['sha256']:
                raise _stage_failure(stage, f'{label} SHA mismatch')
    finally:
        os.close(fd)


def check_context_prestart_w5(op: dict, deadline: float, context_path: Path) -> None:
    """Pre-start DB/settings check. W5 context REQUIRED. Missing/invalid -> REJECT.
    No fallback. No automatic DB recapture. Old DB cold must match."""
    stage = W5Stage.CONTEXT
    if context_path is None:
        raise _stage_failure(stage, 'context file path is None (required)')
    if not context_path.exists():
        raise _stage_failure(stage, 'context file missing (required, no fallback)')
    ctx = validate_context_file_w5(context_path)

    for name, value in ctx['database_no_SQL'].items():
        p = Path(name)
        if value is None:
            if p.exists():
                raise _stage_failure(W5Stage.PRESERVE, f'DB companion {p.name} appeared before start')
        else:
            if not p.exists():
                raise _stage_failure(W5Stage.PRESERVE, f'DB {p.name} missing')
            _verify_file_metadata(p, value, f'DB {p.name}', W5Stage.PRESERVE)

    s = ctx['settings']
    sp = Path(s['path'])
    if not sp.exists():
        raise _stage_failure(W5Stage.PRESERVE, 'settings file missing')
    _verify_file_metadata(sp, s, 'settings', W5Stage.PRESERVE)


def check_context_runtime_w5(op: dict, deadline: float, context_path: Path) -> None:
    """Runtime (watch loop) checks. DB writes EXPECTED. Model/runtime/root/source strict."""
    preserve_continuation(op, deadline, full=False)


def phase_watch5(op: dict, literal: str, deadline: float, run_token: str, context_path: Path) -> None:
    """Watch5: check_material -> context_prestart -> stopped -> screen_lock -> watch5.ready
    -> loop: check_material -> context_runtime -> Restart gate -> screen_lock
    -> watch_decision (reads start5 markers) -> bounded contain."""
    directory = _op_dir(op)
    check_material(op, True)
    check_context_prestart_w5(op, deadline, context_path)
    for unit in APP_UNITS:
        b.stopped(unit, deadline)
    screen_lock_state(directory, deadline)

    proc = Path('/proc/self')
    b.write_new(
        directory / WATCH5_READY,
        b.encoded(dict(
            schema='hyprneuro.boundary-watch5-ready/1',
            operation_sha256=literal,
            run_token=run_token,
            pid=os.getpid(),
            start=proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
        ))
    )

    transient_started_at = None
    while time.monotonic() < deadline:
        check_material(op, True)
        check_context_runtime_w5(op, deadline, context_path)
        for unit in APP_UNITS:
            if b.show(unit, ('Restart',), deadline)['Restart'] != 'no':
                return contain(op)
        lock = screen_lock_state(directory, deadline)
        started = (directory / START5_STARTED).exists()
        completed = (directory / START5_COMPLETED).exists()
        if started and transient_started_at is None:
            transient_started_at = time.monotonic()
        live = {}
        receipt = None
        if completed:
            receipt = validate_start_receipt(
                json.loads(b.file_bytes(directory / START5_COMPLETED)),
                literal, op['generation']
            )
            for unit in APP_UNITS:
                live[unit] = full_identity(unit, deadline)
        watch_decision(receipt, live, lock, started, completed, transient_started_at, time.monotonic())
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return contain(op)


def phase_start5(op: dict, literal: str, deadline: float, run_token: str, context_path: Path) -> None:
    """Start5: watch5.ready validate (run_token/pid/uid/start/op) -> context_prestart
    -> check_material -> effective -> Restart=no -> screen_lock -> start5.started
    -> broker start -> listener gate -> recheck -> UI start -> full identity -> start5.completed."""
    directory = _op_dir(op)
    ready_raw = b.file_bytes(directory / WATCH5_READY)
    ready = json.loads(ready_raw)
    if ready.get('run_token') != run_token:
        raise _stage_failure(W5Stage.WATCH_READY_TOKEN, 'run_token mismatch')
    if ready.get('operation_sha256') != literal:
        raise _stage_failure(W5Stage.WATCH_READY_OP, 'operation SHA mismatch')
    proc = Path('/proc') / str(ready['pid'])
    if not proc.exists():
        raise _stage_failure(W5Stage.WATCH_READY_PID, 'watcher process dead')
    if ready.get('start') != proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]:
        raise _stage_failure(W5Stage.WATCH_READY_START, 'watcher start_ticks mismatch')
    if proc.stat().st_uid != os.getuid():
        raise _stage_failure(W5Stage.WATCH_READY_UID, 'watcher UID mismatch')

    check_context_prestart_w5(op, deadline, context_path)
    check_material(op, True)
    effective(op, deadline)

    for unit in APP_UNITS:
        if b.stopped(unit, deadline)['Restart'] != 'no':
            raise _stage_failure(W5Stage.RESTART, 'BOTH app Restart=no required')
    screen_lock_state(directory, deadline)

    path = Path('/run/user/1000/hyprharness/grant-control.sock')
    b.write_new(directory / START5_STARTED, (literal + '\n').encode())

    b.command(['/usr/bin/systemctl', '--user', 'start', APP_UNITS[0]], deadline)
    proof = wait_broker_listener(APP_UNITS[0], path, deadline)
    recheck_broker_listener(APP_UNITS[0], proof, deadline)
    b.command(['/usr/bin/systemctl', '--user', 'start', APP_UNITS[1]], deadline)

    broker_full = full_identity(APP_UNITS[0], deadline)
    ui_full = wait_app_active(APP_UNITS[1], deadline)
    if broker_full is None:
        raise _stage_failure(W5Stage.IDENTITY, 'Broker not verifiably active')

    b.write_new(
        directory / START5_COMPLETED,
        b.encoded(dict(
            schema='hyprneuro.boundary-start-receipt/1',
            operation_sha256=literal,
            generation=op['generation'],
            run_token=run_token,
            broker=broker_full,
            ui=ui_full
        ))
    )


def unit_evidence_5() -> list:
    """Actual 4-unit evidence: LoadState + MainPID. Socket N/A. Not found -> UNKNOWN."""
    evidence = []
    for unit in ALL_UNITS:
        entry = {'unit': unit}
        try:
            load_state = __import__('subprocess').run(
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
                pid = __import__('subprocess').run(
                    ['/usr/bin/systemctl', '--user', 'show', '-p', 'MainPID', '--value', unit],
                    capture_output=True, text=True, timeout=5
                ).stdout.strip()
                entry['MainPID'] = pid if pid and pid != '0' else 'UNKNOWN'
            except Exception:
                entry['MainPID'] = 'UNKNOWN'
        evidence.append(entry)
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation ops W5 (START ONLY)')
    parser.add_argument('--operation', type=Path, required=True)
    parser.add_argument('--operation-sha256', required=True)
    parser.add_argument('--phase', choices=('watch5', 'start5', 'contain'), required=True)
    parser.add_argument('--run-token', required=True, help='Fresh run token binding this attempt')
    parser.add_argument('--context', type=Path, required=True, help='Required W5 prospective postwrite context')
    args = parser.parse_args()

    op = load(args.operation, args.operation_sha256)
    literal = args.operation_sha256
    run_token = args.run_token
    context_path = args.context

    deadline = time.monotonic() + (600 if args.phase == 'watch5' else 180)

    try:
        if args.phase == 'watch5':
            result = phase_watch5(op, literal, deadline, run_token, context_path)
            if result:
                print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
                return
        elif args.phase == 'start5':
            phase_start5(op, literal, deadline, run_token, context_path)
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
