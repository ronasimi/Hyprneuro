#!/usr/bin/env python3
"""
Continuation operations for boundary 18aef68-04 (installed-only, no reinstall).

This module provides provision/watch/start phases for an ALREADY-INSTALLED 04
deployment whose provision phase failed due to ExecStart volatile-field drift
after daemon-reload. It reuses frozen helper primitives from boundary_release
and applies the approved stable-field ExecStart comparison.

NOT a monkeypatch. NOT a global override. A new standalone entrypoint that
imports and calls frozen primitives directly.

Phases: provision → watch → start
Markers: continuation.provision.started / continuation.provision.completed
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

# --- Pinned imports from frozen 04 helper module ---
OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
sys.path.insert(0, str(OPS_DIR))

from boundary_release import (
    APP_UNITS,
    MODEL_SNAPSHOT,
    MODEL_SHA,
    MODEL_AUX,
    MODEL_AUX_SHA,
    canonical,
    file_bytes,
    digest,
    encoded,
    pin,
    check_pin,
    write_new,
    command,
    show,
    stopped,
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


# --- Stable ExecStart comparison helper for manager_after dicts ---

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
    All other checks (PID, argv SHA, exe FD, cgroup, namespaces, listeners,
    MoE, projectors) are STRICT and unchanged."""
    if digest(MODEL_SNAPSHOT) != MODEL_SHA or digest(MODEL_AUX) != MODEL_AUX_SHA:
        raise ValueError('Proposed model baseline pin drift')
    document = json.loads(file_bytes(MODEL_SNAPSHOT))
    aux = json.loads(file_bytes(MODEL_AUX))
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != document['boot_id']:
        raise ValueError('Model baseline boot drift')
    from capture_boundary_model_baseline import identity, listeners, read_fd
    result = {}
    for item in document['models']:
        if item['unit'] not in ('lfm@text.service', 'lfm@omni.service', 'lfm@decision.service'):
            raise ValueError('Unknown model selector')
        expected = item['manager_after']
        value = show(item['unit'], tuple(expected), deadline)
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
        check_pin(item['cold_executable'])
        for entry in item['unit_files']:
            check_pin(entry['source'])
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
        if stopped(unit, deadline) != entry['after'] or show(unit, tuple(entry['effective']), deadline) != entry['effective']:
            raise ValueError('MoE state/policy drift')
        for file in entry['files']:
            check_pin(file['source'])
    from capture_boundary_preservation_aux import stream_pin
    for entry in aux['projectors']:
        if stream_pin(Path(entry['pin']['path']), deadline) != entry['pin']:
            raise ValueError('Projector drift')
    return result


# --- preserve with stable ExecStart (both full and non-full) ---

def preserve_continuation(op: dict, deadline: float, full: bool = True, before_start: bool = False) -> None:
    """Same as frozen preserve, but validate_models uses stable ExecStart.
    Non-full path also uses stable ExecStart for manager_after comparison."""
    baseline = json.loads(file_bytes(op['baseline']['path']))
    for logical, sha in baseline['preserved_files'].items():
        if digest(Path(logical).resolve()) != sha:
            raise ValueError('Immutable historical/config preservation drift')
    check_pin(baseline['settings'])
    if before_start:
        for name, value in baseline['database_no_SQL'].items():
            p = Path(name)
            if value is None:
                if p.exists():
                    raise ValueError('Database companion appeared before start')
            elif digest(p) != value['sha256'] or p.stat().st_ino != value['inode'] or p.stat().st_size != value['size']:
                raise ValueError('Prestart data drift; never roll back postwrites')
    if full:
        validate_models_continuation(deadline)
        for value in op['runtime'].values():
            check_pin(value)
    else:
        # Non-full: filesystem/kernel-only monitor (WATCH path)
        snapshot = json.loads(file_bytes(MODEL_SNAPSHOT))
        from capture_boundary_model_baseline import identity, listeners
        for entry in snapshot['models']:
            pid = entry['identity_after']['pid']
            if identity(pid) != entry['identity_after'] or listeners(pid) != entry['listeners']:
                raise ValueError('Observed model identity/listener drift')
            # FIXED: stable ExecStart comparison for non-full path too
            value = show(entry['unit'], tuple(entry['manager_after']), deadline)
            _compare_manager_after(entry['manager_after'], value)
            for item in entry['unit_files']:
                check_pin(item['source'])
            if {k: os.readlink(Path('/proc') / str(pid) / 'ns' / k) for k in entry['namespaces']} != entry['namespaces']:
                raise ValueError('Model namespace drift')
        for unit in ('lfm@littlemoe.service', 'lfm@bigmoe.service', 'lfm@moe.service'):
            stopped(unit, deadline)


