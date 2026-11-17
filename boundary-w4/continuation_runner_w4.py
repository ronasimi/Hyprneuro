#!/usr/bin/env python3
"""
Continuation runner W4: START ONLY, concurrent, contain on ALL exits.
Runner STAYS ALIVE. Holds machine lease entire window.

Key differences from W3:
- New markers: watch4, start4, ready
- 4-unit closed table for receipt
- Optional context file for DB/settings pre-start baseline
- Stays alive 600s from watch4 launch ALWAYS → contain → WINDOW_EXPIRED
- No PASS status. Only WINDOW_EXPIRED / FAILED_* / CANCELLED_SIGNAL
- Backend NOT ATTESTED (even if units contain)
- Safe closed enum stage (no raw exception text in receipt)
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

# --- FROZEN literal pins (NOT None, NOT conditional) ---

PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'

# Pre-import PIN checks: verify 04 boundary_release modules BEFORE any import/subprocess
_BOUNDARY_RELEASE_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops/boundary_release.py')
_BOUNDARY_RELEASE_SHA = '9fcb37cf398dfe2f158ef39fa3ab518f233f231e23242a6e22b680ed9b91e74c'
_BOUNDARY_RELEASE_OPS_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops/boundary_release_ops.py')
_BOUNDARY_RELEASE_OPS_SHA = '5e6c50f202090f93699f11f28c0d61409ee2b6bcafec5bc8ad015ceb601659ac'

W4_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3')
OPS_W4_PATH = W4_DIR / 'continuation_ops_w4.py'
OPS_W4_SHA = '74516bc00d0b791575455eaf16f5599b4b9135eceac317cf46417eb3183c7a1c'

COMPARATOR_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts/execstart_stable_compare.py')
COMPARATOR_SHA = '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e'
V5_OPS_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/continuation_ops.py')
V5_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'

OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution-w4')
WATCH_DEADLINE = 600
PHASE_CHECK_INTERVAL = 1
WATCH_READY_TIMEOUT = 90

# Context file path (REQUIRED, prospective postwrite baseline)
CONTEXT_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-w3-v3-postwrite-evidence/postwrite-context.json')
CONTEXT_SHA = '51f9109f0c9515045ce9fbc0f16c1b15bb8cf54116dfe8a230d4aa3a526e39bc'

# W4 marker names
WATCH4_READY = 'continuation.watch4.ready'
START4_STARTED = 'continuation.start4.started'
START4_COMPLETED = 'continuation.start4.completed'
START4_READY_EVENT = 'continuation.start4.ready'

# 4-unit closed table
ALL_UNITS = (
    'hyprneuro.service',
    'hyprneuro-ui.service',
    'hyprneuro-pi-identity.service',
    'hyprneuro-pi-identity.socket',
)

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
    """Verify all frozen code pins. NO conditional skip. Pre-import boundary pins first."""
    # Pre-import: 04 boundary_release modules (BEFORE any subprocess/import)
    if not _valid_sha(_BOUNDARY_RELEASE_SHA):
        raise ValueError('BOUNDARY_RELEASE_SHA malformed')
    if not _valid_sha(_BOUNDARY_RELEASE_OPS_SHA):
        raise ValueError('BOUNDARY_RELEASE_OPS_SHA malformed')
    if not _BOUNDARY_RELEASE_PATH.exists():
        raise ValueError('boundary_release.py missing')
    if sha256_file(_BOUNDARY_RELEASE_PATH) != _BOUNDARY_RELEASE_SHA:
        raise ValueError('boundary_release.py SHA mismatch')
    if not _BOUNDARY_RELEASE_OPS_PATH.exists():
        raise ValueError('boundary_release_ops.py missing')
    if sha256_file(_BOUNDARY_RELEASE_OPS_PATH) != _BOUNDARY_RELEASE_OPS_SHA:
        raise ValueError('boundary_release_ops.py SHA mismatch')

    # Standard pins
    if not _valid_sha(OPERATION_SHA):
        raise ValueError('OPERATION_SHA malformed')
    if not _valid_sha(V5_OPS_SHA):
        raise ValueError('V5_OPS_SHA malformed')
    if not _valid_sha(COMPARATOR_SHA):
        raise ValueError('COMPARATOR_SHA malformed')
    if not OPERATION_PATH.exists():
        raise ValueError('Operation path missing')
    if sha256_file(OPERATION_PATH) != OPERATION_SHA:
        raise ValueError('Operation SHA mismatch')
    if not V5_OPS_PATH.exists():
        raise ValueError('v5 ops path missing')
    if sha256_file(V5_OPS_PATH) != V5_OPS_SHA:
        raise ValueError('v5 ops SHA mismatch')
    if not COMPARATOR_PATH.exists():
        raise ValueError('comparator path missing')
    if sha256_file(COMPARATOR_PATH) != COMPARATOR_SHA:
        raise ValueError('comparator SHA mismatch')

    # W4 ops pin
    if not _valid_sha(OPS_W4_SHA):
        raise ValueError('OPS_W4_SHA malformed')
    if not OPS_W4_PATH.exists():
        raise ValueError('W4 ops path missing')
    if sha256_file(OPS_W4_PATH) != OPS_W4_SHA:
        raise ValueError('W4 ops SHA mismatch')

    # Context file pin (REQUIRED)
    if not _valid_sha(CONTEXT_SHA):
        raise ValueError('CONTEXT_SHA malformed')
    if not CONTEXT_PATH.exists():
        raise ValueError('Context file missing (required)')
    if sha256_file(CONTEXT_PATH) != CONTEXT_SHA:
        raise ValueError('Context file SHA mismatch')


def verify_preconditions() -> None:
    """Verify START ONLY preconditions. W4 markers ABSENT. W3/W2/04 markers immutable."""
    # provision.completed must exist
    prov = OP_DIR / 'continuation.provision.completed'
    if not prov.exists():
        raise ValueError('Precondition FAIL: provision.completed absent')
    if prov.read_text().strip() != OPERATION_SHA:
        raise ValueError('Precondition FAIL: provision.completed SHA mismatch')

    # W4 markers must be ABSENT
    for m in (WATCH4_READY, START4_STARTED, START4_COMPLETED, START4_READY_EVENT):
        if (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: {m} already present')

    # W3 markers must be intact (immutable, retained)
    for m in ('continuation.watch3.ready', 'continuation.start3.started',
              'continuation.start3.completed', 'continuation.start3.ready'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: W3 marker {m} missing')

    # W2 markers must be intact (immutable)
    for m in ('continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: W2 marker {m} missing')

    # Old 04 markers intact
    for m in ('install.completed', 'install.started', 'session.pin',
              'continuation.provision.started', 'continuation.provision.completed',
              'continuation.watch.ready'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: old marker {m} missing')


def _op_argv(phase: str, run_token: str) -> list:
    """Build ops argv. Context file always passed (required). -B prevents pyc creation."""
    return [
        PYTHON, '-I', '-B', str(OPS_W4_PATH),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
        '--run-token', run_token,
        '--context', str(CONTEXT_PATH),
    ]


def _write_start_ready_event(run_token: str) -> None:
    """Write START_READY event file (atomic O_CREAT|O_EXCL 0o600, fsync). NOT consent."""
    event_path = OP_DIR / START4_READY_EVENT
    proc = Path('/proc/self')
    content = json.dumps({
        'schema': 'hyprneuro.boundary-start4-ready/1',
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': run_token,
        'uid': os.getuid(),
        'pid': os.getpid(),
        'start': proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19],
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, sort_keys=True) + '\n'
    # Atomic: O_CREAT|O_EXCL with 0o600 mode (no write_text+chmod race)
    fd = os.open(str(event_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, content.encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def _contain() -> dict:
    """Invoke contain via ops W4. Independent budget. Returns evidence."""
    contain_argv = _op_argv('contain', 'contain')
    try:
        result = subprocess.run(
            contain_argv, shell=False, capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout.strip() else {'status': 'CONTAINED'}
        return {'status': 'CONTAIN_FAILED', 'rc': result.returncode, 'stderr': result.stderr[:2000]}
    except subprocess.TimeoutExpired:
        return {'status': 'CONTAIN_TIMEOUT'}
    except Exception as e:
        return {'status': 'CONTAIN_EXCEPTION', 'error': type(e).__name__}


def _reap(proc: subprocess.Popen) -> int:
    """Terminate and reap a child process. Returns final returncode."""
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return -9
    return proc.returncode if proc.returncode is not None else -1


def _unit_evidence() -> list:
    """Get actual 4-unit PID/job/cgroup evidence (readonly).
    Service: MainPID. Socket: N/A. Not found: UNKNOWN (never fabricated 0).
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


