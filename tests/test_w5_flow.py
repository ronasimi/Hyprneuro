#!/usr/bin/env python3
"""
W5 REAL runner flow tests. Adapts the reviewed W4v3 flow pattern (test_w4v3_flow.py).
Each test Popen's the W5 wrapper which imports and calls the REAL
continuation_runner_w5.main(). Only constants are patched (paths, deadline, PYTHON, SHA).
The REAL _contain(), _reap(), _write_receipt(), _write_start_ready_event() execute.
verify_preconditions_w5 (corrected W5 preconditions) runs for REAL.
Private fake-OS boundary (fake_ops_w5). prod OP_DIR is NEVER touched (verified before/after).

F1: real runner + real waiter, START_READY (start5.ready) while runner alive + watch alive
F2: short deadline expiry -> contain -> STOPPED -> children reaped
F3: REAL runner SIGTERM -> CANCELLED_SIGNAL -> contain
F4: wrong context SHA pre-Popen -> zero starts (verify_pins deny, REAL verify_pins)
F5a: watch death during startup (no ready) -> FAILED_WATCH5_READY -> contain
F5b: watch death after ready -> FAILED_WATCH_DIED(_POST_START) -> contain
F6: bad token -> real waiter deny
F7: start failure (start5 rc!=0) -> FAILED_START5_RC -> contain

No machine lease is required: the boundary is fully private (fake ops writes markers only;
no real systemctl / D-Bus / model / SQL / GUI). Real timestamps are recorded in receipts/logs.
Run: <venv-python> -I -B tests/test_w5_flow.py
"""
import hashlib
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

W5_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5')
RUNNER_WRAPPER = W5_DIR / 'tests' / 'w5_runner_wrapper.py'
FAKE_OPS = W5_DIR / 'tests' / 'fake_ops_w5.py'
WAITER_W5 = W5_DIR / 'continuation_waiter_w5.py'
RUNNER_W5 = W5_DIR / 'continuation_runner_w5.py'
PYTHON = sys.executable

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'
START5_READY_EVENT = 'continuation.start5.ready'
REAL_OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')


def _prod_op_snapshot() -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(REAL_OP_DIR.iterdir()) if p.is_file()}


def _make_env(tmp: Path, watch_deadline: int, mode: str = 'normal',
              patch_pins: bool = True, ctx_sha_override: str = None) -> dict:
    token = str(uuid.uuid4())
    env = {
        **os.environ,
        'W5_FIXTURE_DIR': str(tmp / 'fixture'),
        'W5_OP_DIR': str(tmp / 'operation'),
        'W5_AUDIT_DIR': str(tmp / 'audit'),
        'W5_FAKE_OPS': str(FAKE_OPS),
        'W5_WATCH_DEADLINE': str(watch_deadline),
        'W5_RUN_TOKEN': token,
        'W5_RUNNER_PATH': str(RUNNER_W5),
        'W5_CONTEXT_PATH': str(tmp / 'fixture' / 'context.json'),
        'W5_FAKE_MODE': mode,
        'W5_PATCH_VERIFY_PINS': '1' if patch_pins else '0',
    }
    if ctx_sha_override:
        env['W5_CONTEXT_SHA_OVERRIDE'] = ctx_sha_override
    (tmp / 'fixture').mkdir(exist_ok=True)
    return env, token


