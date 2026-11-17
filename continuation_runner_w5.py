#!/usr/bin/env python3
"""
Continuation runner W5: START ONLY, concurrent, contain on ALL exits. Runner STAYS ALIVE.
Holds machine lease entire window. APPROVED W5 corrections vs frozen W4:
- Fresh W5 marker/event namespace (watch5, start5) across runner+ops+waiter.
- verify_preconditions_w5:
    * W5 markers ABSENT.
    * DROP the W3-success requirement.
    * PIN the known-failed W3 state EXPLICITLY (watch3.ready present; start3.* ABSENT).
    * old W4 ready: READ-ONLY exact-SHA identity (presence + identity); NOT cleared/adopted/replayed.
    * W4 start4.* ABSENT; provision/W2/old-04 intact.
- No PASS status. Only WINDOW_EXPIRED / FAILED_* / CANCELLED_SIGNAL.
- Backend NOT ATTESTED. Safe closed enum stage.
"""

import hashlib
import json
import os
import signal
import stat
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

# --- FROZEN literal pins ---

PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'

_BOUNDARY_RELEASE_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops/boundary_release.py')
_BOUNDARY_RELEASE_SHA = '9fcb37cf398dfe2f158ef39fa3ab518f233f231e23242a6e22b680ed9b91e74c'
_BOUNDARY_RELEASE_OPS_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops/boundary_release_ops.py')
_BOUNDARY_RELEASE_OPS_SHA = '5e6c50f202090f93699f11f28c0d61409ee2b6bcafec5bc8ad015ceb601659ac'

W5_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5')
OPS_W5_PATH = W5_DIR / 'continuation_ops_w5.py'
OPS_W5_SHA = '19699702c74c6d0ded9068ef40197d5b9e9ed0c35f7da309d5cc82eb4fc3b644'

COMPARATOR_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts/execstart_stable_compare.py')
COMPARATOR_SHA = '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e'
V5_OPS_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/continuation_ops.py')
V5_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'

OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution-w5')
WATCH_DEADLINE = 600
PHASE_CHECK_INTERVAL = 1
WATCH_READY_TIMEOUT = 90

CONTEXT_W5_PATH = W5_DIR / 'w5-postwrite-context.json'
CONTEXT_W5_SHA = '1af29c8d3bd960fabfd72227aebab1e4822fe119192fe1e86ba40b549a73561d'

OLD_W4_READY_PATH = OP_DIR / 'continuation.watch4.ready'
OLD_W4_READY_SHA = '08bc1b3bbcf64269e6e9776ded51b7a053cfd707edbf54174379579f1ad62811'

# W5 marker names
WATCH5_READY = 'continuation.watch5.ready'
START5_STARTED = 'continuation.start5.started'
START5_COMPLETED = 'continuation.start5.completed'
START5_READY_EVENT = 'continuation.start5.ready'

ALL_UNITS = (
    'hyprneuro.service',
    'hyprneuro-ui.service',
    'hyprneuro-pi-identity.service',
    'hyprneuro-pi-identity.socket',
)

_SHA_HEX = set('0123456789abcdef')


