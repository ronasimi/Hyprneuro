"""Closed boundary packaging/OPS primitives; importing performs no operation.
Cooperative same-UID/manager scope. File hashes are not loaded-code attestation.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

HOME=Path('/home/ron')
UNITDIR=HOME/'.dotfiles/home/.config/systemd/user'
APP_UNITS=('hyprneuro.service','hyprneuro-ui.service')
HELPER='hyprneuro-pi-identity.service'
SOCKET='hyprneuro-pi-identity.socket'
PYTHON=HOME/'Projects/Hyprneuro/python/.venv/bin/python'
R4=HOME/'Workspace/hn-challenge-714c431-r4-final'
R4_SHA='edf933f46fe96f3572521a143f81f1786a8681b32e7cd9ad376c664c33003a5c'
RECEIPT=HOME/'Workspace/hyprneuro-production-audit/r4-live-ui-process-failure/diagnostic-receipt.json'
RECEIPT_SHA='f069837ef31ac974ff0f5ec27af7294cc27f3e54698ccf3f920de793e93b35a5'
CRITICAL=('Type','Restart','NoNewPrivileges','PrivateTmp','PrivateUsers','Environment','EnvironmentFiles','PassEnvironment','UnsetEnvironment','RuntimeMaxUSec')
STATE=('LoadState','ActiveState','SubState','MainPID','Job','ControlGroup','UnitFileState','FragmentPath','DropInPaths','NeedDaemonReload','Restart')

def canonical(path):
    p=Path(path)
    if not p.is_absolute() or p!=p.resolve() or any(c.isspace() or c in '\\"\'%;' for c in str(p)):
        raise ValueError('Canonical fixed spelling required')
    return p

def file_bytes(path,limit=256*1024*1024):
    p=canonical(path);fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    try:
        a=os.fstat(fd)
        if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or a.st_uid not in (0,os.getuid()) or a.st_mode&0o022 or a.st_size>limit:
            raise ValueError('Unsafe file')
        chunks=[];size=0
        while True:
            chunk=os.read(fd,65536)
            if not chunk:break
            size+=len(chunk)
            if size>limit:raise ValueError('File budget exceeded')
            chunks.append(chunk)
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns,s.st_uid,s.st_gid,s.st_mode,s.st_nlink)
        if identity(a)!=identity(os.fstat(fd)) or identity(a)!=identity(p.lstat()):raise ValueError('File changed during read')
        return b''.join(chunks)
    finally:os.close(fd)

def digest(path):return hashlib.sha256(file_bytes(path)).hexdigest()
def encoded(value):return (json.dumps(value,sort_keys=True,separators=(',',':'))+'\n').encode()
def pin(path):
    p=canonical(path);raw=file_bytes(p);s=p.stat()
    return dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest(),mode=stat.S_IMODE(s.st_mode),uid=s.st_uid)

def check_pin(value):
    if pin(value['path'])!=value:raise ValueError('Exact file pin drift')

def write_new(path,raw,mode=0o400):
    p=canonical(path)
    if isinstance(raw,str):raw=raw.encode()
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode)
    try:
        view=memoryview(raw)
        while view:
            n=os.write(fd,view)
            if n<=0:raise OSError('Incomplete write')
            view=view[n:]
        os.fchmod(fd,mode);os.fsync(fd)
    finally:os.close(fd)

def command(argv,deadline,*,check=True):
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Operation deadline')
    env={**os.environ,'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1000/bus','XDG_RUNTIME_DIR':'/run/user/1000','PYTHONDONTWRITEBYTECODE':'1'}
    return subprocess.run(argv,text=True,capture_output=True,timeout=min(remaining,60),check=check,env=env)

def show(unit,keys,deadline):
    if not unit.endswith(('.service','.socket')) or '/' in unit:raise ValueError('Fixed unit name required')
    args=['/usr/bin/systemctl','--user','show','--all',unit]
    for key in keys:args+=['-p',key]
    raw=command(args,deadline).stdout
    values={}
    for line in raw.splitlines():
        key,value=line.split('=',1)
        if key in values:raise ValueError('Duplicate manager property')
        values[key]=value
    if set(keys)-set(values)=={'EnvironmentFiles'}:
        # systemctl omits this empty structured property even with --all.
        # Verify the actual D-Bus value; omission alone is NOT proof of empty.
        # Keep LoadUnit + property observation on ONE bus connection: inactive
        # services may be GC-unloaded between independent CLI connections.
        code="""import json,sys
