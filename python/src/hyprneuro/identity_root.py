"""Persistent delivery of MAIN's external literal root; no self-authentication.

MAIN supplies LAUNCHROOTSHA to guard_root. The record serializes CONTEXTSHA;
context -> bootstrap/manifest -> units is unchanged and acyclic. Fixed unit
LoadCredential paths deliver MAIN's literal through the user manager, NOT an
ambient environment variable, manifest/helper claim or current-file hash. The
record/credential source are OUTSIDE the recursive catalog and independently
MAIN-reviewed. Cooperative UID/host-manager scope, not hostile UID defense.
"""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat

from .identity_bootstrap import FilePin, _json, _path, _digest, load_reviewed_bootstrap
from .identity_credentials import read_credentials, require_root_credential

ROOT_SCHEMA='hyprneuro.main-launch-root/1'
CREDENTIAL='main-root-sha'


def _generation(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):
        raise PermissionError('Exact reviewed launch generation required')
    return value


def _identity(s):
    return (s.st_dev,s.st_ino,s.st_uid,s.st_gid,s.st_mode,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def _credential(path):
    """Only fixed manager credential copy; never CREDENTIALS_DIRECTORY lookup."""
    path=_path(str(path))
    parent=path.parent.stat()
    if parent.st_uid!=os.getuid() or stat.S_IMODE(parent.st_mode)!=0o500:
        raise PermissionError('Wrong manager credential directory')
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        first=os.fstat(fd)
        if (not stat.S_ISREG(first.st_mode) or first.st_uid!=os.getuid() or first.st_nlink!=1
                or stat.S_IMODE(first.st_mode)!=0o400 or first.st_size!=65):
            raise PermissionError('Unsafe MAIN credential copy')
        raw=os.read(fd,66)
        last=os.fstat(fd)
        if len(raw)!=65 or raw[-1:]!=b'\n' or _identity(first)!=_identity(last) or _identity(last)!=_identity(path.lstat()):
            raise PermissionError('MAIN credential replaced')
        return _digest(raw[:-1].decode('ascii')),_identity(last)
    finally:
        os.close(fd)


@dataclass(frozen=True)
class LaunchRoot:
    record: FilePin
    record_identity: tuple
    generation: str
    bootstrap: object
    credential_path: object = None
    credential_identity: object = None
    source_identity: object = None

    @property
    def source(self):
        return self.record.path.parent/'MAIN-root.sha256'

    def revalidate(self):
        _,identity=self.record.read(limit=4096)
        if identity!=self.record_identity:
            raise PermissionError('Launch record replaced; no rebaseline')
        self.bootstrap.revalidate()
        if self.credential_path is not None:
            literal,identity=_credential(self.credential_path)
            if literal!=self.record.sha256 or identity!=self.credential_identity:
                raise PermissionError('Manager MAIN credential changed')
            source=FilePin(self.source,hashlib.sha256((literal+'\n').encode()).hexdigest(),os.getuid(),0o400)
            _,identity=source.read(limit=65)  # disk source MUST still match manager copy
            if identity!=self.source_identity:
                raise PermissionError('MAIN credential source replaced')


def load_launch_root(record_path,literal_record_sha256,generation):
    """Literal comes ONLY from MAIN guard input or verified manager delivery."""
    pin=FilePin(_path(str(record_path)),_digest(literal_record_sha256),os.getuid(),0o400)
    raw,identity=pin.read(limit=4096)
    value=_json(raw)
    if (set(value)!={'schema','generation','context_path','context_sha256'} or value['schema']!=ROOT_SCHEMA
            or _generation(value['generation'])!=_generation(generation)):
        raise PermissionError('Wrong launch-root schema/generation')
    bootstrap=load_reviewed_bootstrap(_path(value['context_path']),_digest(value['context_sha256']))
    if str(pin.path) in _json(bootstrap.manifest_bytes)['files']:
        raise PermissionError('Recursive launch-root catalog')
    result=LaunchRoot(pin,identity,generation,bootstrap)
    result.revalidate()
    return result


async def guard_root(record_path,literal_record_sha256,generation):
    """MAIN-only prestart validation and exclusive credential provisioning.

    Does NOT install/start/reload a unit. No existing root, ticket or marker is
    overwritten/deleted. A failed or consumed generation requires fresh review.
    """
    from .identity_observer import ObserverPolicy,read_service
    root=load_launch_root(record_path,literal_record_sha256,generation)
    if (root.record.path.parent/'broker-started.json').exists():
        raise PermissionError('Consumed launch generation')
    policy=ObserverPolicy(root.bootstrap)
    policy.check_namespace()  # guard verifies root ownership OUTSIDE broker NS
    for role in ['broker','helper']:
        state=await read_service(policy,role,live=False)
        if state['pid']!=0:
            raise PermissionError('Existing process; no launch-root adoption')
        require_root_credential(await read_credentials(policy.units[role].name),root.source)
        root.revalidate()
        policy.check_files()
    fd=os.open(root.source,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
    try:
        raw=(root.record.sha256+'\n').encode('ascii')
        if os.write(fd,raw)!=len(raw):raise OSError('Incomplete MAIN root provisioning')
        os.fsync(fd)
    finally:
        os.close(fd)
    directory=os.open(root.source.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)
    root.revalidate()
    return root


async def load_manager_root(record_path,generation,role):
    """Entrypoint-only. Authenticate actual unit/credential before app work.

    No arbitrary credential/PID selector: current kernel PID's manager unit
    determines the fixed credential copy. Exact effective configuration and
    entry argv are then checked against the MAIN-rooted manifest BEFORE use.
    """
    if role not in {'broker','helper'}:raise PermissionError('Closed runtime root role required')
    from .trusted_control import metadata
    from .identity_observer import ObserverPolicy,read_service
    unit=await metadata('/usr/bin/systemctl','--user','whoami',str(os.getpid()))
    if not re.fullmatch(r'[A-Za-z0-9_.@\\-]+\.service',unit):
        raise PermissionError('Runtime not in a manager service')
    record_path=_path(str(record_path))
    require_root_credential(await read_credentials(unit),record_path.parent/'MAIN-root.sha256')
    path=Path('/run/user')/str(os.getuid())/'credentials'/unit/CREDENTIAL
    literal,identity=_credential(path)
    initial=load_launch_root(record_path,literal,generation)
    source=FilePin(record_path.parent/'MAIN-root.sha256',hashlib.sha256((literal+'\n').encode()).hexdigest(),os.getuid(),0o400)
    _,source_identity=source.read(limit=65)
    root=LaunchRoot(initial.record,initial.record_identity,initial.generation,initial.bootstrap,path,identity,source_identity)
    root.revalidate()
    policy=ObserverPolicy(root.bootstrap)
    if policy.units[role].name!=unit:raise PermissionError('Wrong runtime root unit role')
    state=await read_service(policy,role)
    argv=Path('/proc/self/cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
    if state['pid']!=os.getpid() or argv!=list(policy.units[role].argv):
        raise PermissionError('Wrong reviewed runtime entry argv')
    require_root_credential(await read_credentials(unit),root.source)
    root.revalidate()
    policy.check_files()
    policy._launch_root=root  # repeated before operations and after every await
    if role=='broker':
        # One broker startup per independently reviewed root generation. Never
        # delete/rewrite/adopt this marker on failure, boot or service restart.
        import json
        marker=root.record.path.parent/'broker-started.json'
        raw=(json.dumps(dict(generation=generation,root_sha256=literal,invocation=state['invocation']),sort_keys=True)+'\n').encode()
        fd=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o400)
        try:
            if os.write(fd,raw)!=len(raw):raise OSError('Incomplete startup claim')
            os.fsync(fd)
        finally:os.close(fd)
    else:
        broker=await read_service(policy,'broker')
        marker=root.record.path.parent/'broker-started.json'
        # Marker is a negative replay/ownership fence, not a new authority root.
        fd=os.open(marker,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        try:
            s=os.fstat(fd)
            if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.getuid() or s.st_nlink!=1 or stat.S_IMODE(s.st_mode)!=0o400:
                raise PermissionError('Unknown broker startup generation')
            raw=os.read(fd,4097)
            if len(raw)>4096 or _identity(os.fstat(fd))!=_identity(marker.lstat()):raise PermissionError('Broker claim replaced')
        finally:os.close(fd)
        if _json(raw)!=dict(generation=generation,root_sha256=literal,invocation=broker['invocation']):
            raise PermissionError('Broker invocation/root replay')
    root.revalidate()
    return policy
