"""Explicit private post-install attempt binding; never grants permission."""
import hashlib
import json
import os
from pathlib import Path
import stat

MANIFEST='44bf0c8d3a41aa402253e5a8548b1b834d1062b0635343c0f271ba854da3a857'


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_context(bundle,root,expected_sha):
    if not bundle.is_absolute() or bundle!=bundle.resolve():raise PermissionError('Canonical bundle required')
    info=root.lstat()
    if root!=root.resolve() or not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise PermissionError('Private canonical continuation directory required')
    file=root/'continuation-context.json';info=file.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o400 or info.st_size>65536:
        raise PermissionError('Pinned private continuation context required')
    raw=file.read_bytes()
    if not isinstance(expected_sha,str) or len(expected_sha)!=64 or hashlib.sha256(raw).hexdigest()!=expected_sha:
        raise RuntimeError('Approved continuation context digest changed/missing')
    data=json.loads(raw)
    if (type(data['version']) is not int or data['version']!=1 or data['id']!=root.name or data['bundle']!=str(bundle)
            or data['manifest_sha256']!=MANIFEST or digest(bundle/'manifest.json')!=MANIFEST):
        raise ValueError('Wrong continuation identity/bundle')
    if data['entry'] not in data['external_files'] or data['driver'] not in data['external_files']:
        raise ValueError('Unpinned continuation entry/driver')
    for path,sha in data['original_failed_files'].items():
        if digest(path)!=sha:raise RuntimeError('Original failed attempt changed; no replay/repair')
    for path,sha in data['external_files'].items():
        if digest(path)!=sha:raise RuntimeError('Continuation source pin changed')
    from runtime_attestation import validate
    validate(data)
    if digest(file)!=expected_sha:raise RuntimeError('Approved context changed during runtime observation')
    return data


def require_parent(bundle,root,argv,pid,start,expected_sha):
    context=load_context(bundle,root,expected_sha)
    expected=[context['entry'],str(bundle),'--continuation',str(root),'--session']
    if argv[1:6]!=expected:raise RuntimeError('Wrong continuation guard ancestry')
    if '--context-sha256' not in argv or argv[argv.index('--context-sha256')+1]!=expected_sha:
        raise RuntimeError('Parent approved context pin missing/mismatched')
    marker=json.loads((root/'operation.started').read_text())
    if marker!={'id':context['id'],'context_sha256':expected_sha,'pid':pid,'start':start}:
        raise RuntimeError('Wrong live continuation generation')
    return context
