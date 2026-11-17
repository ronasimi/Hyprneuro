#!/usr/bin/env python3
"""
W5 private test wrapper: patches REAL W5 runner constants, calls real main().
NOT a fake runner. Imports the actual continuation_runner_w5 module, overrides its
module-level constants to point to private fixture dirs, and invokes production main().

The REAL runner code executes:
- main() -> verify_pins (no-op by default; REAL in F4 via W5_PATCH_VERIFY_PINS=0)
          -> verify_preconditions_w5 (ALWAYS REAL: corrected W5 preconditions)
- _op_argv() -> points to fake OPS script
- Popen watch5 -> real subprocess launch
- Popen start5 -> real subprocess launch
- _contain() -> real subprocess call to fake OPS contain phase
- _reap() -> real process termination
- _write_receipt() -> real file write (w5-receipt.json)
- _write_start_ready_event() -> real O_EXCL file write (continuation.start5.ready)
- _unit_evidence() -> fixture (no real systemctl in private test)

Only CONSTANTS are patched (paths, deadline, PYTHON, SHA literals). No control flow faked.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

# --- Configuration via env (set by the flow test) ---
FIXTURE_DIR = Path(os.environ['W5_FIXTURE_DIR'])
OP_DIR = Path(os.environ['W5_OP_DIR'])
AUDIT_DIR = Path(os.environ['W5_AUDIT_DIR'])
FAKE_OPS = Path(os.environ['W5_FAKE_OPS'])
WATCH_DEADLINE = int(os.environ.get('W5_WATCH_DEADLINE', '8'))
RUN_TOKEN = os.environ.get('W5_RUN_TOKEN', 'test-token')
CONTEXT_PATH = Path(os.environ.get('W5_CONTEXT_PATH', str(FIXTURE_DIR / 'context.json')))
RUNNER_PATH = Path(os.environ['W5_RUNNER_PATH'])
PATCH_VERIFY_PINS = os.environ.get('W5_PATCH_VERIFY_PINS', '1') == '1'
CONTEXT_SHA_OVERRIDE = os.environ.get('W5_CONTEXT_SHA_OVERRIDE')  # F4: force a wrong SHA

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'


def _setup_fixture() -> None:
    OP_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(str(OP_DIR), 0o700)
    os.chmod(str(AUDIT_DIR), 0o700)

    # operation.json (fake, for ops --operation; op_dir = operation.parent / 'operation')
    (OP_DIR.parent / 'operation.json').write_text(
        json.dumps({'bundle': str(OP_DIR.parent), 'generation': GENERATION}))

    # W5 context (private, valid schema + 5-field ancestry)
    if not CONTEXT_PATH.exists():
        ctx = {
            'schema': 'hyprneuro.boundary-postwrite-context/1',
            'ts_utc': '2026-01-01T00:00:00Z',
            'ancestry': {
                'original_operation_sha': OPERATION_SHA,
                'original_generation': GENERATION,
                'known_failed_w3_execution': 'exec-w3-known-failed',
                'prior_successful_execution': 'exec-prior-ok',
                'source_context_sha': '51f9109f0c9515045ce9fbc0f16c1b15bb8cf54116dfe8a230d4aa3a526e39bc',
            },
            'database_no_SQL': {},
            'settings': {'path': str(FIXTURE_DIR / 'settings.json'),
                         'sha256': 'a' * 64, 'uid': os.getuid()},
        }
        CONTEXT_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONTEXT_PATH.write_text(json.dumps(ctx))
        os.chmod(str(CONTEXT_PATH), 0o600)

    # Required precondition markers: known-failed W3 state (watch3 ready; start3.* ABSENT)
    for m in ('install.completed', 'install.started', 'session.pin',
              'continuation.provision.started', 'continuation.provision.completed',
              'continuation.watch.ready',
              'continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed',
              'continuation.watch3.ready'):
        p = OP_DIR / m
        if not p.exists():
            p.write_text(OPERATION_SHA + '\n')

    # old W4 ready: preserved stale event (private content; SHA pinned to it by the wrapper)
    w4 = OP_DIR / 'continuation.watch4.ready'
    if not w4.exists():
        w4.write_text((json.dumps({
            'schema': 'hyprneuro.boundary-watch4-ready/1',
            'operation_sha256': OPERATION_SHA,
            'run_token': 'stale-w4-token',
            'pid': 1032477,
            'start': '13858149',
        }, sort_keys=True) + '\n'))
        os.chmod(str(w4), 0o400)


def _patch() -> None:
    sys.path.insert(0, str(RUNNER_PATH.parent))
    import continuation_runner_w5 as runner
    runner.OP_DIR = OP_DIR
    runner.AUDIT_DIR = AUDIT_DIR
    runner.OPS_W5_PATH = FAKE_OPS
    runner.OPS_W5_SHA = hashlib.sha256(FAKE_OPS.read_bytes()).hexdigest()
    runner.WATCH_DEADLINE = WATCH_DEADLINE
    runner.CONTEXT_W5_PATH = CONTEXT_PATH
    runner.CONTEXT_W5_SHA = (CONTEXT_SHA_OVERRIDE
                             if CONTEXT_SHA_OVERRIDE
                             else hashlib.sha256(CONTEXT_PATH.read_bytes()).hexdigest())
    runner.OLD_W4_READY_PATH = OP_DIR / 'continuation.watch4.ready'
    runner.OLD_W4_READY_SHA = hashlib.sha256((OP_DIR / 'continuation.watch4.ready').read_bytes()).hexdigest()
    runner.PYTHON = sys.executable
    runner.OPERATION_PATH = OP_DIR.parent / 'operation.json'
    if PATCH_VERIFY_PINS:
        runner.verify_pins = lambda: None
    # fixture unit evidence (no real systemctl in private test)
    runner._unit_evidence = lambda: [
        {'unit': u, 'LoadState': 'loaded', 'MainPID': 'UNKNOWN'}
        for u in ('hyprneuro.service', 'hyprneuro-ui.service', 'hyprneuro-pi-identity.service')
    ] + [{'unit': 'hyprneuro-pi-identity.socket', 'LoadState': 'loaded', 'MainPID': 'N/A'}]
    return runner


def main() -> None:
    _setup_fixture()
    runner = _patch()
    sys.argv = [str(RUNNER_PATH), '--run-token', RUN_TOKEN]
    runner.main()


if __name__ == '__main__':
    main()
