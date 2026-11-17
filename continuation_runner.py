#!/usr/bin/env python3
"""
Continuation runner for boundary 18aef68-04 (external, installed-only).
Version: 4 (FROZEN literal pins, no None, no conditional skip)

All code pins are LITERAL CONSTANTS verified before import and before each phase.
No mutable worktree fallback. No self-hash trust cycle.
Runner itself is externally pinned by MAIN (sha256sum of this file).
"""

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

# --- FROZEN v4 LITERAL PINS (not None, not conditional) ---

PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'

# Frozen v5 code paths with LITERAL SHA constants (immutable artifact directory)
CONTINUATION_OPS_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/continuation_ops.py')
CONTINUATION_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'
STABLE_COMPARE_PATH = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts/execstart_stable_compare.py')
STABLE_COMPARE_SHA = '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e'

AUDIT_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-execution')

# Valid SHA format: exactly 64 lowercase hex chars
_SHA_HEX = set('0123456789abcdef')


def _valid_sha(s) -> bool:
    """Reject None, non-string, wrong length, non-hex."""
    if not isinstance(s, str) or len(s) != 64:
        return False
    return all(c in _SHA_HEX for c in s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_pins() -> None:
    """Verify ALL frozen code pins. Raises ValueError on any mismatch/missing/malformed.
    Called before import AND before each phase. No skip, no fallback."""
    # Validate constants are well-formed (not None, not malformed)
    if not _valid_sha(OPERATION_SHA):
        raise ValueError('OPERATION_SHA malformed')
    if not _valid_sha(CONTINUATION_OPS_SHA):
        raise ValueError('CONTINUATION_OPS_SHA malformed')
    if not _valid_sha(STABLE_COMPARE_SHA):
        raise ValueError('STABLE_COMPARE_SHA malformed')

    # Verify operation pin
    if not OPERATION_PATH.exists():
        raise ValueError(f'Operation path missing: {OPERATION_PATH}')
    actual = sha256_file(OPERATION_PATH)
    if actual != OPERATION_SHA:
        raise ValueError(f'Operation SHA mismatch: got {actual[:16]}... want {OPERATION_SHA[:16]}...')

    # Verify continuation ops pin
    if not CONTINUATION_OPS_PATH.exists():
        raise ValueError(f'continuation_ops path missing: {CONTINUATION_OPS_PATH}')
    actual = sha256_file(CONTINUATION_OPS_PATH)
    if actual != CONTINUATION_OPS_SHA:
        raise ValueError(f'continuation_ops SHA mismatch: got {actual[:16]}... want {CONTINUATION_OPS_SHA[:16]}...')

    # Verify stable compare pin
    if not STABLE_COMPARE_PATH.exists():
        raise ValueError(f'stable_compare path missing: {STABLE_COMPARE_PATH}')
    actual = sha256_file(STABLE_COMPARE_PATH)
    if actual != STABLE_COMPARE_SHA:
        raise ValueError(f'stable_compare SHA mismatch: got {actual[:16]}... want {STABLE_COMPARE_SHA[:16]}...')


def run_phase(phase: str, timeout: float) -> int:
    """Run a single continuation_ops phase. Verifies pins before each execute."""
    verify_pins()
    argv = [
        PYTHON, '-I', str(CONTINUATION_OPS_PATH),
        '--operation', str(OPERATION_PATH),
        '--operation-sha256', OPERATION_SHA,
        '--phase', phase,
    ]
    try:
        proc = subprocess.Popen(
            argv,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=str(CONTINUATION_OPS_PATH.parent),
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
    # Verify ALL pins before any action
    verify_pins()

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIT_DIR.chmod(0o700)

    receipt = {
        'schema': 'hyprneuro.boundary-continuation-runner/4',
        'ts_start': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
        'operation_sha256': OPERATION_SHA,
        'operation_path': str(OPERATION_PATH),
        'continuation_ops_path': str(CONTINUATION_OPS_PATH),
        'continuation_ops_sha256': CONTINUATION_OPS_SHA,
        'stable_compare_path': str(STABLE_COMPARE_PATH),
        'stable_compare_sha256': STABLE_COMPARE_SHA,
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
