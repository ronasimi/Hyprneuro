#!/usr/bin/env python3
"""
Continuation runner W3: START ONLY, concurrent, contain on ALL exits.
Runner STAYS ALIVE. Holds machine lease entire window.

Key differences from W2:
- ALL exits invoke contain (independent budget) BEFORE killing watch
- Writes START_READY event (O_EXCL, fsync) after start achieves
- Stays alive after start (does NOT exit early)
- Deadline 600s from watch3 launch ALWAYS → contain → WINDOW_EXPIRED
- No PASS status. Only WINDOW_EXPIRED / FAILED_* / CANCELLED
"""

import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# --- FROZEN literal pins (NOT None, NOT conditional) ---

PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'

W3_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w3')
OPS_W3_PATH = W3_DIR / 'continuation_ops_w3.py'
OPS_W3_SHA = '17c79cb7f81f7e271542711c39bca503f8a7f27bdf322dea4c0df666dbe4eeb5'
COMPARATOR_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts/execstart_stable_compare.py')
COMPARATOR_SHA = '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e'
V5_OPS_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/continuation_ops.py')
V5_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'

OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution-w3')
WATCH_DEADLINE = 600
PHASE_CHECK_INTERVAL = 1
WATCH_READY_TIMEOUT = 90

# W3 marker names
WATCH3_READY = 'continuation.watch3.ready'
START3_STARTED = 'continuation.start3.started'
START3_COMPLETED = 'continuation.start3.completed'
START3_READY_EVENT = 'continuation.start3.ready'

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
    """Verify all frozen code pins. NO conditional skip."""
    if not _valid_sha(OPERATION_SHA):
        raise ValueError('OPERATION_SHA malformed')
    if not _valid_sha(V5_OPS_SHA):
        raise ValueError('V5_OPS_SHA malformed')
    if not _valid_sha(OPS_W3_SHA):
        raise ValueError('OPS_W3_SHA malformed')
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
    if not OPS_W3_PATH.exists():
        raise ValueError('W3 ops path missing')
    if sha256_file(OPS_W3_PATH) != OPS_W3_SHA:
        raise ValueError('W3 ops SHA mismatch')
    if not COMPARATOR_PATH.exists():
        raise ValueError('comparator path missing')
    if sha256_file(COMPARATOR_PATH) != COMPARATOR_SHA:
        raise ValueError('comparator SHA mismatch')