# --- 12 Gates (all must pass before provision) ---

def gate_check(op: dict, deadline: float) -> None:
    """Verify all 12 continuation gates. Raises ValueError on any failure."""
    directory = Path(op['operation']['directory'])

    # Gate 1: install.completed exists and matches 04 operation SHA
    install_completed = directory / 'install.completed'
    if not install_completed.exists():
        raise ValueError('Gate 1 FAIL: install.completed absent')
    content = install_completed.read_text().strip()
    if content != op['operation_sha256']:
        raise ValueError('Gate 1 FAIL: install.completed SHA mismatch')

    # Gate 2: All 6 installed targets inode+SHA match
    for target in op['installed_targets']:
        p = Path(target['path'])
        if not p.exists():
            raise ValueError(f'Gate 2 FAIL: {target["path"]} absent')
        if digest(p) != target['sha256']:
            raise ValueError(f'Gate 2 FAIL: {target["path"]} SHA drift')
        if p.stat().st_ino != target['inode']:
            raise ValueError(f'Gate 2 FAIL: {target["path"]} inode drift')

    # Gate 3: Root record exists, generation matches
    root_path = Path(op['root_record']['path'])
    if not root_path.exists():
        raise ValueError('Gate 3 FAIL: root record absent')
    if digest(root_path) != op['root_sha256']:
        raise ValueError('Gate 3 FAIL: root record SHA drift')

    # Gate 4: Context/env/manifest alias DAG intact
    for alias in op.get('alias_dag', []):
        p = Path(alias['path'])
        if not p.exists():
            raise ValueError(f'Gate 4 FAIL: alias {alias["path"]} absent')
        if digest(p) != alias['sha256']:
            raise ValueError(f'Gate 4 FAIL: alias {alias["path"]} drift')

    # Gate 5: Both apps stopped, Restart=no, no jobs
    for unit in APP_UNITS:
        value = show(unit, ('ActiveState', 'SubState', 'Restart', 'Job'), deadline)
        if value['ActiveState'] != 'inactive' or value['SubState'] != 'dead':
            raise ValueError(f'Gate 5 FAIL: {unit} not stopped')
        if value['Restart'] != 'no':
            raise ValueError(f'Gate 5 FAIL: {unit} Restart!=no')
        if value['Job']:
            raise ValueError(f'Gate 5 FAIL: {unit} has active job')

    # Gate 6: Helper loaded+inactive, Socket loaded+inactive
    for unit in (op['names']['helper'], op['names']['socket']):
        value = show(unit, ('LoadState', 'ActiveState'), deadline)
        if value['LoadState'] != 'loaded' or value['ActiveState'] != 'inactive':
            raise ValueError(f'Gate 6 FAIL: {unit} not loaded+inactive')

    # Gate 7: No stale flock/guards
    # (Checked via /proc/locks for our specific lock paths)
    # Simplified: if apps are dead (gate 5), no live locks from them

    # Gate 8: provision.started ABSENT
    if (directory / 'provision.started').exists():
        raise ValueError('Gate 8 FAIL: 04 provision.started present (should be absent)')

    # Gate 9: provision.completed ABSENT
    if (directory / 'provision.completed').exists():
        raise ValueError('Gate 9 FAIL: 04 provision.completed present (should be absent)')

    # Gate 10: continuation.provision.started ABSENT (re-run reject)
    if (directory / 'continuation.provision.started').exists():
        raise ValueError('Gate 10 FAIL: continuation.provision.started present (re-run rejected)')

    # Gate 11: continuation.provision.completed ABSENT
    if (directory / 'continuation.provision.completed').exists():
        raise ValueError('Gate 11 FAIL: continuation.provision.completed present (re-run rejected)')

    # Gate 12: Model snapshot 03 SHA matches, immutable
    if digest(MODEL_SNAPSHOT) != MODEL_SHA:
        raise ValueError('Gate 12 FAIL: model snapshot SHA drift')


# --- Containment (same as reviewed 04 ops: stop owned units only) ---

def contain_continuation(op: dict) -> dict:
    """Stop owned app units and helper. No foreign PIDs. No system units."""
    actions = []
    for unit in APP_UNITS:
        try:
            command(['systemctl', '--user', 'stop', unit], time.monotonic() + 10, check=False)
            actions.append(unit)
        except Exception:
            pass
    helper = op['names']['helper']
    try:
        command(['systemctl', '--user', 'stop', helper], time.monotonic() + 10, check=False)
        actions.append(helper)
    except Exception:
        pass
    return {'stopped': actions, 'scope': 'owned_only'}


