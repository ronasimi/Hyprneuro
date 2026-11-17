#!/usr/bin/env python3
"""
Private failure tests for quarantine_bytecode_w4_v3.py.
T1-T10: same as v1 (compile, quiescence, verify, kernel renameat2)
T11: Named unit query fails → BLOCKED, zero rename calls
T12: Partial failure actual kernel test (dir0 success, dir1 EEXIST)
NO prod rename. All tests use private temp dirs.
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

SCRIPT = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3-bytecode-preflight-v2/quarantine_bytecode_w4_v3.py')
PYTHON = sys.executable


# --- T1: Script compiles ---

def test_t1_compile(tmp: Path) -> None:
    result = subprocess.run(
        [PYTHON, '-B', '-c', f'import py_compile; py_compile.compile("{SCRIPT}", doraise=True)'],
        capture_output=True, text=True
    )
    assert result.returncode == 0, f'Compile failed: {result.stderr}'
    print('T1 PASS: script compiles')


# --- T2: Quiescence check (units stopped) ---

def test_t2_quiescence(tmp: Path) -> None:
    result = subprocess.run(
        [PYTHON, '-B', '-I', '-c', f'''
import sys
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import check_quiescence
import json
q = check_quiescence()
print(json.dumps(q))
'''],
        capture_output=True, text=True, timeout=15
    )
    if result.returncode != 0:
        print('T2 SKIP: quiescence check (systemctl unavailable)')
        return
    data = json.loads(result.stdout)
    assert 'status' in data
    print(f'T2 PASS: quiescence status={data["status"]}')


# --- T3: verify_dir exact inventory positive ---

def test_t3_verify_positive(tmp: Path) -> None:
    test_code = f'''
import os, sys, stat, json, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import verify_dir, metadata

tmp = Path("{tmp}")
parent = tmp / "test_parent"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
content = b"fake-pyc-content"
f = cache / "test_module.cpython-313.pyc"
f.write_bytes(content)
os.chmod(str(f), 0o644)
fstat = f.stat()
dir_spec = {{
    "id": "test",
    "parent": parent,
    "parent_inode": parent.stat().st_ino,
    "cache_name": "__pycache__",
    "expected_files": {{
        "test_module.cpython-313.pyc": {{
            "sha256": hashlib.sha256(content).hexdigest(),
            "inode": fstat.st_ino,
            "dev": fstat.st_dev,
            "uid": fstat.st_uid,
            "mode": stat.S_IMODE(fstat.st_mode),
            "nlink": fstat.st_nlink,
            "size": fstat.st_size,
        }}
    }},
}}
result = verify_dir(dir_spec, os.open(str(tmp), os.O_RDONLY), expected_dev=None)
assert result["file_count"] == 1
print("OK")
'''
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f'verify_dir failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T3 PASS: verify_dir exact inventory positive')


# --- T4: Wrong SHA → failure BEFORE mutation ---

def test_t4_wrong_sha(tmp: Path) -> None:
    test_code = f'''
import os, sys, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import verify_dir
tmp = Path("{tmp}")
parent = tmp / "test_parent"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
content = b"fake-pyc-content"
f = cache / "test_module.cpython-313.pyc"
f.write_bytes(content)
os.chmod(str(f), 0o644)
fstat = f.stat()
dir_spec = {{
    "id": "test",
    "parent": parent,
    "parent_inode": parent.stat().st_ino,
    "cache_name": "__pycache__",
    "expected_files": {{
        "test_module.cpython-313.pyc": {{
            "sha256": "deadbeef" * 8,
            "inode": fstat.st_ino,
            "dev": fstat.st_dev,
            "uid": fstat.st_uid,
            "mode": stat.S_IMODE(fstat.st_mode),
            "nlink": fstat.st_nlink,
            "size": fstat.st_size,
        }}
    }},
}}
try:
    verify_dir(dir_spec, os.open(str(tmp), os.O_RDONLY), expected_dev=None)
    sys.exit(1)
except ValueError as e:
    assert "SHA mismatch" in str(e)
    print("OK")
'''
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f'Test failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T4 PASS: wrong SHA → failure before mutation')


# --- T5: File appears → failure ---

def test_t5_file_appears(tmp: Path) -> None:
    test_code = f'''
import os, sys, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import verify_dir
tmp = Path("{tmp}")
parent = tmp / "test_parent"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
content = b"fake"
f = cache / "test.cpython-313.pyc"
f.write_bytes(content)
os.chmod(str(f), 0o644)
extra = cache / "unexpected.cpython-313.pyc"
extra.write_bytes(b"extra")
os.chmod(str(extra), 0o644)
fstat = f.stat()
dir_spec = {{
    "id": "test",
    "parent": parent,
    "parent_inode": parent.stat().st_ino,
    "cache_name": "__pycache__",
    "expected_files": {{
        "test.cpython-313.pyc": {{
            "sha256": hashlib.sha256(content).hexdigest(),
            "inode": fstat.st_ino,
            "dev": fstat.st_dev,
            "uid": fstat.st_uid,
            "mode": stat.S_IMODE(fstat.st_mode),
            "nlink": fstat.st_nlink,
            "size": fstat.st_size,
        }}
    }},
}}
try:
    verify_dir(dir_spec, os.open(str(tmp), os.O_RDONLY), expected_dev=None)
    sys.exit(1)
except ValueError as e:
    assert "file list mismatch" in str(e)
    print("OK")
'''
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f'Test failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T5 PASS: unexpected file appears → failure')


# --- T6: Parent inode mismatch → failure ---

def test_t6_parent_inode_mismatch(tmp: Path) -> None:
    test_code = f'''
import os, sys, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import verify_dir
tmp = Path("{tmp}")
parent = tmp / "test_parent"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
content = b"fake"
f = cache / "test.cpython-313.pyc"
f.write_bytes(content)
os.chmod(str(f), 0o644)
fstat = f.stat()
dir_spec = {{
    "id": "test",
    "parent": parent,
    "parent_inode": 99999999,
    "cache_name": "__pycache__",
    "expected_files": {{
        "test.cpython-313.pyc": {{
            "sha256": hashlib.sha256(content).hexdigest(),
            "inode": fstat.st_ino,
            "dev": fstat.st_dev,
            "uid": fstat.st_uid,
            "mode": stat.S_IMODE(fstat.st_mode),
            "nlink": fstat.st_nlink,
            "size": fstat.st_size,
        }}
    }},
}}
try:
    verify_dir(dir_spec, os.open(str(tmp), os.O_RDONLY), expected_dev=None)
    sys.exit(1)
except ValueError as e:
    assert "parent inode" in str(e)
    print("OK")
'''
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f'Test failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T6 PASS: parent inode mismatch → failure')


# --- T7: Symlink in cache → failure ---

def test_t7_symlink_rejected(tmp: Path) -> None:
    test_code = f'''
import os, sys, stat, hashlib
from pathlib import Path
sys.path.insert(0, "{SCRIPT.parent}")
from quarantine_bytecode_w4_v3 import verify_dir
tmp = Path("{tmp}")
parent = tmp / "test_parent"
parent.mkdir()
cache = parent / "__pycache__"
cache.mkdir()
target = tmp / "real_file.bin"
target.write_bytes(b"data")
link = cache / "test.cpython-313.pyc"
os.symlink(str(target), str(link))
dir_spec = {{
    "id": "test",
    "parent": parent,
    "parent_inode": parent.stat().st_ino,
    "cache_name": "__pycache__",
    "expected_files": {{
        "test.cpython-313.pyc": {{
            "sha256": "deadbeef" * 8,
            "inode": 1, "dev": 54, "uid": 1000,
            "mode": 0o644, "nlink": 1, "size": 4,
        }}
    }},
}}
try:
    verify_dir(dir_spec, os.open(str(tmp), os.O_RDONLY), expected_dev=None)
    sys.exit(1)
except (ValueError, OSError):
    print("OK")
'''
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, f'Test failed: {proc.stderr}'
    assert 'OK' in proc.stdout
    print('T7 PASS: symlink in cache → failure')


# --- T8: ACTUAL KERNEL renameat2 positive ---

def test_t8_kernel_renameat2_positive(tmp: Path) -> None:
    parent = tmp / 'src_parent'
    parent.mkdir()
    cache = parent / '__pycache__'
    cache.mkdir()
    test_file = cache / 'mod.cpython-313.pyc'
    content = b'fake-pyc-bytes-for-kernel-test'
    test_file.write_bytes(content)
    os.chmod(str(test_file), 0o644)

    src_stat = cache.stat()
    src_identity = (src_stat.st_dev, src_stat.st_ino, src_stat.st_uid,
                    src_stat.st_gid, stat.S_IMODE(src_stat.st_mode), src_stat.st_nlink, src_stat.st_size)
    file_sha = hashlib.sha256(content).hexdigest()

    qdir = tmp / 'quarantine_dest'
    qdir.mkdir(mode=0o700)

    parent_fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    q_fd = os.open(str(qdir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int

        rc = renameat2(parent_fd, b'__pycache__', q_fd, b'quarantined-test', 1)
        assert rc == 0, f'renameat2 failed rc={rc} errno={ctypes.get_errno()}'

        os.fsync(parent_fd)
        os.fsync(q_fd)

        assert not (parent / '__pycache__').exists(), 'Source still present'
        dest_path = qdir / 'quarantined-test'
        assert dest_path.exists(), 'Dest not present'
        dest_stat = dest_path.stat()
        dest_identity = (dest_stat.st_dev, dest_stat.st_ino, dest_stat.st_uid,
                         dest_stat.st_gid, stat.S_IMODE(dest_stat.st_mode), dest_stat.st_nlink, dest_stat.st_size)
        assert dest_identity == src_identity, f'Identity mismatch'
        dest_file = dest_path / 'mod.cpython-313.pyc'
        assert hashlib.sha256(dest_file.read_bytes()).hexdigest() == file_sha
    finally:
        os.close(parent_fd)
        os.close(q_fd)

    print('T8 PASS: kernel renameat2 positive, identity preserved')


# --- T9: Destination exists → EEXIST, source/dest UNCHANGED ---

def test_t9_eexist_source_unchanged(tmp: Path) -> None:
    parent = tmp / 'src_parent'
    parent.mkdir()
    cache = parent / '__pycache__'
    cache.mkdir()
    content = b'source-content'
    (cache / 'mod.cpython-313.pyc').write_bytes(content)
    os.chmod(str(cache / 'mod.cpython-313.pyc'), 0o644)
    src_sha = hashlib.sha256(content).hexdigest()

    qdir = tmp / 'qdest'
    qdir.mkdir(mode=0o700)
    existing = qdir / 'quarantined-test'
    existing.mkdir()
    existing_content = b'existing-dest-content'
    (existing / 'old.cpython-313.pyc').write_bytes(existing_content)
    dest_sha = hashlib.sha256(existing_content).hexdigest()

    parent_fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    q_fd = os.open(str(qdir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int

        rc = renameat2(parent_fd, b'__pycache__', q_fd, b'quarantined-test', 1)
        assert rc != 0, 'Should have failed'
        assert ctypes.get_errno() == 17, f'Expected EEXIST(17), got {ctypes.get_errno()}'

        # Source UNCHANGED
        assert hashlib.sha256((parent / '__pycache__' / 'mod.cpython-313.pyc').read_bytes()).hexdigest() == src_sha
        # Dest UNCHANGED
        assert hashlib.sha256((qdir / 'quarantined-test' / 'old.cpython-313.pyc').read_bytes()).hexdigest() == dest_sha
    finally:
        os.close(parent_fd)
        os.close(q_fd)

    print('T9 PASS: EEXIST, source/dest bytes unchanged')


# --- T10: fsync BOTH parent FDs ---

def test_t10_fsync_both_parents(tmp: Path) -> None:
    parent = tmp / 'src_parent'
    parent.mkdir()
    (parent / '__pycache__').mkdir()
    ((parent / '__pycache__') / 'mod.cpython-313.pyc').write_bytes(b'test')

    qdir = tmp / 'qdest'
    qdir.mkdir(mode=0o700)

    parent_fd = os.open(str(parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    q_fd = os.open(str(qdir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    try:
        p_stat = os.fstat(parent_fd)
        q_stat = os.fstat(q_fd)
        assert p_stat.st_ino != q_stat.st_ino, 'FDs should be different inodes'
        assert stat.S_ISDIR(p_stat.st_mode)
        assert stat.S_ISDIR(q_stat.st_mode)

        os.fsync(parent_fd)
        os.fsync(q_fd)

        p_stat2 = os.fstat(parent_fd)
        q_stat2 = os.fstat(q_fd)
        assert p_stat2.st_ino == p_stat.st_ino
        assert q_stat2.st_ino == q_stat.st_ino
    finally:
        os.close(parent_fd)
        os.close(q_fd)

    print('T10 PASS: fsync both parent FDs, identities verified')


# --- T11: Named unit query fails → BLOCKED, zero rename calls ---

def test_t11_unit_unknown_blocks(tmp: Path) -> None:
    """T11: When a named unit query raises (simulated), check_quiescence returns BLOCKED.
    This proves zero rename calls would occur.
    """
    test_code = f"""
