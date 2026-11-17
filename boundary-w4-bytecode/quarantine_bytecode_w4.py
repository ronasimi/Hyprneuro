#!/usr/bin/env python3
"""
Standalone bytecode quarantine for W4-v3 declared import chain.
ONE operation: atomic renameat2 RENAME_NOREPLACE for ALL 4 cache dirs.
Reuses pattern from driver-key-cleanup-correction/quarantine_once.py.

NOT a security boundary. Cooperative same-UID/manager scope.
No import of old modules. Standalone. Current runtime modules hashed BEFORE any import.
"""
import ctypes
import datetime
import hashlib
import json
import os
import stat
import sys
import time
import uuid
from pathlib import Path

# --- Closed literal inventory (EXACT, not dynamic) ---

QUARANTINE_DEST = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3-bytecode-preflight/quarantined')

DIRS = [
    {
        'id': 'v3',
        'parent': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3'),
        'parent_inode': 10549454,
        'cache_name': '__pycache__',
        'expected_files': {
            'continuation_ops_w4.cpython-313.pyc': {
                'sha256': 'd09c448f285c10363c2e3cf9f589914535d57bb3e8e1320e5e4181a5c83bd81f',
                'inode': 10557880, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 22620,
            },
            'continuation_runner_w4.cpython-313.pyc': {
                'sha256': '2baa4ae46eb6305b046525faced20fce5787d9491cbc4dbfe95c0463c0c3fb39',
                'inode': 10557881, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 23001,
            },
            'continuation_waiter_w4.cpython-313.pyc': {
                'sha256': '059a8c6b404cb2500e01d35bf0f396f331d916826ebbbc5425e35e846fa17246',
                'inode': 10557882, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 8999,
            },
        },
    },
    {
        'id': 'v5_root',
        'parent': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5'),
        'parent_inode': 10485370,
        'cache_name': '__pycache__',
        'expected_files': {
            'continuation_ops.cpython-313.pyc': {
                'sha256': 'b23ef48cba33a1c25e714c7e151bd4bec575ef3e6e002827084daf7780e0999c',
                'inode': 10485580, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 24150,
            },
            'continuation_runner.cpython-313.pyc': {
                'sha256': '63d037d904d88c6781cde10995ea6c44f27e2e56d23427de8ec2ab684608b876',
                'inode': 10486985, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 8971,
            },
        },
    },
    {
        'id': 'v5_scripts',
        'parent': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts'),
        'parent_inode': 10485371,
        'cache_name': '__pycache__',
        'expected_files': {
            'execstart_stable_compare.cpython-313.pyc': {
                'sha256': 'd114d8b22159f78fdbb3636b8f7a2cee69cb065d323f2b3025975a79a2ed7807',
                'inode': 10485582, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 6441,
            },
        },
    },
    {
        'id': '04_ops',
        'parent': Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops'),
        'parent_inode': 10432649,
        'cache_name': '__pycache__',
        'expected_files': {
            'boundary_release.cpython-313.pyc': {
                'sha256': 'dc8b83936a6a9221b9ad873f7a713655fe9020f037e9f78bd6a82d290e3763d0',
                'inode': 10453989, 'dev': 54, 'uid': 1000, 'mode': 0o600, 'nlink': 1, 'size': 25335,
            },
            'boundary_release_ops.cpython-313.pyc': {
                'sha256': 'b3aa5d72f81accaabd1ce881f5b55257f19b2b448f3f06925ae30e435bb1728c',
                'inode': 10474823, 'dev': 54, 'uid': 1000, 'mode': 0o600, 'nlink': 1, 'size': 44579,
            },
            'capture_boundary_model_baseline.cpython-313.pyc': {
                'sha256': 'ed6476bfaa39c2529c89a634b9f015a961fc22aba1a276fac399f3751a83a220',
                'inode': 10453996, 'dev': 54, 'uid': 1000, 'mode': 0o600, 'nlink': 1, 'size': 21804,
            },
            'capture_boundary_preservation_aux.cpython-313.pyc': {
                'sha256': '5852015d0c40a6d1208d5739f0fa9754f8359c57c975b4afd244caac8805c37f',
                'inode': 10453997, 'dev': 54, 'uid': 1000, 'mode': 0o600, 'nlink': 1, 'size': 8071,
            },
        },
    },
]

