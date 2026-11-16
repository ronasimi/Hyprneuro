#!/usr/bin/env python3
"""Capture a NEW PROPOSED preservation-only model baseline; never starts models.
Only three literal unit/PID selectors and loopback metadata GETs. No inference,
model executable invocation, environment dump, SQL, installation or reload.
"""
import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import subprocess
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parent))
import boundary_release as b

MODELS={'lfm@text.service':8081,'lfm@omni.service':8082,'lfm@decision.service':8083}
FIELDS=('ActiveState','SubState','MainPID','Job','ControlGroup','FragmentPath','DropInPaths','ExecStart',
        'NeedDaemonReload','PrivateUsers','PrivateTmp','NoNewPrivileges','Nice','CPUSchedulingPolicy','CPUWeight',
        'MemoryHigh','MemoryMax','MemorySwapMax','MemoryLow','OOMPolicy','OOMScoreAdjust','Restart','Environment','EnvironmentFiles',
        'PassEnvironment','UnsetEnvironment','RestrictAddressFamilies','ProtectSystem','ProtectHome','NetworkNamespacePath',
        'PrivateNetwork','RestrictNamespaces','CapabilityBoundingSet','AmbientCapabilities')

def identity(pid):
    p=Path('/proc')/str(pid)
    return dict(pid=pid,start_ticks=p.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19],
                uid=p.stat().st_uid,cgroup_sha256=hashlib.sha256(p.joinpath('cgroup').read_bytes()).hexdigest())

def no_secrets(raw):
    # Unknown secret-bearing configuration is NOT dumped to an archive/log.
    if re.search(rb'(?:api[-_]?key|password|secret|(?:hf[-_]?|auth[-_]?)token)\s*(?:=|\s)',raw,re.I):
        raise ValueError('Secret-bearing metadata requires separately reviewed redacted capture')

def read_fd(fd):
    first=os.fstat(fd);raw=[];size=0
    while True:
        data=os.read(fd,65536)
        if not data:break
        size+=len(data)
        if size>256*1024*1024:raise ValueError('Executable exceeds capture budget')
        raw.append(data)
    last=os.fstat(fd)
    fields=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_mode,s.st_uid,s.st_gid,s.st_nlink)
    if fields(first)!=fields(last):raise ValueError('Process executable changed during FD read')
    return b''.join(raw),dict(dev=first.st_dev,inode=first.st_ino,size=first.st_size,uid=first.st_uid,gid=first.st_gid,
                             mode=stat.S_IMODE(first.st_mode),nlink=first.st_nlink)

def metadata(port,route,deadline):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Capture deadline')
    connection=http.client.HTTPConnection('127.0.0.1',port,timeout=min(remaining,3))
    try:
        connection.request('GET',route,headers={'Connection':'close'})
        response=connection.getresponse();raw=response.read(65537)
        if len(raw)>65536:raise ValueError('Metadata response oversized')
        value=json.loads(raw)
        if response.status!=200:raise ValueError('Model metadata unavailable')
        if route=='/health':return dict(http_status=response.status,status=value.get('status'))
        return dict(http_status=response.status,models=[dict(id=x.get('id'),object=x.get('object'),owned_by=x.get('owned_by')) for x in value['data']])
    finally:connection.close()

def listeners(pid):
    proc=Path('/proc')/str(pid)
    sockets=set()
    for fd in proc.joinpath('fd').iterdir():
        try:target=os.readlink(fd)
        except FileNotFoundError:continue
        if target.startswith('socket:['):sockets.add(target[8:-1])
    owned=[];moe=[]
    for family in ('tcp','tcp6'):
        for line in proc.joinpath('net',family).read_text().splitlines()[1:]:
            values=line.split()
            if values[3]!='0A':continue
            host,port=values[1].split(':');port=int(port,16)
            if family=='tcp':address=socket.inet_ntop(socket.AF_INET,struct.pack('<I',int(host,16)))
            else:address=socket.inet_ntop(socket.AF_INET6,b''.join(struct.pack('<I',int(host[i:i+8],16)) for i in range(0,32,8)))
            entry=dict(address=address,port=port,inode=values[9],family=family)
            if values[9] in sockets:owned.append(entry)
            if port==8080:moe.append(entry)
    return dict(owned=owned,port8080_in_same_network_namespace=moe)

