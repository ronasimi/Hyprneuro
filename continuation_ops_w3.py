#!/usr/bin/env python3
"""
Continuation ops W3: START ONLY (watch3 + start3 phases).
Minimal clone of v5 ops with new concurrent-phase markers.

- Preserves ALL old markers (install, provision, watch.ready) immutable
- New one-shot markers: continuation.watch3.ready, continuation.start3.started, continuation.start3.completed
- Fresh run_token binds ready/start receipts to this specific attempt
- Uses frozen v5 preserve_continuation (pinned import, no worktree fallback)
- NO gate_check (incompatible with already-provisioned state)
- NO deletion of any existing marker
- NO re-provision, NO guard, NO install

Phases: watch3 → start3
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time
import uuid
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


# --- W2 marker names (new, one-shot, NOT reuse old) ---

WATCH3_READY = 'continuation.watch3.ready'
START3_STARTED = 'continuation.start3.started'
START3_COMPLETED = 'continuation.start3.completed'


def _op_dir(op: dict) -> Path:
    return Path(op['bundle']) / 'operation'


# --- Phase: watch3 ---

def phase_watch3(op: dict, literal: str, deadline: float, run_token: str) -> None:
    """Watch3: check_material → preserve → stopped → screen_lock → watch3.ready
    → loop: check_material → preserve(non-full) → Restart → screen_lock
    → watch_decision (reads start3 markers) → bounded contain"""
    directory = _op_dir(op)

    check_material(op, True)
    preserve_continuation(op, deadline)
    for unit in b.APP_UNITS:
        b.stopped(unit, deadline)
    screen_lock_state(directory, deadline)

    # Write watch3.ready with run_token (new marker, NOT old watch.ready)
    proc = Path('/proc/self')
    b.write_new(
        directory / WATCH3_READY,
        b.encoded(dict(
            schema='hyprneuro.boundary-watch3-ready/1',
            operation_sha256=literal,
            run_token=run_token,
            pid=os.getpid(),
            start=proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]
        ))
    )

    transient_started_at = None
    while time.monotonic() < deadline:
        check_material(op, True)
        preserve_continuation(op, deadline, full=False)
        for unit in b.APP_UNITS:
            if b.show(unit, ('Restart',), deadline)['Restart'] != 'no':
                return contain(op)
        lock = screen_lock_state(directory, deadline)
        started = (directory / START3_STARTED).exists()
        completed = (directory / START3_COMPLETED).exists()
        if started and transient_started_at is None:
            transient_started_at = time.monotonic()
        live = {}
        receipt = None
        if completed:
            receipt = validate_start_receipt(
                json.loads(b.file_bytes(directory / START3_COMPLETED)),
                literal, op['generation']
            )
            for unit in b.APP_UNITS:
                live[unit] = full_identity(unit, deadline)
        watch_decision(receipt, live, lock, started, completed, transient_started_at, time.monotonic())
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return contain(op)


# --- Phase: start3 ---

def phase_start3(op: dict, literal: str, deadline: float, run_token: str) -> None:
    """Start3: watch3.ready validate (run_token) → preserve → check_material
    → effective → Restart=no → screen_lock → start3.started → broker start
    → broker listener gate → recheck → UI start → full identity → start3.completed"""
    directory = _op_dir(op)

    # Validate watch3.ready (new marker, check run_token)
    ready_raw = b.file_bytes(directory / WATCH3_READY)
    ready = json.loads(ready_raw)
    if ready.get('run_token') != run_token:
        raise ValueError('watch3.ready run_token mismatch')
    if ready.get('operation_sha256') != literal:
        raise ValueError('watch3.ready operation SHA mismatch')
    proc = Path('/proc') / str(ready['pid'])
    if not proc.exists():
        raise ValueError('watch3 watcher process dead')
    if ready.get('start') != proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]:
        raise ValueError('watch3 watcher start_ticks mismatch')
    if proc.stat().st_uid != os.getuid():
        raise ValueError('watch3 watcher UID mismatch')

    preserve_continuation(op, deadline, before_start=True)
    check_material(op, True)
    effective(op, deadline)

    for unit in b.APP_UNITS:
        if b.stopped(unit, deadline)['Restart'] != 'no':
            raise ValueError('BOTH app Restart=no required before EITHER start')

    screen_lock_state(directory, deadline)

    path = Path('/run/user/1000/hyprharness/grant-control.sock')
    b.write_new(directory / START3_STARTED, (literal + '\n').encode())

    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[0]], deadline)
    proof = wait_broker_listener(b.APP_UNITS[0], path, deadline)
    recheck_broker_listener(b.APP_UNITS[0], proof, deadline)
    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[1]], deadline)

    broker_full = full_identity(b.APP_UNITS[0], deadline)
    ui_full = wait_app_active(b.APP_UNITS[1], deadline)
    if broker_full is None:
        raise ValueError('Broker not verifiably active at start completion')

    b.write_new(
        directory / START3_COMPLETED,
        b.encoded(dict(
            schema='hyprneuro.boundary-start-receipt/1',
            operation_sha256=literal,
            generation=op['generation'],
            run_token=run_token,
            broker=broker_full,
            ui=ui_full
        ))
    )


# --- Main entrypoint ---

def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation ops W2 (START ONLY)')
    parser.add_argument('--operation', type=Path, required=True)
    parser.add_argument('--operation-sha256', required=True)
    parser.add_argument('--phase', choices=('watch3', 'start3', 'contain'), required=True)
    parser.add_argument('--run-token', required=True, help='Fresh run token binding this attempt')
    args = parser.parse_args()

    op = load(args.operation, args.operation_sha256)
    literal = args.operation_sha256
    run_token = args.run_token

    deadline = time.monotonic() + (600 if args.phase == 'watch3' else 180)

    try:
        if args.phase == 'watch3':
            result = phase_watch3(op, literal, deadline, run_token)
            if result:
                print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
                return
        elif args.phase == 'start3':
            phase_start3(op, literal, deadline, run_token)
        elif args.phase == 'contain':
            result = contain(op)
            print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
            return
        print(json.dumps({'status': 'PASS', 'phase': args.phase, 'run_token': run_token}, sort_keys=True))
    except Exception as e:
        result = contain(op)
        print(json.dumps({
            'status': 'FAILED_NO_REPLAY',
            'stage': args.phase.upper(),
            'exception_class': _safe_exception_label(e),
            'run_token': run_token,
            'containment': result
        }, sort_keys=True))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
