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


def broker_identity(unit,deadline):
    value=b.show(unit,('MainPID','ActiveState','SubState','Job','NeedDaemonReload'),deadline)
    if (value['ActiveState'],value['SubState'],value['Job'],value['NeedDaemonReload'])!=('active','running','','no'):
        raise ValueError('Broker state/job/reload invalid')
    pid=int(value['MainPID']);proc=Path('/proc')/str(pid)
    if pid<=0 or proc.stat().st_uid!=os.getuid():raise ValueError('Broker PID/UID invalid')
    return dict(pid=pid,start=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19])

def broker_listener_snapshot(path,pid):
    # Exact f2b03b2 passive listener proof: socket path/type/UID/mode + filesystem
    # inode vs /proc/net/unix STREAM LISTEN FD kernel inode owned by the broker PID.
    try:info=path.lstat()
    except FileNotFoundError:return None
    if path!=path.resolve() or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
        raise ValueError('Broker listener path/type/UID/mode invalid')
    owned=set()
    for fd in (Path('/proc')/str(pid)/'fd').iterdir():
        try:target=os.readlink(fd)
        except FileNotFoundError:continue
        if target.startswith('socket:[') and target.endswith(']'):owned.add(target[8:-1])
    rows=[]
    for line in (Path('/proc')/str(pid)/'net/unix').read_text().splitlines()[1:]:
        row=line.split()
        if len(row)==8 and row[7]==str(path):rows.append(row)
    if len(rows)>1:raise ValueError('Ambiguous broker socket pathname')
    valid=[r for r in rows if r[6] in owned and int(r[3],16)&0x10000 and r[4]=='0001' and r[5]=='01']
    if len(valid)>1:raise ValueError('Ambiguous broker listener')
    if not valid:return None
    return dict(filesystem_device=info.st_dev,filesystem_inode=info.st_ino,kernel_socket_inode=valid[0][6])

def wait_broker_listener(unit,path,deadline):
    expected=broker_identity(unit,deadline)
    while time.monotonic()<deadline:
        if broker_identity(unit,deadline)!=expected:raise ValueError('Broker PID/start replaced')
        snapshot=broker_listener_snapshot(path,expected['pid'])
        if snapshot:
            if broker_identity(unit,deadline)!=expected:raise ValueError('Broker changed during readiness')
            return dict(identity=expected,path=str(path),snapshot=snapshot)
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
    raise TimeoutError('Broker listener readiness deadline; UI NOT started')

def recheck_broker_listener(unit,proof,deadline):
    # Final fresh recheck immediately before UI start (after any intervening await).
    if broker_identity(unit,deadline)!=proof['identity'] or broker_listener_snapshot(Path(proof['path']),proof['identity']['pid'])!=proof['snapshot'] or broker_identity(unit,deadline)!=proof['identity']:
        raise ValueError('Broker listener changed before UI start')

def full_identity(unit,deadline):
    """Full running identity {pid,start,invocation,cgroup} or None when verifiably
    stopped; raises on death/UNKNOWN. ALL four origin fields are required for the
    post-completion receipt comparison (never PID/start alone)."""
    value=b.show(unit,('MainPID','ActiveState','SubState','Job','ControlGroup','NeedDaemonReload','InvocationID'),deadline)
    if value['Job'] or value['NeedDaemonReload']!='no':raise ValueError('App job/reload UNKNOWN')
    pid=int(value['MainPID'])
    if pid==0 and (value['ActiveState'],value['SubState'])==('inactive','dead') and value['ControlGroup']=='':
        return None
    if pid==0 or value['ActiveState']!='active' or value['SubState']!='running':raise ValueError('App death/UNKNOWN state')
    proc=Path('/proc')/str(pid)
    if proc.stat().st_uid!=os.getuid():raise ValueError('App PID UID UNKNOWN')
    start=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]
    if proc.joinpath('cgroup').read_text().strip()!='0::'+value['ControlGroup']:raise ValueError('App cgroup ownership UNKNOWN')
    return dict(pid=pid,start=start,invocation=value['InvocationID'],cgroup=value['ControlGroup'])

def wait_app_active(unit,deadline):
    end=min(deadline,time.monotonic()+5)
    while time.monotonic()<end:
        value=full_identity(unit,deadline)
        if value is not None:return value
        if time.monotonic()>=end:break
        time.sleep(.1)
    raise TimeoutError('App not active after start')

def _lock_deadline(deadline):
    # Per-command bound: never exceed 5s even if the operation deadline is larger.
    return min(deadline,time.monotonic()+5)