def selected_files(argv):
    result={}
    for index,arg in enumerate(argv[:-1]):
        if arg not in ('-m','--model','--mmproj','--model-draft'):continue
        p=Path(argv[index+1]);s=p.stat()
        result[arg]=dict(argument=str(p),canonical=str(p.resolve()),dev=s.st_dev,inode=s.st_ino,size=s.st_size,
                         mode=stat.S_IMODE(s.st_mode),uid=s.st_uid,gid=s.st_gid,mtime_ns=s.st_mtime_ns,
                         contents_hashed=False)
    if not any(k in result for k in ('-m','--model')):raise ValueError('No selected model path in actual argv')
    return result

def capture(output,deadline):
    output=b.canonical(output);output.mkdir(mode=0o700)
    for name in ('files','executables'):output.joinpath(name).mkdir(mode=0o700)
    historical=json.loads(b.file_bytes(b.R4/'manifest.json'))
    if b.digest(b.R4/'manifest.json')!=b.R4_SHA:raise ValueError('Historical comparison pin drift')
    records=[];archives={};findings=[]
    def archive(path):
        path=Path(path);canonical=path.resolve();raw=b.file_bytes(canonical);no_secrets(raw)
        source=b.pin(canonical);sha=source['sha256']
        if sha not in archives:
            dest=output/'files'/sha;b.write_new(dest,raw);archives[sha]=b.pin(dest)
        return dict(logical_path=str(path),source=source,archive=archives[sha])
    for unit,port in MODELS.items():
        before=b.show(unit,FIELDS,deadline)
        for key in ('ExecStart','Environment','EnvironmentFiles','PassEnvironment','UnsetEnvironment'):no_secrets(before[key].encode())
        pid=int(before['MainPID']);proc=Path('/proc')/str(pid);first=identity(pid)
        if pid<=1 or before['Job'] or before['ActiveState']!='active' or first['uid']!=os.getuid():raise ValueError('Model unit not stable')
        argv_raw=proc.joinpath('cmdline').read_bytes();no_secrets(argv_raw);argv=argv_raw.rstrip(b'\0').decode().split('\0')
        fd=os.open(proc/'exe',os.O_RDONLY|os.O_CLOEXEC)
        try:raw,fdstat=read_fd(fd)
        finally:os.close(fd)
        running_sha=hashlib.sha256(raw).hexdigest();exepath=os.readlink(proc/'exe')
        artifact=output/'executables'/(running_sha+'.elf')
        if not artifact.exists():b.write_new(artifact,raw)
        cold=None;match=None
        if not exepath.endswith(' (deleted)'):
            cold=b.pin(Path(exepath).resolve());match=cold['sha256']==running_sha
        if match is not True:findings.append(unit+': process-exe FD and disk identity UNKNOWN/mismatch')
        elf=b.command(['/usr/bin/readelf','-n','-d',str(artifact)],deadline).stdout
        build_ids=re.findall(r'Build ID: ([0-9a-f]+)',elf)
        needed=re.findall(r'Shared library: \[([^\]]+)\]',elf)
        mapped=[]
        for line in proc.joinpath('maps').read_text().splitlines():
            fields=line.split(maxsplit=5)
            if len(fields)!=6 or not fields[5].startswith('/'):continue
            path=fields[5]
            if Path(path).name not in needed:continue
            if path in {x['path'] for x in mapped}:continue
            cold_library=None
            if not path.endswith(' (deleted)'):cold_library=b.pin(Path(path).resolve())
            mapped.append(dict(path=path,mapped_dev=fields[3],mapped_inode=fields[4],cold_disk_pin=cold_library,
                               cold_hash_is_not_loaded_mapping_attestation=True))
        config=[archive(before['FragmentPath'])]+[archive(x) for x in before['DropInPaths'].split()]
        config.append(archive(b.HOME/'.bin/lfm'))
        sockets=listeners(pid)
        expected=[x for x in sockets['owned'] if x['port']==port and x['address']=='127.0.0.1']
        if len(expected)!=1 or len(sockets['owned'])!=1 or sockets['port8080_in_same_network_namespace']:
            findings.append(unit+': unexpected or missing listeners')
        health=metadata(port,'/health',deadline);api=metadata(port,'/v1/models',deadline)
        if health['status']!='ok' or len(api['models'])!=1:findings.append(unit+': unexpected API metadata')
        after=b.show(unit,FIELDS,deadline);last=identity(pid)
        if first!=last or before!=after or proc.joinpath('cmdline').read_bytes()!=argv_raw:raise ValueError('Model changed during capture')
        for item in config:b.check_pin(item['source'])
        prior=next(x for x in historical['models'] if x['unit']==unit)
        package=b.command(['/usr/bin/pacman','-Qo',str(Path(exepath).resolve())],deadline,check=False) if cold else None
        records.append(dict(unit=unit,expected_ordinary_port=port,identity_before=first,identity_after=last,manager_before=before,manager_after=after,
            argv=argv,argv_sha256=hashlib.sha256(argv_raw).hexdigest(),selected_path_metadata=selected_files(argv),
            process_executable_fd=dict(sha256=running_sha,stat=fdstat,path_link=exepath,archive=b.pin(artifact)),
            cold_executable=cold,process_fd_bytes_equal_cold_disk=match,ELF_build_ids=build_ids,ELF_needed=needed,
            direct_mapped_libraries=mapped,package_lookup=dict(exit=package.returncode,stdout=package.stdout,stderr=package.stderr) if package else None,
            source_build_provenance='UNKNOWN: ELF notes/package query do not prove source checkout/build recipe',
            namespaces={x:os.readlink(proc/'ns'/x) for x in ('user','mnt','net','pid')},unit_files=config,listeners=sockets,health=health,API_models=api,
            historical_comparison=dict(pid=prior['pid'],start=prior['start'],exe_sha256=prior['exe_sha256'],fragment=prior['fragment'],dropins=prior['dropins']),
            semantic_diff=dict(pid_changed=first['pid']!=prior['pid'],start_changed=first['start_ticks']!=prior['start'],
              cold_exe_sha_changed=cold is None or cold['sha256']!=prior['exe_sha256'],fragment_changed=before['FragmentPath']!=prior['fragment'],
              added_dropins=sorted(set(before['DropInPaths'].split())-set(prior['dropins'])),removed_dropins=sorted(set(prior['dropins'])-set(before['DropInPaths'].split())))))
    moe={unit:b.stopped(unit,deadline) for unit in ('lfm@littlemoe.service','lfm@bigmoe.service','lfm@moe.service')}
    capture_sources=[b.pin(Path(__file__).resolve()),b.pin(Path(b.__file__).resolve())]
    record=dict(schema='hyprneuro.proposed-model-preservation/1',status='PROPOSED_PRESERVATION_ONLY_EXECUTION_BLOCKED',
        independent_standalone_contract_review_required=True,authority='MAIN authorizes capture/preservation proposal only; NOT execution/model trust approval',
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),models=records,MoE_inert=moe,findings=findings,
        capture_sources=capture_sources,scope='Same-UID proc-exe FD snapshot and cold files; NOT loaded/shared-code or same-PID-exec attestation; weight metadata NOT weight bytes',
        production_mutation=False,model_action=False,inference_requests=False,production_SQL=False)
    b.write_new(output/'snapshot.json',b.encoded(record));return b.pin(output/'snapshot.json')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    print(json.dumps(capture(args.output,time.monotonic()+90),sort_keys=True))

if __name__=='__main__':main()