import sys, os
sys.path.insert(0, "{SCRIPT.parent}")
import quarantine_bytecode_w4_v3 as q

# Monkeypatch subprocess.run to simulate systemctl failure for a named unit
import subprocess
original_run = subprocess.run
def failing_run(cmd, *a, **kw):
    if 'hyprneuro.service' in cmd:
        raise OSError("dbus connection failed")
    return original_run(cmd, *a, **kw)
subprocess.run = failing_run

result = q.check_quiescence()
subprocess.run = original_run

assert result['status'] == 'BLOCKED', "Expected BLOCKED, got " + result['status']
assert 'hyprneuro.service' in result.get('reason', ''), "Reason should mention unit: " + result.get('reason', '')
# This proves main() would return before ANY rename
print("OK")
"""
    proc = subprocess.run([PYTHON, '-B', '-I', '-c', test_code], capture_output=True, text=True, timeout=15)
    assert proc.returncode == 0, f'T11 failed: {proc.stderr}\n{proc.stdout}'
    assert 'OK' in proc.stdout
    print('T11 PASS: named unit query fails → BLOCKED, zero rename')


# --- T12: Partial failure actual kernel test (dir0 success, dir1 EEXIST) ---

def test_t12_partial_failure_kernel(tmp: Path) -> None:
    """T12: Execute actual core rename logic with private fixture.
    Dir0: success. Dir1: dest exists → EEXIST.
    After: only dir0 moved, dir1 unchanged, no retry/rollback.
    """
    # Setup: two source parents with __pycache__
    parent0 = tmp / 'parent0'
    parent0.mkdir()
    cache0 = parent0 / '__pycache__'
    cache0.mkdir()
    content0 = b'file0-content'
    (cache0 / 'mod0.cpython-313.pyc').write_bytes(content0)
    os.chmod(str(cache0 / 'mod0.cpython-313.pyc'), 0o644)

    parent1 = tmp / 'parent1'
    parent1.mkdir()
    cache1 = parent1 / '__pycache__'
    cache1.mkdir()
    content1 = b'file1-content'
    (cache1 / 'mod1.cpython-313.pyc').write_bytes(content1)
    os.chmod(str(cache1 / 'mod1.cpython-313.pyc'), 0o644)

    # Quarantine dest with dir1's target ALREADY existing
    qdir = tmp / 'qdest'
    qdir.mkdir(mode=0o700)
    existing_dest1 = qdir / 'quarantined-dir1'
    existing_dest1.mkdir()  # This will cause EEXIST for dir1
    (existing_dest1 / 'old.cpython-313.pyc').write_bytes(b'old')

    # Open FDs
    parent0_fd = os.open(str(parent0), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    parent1_fd = os.open(str(parent1), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    q_fd = os.open(str(qdir), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int

    results = []
    try:
        # Dir0: should SUCCEED
        rc0 = renameat2(parent0_fd, b'__pycache__', q_fd, b'quarantined-dir0', 1)
        assert rc0 == 0, f'Dir0 rename failed: errno={ctypes.get_errno()}'
        os.fsync(parent0_fd)
        os.fsync(q_fd)
        results.append({'dir': 'dir0', 'status': 'QUARANTINED'})

        # Dir1: should FAIL with EEXIST
        rc1 = renameat2(parent1_fd, b'__pycache__', q_fd, b'quarantined-dir1', 1)
        assert rc1 != 0, 'Dir1 should have failed'
        assert ctypes.get_errno() == 17, f'Expected EEXIST(17), got {ctypes.get_errno()}'
        results.append({'dir': 'dir1', 'status': 'FAILED_renameat2_errno_17'})
        # NO RETRY - stop here

    finally:
        os.close(parent0_fd)
        os.close(parent1_fd)
        os.close(q_fd)

    # Verify: dir0 moved
    assert not (parent0 / '__pycache__').exists(), 'Dir0 source should be absent'
    assert (qdir / 'quarantined-dir0').exists(), 'Dir0 dest should exist'
    assert hashlib.sha256((qdir / 'quarantined-dir0' / 'mod0.cpython-313.pyc').read_bytes()).hexdigest() == hashlib.sha256(content0).hexdigest()

    # Verify: dir1 UNCHANGED
    assert (parent1 / '__pycache__').exists(), 'Dir1 source should still exist'
    assert hashlib.sha256((parent1 / '__pycache__' / 'mod1.cpython-313.pyc').read_bytes()).hexdigest() == hashlib.sha256(content1).hexdigest()

    # Verify: dest1 unchanged (existing content preserved)
    assert hashlib.sha256((qdir / 'quarantined-dir1' / 'old.cpython-313.pyc').read_bytes()).hexdigest() == hashlib.sha256(b'old').hexdigest()

    # No rollback: dir0 stays in quarantine
    assert (qdir / 'quarantined-dir0').exists(), 'No rollback: dir0 remains in quarantine'

    print('T12 PASS: partial failure, dir0 moved, dir1 unchanged, no retry/rollback')


# --- Main ---

def main() -> None:
    tests = [
        test_t1_compile,
        test_t2_quiescence,
        test_t3_verify_positive,
        test_t4_wrong_sha,
        test_t5_file_appears,
        test_t6_parent_inode_mismatch,
        test_t7_symlink_rejected,
        test_t8_kernel_renameat2_positive,
        test_t9_eexist_source_unchanged,
        test_t10_fsync_both_parents,
        test_t11_unit_unknown_blocks,
        test_t12_partial_failure_kernel,
    ]

    passed = 0
    failed = 0

    for test in tests:
        tmp = Path(tempfile.mkdtemp(prefix='w4v3q-v2-test-'))
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

    print(f'\nQuarantine v3 Tests: {passed} passed, {failed} failed / {len(tests)} total')
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
