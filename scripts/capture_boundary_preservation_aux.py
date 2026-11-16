"""New preservation-only supplement; never mutates/refreshed snapshot03."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import boundary_release as b

SNAPSHOT=Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-model-preservation-03/snapshot.json')
SHA='a782093b628f37d55def04d517c237af43a31aafed0cb4983d16951a39b2c08f'
MOES=('lfm@littlemoe.service','lfm@bigmoe.service','lfm@moe.service')

def stream_pin(path,deadline):
    path=b.canonical(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK)
    try:
        first=os.fstat(fd)
        if not stat.S_ISREG(first.st_mode) or first.st_nlink!=1 or first.st_mode&0o022 or first.st_uid!=os.getuid():raise ValueError('Unsafe projector')
        h=hashlib.sha256()
        while True:
            if time.monotonic()>=deadline:raise TimeoutError('Projector deadline')
            chunk=os.read(fd,65536)
            if not chunk:break
            h.update(chunk)
        fields=lambda s:(s.st_dev,s.st_ino,s.st_mode,s.st_uid,s.st_gid,s.st_nlink,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
        if fields(first)!=fields(os.fstat(fd)) or fields(first)!=fields(path.lstat()):raise ValueError('Projector changed')
        return dict(path=str(path),sha256=h.hexdigest(),dev=first.st_dev,inode=first.st_ino,size=first.st_size,
                    mode=stat.S_IMODE(first.st_mode),uid=first.st_uid,gid=first.st_gid,mtime_ns=first.st_mtime_ns)
    finally:os.close(fd)

def capture(output,deadline):
    if b.digest(SNAPSHOT)!=SHA:raise ValueError('Snapshot03 pin changed')
    output=b.canonical(output);output.mkdir(mode=0o700);(output/'files').mkdir(mode=0o700)
    snapshot=json.loads(b.file_bytes(SNAPSHOT));projectors=[]
    for entry in snapshot['models']:
        argv=entry['argv']
        for index,flag in enumerate(argv[:-1]):
            if flag in ('-mm','--mmproj'):
                path=Path(argv[index+1])
                profile={'lfm@omni.service':'omni','lfm@decision.service':'decision'}.get(entry['unit'])
                if profile is None or path.parent!=b.HOME/'.models'/profile:raise ValueError('Unexpected projector scope')
                projectors.append(dict(unit=entry['unit'],argv_flag=flag,pin=stream_pin(path,deadline),scope='actual file bytes; NOT loaded projector/mapping attestation'))
    moes={}
    for unit in MOES:
        before=b.stopped(unit,deadline)
        effective=b.show(unit,('PrivateTmp','PrivateUsers','PrivateNetwork','NoNewPrivileges','Nice','CPUSchedulingPolicy','CPUWeight',
            'MemoryHigh','MemoryMax','MemorySwapMax','OOMPolicy','OOMScoreAdjust','Environment','EnvironmentFiles','ExecStart'),deadline)
        files=[]
        for logical in [before['FragmentPath'],*before['DropInPaths'].split()]:
            source=b.pin(Path(logical).resolve());archive=output/'files'/source['sha256']
            if not archive.exists():b.write_new(archive,b.file_bytes(source['path']))
            files.append(dict(logical=logical,source=source,archive=b.pin(archive)))
        after=b.stopped(unit,deadline)
        if before!=after:raise ValueError('MoE metadata drift')
        for item in files:b.check_pin(item['source'])
        moes[unit]=dict(before=before,after=after,effective=effective,files=files)
    result=dict(schema='hyprneuro.boundary-preservation-aux/1',status='PROPOSED_COMPARISON_ONLY_EXECUTION_BLOCKED',
        snapshot=dict(path=str(SNAPSHOT),sha256=SHA),projectors=projectors,MoEs=moes,
        qualifications=['No original snapshot rewritten','ordinary shared20-host.conf is NOT MoE policy: per-instance basename override applies',
          'weights remain stat-only; cold six library files NOT fourteen dependency mappings','source/build provenance UNKNOWN',
          'no egress/server-behavior/private-input-use guarantee','No model requests, inference, model invocation, reconfiguration or SQL'],
        capture_source=b.pin(Path(__file__).resolve()))
    b.write_new(output/'aux.json',b.encoded(result));return b.pin(output/'aux.json')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(capture(args.output,time.monotonic()+90),sort_keys=True))
