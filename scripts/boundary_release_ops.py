#!/usr/bin/env python3
"""Frozen future MAIN operations. NOT authorized by proposal generation.
Only reviewed literal operation SHA chooses closed targets. No rollback, old
apply replay, model action, DB/settings write, enable or helper activation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import select
import stat
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parent))
import boundary_release as b


def load(path,literal):
    if len(literal)!=64 or any(c not in '0123456789abcdef' for c in literal) or b.digest(path)!=literal:raise ValueError('External MAIN operation pin required')
    op=json.loads(b.file_bytes(path));bundle=b.canonical(op['bundle'])
    if Path(path)!=bundle/'operation.json' or op['schema']!='hyprneuro.boundary-operation/1':raise ValueError('Closed operation required')
    if set(op['names'])!={'ui','broker','helper','socket','owner'} or op['names']['helper']!=b.HELPER or op['names']['socket']!=b.SOCKET or op['names']['broker']!=b.APP_UNITS[0] or op['names']['ui']!=b.APP_UNITS[1]:raise ValueError('Closed role names required')
    rows=op['targets'];closed=b.destinations()
    if len(rows)!=len(closed) or {r['role']:r['destination'] for r in rows}!={k:str(v) for k,v in closed.items()}:raise ValueError('Closed destination table required')
    if len({r['destination'] for r in rows})!=len(rows):raise ValueError('Duplicate canonical target')
    for value in op['code'].values():b.check_pin(value)
    for row in rows:
        b.check_pin(row['source'])
        if row['backup']:b.check_pin(row['backup'])
    b.check_pin(op['root_record']);b.check_pin(op['manifest']);b.check_pin(op['baseline'])
    if op['root_record']['sha256']!=op['root_sha256']:raise ValueError('Independent root literal mismatch')
    source=bundle/'source'
    for relative,sha in op['managed_source'].items():
        path=b.canonical(source/relative)
        if not path.is_relative_to(source) or b.digest(path)!=sha:raise ValueError('Exact managed source export drift')
    sys.path.insert(0,str(source/'python/src'))
    from hyprneuro.identity_root import load_launch_root
    load_launch_root(op['root_record']['path'],op['root_sha256'],op['generation'])
    return op

def stamp(path):
    from hyprneuro.identity_unit_path import _stamp
    return _stamp(Path(path))

def preserve(op,deadline,full=True,before_start=False):
    baseline=json.loads(b.file_bytes(op['baseline']['path']))
    for logical,sha in baseline['preserved_files'].items():
        if b.digest(Path(logical).resolve())!=sha:raise ValueError('Immutable historical/config preservation drift')
    b.check_pin(baseline['settings'])
    if before_start:
        for name,value in baseline['database_no_SQL'].items():
            p=Path(name)
            if value is None:
                if p.exists():raise ValueError('Database companion appeared before start')
            elif b.digest(p)!=value['sha256'] or p.stat().st_ino!=value['inode'] or p.stat().st_size!=value['size']:
                raise ValueError('Prestart data drift; never roll back postwrites')
    if full:
        b.validate_models(deadline)
        for value in op['runtime'].values():b.check_pin(value)
    else:
        # No model requests or authority renewal. Filesystem/kernel-only monitor.
        snapshot=json.loads(b.file_bytes(b.MODEL_SNAPSHOT))
        from capture_boundary_model_baseline import identity,listeners
        for entry in snapshot['models']:
            pid=entry['identity_after']['pid']
            if identity(pid)!=entry['identity_after'] or listeners(pid)!=entry['listeners']:raise ValueError('Observed model identity/listener drift')
            if b.show(entry['unit'],tuple(entry['manager_after']),deadline)!=entry['manager_after']:raise ValueError('Model effective policy drift')
            for item in entry['unit_files']:b.check_pin(item['source'])
            if {k:os.readlink(Path('/proc')/str(pid)/'ns'/k) for k in entry['namespaces']}!=entry['namespaces']:raise ValueError('Model namespace drift')
        for unit in ('lfm@littlemoe.service','lfm@bigmoe.service','lfm@moe.service'):b.stopped(unit,deadline)


def check_material(op,installed):
    """Root file/schema/hash/alias checks BEFORE reload or any start."""
    from hyprneuro.identity_root import load_launch_root
    from hyprneuro.identity_observer import ObserverPolicy
    from hyprneuro.identity_unit_path import _parents,_location
    root=load_launch_root(op['root_record']['path'],op['root_sha256'],op['generation'])
    manifest=json.loads(root.bootstrap.manifest_bytes);rows={r['destination']:r for r in op['targets']}
    if installed:
        ObserverPolicy(root.bootstrap) # full schema/catalog/namespace/path binding checks; no manager mutation
        for row in rows.values():
            if stamp(row['destination'])!=row['target_identity']:raise ValueError('Installed object identity drift')
            if b.digest(row['destination'])!=row['source']['sha256']:raise ValueError('Installed bytes drift')
    else:
        for role,entries in manifest['unit_path_bindings'].items():
            for entry in entries:
                logical,canonical=_location(entry['logical'],entry['canonical'],manifest['units'][role]['name'])
                if entry['chain']!=[_parents(logical),_parents(canonical)]:raise ValueError('Preinstall alias chain drift')
                row=rows.get(str(canonical));actual=Path(row['install_object']['path']) if row else canonical
                if stamp(actual)!=entry['target']:raise ValueError('Frozen future unit inode drift')
        for path,sha in manifest['files'].items():
            actual=rows[path]['source']['path'] if path in rows else path
            if b.digest(actual)!=sha:raise ValueError('Staged root catalog mismatch')
        for row in rows.values():
            b.check_pin(row['install_object'])
            if stamp(row['install_object']['path'])!=row['target_identity']:raise ValueError('Install object changed')
            if row['before'] is None:
                if Path(row['destination']).exists() or Path(row['destination']).is_symlink():raise ValueError('Expected absent target changed')
            elif b.pin(row['destination'])!=row['before'] or stamp(row['destination'])!=row['before_identity']:raise ValueError('Exact target baseline drift')


def install_one(row):
    """MOVE the pre-pinned inode; keep separate immutable source/backup bytes."""
    source=b.canonical(row['install_object']['path']);target=b.canonical(row['destination'])
    b.check_pin(row['install_object'])
    if stamp(source)!=row['target_identity'] or source.stat().st_dev!=target.parent.stat().st_dev:raise ValueError('Install inode/filesystem drift')
    if row['before'] is None:
        os.link(source,target,follow_symlinks=False) # atomic no-replace, temporary two links
        source.unlink() # final target single-link; a crash before this remains fail-closed
    else:
        b.check_pin(row['before'])
        if stamp(target)!=row['before_identity']:raise ValueError('Target object drift')
        os.replace(source,target)
    directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)
    if stamp(target)!=row['target_identity'] or b.digest(target)!=row['source']['sha256']:raise ValueError('Postwrite target verification failed')


def effective(op,deadline):
    from hyprneuro.identity_observer import ObserverPolicy,read_service
    from hyprneuro.identity_root import load_launch_root
    import asyncio
    root=load_launch_root(op['root_record']['path'],op['root_sha256'],op['generation']);policy=ObserverPolicy(root.bootstrap)
    for role in ('broker','helper','ui','owner'):
        value=b.show(op['names'][role],tuple(op['probe_metadata'][role]['properties']),deadline)
        if value!=op['probe_metadata'][role]['properties']:raise ValueError('Unexpected effective property/override')
        # Owner template expansion/argv is checked at the exact instance, not a fake unit.
        asyncio.run(read_service(policy,role,live=False))
    for role in ('helper','socket'):
        value=b.show(op['names'][role],('UnitFileState','ActiveState','Job','FragmentPath','DropInPaths'),deadline)
        if value['UnitFileState'] not in ('static','disabled') or value['Job'] or value['ActiveState']!='inactive' or value['DropInPaths']:
            raise ValueError('Auxiliary units enabled/active/overridden')
    return policy


def owned_helper(op,deadline):
    unit=op['names']['helper'];value=b.show(unit,('MainPID','Job','ControlGroup','FragmentPath','DropInPaths','ExecStart','InvocationID','ActiveState'),deadline)
    expected=json.loads(b.file_bytes(op['manifest']['path']))['units']['helper']
    if (value['FragmentPath'],*value['DropInPaths'].split())!=tuple(expected['fragments']):raise ValueError('Helper not operation-owned')
    prefix='{ path='+expected['argv'][0]+' ; argv[]='+' '.join(expected['argv'])+' ; ignore_errors=no ; '
    if not value['ExecStart'].startswith(prefix):raise ValueError('Wrong owned helper command')
    pid=int(value['MainPID'])
    if pid==0:
        if value['Job'] or value['ControlGroup'] or value['ActiveState'] not in ('inactive','failed'):raise ValueError('Helper reap UNKNOWN')
        return None
    proc=Path('/proc')/str(pid);start=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]
    if proc.stat().st_uid!=os.getuid() or proc.joinpath('cmdline').read_bytes().rstrip(b'\0').decode().split('\0')!=expected['argv']:
        raise ValueError('Helper PID/start ownership UNKNOWN')
    if proc.joinpath('cgroup').read_text().strip()!='0::'+value['ControlGroup']:raise ValueError('Helper cgroup ownership UNKNOWN')
    fd=os.pidfd_open(pid)
    if proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]!=start:
        os.close(fd);raise ValueError('Helper reused PID')
    return dict(pid=pid,start=start,invocation=value['InvocationID'],pidfd=fd)


def contain(op):
    """Independent app-stop/reap budgets, not an exhausted operation deadline."""
    result=dict(backend_cleanup='NOT_ATTESTED',key_injection_performed=False,owned_key_release_required=False)
    for unit in reversed(b.APP_UNITS):
        try:
            end=time.monotonic()+5;b.command(['/usr/bin/systemctl','--user','stop',unit],end,check=False);b.stopped(unit,end);result[unit]='STOPPED'
        except Exception:result[unit]='UNKNOWN'
    try:
        end=time.monotonic()+6;check_material(op,True)
        helper=owned_helper(op,end)
        # Stop only this operation's exact socket admission definition.
        row=next(r for r in op['targets'] if r['role']=='socket')
        if b.digest(row['destination'])!=row['source']['sha256']:raise ValueError('Socket ownership UNKNOWN')
        b.command(['/usr/bin/systemctl','--user','stop',op['names']['socket']],end,check=False)
        if helper is not None:
            try:
                current=owned_helper(op,end)
                if current is None or (current['pid'],current['start'],current['invocation'])!=(helper['pid'],helper['start'],helper['invocation']):raise ValueError('Helper changed before stop')
                os.close(current['pidfd']);b.command(['/usr/bin/systemctl','--user','stop',op['names']['helper']],end,check=False)
                if not select.select([helper['pidfd']],[],[],max(0,end-time.monotonic()))[0]:raise TimeoutError('Helper reap UNKNOWN')
            finally:os.close(helper['pidfd'])
        b.stopped(op['names']['helper'],end);result['helper_unit']='REAPED_NOT_BACKEND_RECEIPT'
    except Exception:result['helper_unit']='UNKNOWN_NO_FOREIGN_PID_SIGNAL'
    return result


def run(op,literal,phase,deadline):
    bundle=Path(op['bundle']);directory=bundle/'operation'
    if phase=='contain':return contain(op)
    if phase=='install':
        # No old marker is consumed/replayed; every phase is one-shot.
        baseline=b.baseline(deadline)
        if b.encoded(baseline)!=b.file_bytes(op['baseline']['path']):raise ValueError('Fresh stopped baseline differs')
        preserve(op,deadline,before_start=True);check_material(op,False)
        b.write_new(directory/'install.started',literal+'\n')
        for row in op['targets']:
            if time.monotonic()>=deadline:raise TimeoutError('Install deadline')
            install_one(row)
        check_material(op,True) # validates all ROOT BYTES before any reload
        b.command(['/usr/bin/systemctl','--user','daemon-reload'],deadline)
        effective(op,deadline);b.write_new(directory/'install.completed',literal+'\n')
    elif phase=='provision':
        if b.file_bytes(directory/'install.completed')!=(literal+'\n').encode():raise ValueError('Install not confirmed')
        preserve(op,deadline,before_start=True);check_material(op,True);effective(op,deadline)
        b.write_new(directory/'provision.started',literal+'\n')
        guard=Path(op['bundle'])/'source/python/src/hyprneuro/identity_guard.py'
        b.command([str(b.PYTHON),'-I',str(guard),'--record',op['root_record']['path'],'--root-sha256',op['root_sha256'],'--generation',op['generation']],deadline)
        b.write_new(directory/'provision.completed',literal+'\n')
    elif phase=='start':
        if b.file_bytes(directory/'provision.completed')!=(literal+'\n').encode():raise ValueError('Root provisioning not confirmed')
        ready=json.loads(b.file_bytes(directory/'watch.ready'));proc=Path('/proc')/str(ready['pid'])
        if ready['operation_sha256']!=literal or ready['start']!=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19] or proc.stat().st_uid!=os.getuid():raise ValueError('Independent MAIN watcher unavailable')
        preserve(op,deadline,before_start=True);check_material(op,True);effective(op,deadline)
        for unit in b.APP_UNITS:
            if b.stopped(unit,deadline)['Restart']!='no':raise ValueError('BOTH app Restart=no required before EITHER start')
        path=Path('/run/user/1000/hyprharness/grant-control.sock')
        prior_socket=(path.stat().st_dev,path.stat().st_ino) if path.exists() else None
        b.write_new(directory/'start.started',literal+'\n')
        b.command(['/usr/bin/systemctl','--user','start',b.APP_UNITS[0]],deadline)
        # No startup sockets guessed from PID0: exact broker control endpoint.
        while (not path.is_socket() or (path.stat().st_dev,path.stat().st_ino)==prior_socket):
            if time.monotonic()>=deadline:raise TimeoutError('Broker control readiness UNKNOWN')
            time.sleep(.05)
        b.command(['/usr/bin/systemctl','--user','start',b.APP_UNITS[1]],deadline)
        b.write_new(directory/'start.completed',literal+'\n')
    elif phase=='watch':
        check_material(op,True);preserve(op,deadline)
        proc=Path('/proc/self');b.write_new(directory/'watch.ready',b.encoded(dict(operation_sha256=literal,pid=os.getpid(),start=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19])))
        while time.monotonic()<deadline:
            check_material(op,True);preserve(op,deadline,full=False)
            for unit in b.APP_UNITS:
                if b.show(unit,('Restart',),deadline)['Restart']!='no':raise ValueError('App restart policy changed')
            time.sleep(min(1,max(0,deadline-time.monotonic())))
        return contain(op) # bounded window closes; never leave a keepalive job
    else:raise ValueError('Closed phase required')
    return dict(phase=phase,status='COMPLETED_NOT_ACCEPTANCE')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--operation',type=Path,required=True);parser.add_argument('--operation-sha256',required=True)
    parser.add_argument('--phase',choices=('install','provision','start','watch','contain'),required=True);args=parser.parse_args()
    op=None
    try:
        op=load(args.operation,args.operation_sha256)
        result=run(op,args.operation_sha256,args.phase,time.monotonic()+(600 if args.phase=='watch' else 180))
        print(json.dumps(result,sort_keys=True))
    except Exception:
        result=contain(op) if op else {'containment':'NOT_RUN_UNAUTHENTICATED_OPERATION'}
        # Static diagnostics only; uncertain writes/markers retained, no rollback.
        print(json.dumps(dict(status='FAILED_UNCERTAIN_NO_REPLAY',containment=result),sort_keys=True));raise SystemExit(1)
