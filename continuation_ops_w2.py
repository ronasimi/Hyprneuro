#!/usr/bin/env python3
"""
Continuation ops W2: START ONLY (watch2 + start2 phases).
Minimal clone of v5 ops with new concurrent-phase markers.

- Preserves ALL old markers (install, provision, watch.ready) immutable
- New one-shot markers: continuation.watch2.ready, continuation.start2.started, continuation.start2.completed
- Fresh run_token binds ready/start receipts to this specific attempt
- Uses frozen v5 preserve_continuation (pinned import, no worktree fallback)
- NO gate_check (incompatible with already-provisioned state)
- NO deletion of any existing marker
- NO re-provision, NO guard, NO install

Phases: watch2 → start2
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

WATCH2_READY = 'continuation.watch2.ready'
START2_STARTED = 'continuation.start2.started'
START2_COMPLETED = 'continuation.start2.completed'


def _op_dir(op: dict) -> Path:
    return Path(op['bundle']) / 'operation'


# --- Phase: watch2 ---

def phase_watch2(op: dict, literal: str, deadline: float, run_token: str) -> None:
    """Watch2: check_material → preserve → stopped → screen_lock → watch2.ready
    → loop: check_material → preserve(non-full) → Restart → screen_lock
    → watch_decision (reads start2 markers) → bounded contain"""
    directory = _op_dir(op)

    check_material(op, True)
    preserve_continuation(op, deadline)
    for unit in b.APP_UNITS:
        b.stopped(unit, deadline)
    screen_lock_state(directory, deadline)

    # Write watch2.ready with run_token (new marker, NOT old watch.ready)
    proc = Path('/proc/self')
    b.write_new(
        directory / WATCH2_READY,
        b.encoded(dict(
            schema='hyprneuro.boundary-watch2-ready/1',
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
        started = (directory / START2_STARTED).exists()
        completed = (directory / START2_COMPLETED).exists()
        if started and transient_started_at is None:
            transient_started_at = time.monotonic()
        live = {}
        receipt = None
        if completed:
            receipt = validate_start_receipt(
                json.loads(b.file_bytes(directory / START2_COMPLETED)),
                literal, op['generation']
            )
            for unit in b.APP_UNITS:
                live[unit] = full_identity(unit, deadline)
        watch_decision(receipt, live, lock, started, completed, transient_started_at, time.monotonic())
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return contain(op)


# --- Phase: start2 ---

def phase_start2(op: dict, literal: str, deadline: float, run_token: str) -> None:
    """Start2: watch2.ready validate (run_token) → preserve → check_material
    → effective → Restart=no → screen_lock → start2.started → broker start
    → broker listener gate → recheck → UI start → full identity → start2.completed"""
    directory = _op_dir(op)

    # Validate watch2.ready (new marker, check run_token)
    ready_raw = b.file_bytes(directory / WATCH2_READY)
    ready = json.loads(ready_raw)
    if ready.get('run_token') != run_token:
        raise ValueError('watch2.ready run_token mismatch')
    if ready.get('operation_sha256') != literal:
        raise ValueError('watch2.ready operation SHA mismatch')
    proc = Path('/proc') / str(ready['pid'])
    if not proc.exists():
        raise ValueError('watch2 watcher process dead')
    if ready.get('start') != proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]:
        raise ValueError('watch2 watcher start_ticks mismatch')
    if proc.stat().st_uid != os.getuid():
        raise ValueError('watch2 watcher UID mismatch')

    preserve_continuation(op, deadline, before_start=True)
    check_material(op, True)
    effective(op, deadline)

    for unit in b.APP_UNITS:
        if b.stopped(unit, deadline)['Restart'] != 'no':
            raise ValueError('BOTH app Restart=no required before EITHER start')

    screen_lock_state(directory, deadline)

    path = Path('/run/user/1000/hyprharness/grant-control.sock')
    b.write_new(directory / START2_STARTED, (literal + '\n').encode())

    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[0]], deadline)
    proof = wait_broker_listener(b.APP_UNITS[0], path, deadline)
    recheck_broker_listener(b.APP_UNITS[0], proof, deadline)
    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[1]], deadline)

    broker_full = full_identity(b.APP_UNITS[0], deadline)
    ui_full = wait_app_active(b.APP_UNITS[1], deadline)
    if broker_full is None:
        raise ValueError('Broker not verifiably active at start completion')

    b.write_new(
        directory / START2_COMPLETED,
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
    parser.add_argument('--phase', choices=('watch2', 'start2', 'contain'), required=True)
    parser.add_argument('--run-token', required=True, help='Fresh run token binding this attempt')
    args = parser.parse_args()

    op = load(args.operation, args.operation_sha256)
    literal = args.operation_sha256
    run_token = args.run_token

    deadline = time.monotonic() + (600 if args.phase == 'watch2' else 180)

    try:
        if args.phase == 'watch2':
            result = phase_watch2(op, literal, deadline, run_token)
            if result:
                print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
                return
        elif args.phase == 'start2':
            phase_start2(op, literal, deadline, run_token)
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