def check_session_fields(fields):
    """Pure property validation of structured loginctl show-session output. The
    authoritative unlocked wayland graphical session is: own UID, Active=yes,
    State=active, LockedHint=no, Type=wayland, Remote=no, non-empty Seat. Any
    deviation (locked hint, inactive, foreign UID, remote, missing property) fails
    closed. This is the approved LoginSessionGuard logic - NOT a string table."""
    required=dict(User=str(os.getuid()),Active='yes',State='active',LockedHint='no',Type='wayland',Remote='no')
    for key,expected in required.items():
        if fields.get(key)!=expected:raise ValueError('Session property %s invalid (got %r) -> containment'%(key,fields.get(key)))
    if not fields.get('Seat') or fields.get('Seat')=='-':raise ValueError('Session Seat missing -> containment')
    return fields

def select_display_session(deadline):
    # Select the graphical/Display session for own uid (approved guard logic).
    r=b.command(['/usr/bin/loginctl','show-user',str(os.getuid()),'-p','Display','--value'],_lock_deadline(deadline),check=False)
    if r.returncode!=0:raise ValueError('loginctl show-user Display UNKNOWN -> containment')
    sid=r.stdout.strip()
    if not sid.isdigit():raise ValueError('Display session ID missing/non-numeric -> containment')
    return sid

def verify_session(sid,deadline):
    r=b.command(['/usr/bin/loginctl','show-session',sid,'-p','User','-p','Active','-p','State','-p','LockedHint','-p','Type','-p','Remote','-p','Seat'],_lock_deadline(deadline),check=False)
    if r.returncode!=0:raise ValueError('loginctl show-session UNKNOWN -> containment')
    fields={}
    for line in r.stdout.splitlines():
        if '=' not in line:raise ValueError('loginctl show-session parse fail -> containment')
        key,value=line.split('=',1);fields[key]=value
    return check_session_fields(fields)

def screen_lock_state(directory,deadline):
    """Bounded fresh own-session logind (structured show-session) + independent
    hyprlock classification. Only UNLOCKED is allowed. The Display session ID is
    selected ONCE (pinned to the op dir) before the first mutation and re-verified
    (never re-selected / choose-first) on every recheck. pgrep hyprlock: 0=locking
    -> contain, 1=absent, other=ambiguous -> fail closed. No screen bypass."""
    r=b.command(['/usr/bin/pgrep','-x','hyprlock'],_lock_deadline(deadline),check=False)
    if r.returncode==0:raise ValueError('Screen locker hyprlock RUNNING -> containment')
    if r.returncode!=1:raise ValueError('Screen locker observation ambiguous (pgrep non-0/1) -> fail closed')
    pin=directory/'session.pin'
    if pin.exists():
        sid=b.file_bytes(pin).decode().strip()
    else:
        sid=select_display_session(deadline);b.write_new(pin,sid+'\n')
    verify_session(sid,deadline)
    return 'UNLOCKED'

def validate_start_receipt(receipt,literal,generation):
    """Pure structural validation of the pinned start.completed receipt: exact
    schema, OP/generation binding, both roles present, and all four origin fields
    with exact types. Raises on any deviation (wrong op/partial/invalid)."""
    if not isinstance(receipt,dict) or receipt.get('schema')!='hyprneuro.boundary-start-receipt/1':raise ValueError('Start receipt schema invalid')
    if receipt.get('operation_sha256')!=literal:raise ValueError('Start receipt bound to wrong operation')
    if receipt.get('generation')!=generation:raise ValueError('Start receipt bound to wrong generation')
    for role in ('broker','ui'):
        rec=receipt.get(role)
        if not isinstance(rec,dict):raise ValueError('Start receipt missing role '+role)
        if set(rec)!={'pid','start','invocation','cgroup'}:raise ValueError('Start receipt incomplete role fields '+role)
        if not isinstance(rec['pid'],int) or not isinstance(rec['start'],str) or not isinstance(rec['invocation'],str) or not isinstance(rec['cgroup'],str):
            raise ValueError('Start receipt field type invalid '+role)
    return receipt