# 4 units for quiescence check
UNITS = ('hyprneuro.service', 'hyprneuro-ui.service', 'hyprneuro-pi-identity.service', 'hyprneuro-pi-identity.socket')


# --- Utilities (standalone, no external imports) ---

def metadata(st):
    return {k: getattr(st, k) for k in
            ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns']}

def identity(st):
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode), st.st_nlink, st.st_size)

def stable(st):
    return identity(st) + (st.st_mtime_ns, st.st_ctime_ns)

def hash_fd(fd):
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()

def canonical_dir_fd(path: Path) -> int:
    """Open directory chain with O_NOFOLLOW at each level."""
    assert path.is_absolute() and path == path.resolve()
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in path.parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise

def durable_write(dir_fd: int, name: str, data: dict) -> str:
    """Write evidence file with O_EXCL + fsync. Returns SHA."""
    raw = (json.dumps(data, indent=2, sort_keys=True) + '\n').encode()
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=dir_fd)
    try:
        offset = 0
        while offset < len(raw):
            offset += os.write(fd, raw[offset:])
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(dir_fd)
    return hashlib.sha256(raw).hexdigest()


# --- Quiescence (cooperative, bounded) ---

def check_quiescence() -> dict:
    """Check 4 units inactive + bounded relevant writer check.
    Cooperative assumption: NOT hostile same-UID isolation.
    Unreadable/unrelated → UNKNOWN, not blanket block.
    """
    result = {'units': {}, 'relevant_writers': 'UNKNOWN', 'status': 'OK'}

    # Unit states (bounded systemctl show)
    for unit in UNITS:
        try:
            import subprocess
            out = subprocess.run(
                ['/usr/bin/systemctl', '--user', 'show', '-p', 'ActiveState', '-p', 'SubState',
                 '-p', 'MainPID', '-p', 'Job', '-p', 'ControlGroup', '--value', unit],
                capture_output=True, text=True, timeout=5
            ).stdout.strip().split('\n')
            states = dict(zip(['ActiveState', 'SubState', 'MainPID', 'Job', 'ControlGroup'], out))
            result['units'][unit] = states
            if states.get('ActiveState') != 'inactive' or states.get('SubState') != 'dead':
                result['status'] = 'BLOCKED'
                result['reason'] = f'{unit} not inactive/dead'
                return result
        except Exception as e:
            result['units'][unit] = 'UNKNOWN'
            # Don't block on unreadable - record UNKNOWN

    # Bounded relevant writer check: only processes with cwd/fds pointing to our 4 roots
    roots = [str(d['parent']) for d in DIRS]
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            # Check cwd
            try:
                cwd = os.readlink(proc / 'cwd')
                if any(cwd.startswith(r) for r in roots):
                    found.append(int(proc.name))
                    continue
            except (FileNotFoundError, PermissionError):
                pass
            # Check fds (bounded: only check if proc is readable)
            try:
                for fd_entry in (proc / 'fd').iterdir():
                    try:
                        link = os.readlink(fd_entry)
                        if any(link.startswith(r) for r in roots):
                            found.append(int(proc.name))
                            break
                    except (FileNotFoundError, PermissionError):
                        pass
            except (PermissionError, FileNotFoundError):
                pass  # Unreadable → UNKNOWN, not block
        except (FileNotFoundError, ProcessLookupError):
            pass

    if found:
        result['relevant_writers'] = sorted(set(found))
        result['status'] = 'BLOCKED'
        result['reason'] = f'Relevant writers found: {sorted(set(found))}'
    else:
        result['relevant_writers'] = 'NONE_FOUND'

    return result


# --- Verify single dir ---

