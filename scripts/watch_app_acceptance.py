#!/usr/bin/python
"""Read-only one-event inotify watcher. Exit wakes parent; NEVER grants consent.

Parent launches outside machine lease via MAIN functions.subagents(action=run);
completion wakes MAIN. After each genuine human gate,
parent starts a new watcher with the returned sequence. No polling, mutation,
model/GUI actions or notifications to invented Durable targets.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import struct
import sys
import time

MANIFEST='44bf0c8d3a41aa402253e5a8548b1b834d1062b0635343c0f271ba854da3a857'
EVENT='acceptance-human-gate.json'


def private_read(path,bound=32768):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_nlink!=1:
            raise PermissionError('Unsafe private event/operation file')
        value=os.read(fd,bound+1)
        if len(value)>bound:raise ValueError('Event byte bound')
        return value
    finally:os.close(fd)


def watch(bundle,after,timeout=7200,expected_manifest=MANIFEST,continuation=None,context_sha256=None):
    deadline=time.monotonic()+timeout
    if type(after) is not int or after<0:raise ValueError('Invalid sequence cursor')
    info=bundle.lstat()
    if bundle!=bundle.resolve() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise PermissionError('Unsafe private event directory')
    if continuation:
        from continuation_context import load_context
        expected_manifest=load_context(bundle,continuation,context_sha256,deadline=deadline)['manifest_sha256']
    raw=private_read(bundle/'manifest.json',1024*1024)
    if hashlib.sha256(raw).hexdigest()!=expected_manifest:raise ValueError('Wrong immutable manifest')
    descriptor=json.loads(raw)['owner_descriptor_sha256']
    event_root=continuation or bundle
    if continuation:
        from continuation_context import load_context
        load_context(bundle,continuation,context_sha256,deadline=deadline)
    libc=ctypes.CDLL(None,use_errno=True)
    fd=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
    if fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
    operation=None
    try:
        # Watch FIRST, then read/recheck state: no check→subscribe lost-wake gap.
        wd=libc.inotify_add_watch(fd,os.fsencode(event_root),0x100|0x80|0x8|0x400|0x800)
        if wd<0:raise OSError(ctypes.get_errno(),'inotify_add_watch')
        while True:
            if continuation:load_context(bundle,continuation,context_sha256,deadline=deadline)
            try:token=hashlib.sha256(private_read(event_root/'operation.started')).hexdigest()
            except FileNotFoundError:token=None
            if operation is not None and token!=operation:raise RuntimeError('Operation changed/disappeared')
            if token is not None:operation=token
            try:data=json.loads(private_read(event_root/EVENT))
            except FileNotFoundError:data=None
            if data is not None:
                if (not isinstance(data,dict) or set(data)!={'version','operation_sha256','seq','kind','prompt','descriptor_sha256'}
                        or type(data['version']) is not int or data['version']!=1
                        or type(data['seq']) is not int or data['seq']<=0
                        or data['kind'] not in ['chooser','consent'] or not isinstance(data['prompt'],str)
                        or not data['prompt'] or len(data['prompt'])>20000
                        or data['descriptor_sha256']!=descriptor or not operation or data['operation_sha256']!=operation):
                    raise ValueError('Malformed/stale operation-bound human event')
                if data['seq']>after:
                    if data['seq']!=after+1:raise RuntimeError('Human event sequence gap; manual review')
                    return dict(status='human-gate-pending-NOT-approval',event=data)
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('No new human event; NOT approval')
            if not select.select([fd],[],[],remaining)[0]:raise TimeoutError('No new human event; NOT approval')
            changes=os.read(fd,65536);offset=0
            while offset<len(changes):
                _,mask,_,length=struct.unpack_from('iIII',changes,offset);offset+=16+length
                if mask&(0x400|0x800|0x4000|0x8000):
                    raise RuntimeError('Event watch disconnected/overflow; manual review')
            # Recheck actual atomic event after EVERY wake, including publication
            # between initial read and blocking select. Unrelated writes confer nothing.
    finally:os.close(fd)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path)
    parser.add_argument('after',type=int);parser.add_argument('--continuation',type=Path);parser.add_argument('--context-sha256')
    args=parser.parse_args()
    print(json.dumps(watch(args.bundle,args.after,continuation=args.continuation,context_sha256=args.context_sha256)),flush=True)
