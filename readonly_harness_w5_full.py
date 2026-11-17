#!/usr/bin/env python3
"""
READONLY quiescent passive harness — W5 FULL-model fresh preflight (CORRECTED).
SOURCE ONLY. NOT EXECUTED. Awaiting parent safety review + explicit execution authorization.

WHY THIS EXISTS
  The W5 watch loop (phase_watch5 -> check_context_runtime_w5) uses preserve_continuation
  (full=False) — the non-full watch path. It does NOT run the FULL model preflight.
  Therefore a separate, independent FULL-model fresh preflight is still required before any
  W5 launch. The original W4v3 harness gate 'validate_models_full' used b.validate_models,
  which does DIRECT equality on manager_after (volatile ExecStart start_time/pid/code/status)
  and false-FAILs on a live, drift-free system. This harness replaces ONLY that gate with the
  v5-approved stable-ExecStart full preservation ACTUAL call: preserve_continuation(full=True).

CORRECTION (minimal, no baseline weaken)
  - Gate 'validate_models_full_stable' calls preserve_continuation(op, DEADLINE, full=True),
    which runs validate_models_continuation: stable-field ExecStart comparison (path/argv[]/
    ignore_errors) + ALL other checks STRICT and unchanged (configs baseline pin, boot_id,
    process-executable FD, argv/cmdline SHA, kernel identity, listeners, MoE state/policy,
    projector aux, weight-file metadata). The model baseline is NOT weakened or rebaselined.
  - Every other gate from the reviewed W4v3 harness is preserved verbatim.

INVOCATION (parent-run, under machine lease) — ONLY after safety review:
  pi-durable-subagents hold machine -- \
    /home/ron/Projects/Hyprneuro/python/.venv/bin/python -I -B <this-file>

GUARANTEES (by construction):
  - python -I -B : isolated, no pyc creation.
  - Imports the 3 frozen prod modules + v5 (clean: stdlib-only at import, no side effects).
  - Calls ONLY readonly helpers: load, check_material, full_identity, b.stopped,
    preserve_continuation(full=True / full=False), select_display_session, verify_session,
    (best-effort) effective.
  - NEVER calls: contain(), b.command([... start ...]), write_new(), screen_lock_state().
  - Writes NEW audit evidence ONLY to a new dir (0700/0600). Never touches OP_DIR / prod markers.
  - Records argv, exit, stdout, stderr, realtime UTC, uid/pid, interpreter. No invented callID.

KNOWN SCOPE LIMITS (reported honestly, not faked):
  - full / non-full preservation require the model processes (lfm@text/omni/decision,
    lfm@littlemoe/bigmoe/moe) ALIVE with baseline pids; if not, the gate records the specific
    drift/absence error (a valid readonly observation).
  - effective() needs hyprneuro.* (venv site-packages) which -I excludes -> expected
    UNAVAILABLE under -I; recorded as such, NOT a hard fail.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# --- FROZEN literal pins (verify BEFORE any prod import) ---
PYTHON = '/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
OPERATION_PATH = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation.json')
OPERATION_SHA = '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4'

OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
BOUNDARY_RELEASE_PATH = OPS_DIR / 'boundary_release.py'
BOUNDARY_RELEASE_SHA = '9fcb37cf398dfe2f158ef39fa3ab518f233f231e23242a6e22b680ed9b91e74c'
BOUNDARY_RELEASE_OPS_PATH = OPS_DIR / 'boundary_release_ops.py'
BOUNDARY_RELEASE_OPS_SHA = '5e6c50f202090f93699f11f28c0d61409ee2b6bcafec5bc8ad015ceb601659ac'

V5_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5')
V5_OPS_PATH = V5_DIR / 'continuation_ops.py'
V5_OPS_SHA = '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c'
COMPARATOR_PATH = V5_DIR / 'scripts' / 'execstart_stable_compare.py'
COMPARATOR_SHA = '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e'

EVIDENCE_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5/harness-evidence-w5')
EVIDENCE_PATH = EVIDENCE_DIR / 'readonly-harness-w5-full.json'

DEADLINE = time.monotonic() + 180  # bounded; readonly checks are fast

APP_UNITS = ('hyprneuro.service', 'hyprneuro-ui.service')

_SHA_HEX = set('0123456789abcdef')


def _valid_sha(s):
    return isinstance(s, str) and len(s) == 64 and all(c in _SHA_HEX for c in s)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def verify_pins() -> None:
    for p, s in ((BOUNDARY_RELEASE_PATH, BOUNDARY_RELEASE_SHA),
                 (BOUNDARY_RELEASE_OPS_PATH, BOUNDARY_RELEASE_OPS_SHA),
                 (OPERATION_PATH, OPERATION_SHA),
                 (V5_OPS_PATH, V5_OPS_SHA),
                 (COMPARATOR_PATH, COMPARATOR_SHA)):
        if not _valid_sha(s):
            raise ValueError('malformed pin sha')
        if not p.exists():
            raise ValueError(f'pin missing: {p}')
        if sha256_file(p) != s:
            raise ValueError(f'pin SHA mismatch: {p}')


def _utc() -> str:
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _gate(name, fn):
    """Run one readonly gate; return a closed result dict. Never raises to top."""
    t0 = time.monotonic()
    try:
        value = fn()
        return {'gate': name, 'status': 'PASS', 'ms': round((time.monotonic() - t0) * 1000, 1),
                'detail': value if isinstance(value, (str, int, float, bool, type(None))) else 'ok'}
    except Exception as e:  # closed label: type only, no raw private values
        return {'gate': name, 'status': 'FAIL', 'ms': round((time.monotonic() - t0) * 1000, 1),
                'exception_class': type(e).__name__, 'message': str(e)[:500]}


def main() -> None:
    verify_pins()

    # Import frozen prod modules (clean at import).
    sys.path.insert(0, str(OPS_DIR))
    sys.path.insert(0, str(V5_DIR))
    import boundary_release as b  # noqa: E402
    from boundary_release_ops import (  # noqa: E402
        load, check_material, effective, full_identity,
        select_display_session, verify_session,
    )
    from continuation_ops import preserve_continuation  # noqa: E402

    op = load(OPERATION_PATH, OPERATION_SHA)
    results = []

    # 1) 6 material objects exact-BYTES vs source catalog
    results.append(_gate('check_material_6_exact_bytes', lambda: check_material(op, True) is None and 'ok'))

    # 2) per-APP-unit full identity + verifiably-stopped
    for unit in APP_UNITS:
        def _u(unit=unit):
            ident = full_identity(unit, DEADLINE)
            b.stopped(unit, DEADLINE)  # raises if not verifiably stopped
            return f'{unit}: full_identity={ident!r} stopped=OK'
        results.append(_gate(f'unit_full_identity_stopped[{unit}]', _u))

    # 3) CORRECTED FULL-model fresh preflight: v5 stable-ExecStart preserve(full=True).
    #    Replaces the buggy direct-equality b.validate_models. All mandatory raw-cmdline
    #    checks (configs baseline pin, boot_id, exe FD, argv/cmdline SHA, kernel identity,
    #    listeners, MoE state/policy, projector aux, weight metadata) STRICT; baseline unchanged.
    results.append(_gate('validate_models_full_stable',
                         lambda: preserve_continuation(op, DEADLINE, full=True) is None and 'ok'))

    # 4) non-full preserve (models + runtime pins; NOT DB/settings; stable ExecStart)
    results.append(_gate('preserve_continuation_nonfull',
                         lambda: preserve_continuation(op, DEADLINE, full=False) is None and 'ok'))

    # 5) logind proof (pure-readonly pieces; NO screen_lock_state, NO write_new)
    def _logind():
        pg = subprocess.run(['/usr/bin/pgrep', '-x', 'hyprlock'],
                            capture_output=True, text=True, timeout=10)
        lock = 'absent' if pg.returncode == 1 else f'rc={pg.returncode}(AMBIGUOUS/RUNNING)'
        sid = select_display_session(DEADLINE)
        fields = verify_session(sid, DEADLINE)  # raises if session not wayland/active/unlocked/local
        return f'display_session={sid} hyprlock={lock} session={json.dumps(fields, sort_keys=True)}'
    results.append(_gate('logind_session_proof', _logind))

    # 6) best-effort effective() (needs hyprneuro.* -> expected UNAVAILABLE under -I)
    def _effective():
        return effective(op, DEADLINE) is not None and 'ok'
    r6 = _gate('effective_best_effort', _effective)
    if r6['status'] == 'FAIL' and r6.get('exception_class') == 'ImportError':
        r6['status'] = 'UNAVAILABLE'
        r6['note'] = 'hyprneuro.* not importable under -I isolated mode (expected)'
    results.append(r6)

    evidence = {
        'schema': 'hyprneuro.w5-readonly-harness/1',
        'ts_utc': _utc(),
        'argv': sys.argv,
        'interpreter': sys.executable,
        'uid': os.getuid(),
        'pid': os.getpid(),
        'operation_sha256': OPERATION_SHA,
        'correction': 'validate_models_full -> preserve_continuation(full=True) stable ExecStart',
        'mutation_calls_performed': [],  # invariant: always empty
        'gates': results,
    }
    passed = sum(1 for r in results if r['status'] == 'PASS')
    failed = sum(1 for r in results if r['status'] == 'FAIL')
    evidence['summary'] = {'pass': passed, 'fail': failed,
                           'unavailable': sum(1 for r in results if r['status'] == 'UNAVAILABLE')}

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.chmod(0o700)
    EVIDENCE_PATH.write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
    EVIDENCE_PATH.chmod(0o600)

    print(json.dumps({'evidence': str(EVIDENCE_PATH), **evidence['summary'],
                      'evidence_sha256': sha256_file(EVIDENCE_PATH)}, sort_keys=True))
    raise SystemExit(1 if failed else 0)


if __name__ == '__main__':
    main()