def verify_dir(dir_spec: dict, journal_dir_fd: int, expected_dev: int = 54) -> dict:
    """Verify one cache dir matches exact inventory. Returns evidence or raises."""
    parent_fd = canonical_dir_fd(dir_spec['parent'])
    try:
        # Verify parent identity
        pstat = os.fstat(parent_fd)
        if pstat.st_ino != dir_spec['parent_inode']:
            raise ValueError(f"{dir_spec['id']}: parent inode {pstat.st_ino} != expected {dir_spec['parent_inode']}")
        if expected_dev is not None and pstat.st_dev != expected_dev:
            raise ValueError(f"{dir_spec['id']}: parent dev {pstat.st_dev} != {expected_dev}")

        # Open cache dir
        cache_fd = os.open(dir_spec['cache_name'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
        try:
            cstat = os.fstat(cache_fd)
            if not stat.S_ISDIR(cstat.st_mode):
                raise ValueError(f"{dir_spec['id']}: not a directory")
            if cstat.st_uid != 1000:
                raise ValueError(f"{dir_spec['id']}: uid {cstat.st_uid} != 1000")

            # Verify exact file list
            actual_files = os.listdir(cache_fd)
            expected_names = list(dir_spec['expected_files'].keys())
            if sorted(actual_files) != sorted(expected_names):
                raise ValueError(f"{dir_spec['id']}: file list mismatch: {actual_files} != {expected_names}")

            # Verify each file
            file_evidence = {}
            for name, expected in dir_spec['expected_files'].items():
                ffd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=cache_fd)
                try:
                    fstat = os.fstat(ffd)
                    if not stat.S_ISREG(fstat.st_mode):
                        raise ValueError(f"{dir_spec['id']}/{name}: not regular")
                    if fstat.st_nlink != 1:
                        raise ValueError(f"{dir_spec['id']}/{name}: nlink {fstat.st_nlink} != 1")
                    if fstat.st_uid != expected['uid']:
                        raise ValueError(f"{dir_spec['id']}/{name}: uid mismatch")
                    if stat.S_IMODE(fstat.st_mode) != expected['mode']:
                        raise ValueError(f"{dir_spec['id']}/{name}: mode mismatch")
                    if fstat.st_size != expected['size']:
                        raise ValueError(f"{dir_spec['id']}/{name}: size mismatch")
                    if fstat.st_ino != expected['inode']:
                        raise ValueError(f"{dir_spec['id']}/{name}: inode mismatch")
                    sha = hash_fd(ffd)
                    if sha != expected['sha256']:
                        raise ValueError(f"{dir_spec['id']}/{name}: SHA mismatch")
                    file_evidence[name] = metadata(fstat) | {'sha256': sha}
                finally:
                    os.close(ffd)

            return {
                'dir_id': dir_spec['id'],
                'dir_stat': metadata(cstat),
                'files': file_evidence,
                'file_count': len(file_evidence),
                'parent_fd': parent_fd,
                'cache_fd': cache_fd,
            }
        finally:
            # Don't close here - caller manages
            pass
    except BaseException:
        os.close(parent_fd)
        raise


# --- Main quarantine operation ---

def main() -> None:
    os.umask(0o077)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Quiescence
    quiescence = check_quiescence()
    if quiescence['status'] == 'BLOCKED':
        print(json.dumps({'status': 'BLOCKED', 'reason': quiescence.get('reason'), 'quiescence': quiescence}))
        raise SystemExit(1)

    # Create quarantine destination
    QUARANTINE_DEST.parent.mkdir(parents=True, exist_ok=True)
    if not QUARANTINE_DEST.exists():
        os.mkdir(str(QUARANTINE_DEST), 0o700)
    q_fd = canonical_dir_fd(QUARANTINE_DEST)
    q_stat = os.fstat(q_fd)
    if stat.S_IMODE(q_stat.st_mode) != 0o700:
        os.close(q_fd)
        raise ValueError(f'Quarantine dest mode {oct(stat.S_IMODE(q_stat.st_mode))} != 0o700')
    if q_stat.st_dev != 54:
        os.close(q_fd)
        raise ValueError(f'Quarantine dest dev {q_stat.st_dev} != 54 (not same filesystem)')

    # Verify ALL dirs BEFORE any mutation (FDs managed in list, closed in finally)
    open_fds = []  # Track all opened FDs for cleanup
    verifications = []
    try:
        for dir_spec in DIRS:
            v = verify_dir(dir_spec, q_fd)
            verifications.append(v)
            open_fds.extend([v['parent_fd'], v['cache_fd']])

        # Write before.json
        before = {
            'timestamp': ts,
            'action': 'quarantine_all_4_cache_dirs',
            'quiescence': quiescence,
            'dirs': [{k: v[k] for k in ('dir_id', 'dir_stat', 'files', 'file_count')} for v in verifications],
            'total_files': sum(v['file_count'] for v in verifications),
        }
        before_sha = durable_write(q_fd, 'before.json', before)

        # Write intent.json
        intent = {
            'timestamp': ts,
            'action': 'renameat2 RENAME_NOREPLACE x4',
            'source_dirs': [str(d['parent'] / d['cache_name']) for d in DIRS],
            'destination': str(QUARANTINE_DEST),
            'before_sha256': before_sha,
            'copy_fallback': False,
            'restore_or_retry': False,
        }
        intent_sha = durable_write(q_fd, 'intent.json', intent)

        # Execute: renameat2 for each dir
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        RENAME_NOREPLACE = 1

        results = []
        for i, (dir_spec, v) in enumerate(zip(DIRS, verifications)):
            dest_name = f'quarantined-{dir_spec["id"]}'
            # Final check immediately before mutation
            actual_files = os.listdir(v['cache_fd'])
            if sorted(actual_files) != sorted(dir_spec['expected_files'].keys()):
                results.append({'dir': dir_spec['id'], 'status': 'BLOCKED_FILE_DRIFT'})
                break

            rc = renameat2(v['parent_fd'], dir_spec['cache_name'].encode(), q_fd, dest_name.encode(), RENAME_NOREPLACE)
            if rc != 0:
                errno = ctypes.get_errno()
                results.append({'dir': dir_spec['id'], 'status': f'FAILED_renameat2_errno_{errno}'})
                break

            # fsync BOTH parent fds (source parent + quarantine dest)
            os.fsync(v['parent_fd'])
            os.fsync(q_fd)

            # Verify: original absent
            try:
                os.stat(dir_spec['cache_name'], dir_fd=v['parent_fd'], follow_symlinks=False)
                results.append({'dir': dir_spec['id'], 'status': 'ERROR_original_still_present'})
                break
            except FileNotFoundError:
                pass

            # Verify: destination present with matching identity
            dest_fd = os.open(dest_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=q_fd)
            try:
                dest_stat = os.fstat(dest_fd)
                if identity(dest_stat) != identity(v['dir_stat']):
                    results.append({'dir': dir_spec['id'], 'status': 'ERROR_identity_mismatch'})
                    break
            finally:
                os.close(dest_fd)

            results.append({'dir': dir_spec['id'], 'status': 'QUARANTINED'})
            # Close this dir's FDs (no longer needed)
            os.close(v['cache_fd'])
            os.close(v['parent_fd'])
            # Remove from open_fds track
            open_fds.remove(v['cache_fd'])
            open_fds.remove(v['parent_fd'])

        # Write after.json (always, even on partial failure)
        after = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'results': results,
            'all_succeeded': all(r['status'] == 'QUARANTINED' for r in results) and len(results) == 4,
            'partial_failure': any(r['status'] != 'QUARANTINED' for r in results),
            'before_sha256': before_sha,
            'intent_sha256': intent_sha,
            'no_retry_performed': True,
            'no_copy_fallback': True,
            'no_rollback': True,
        }
        after_sha = durable_write(q_fd, 'after.json', after)

    finally:
        # Close ALL remaining FDs (no leaks)
        for fd in open_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        os.close(q_fd)

    print(json.dumps({
        'status': 'COMPLETE' if after['all_succeeded'] else 'PARTIAL_FAILURE',
        'quarantine_dir': str(QUARANTINE_DEST),
        'before_sha256': before_sha,
        'intent_sha256': intent_sha,
        'after_sha256': after_sha,
        'results': results,
    }, indent=2))

    if not after['all_succeeded']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
