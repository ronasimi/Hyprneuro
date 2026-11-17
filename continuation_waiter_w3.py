#!/usr/bin/env python3
"""
Continuation waiter W3: Read-only inotify event watcher.
NO machine lease. NO input/services/GUI. Blocking inotify, bounded deadline.

Wakes MAIN on valid START_READY event. Does NOT grant consent.
Lost-wake protection: register watch FIRST, then read state.
"""

import ctypes
import json
import os
import select
import stat
import struct
import sys
import time
from pathlib import Path

# --- Literal pins (passed via argv, verified here) ---

OP_DIR = Path('/home/ron/Workspace/hn-boundary-18aef68-04/operation')
EVENT_FILE = 'continuation.start3.ready'
TIMEOUT = 615  # 600 + 15s startup queue margin

# IN_CREATE | IN_MOVED_TO | IN_MODIFY | IN_CLOSE_WRITE
IN_MASK = 0x100 | 0x80 | 0x2 | 0x8


def private_read(path: Path, bound: int = 32768) -> bytes:
    """Read event file with strict safety checks. Fail-closed."""
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            raise PermissionError('Not a regular file')
        if info.st_uid != os.getuid():
            raise PermissionError('UID mismatch')
        if info.st_mode & 0o077:
            raise PermissionError('Not private mode')
        if info.st_nlink != 1:
            raise PermissionError('Nlink != 1')
        value = os.read(fd, bound + 1)
        if len(value) > bound:
            raise ValueError('Event byte bound exceeded')
        return value
    finally:
        os.close(fd)


def validate_event(raw: bytes, expected_op_sha: str, expected_gen: str, expected_token: str) -> dict:
    """Validate START_READY event content. STRICT schema. Fail-closed."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise ValueError('Event not valid JSON')

    if not isinstance(data, dict):
        raise ValueError('Event not a dict')

    # Required fields (exact set)
    required = {'schema', 'operation_sha256', 'generation', 'run_token', 'uid', 'pid', 'start', 'ts_utc'}
    if set(data.keys()) != required:
        raise ValueError(f'Event schema mismatch: {sorted(data.keys())}')

    if data['schema'] != 'hyprneuro.boundary-start3-ready/1':
        raise ValueError('Wrong schema')
    if data['operation_sha256'] != expected_op_sha:
        raise ValueError('OP SHA mismatch')
    if data['generation'] != expected_gen:
        raise ValueError('Generation mismatch')
    if data['run_token'] != expected_token:
        raise ValueError('Run token mismatch')
    if not isinstance(data['uid'], int):
        raise ValueError('UID not int')
    if not isinstance(data['pid'], int):
        raise ValueError('PID not int')
    if not isinstance(data['start'], str):
        raise ValueError('Start not str')
    if not isinstance(data['ts_utc'], str):
        raise ValueError('ts_utc not str')

    return data


def watch(event_dir: Path, timeout: int, op_sha: str, generation: str, run_token: str) -> dict:
    """Blocking inotify watch. Register FIRST, then read (lost-wake protection)."""
    event_path = event_dir / EVENT_FILE

    # Verify event dir safety
    info = event_dir.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise PermissionError('Unsafe event directory')

    libc = ctypes.CDLL(None, use_errno=True)
    fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'inotify_init1')

    deadline = time.monotonic() + timeout
    try:
        # Register watch FIRST (no check→subscribe lost-wake gap)
        wd = libc.inotify_add_watch(fd, os.fsencode(str(event_dir)), IN_MASK)
        if wd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_add_watch')

        # Then check if event already exists (already-ready case)
        if event_path.exists():
            raw = private_read(event_path)
            data = validate_event(raw, op_sha, generation, run_token)
            return {'status': 'START_READY', 'event': data, 'method': 'pre-existing'}

        # Block on inotify
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return {'status': 'TIMEOUT', 'event': None}

            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                return {'status': 'TIMEOUT', 'event': None}

            # Read inotify events (validate full buffer, advance 16+length)
            changes = os.read(fd, 65536)
            offset = 0
            event_found = False
            buf_len = len(changes)
            while offset < buf_len:
                # Header is 16 bytes: int wd, uint32 mask, uint32 cookie, uint32 len
                if buf_len - offset < 16:
                    raise ValueError('Truncated inotify buffer (header)')
                _wd, mask, _cookie, length = struct.unpack_from('iIII', changes, offset)
                # Validate name length fits in buffer
                if 16 + length > buf_len - offset:
                    raise ValueError('Truncated inotify buffer (name overflow)')
                # Zero-length name is valid (directory-level events)
                offset += 16 + length
                if mask & (0x100 | 0x80):  # IN_CREATE | IN_MOVED_TO
                    event_found = True
                    break

            if not event_found:
                # Check deadline before continuing (no spin)
                if time.monotonic() >= deadline:
                    return {'status': 'TIMEOUT', 'event': None}
                continue

            # Lost-wake protection: re-read after inotify signal
            if event_path.exists():
                raw = private_read(event_path)
                data = validate_event(raw, op_sha, generation, run_token)
                return {'status': 'START_READY', 'event': data, 'method': 'inotify'}
            # Event appeared then disappeared (race) - continue watching
    finally:
        os.close(fd)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--op-sha', required=True)
    parser.add_argument('--generation', required=True)
    parser.add_argument('--run-token', required=True)
    parser.add_argument('--timeout', type=int, default=TIMEOUT)
    parser.add_argument('--event-dir', type=Path, default=OP_DIR)
    args = parser.parse_args()

    result = watch(args.event_dir, args.timeout, args.op_sha, args.generation, args.run_token)
    print(json.dumps(result, sort_keys=True))

    if result['status'] == 'START_READY':
        raise SystemExit(0)
    raise SystemExit(1)


if __name__ == '__main__':
    main()
