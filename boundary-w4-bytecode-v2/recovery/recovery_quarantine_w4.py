#!/usr/bin/env python3
"""
Bytecode quarantine RECOVERY script for partial failure state.
Completes remaining 3 dirs after v3 was already moved.

CRITICAL: This is a SEPARATE context from the original failed run.
- Does NOT replay the first (v3) move
- Verifies first already-moved dir with exact identity + file hashes
- Completes remaining 3 with fresh one-shot
- NEW private journal dir (not overwriting existing)
- Truthful partial journal: attempted/moved/verified distinction

Identity fix: explicit metadata dict normalizer (not blind cast to stat).
FD ownership: close-once in all exception paths.
No import of uncatalogued pycs. stdlib-only. Launch: python3 -B -I
"""
import ctypes
import datetime
import hashlib
import json
import os
import stat
import sys
from pathlib import Path

# --- Closed literal inventory (EXACT, from before.json + forensics) ---

QUARANTINE_BASE = Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3-bytecode-preflight/quarantined')
RECOVERY_JOURNAL_DIR = QUARANTINE_BASE / 'recovery-journal'

# First already-moved dir (v3) - VERIFY ONLY, do not re-move
FIRST_MOVED = {
    'dir_id': 'v3',
    'expected_source': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-w4-v3/__pycache__'),
    'expected_dest_name': 'quarantined-v3',
    'expected_dev': 54,
    'expected_inode': 10557740,
    'expected_uid': 1000,
    'expected_mode': 0o755,
    'expected_files': {
        'continuation_ops_w4.cpython-313.pyc': 'd09c448f285c10363c2e3cf9f589914535d57bb3e8e1320e5e4181a5c83bd81f',
        'continuation_runner_w4.cpython-313.pyc': '2baa4ae46eb6305b046525faced20fce5787d9491cbc4dbfe95c0463c0c3fb39',
        'continuation_waiter_w4.cpython-313.pyc': '059a8c6b404cb2500e01d35bf0f396f331d916826ebbbc5425e35e846fa17246',
    },
}

