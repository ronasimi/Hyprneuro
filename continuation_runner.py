#!/usr/bin/env python3
"""
Continuation runner for boundary 18aef68-04 (external, installed-only).

Adapted from the reviewed parent_runner.py pattern. Uses external arrays
(continuation_arrays.json) NOT the frozen 04 MAIN arrays. Phases:
provision → watch → start. Bounded 600s from watch launch.

No nested lease. No --wake caller. Single lease held by parent.
"""

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

# Pinned paths
CONTINUATION_OPS = Path('/home/ron/Workspace/hyprneuro-pi-owner-gtk/continuation_ops.py')
CONTINUATION_SCRIPTS = Path('/home/ron/Workspace/hyprneuro-pi-owner-gtk/scripts')
PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def run_phase(phase: str, arrays_path: Path, arrays_sha: str, op_sha: str, timeout: float) -> int:
    """Run a single continuation_ops phase. Returns exit code."""
    argv = [
        PYTHON, '-I', str(CONTINUATION_OPS),
        '--phase', phase,
        '--arrays', str(arrays_path),
        '--arrays-sha256', arrays_sha,
        '--operation-sha256', op_sha,
    ]
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(CONTINUATION_OPS.parent),
        )
        out, _ = proc.communicate(timeout=timeout)
        AUDIT_DIR.joinpath(f'continuation-{phase}.log').write_bytes(out)
        return proc.returncode
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        AUDIT_DIR.joinpath(f'continuation-{phase}.log').write_text('TIMEOUT\n')
        return -1


def main() -> None:
    parser = argparse.ArgumentParser(description='Continuation runner for 18aef68-04')
    parser.add_argument('--arrays', required=True)
    parser.add_argument('--arrays-sha256', required=True)
    parser.add_argument('--operation-sha256', required=True)
    args = parser.parse_args()

    arrays_path = Path(args.arrays)

    # Verify arrays SHA before any action
    actual_sha = sha256_file(arrays_path)
    if actual_sha != args.arrays_sha256:
        print(json.dumps({'status': 'FAILED', 'reason': 'arrays SHA mismatch'}))
        raise SystemExit(1)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)

    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'arrays_sha256': args.arrays_sha256,
        'operation_sha256': args.operation_sha256,
        'phases': []
    }

    # Phase 1: provision (180s timeout)
    rc = run_phase('provision', arrays_path, args.arrays_sha256, args.operation_sha256, 180)
    receipt['phases'].append({'phase': 'provision', 'rc': rc})
    if rc != 0:
        receipt['status'] = 'FAILED_PROVISION'
        _write_receipt(receipt)
        raise SystemExit(1)

    # Phase 2: watch (600s bounded from launch)
    watch_start = time.monotonic()
    rc = run_phase('watch', arrays_path, args.arrays_sha256, args.operation_sha256, 600)
    watch_elapsed = time.monotonic() - watch_start
    receipt['phases'].append({'phase': 'watch', 'rc': rc, 'elapsed': round(watch_elapsed, 1)})
    if rc != 0:
        receipt['status'] = 'FAILED_WATCH'
        _write_receipt(receipt)
        raise SystemExit(1)

    # Phase 3: start (remaining budget from 600s)
    remaining = max(60.0, 600.0 - watch_elapsed)
    rc = run_phase('start', arrays_path, args.arrays_sha256, args.operation_sha256, remaining)
    receipt['phases'].append({'phase': 'start', 'rc': rc, 'budget': round(remaining, 1)})
    if rc != 0:
        receipt['status'] = 'FAILED_START'
        _write_receipt(receipt)
        raise SystemExit(1)

    receipt['status'] = 'PASS'
    receipt['ts_end'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')
    _write_receipt(receipt)
    print(json.dumps({'status': 'PASS', 'phases': len(receipt['phases'])}))


def _write_receipt(receipt: dict) -> None:
    receipt['ts_end'] = receipt.get('ts_end', time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    path = AUDIT_DIR / 'continuation-receipt.json'
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    path.chmod(0o644)


if __name__ == '__main__':
    main()