from gi.repository import Gio,GLib
c=Gio.DBusConnection.new_for_address_sync('unix:path=/run/user/1000/bus',Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
p=c.call_sync('org.freedesktop.systemd1','/org/freedesktop/systemd1','org.freedesktop.systemd1.Manager','LoadUnit',GLib.Variant('(s)',(sys.argv[1],)),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
r=c.call_sync('org.freedesktop.systemd1',p,'org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.freedesktop.systemd1.Service','EnvironmentFiles')),None,Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
print(json.dumps(r))
"""
        if json.loads(command(['/usr/bin/python','-I','-c',code,unit],deadline).stdout)!=[]:
            raise ValueError('Unrendered nonempty EnvironmentFiles')
        values['EnvironmentFiles']=''
    if set(values)!=set(keys):raise ValueError('Incomplete manager properties')
    return values

def stopped(unit,deadline):
    value=show(unit,STATE,deadline)
    if any(value[k]!=v for k,v in dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',ControlGroup='',NeedDaemonReload='no').items()):
        raise ValueError('Unit not verifiably stopped')
    return value

def destinations():
    # Parent-symlink resolution is explicit; no final symlink aliases accepted.
    if (HOME/'.config/systemd/user').resolve()!=canonical(UNITDIR):raise ValueError('Unexpected systemd-user layout')
    return dict(ui=canonical(HOME/'.local/bin/hyprneuro-ui'),
        broker_drop=UNITDIR/'hyprneuro.service.d/95-reviewed-readonly-release.conf',
        ui_drop=UNITDIR/'hyprneuro-ui.service.d/95-reviewed-readonly-release.conf',
        owner=UNITDIR/'hyprneuro-pi-owner@.service',helper=UNITDIR/HELPER,socket=UNITDIR/SOCKET)

def baseline(deadline):
    """READ ONLY. No SQL connection, mutable audit or production cache writes."""
    if digest(R4/'manifest.json')!=R4_SHA or digest(RECEIPT)!=RECEIPT_SHA:raise ValueError('Stopped-R4 ancestry pin drift')
    old=json.loads(file_bytes(R4/'manifest.json'));receipt=json.loads(file_bytes(RECEIPT))
    context=HOME/'Workspace/hyprneuro-production-audit/challenge-r4-repair/repair-58bdbf4888164557baf1e975040fcf97/continuation-context.json'
    check_pin(dict(pin(context),sha256=receipt['all_seven_core_failed_pins'][str(context)]))
    ctx=json.loads(file_bytes(context));preserved={**receipt['all_seven_core_failed_pins'],**ctx.get('preserved_files',{})}
    for name,sha in preserved.items():
        if digest(Path(name).resolve())!=sha:raise ValueError('Historical/config preservation drift')
    state=json.loads(file_bytes(context.with_name('continuation-state.json')))
    if state['phase']!='failed-apps-stopped' or not state['acceptance_driver_stopped']:raise ValueError('Failure baseline not contained')
    apps={u:stopped(u,deadline) for u in APP_UNITS}
    for unit,v in apps.items():
        expected=old['sidecar' if unit==APP_UNITS[0] else 'ui']
        if v['Restart']!='no' or v['FragmentPath']!=expected['fragment'] or v['DropInPaths'].split()!=expected['dropins']:
            raise ValueError('Effective stopped-R4 unit/override drift')
    for unit in [old['owner_unit'],'lfm@littlemoe.service','lfm@bigmoe.service','lfm@moe.service']:
        stopped(unit,deadline)
    for label in ('list-units','list-unit-files'):
        values=json.loads(command(['/usr/bin/systemctl','--user',label,'--all','--no-pager','--output=json','hyprneuro-pi-owner@*.service'],deadline).stdout)
        for value in values:
            if label=='list-units' and (value.get('active')!='inactive' or value.get('job_id')!=0):raise ValueError('Owner active/unknown')
            if label=='list-unit-files' and value.get('state')!='static':raise ValueError('Owner enabled/unknown')
    targets={}
    installed={**ctx['installed_files'],**{p:v['sha256'] for p,v in ctx['replacement_files'].items()}}
    for role,p in destinations().items():
        if role in ('helper','socket'):
            if p.exists() or p.is_symlink():raise ValueError('New helper/socket path already exists; no ambient adoption')
            for pattern in (p.with_suffix(p.suffix+'.d'),UNITDIR/'sockets.target.wants'/p.name,UNITDIR/'default.target.wants'/p.name):
                if pattern.exists() or pattern.is_symlink():raise ValueError('Unexpected helper enablement/override')
            expected=dict(LoadState='not-found',ActiveState='inactive',Job='',ControlGroup='',UnitFileState='')
            if role=='helper':expected['MainPID']='0'
            loaded=show(p.name,tuple(expected),deadline)
            if loaded!=expected:
                raise ValueError('Unexpected helper/socket manager state')
            targets[role]=None
        else:
            value=pin(p)
            if str(p) not in installed:
                aliases=[k for k in installed if Path(k).resolve()==p]
                if len(aliases)!=1:raise ValueError('Baseline target mapping ambiguous')
                expected=installed[aliases[0]]
            else:expected=installed[str(p)]
            if value['sha256']!=expected:raise ValueError('Installed target baseline drift')
            targets[role]=value
    if digest(HOME/'.config/hyprneuro/settings.json')!=receipt['settings_sha256']:raise ValueError('Settings drift')
    database={}
    for name,expected in receipt['database_metadata_no_SQL'].items():
        p=Path(name)
        if expected is None:
            if p.exists():raise ValueError('Unexpected database companion')
            database[name]=None
        else:
            s=p.lstat();value=dict(size=s.st_size,inode=s.st_ino,sha256=digest(p))
            if value!=expected:raise ValueError('Database file metadata/bytes drift; no SQL probe')
            database[name]=value
    models=validate_models(deadline)
    return dict(schema='hyprneuro.boundary-stopped-baseline/1',r4_manifest=R4_SHA,context=pin(context),
        apps=apps,targets=targets,preserved_files=preserved,database_no_SQL=database,models=models,
        settings=pin(HOME/'.config/hyprneuro/settings.json'),boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())

def replace_target(entry):
    """Atomic guarded file install. Never rolls back uncertainty or prior writes."""
    target=canonical(entry['destination']);source=entry['source'];check_pin(source)
    if target.parent.resolve()!=target.parent:raise ValueError('Destination parent alias')
    parent=target.parent.stat()
    if parent.st_uid!=os.getuid() or parent.st_mode&0o022:raise ValueError('Unsafe destination directory')
    before=entry['before']
    if before is None:
        if target.exists() or target.is_symlink():raise ValueError('New target no longer absent')
    else:
        if before['path']!=str(target):raise ValueError('Target pin mismatch')
        check_pin(before)
    temporary=target.with_name('.'+target.name+'.boundary-'+entry['operation_id'])
    write_new(temporary,file_bytes(source['path']),entry['mode'])
    if before is None:
        os.link(temporary,target,follow_symlinks=False)  # atomic no-replace
        temporary.unlink()
    else:
        check_pin(before)  # immediately before replacement; cooperative-writer scope
        os.replace(temporary,target)
    directory=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_CLOEXEC)
    try:os.fsync(directory)
    finally:os.close(directory)
    if digest(target)!=source['sha256'] or stat.S_IMODE(target.stat().st_mode)!=entry['mode']:raise ValueError('Installed artifact mismatch')

MODEL_SNAPSHOT=Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-model-preservation-03/snapshot.json')
MODEL_SHA='a782093b628f37d55def04d517c237af43a31aafed0cb4983d16951a39b2c08f'
MODEL_AUX=Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-preservation-aux-03/aux.json')
MODEL_AUX_SHA='058a879a91927569040d35279030634ca4fce2a0329ea874f64272765017cf76'

def validate_models(deadline):
    """Fresh preservation comparison ONLY, not new binary or model trust."""
    if digest(MODEL_SNAPSHOT)!=MODEL_SHA or digest(MODEL_AUX)!=MODEL_AUX_SHA:raise ValueError('Proposed model baseline pin drift')
    document=json.loads(file_bytes(MODEL_SNAPSHOT));aux=json.loads(file_bytes(MODEL_AUX))
    if Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=document['boot_id']:raise ValueError('Model baseline boot drift')
    from capture_boundary_model_baseline import identity,listeners,read_fd
    result={}
    for item in document['models']:
        if item['unit'] not in ('lfm@text.service','lfm@omni.service','lfm@decision.service'):raise ValueError('Unknown model selector')
        expected=item['manager_after'];value=show(item['unit'],tuple(expected),deadline)
        if value!=expected:raise ValueError('Effective model configuration drift')
        pid=item['identity_after']['pid'];proc=Path('/proc')/str(pid)
        if identity(pid)!=item['identity_after']:raise ValueError('Model kernel identity drift')
        if hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest()!=item['argv_sha256']:raise ValueError('Model argv drift')
        fd=os.open(proc/'exe',os.O_RDONLY|os.O_CLOEXEC)
        try:raw,metadata=read_fd(fd)
        finally:os.close(fd)
        if hashlib.sha256(raw).hexdigest()!=item['process_executable_fd']['sha256'] or metadata!=item['process_executable_fd']['stat']:
            raise ValueError('Model process executable FD drift')
        check_pin(item['cold_executable'])
        for entry in item['unit_files']:check_pin(entry['source'])
        for selected in item['selected_path_metadata'].values():
            p=Path(selected['canonical']);s=p.stat()
            if (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,stat.S_IMODE(s.st_mode),s.st_uid,s.st_gid)!=(selected['dev'],selected['inode'],selected['size'],selected['mtime_ns'],selected['mode'],selected['uid'],selected['gid']):raise ValueError('Weight metadata drift')
        if listeners(pid)!=item['listeners'] or identity(pid)!=item['identity_after']:raise ValueError('Model listener ownership/identity drift')
        result[item['unit']]=value
    if len(result)!=3:raise ValueError('Incomplete ordinary model baseline')
    for unit,entry in aux['MoEs'].items():
        if unit not in ('lfm@littlemoe.service','lfm@bigmoe.service','lfm@moe.service'):raise ValueError('Unknown MoE selector')
        if stopped(unit,deadline)!=entry['after'] or show(unit,tuple(entry['effective']),deadline)!=entry['effective']:raise ValueError('MoE state/policy drift')
        for file in entry['files']:check_pin(file['source'])
    from capture_boundary_preservation_aux import stream_pin
    for entry in aux['projectors']:
        if stream_pin(Path(entry['pin']['path']),deadline)!=entry['pin']:raise ValueError('Projector drift')
    return result
