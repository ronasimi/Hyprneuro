#!/usr/bin/env python3
"""
Continuation runner W2: START ONLY, ACTUAL CONCURRENT pattern.
Version: 1 (new, not a clone of v5 sequential runner)

Pattern (from v2 parent runner, READ and adapted):
  1. Verify pins + preconditions (readonly)
  2. Launch watch2 as CHILD Popen (descendant, no independent lease)
  3. Bounded wait (90s) for valid watch2.ready (PID match, run_token)
  4. Launch start2 as Popen with CONCURRENT watcher monitoring
  5. Post-start bounded supervision (remaining 600s since watch2 launch)
  6. Any failure: terminate owned start (5s reap) → contain → terminate watch

NOT sequential. NOT blocking run_phase. Real Popen concurrent monitor.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

# --- FROZEN literal pins ---

PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'

# Frozen W2 code paths
W2_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w2')
OPS_W2_PATH = W2_DIR / 'continuation_ops_w2.py'
OPS_W2_SHA = None  # Set at freeze time
COMPARATOR_PATH = W2_DIR / 'scripts' / 'execstart_stable_compare.py'
COMPARATOR_SHA = None  # Set at freeze time
V5_OPS_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/continuation_ops.py')
V5_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'

AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution-w2')
OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
PHASE_CHECK_INTERVAL = 1
WATCH_READY_TIMEOUT = 90
WATCH_DEADLINE = 600

_SHA_HEX = set('0123456789abcdef')


def _valid_sha(s) -> bool:
    if not isinstance(s, str) or len(s) != 64:
        return False
    return all(c in _SHA_HEX for c in s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_pins() -> None:
    """Verify all frozen code pins. Raises on any issue."""
    if not _valid_sha(OPERATION_SHA):
        raise ValueError('OPERATION_SHA malformed')
    if not _valid_sha(V5_OPS_SHA):
        raise ValueError('V5_OPS_SHA malformed')
    if OPS_W2_SHA is not None and not _valid_sha(OPS_W2_SHA):
        raise ValueError('OPS_W2_SHA malformed')
    if COMPARATOR_SHA is not None and not _valid_sha(COMPARATOR_SHA):
        raise ValueError('COMPARATOR_SHA malformed')

    if not OPERATION_PATH.exists():
        raise ValueError('Operation path missing')
    if sha256_file(OPERATION_PATH) != OPERATION_SHA:
        raise ValueError('Operation SHA mismatch')
    if not V5_OPS_PATH.exists():
        raise ValueError('v5 ops path missing')
    if sha256_file(V5_OPS_PATH) != V5_OPS_SHA:
        raise ValueError('v5 ops SHA mismatch')
    if OPS_W2_PATH.exists() and OPS_W2_SHA is not None:
        if sha256_file(OPS_W2_PATH) != OPS_W2_SHA:
            raise ValueError('W2 ops SHA mismatch')
    if COMPARATOR_PATH.exists() and COMPARATOR_SHA is not None:
        if sha256_file(COMPARATOR_PATH) != COMPARATOR_SHA:
            raise ValueError('comparator SHA mismatch')


def verify_preconditions() -> None:
    """Verify START ONLY preconditions (readonly). NO writes."""
    op_dir = OP_DIR

    # provision.completed must exist with correct SHA
    prov_completed = op_dir / 'continuation.provision.completed'
    if not prov_completed.exists():
        raise ValueError('Precondition FAIL: continuation.provision.completed absent')
    content = prov_completed.read_text().strip()
    if content != OPERATION_SHA:
        raise ValueError('Precondition FAIL: provision.completed SHA mismatch')

    # New W2 markers must be ABSENT (fresh attempt)
    for marker in ('continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed'):
        if (op_dir / marker).exists():
            raise ValueError(f'Precondition FAIL: {marker} already present (not a fresh attempt)')

    # Old markers must be intact (not deleted)
    for marker in ('install.completed', 'install.started', 'session.pin',
                   'continuation.provision.started', 'continuation.provision.completed',
                   'continuation.watch.ready'):
        if not (op_dir / marker).exists():
            raise ValueError(f'Precondition FAIL: old marker {marker} missing')


def _op_argv(phase: str, run_token: str) -> list:
    return [
        PYTHON, '-I', str(OPS_W2_PATH),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
        '--run-token', run_token,
    ]


def _validate_watch2_ready(path: Path, expected_pid: int, expected_token: str, expected_sha: str) -> bool:
    """Validate watch2.ready content: PID, run_token, op SHA, start_ticks."""
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return False
    if data.get('pid') != expected_pid:
        return False
    if data.get('run_token') != expected_token:
        return False
    if data.get('operation_sha256') != expected_sha:
        return False
    # Verify start_ticks against /proc
    proc = Path('/proc') / str(expected_pid)
    if not proc.exists():
        return False
    try:
        stat_fields = proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()
        if data.get('start') != stat_fields[19]:
            return False
    except (OSError, IndexError):
        return False
    return True


def main() -> None:
    verify_pins()
    verify_preconditions()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)

    run_token = uuid.uuid4().hex
    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner-w2/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'run_token': run_token,
        'operation_sha256': OPERATION_SHA,
        'phases': []
    }

    # --- Launch watch2 as CHILD Popen (concurrent, not blocking) ---
    watch_argv = _op_argv('watch2', run_token)
    watch_log = open(AUDIT_DIR / 'watch2.log', 'w')
    watch_log.write(f'=== watch2 (child Popen) ===\nargv: {json.dumps(watch_argv)}\nrun_token: {run_token}\n')
    watch_log.flush()

    watcher = subprocess.Popen(watch_argv, shell=False, stdout=watch_log, stderr=subprocess.STDOUT)
    receipt['phases'].append({'phase': 'watch2_launch', 'pid': watcher.pid})

    # --- Bounded wait for valid watch2.ready ---
    watch2_ready_path = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation/continuation.watch2.ready')
    ready_deadline = time.monotonic() + WATCH_READY_TIMEOUT
    ready_ok = False
    while time.monotonic() < ready_deadline:
        if watcher.poll() is not None:
            break  # watcher died
        if _validate_watch2_ready(watch2_ready_path, watcher.pid, run_token, OPERATION_SHA):
            ready_ok = True
            break
        time.sleep(PHASE_CHECK_INTERVAL)

    if not ready_ok:
        # Watcher died or never produced valid ready
        watcher.terminate()
        try:
            watcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=5)
        receipt['status'] = 'FAILED_WATCH2_READY'
        _write_receipt(receipt)
        raise SystemExit(1)

    receipt['phases'].append({'phase': 'watch2_ready', 'ok': True})

    # --- Launch start2 as Popen with CONCURRENT watcher monitoring ---
    start_argv = _op_argv('start2', run_token)
    start_log = open(AUDIT_DIR / 'start2.log', 'w')
    start_log.write(f'=== start2 (concurrent with watch2) ===\nargv: {json.dumps(start_argv)}\n')
    start_log.flush()

    start_proc = subprocess.Popen(
        start_argv, shell=False, stdout=start_log, stderr=subprocess.STDOUT
    )
    receipt['phases'].append({'phase': 'start2_launch', 'pid': start_proc.pid})

    # --- Concurrent monitoring: watch watcher + start ---
    watch_launch_time = time.monotonic()
    supervision_deadline = watch_launch_time + WATCH_DEADLINE
    watcher_died = False
    start_rc = None

    while time.monotonic() < supervision_deadline:
        # Check watcher aliveness
        if watcher.poll() is not None:
            watcher_died = True
            break
        # Check if start finished
        if start_proc.poll() is not None:
            start_rc = start_proc.returncode
            break
        time.sleep(PHASE_CHECK_INTERVAL)
    else:
        # Supervision deadline exceeded
        start_proc.terminate()
        try:
            start_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            start_proc.kill()
            start_proc.wait(timeout=5)
        start_rc = -1

    # --- Handle outcomes ---
    if watcher_died:
        # Watcher died during start: terminate owned start, reap
        start_proc.terminate()
        try:
            start_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            start_proc.kill()
            start_proc.wait(timeout=5)
        receipt['phases'].append({'phase': 'start2', 'status': 'WATCHER_DIED', 'start_reaped': True})
        receipt['status'] = 'FAILED_WATCHER_DIED'
    elif start_rc == 0:
        receipt['phases'].append({'phase': 'start2', 'rc': 0})
        # Start succeeded: let watcher continue bounded supervision, then stop it
        # Wait for watcher to finish naturally or bounded remaining time
        remaining = max(0, supervision_deadline - time.monotonic())
        try:
            watcher.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            watcher.terminate()
            try:
                watcher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watcher.kill()
                watcher.wait(timeout=5)
        receipt['status'] = 'PASS'
    else:
        # Start failed
        receipt['phases'].append({'phase': 'start2', 'rc': start_rc})
        watcher.terminate()
        try:
            watcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=5)
        receipt['status'] = 'FAILED_START2'

    receipt['ts_end'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    _write_receipt(receipt)

    if receipt['status'] != 'PASS':
        raise SystemExit(1)
    print(json.dumps({'status': 'PASS', 'run_token': run_token}))


def _write_receipt(receipt: dict) -> None:
    path = AUDIT_DIR / 'w2-receipt.json'
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


if __name__ == '__main__':
    main()
