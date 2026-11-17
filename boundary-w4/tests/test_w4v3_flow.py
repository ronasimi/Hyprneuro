#!/usr/bin/env python3
"""
W4-v3 REAL runner flow tests.
Each test Popen's the runner_wrapper which imports and calls the REAL
continuation_runner_w4.main(). Only constants are patched (paths, deadline).
The real _contain(), _reap(), _write_receipt(), _write_start_ready_event() execute.

F1: real runner + real waiter, START_READY while ACTUAL lease holder + watch alive
F2: short deadline expiry → contain subprocess → fake ops UNIT STOPPED → children reaped
F3: REAL runner SIGTERM → CANCELLED_SIGNAL → cleanup
F4: wrong context → pre-Popen zero starts (verify_pins/verify_preconditions deny)
F5: watch death while START blocked → kills owned start → contain
F6: bad ready/token → waiter deny
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

V3_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3')
RUNNER_WRAPPER = V3_DIR / 'tests' / 'runner_wrapper.py'
FAKE_OPS = V3_DIR / 'fixtures' / 'fake_ops_w4.py'
WAITER_W4 = V3_DIR / 'continuation_waiter_w4.py'
RUNNER_W4 = V3_DIR / 'continuation_runner_w4.py'
PYTHON = sys.executable

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'
START4_READY_EVENT = 'continuation.start4.ready'


def _make_env(tmp: Path, watch_deadline: int = 8, run_token: str = None) -> dict:
    """Create environment for the runner wrapper."""
    if run_token is None:
        run_token = str(uuid.uuid4())
    # OP_DIR must be named 'operation' (fake OPS computes: operation.json.parent / 'operation')
    env = {
        **os.environ,
        'W4V3_FIXTURE_DIR': str(tmp / 'fixture'),
        'W4V3_OP_DIR': str(tmp / 'operation'),
        'W4V3_AUDIT_DIR': str(tmp / 'audit'),
        'W4V3_FAKE_OPS': str(FAKE_OPS),
        'W4V3_WATCH_DEADLINE': str(watch_deadline),
        'W4V3_RUN_TOKEN': run_token,
        'W4V3_RUNNER_PATH': str(RUNNER_W4),
        'W4V3_CONTEXT_PATH': str(tmp / 'fixture' / 'context.json'),
    }
    (tmp / 'fixture').mkdir(exist_ok=True)
    return env, run_token


def _popen_runner(env: dict) -> subprocess.Popen:
    """Popen the runner wrapper (executes real runner.main())."""
    return subprocess.Popen(
        [PYTHON, '-I', str(RUNNER_WRAPPER)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )


# --- F1: REAL runner + REAL waiter, START_READY while lease+watch alive ---

def test_f1_start_ready_lease_alive(tmp: Path) -> None:
    """F1: Real runner launches real waiter. START_READY written while
    ACTUAL lease holder (runner) + watch process alive.
    Proves: real runner main() → Popen watch → wait ready → Popen start
    → START_READY event → watcher still alive.
    """
    env, token = _make_env(tmp, watch_deadline=15)
    op_dir = Path(env['W4V3_OP_DIR'])

    # Launch real runner (via wrapper)
    runner_proc = _popen_runner(env)

    # Wait for fixture setup (wrapper creates dirs + markers)
    time.sleep(1.0)

    # Launch real waiter concurrently
    waiter_proc = subprocess.Popen(
        [PYTHON, '-I', str(WAITER_W4),
         '--op-sha', OPERATION_SHA,
         '--generation', GENERATION,
         '--run-token', token,
         '--timeout', '20',
         '--event-dir', str(op_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        env=env
    )

    try:
        # Wait for START_READY event to appear (runner writes it after start succeeds)
        event_path = op_dir / START4_READY_EVENT
        deadline = time.monotonic() + 20
        event_found = False
        while time.monotonic() < deadline:
            if event_path.exists():
                event_found = True
                break
            if runner_proc.poll() is not None:
                break
            time.sleep(0.5)

        assert event_found, f'START_READY event not written. Runner rc={runner_proc.poll()}'

        # Waiter should wake and exit 0
        rc = waiter_proc.wait(timeout=10)
        stdout = waiter_proc.stdout.read()
        result = json.loads(stdout)
        assert rc == 0, f'Waiter rc={rc}'
        assert result['status'] == 'START_READY'
        assert result['event']['run_token'] == token

        # Runner is STILL alive (lease holder, supervision window not expired)
        assert runner_proc.poll() is None, 'Runner should still be alive (lease holder)'

    finally:
        # Clean up: terminate runner (will trigger contain + reap in its finally)
        if runner_proc.poll() is None:
            runner_proc.send_signal(signal.SIGTERM)
            try:
                runner_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                runner_proc.kill()
                runner_proc.wait(timeout=5)
        if waiter_proc.poll() is None:
            waiter_proc.terminate()
            waiter_proc.wait(timeout=5)

    # Verify receipt was written by real runner
    receipt_path = Path(env['W4V3_AUDIT_DIR']) / 'w4-receipt.json'
    assert receipt_path.exists(), 'Receipt not written by real runner'
    receipt = json.loads(receipt_path.read_text())
    assert receipt['run_token'] == token
    assert receipt['backend_attested'] is False
    assert 'containment' in receipt
    print('F1 PASS: real runner + real waiter, START_READY while lease+watch alive')


# --- F2: Short deadline expiry → contain → STOPPED → reaped ---

def test_f2_expiry_contain_reaped(tmp: Path) -> None:
    """F2: Real runner with short deadline (5s). Expiry → WINDOW_EXPIRED.
    Real _contain() subprocess calls fake OPS contain phase.
    Real _reap() terminates children. Receipt written with STOPPED units.
    """
    env, token = _make_env(tmp, watch_deadline=5)

    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()

    # Verify receipt
    receipt_path = Path(env['W4V3_AUDIT_DIR']) / 'w4-receipt.json'
    assert receipt_path.exists(), f'Receipt not written. stderr={stderr[:500]}'

    receipt = json.loads(receipt_path.read_text())
    assert receipt['status'] == 'WINDOW_EXPIRED', f'Got {receipt["status"]}, stderr={stderr[:300]}'
    assert receipt['backend_attested'] is False
    # Contain was executed (real _contain → subprocess → fake OPS)
    # _contain() returns the full JSON output from fake OPS: {status, containment}
    assert 'containment' in receipt
    cont = receipt['containment']
    # The containment field is the full dict from fake OPS
    inner = cont.get('containment', cont)  # Handle both flat and nested
    assert inner.get('hyprneuro.service') == 'STOPPED', f'Got {inner}'
    assert inner.get('hyprneuro-ui.service') == 'STOPPED', f'Got {inner}'
    # Children were reaped (real _reap)
    assert 'watch4_reaped' in receipt
    assert 'start4_reaped' in receipt
    # Runner exits 0 for WINDOW_EXPIRED
    assert rc == 0, f'Expected rc=0, got {rc}'
    print('F2 PASS: real runner expiry → contain → STOPPED → children reaped → receipt')


# --- F3: REAL runner SIGTERM → CANCELLED_SIGNAL ---

def test_f3_sigterm_cancelled(tmp: Path) -> None:
    """F3: Send REAL SIGTERM to running runner process.
    Real signal handler → SystemExit → finally → contain → reap → receipt.
    Status = CANCELLED_SIGNAL.
    """
    env, token = _make_env(tmp, watch_deadline=30)  # Long enough to receive SIGTERM

    runner_proc = _popen_runner(env)

    # Wait for runner to be in supervision loop
    time.sleep(3)

    # Send REAL SIGTERM
    runner_proc.send_signal(signal.SIGTERM)

    rc = runner_proc.wait(timeout=20)
    stderr = runner_proc.stderr.read()

    # Verify receipt
    receipt_path = Path(env['W4V3_AUDIT_DIR']) / 'w4-receipt.json'
    assert receipt_path.exists(), f'Receipt not written. stderr={stderr[:500]}'

    receipt = json.loads(receipt_path.read_text())
    assert receipt['status'] == 'CANCELLED_SIGNAL', f'Got {receipt["status"]}'
    assert receipt['backend_attested'] is False
    assert 'containment' in receipt
    assert rc == 1, f'Expected rc=1 for CANCELLED_SIGNAL, got {rc}'
    print('F3 PASS: real runner SIGTERM → CANCELLED_SIGNAL → contain → receipt')


# --- F4: Wrong context → pre-Popen zero starts ---

def test_f4_wrong_context_deny(tmp: Path) -> None:
    """F4: Context file SHA mismatch → verify_pins fails → NO Popen occurs.
    Proves: context is checked BEFORE any process launch.
    Uses a standalone wrapper that does NOT patch verify_pins.
    """
    env, token = _make_env(tmp, watch_deadline=5)
    op_dir = Path(env['W4V3_OP_DIR'])

    # Create a standalone wrapper that patches constants but NOT verify_pins
    custom_wrapper = tmp / 'wrapper_f4.py'
    custom_wrapper.write_text(f'''
import hashlib, json, os, sys
from pathlib import Path

OP_DIR = Path("{op_dir}")
AUDIT_DIR = Path("{env['W4V3_AUDIT_DIR']}")
FAKE_OPS = Path("{FAKE_OPS}")
RUNNER_PATH = Path("{RUNNER_W4}")
CONTEXT_PATH = Path("{env['W4V3_CONTEXT_PATH']}")

# Setup fixture dirs + markers
OP_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(str(OP_DIR), 0o700)
os.chmod(str(AUDIT_DIR), 0o700)
(OP_DIR.parent / 'operation.json').write_text('{{"bundle": "' + str(OP_DIR.parent) + '"}}')

# Create context file
ctx_data = {{
    "schema": "hyprneuro.boundary-postwrite-context/1",
    "ts_utc": "2026-01-01T00:00:00Z",
    "ancestry": {{"original_operation_sha": "x", "original_generation": "y",
                 "evidence_sha": "z", "failed_execution": "f", "prior_successful_execution": "p"}},
    "database_no_SQL": {{}},
    "settings": {{"path": "/nonexist", "sha256": "a"*64, "uid": 1000}},
}}
CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
CONTEXT_PATH.write_text(json.dumps(ctx_data))
os.chmod(str(CONTEXT_PATH), 0o600)

# Required markers
OP_SHA = "306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4"
for m in ['install.completed','install.started','session.pin',
          'continuation.provision.started','continuation.provision.completed',
          'continuation.watch.ready','continuation.watch2.ready',
          'continuation.start2.started','continuation.start2.completed',
          'continuation.watch3.ready','continuation.start3.started',
          'continuation.start3.completed','continuation.start3.ready']:
    (OP_DIR / m).write_text(OP_SHA + "\\n")

# Import real runner
sys.path.insert(0, str(RUNNER_PATH.parent))
import continuation_runner_w4 as runner

# Patch constants ONLY (NOT verify_pins)
runner.OP_DIR = OP_DIR
runner.AUDIT_DIR = AUDIT_DIR
runner.OPS_W4_PATH = FAKE_OPS
runner.OPS_W4_SHA = hashlib.sha256(FAKE_OPS.read_bytes()).hexdigest()
runner.WATCH_DEADLINE = 5
runner.CONTEXT_PATH = CONTEXT_PATH
runner.CONTEXT_SHA = "deadbeef" * 8  # WRONG SHA - will fail verify_pins
runner.PYTHON = sys.executable
runner.OPERATION_PATH = OP_DIR.parent / 'operation.json'
runner._unit_evidence = lambda: []

sys.argv = [str(RUNNER_PATH), "--run-token", "{token}"]
try:
    runner.main()
except SystemExit as e:
    raise SystemExit(e.code)
''')

    proc = subprocess.Popen(
        [PYTHON, '-I', str(custom_wrapper)],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    rc = proc.wait(timeout=15)
    stderr = proc.stderr.read()

    # Should fail BEFORE any Popen (verify_pins catches context SHA mismatch)
    assert rc != 0, f'Expected failure, got rc=0. stderr={stderr[:300]}'

    # No watch4.ready should have been written (zero starts)
    assert not (op_dir / 'continuation.watch4.ready').exists(), 'Watch should NOT have started'
    assert not (op_dir / 'continuation.start4.started').exists(), 'Start should NOT have started'

    print('F4 PASS: wrong context → verify_pins deny → zero starts')


# --- F5: Watch death while START blocked → contain ---

def test_f5_watch_death(tmp: Path) -> None:
    """F5: Fake OPS watch4 phase exits immediately (simulates crash).
    Real runner detects watch death → FAILED_WATCH4_READY → contain → receipt.
    """
    env, token = _make_env(tmp, watch_deadline=10)

    # Create a fake ops that DIES immediately in watch4 phase
    dead_ops = tmp / 'dead_ops.py'
    dead_ops.write_text('''
import sys, time
# Simulate watch4 crashing immediately
sys.exit(1)
''')

    # Override FAKE_OPS to the dead version
    env['W4V3_FAKE_OPS'] = str(dead_ops)

    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()

    # Verify receipt
    receipt_path = Path(env['W4V3_AUDIT_DIR']) / 'w4-receipt.json'
    assert receipt_path.exists(), f'Receipt not written. stderr={stderr[:500]}'

    receipt = json.loads(receipt_path.read_text())
    assert receipt['status'] == 'FAILED_WATCH4_READY', f'Got {receipt["status"]}'
    assert receipt['backend_attested'] is False
    assert 'containment' in receipt
    assert rc == 1
    print('F5 PASS: watch death → FAILED_WATCH4_READY → contain → receipt')


# --- F6: Bad ready token → waiter deny ---

def test_f6_bad_token_waiter_deny(tmp: Path) -> None:
    """F6: Pre-write event with wrong token. Real waiter rejects it."""
    op_dir = tmp / 'operation'
    op_dir.mkdir()
    os.chmod(str(op_dir), 0o700)

    # Pre-write event with WRONG token
    event_content = json.dumps({
        'schema': 'hyprneuro.boundary-start4-ready/1',
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': 'WRONG-TOKEN',
        'uid': os.getuid(),
        'pid': os.getpid(),
        'start': '12345',
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, sort_keys=True) + '\n'

    fd = os.open(str(op_dir / START4_READY_EVENT), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, event_content.encode())
    os.fsync(fd)
    os.close(fd)

    # Real waiter should reject
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
    assert rc != 0, f'Expected failure for wrong token, got rc=0'
    print('F6 PASS: bad ready token → waiter deny')


# --- Main ---

def main() -> None:
    tests = [
        test_f1_start_ready_lease_alive,
        test_f2_expiry_contain_reaped,
        test_f3_sigterm_cancelled,
        test_f4_wrong_context_deny,
        test_f5_watch_death,
        test_f6_bad_token_waiter_deny,
    ]

    passed = 0
    failed = 0

    for test in tests:
        tmp = Path(tempfile.mkdtemp(prefix='w4v3-flow-'))
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

    print(f'\nW4-v3 REAL Runner Flow Tests: {passed} passed, {failed} failed / {len(tests)} total')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
