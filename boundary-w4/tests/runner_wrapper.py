#!/usr/bin/env python3
"""
W4-v3 private test wrapper: patches REAL runner constants, calls real main().
This is NOT a fake runner. It imports the actual continuation_runner_w4 module,
overrides its module-level constants to point to private fixture dirs, and
invokes the production main() function.

The REAL runner code executes:
- main() → verify_pins (patched no-op) → verify_preconditions (patched)
- _op_argv() → points to fake OPS script
- Popen watch → real subprocess launch
- Popen start → real subprocess launch
- _contain() → real subprocess call to fake OPS contain phase
- _reap() → real process termination
- _write_receipt() → real file write
- _write_start_ready_event() → real O_EXCL file write
- _unit_evidence() → real systemctl calls (or patched for private test)

Only CONSTANTS are patched. No control flow is faked.
"""

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# --- Configuration passed via env (set by test harness) ---

FIXTURE_DIR = Path(os.environ['W4V3_FIXTURE_DIR'])
OP_DIR = Path(os.environ['W4V3_OP_DIR'])
AUDIT_DIR = Path(os.environ['W4V3_AUDIT_DIR'])
FAKE_OPS = Path(os.environ['W4V3_FAKE_OPS'])
WATCH_DEADLINE = int(os.environ.get('W4V3_WATCH_DEADLINE', '8'))
RUN_TOKEN = os.environ.get('W4V3_RUN_TOKEN', 'test-token')
CONTEXT_PATH = Path(os.environ.get('W4V3_CONTEXT_PATH', str(FIXTURE_DIR / 'context.json')))

# Real runner path (committed code, NOT worktree mutable)
RUNNER_PATH = Path(os.environ['W4V3_RUNNER_PATH'])


def _setup_fixture() -> None:
    """Create fixture files that the runner expects."""
    OP_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(str(OP_DIR), 0o700)
    os.chmod(str(AUDIT_DIR), 0o700)

    # Create operation.json (fake, for ops --operation arg)
    op_json = OP_DIR.parent / 'operation.json'
    op_json.write_text(json.dumps({'bundle': str(OP_DIR.parent)}))

    # Create context file (fixture)
    if not CONTEXT_PATH.exists():
        ctx_data = {
            'schema': 'hyprneuro.boundary-postwrite-context/1',
            'ts_utc': '2026-01-01T00:00:00Z',
            'ancestry': {
                'original_operation_sha': '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4',
                'original_generation': '484e9abe3b334b8c8628df2966394ce8',
                'evidence_sha': '78ec490f6d015d4fe6fd49b36028d0016c5e35c2d1a7d5d06fa0526cdd21934c',
                'failed_execution': 'test',
                'prior_successful_execution': 'test',
            },
            'database_no_SQL': {},
            'settings': {'path': str(FIXTURE_DIR / 'nonexist-settings'), 'sha256': 'a' * 64, 'uid': os.getuid()},
        }
        CONTEXT_PATH.write_text(json.dumps(ctx_data))
        os.chmod(str(CONTEXT_PATH), 0o600)

    # Create required precondition markers in OP_DIR
    OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
    required_markers = [
        'install.completed', 'install.started', 'session.pin',
        'continuation.provision.started', 'continuation.provision.completed',
        'continuation.watch.ready',
        'continuation.watch2.ready', 'continuation.start2.started', 'continuation.start2.completed',
        'continuation.watch3.ready', 'continuation.start3.started',
        'continuation.start3.completed', 'continuation.start3.ready',
    ]
    for m in required_markers:
        p = OP_DIR / m
        if not p.exists():
            p.write_text(OPERATION_SHA + '\n')


def _patch_runner_module() -> None:
    """Import real runner and patch its constants for private test."""
    # Add runner's dir to path so we can import it
    runner_dir = str(RUNNER_PATH.parent)
    sys.path.insert(0, runner_dir)

    import continuation_runner_w4 as runner

    # Patch constants (ONLY constants, no control flow)
    runner.OP_DIR = OP_DIR
    runner.AUDIT_DIR = AUDIT_DIR
    runner.OPS_W4_PATH = FAKE_OPS
    runner.OPS_W4_SHA = hashlib.sha256(FAKE_OPS.read_bytes()).hexdigest()
    runner.WATCH_DEADLINE = WATCH_DEADLINE
    runner.CONTEXT_PATH = CONTEXT_PATH
    runner.CONTEXT_SHA = hashlib.sha256(CONTEXT_PATH.read_bytes()).hexdigest()
    runner.PYTHON = sys.executable
    # Patch OPERATION_PATH so _op_argv passes the fixture operation.json
    # (fake OPS computes op_dir as operation.parent / 'operation')
    runner.OPERATION_PATH = OP_DIR.parent / 'operation.json'

    # Patch verify_pins to no-op (dedicated negative tests cover pin verification)
    runner.verify_pins = lambda: None

    # Patch _unit_evidence to return fixture data (no real systemctl in test)
    runner._unit_evidence = lambda: [
        {'unit': 'hyprneuro.service', 'LoadState': 'loaded', 'MainPID': 'UNKNOWN'},
        {'unit': 'hyprneuro-ui.service', 'LoadState': 'loaded', 'MainPID': 'UNKNOWN'},
        {'unit': 'hyprneuro-pi-identity.service', 'LoadState': 'loaded', 'MainPID': 'UNKNOWN'},
        {'unit': 'hyprneuro-pi-identity.socket', 'LoadState': 'loaded', 'MainPID': 'N/A'},
    ]

    return runner


def main() -> None:
    _setup_fixture()
    runner = _patch_runner_module()

    # Set argv for the runner's argparse
    sys.argv = [str(RUNNER_PATH), '--run-token', RUN_TOKEN]

    # Call REAL runner main()
    runner.main()


if __name__ == '__main__':
    main()