def _valid_sha(s) -> bool:
    return isinstance(s, str) and len(s) == 64 and all(c in _SHA_HEX for c in s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_pins() -> None:
    """Verify all frozen + W5 code pins. NO conditional skip. Pre-import boundary pins first."""
    for p, s in ((_BOUNDARY_RELEASE_PATH, _BOUNDARY_RELEASE_SHA),
                 (_BOUNDARY_RELEASE_OPS_PATH, _BOUNDARY_RELEASE_OPS_SHA),
                 (OPERATION_PATH, OPERATION_SHA),
                 (V5_OPS_PATH, V5_OPS_SHA),
                 (COMPARATOR_PATH, COMPARATOR_SHA),
                 (OPS_W5_PATH, OPS_W5_SHA),
                 (CONTEXT_W5_PATH, CONTEXT_W5_SHA)):
        if not _valid_sha(s):
            raise ValueError(f'pin sha malformed: {p.name}')
        if not p.exists():
            raise ValueError(f'pin missing: {p}')
        if sha256_file(p) != s:
            raise ValueError(f'pin SHA mismatch: {p}')


def _verify_old_w4_ready_identity() -> None:
    """READ-ONLY exact-SHA identity of the preserved stale W4 ready. Presence + identity.
    Never cleared/adopted/replayed. O_NOFOLLOW same-FD to avoid TOCTOU."""
    if not OLD_W4_READY_PATH.exists():
        raise ValueError('W5 precond: old W4 watch4.ready missing (expected preserved)')
    fd = os.open(str(OLD_W4_READY_PATH), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1:
            raise ValueError('W5 precond: old W4 watch4.ready not private single-link regular file')
        raw = b''
        while True:
            c = os.read(fd, 65536)
            if not c:
                break
            raw += c
        if hashlib.sha256(raw).hexdigest() != OLD_W4_READY_SHA:
            raise ValueError('W5 precond: old W4 watch4.ready SHA identity drift')
    finally:
        os.close(fd)


def verify_preconditions_w5() -> None:
    """W5 START-ONLY preconditions. Fresh W5 namespace; known-failed W3 state PINNED.
    No W3-success requirement. No fallback. Fail-closed."""
    prov = OP_DIR / 'continuation.provision.completed'
    if not prov.exists():
        raise ValueError('W5 precond: provision.completed absent')
    if prov.read_text().strip() != OPERATION_SHA:
        raise ValueError('W5 precond: provision.completed SHA mismatch')

    # W5 markers must be ABSENT (fresh namespace)
    for m in (WATCH5_READY, START5_STARTED, START5_COMPLETED, START5_READY_EVENT):
        if (OP_DIR / m).exists():
            raise ValueError(f'W5 precond: {m} already present')

    # Known-failed W3 state PINNED EXPLICITLY (missingness explicit; NO W3-success requirement)
    if not (OP_DIR / 'continuation.watch3.ready').exists():
        raise ValueError('W5 precond: W3 watch3.ready missing (expected present)')
    for m in ('continuation.start3.started', 'continuation.start3.completed', 'continuation.start3.ready'):
        if (OP_DIR / m).exists():
            raise ValueError(f'W5 precond: W3 {m} present (expected ABSENT in known-failed W3 state)')

    # W2 markers intact (immutable)
    for m in ('continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'W5 precond: W2 marker {m} missing')

    # old 04 markers intact
    for m in ('install.completed', 'install.started', 'session.pin',
              'continuation.provision.started', 'continuation.provision.completed',
              'continuation.watch.ready'):
        if not (OP_DIR / m).exists():
            raise ValueError(f'W5 precond: old marker {m} missing')

    # old W4 ready: READ-ONLY exact-SHA identity (preserved; not cleared/adopted)
    _verify_old_w4_ready_identity()

    # W4 start4.* must be ABSENT (never written in W4)
    for m in ('continuation.start4.started', 'continuation.start4.completed', 'continuation.start4.ready'):
        if (OP_DIR / m).exists():
            raise ValueError(f'W5 precond: W4 {m} present (expected absent)')


def _op_argv(phase: str, run_token: str) -> list:
    """Build ops argv. W5 context always passed (required). -I -B prevents pyc + isolates."""
    return [
        PYTHON, '-I', '-B', str(OPS_W5_PATH),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
        '--run-token', run_token,
        '--context', str(CONTEXT_W5_PATH),
    ]


def _write_start_ready_event(run_token: str) -> None:
    """Write START5_READY event file (atomic O_CREAT|O_EXCL 0o600, fsync). NOT consent."""
    event_path = OP_DIR / START5_READY_EVENT
    proc = Path('/proc/self')
    content = json.dumps({
        'schema': 'hyprneuro.boundary-start5-ready/1',
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
    contain_argv = _op_argv('contain', 'contain')
    try:
        result = subprocess.run(contain_argv, shell=False, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout.strip() else {'status': 'CONTAINED'}
        return {'status': 'CONTAIN_FAILED', 'rc': result.returncode, 'stderr': result.stderr[:2000]}
    except subprocess.TimeoutExpired:
        return {'status': 'CONTAIN_TIMEOUT'}
    except Exception as e:
        return {'status': 'CONTAIN_EXCEPTION', 'error': type(e).__name__}


def _reap(proc: subprocess.Popen) -> int:
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
    path = AUDIT_DIR / 'w5-receipt.json'
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


def _sigterm_handler(signum, frame, state: dict):
    state['sigterm'] = True
    raise SystemExit(143)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-token', required=True)
    args = parser.parse_args()
    run_token = args.run_token

    verify_pins()
    verify_preconditions_w5()

    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner-w5/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'run_token': run_token,
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'context_path': str(CONTEXT_W5_PATH),
        'context_sha': CONTEXT_W5_SHA,
        'old_w4_ready_sha': OLD_W4_READY_SHA,
        'phases': []
    }

    watcher = None
    start_proc = None
    status = 'UNKNOWN'
    state = {'sigterm': False, 'cleanup': False}

    def _sigterm_during_cleanup(signum, frame):
        if state['cleanup']:
            return
        state['sigterm'] = True
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, lambda s, f: _sigterm_handler(s, f, state))

    try:
        watch_argv = _op_argv('watch5', run_token)
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        AUDIT_DIR.chmod(0o700)
        watch_log = open(AUDIT_DIR / 'watch5.log', 'w')
        watch_log.write(f'=== watch5 ===\nrun_token: {run_token}\n')
        watch_log.flush()

        watch_launch_time = time.monotonic()
        supervision_deadline = watch_launch_time + WATCH_DEADLINE

        watcher = subprocess.Popen(watch_argv, shell=False, stdout=watch_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'watch5_launch', 'pid': watcher.pid})

        watch5_ready_path = OP_DIR / WATCH5_READY
        ready_deadline = min(time.monotonic() + WATCH_READY_TIMEOUT, supervision_deadline)
        ready_ok = False
        while time.monotonic() < ready_deadline:
            if watcher.poll() is not None:
                break
            if watch5_ready_path.exists():
                try:
                    data = json.loads(watch5_ready_path.read_text())
                    if (data.get('pid') == watcher.pid and
                        data.get('run_token') == run_token and
                        data.get('operation_sha256') == OPERATION_SHA):
                        ready_ok = True
                        break
                except (json.JSONDecodeError, OSError):
                    pass
            time.sleep(PHASE_CHECK_INTERVAL)

        if not ready_ok:
            status = 'FAILED_WATCH5_READY'
            raise ValueError('watch5 ready not achieved')

        receipt['phases'].append({'phase': 'watch5_ready', 'ok': True})

        start_argv = _op_argv('start5', run_token)
        start_log = open(AUDIT_DIR / 'start5.log', 'w')
        start_log.write(f'=== start5 ===\nrun_token: {run_token}\n')
        start_log.flush()

        start_proc = subprocess.Popen(start_argv, shell=False, stdout=start_log, stderr=subprocess.STDOUT)
        receipt['phases'].append({'phase': 'start5_launch', 'pid': start_proc.pid})

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
            start_rc = -1

        if watcher_died:
            status = 'FAILED_WATCH_DIED'
        elif start_rc == 0:
            try:
                _write_start_ready_event(run_token)
                receipt['phases'].append({'phase': 'start5_ready_event', 'ok': True})
            except FileExistsError:
                status = 'FAILED_EVENT_EXISTS'
                raise
            except Exception as e:
                status = 'FAILED_EVENT_WRITE'
                receipt['phases'].append({'phase': 'start5_ready_event', 'error': type(e).__name__})

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
            status = f'FAILED_START5_RC_{start_rc}'

    except SystemExit as e:
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

        containment = _contain()
        receipt['containment'] = containment

        if start_proc is not None:
            receipt['start5_reaped'] = _reap(start_proc)
        if watcher is not None:
            receipt['watch5_reaped'] = _reap(watcher)

        receipt['units'] = _unit_evidence()
        if status == 'UNKNOWN':
            status = 'CANCELLED_SIGNAL' if state['sigterm'] else 'FAILED_EXCEPTION'
        receipt['status'] = status
        receipt['ts_end'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        receipt['backend_attested'] = False
        _write_receipt(receipt)

    if status == 'WINDOW_EXPIRED':
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == '__main__':
    main()