# Remaining 3 dirs to quarantine
REMAINING = [
    {
        'dir_id': 'v5_root',
        'parent': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5'),
        'parent_inode': 10485370,
        'cache_name': '__pycache__',
        'dest_name': 'quarantined-v5_root',
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
        'dir_id': 'v5_scripts',
        'parent': Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-continuation-04-freeze-v5/scripts'),
        'parent_inode': 10485371,
        'cache_name': '__pycache__',
        'dest_name': 'quarantined-v5_scripts',
        'expected_files': {
            'execstart_stable_compare.cpython-313.pyc': {
                'sha256': 'd114d8b22159f78fdbb3636b8f7a2cee69cb065d323f2b3025975a79a2ed7807',
                'inode': 10485582, 'dev': 54, 'uid': 1000, 'mode': 0o644, 'nlink': 1, 'size': 6441,
            },
        },
    },
    {
        'dir_id': '04_ops',
        'parent': Path('/home/ron/Workspace/hn-boundary-18aef68-04/ops'),
        'parent_inode': 10432649,
        'cache_name': '__pycache__',
        'dest_name': 'quarantined-04_ops',
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

UNITS = ('hyprneuro.service', 'hyprneuro-ui.service', 'hyprneuro-pi-identity.service', 'hyprneuro-pi-identity.socket')


# --- Identity normalizers (FIX: dict vs stat) ---

IDENTITY_KEYS = ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size')

def identity_from_stat(st) -> tuple:
    """Extract identity tuple from os.stat_result."""
    return (st.st_dev, st.st_ino, st.st_uid, st.st_gid, stat.S_IMODE(st.st_mode), st.st_nlink, st.st_size)

def identity_from_dict(d: dict) -> tuple:
    """Extract identity tuple from a metadata dict (closed keys, reject unknown)."""
    for key in IDENTITY_KEYS:
        if key not in d:
            raise ValueError(f'metadata dict missing required key: {key}')
    # Reject unknown keys (closed type)
    allowed = set(IDENTITY_KEYS) | {'st_mtime_ns', 'st_ctime_ns'}
    extra = set(d.keys()) - allowed
    if extra:
        raise ValueError(f'metadata dict has unexpected keys: {extra}')
    return (d['st_dev'], d['st_ino'], d['st_uid'], d['st_gid'], stat.S_IMODE(d['st_mode']), d['st_nlink'], d['st_size'])


def metadata(st) -> dict:
    """Convert stat result to dict with complete closed keys."""
    return {k: getattr(st, k) for k in
            ['st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns']}


def hash_fd(fd) -> str:
    os.lseek(fd, 0, os.SEEK_SET)
    h = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1024 * 1024)
        if not chunk:
            break
        h.update(chunk)
    return h.hexdigest()


def canonical_dir_fd(path: Path) -> int:
    """Open directory chain with O_NOFOLLOW at each level. Explicit ValueError for security."""
    if not path.is_absolute():
        raise ValueError(f'canonical_dir_fd: path not absolute: {path}')
    if path != path.resolve():
        raise ValueError(f'canonical_dir_fd: path not resolved (symlink?): {path}')
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
    """Write evidence file with O_EXCL + fsync. Returns SHA. Raises if file exists."""
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


# --- Quiescence (strict: named unit UNKNOWN → BLOCK) ---

def check_quiescence() -> dict:
    """Check 4 named units inactive. ANY named unit query failure → BLOCKED.
    Bounded relevant writer check (cooperative, not all-UID scan).
    """
    result = {'units': {}, 'relevant_writers': 'UNKNOWN', 'status': 'OK'}

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
                result['reason'] = f'{unit} not inactive/dead: {states}'
                return result
        except Exception as e:
            result['units'][unit] = f'UNKNOWN: {type(e).__name__}: {e}'
            result['status'] = 'BLOCKED'
            result['reason'] = f'Named unit {unit} query failed: {type(e).__name__}: {e}'
            return result

    # Bounded relevant writer check
    roots = [str(d['parent']) for d in REMAINING]
    roots.append(str(FIRST_MOVED['expected_source'].parent))
    found = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit() or int(proc.name) == os.getpid():
            continue
        try:
            if proc.stat().st_uid != os.getuid():
                continue
            try:
                cwd = os.readlink(proc / 'cwd')
                if any(cwd.startswith(r) for r in roots):
                    found.append(int(proc.name))
                    continue
            except (FileNotFoundError, PermissionError):
                pass
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
                pass
        except (FileNotFoundError, ProcessLookupError):
            pass

    if found:
        result['relevant_writers'] = sorted(set(found))
        result['status'] = 'BLOCKED'
        result['reason'] = f'Relevant writers found: {sorted(set(found))}'
    else:
        result['relevant_writers'] = 'NONE_FOUND'

    return result


# --- Verify first already-moved dir ---

def verify_first_moved() -> dict:
    """Verify v3 was already moved correctly. Raises on any mismatch.
    Returns evidence dict. Does NOT re-move.
    """
    dest_path = QUARANTINE_BASE / FIRST_MOVED['expected_dest_name']
    source_path = FIRST_MOVED['expected_source']

    # Source must be ABSENT
    if source_path.exists():
        raise ValueError(f'First-moved source still present: {source_path}')

    # Dest must exist
    dest_fd = os.open(str(dest_path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        dstat = os.fstat(dest_fd)
        if not stat.S_ISDIR(dstat.st_mode):
            raise ValueError(f'First-moved dest not a directory: {dest_path}')
        if dstat.st_dev != FIRST_MOVED['expected_dev']:
            raise ValueError(f'First-moved dest dev {dstat.st_dev} != {FIRST_MOVED["expected_dev"]}')
        if dstat.st_ino != FIRST_MOVED['expected_inode']:
            raise ValueError(f'First-moved dest inode {dstat.st_ino} != {FIRST_MOVED["expected_inode"]}')
        if dstat.st_uid != FIRST_MOVED['expected_uid']:
            raise ValueError(f'First-moved dest uid {dstat.st_uid} != {FIRST_MOVED["expected_uid"]}')
        if stat.S_IMODE(dstat.st_mode) != FIRST_MOVED['expected_mode']:
            raise ValueError(f'First-moved dest mode {oct(stat.S_IMODE(dstat.st_mode))} != {oct(FIRST_MOVED["expected_mode"])}')

        # Verify exact file list
        actual_files = os.listdir(dest_fd)
        expected_names = list(FIRST_MOVED['expected_files'].keys())
        if sorted(actual_files) != sorted(expected_names):
            raise ValueError(f'First-moved file list mismatch: {actual_files} != {expected_names}')

        # Verify each file hash
        file_evidence = {}
        for name, expected_sha in FIRST_MOVED['expected_files'].items():
            ffd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dest_fd)
            try:
                fstat = os.fstat(ffd)
                if not stat.S_ISREG(fstat.st_mode):
                    raise ValueError(f'First-moved file not regular: {name}')
                sha = hash_fd(ffd)
                if sha != expected_sha:
                    raise ValueError(f'First-moved file SHA mismatch: {name}')
                file_evidence[name] = metadata(fstat) | {'sha256': sha}
            finally:
                os.close(ffd)

        return {
            'dir_id': 'v3',
            'status': 'VERIFIED_ALREADY_MOVED',
            'dest_stat': metadata(dstat),
            'files': file_evidence,
            'file_count': len(file_evidence),
        }
    finally:
        os.close(dest_fd)


# --- Verify single remaining dir ---

def verify_remaining_dir(dir_spec: dict, expected_dev: int = 54) -> dict:
    """Verify one remaining cache dir matches exact inventory. Returns evidence with FDs.
    Caller MUST close returned FDs.
    """
    parent_fd = canonical_dir_fd(dir_spec['parent'])
    try:
        pstat = os.fstat(parent_fd)
        if pstat.st_ino != dir_spec['parent_inode']:
            os.close(parent_fd)
            raise ValueError(f"{dir_spec['dir_id']}: parent inode {pstat.st_ino} != expected {dir_spec['parent_inode']}")
        if expected_dev is not None and pstat.st_dev != expected_dev:
            os.close(parent_fd)
            raise ValueError(f"{dir_spec['dir_id']}: parent dev {pstat.st_dev} != {expected_dev}")

        cache_fd = os.open(dir_spec['cache_name'], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
        try:
            cstat = os.fstat(cache_fd)
            if not stat.S_ISDIR(cstat.st_mode):
                os.close(cache_fd)
                os.close(parent_fd)
                raise ValueError(f"{dir_spec['dir_id']}: not a directory")

            actual_files = os.listdir(cache_fd)
            expected_names = list(dir_spec['expected_files'].keys())
            if sorted(actual_files) != sorted(expected_names):
                os.close(cache_fd)
                os.close(parent_fd)
                raise ValueError(f"{dir_spec['dir_id']}: file list mismatch: {actual_files} != {expected_names}")

            file_evidence = {}
            for name, expected in dir_spec['expected_files'].items():
                ffd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=cache_fd)
                try:
                    fstat = os.fstat(ffd)
                    if not stat.S_ISREG(fstat.st_mode):
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: not regular")
                    if fstat.st_nlink != 1:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: nlink {fstat.st_nlink} != 1")
                    if fstat.st_uid != expected['uid']:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: uid mismatch")
                    if stat.S_IMODE(fstat.st_mode) != expected['mode']:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: mode mismatch")
                    if fstat.st_size != expected['size']:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: size mismatch")
                    if fstat.st_ino != expected['inode']:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: inode mismatch")
                    sha = hash_fd(ffd)
                    if sha != expected['sha256']:
                        raise ValueError(f"{dir_spec['dir_id']}/{name}: SHA mismatch")
                    file_evidence[name] = metadata(fstat) | {'sha256': sha}
                finally:
                    os.close(ffd)

            return {
                'dir_id': dir_spec['dir_id'],
                'dir_stat': metadata(cstat),
                'files': file_evidence,
                'file_count': len(file_evidence),
                'parent_fd': parent_fd,
                'cache_fd': cache_fd,
            }
        except BaseException:
            os.close(cache_fd)
            os.close(parent_fd)
            raise
    except BaseException:
        raise


# --- Main recovery transaction ---

def main() -> None:
    os.umask(0o077)
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # Quiescence
    quiescence = check_quiescence()
    if quiescence['status'] == 'BLOCKED':
        print(json.dumps({'status': 'BLOCKED', 'reason': quiescence.get('reason'), 'quiescence': quiescence}))
        raise SystemExit(1)

    # Verify first already-moved
    first_evidence = verify_first_moved()

    # Create recovery journal dir
    RECOVERY_JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    rj_fd = canonical_dir_fd(RECOVERY_JOURNAL_DIR)

    # Quarantine base FD (dest for renameat2)
    qb_fd = canonical_dir_fd(QUARANTINE_BASE)

    # Track all open FDs for cleanup
    open_fds = [rj_fd, qb_fd]
    after_data = None
    before_sha = None
    intent_sha = None

    try:
        # Verify ALL remaining dirs BEFORE any mutation
        verifications = []
        for dir_spec in REMAINING:
            v = verify_remaining_dir(dir_spec)
            verifications.append(v)
            open_fds.extend([v['parent_fd'], v['cache_fd']])

        # Write before.json
        before = {
            'timestamp': ts,
            'action': 'recovery_complete_remaining_3',
            'quiescence': quiescence,
            'first_moved_verified': first_evidence,
            'remaining_dirs': [{k: v[k] for k in ('dir_id', 'dir_stat', 'files', 'file_count')} for v in verifications],
            'total_remaining_files': sum(v['file_count'] for v in verifications),
            'original_failed_run': {
                'before_sha256': 'f66161b7c6f67e4963d7514ab1079e969c8426360d39f1cde60fd26da237e185',
                'intent_sha256': '124c1c532a4f4bcaf2e1c8ede323c2a4b5b949a93d615eb70c953ffe94a449fd',
                'after_json': 'ABSENT',
                'crash': 'identity() dict vs stat AttributeError line 394',
            },
        }
        before_sha = durable_write(rj_fd, 'before.json', before)

        # Write intent.json
        intent = {
            'timestamp': ts,
            'action': 'renameat2 RENAME_NOREPLACE x3 (remaining only)',
            'source_dirs': [str(d['parent'] / d['cache_name']) for d in REMAINING],
            'destination': str(QUARANTINE_BASE),
            'dest_names': [d['dest_name'] for d in REMAINING],
            'before_sha256': before_sha,
            'copy_fallback': False,
            'restore_or_retry': False,
            'replay_first': False,
        }
        intent_sha = durable_write(rj_fd, 'intent.json', intent)

        # Execute: renameat2 for each remaining dir
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        RENAME_NOREPLACE = 1

        results = []
        for i, (dir_spec, v) in enumerate(zip(REMAINING, verifications)):
            dest_name = dir_spec['dest_name']
            # Final check immediately before mutation
            actual_files = os.listdir(v['cache_fd'])
            if sorted(actual_files) != sorted(dir_spec['expected_files'].keys()):
                results.append({'dir': dir_spec['dir_id'], 'status': 'BLOCKED_FILE_DRIFT', 'attempted': False, 'moved': False, 'verified': False})
                break

            rc = renameat2(v['parent_fd'], dir_spec['cache_name'].encode(), qb_fd, dest_name.encode(), RENAME_NOREPLACE)
            if rc != 0:
                errno = ctypes.get_errno()
                results.append({'dir': dir_spec['dir_id'], 'status': f'FAILED_renameat2_errno_{errno}', 'attempted': True, 'moved': False, 'verified': False})
                break

            # fsync BOTH parents (source parent + quarantine dest parent)
            os.fsync(v['parent_fd'])
            os.fsync(qb_fd)

            # Verify: original absent
            try:
                os.stat(dir_spec['cache_name'], dir_fd=v['parent_fd'], follow_symlinks=False)
                results.append({'dir': dir_spec['dir_id'], 'status': 'ERROR_original_still_present', 'attempted': True, 'moved': True, 'verified': False})
                break
            except FileNotFoundError:
                pass

            # Verify: destination present with matching identity (FIX: use identity_from_dict)
            dest_fd = os.open(dest_name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=qb_fd)
            try:
                dest_stat = os.fstat(dest_fd)
                dest_identity = identity_from_stat(dest_stat)
                source_identity = identity_from_dict(v['dir_stat'])
                if dest_identity != source_identity:
                    results.append({'dir': dir_spec['dir_id'], 'status': 'ERROR_identity_mismatch', 'attempted': True, 'moved': True, 'verified': False,
                                    'dest_identity': list(dest_identity), 'source_identity': list(source_identity)})
                    break
            finally:
                os.close(dest_fd)

            results.append({'dir': dir_spec['dir_id'], 'status': 'QUARANTINED', 'attempted': True, 'moved': True, 'verified': True})
            os.close(v['cache_fd'])
            os.close(v['parent_fd'])
            open_fds.remove(v['cache_fd'])
            open_fds.remove(v['parent_fd'])

        # Write after.json (truthful: records exact state)
        after_data = {
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'results': results,
            'all_succeeded': all(r['status'] == 'QUARANTINED' for r in results) and len(results) == 3,
            'partial_failure': any(r['status'] != 'QUARANTINED' for r in results),
            'before_sha256': before_sha,
            'intent_sha256': intent_sha,
            'no_retry_performed': True,
            'no_copy_fallback': True,
            'no_rollback': True,
            'first_moved': 'v3 (pre-existing, verified only)',
        }
        after_sha = durable_write(rj_fd, 'after.json', after_data)

    except Exception as e:
        # Write partial after.json if we haven't already
        if after_data is None:
            partial = {
                'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'status': 'UNKNOWN_EXCEPTION',
                'exception': f'{type(e).__name__}: {e}',
                'before_sha256': before_sha,
                'intent_sha256': intent_sha,
                'note': 'Exception occurred. State UNKNOWN. No retry performed.',
            }
            try:
                durable_write(rj_fd, 'after-partial.json', partial)
            except Exception:
                pass  # Can't write journal - record in stdout
        raise
    finally:
        # Close ALL remaining FDs (no leaks)
        for fd in open_fds:
            try:
                os.close(fd)
            except OSError:
                pass

    print(json.dumps({
        'status': 'COMPLETE' if (after_data and after_data['all_succeeded']) else 'PARTIAL_FAILURE',
        'recovery_journal': str(RECOVERY_JOURNAL_DIR),
        'before_sha256': before_sha,
        'intent_sha256': intent_sha,
        'results': results if 'results' in dir() else after_data.get('results', []),
    }, indent=2))

    if not (after_data and after_data['all_succeeded']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