def watch_decision(receipt,live,lock,started,completed,transient_started_at,now,transient_budget=200):
    """Core watch-cycle decision (the actual logic, isolated for testing). Returns
    'continue' or raises (-> bounded containment immediately).
      lock: 'UNLOCKED' allowed; any other value -> raise (contain).
      receipt: op/generation-bound validated start.completed dict, or None pre-completion.
      live: {unit: full_identity record or None} observed this cycle.
      started/completed: start.started / start.completed marker presence.
      transient_started_at: monotonic when start.started first observed (or None).
    Post-completion: compare the PINNED receipt to LIVE on ALL four origin fields
    (pid/start/invocation/cgroup); None (clean dead) OR any drift -> contain.
    Pre-completion: STOPPED/transient allowed, but a start that began and never
    completed within the bounded transient window is failed (do not wait the full
    deadline). Never keys off the transient start.started marker for identity."""
    if lock!='UNLOCKED':raise ValueError('Screen lock state not unlocked -> containment')
    if completed:
        if receipt is None:raise ValueError('start.completed present but receipt invalid -> containment')
        for role in ('broker','ui'):
            unit=b.APP_UNITS[0] if role=='broker' else b.APP_UNITS[1]
            live_rec=live.get(unit)
            if live_rec is None:raise ValueError('Role '+role+' verifiably dead post-completion -> containment')
            for field in ('pid','start','invocation','cgroup'):
                if live_rec.get(field)!=receipt[role].get(field):raise ValueError('Role '+role+' field '+field+' drift post-completion -> containment')
        return 'continue'
    if started and transient_started_at is not None and (now-transient_started_at)>transient_budget:
        raise ValueError('Start began but never completed within bounded transient window -> containment')
    return 'continue'

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
        screen_lock_state(directory,deadline) # mandatory after baseline, before first replacement
        b.write_new(directory/'install.started',literal+'\n')
        for row in op['targets']:
            if time.monotonic()>=deadline:raise TimeoutError('Install deadline')
            screen_lock_state(directory,deadline) # safety recheck immediately before each mutation
            install_one(row)
        check_material(op,True) # validates all ROOT BYTES before any reload
        b.command(['/usr/bin/systemctl','--user','daemon-reload'],deadline)
        effective(op,deadline);b.write_new(directory/'install.completed',literal+'\n')
    elif phase=='provision':
        if b.file_bytes(directory/'install.completed')!=(literal+'\n').encode():raise ValueError('Install not confirmed')
        preserve(op,deadline,before_start=True);check_material(op,True);effective(op,deadline)
        screen_lock_state(directory,deadline) # mandatory before provision
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
        screen_lock_state(directory,deadline) # mandatory before start
        path=Path('/run/user/1000/hyprharness/grant-control.sock')
        b.write_new(directory/'start.started',literal+'\n')
        b.command(['/usr/bin/systemctl','--user','start',b.APP_UNITS[0]],deadline)
        # Exact f2b03b2 passive broker listener gate: Type=simple start returns before
        # a later broker reject, so actual listener state is watched, not a socket
        # inode guess. PID/start/state/jobs/reload + socket uid/mode/type + filesystem
        # inode vs /proc/net/unix STREAM LISTEN FD kernel inode owned by the broker.
        proof=wait_broker_listener(b.APP_UNITS[0],path,deadline)
        recheck_broker_listener(b.APP_UNITS[0],proof,deadline)  # immediately before UI start
        b.command(['/usr/bin/systemctl','--user','start',b.APP_UNITS[1]],deadline)
        # start.completed pins the op/generation-bound FULL identity receipt (all four
        # origin fields for BOTH roles); the watcher compares it to LIVE each cycle.
        broker_full=full_identity(b.APP_UNITS[0],deadline)
        ui_full=wait_app_active(b.APP_UNITS[1],deadline)
        if broker_full is None:raise ValueError('Broker not verifiably active at start completion')
        b.write_new(directory/'start.completed',b.encoded(dict(schema='hyprneuro.boundary-start-receipt/1',operation_sha256=literal,generation=op['generation'],broker=broker_full,ui=ui_full)))
    elif phase=='watch':
        # BEFORE any start: the reviewed STOPPED baseline is the expected state (allow,
        # never fail prematurely). The watcher runs OUTSIDE (concurrent, same guarded
        # lease); it writes watch.ready so the start phase can proceed, then monitors.
        # Screen lock is checked fresh BEFORE the first replacement/start and every cycle.
        check_material(op,True);preserve(op,deadline)
        for unit in b.APP_UNITS:b.stopped(unit,deadline)
        screen_lock_state(directory,deadline) # mandatory before watch.ready
        proc=Path('/proc/self');b.write_new(directory/'watch.ready',b.encoded(dict(operation_sha256=literal,pid=os.getpid(),start=proc.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19])))
        transient_started_at=None
        while time.monotonic()<deadline:
            check_material(op,True);preserve(op,deadline,full=False)
            for unit in b.APP_UNITS:
                if b.show(unit,('Restart',),deadline)['Restart']!='no':return contain(op) # policy changed -> bounded containment now
            lock=screen_lock_state(directory,deadline)
            started=(directory/'start.started').exists();completed=(directory/'start.completed').exists()
            if started and transient_started_at is None:transient_started_at=time.monotonic()
            live={};receipt=None
            if completed:
                receipt=validate_start_receipt(json.loads(b.file_bytes(directory/'start.completed')),literal,op['generation'])
                for unit in b.APP_UNITS:live[unit]=full_identity(unit,deadline)
            # Pinned-receipt decision: post-completion compares ALL four origin fields
            # to LIVE (None/dead OR drift -> raise -> immediate containment); pre-start
            # STOPPED/transient allowed; never keyed off the transient start.started.
            watch_decision(receipt,live,lock,started,completed,transient_started_at,time.monotonic())
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
