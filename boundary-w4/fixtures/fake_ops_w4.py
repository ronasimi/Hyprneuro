#!/usr/bin/env python3
"""
Fake OPS boundary for W4-v3 private flow tests.
Simulates ops phases (watch4, start4, contain) WITHOUT touching real services.
This is the ONLY fake component. The REAL runner code orchestrates it.

Phases:
- watch4: Write watch4.ready marker, then sleep (simulates watch loop)
- start4: Validate watch4.ready, write start4.started + start4.completed
- contain: Write fake unit states STOPPED to stdout (JSON)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

# Marker names (must match W4 ops)
WATCH4_READY = 'continuation.watch4.ready'
START4_STARTED = 'continuation.start4.started'
START4_COMPLETED = 'continuation.start4.completed'

OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
GENERATION = '484e9abe3b334b8c8628df2966394ce8'


def phase_watch4(op_dir: Path, run_token: str, sleep_secs: float) -> None:
    """Write watch4.ready, then sleep (simulates watch loop staying alive)."""
    proc = Path('/proc/self')
    ready_data = {
        'schema': 'hyprneuro.boundary-watch4-ready/1',
        'operation_sha256': OPERATION_SHA,
        'run_token': run_token,
        'pid': os.getpid(),
        'start': proc.joinpath('stat').read_text().rsplit(') ', 1)[1].split()[19],
    }
    # Atomic write (O_EXCL)
    ready_path = op_dir / WATCH4_READY
    fd = os.open(str(ready_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o400)
    content = (json.dumps(ready_data, sort_keys=True) + '\n').encode()
    os.write(fd, content)
    os.fsync(fd)
    os.close(fd)

    # Stay alive (simulates watch loop monitoring)
    time.sleep(sleep_secs)


def phase_start4(op_dir: Path, run_token: str, deadline_secs: float) -> None:
    """Validate watch4.ready, write start4.started + start4.completed."""
    # Validate watch4.ready
    ready_path = op_dir / WATCH4_READY
    if not ready_path.exists():
        print(json.dumps({'status': 'FAILED', 'error': 'watch4.ready missing'}))
        raise SystemExit(1)

    ready = json.loads(ready_path.read_text())
    if ready.get('run_token') != run_token:
        print(json.dumps({'status': 'FAILED', 'error': 'token mismatch'}))
        raise SystemExit(1)

    # Write start4.started
    started_path = op_dir / START4_STARTED
    fd = os.open(str(started_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o400)
    os.write(fd, (OPERATION_SHA + '\n').encode())
    os.fsync(fd)
    os.close(fd)

    # Simulate brief work
    time.sleep(0.5)

    # Write start4.completed (receipt)
    completed_data = {
        'schema': 'hyprneuro.boundary-start-receipt/1',
        'operation_sha256': OPERATION_SHA,
        'generation': GENERATION,
        'run_token': run_token,
        'broker': {'unit': 'hyprneuro.service', 'pid': '12345', 'start': 'abc'},
        'ui': {'unit': 'hyprneuro-ui.service', 'pid': '12346', 'start': 'def'},
    }
    completed_path = op_dir / START4_COMPLETED
    fd = os.open(str(completed_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o400)
    os.write(fd, (json.dumps(completed_data, sort_keys=True) + '\n').encode())
    os.fsync(fd)
    os.close(fd)

    print(json.dumps({'status': 'PASS', 'phase': 'start4', 'run_token': run_token}))


def phase_contain(op_dir: Path) -> None:
    """Write fake unit states STOPPED to stdout."""
    result = {
        'status': 'CONTAINED',
        'containment': {
            'hyprneuro.service': 'STOPPED',
            'hyprneuro-ui.service': 'STOPPED',
            'hyprneuro-pi-identity.service': 'REAPED_NOT_BACKEND_RECEIPT',
            'hyprneuro-pi-identity.socket': 'STOPPED',
            'backend_cleanup': 'NOT_ATTESTED',
        }
    }
    print(json.dumps(result, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description='Fake OPS boundary for W4-v3 tests')
    parser.add_argument('--operation', type=Path, required=True)
    parser.add_argument('--operation-sha256', required=True)
    parser.add_argument('--phase', choices=('watch4', 'start4', 'contain'), required=True)
    parser.add_argument('--run-token', required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--watch-sleep', type=float, default=30.0,
                        help='Seconds for watch4 to stay alive')
    args = parser.parse_args()

    # OP dir is operation.json.parent / 'operation'
    op_dir = args.operation.parent / 'operation'

    if args.phase == 'watch4':
        phase_watch4(op_dir, args.run_token, args.watch_sleep)
    elif args.phase == 'start4':
        phase_start4(op_dir, args.run_token, 5.0)
    elif args.phase == 'contain':
        phase_contain(op_dir)


if __name__ == '__main__':
    main()
