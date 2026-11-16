"""Closed MAIN-reviewed unit-path aliases; not a general path resolver.

Schema3 only. Same-UID/manager cooperative scope, not loaded-code attestation.
"""
from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat

LOGICAL_ROOT=Path('/home/ron/.config/systemd/user')
CANONICAL_ROOT=Path('/home/ron/.dotfiles/home/.config/systemd/user')
SCHEMA='hyprneuro.identity-boundary/3'
FIELDS=('dev','inode','uid','gid','mode','nlink')

def _stamp(path):
    s=path.lstat()
    return dict(dev=s.st_dev,inode=s.st_ino,uid=s.st_uid,gid=s.st_gid,mode=s.st_mode,nlink=s.st_nlink)

def _parents(path):
    result=[]
    for parent in path.parents:
        value=_stamp(parent)
        if value['uid'] not in (0,os.getuid()):raise PermissionError('Unsafe unit parent owner')
        if stat.S_ISLNK(value['mode']):
            if value['uid']!=os.getuid():raise PermissionError('Unsafe unit parent link')
            link=os.readlink(parent)
            if parent!=LOGICAL_ROOT.parent or link!=str(CANONICAL_ROOT.parent):raise PermissionError('Unapproved unit parent link')
        else:
            if not stat.S_ISDIR(value['mode']) or value['mode']&0o022:raise PermissionError('Unsafe unit parent')
            link=None
        result.append(dict(path=str(parent),identity=value,readlink=link))
        if stat.S_ISDIR(value['mode']) and value['uid']==os.getuid() and stat.S_IMODE(value['mode'])==0o700:
            return result
    raise PermissionError('No private unit parent anchor')

def _location(logical,canonical,unit):
    if not isinstance(unit,str) or (unit!='hyprneuro.service' and not re.fullmatch(r'hyprneuro-[A-Za-z0-9_.@\\-]+\.(service|socket)',unit)):
        raise PermissionError('Not a closed Hyprneuro unit')
    # The historical broker spelling is the sole unhyphenated app unit.
    for value in (logical,canonical):
        if not isinstance(value,str) or str(Path(value))!=value or any(c.isspace() for c in value):raise PermissionError('Wrong unit path spelling')
    lp=Path(logical);cp=Path(canonical)
    if not cp.is_relative_to(CANONICAL_ROOT) or cp.resolve()!=cp:raise PermissionError('Wrong canonical unit root')
    roots=[root for root in (LOGICAL_ROOT,CANONICAL_ROOT) if lp.is_relative_to(root)]
    if len(roots)!=1 or lp.relative_to(roots[0])!=cp.relative_to(CANONICAL_ROOT):raise PermissionError('Unapproved logical unit root')
    relative=cp.relative_to(CANONICAL_ROOT);template=unit.split('@',1)[0]+'@.'+unit.rsplit('.',1)[1]
    bases={unit,template} if '@' in unit else {unit}
    if not ((len(relative.parts)==1 and relative.name in bases) or
            (len(relative.parts)==2 and relative.parts[0] in {x+'.d' for x in bases} and re.fullmatch(r'[A-Za-z0-9_.-]+\.conf',relative.name))):
        raise PermissionError('Not this closed unit fragment/drop-in')
    return lp,cp

@dataclass(frozen=True)
class UnitPathBinding:
    logical: str
    canonical: str
    chain_bytes: bytes
    target_bytes: bytes

    @classmethod
    def load(cls,value,unit,catalog):
        from .identity_bootstrap import _json
        import json
        if not isinstance(value,dict) or set(value)!={'logical','canonical','chain','target'}:raise PermissionError('Exact unit binding required')
        lp,cp=_location(value['logical'],value['canonical'],unit)
        if str(cp) not in catalog:raise PermissionError('Uncatalogued unit target')
        # Immutable serialized copies, never caller-retained mutable dicts.
        result=cls(str(lp),str(cp),json.dumps(value['chain'],sort_keys=True).encode(),json.dumps(value['target'],sort_keys=True).encode())
        target=_json(result.target_bytes)
        if set(target)!=set(FIELDS) or any(type(target[k]) is not int for k in FIELDS):raise PermissionError('Exact unit target identity required')
        if not stat.S_ISREG(target['mode']) or target['uid']!=os.getuid() or target['nlink']!=1 or target['mode']&0o022:
            raise PermissionError('Unsafe reviewed unit target')
        result.check()
        return result

    def check(self):
        import json
        lp=Path(self.logical);cp=Path(self.canonical)
        expected=json.loads(self.chain_bytes)
        if [_parents(lp),_parents(cp)]!=expected:raise PermissionError('Unit alias chain changed')
        if lp.resolve()!=cp or _stamp(lp)!=json.loads(self.target_bytes) or _stamp(cp)!=json.loads(self.target_bytes):
            raise PermissionError('Unit target changed')
        if [_parents(lp),_parents(cp)]!=expected:raise PermissionError('Unit alias changed across target observation')

    def read(self,sha256):
        from .identity_observer import read_catalog_file
        self.check()
        result=read_catalog_file(self.canonical,sha256)
        self.check()
        return result