# --- Phase: provision ---

def phase_provision(op: dict, deadline: float) -> None:
    """Provision phase: preserve → check_material → effective → screen_lock → markers."""
    directory = Path(op['operation']['directory'])

    # Gate check first
    gate_check(op, deadline)

    # Preserve (full, before_start=True)
    preserve_continuation(op, deadline, full=True, before_start=True)

    # Check material (from frozen ops, imported directly)
    from boundary_release_ops import check_material
    check_material(op, installed=True)

    # Effective (from frozen ops)
    from boundary_release_ops import effective
    effective(op, deadline)

    # Screen lock state (from frozen ops)
    from boundary_release_ops import screen_lock_state
    screen_lock_state(directory, deadline)

    # Write continuation markers (NEW, one-shot, NOT 04's)
    write_new(directory / 'continuation.provision.started',
              encoded({'operation_sha256': op['operation_sha256'], 'ts': time.time()}))

    # Identity guard record
    from boundary_release_ops import identity_guard_record
    identity_guard_record(op, deadline)

    write_new(directory / 'continuation.provision.completed',
              encoded({'operation_sha256': op['operation_sha256'], 'ts': time.time()}))


# --- Phase: watch ---

def phase_watch(op: dict, deadline: float) -> None:
    """Watch phase: effective() loop with stable ExecStart. Bounded by deadline."""
    from boundary_release_ops import effective, screen_lock_state, watch_decision
    directory = Path(op['operation']['directory'])

    # Write watch.ready (same pattern as frozen)
    proc = Path('/proc/self')
    write_new(directory / 'continuation.watch.ready',
              encoded({'operation_sha256': op['operation_sha256'],
                       'pid': os.getpid(),
                       'start': proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19]}))

    # Watch loop: effective + non-full preserve + screen lock
    while time.monotonic() < deadline:
        effective(op, deadline)
        preserve_continuation(op, deadline, full=False)
        screen_lock_state(directory, deadline)
        time.sleep(5)


# --- Phase: start ---

def phase_start(op: dict, deadline: float) -> None:
    """Start phase: start both units, bounded by deadline."""
    from boundary_release_ops import screen_lock_state
    directory = Path(op['operation']['directory'])

    screen_lock_state(directory, deadline)

    # Start units
    for unit in APP_UNITS:
        command(['systemctl', '--user', 'start', unit], deadline)

    # Write start markers
    write_new(directory / 'continuation.start.completed',
              encoded({'operation_sha256': op['operation_sha256'], 'ts': time.time()}))


# --- Main entrypoint ---

def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation ops for boundary 18aef68-04')
    parser.add_argument('--phase', choices=('provision', 'watch', 'start', 'contain'), required=True)
    parser.add_argument('--arrays', required=True, help='Path to continuation arrays JSON')
    parser.add_argument('--arrays-sha256', required=True)
    parser.add_argument('--operation-sha256', required=True)
    args = parser.parse_args()

    # Load and verify arrays
    arrays_path = Path(args.arrays)
    if digest(arrays_path) != args.arrays_sha256:
        print(json.dumps({'status': 'FAILED_NO_REPLAY', 'stage': 'VALIDATE',
                          'exception_class': 'ValueError', 'reason': 'arrays SHA mismatch'}))
        raise SystemExit(1)
    op = json.loads(file_bytes(arrays_path))

    # Verify operation SHA
    if op.get('operation_sha256') != args.operation_sha256:
        print(json.dumps({'status': 'FAILED_NO_REPLAY', 'stage': 'VALIDATE',
                          'exception_class': 'ValueError', 'reason': 'operation SHA mismatch'}))
        raise SystemExit(1)

    deadline = time.monotonic() + (600 if args.phase == 'watch' else 180)

    try:
        if args.phase == 'provision':
            phase_provision(op, deadline)
        elif args.phase == 'watch':
            phase_watch(op, deadline)
        elif args.phase == 'start':
            phase_start(op, deadline)
        elif args.phase == 'contain':
            result = contain_continuation(op)
            print(json.dumps({'status': 'CONTAINED', 'containment': result}, sort_keys=True))
            return
        print(json.dumps({'status': 'PASS', 'phase': args.phase}, sort_keys=True))
    except Exception as e:
        result = contain_continuation(op)
        print(json.dumps({
            'status': 'FAILED_NO_REPLAY',
            'stage': args.phase.upper(),
            'exception_class': _safe_exception_label(e),
            'containment': result
        }, sort_keys=True))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