def _write_receipt(receipt: dict) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)
    path = AUDIT_DIR / 'w4-receipt.json'
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


def _sigterm_handler(signum, frame, state: dict):
    """SIGTERM → set flag + raise SystemExit into owned try/finally."""
    state['sigterm'] = True
    raise SystemExit(143)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-token', required=True)
    args = parser.parse_args()
    run_token = args.run_token

    verify_pins()
    verify_preconditions()

    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner-w4/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'run_token': run_token,
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'context_path': str(CONTEXT_PATH),
        'context_sha': CONTEXT_SHA,
        'phases': []
    }

    watcher = None
    start_proc = None
    status = 'UNKNOWN'
    state = {'sigterm': False, 'cleanup': False}

    def _sigterm_during_cleanup(signum, frame):
        if state['cleanup']:
            return  # Second TERM during cleanup: defer, no SIGKILL
        state['sigterm'] = True
        raise SystemExit(143)

    # Install SIGTERM handler after minimal init (state vars set)
    signal.signal(signal.SIGTERM, lambda s, f: _sigterm_handler(s, f, state))

    try:
        # Launch watch4 as child Popen
        watch_argv = _op_argv('watch4', run_token)
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_DIR.chmod(0o700)
        watch_log = open(AUDIT_DIR / 'watch4.log', 'w')
        watch_log.write(f'=== watch4 ===\nrun_token: {run_token}\n')
        watch_log.flush()

        watch_launch_time = time.monotonic()
        supervision_deadline = watch_launch_time + WATCH_DEADLINE

        watcher = subprocess.Popen(watch_argv, shell=False, stdout=watch_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'watch4_launch', 'pid': watcher.pid})

        # Bounded wait for valid watch4.ready
        watch4_ready_path = OP_DIR / WATCH4_READY
        ready_deadline = min(time.monotonic() + WATCH_READY_TIMEOUT, supervision_deadline)
        ready_ok = False
        while time.monotonic() < ready_deadline:
            if watcher.poll() is not None:
                break
            if watch4_ready_path.exists():
                try:
                    data = json.loads(watch4_ready_path.read_text())
                    if (data.get('pid') == watcher.pid and
                        data.get('run_token') == run_token and
                        data.get('operation_sha256') == OPERATION_SHA):
                        ready_ok = True
                        break
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(PHASE_CHECK_INTERVAL)

        if not ready_ok:
            status = 'FAILED_WATCH4_READY'
            raise ValueError('watch4 ready not achieved')

        receipt['phases'].append({'phase': 'watch4_ready', 'ok': True})

        # Launch start4 as Popen (concurrent with watcher)
        start_argv = _op_argv('start4', run_token)
        start_log = open(AUDIT_DIR / 'start4.log', 'w')
        start_log.write(f'=== start4 ===\nrun_token: {run_token}\n')
        start_log.flush()

        start_proc = subprocess.Popen(start_argv, shell=False, stdout=start_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'start4_launch', 'pid': start_proc.pid})

        # Concurrent monitoring
        start_rc = None
        watcher_died = False
        while time.monotonic() < supervision_deadline:
            if watcher.poll() is not None:
                watcher_died = True
                break
            if start_proc.poll() is not None:
                start_rc = start_proc.returncode
                break
            time.sleep(PHASE_CHECK_INTERVAL)
        else:
            start_rc = -1  # Deadline exceeded

        # Handle outcomes
        if watcher_died:
            status = 'FAILED_WATCH_DIED'
        elif start_rc == 0:
            # Start achieved: write START_READY event
            try:
                _write_start_ready_event(run_token)
                receipt['phases'].append({'phase': 'start4_ready_event', 'ok': True})
            except FileExistsError:
                status = 'FAILED_EVENT_EXISTS'
                raise
            except Exception as e:
                status = 'FAILED_EVENT_WRITE'
                receipt['phases'].append({'phase': 'start4_ready_event', 'error': type(e).__name__})

            # Continue supervision until deadline (runner stays alive)
            while time.monotonic() < supervision_deadline:
                if watcher.poll() is not None:
                    watcher_died = True
                    break
                time.sleep(PHASE_CHECK_INTERVAL)
            if watcher_died:
                status = 'FAILED_WATCH_DIED_POST_START'
            else:
                # WINDOW_EXPIRED: normal completion. NOT inference PASS.
                # Backend NOT ATTESTED even if units contain/stop.
                status = 'WINDOW_EXPIRED'
        else:
            status = f'FAILED_START4_RC_{start_rc}'

    except SystemExit as e:
        # SystemExit is BaseException, NOT caught by except Exception
        if state['sigterm']:
            status = 'CANCELLED_SIGNAL'
        else:
            status = 'UNKNOWN'
        receipt['exception'] = f'SystemExit({e.code})'
    except Exception as e:
        if status == 'UNKNOWN':
            status = 'FAILED_EXCEPTION'
        receipt['exception'] = type(e).__name__
    finally:
        state['cleanup'] = True
        signal.signal(signal.SIGTERM, _sigterm_during_cleanup)

        # ALL exits: contain → reap → evidence
        containment = _contain()
        receipt['containment'] = containment

        if start_proc is not None:
            receipt['start4_reaped'] = _reap(start_proc)
        if watcher is not None:
            receipt['watch4_reaped'] = _reap(watcher)

        receipt['units'] = _unit_evidence()
        if status == 'UNKNOWN':
            status = 'CANCELLED_SIGNAL' if state['sigterm'] else 'FAILED_EXCEPTION'
        receipt['status'] = status
        receipt['ts_end'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        receipt['backend_attested'] = False
        _write_receipt(receipt)

    # Exit code: 0 only for WINDOW_EXPIRED (normal completion)
    if status == 'WINDOW_EXPIRED':
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == '__main__':
    main()