def _popen_runner(env: dict) -> subprocess.Popen:
    return subprocess.Popen([PYTHON, '-I', '-B', str(RUNNER_WRAPPER)], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _receipt(env: dict) -> dict:
    path = Path(env['W5_AUDIT_DIR']) / 'w5-receipt.json'
    return json.loads(path.read_text())


# --- F1: REAL runner + REAL waiter, START_READY while runner alive + watch alive ---
def test_f1_start_ready_lease_alive(tmp: Path) -> None:
    env, token = _make_env(tmp, 15)
    op_dir = Path(env['W5_OP_DIR'])
    runner_proc = _popen_runner(env)
    time.sleep(1.0)  # fixture setup
    waiter_proc = subprocess.Popen(
        [PYTHON, '-I', '-B', str(WAITER_W5), '--op-sha', OPERATION_SHA, '--generation', GENERATION,
         '--run-token', token, '--timeout', '20', '--event-dir', str(op_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        event_path = op_dir / START5_READY_EVENT
        found = False
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if event_path.exists():
                found = True
                break
            if runner_proc.poll() is not None:
                break
            time.sleep(0.5)
        assert found, f'START5_READY not written. runner rc={runner_proc.poll()}'
        rc = waiter_proc.wait(timeout=10)
        result = json.loads(waiter_proc.stdout.read())
        assert rc == 0, f'waiter rc={rc}'
        assert result['status'] == 'START_READY'
        assert result['event']['run_token'] == token
        assert runner_proc.poll() is None, 'runner should still be alive (supervision window)'
    finally:
        if runner_proc.poll() is None:
            runner_proc.send_signal(signal.SIGTERM)
            try:
                runner_proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                runner_proc.kill(); runner_proc.wait(timeout=5)
        if waiter_proc.poll() is None:
            waiter_proc.terminate(); waiter_proc.wait(timeout=5)
    r = _receipt(env)
    assert r['run_token'] == token
    assert r['backend_attested'] is False
    assert 'containment' in r
    print('F1 PASS: real runner + real waiter, START5_READY while runner ALIVE + watch alive')


# --- F2: short deadline expiry -> contain -> STOPPED -> reaped ---
def test_f2_expiry_contain_reaped(tmp: Path) -> None:
    env, token = _make_env(tmp, 5)
    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()
    r = _receipt(env)
    assert r['status'] == 'WINDOW_EXPIRED', f"got {r['status']}, stderr={stderr[:300]}"
    assert r['backend_attested'] is False
    inner = r['containment'].get('containment', r['containment'])
    assert inner.get('hyprneuro.service') == 'STOPPED', f"got {inner}"
    assert inner.get('hyprneuro-ui.service') == 'STOPPED', f"got {inner}"
    assert r.get('watch5_reaped') is not None
    assert r.get('start5_reaped') is not None
    assert rc == 0, f'expected rc=0, got {rc}'
    print('F2 PASS: real runner expiry -> contain -> STOPPED -> children reaped -> receipt')


# --- F3: REAL runner SIGTERM -> CANCELLED_SIGNAL ---
def test_f3_sigterm_cancelled(tmp: Path) -> None:
    env, token = _make_env(tmp, 30)
    runner_proc = _popen_runner(env)
    time.sleep(3)
    runner_proc.send_signal(signal.SIGTERM)
    rc = runner_proc.wait(timeout=20)
    stderr = runner_proc.stderr.read()
    r = _receipt(env)
    assert r['status'] == 'CANCELLED_SIGNAL', f"got {r['status']}, stderr={stderr[:300]}"
    assert r['backend_attested'] is False
    assert 'containment' in r
    assert rc == 1, f'expected rc=1, got {rc}'
    print('F3 PASS: real runner SIGTERM -> CANCELLED_SIGNAL -> contain -> receipt')


# --- F4: wrong context SHA pre-Popen -> zero starts (REAL verify_pins deny) ---
def test_f4_wrong_context_deny(tmp: Path) -> None:
    env, token = _make_env(tmp, 5, patch_pins=False, ctx_sha_override='deadbeef' * 8)
    op_dir = Path(env['W5_OP_DIR'])
    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=15)
    stderr = runner_proc.stderr.read()
    assert rc != 0, f'expected failure, got rc=0. stderr={stderr[:300]}'
    assert 'pin SHA mismatch' in stderr, f'expected context pin SHA mismatch, got: {stderr[:500]}'
    assert not (op_dir / 'continuation.watch5.ready').exists(), 'watch5 should NOT have started'
    assert not (op_dir / 'continuation.start5.started').exists(), 'start5 should NOT have started'
    print('F4 PASS: wrong context SHA -> REAL verify_pins deny -> zero starts')


# --- F5a: watch death during startup (no ready) -> FAILED_WATCH5_READY ---
def test_f5a_watch_death_early(tmp: Path) -> None:
    env, token = _make_env(tmp, 10, mode='watch-die-early')
    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()
    r = _receipt(env)
    assert r['status'] == 'FAILED_WATCH5_READY', f"got {r['status']}, stderr={stderr[:300]}"
    assert r['backend_attested'] is False
    assert 'containment' in r
    assert rc == 1
    print('F5a PASS: watch death during startup -> FAILED_WATCH5_READY -> contain -> receipt')


# --- F5b: watch death after ready -> FAILED_WATCH_DIED(_POST_START) ---
def test_f5b_watch_death_after_ready(tmp: Path) -> None:
    env, token = _make_env(tmp, 10, mode='watch-die-after-ready')
    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()
    r = _receipt(env)
    assert r['status'] in ('FAILED_WATCH_DIED', 'FAILED_WATCH_DIED_POST_START'), \
        f"got {r['status']}, stderr={stderr[:300]}"
    assert r['backend_attested'] is False
    assert 'containment' in r
    assert rc == 1
    print(f"F5b PASS: watch death after ready -> {r['status']} -> contain -> receipt")


# --- F6: bad ready token -> real waiter deny ---
def test_f6_bad_token_waiter_deny(tmp: Path) -> None:
    op_dir = tmp / 'operation'
    op_dir.mkdir()
    os.chmod(str(op_dir), 0o700)
    event = json.dumps({
        'schema': 'hyprneuro.boundary-start5-ready/1',
        'operation_sha256': OPERATION_SHA, 'generation': GENERATION,
        'run_token': 'WRONG-TOKEN', 'uid': os.getuid(), 'pid': os.getpid(),
        'start': '12345',
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
    }, sort_keys=True) + '\n'
    fd = os.open(str(op_dir / START5_READY_EVENT), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.write(fd, event.encode()); os.fsync(fd); os.close(fd)
    proc = subprocess.Popen(
        [PYTHON, '-I', '-B', str(WAITER_W5), '--op-sha', OPERATION_SHA, '--generation', GENERATION,
         '--run-token', 'correct-token', '--timeout', '5', '--event-dir', str(op_dir)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    rc = proc.wait(timeout=10)
    assert rc != 0, f'expected failure for wrong token, got rc=0'
    print('F6 PASS: bad start5.ready token -> real waiter deny')


# --- F7: start failure (start5 rc!=0) -> FAILED_START5_RC ---
def test_f7_start_failure(tmp: Path) -> None:
    env, token = _make_env(tmp, 15, mode='start-fail')
    runner_proc = _popen_runner(env)
    rc = runner_proc.wait(timeout=30)
    stderr = runner_proc.stderr.read()
    r = _receipt(env)
    assert str(r['status']).startswith('FAILED_START5_RC'), \
        f"got {r['status']}, stderr={stderr[:300]}"
    assert r['backend_attested'] is False
    assert 'containment' in r
    assert rc == 1
    print(f"F7 PASS: start failure -> {r['status']} -> contain -> receipt")


def main() -> None:
    tests = [
        test_f1_start_ready_lease_alive,
        test_f2_expiry_contain_reaped,
        test_f3_sigterm_cancelled,
        test_f4_wrong_context_deny,
        test_f5a_watch_death_early,
        test_f5b_watch_death_after_ready,
        test_f6_bad_token_waiter_deny,
        test_f7_start_failure,
    ]
    prod_before = _prod_op_snapshot()
    passed = failed = 0
    for test in tests:
        tmp = Path(tempfile.mkdtemp(prefix='w5-flow-'))
        t0 = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        try:
            test(tmp)
            passed += 1
        except AssertionError as e:
            print(f'  ASSERT: {e}'); failed += 1
        except Exception as e:
            print(f'  ERROR: {type(e).__name__}: {e}'); failed += 1
        finally:
            print(f'    [ts {t0}] {test.__name__}')
            shutil.rmtree(tmp, ignore_errors=True)
    prod_after = _prod_op_snapshot()
    print(f'\nW5 REAL Runner Flow Tests: {passed} passed, {failed} failed / {len(tests)} total')
    if prod_before != prod_after:
        print('PROD OP_DIR MUTATED (FAILURE):')
        for k in set(prod_before) | set(prod_after):
            if prod_before.get(k) != prod_after.get(k):
                print(f'  {k}: {prod_before.get(k)} -> {prod_after.get(k)}')
        failed += 1
    else:
        print(f'PROD OP_DIR UNCHANGED ({len(prod_before)} markers, real watch4.ready preserved)')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
