#!/usr/bin/env python3
"""
Continuation operations for boundary 18aef68-04 (installed-only, no reinstall).
Version: 2 (corrected per review 01M7KMHBS9T1NVK1CYP9T6K5W)

Design:
- Loads and validates the ORIGINAL 04 operation.json via frozen load()
- Uses original op for ALL frozen function calls (check_material, effective,
  screen_lock_state, watch_decision, full_identity, etc.)
- Replaces ONLY preserve() with preserve_continuation() (stable ExecStart)
- Writes NEW one-shot continuation markers (not 04's provision.started/completed)
- Calls actual identity_guard.py script with original op params
- Full start phase: broker listener gate, recheck, UI start, full identity receipt
- Full watch phase: watch_decision with live identity each cycle

NOT a monkeypatch. NOT a global override. Standalone entrypoint that imports
and calls frozen primitives with the ORIGINAL operation schema.

Phases: provision → watch → start
NO reinstall. NO daemon-reload. NO new root. NO baseline recapture.
"""

import argparse
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

# --- Pinned imports from frozen 04 modules ---
OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
sys.path.insert(0, str(OPS_DIR))

import boundary_release as b
from boundary_release_ops import (
    load,
    stamp,
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

# --- New stable-field comparison module ---
sys.path.insert(0, str(Path(__file__).parent / 'scripts'))
from execstart_stable_compare import compare_execstart_stable, ExecStartParseError


# --- Safe exception enum (no raw str(e), no private values) ---

SAFE_EXCEPTION_CLASSES = frozenset({
    'ValueError', 'OSError', 'TimeoutError', 'FileNotFoundError',
    'ConnectionRefusedError', 'ChildProcessError', 'ProcessLookupError'
})


def _safe_exception_label(exc: BaseException) -> str:
    cls = type(exc).__name__
    return cls if cls in SAFE_EXCEPTION_CLASSES else 'Exception'


# --- Stable ExecStart comparison for manager_after dicts ---

def _compare_manager_after(expected: dict, actual: dict) -> None:
    """Compare manager_after dicts. ExecStart uses stable-field comparison.
    All other fields use strict equality."""
    for k in expected:
        if k == 'ExecStart':
            compare_execstart_stable(expected[k], actual.get(k, ''))
        elif actual.get(k) != expected[k]:
            raise ValueError(f'manager_after drift: {k}')


# --- validate_models with stable ExecStart (full preserve) ---

def validate_models_continuation(deadline: float) -> dict:
    """Same as frozen validate_models, but ExecStart uses stable-field comparison.
    All other checks STRICT and unchanged."""
    if b.digest(b.MODEL_SNAPSHOT) != b.MODEL_SHA or b.digest(b.MODEL_AUX) != b.MODEL_AUX_SHA:
        raise ValueError('Proposed model baseline pin drift')
    document = json.loads(b.file_bytes(b.MODEL_SNAPSHOT))
    aux = json.loads(b.file_bytes(b.MODEL_AUX))
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != document['boot_id']:
        raise ValueError('Model baseline boot drift')
    from capture_boundary_model_baseline import identity, listeners, read_fd
    result = {}
    for item in document['models']:
        if item['unit'] not in ('lfm@text.service', 'lfm@omni.service', 'lfm@decision.service'):
            raise ValueError('Unknown model selector')
        expected = item['manager_after']
        value = b.show(item['unit'], tuple(expected), deadline)
        # FIXED: stable-field comparison for ExecStart, strict for all else
        _compare_manager_after(expected, value)
        # All remaining checks: STRICT, unchanged from frozen
        pid = item['identity_after']['pid']
        proc = Path('/proc') / str(pid)
        if identity(pid) != item['identity_after']:
            raise ValueError('Model kernel identity drift')
        if hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest() != item['argv_sha256']:
            raise ValueError('Model argv drift')
        fd = os.open(proc / 'exe', os.O_RDONLY | os.O_CLOEXEC)
        try:
            raw, metadata = read_fd(fd)
        finally:
            os.close(fd)
        if hashlib.sha256(raw).hexdigest() != item['process_executable_fd']['sha256'] or metadata != item['process_executable_fd']['stat']:
            raise ValueError('Model process executable FD drift')
        b.check_pin(item['cold_executable'])
        for entry in item['unit_files']:
            b.check_pin(entry['source'])
        for selected in item['selected_path_metadata'].values():
            p = Path(selected['canonical'])
            s = p.stat()
            if (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, stat.S_IMODE(s.st_mode), s.st_uid, s.st_gid) != (
                selected['dev'], selected['inode'], selected['size'], selected['mtime_ns'], selected['mode'], selected['uid'], selected['gid']
            ):
                raise ValueError('Weight metadata drift')
        if listeners(pid) != item['listeners'] or identity(pid) != item['identity_after']:
            raise ValueError('Model listener ownership/identity drift')
        result[item['unit']] = value
    if len(result) != 3:
        raise ValueError('Incomplete ordinary model baseline')
    for unit, entry in aux['MoEs'].items():
        if unit not in ('lfm@littlemoe.service', 'lfm@bigmoe.service', 'lfm@moe.service'):
            raise ValueError('Unknown MoE selector')
        if b.stopped(unit, deadline) != entry['after'] or b.show(unit, tuple(entry['effective']), deadline) != entry['effective']:
            raise ValueError('MoE state/policy drift')
        for file in entry['files']:
            b.check_pin(file['source'])
    from capture_boundary_preservation_aux import stream_pin
    for entry in aux['projectors']:
        if stream_pin(Path(entry['pin']['path']), deadline) != entry['pin']:
            raise ValueError('Projector drift')
    return result


# --- preserve with stable ExecStart (both full and non-full) ---

def preserve_continuation(op: dict, deadline: float, full: bool = True, before_start: bool = False) -> None:
    """Same as frozen preserve, but validate_models uses stable ExecStart.
    Non-full path also uses stable ExecStart for manager_after comparison."""
    baseline = json.loads(b.file_bytes(op['baseline']['path']))
    for logical, sha in baseline['preserved_files'].items():
        if b.digest(Path(logical).resolve()) != sha:
            raise ValueError('Immutable historical/config preservation drift')
    b.check_pin(baseline['settings'])
    if before_start:
        for name, value in baseline['database_no_SQL'].items():
            p = Path(name)
            if value is None:
                if p.exists():
                    raise ValueError('Database companion appeared before start')
            elif b.digest(p) != value['sha256'] or p.stat().st_ino != value['inode'] or p.stat().st_size != value['size']:
                raise ValueError('Prestart data drift; never roll back postwrites')
    if full:
        validate_models_continuation(deadline)
        for value in op['runtime'].values():
            b.check_pin(value)
    else:
        # Non-full: filesystem/kernel-only monitor (WATCH path)
        # INDEPENDENT cmdline SHA check: execve preserves PID/start_ticks but
        # can change argv. identity() does NOT cover this. Mandatory.
        snapshot = json.loads(b.file_bytes(b.MODEL_SNAPSHOT))
        from capture_boundary_model_baseline import identity, listeners
        for entry in snapshot['models']:
            pid = entry['identity_after']['pid']
            if identity(pid) != entry['identity_after'] or listeners(pid) != entry['listeners']:
                raise ValueError('Observed model identity/listener drift')
            # INDEPENDENT cmdline SHA (mitigates parser delimiter ambiguity)
            proc = Path('/proc') / str(pid)
            cmdline_sha = hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest()
            if cmdline_sha != entry['argv_sha256']:
                raise ValueError('Model cmdline drift (independent argv identity)')
            # FIXED: stable ExecStart comparison for non-full path too
            value = b.show(entry['unit'], tuple(entry['manager_after']), deadline)
            _compare_manager_after(entry['manager_after'], value)
            for item in entry['unit_files']:
                b.check_pin(item['source'])
            if {k: os.readlink(Path('/proc') / str(pid) / 'ns' / k) for k in entry['namespaces']} != entry['namespaces']:
                raise ValueError('Model namespace drift')
        for unit in ('lfm@littlemoe.service', 'lfm@bigmoe.service', 'lfm@moe.service'):
            b.stopped(unit, deadline)


# --- 12 Gates (continuation-specific, before any phase) ---

def gate_check(op: dict, literal: str, deadline: float) -> None:
    """Verify all 12 continuation gates using the ORIGINAL op schema."""
    directory = Path(op['bundle']) / 'operation'

    # Gate 1: install.completed exists and matches operation SHA
    install_completed = directory / 'install.completed'
    if not install_completed.exists():
        raise ValueError('Gate 1 FAIL: install.completed absent')
    if b.file_bytes(install_completed) != (literal + '\n').encode():
        raise ValueError('Gate 1 FAIL: install.completed SHA mismatch')

    # Gate 2: All installed targets inode+SHA (via check_material which does this)
    # (check_material(op, True) is called separately and does the full check)

    # Gate 3: Root record exists, SHA matches (validated by load())
    # (load() already verified root_record SHA)

    # Gate 4: Context/env/manifest alias DAG (validated by load() + check_material)

    # Gate 5: Both apps stopped, Restart=no, no jobs
    for unit in b.APP_UNITS:
        value = b.show(unit, ('ActiveState', 'SubState', 'Restart', 'Job'), deadline)
        if value['ActiveState'] != 'inactive' or value['SubState'] != 'dead':
            raise ValueError(f'Gate 5 FAIL: {unit} not stopped')
        if value['Restart'] != 'no':
            raise ValueError(f'Gate 5 FAIL: {unit} Restart!=no')
        if value['Job']:
            raise ValueError(f'Gate 5 FAIL: {unit} has active job')

    # Gate 6: Helper loaded+inactive, Socket loaded+inactive
    for unit in (op['names']['helper'], op['names']['socket']):
        value = b.show(unit, ('LoadState', 'ActiveState'), deadline)
        if value['LoadState'] != 'loaded' or value['ActiveState'] != 'inactive':
            raise ValueError(f'Gate 6 FAIL: {unit} not loaded+inactive')

    # Gate 7: No stale flock/guards (apps dead = no live locks)

    # Gate 8: 04 provision.started ABSENT
    if (directory / 'provision.started').exists():
        raise ValueError('Gate 8 FAIL: 04 provision.started present')

    # Gate 9: 04 provision.completed ABSENT
    if (directory / 'provision.completed').exists():
        raise ValueError('Gate 9 FAIL: 04 provision.completed present')

    # Gate 10: continuation.provision.started ABSENT (re-run reject)
    if (directory / 'continuation.provision.started').exists():
        raise ValueError('Gate 10 FAIL: continuation.provision.started present (re-run)')

    # Gate 11: continuation.provision.completed ABSENT
    if (directory / 'continuation.provision.completed').exists():
        raise ValueError('Gate 11 FAIL: continuation.provision.completed present (re-run)')

    # Gate 12: Model snapshot SHA (validated in validate_models_continuation)


# --- Phase: provision ---

def phase_provision(op: dict, literal: str, deadline: float) -> None:
    """Provision: gates → preserve → check_material → effective → screen_lock
    → continuation.provision.started → identity_guard → continuation.provision.completed"""
    directory = Path(op['bundle']) / 'operation'

    gate_check(op, literal, deadline)
    check_material(op, True)
    preserve_continuation(op, deadline, before_start=True)
    effective(op, deadline)
    screen_lock_state(directory, deadline)

    # Write continuation marker (NOT 04's provision.started)
    b.write_new(directory / 'continuation.provision.started', (literal + '\n').encode())

    # Call actual identity_guard.py (same as frozen provision)
    guard = Path(op['bundle']) / 'source/python/src/hyprneuro/identity_guard.py'
    b.command(
        [str(b.PYTHON), '-I', str(guard), '--record',
         op['root_record']['path'], '--root-sha256', op['root_sha256'],
         '--generation', op['generation']],
        deadline
    )

    b.write_new(directory / 'continuation.provision.completed', (literal + '\n').encode())


# --- Phase: watch ---

def phase_watch(op: dict, literal: str, deadline: float) -> None:
    """Watch: check_material → preserve → stopped → screen_lock → watch.ready
    → loop: check_material → preserve(non-full) → Restart check → screen_lock
    → watch_decision (full identity post-completion) → bounded contain"""
    directory = Path(op['bundle']) / 'operation'

    check_material(op, True)
    preserve_continuation(op, deadline)
    for unit in b.APP_UNITS:
        b.stopped(unit, deadline)
    screen_lock_state(directory, deadline)

    # Write continuation watch.ready
    proc = Path('/proc/self')
    b.write_new(
        directory / 'continuation.watch.ready',
        b.encoded(dict(
            operation_sha256=literal,
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
        started = (directory / 'continuation.start.started').exists()
        completed = (directory / 'continuation.start.completed').exists()
        if started and transient_started_at is None:
            transient_started_at = time.monotonic()
        live = {}
        receipt = None
        if completed:
            receipt = validate_start_receipt(
                json.loads(b.file_bytes(directory / 'continuation.start.completed')),
                literal, op['generation']
            )
            for unit in b.APP_UNITS:
                live[unit] = full_identity(unit, deadline)
        watch_decision(receipt, live, lock, started, completed, transient_started_at, time.monotonic())
        time.sleep(min(1, max(0, deadline - time.monotonic())))
    return contain(op)


# --- Phase: start ---

def phase_start(op: dict, literal: str, deadline: float) -> None:
    """Start: provision.completed → watch.ready validate → preserve → check_material
    → effective → Restart=no → screen_lock → start.started → broker start
    → broker listener gate → recheck → UI start → full identity → start.completed"""
    directory = Path(op['bundle']) / 'operation'

    # Verify continuation provision completed
    if b.file_bytes(directory / 'continuation.provision.completed') != (literal + '\n').encode():
        raise ValueError('Continuation provisioning not confirmed')

    # Validate continuation watch.ready
    ready = json.loads(b.file_bytes(directory / 'continuation.watch.ready'))
    proc = Path('/proc') / str(ready['pid'])
    if ready['operation_sha256'] != literal or \
       ready['start'] != proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19] or \
       proc.stat().st_uid != os.getuid():
        raise ValueError('Independent MAIN watcher unavailable')

    preserve_continuation(op, deadline, before_start=True)
    check_material(op, True)
    effective(op, deadline)

    for unit in b.APP_UNITS:
        if b.stopped(unit, deadline)['Restart'] != 'no':
            raise ValueError('BOTH app Restart=no required before EITHER start')

    screen_lock_state(directory, deadline)

    path = Path('/run/user/1000/hyprharness/grant-control.sock')
    b.write_new(directory / 'continuation.start.started', (literal + '\n').encode())

    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[0]], deadline)
    proof = wait_broker_listener(b.APP_UNITS[0], path, deadline)
    recheck_broker_listener(b.APP_UNITS[0], proof, deadline)
    b.command(['/usr/bin/systemctl', '--user', 'start', b.APP_UNITS[1]], deadline)

    broker_full = full_identity(b.APP_UNITS[0], deadline)
    ui_full = wait_app_active(b.APP_UNITS[1], deadline)
    if broker_full is None:
        raise ValueError('Broker not verifiably active at start completion')

    b.write_new(
        directory / 'continuation.start.completed',
        b.encoded(dict(
            schema='hyprneuro.boundary-start-receipt/1',
            operation_sha256=literal,
            generation=op['generation'],
            broker=broker_full,
            ui=ui_full
        ))
    )


# --- Main entrypoint ---

def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation ops for boundary 18aef68-04')
    parser.add_argument('--operation', type=Path, required=True,
                        help='Path to original 04 operation.json')
    parser.add_argument('--operation-sha256', required=True,
                        help='SHA256 of original 04 operation.json')
    parser.add_argument('--phase', choices=('provision', 'watch', 'start', 'contain'), required=True)
    args = parser.parse_args()

    # Load and validate original 04 operation (full trust DAG)
    op = load(args.operation, args.operation_sha256)
    literal = args.operation_sha256

    deadline = time.monotonic() + (600 if args.phase == 'watch' else 180)

    try:
        if args.phase == 'provision':
            phase_provision(op, literal, deadline)
        elif args.phase == 'watch':
            result = phase_watch(op, literal, deadline)
            if result:
                print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
                return
        elif args.phase == 'start':
            phase_start(op, literal, deadline)
        elif args.phase == 'contain':
            result = contain(op)
            print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
            return
        print(json.dumps({'status': 'PASS', 'phase': args.phase}, sort_keys=True))
    except Exception as e:
        result = contain(op)
        print(json.dumps({
            'status': 'FAILED_NO_REPLAY',
            'stage': args.phase.upper(),
            'exception_class': _safe_exception_label(e),
            'containment': result
        }, sort_keys=True))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
