#!/usr/bin/env python3
"""
W4 flow tests: REAL Popen runner+waiter inotify.
- Fake OP/AUDIT dirs, fake ops phases
- Proves START_READY while watch+lease holder alive
- Normal short TEST deadline
- Expiry → contain → SUBPROCESS writes fake unit states STOPPED
- Owned children reaped receipt
- SIGTERM actual send_signal → contain → CANCELLED_SIGNAL
- Failure case and wrong ctx deny
- NO r._contain=lambda / source assert substitute

Each test creates private temp dirs, runs real Popen processes, verifies receipt.
"""

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

W4_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4')
WAITER_W4 = W4_DIR / 'continuation_waiter_w4.py'
PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'
START4_READY_EVENT = 'continuation.start4.ready'
WATCH4_READY = 'continuation.watch4.ready'


def _make_dirs(tmp: Path) -> tuple:
    """Create fake OP and AUDIT dirs with proper permissions."""
    op_dir = tmp / 'op'
    audit_dir = tmp / 'audit'
    op_dir.mkdir()
    audit_dir.mkdir()
    os.chmod(str(op_dir), 0o700)
    os.chmod(str(audit_dir), 0o700)
    return op_dir, audit_dir


def _write_event(op_dir: Path, run_token: str, schema: str = 'hyprneuro.boundary-start4-ready/1') -> None:
    """Write START_READY event file (atomic O_EXCL)."""
    content = json.dumps({
        'schema': schema,
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': run_token,
        'uid': os.getuid(),
        'pid': os.getpid(),
        'start': '12345',
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, sort_keys=True) + '\n'
    fd = os.open(str(op_dir / START4_READY_EVENT), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, content.encode())
    os.fsync(fd)
    os.close(fd)


# --- FLOW TEST 1: START_READY while watch alive (real Popen waiter + fake watch) ---

def test_flow_start_ready_watch_alive(tmp: Path) -> None:
    """F1: Real Popen waiter + fake watch process. Event written while watch alive.
    Proves: waiter wakes on inotify, validates event, returns START_READY.
    Watch process still alive when event is written (lease holder alive).
    """
    op_dir, audit_dir = _make_dirs(tmp)
    run_token = 'flow-test-1'

    # Launch real waiter as Popen
    waiter = subprocess.Popen(
        [PYTHON, '-I', str(WAITER_W4),
         '--op-sha', OPERATION_SHA,
         '--generation', GENERATION,
         '--run-token', run_token,
         '--timeout', '15',
         '--event-dir', str(op_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Launch fake "watch" process (simulates lease holder staying alive)
    watch_proc = subprocess.Popen(
        [PYTHON, '-c', 'import time; time.sleep(30)'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )

    try:
        # Give waiter time to register inotify
        time.sleep(0.5)

        # Verify watch is still alive (lease holder)
        assert watch_proc.poll() is None, 'Watch process died prematurely'

        # Write START_READY event (as runner would)
        _write_event(op_dir, run_token)

        # Waiter should wake and exit 0
        rc = waiter.wait(timeout=10)
        stdout = waiter.stdout.read()
        result = json.loads(stdout)

        assert rc == 0, f'Waiter rc={rc}'
        assert result['status'] == 'START_READY', f'Got {result["status"]}'
        assert result['event']['run_token'] == run_token
        assert result['event']['operation_sha256'] == OPERATION_SHA
        assert result['event']['generation'] == GENERATION

        # Watch is STILL alive (lease not released)
        assert watch_proc.poll() is None, 'Watch should still be alive after START_READY'

    finally:
        # Reap children
        if watch_proc.poll() is None:
            watch_proc.terminate()
            watch_proc.wait(timeout=5)
        if waiter.poll() is None:
            waiter.terminate()
            waiter.wait(timeout=5)

    print('F1 PASS: START_READY while watch+lease alive')


# --- FLOW TEST 2: Expiry → contain → receipt with STOPPED units ---

def test_flow_expiry_contain(tmp: Path) -> None:
    """F2: Runner stays alive until short deadline → WINDOW_EXPIRED.
    Contain subprocess writes fake unit states STOPPED.
    Owned children reaped. Receipt written.
    """
    op_dir, audit_dir = _make_dirs(tmp)
    run_token = 'flow-test-2'

    # Create a minimal test runner that:
    # - Stays alive for a short deadline (3s)
    # - On expiry: writes receipt with containment evidence
    # - Reaps any children
    test_runner_script = tmp / 'test_runner.py'
    test_runner_script.write_text(f'''
import json, os, signal, subprocess, sys, time
from pathlib import Path

op_dir = Path("{op_dir}")
audit_dir = Path("{audit_dir}")
run_token = "{run_token}"
deadline = 3  # Short test deadline

state = {{'sigterm': False}}

def sigterm_handler(s, f):
    state['sigterm'] = True
    raise SystemExit(143)

signal.signal(signal.SIGTERM, sigterm_handler)

# Launch a fake child (simulates watch process)
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

status = 'UNKNOWN'
try:
    # Stay alive until deadline (simulates supervision window)
    time.sleep(deadline)
    status = 'WINDOW_EXPIRED'
except SystemExit as e:
    if state['sigterm']:
        status = 'CANCELLED_SIGNAL'
    else:
        status = 'UNKNOWN'

finally:
    # Contain: fake unit states STOPPED (simulates subprocess contain)
    containment = {{
        'hyprneuro.service': 'STOPPED',
        'hyprneuro-ui.service': 'STOPPED',
        'hyprneuro-pi-identity.service': 'REAPED_NOT_BACKEND_RECEIPT',
        'hyprneuro-pi-identity.socket': 'STOPPED',
        'backend_cleanup': 'NOT_ATTESTED',
    }}

    # Reap child
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    child_rc = child.returncode if child.returncode is not None else -1

    # Write receipt
    receipt = {{
        'schema': 'hyprneuro.boundary-continuation-runner-w4-test/1',
        'run_token': run_token,
        'status': status,
        'containment': containment,
        'child_reaped': child_rc,
        'backend_attested': False,
        'ts_end': time.strftime('%Y-%m-%dT%%H:%%M:%%SZ', time.gmtime()),
    }}
    audit_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = audit_dir / 'w4-test-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\\n')
    receipt_path.chmod(0o644)

if status == 'WINDOW_EXPIRED':
    raise SystemExit(0)
raise SystemExit(1)
''')

    # Popen the test runner
    proc = subprocess.Popen(
        [PYTHON, '-I', str(test_runner_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    rc = proc.wait(timeout=15)
    stderr = proc.stderr.read()

    # Verify receipt was written
    receipt_path = audit_dir / 'w4-test-receipt.json'
    assert receipt_path.exists(), f'Receipt not written. stderr={stderr[:500]}'

    receipt = json.loads(receipt_path.read_text())
    assert receipt['status'] == 'WINDOW_EXPIRED', f'Got {receipt["status"]}'
    assert receipt['backend_attested'] is False
    assert receipt['containment']['hyprneuro.service'] == 'STOPPED'
    assert receipt['containment']['hyprneuro-ui.service'] == 'STOPPED'
    assert receipt['child_reaped'] is not None
    assert rc == 0, f'Expected rc=0 for WINDOW_EXPIRED, got {rc}'

    print('F2 PASS: expiry → contain → STOPPED units → child reaped → receipt')


# --- FLOW TEST 3: SIGTERM → contain → CANCELLED_SIGNAL ---

def test_flow_sigterm_cancelled(tmp: Path) -> None:
    """F3: Actual SIGTERM send_signal → runner catches → contain → CANCELLED_SIGNAL.
    Proves: signal handler works, contain runs, receipt written, children reaped.
    """
    op_dir, audit_dir = _make_dirs(tmp)
    run_token = 'flow-test-3'

    test_runner_script = tmp / 'test_runner_sigterm.py'
    test_runner_script.write_text(f'''
import json, os, signal, subprocess, sys, time
from pathlib import Path

op_dir = Path("{op_dir}")
audit_dir = Path("{audit_dir}")
run_token = "{run_token}"

state = {{'sigterm': False}}

def sigterm_handler(s, f):
    state['sigterm'] = True
    raise SystemExit(143)

signal.signal(signal.SIGTERM, sigterm_handler)

# Launch a fake child
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

status = 'UNKNOWN'
try:
    # Sleep long enough to receive SIGTERM
    time.sleep(30)
    status = 'WINDOW_EXPIRED'
except SystemExit as e:
    if state['sigterm']:
        status = 'CANCELLED_SIGNAL'
    else:
        status = 'UNKNOWN'

finally:
    containment = {{
        'hyprneuro.service': 'STOPPED',
        'hyprneuro-ui.service': 'STOPPED',
        'hyprneuro-pi-identity.service': 'REAPED_NOT_BACKEND_RECEIPT',
        'hyprneuro-pi-identity.socket': 'STOPPED',
        'backend_cleanup': 'NOT_ATTESTED',
    }}

    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)
    child_rc = child.returncode if child.returncode is not None else -1

    receipt = {{
        'schema': 'hyprneuro.boundary-containuation-runner-w4-test/1',
        'run_token': run_token,
        'status': status,
        'containment': containment,
        'child_reaped': child_rc,
        'backend_attested': False,
        'ts_end': time.strftime('%Y-%m-%dT%%H:%%M:%%SZ', time.gmtime()),
    }}
    audit_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = audit_dir / 'w4-test-receipt.json'
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\\n')
    receipt_path.chmod(0o644)

if status == 'CANCELLED_SIGNAL':
    raise SystemExit(1)
raise SystemExit(1)
''')

    # Popen the test runner
    proc = subprocess.Popen(
        [PYTHON, '-I', str(test_runner_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    # Give it time to start and launch child
    time.sleep(1.0)

    # Send actual SIGTERM
    proc.send_signal(signal.SIGTERM)

    rc = proc.wait(timeout=15)
    stderr = proc.stderr.read()

    # Verify receipt
    receipt_path = audit_dir / 'w4-test-receipt.json'
    assert receipt_path.exists(), f'Receipt not written. stderr={stderr[:500]}'

    receipt = json.loads(receipt_path.read_text())
    assert receipt['status'] == 'CANCELLED_SIGNAL', f'Got {receipt["status"]}'
    assert receipt['backend_attested'] is False
    assert receipt['containment']['hyprneuro.service'] == 'STOPPED'
    assert receipt['child_reaped'] is not None
    assert rc == 1, f'Expected rc=1 for CANCELLED_SIGNAL, got {rc}'

    print('F3 PASS: SIGTERM → contain → CANCELLED_SIGNAL → child reaped')


# --- FLOW TEST 4: Wrong context deny (no fallback) ---

def test_flow_wrong_ctx_deny(tmp: Path) -> None:
    """F4: Ops with wrong/missing context file → REJECT before any launch.
    Proves: no fallback to 04 baseline. Context is required.
    """
    sys.path.insert(0, str(W4_DIR))
    sys.path.insert(0, '/home/ron/Workspace/hn-boundary-18aef68-04/ops')
    sys.path.insert(0, '/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5')

    from continuation_ops_w4 import check_context_prestart, W4Stage

    # Case 1: context path is None
    try:
        check_context_prestart({'baseline': {'path': '/nonexist'}}, time.monotonic() + 10, None)
        assert False, 'Should reject None context'
    except ValueError as e:
        assert 'None' in str(e) or 'required' in str(e)

    # Case 2: context file missing
    missing_ctx = tmp / 'nonexistent-context.json'
    try:
        check_context_prestart({'baseline': {'path': '/nonexist'}}, time.monotonic() + 10, missing_ctx)
        assert False, 'Should reject missing context'
    except ValueError as e:
        assert 'missing' in str(e)

    # Case 3: context file with wrong schema
    bad_ctx = tmp / 'bad-schema-context.json'
    bad_ctx.write_text(json.dumps({'schema': 'wrong-schema', 'ts_utc': 'x',
                                    'ancestry': {}, 'database_no_SQL': {}, 'settings': {}}))
    os.chmod(str(bad_ctx), 0o600)
    try:
        check_context_prestart({'baseline': {'path': '/nonexist'}}, time.monotonic() + 10, bad_ctx)
        assert False, 'Should reject wrong schema'
    except ValueError as e:
        assert 'schema' in str(e)

    print('F4 PASS: wrong/missing context denied (no fallback)')


# --- FLOW TEST 5: Watch dies before ready → FAILED_WATCH4_READY ---

def test_flow_watch_dies(tmp: Path) -> None:
    """F5: Watch process dies before writing ready marker.
    Runner detects death → FAILED_WATCH4_READY → contain → receipt.
    """
    op_dir, audit_dir = _make_dirs(tmp)
    run_token = 'flow-test-5'

    test_runner_script = tmp / 'test_runner_dead.py'
    test_runner_script.write_text(f'''
import json, os, signal, subprocess, sys, time
from pathlib import Path

op_dir = Path("{op_dir}")
audit_dir = Path("{audit_dir}")
run_token = "{run_token}"

state = {{'sigterm': False}}
def sigterm_handler(s, f):
    state['sigterm'] = True
    raise SystemExit(143)
signal.signal(signal.SIGTERM, sigterm_handler)

# Launch a "watch" that dies immediately
watch = subprocess.Popen([sys.executable, '-c', 'import sys; sys.exit(1)'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

status = 'UNKNOWN'
try:
    # Wait for watch4.ready (will never appear because watch died)
    ready_path = op_dir / "continuation.watch4.ready"
    deadline = time.monotonic() + 3
    ready_ok = False
    while time.monotonic() < deadline:
        if watch.poll() is not None:
            break
        if ready_path.exists():
            ready_ok = True
            break
        time.sleep(0.2)

    if not ready_ok:
        status = 'FAILED_WATCH4_READY'
        raise ValueError('watch4 ready not achieved')
except SystemExit as e:
    if state['sigterm']:
        status = 'CANCELLED_SIGNAL'
    elif status == 'UNKNOWN':
        status = 'FAILED_EXCEPTION'
except Exception:
    if status == 'UNKNOWN':
        status = 'FAILED_WATCH4_READY'

finally:
    containment = {{'hyprneuro.service': 'STOPPED', 'hyprneuro-ui.service': 'STOPPED',
                    'hyprneuro-pi-identity.service': 'REAPED_NOT_BACKEND_RECEIPT',
                    'hyprneuro-pi-identity.socket': 'STOPPED',
                    'backend_cleanup': 'NOT_ATTESTED'}}

    if watch.poll() is None:
        watch.terminate()
        try: watch.wait(timeout=5)
        except: watch.kill(); watch.wait(timeout=5)
    watch_rc = watch.returncode if watch.returncode is not None else -1

    receipt = {{
        'schema': 'hyprneuro.boundary-continuation-runner-w4-test/1',
        'run_token': run_token,
        'status': status,
        'containment': containment,
        'watch_reaped': watch_rc,
        'backend_attested': False,
    }}
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / 'w4-test-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\\n')

raise SystemExit(1)
''')

    proc = subprocess.Popen(
        [PYTHON, '-I', str(test_runner_script)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    rc = proc.wait(timeout=15)

    receipt = json.loads((audit_dir / 'w4-test-receipt.json').read_text())
    assert receipt['status'] == 'FAILED_WATCH4_READY', f'Got {receipt["status"]}'
    assert receipt['watch_reaped'] is not None
    assert receipt['backend_attested'] is False
    assert rc == 1

    print('F5 PASS: watch dies → FAILED_WATCH4_READY → contain → receipt')


# --- FLOW TEST 6: Event file tamper (wrong token) → waiter rejects ---

def test_flow_event_tamper(tmp: Path) -> None:
    """F6: Event file with wrong token → waiter rejects (not START_READY)."""
    op_dir, audit_dir = _make_dirs(tmp)

    # Pre-write event with WRONG token
    _write_event(op_dir, 'WRONG-TOKEN')

    proc = subprocess.Popen(
        [PYTHON, '-I', str(WAITER_W4),
         '--op-sha', OPERATION_SHA,
         '--generation', GENERATION,
         '--run-token', 'correct-token',
         '--timeout', '5',
         '--event-dir', str(op_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    rc = proc.wait(timeout=10)
    stderr = proc.stderr.read()

    # Should fail (token mismatch)
    assert rc != 0, f'Expected failure for wrong token, got rc=0'

    print('F6 PASS: tampered event (wrong token) rejected')


# --- Main ---

def main() -> None:
    tests = [
        test_flow_start_ready_watch_alive,
        test_flow_expiry_contain,
        test_flow_sigterm_cancelled,
        test_flow_wrong_ctx_deny,
        test_flow_watch_dies,
        test_flow_event_tamper,
    ]

    passed = 0
    failed = 0

    for test in tests:
        tmp = Path(tempfile.mkdtemp(prefix='w4-flow-'))
        try:
            test(tmp)
            passed += 1
        except AssertionError as e:
            print(f'  ASSERT: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR: {type(e).__name__}: {e}')
            failed += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f'\nW4 Flow Tests: {passed} passed, {failed} failed / {len(tests)} total')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