def verify_preconditions() -> None:
    """Verify START ONLY preconditions. W3 markers ABSENT. W2 markers immutable."""
    # provision.completed must exist
    prov = OP_DIR / 'continuation.provision.completed'
    if not prov.exists():
        raise ValueError('Precondition FAIL: provision.completed absent')
    if prov.read_text().strip() != OPERATION_SHA:
        raise ValueError('Precondition FAIL: provision.completed SHA mismatch')

    # W3 markers must be ABSENT
    for m in (WATCH3_READY, START3_STARTED, START3_COMPLETED, START3_READY_EVENT):
        if (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: {m} already present')

    # W2 markers must be intact (immutable)
    for m in ('continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: W2 marker {m} missing')

    # Old markers intact
    for m in ('install.completed', 'install.started', 'session.pin',
              'continuation.provision.started', 'continuation.provision.completed',
              'continuation.watch.ready'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'Precondition FAIL: old marker {m} missing')


def _op_argv(phase: str, run_token: str) -> list:
    return [
        PYTHON, '-I', str(OPS_W3_PATH),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
        '--run-token', run_token,
    ]


def _write_start_ready_event(run_token: str) -> None:
    """Write START_READY event file (O_EXCL, fsync). Startup receipt, NOT consent."""
    event_path = OP_DIR / START3_READY_EVENT
    proc = Path('/proc/self')
    content = json.dumps({
        'schema': 'hyprneuro.boundary-start3-ready/1',
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': run_token,
        'uid': os.getuid(),
        'pid': os.getpid(),
        'start': proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19],
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, sort_keys=True) + '\n'
    fd = os.open(str(event_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, content.encode())
        os.fsync(fd)
    finally:
        os.close(fd)


def _contain() -> dict:
    """Invoke contain via ops W3. Independent budget. Returns evidence."""
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
        return {'status': 'CONTAIN_EXCEPTION', 'error': str(e)[:2000]}


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
    """Get actual unit PID/job/cgroup evidence (readonly)."""
    units = ['hyprharness-broker.service', 'hyprharness-helper.service',
             'hyprharness-socket.service', 'hyprharness-ui.service']
    evidence = []
    for unit in units:
        try:
            pid = subprocess.run(
                ['/usr/bin/systemctl', '--user', 'show', '-p', 'MainPID', '--value', unit],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
            job = subprocess.run(
                ['/usr/bin/systemctl', '--user', 'show', '-p', 'Job', '--value', unit],
                capture_output=True, text=True, timeout=5
            ).stdout.strip()
            evidence.append({'unit': unit, 'pid': pid, 'job': job})
        except Exception:
            evidence.append({'unit': unit, 'pid': 'UNKNOWN', 'job': 'UNKNOWN'})
    return evidence


def _write_receipt(receipt: dict) -> None:
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)
    path = AUDIT_DIR / 'w3-receipt.json'
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


def _sigterm_handler(signum, frame):
    """SIGTERM → raise SystemExit into owned try/finally. Bounded cleanup."""
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
        'schema': 'hyprneuro.boundary-continuation-runner-w3/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'run_token': run_token,
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'phases': []
    }

    watcher = None
    start_proc = None
    status = 'UNKNOWN'
    _cleanup_in_progress = False

    def _sigterm_during_cleanup(signum, frame):
        nonlocal _cleanup_in_progress
        if _cleanup_in_progress:
            # Second TERM during cleanup: best-effort log, no SIGKILL guarantee
            return
        raise SystemExit(143)

    # Install SIGTERM handler ONLY after minimal init (cleanup vars set)
    signal.signal(signal.SIGTERM, _sigterm_handler)

    try:
        # Launch watch3 as child Popen
        watch_argv = _op_argv('watch3', run_token)
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_DIR.chmod(0o700)
        watch_log = open(AUDIT_DIR / 'watch3.log', 'w')
        watch_log.write(f'=== watch3 ===\nrun_token: {run_token}\n')
        watch_log.flush()

        watch_launch_time = time.monotonic()
        supervision_deadline = watch_launch_time + WATCH_DEADLINE

        watcher = subprocess.Popen(watch_argv, shell=False, stdout=watch_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'watch3_launch', 'pid': watcher.pid})

        # Bounded wait for valid watch3.ready
        watch3_ready_path = OP_DIR / WATCH3_READY
        ready_deadline = min(time.monotonic() + WATCH_READY_TIMEOUT, supervision_deadline)
        ready_ok = False
        while time.monotonic() < ready_deadline:
            if watcher.poll() is not None:
                break
            if watch3_ready_path.exists():
                try:
                    data = json.loads(watch3_ready_path.read_text())
                    if (data.get('pid') == watcher.pid and
                        data.get('run_token') == run_token and
                        data.get('operation_sha256') == OPERATION_SHA):
                        ready_ok = True
                        break
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(PHASE_CHECK_INTERVAL)

        if not ready_ok:
            status = 'FAILED_WATCH3_READY'
            raise ValueError('watch3 ready not achieved')

        receipt['phases'].append({'phase': 'watch3_ready', 'ok': True})

        # Launch start3 as Popen (concurrent with watcher)
        start_argv = _op_argv('start3', run_token)
        start_log = open(AUDIT_DIR / 'start3.log', 'w')
        start_log.write(f'=== start3 ===\nrun_token: {run_token}\n')
        start_log.flush()

        start_proc = subprocess.Popen(start_argv, shell=False, stdout=start_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'start3_launch', 'pid': start_proc.pid})

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
                receipt['phases'].append({'phase': 'start3_ready_event', 'ok': True})
            except FileExistsError:
                status = 'FAILED_EVENT_EXISTS'
                raise
            except Exception as e:
                status = 'FAILED_EVENT_WRITE'
                receipt['phases'].append({'phase': 'start3_ready_event', 'error': str(e)[:200]})

            # Continue supervision until deadline (runner stays alive)
            while time.monotonic() < supervision_deadline:
                if watcher.poll() is not None:
                    watcher_died = True
                    break
                time.sleep(PHASE_CHECK_INTERVAL)
            if watcher_died:
                status = 'FAILED_WATCH_DIED_POST_START'
            else:
                status = 'WINDOW_EXPIRED'
        else:
            status = f'FAILED_START3_RC_{start_rc}'

    except Exception as e:
        if status == 'UNKNOWN':
            status = 'FAILED_EXCEPTION'
        receipt['exception'] = str(e)[:2000]
    finally:
        _cleanup_in_progress = True
        signal.signal(signal.SIGTERM, _sigterm_during_cleanup)

        # ALL exits: contain → reap → evidence
        containment = _contain()
        receipt['containment'] = containment

        if start_proc is not None:
            receipt['start3_reaped'] = _reap(start_proc)
        if watcher is not None:
            receipt['watch3_reaped'] = _reap(watcher)

        receipt['units'] = _unit_evidence()
        if status == 'UNKNOWN':
            status = 'CANCELLED_SIGNAL' if receipt.get('exception', '').startswith('SystemExit') else 'FAILED_EXCEPTION'
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
