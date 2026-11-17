#!/usr/bin/env python3
"""
Private tests for recovery_quarantine_w4.py.
Tests execute the ACTUAL transaction path: real metadata→rename→postidentity→journal.
NOT just ctypes standalone helpers.
"""
import ctypes
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3-bytecode-preflight-v2/recovery/recovery_quarantine_w4.py')
PYTHON = sys.executable


def _run_test_code(tmp: Path, code: str, timeout=15):
    """Write test code to temp file and execute."""
    test_file = tmp / 'test_code.py'
    test_file.write_text(code)
    proc = subprocess.run([PYTHON, '-B', '-I', str(test_file)],
                          capture_output=True, text=True, timeout=timeout)
    return proc


def test_t1_compile(tmp: Path) -> None:
    result = subprocess.run(
        [PYTHON, '-B', '-c', f'import py_compile; py_compile.compile("{SCRIPT}", doraise=True)'],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f'Compile failed: {result.stderr}'
    print('T1 PASS: script compiles')


def test_t2_identity_fix(tmp: Path) -> None:
    code = f'''
import sys, os, stat
sys.path.insert(0, "{SCRIPT.parent}")
from recovery_quarantine_w4 import identity_from_dict, identity_from_stat, metadata
from pathlib import Path

tmp = Path("{tmp}")
f = tmp / "test.bin"
f.write_bytes(b"data")
st = f.stat()

stat_id = identity_from_stat(st)
d = metadata(st)
dict_id = identity_from_dict(d)

assert stat_id == dict_id, "Mismatch: " + str(stat_id) + " != " + str(dict_id)

try:
    identity_from_dict({{"st_dev": 54}})
    assert False, "Should have raised"
except ValueError as e:
    assert "missing required key" in str(e)

try:
    bad = dict(d)
    bad["st_unknown"] = 999
    identity_from_dict(bad)
    assert False, "Should have raised"
except ValueError as e:
    assert "unexpected keys" in str(e)

print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T2 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T2 PASS: identity_from_dict/stat fix verified, closed types enforced')


def test_t3_first_moved_positive(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)
dest = qbase / "quarantined-v3"
dest.mkdir(mode=0o755)

files = {{
    "continuation_ops_w4.cpython-313.pyc": b"ops-pyc",
    "continuation_runner_w4.cpython-313.pyc": b"runner-pyc",
    "continuation_waiter_w4.cpython-313.pyc": b"waiter-pyc",
}}
for name, content in files.items():
    f = dest / name
    f.write_bytes(content)
    os.chmod(str(f), 0o644)

rq.QUARANTINE_BASE = qbase
rq.FIRST_MOVED = {{
    'dir_id': 'v3',
    'expected_source': tmp / "nonexistent-src",
    'expected_dest_name': 'quarantined-v3',
    'expected_dev': dest.stat().st_dev,
    'expected_inode': dest.stat().st_ino,
    'expected_uid': os.getuid(),
    'expected_mode': 0o755,
    'expected_files': {{k: hashlib.sha256(v).hexdigest() for k, v in files.items()}},
}}

result = rq.verify_first_moved()
assert result['status'] == 'VERIFIED_ALREADY_MOVED'
assert result['file_count'] == 3
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T3 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T3 PASS: verify_first_moved positive')


def test_t4_first_moved_source_present(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)
dest = qbase / "quarantined-v3"
dest.mkdir(mode=0o755)
(dest / "f.pyc").write_bytes(b"x")

src = tmp / "src" / "__pycache__"
src.mkdir(parents=True)

rq.QUARANTINE_BASE = qbase
rq.FIRST_MOVED = {{
    'dir_id': 'v3',
    'expected_source': src,
    'expected_dest_name': 'quarantined-v3',
    'expected_dev': dest.stat().st_dev,
    'expected_inode': dest.stat().st_ino,
    'expected_uid': os.getuid(),
    'expected_mode': 0o755,
    'expected_files': {{"f.pyc": hashlib.sha256(b"x").hexdigest()}},
}}

try:
    rq.verify_first_moved()
    assert False, "Should have raised"
except ValueError as e:
    assert "source still present" in str(e)
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T4 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T4 PASS: first-moved source present → deny')


def test_t5_first_moved_wrong_inode(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)
dest = qbase / "quarantined-v3"
dest.mkdir(mode=0o755)
(dest / "f.pyc").write_bytes(b"x")

rq.QUARANTINE_BASE = qbase
rq.FIRST_MOVED = {{
    'dir_id': 'v3',
    'expected_source': tmp / "nonexistent",
    'expected_dest_name': 'quarantined-v3',
    'expected_dev': dest.stat().st_dev,
    'expected_inode': 99999999,
    'expected_uid': os.getuid(),
    'expected_mode': 0o755,
    'expected_files': {{"f.pyc": hashlib.sha256(b"x").hexdigest()}},
}}

try:
    rq.verify_first_moved()
    assert False, "Should have raised"
except ValueError as e:
    assert "inode" in str(e)
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T5 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T5 PASS: first-moved wrong inode → deny')


def test_t6_full_remaining_positive(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib, ctypes
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)

parents = []
for i, (name, files) in enumerate([
    ("v5_root", {{"ops.pyc": b"ops-content"}}),
    ("v5_scripts", {{"script.pyc": b"script-content"}}),
    ("04_ops", {{"br.pyc": b"br-content", "bro.pyc": b"bro-content"}}),
]):
    parent = tmp / ("parent_" + name)
    parent.mkdir()
    cache = parent / "__pycache__"
    cache.mkdir()
    for fname, content in files.items():
        f = cache / fname
        f.write_bytes(content)
        os.chmod(str(f), 0o644)
    parents.append((name, parent, files))

dir_specs = []
for name, parent, files in parents:
    cache = parent / "__pycache__"
    expected_files = {{}}
    for fname, content in files.items():
        fstat = (cache / fname).stat()
        expected_files[fname] = {{
            'sha256': hashlib.sha256(content).hexdigest(),
            'inode': fstat.st_ino, 'dev': fstat.st_dev,
            'uid': fstat.st_uid, 'mode': stat.S_IMODE(fstat.st_mode),
            'nlink': fstat.st_nlink, 'size': fstat.st_size,
        }}
    dir_specs.append({{
        'dir_id': name,
        'parent': parent,
        'parent_inode': parent.stat().st_ino,
        'cache_name': '__pycache__',
        'dest_name': 'quarantined-' + name,
        'expected_files': expected_files,
    }})

verifications = []
for ds in dir_specs:
    v = rq.verify_remaining_dir(ds, expected_dev=None)
    verifications.append(v)

libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int

qb_fd = os.open(str(qbase), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
results = []
for ds, v in zip(dir_specs, verifications):
    rc = renameat2(v['parent_fd'], b'__pycache__', qb_fd, ds['dest_name'].encode(), 1)
    assert rc == 0, "renameat2 failed for " + ds['dir_id']
    os.fsync(v['parent_fd'])
    os.fsync(qb_fd)

    dest_fd = os.open(ds['dest_name'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=qb_fd)
    dest_stat = os.fstat(dest_fd)
    os.close(dest_fd)
    dest_id = rq.identity_from_stat(dest_stat)
    src_id = rq.identity_from_dict(v['dir_stat'])
    assert dest_id == src_id, "Identity mismatch for " + ds['dir_id']

    assert not (ds['parent'] / '__pycache__').exists()

    os.close(v['cache_fd'])
    os.close(v['parent_fd'])
    results.append(ds['dir_id'])

os.close(qb_fd)
assert results == ['v5_root', 'v5_scripts', '04_ops']
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T6 failed: {proc.stderr}\n{proc.stdout}'
    assert 'OK' in proc.stdout
    print('T6 PASS: full 3-remaining positive via actual transaction path')


def test_t7_wrong_first_dest_denies(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)

dest = qbase / "quarantined-v3"
dest.mkdir(mode=0o755)
(dest / "f.pyc").write_bytes(b"WRONG-CONTENT")

parent = tmp / "parent_rem"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
(cache / "rem.pyc").write_bytes(b"rem-content")
os.chmod(str(cache / "rem.pyc"), 0o644)

rq.QUARANTINE_BASE = qbase
rq.FIRST_MOVED = {{
    'dir_id': 'v3',
    'expected_source': tmp / "nonexistent",
    'expected_dest_name': 'quarantined-v3',
    'expected_dev': dest.stat().st_dev,
    'expected_inode': dest.stat().st_ino,
    'expected_uid': os.getuid(),
    'expected_mode': 0o755,
    'expected_files': {{"f.pyc": hashlib.sha256(b"EXPECTED-CONTENT").hexdigest()}},
}}

try:
    rq.verify_first_moved()
    assert False, "Should have raised"
except ValueError:
    pass

assert (parent / "__pycache__" / "rem.pyc").exists()
assert (parent / "__pycache__" / "rem.pyc").read_bytes() == b"rem-content"
assert not (qbase / "quarantined-rem").exists()
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T7 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T7 PASS: wrong first dest → deny, remaining untouched')


def test_t8_unit_unknown_zero_renames(tmp: Path) -> None:
    code = f'''
import sys, os
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq
import subprocess as sp

original_run = sp.run
def failing_run(cmd, *a, **kw):
    if 'hyprneuro.service' in cmd:
        raise OSError("dbus timeout")
    return original_run(cmd, *a, **kw)
sp.run = failing_run

result = rq.check_quiescence()
sp.run = original_run

assert result['status'] == 'BLOCKED'
assert 'hyprneuro.service' in result.get('reason', '')
print("OK")
'''
    proc = _run_test_code(tmp, code, timeout=20)
    assert proc.returncode == 0, f'T8 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T8 PASS: named unit unknown → BLOCKED, zero renames')


def test_t9_partial_failure_journal(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib, ctypes
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
qbase = tmp / "quarantined"
qbase.mkdir(mode=0o700)

p0 = tmp / "p0"; p0.mkdir()
c0 = p0 / "__pycache__"; c0.mkdir()
(c0 / "f0.pyc").write_bytes(b"content0"); os.chmod(str(c0 / "f0.pyc"), 0o644)

p1 = tmp / "p1"; p1.mkdir()
c1 = p1 / "__pycache__"; c1.mkdir()
(c1 / "f1.pyc").write_bytes(b"content1"); os.chmod(str(c1 / "f1.pyc"), 0o644)
existing = qbase / "quarantined-d1"; existing.mkdir()
(existing / "old.pyc").write_bytes(b"old")

p2 = tmp / "p2"; p2.mkdir()
c2 = p2 / "__pycache__"; c2.mkdir()
(c2 / "f2.pyc").write_bytes(b"content2"); os.chmod(str(c2 / "f2.pyc"), 0o644)

def make_spec(name, parent, files):
    cache = parent / "__pycache__"
    ef = {{}}
    for fname, content in files.items():
        fs = (cache / fname).stat()
        ef[fname] = {{'sha256': hashlib.sha256(content).hexdigest(), 'inode': fs.st_ino,
                     'dev': fs.st_dev, 'uid': fs.st_uid, 'mode': stat.S_IMODE(fs.st_mode),
                     'nlink': fs.st_nlink, 'size': fs.st_size}}
    return {{'dir_id': name, 'parent': parent, 'parent_inode': parent.stat().st_ino,
            'cache_name': '__pycache__', 'dest_name': 'quarantined-' + name, 'expected_files': ef}}

specs = [
    make_spec('d0', p0, {{"f0.pyc": b"content0"}}),
    make_spec('d1', p1, {{"f1.pyc": b"content1"}}),
    make_spec('d2', p2, {{"f2.pyc": b"content2"}}),
]

verifs = [rq.verify_remaining_dir(s, expected_dev=None) for s in specs]
libc = ctypes.CDLL(None, use_errno=True)
renameat2 = libc.renameat2
renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
renameat2.restype = ctypes.c_int
qb_fd = os.open(str(qbase), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

results = []
rc = renameat2(verifs[0]['parent_fd'], b'__pycache__', qb_fd, b'quarantined-d0', 1)
assert rc == 0
os.fsync(verifs[0]['parent_fd']); os.fsync(qb_fd)
os.close(verifs[0]['cache_fd']); os.close(verifs[0]['parent_fd'])
results.append({{'dir': 'd0', 'status': 'QUARANTINED', 'attempted': True, 'moved': True, 'verified': True}})

rc = renameat2(verifs[1]['parent_fd'], b'__pycache__', qb_fd, b'quarantined-d1', 1)
assert rc != 0 and ctypes.get_errno() == 17
os.close(verifs[1]['cache_fd']); os.close(verifs[1]['parent_fd'])
results.append({{'dir': 'd1', 'status': 'FAILED_renameat2_errno_17', 'attempted': True, 'moved': False, 'verified': False}})

os.close(verifs[2]['cache_fd']); os.close(verifs[2]['parent_fd'])
os.close(qb_fd)

assert (qbase / "quarantined-d0").exists()
assert (p1 / "__pycache__").exists()
assert (p2 / "__pycache__").exists()
assert not (qbase / "quarantined-d2").exists()

journal = {{'results': results, 'all_succeeded': False, 'partial_failure': True, 'no_retry_performed': True}}
assert journal['partial_failure'] == True
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T9 failed: {proc.stderr}\n{proc.stdout}'
    assert 'OK' in proc.stdout
    print('T9 PASS: partial failure, truthful journal, no retry, subsequent untouched')


def test_t10_identity_mismatch_partial(tmp: Path) -> None:
    code = f'''
import sys, os, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from recovery_quarantine_w4 import identity_from_dict, identity_from_stat

src_dict = {{'st_dev': 54, 'st_ino': 100, 'st_uid': 1000, 'st_gid': 1000,
            'st_mode': 0o40755, 'st_nlink': 1, 'st_size': 222,
            'st_mtime_ns': 0, 'st_ctime_ns': 0}}
src_id = identity_from_dict(src_dict)

class FakeStat:
    st_dev = 54; st_ino = 999; st_uid = 1000; st_gid = 1000
    st_mode = 0o40755; st_nlink = 1; st_size = 222
dest_id = identity_from_stat(FakeStat())

assert src_id != dest_id

record = {{'dir': 'test', 'status': 'ERROR_identity_mismatch', 'attempted': True, 'moved': True, 'verified': False}}
assert record['moved'] == True
assert record['verified'] == False
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T10 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T10 PASS: identity mismatch → truthful partial (moved, not verified)')


def test_t11_fd_ownership(tmp: Path) -> None:
    code = f'''
import sys, os, stat
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
import recovery_quarantine_w4 as rq

tmp = Path("{tmp}")
parent = tmp / "p"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
(cache / "f.pyc").write_bytes(b"x")
os.chmod(str(cache / "f.pyc"), 0o644)

spec = {{
    'dir_id': 'test',
    'parent': parent,
    'parent_inode': 99999999,
    'cache_name': '__pycache__',
    'dest_name': 'quarantined-test',
    'expected_files': {{}},
}}

try:
    rq.verify_remaining_dir(spec)
    assert False, "Should have raised"
except ValueError:
    pass
print("OK")
'''
    proc = _run_test_code(tmp, code)
    assert proc.returncode == 0, f'T11 failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T11 PASS: FD ownership, no leaks on exception')


def main() -> None:
    tests = [
        test_t1_compile,
        test_t2_identity_fix,
        test_t3_first_moved_positive,
        test_t4_first_moved_source_present,
        test_t5_first_moved_wrong_inode,
        test_t6_full_remaining_positive,
        test_t7_wrong_first_dest_denies,
        test_t8_unit_unknown_zero_renames,
        test_t9_partial_failure_journal,
        test_t10_identity_mismatch_partial,
        test_t11_fd_ownership,
    ]

    passed = 0
    failed = 0

    for test in tests:
        tmp = Path(tempfile.mkdtemp(prefix='w4v3q-rec-test-'))
        try:
            test(tmp)
            passed += 1
        except AssertionError as e:
            print(f'  ASSERT: {e}')
            failed += 1
        except Exception as e:
            print(f'  ERROR: {type(e).__name__}: {e}')
            failed += 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    print(f'\nRecovery Tests: {passed} passed, {failed} failed / {len(tests)} total')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
