#!/usr/bin/env python3
"""
Continuation runner for boundary 18aef68-04 (external, installed-only).
Version: 2 (corrected per review 01M7KMHBS9T1NVK1CYP9T6K5W)

Uses the ORIGINAL 04 operation.json (pinned by SHA). Phases:
provision → watch → start. Bounded 600s from watch launch.

No nested lease. No --wake caller. Single lease held by parent.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Pinned paths
CONTINUATION_OPS = Path('/home/ron/Workspace/hyprneuro-pi-owner-gtk/continuation_ops.py')
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'
PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution')


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def run_phase(phase: str, timeout: float) -> int:
    """Run a single continuation_ops phase. Returns exit code."""
    argv = [
        PYTHON, '-I', str(CONTINUATION_OPS),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
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
    # Verify operation SHA before any action
    actual_sha = sha256_file(OPERATION_PATH)
    if actual_sha != OPERATION_SHA:
        print(json.dumps({'status': 'FAILED', 'reason': 'operation SHA mismatch'}))
        raise SystemExit(1)

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)

    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner/1',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'operation_sha256': OPERATION_SHA,
        'operation_path': str(OPERATION_PATH),
        'phases': []
    }

    # Phase 1: provision (180s timeout)
    rc = run_phase('provision', 180)
    receipt['phases'].append({'phase': 'provision', 'rc': rc})
    if rc != 0:
        receipt['status'] = 'FAILED_PROVISION'
        _write_receipt(receipt)
        raise SystemExit(1)

    # Phase 2: watch (600s bounded from launch)
    watch_start = time.monotonic()
    rc = run_phase('watch', 600)
    watch_elapsed = time.monotonic() - watch_start
    receipt['phases'].append({'phase': 'watch', 'rc': rc, 'elapsed': round(watch_elapsed, 1)})
    if rc != 0:
        receipt['status'] = 'FAILED_WATCH'
        _write_receipt(receipt)
        raise SystemExit(1)

    # Phase 3: start (remaining budget from 600s)
    remaining = max(60.0, 600.0 - watch_elapsed)
    rc = run_phase('start', remaining)
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
