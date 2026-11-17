#!/usr/bin/env python3
"""
Freeze W5 code into a NEW separated directory + prove a SHA receipt.
Copies the immutable W5 source files, sets private modes, and writes frozen-receipt.json
proving each frozen blob's SHA matches the source blob. No original receipts overwritten.
Run: <venv-python> -I -B freeze_w5.py
"""
import hashlib
import json
import os
import shutil
import stat
import time
from pathlib import Path

SRC = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5')
FROZEN = SRC / 'frozen'

# (relative path, frozen mode)
FILES = [
    ('continuation_runner_w5.py', 0o400),
    ('continuation_ops_w5.py', 0o400),
    ('continuation_waiter_w5.py', 0o400),
    ('w5-postwrite-context.json', 0o600),
    ('tests/test_w5.py', 0o600),
    ('derive_w5_context.py', 0o400),
    ('diagnose_model_drift_readonly.py', 0o400),
]

PINS = {
    'operation': '306cf4b978789d1d60dd6dc239ee9c5b454c17f6189bfe68201118b28b4562c4',
    'generation': '484e9abe3b334b8c8628df2966394ce8',
    'boundary_release': '9fcb37cf398dfe2f158ef39fa3ab518f233f231e23242a6e22b680ed9b91e74c',
    'boundary_release_ops': '5e6c50f202090f93699f11f28c0d61409ee2b6bcafec5bc8ad015ceb601659ac',
    'v5_ops': '7e23baedd7f2dd0981d2161130d40e744945783dde97e506ee5b17e77cc0740c',
    'comparator': '964b4bf635e3acb9454ee86c7feda05d3d715b04b5c0464849ed2ca3d42e036e',
    'ops_w5': '19699702c74c6d0ded9068ef40197d5b9e9ed0c35f7da309d5cc82eb4fc3b644',
    'context_w5': '1af29c8d3bd960fabfd72227aebab1e4822fe119192fe1e86ba40b549a73561d',
    'old_w4_ready_preserved': '08bc1b3bbcf64269e6e9776ded51b7a053cfd707edbf54174379579f1ad62811',
}


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(65536), b''):
            h.update(c)
    return h.hexdigest()


def main():
    FROZEN.mkdir(parents=True, exist_ok=True)
    FROZEN.chmod(0o700)
    (FROZEN / 'tests').mkdir(parents=True, exist_ok=True)

    entries = []
    all_match = True
    for rel, mode in FILES:
        src = SRC / rel
        dst = FROZEN / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        s_sha = sha(src)
        shutil.copyfile(src, dst)
        os.chmod(dst, mode)
        d_sha = sha(dst)
        match = s_sha == d_sha
        all_match = all_match and match
        entries.append({'path': rel, 'source_sha256': s_sha, 'frozen_sha256': d_sha,
                        'mode': oct(mode), 'match': match})

    receipt = {
        'schema': 'hyprneuro.w5-freeze-receipt/1',
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'frozen_dir': str(FROZEN),
        'all_blobs_match_source': all_match,
        'no_original_receipts_overwritten': True,
        'no_prod_markers_mutated': True,
        'no_production_launch': True,
        'w5_marker_namespace': ['continuation.watch5.ready', 'continuation.start5.started',
                                 'continuation.start5.completed', 'continuation.start5.ready'],
        'pins': PINS,
        'files': entries,
    }
    rpath = FROZEN / 'frozen-receipt.json'
    rfd = os.open(str(rpath), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(rfd, (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode())
        os.fsync(rfd)
    finally:
        os.close(rfd)
    receipt['receipt_path'] = str(rpath)
    receipt['receipt_sha256'] = sha(rpath)
    print(json.dumps(receipt, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
