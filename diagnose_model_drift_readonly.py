#!/usr/bin/env python3
"""
READONLY independent diagnosis of the validate_models_full 'Effective model
configuration drift' gate. Captures the EXACT raw configured-property difference
vs the approved baseline, using BOTH the direct predicate (frozen b.validate_models)
and the approved stable ExecStart comparator (v5 _compare_manager_after).
No model restart, no SQL, no capture, no mutation. Writes a new diagnosis JSON only.
Run: <venv-python> -I -B diagnose_model_drift_readonly.py
"""
import hashlib
import json
import os
import sys
import time
from pathlib import Path

SNAPSHOT = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-model-preservation-03/snapshot.json')
SNAPSHOT_SHA = 'a782093b628f37d55def04d517c237af43a31aafed0cb4983d16951a39b2c08f'
OPS_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops')
SCRIPTS_DIR = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts')
OUT = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5/diagnosis-model-drift-readonly.json')

DEADLINE = time.monotonic() + 60


def main():
    sys.path.insert(0, str(OPS_DIR))
    sys.path.insert(0, str(SCRIPTS_DIR))
    import boundary_release as b  # noqa: E402
    from execstart_stable_compare import parse_execstart_stable, compare_execstart_stable  # noqa: E402

    # 1) baseline unchanged?
    snap_sha = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    baseline_unchanged = snap_sha == SNAPSHOT_SHA
    doc = json.loads(SNAPSHOT.read_text())

    models = []
    for item in doc['models']:
        unit = item['unit']
        expected = item['manager_after']
        try:
            actual = b.show(unit, tuple(expected), DEADLINE)
            show_err = None
        except Exception as e:
            actual, show_err = None, f'{type(e).__name__}: {e}'

        # direct predicate (frozen b.validate_models): which keys differ
        direct_diff = {}
        if actual is not None:
            for k in expected:
                if actual.get(k) != expected[k]:
                    direct_diff[k] = {'baseline': expected[k], 'actual': actual.get(k)}

        # stable predicate (v5 _compare_manager_after)
        stable = {}
        if actual is not None and 'ExecStart' in expected:
            try:
                compare_execstart_stable(expected['ExecStart'], actual.get('ExecStart', ''))
                stable['execstart_stable_compare'] = 'MATCH'
            except Exception as e:
                stable['execstart_stable_compare'] = f'FAIL: {type(e).__name__}: {e}'
            try:
                se = parse_execstart_stable(expected['ExecStart'])
                sa = parse_execstart_stable(actual['ExecStart'])
                stable['execstart_stable_fields'] = {
                    'baseline': {'path': se.path, 'argv': se.argv, 'ignore_errors': se.ignore_errors},
                    'actual':   {'path': sa.path, 'argv': sa.argv, 'ignore_errors': sa.ignore_errors},
                    'path_eq': se.path == sa.path, 'argv_eq': se.argv == sa.argv,
                    'ignore_errors_eq': se.ignore_errors == sa.ignore_errors,
                }
            except Exception as e:
                stable['execstart_parse'] = f'{type(e).__name__}: {e}'
            stable['execstart_raw_baseline'] = expected.get('ExecStart', '')[:400]
            stable['execstart_raw_actual'] = (actual.get('ExecStart', '') if actual else '')[:400]

        models.append({
            'unit': unit,
            'show_error': show_err,
            'direct_diff_keys': sorted(direct_diff.keys()),
            'direct_diff': direct_diff,
            'stable': stable,
        })

    report = {
        'schema': 'hyprneuro.w5-model-drift-diagnosis/1',
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'baseline_snapshot_sha': snap_sha,
        'baseline_unchanged': baseline_unchanged,
        'boot_id_match': Path('/proc/sys/kernel/random/boot_id').read_text().strip() == doc.get('boot_id'),
        'models': models,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(OUT), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (json.dumps(report, indent=2, sort_keys=True) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    report['out_path'] = str(OUT)
    report['out_sha256'] = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
