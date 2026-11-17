#!/usr/bin/env python3
"""
W5 context derivation (one-time setup). READ-ONLY verification of the old approved
postwrite context (51f...) + cold DB/settings match, then writes the NEW W5 context.
No DB recapture. No prod mutation. Writes only the new W5 context file (0600).
Run: <venv-python> -I -B derive_w5_context.py
"""
import hashlib
import json
import os
import stat
import sys
import time
from pathlib import Path

OLD_CTX = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-w3-v3-postwrite-evidence/postwrite-context.json')
OLD_CTX_SHA = '51f9109f0c9515045ce9fbc0f16c1b15bb8cf54116dfe8a230d4aa3a526e39bc'
W5_CTX = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w5/w5-postwrite-context.json')

SCHEMA = 'hyprneuro.boundary-postwrite-context/1'


def fd_verify(path: Path, expected_sha=None, label=''):
    """O_NOFOLLOW same-FD: regular, uid, private mode, nlink==1, full SHA. No TOCTOU."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise SystemExit(f'FAIL {label}: not regular file')
        if before.st_uid != os.getuid():
            raise SystemExit(f'FAIL {label}: uid mismatch {before.st_uid}')
        if before.st_nlink != 1:
            raise SystemExit(f'FAIL {label}: nlink {before.st_nlink} != 1')
        chunks, total = [], 0
        while True:
            c = os.read(fd, 65536)
            if not c:
                break
            total += len(c)
            if total > 64 * 1024 * 1024:
                raise SystemExit(f'FAIL {label}: size budget')
            chunks.append(c)
        raw = b''.join(chunks)
        after = os.fstat(fd)
        ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_uid, s.st_mode, s.st_nlink)
        if ident(before) != ident(after):
            raise SystemExit(f'FAIL {label}: changed during read')
        sha = hashlib.sha256(raw).hexdigest()
        if expected_sha and sha != expected_sha:
            raise SystemExit(f'FAIL {label}: SHA {sha} != {expected_sha}')
        return {'sha256': sha, 'inode': before.st_ino, 'dev': before.st_dev,
                'uid': before.st_uid, 'mode': stat.S_IMODE(before.st_mode), 'size': before.st_size}
    finally:
        os.close(fd)


def main():
    # 1) old approved postwrite context: FD verify + SHA
    old_meta = fd_verify(OLD_CTX, OLD_CTX_SHA, 'old_ctx')
    old = json.loads(OLD_CTX.read_text())
    if old.get('schema') != SCHEMA:
        raise SystemExit('FAIL old_ctx schema')

    # 2) cold DB/settings match (no recapture): carry exact old metadata, verify live files match
    db = {}
    for name, value in old['database_no_SQL'].items():
        p = Path(name)
        if value is None:
            if p.exists():
                raise SystemExit(f'FAIL cold DB: {p.name} should be absent')
            db[name] = None
        else:
            m = fd_verify(p, value['sha256'], f'db:{p.name}')
            for k in ('inode', 'dev', 'uid', 'mode', 'size'):
                if m[k] != value[k]:
                    raise SystemExit(f'FAIL cold DB {p.name}: {k} {m[k]} != {value[k]}')
            db[name] = value
    s = old['settings']
    sm = fd_verify(Path(s['path']), s['sha256'], 'settings')
    for k in ('inode', 'dev', 'uid', 'mode', 'size'):
        if sm[k] != s[k]:
            raise SystemExit(f'FAIL cold settings: {k} {sm[k]} != {s[k]}')

    # 3) build W5 context (carry old DB/settings; bind original op/gen + known-failed W3 + source ctx)
    a = old['ancestry']
    w5 = {
        'schema': SCHEMA,
        'ts_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        'ancestry': {
            'original_operation_sha': a['original_operation_sha'],
            'original_generation': a['original_generation'],
            'known_failed_w3_execution': a['failed_execution'],
            'prior_successful_execution': a['prior_successful_execution'],
            'source_context_sha': OLD_CTX_SHA,
        },
        'database_no_SQL': db,
        'settings': s,
        'not_recaptured': old.get('not_recaptured', []),
        'w5_source': 'derived-from-old-approved-postwrite-ctx-51f-no-recapture',
    }
    W5_CTX.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(W5_CTX), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, (json.dumps(w5, indent=2, sort_keys=True) + '\n').encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    out = fd_verify(W5_CTX, None, 'w5_ctx')
    print(json.dumps({
        'status': 'OK', 'ts_utc': w5['ts_utc'],
        'old_ctx_sha': old_meta['sha256'], 'old_ctx_match': old_meta['sha256'] == OLD_CTX_SHA,
        'cold_db_match': True, 'cold_settings_match': True,
        'w5_ctx_path': str(W5_CTX), 'w5_ctx_sha256': out['sha256'],
        'w5_ctx_mode': oct(out['mode']), 'w5_ctx_size': out['size'],
    }, sort_keys=True))


if __name__ == '__main__':
    main()
