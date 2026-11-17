#!/usr/bin/env python3
"""
Fake OPS boundary for W5 private flow tests.
Simulates ops phases (watch5, start5, contain) WITHOUT touching real services.
This is the ONLY fake component; the REAL runner (continuation_runner_w5.main) orchestrates it.

Phases (same argv as real continuation_ops_w5):
- watch5: write continuation.watch5.ready (real pid + start ticks), then stay alive
- start5: validate watch5.ready, write start5.started + start5.completed (receipt), exit 0
- contain: print fake 4-unit STOPPED states to stdout (JSON)

Behavior mode (env W5_FAKE_MODE):
- 'normal' (default): watch5 stays alive; start5 succeeds
- 'watch-die-early':     watch5 exits 1 immediately (never writes ready)
- 'watch-die-after-ready': watch5 writes ready, then exits 1
- 'start-fail':          start5 exits 1 (after validating ready)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

WATCH5_READY = 'continuation.watch5.ready'
START5_STARTED = 'continuation.start5.started'
START5_COMPLETED = 'continuation.start5.completed'

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'


def _start_ticks(pid):
    return (Path('/proc') / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()[19]


def _write(path, data, mode=0o400):
    fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, mode)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)


def phase_watch5(op_dir: Path, run_token: str, mode: str) -> None:
    if mode == 'watch-die-early':
        sys.exit(1)  # never writes ready
    ready = {
        'schema': 'hyprneuro.boundary-watch5-ready/1',
        'operation_sha256': OPERATION_SHA,
        'run_token': run_token,
        'pid': os.getpid(),
        'start': _start_ticks(os.getpid()),
    }
    _write(op_dir / WATCH5_READY, (json.dumps(ready, sort_keys=True) + '\n').encode())
    if mode == 'watch-die-after-ready':
        # Die AFTER the runner's 1s ready-poll has read the ready file, so the flow
        # reaches supervision (start5 succeeds first) and reports FAILED_WATCH_DIED(_POST_START)
        # rather than the 'dead before ready' path. (test timing; W5 source unchanged)
        time.sleep(3.0)
        sys.exit(1)  # dies after ready + start5 completion
    time.sleep(300)  # normal: stay alive (supervised)


def phase_start5(op_dir: Path, run_token: str, mode: str) -> None:
    ready_path = op_dir / WATCH5_READY
    if not ready_path.exists():
        print(json.dumps({'status': 'FAILED', 'error': 'watch5.ready missing'}))
        sys.exit(1)
    ready = json.loads(ready_path.read_text())
    if ready.get('run_token') != run_token:
        print(json.dumps({'status': 'FAILED', 'error': 'token mismatch'}))
        sys.exit(1)
    if mode == 'start-fail':
        print(json.dumps({'status': 'FAILED', 'error': 'simulated start failure'}))
        sys.exit(1)
    _write(op_dir / START5_STARTED, (OPERATION_SHA + '\n').encode())
    time.sleep(0.3)
    completed = {
        'schema': 'hyprneuro.boundary-start-receipt/1',
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': run_token,
        'broker': {'unit': 'hyprneuro.service', 'pid': '9001', 'start': 'abc'},
        'ui': {'unit': 'hyprneuro-ui.service', 'pid': '9002', 'start': 'def'},
    }
    _write(op_dir / START5_COMPLETED, (json.dumps(completed, sort_keys=True) + '\n').encode())
    print(json.dumps({'status': 'PASS', 'phase': 'start5', 'run_token': run_token}))


def phase_contain(op_dir: Path) -> None:
    result = {
        'status': 'CONTAINED',
        'containment': {
            'hyprneuro.service': 'STOPPED',
            'hyprneuro-ui.service': 'STOPPED',
            'hyprneuro-pi-identity.service': 'REAPED_NOT_BACKEND_RECEIPT',
            'hyprneuro-pi-identity.socket': 'STOPPED',
            'backend_cleanup': 'NOT_ATTESTED',
        },
    }
    print(json.dumps(result, sort_keys=True))


def main() -> None:
    p = argparse.ArgumentParser(description='Fake OPS boundary for W5 private flow tests')
    p.add_argument('--operation', type=Path, required=True)
    p.add_argument('--operation-sha256', required=True)
    p.add_argument('--phase', choices=('watch5', 'start5', 'contain'), required=True)
    p.add_argument('--run-token', required=True)
    p.add_argument('--context', type=Path, required=True)
    args = p.parse_args()

    op_dir = Path(args.operation.parent) / 'operation'
    mode = os.environ.get('W5_FAKE_MODE', 'normal')
    if args.phase == 'watch5':
        phase_watch5(op_dir, args.run_token, mode)
    elif args.phase == 'start5':
        phase_start5(op_dir, args.run_token, mode)
    elif args.phase == 'contain':
        phase_contain(op_dir)


if __name__ == '__main__':
    main()
