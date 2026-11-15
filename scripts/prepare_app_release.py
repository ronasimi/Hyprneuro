#!/usr/bin/env python3
"""Stage a committed app-only release and private rollback; NEVER start/apply it."""
import argparse
from contextlib import closing
import hashlib
import json
import os
import re
import secrets
import socket
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess
import tarfile
import time


def run(*args, deadline=None, **kw):
    from command_budget import timeout
    kw['timeout']=timeout(deadline,kw.get('timeout',5))
    return subprocess.check_output(args, text=True, **kw).strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_file(path):
    p = Path(path)
    st = p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1:
        raise RuntimeError('Unsafe regular file: ' + str(p))
    return p


MOE_UNITS = ('lfm@littlemoe.service', 'lfm@bigmoe.service', 'lfm@moe.service')


def check_moe_inert(deadline=None):
    for unit in MOE_UNITS:
        fields = dict(line.split('=', 1) for line in run('systemctl','--user','show',unit,
            '-p','ActiveState','-p','SubState','-p','MainPID','-p','Job','-p','NeedDaemonReload',timeout=5,deadline=deadline).splitlines())
        if fields != dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',NeedDaemonReload='no'):
            raise RuntimeError('MoE profile active/pending/unknown: '+unit)


def check_owner_inert(template, previous_instance,deadline=None):
    """Read-only global gate: no enabled template/instances, jobs or live owners."""
    pattern='hyprneuro-pi-owner@*.service'
    try:
        files=json.loads(run('systemctl','--user','list-unit-files','--no-pager','--output=json',pattern,timeout=10,deadline=deadline))
        loaded=json.loads(run('systemctl','--user','list-units','--all','--no-pager','--output=json',pattern,timeout=10,deadline=deadline))
        if (not isinstance(files,list) or len(files)!=1 or not isinstance(files[0],dict) or
                files[0].get('unit_file')!=template.name or files[0].get('state')!='static'):
            raise ValueError('Owner template/instance enabled or unknown')
        if not isinstance(loaded,list):raise ValueError('Unknown owner enumeration')
        instances={previous_instance}
        for item in loaded:
            name=item['unit']
            if not re.fullmatch(r'hyprneuro-pi-owner@.+\.service',name) or item['load']!='loaded' or item['active']!='inactive' or item['sub']!='dead' or item['job_id']!=0:
                raise ValueError('Active/unknown owner instance or pending job')
            instances.add(name)
        for name in sorted(instances):
            fields=dict(line.split('=',1) for line in run('systemctl','--user','show',name,
                '-p','LoadState','-p','ActiveState','-p','SubState','-p','MainPID','-p','UnitFileState',
                '-p','FragmentPath','-p','DropInPaths','-p','NeedDaemonReload','-p','Job',timeout=10,deadline=deadline).splitlines())
            fields['FragmentPath']=str(private_file(fields['FragmentPath']).resolve())
            if fields!={'LoadState':'loaded','ActiveState':'inactive','SubState':'dead','MainPID':'0',
                        'UnitFileState':'static','FragmentPath':str(template.resolve()),'DropInPaths':'','NeedDaemonReload':'no','Job':''}:
                raise ValueError('Owner instance not inert/exact')
    except (OSError,RuntimeError,ValueError,KeyError,IndexError,TypeError,subprocess.SubprocessError) as error:
        raise RuntimeError('Owner template/instances not verifiably inert; no cutover') from error


def check_owner_baseline(template, entry,deadline=None):
    """A previous exact applied manifest pins ownership; never adopt ambient units."""
    try:
        previous=Path(entry['previous_bundle'])
        st=previous.lstat()
        if (not previous.is_absolute() or previous!=previous.resolve() or not stat.S_ISDIR(st.st_mode) or
                st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o700):
            raise ValueError('Private canonical previous release required')
        private_file(previous/'apply.completed')
        manifest=private_file(previous/'manifest.json')
        old=json.loads(manifest.read_text())
        file=private_file(template)
        if (entry['path']!=str(file.resolve()) or entry['role']!='owner-template' or
                stat.S_IMODE(file.stat().st_mode)!=entry['mode'] or entry['mode'] not in (0o400,0o600) or
                digest(manifest)!=entry['previous_manifest_sha256'] or old.get('persistent_owner') is not True or
                old['staged_files'][template.name]!=entry['sha256'] or digest(file)!=entry['sha256'] or
                not re.fullmatch(r'hyprneuro-pi-owner@.+\.service',old['owner_unit'])):
            raise ValueError('Unreviewed owner template/mode or previous manifest drift')
        check_owner_inert(template,old['owner_unit'],deadline=deadline)
    except (OSError,ValueError,KeyError,TypeError) as error:
        raise RuntimeError('Owner template baseline missing, unsafe or changed; no adoption/cutover') from error


def backup_owner_template(template, backup, index, previous, previous_sha):
    if not template.exists() and not template.is_symlink():
        if previous is not None or previous_sha is not None:
            raise RuntimeError('Previously reviewed owner template missing; no cutover')
        return None
    if previous is None or previous_sha is None:
        raise RuntimeError('Existing owner template requires exact previous applied manifest pin')
    file=private_file(template)
    entry=dict(path=str(file.resolve()),role='owner-template',sha256=digest(file),
        mode=stat.S_IMODE(file.stat().st_mode),previous_bundle=str(previous),previous_manifest_sha256=previous_sha,
        backup=str(backup/(str(index)+'-'+template.name)))
    check_owner_baseline(template,entry)
    with Path(entry['backup']).open('xb') as stream:stream.write(file.read_bytes())
    Path(entry['backup']).chmod(0o600)
    if digest(entry['backup'])!=entry['sha256']:raise RuntimeError('Owner template backup changed')
    check_owner_baseline(template,entry)
    return entry


def unit_identity(name,deadline=None):
    fields = dict(line.split('=', 1) for line in run('systemctl', '--user', 'show', name,
        '-p', 'MainPID', '-p', 'ActiveState', '-p', 'FragmentPath', '-p', 'DropInPaths',deadline=deadline).splitlines())
    pid = int(fields['MainPID'])
    if not pid or fields['ActiveState'] != 'active':
        raise RuntimeError('Expected active unit: ' + name)
    proc = Path('/proc') / str(pid)
    if proc.stat().st_uid != os.getuid():
        raise RuntimeError('Wrong process UID')
    # Type=simple may report MainPID before exec finishes; proc/exe can be
    # temporarily unreadable. Retry metadata only, never restart/replay a unit.
    for attempt in range(50):
        try:
            return dict(unit=name, pid=pid, start=proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
                exe=str(proc.joinpath('exe').resolve()), exe_sha256=digest(proc/'exe'),
                fragment=fields['FragmentPath'], dropins=fields['DropInPaths'].split())
        except PermissionError:
            if attempt == 49:
                raise
            time.sleep(.02)


def prepare_parent_owner(source, owner, python, staged):
    """Stage the reviewed persistent descriptor/unit only; no start or grant."""
    env = {**os.environ, 'PYTHONPATH': str(source/'python/src'), 'PYTHONDONTWRITEBYTECODE': '1'}
    subprocess.run([str(python), '-m', 'hyprneuro.pi_owner_service', str(owner), '--prepare',
        '--source', str(source), '--node', '/usr/bin/node',
        '--sdk', '/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js',
        '--durable', '/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents',
        '--pi', '/home/ron/.pi/agent/bin/pi', '--read-path', 'fixture.txt',
        '--python', str(python), '--unit-output', str(staged/'hyprneuro-pi-owner@.service')],
        env=env, check=True)
    return json.loads(private_file(owner/'owner.json').read_text())['task_id']



def copy_database_snapshot(bundle, manifest_sha, production_path, destination):
    """Copy a pinned ALREADY PREPARED backup; never open production SQLite."""
    manifest = private_file(bundle/'manifest.json')
    if digest(manifest) != manifest_sha: raise RuntimeError('Snapshot manifest changed')
    data = json.loads(manifest.read_text())['database']
    snapshot = private_file(data['backup'])
    if data['path'] != str(production_path) or digest(snapshot) != data['backup_sha256']:
        raise RuntimeError('Snapshot identity changed')
    with destination.open('xb') as file: file.write(snapshot.read_bytes())
    return dict(bundle=str(bundle),manifest_sha256=manifest_sha,sha256=data['backup_sha256'],
                current_database_read=False,not_current_database_attestation=True)


def prepare_trusted_launch(source, python, binary, staged, runtime):
    """Stage only fixed launch material; no server, consent, database or unit calls."""
    entry = staged/'pi-desktop-entry.py'
    body = ("import pathlib,sys\n"
            "source=pathlib.Path(__file__).resolve().parents[1]/'source/python/src'\n"
            "sys.path.insert(0,str(source))\n"
            "from hyprneuro.pi_desktop_bridge import main\n"
            "raise SystemExit(main())\n")
    # Exclusive creation: never patch an existing release entry or policy.
    with entry.open('x') as file:
        file.write(body)
    entry.chmod(0o500)
    policy = staged/'trusted-launch.json'
    data = dict(schema='hyprneuro.trusted-launch/1', python=str(python),entry=str(entry),
                source=str(source),ui_sha256=digest(binary),entry_sha256=digest(entry))
    with policy.open('x') as file:
        json.dump(data,file,sort_keys=True,separators=(',', ':'));file.write('\n')
    policy.chmod(0o400)
    def quoted(value):
        return str(value).replace('\\','\\\\').replace('"','\\"').replace('%','%%')
    return ('Environment="HYPRNEURO_PI_TRUSTED_POLICY='+quoted(policy)+'" '
            '"HYPRNEURO_PI_TRUSTED_POLICY_SHA256='+digest(policy)+'" '
            '"HYPRNEURO_PI_BROKER_SOCKET='+quoted(Path(runtime)/'hyprharness/grant-control.sock')+'"\n')


def ui_dropin(common, mode):
    # Explicit ordering prevents graphical-session.target's implicit After=UI
    # from closing a cycle through UI -> sidecar -> graphical-session.target.
    return '[Unit]\nAfter=graphical-session.target\n[Service]\n' + common + mode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--previous-bundle', type=Path, help='Exact previously reviewed/applied owner-template release')
    parser.add_argument('--previous-manifest-sha256', help='Pinned reviewed previous manifest SHA256; never ambient adoption')
    parser.add_argument('--database-snapshot-bundle',type=Path,help='Use existing pinned preparation backup; no production DB open')
    parser.add_argument('--database-snapshot-manifest-sha256')
    args = parser.parse_args()
    if bool(args.database_snapshot_bundle) != bool(args.database_snapshot_manifest_sha256):
        parser.error('Both database snapshot pins required')
    repo = Path(__file__).resolve().parents[1]
    commit = run('git', '-C', str(repo), 'rev-parse', args.commit + '^{commit}')
    dest = args.output
    if not dest.is_absolute() or dest.exists() or str(dest) != str(dest.resolve()) or not re.fullmatch(r'[A-Za-z0-9_./-]+',str(dest)):
        raise RuntimeError('New canonical absolute output directory required')
    if int(next(line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))<1024*1024:
        raise RuntimeError('Less than1GiB available; do not build or launch')
    os.umask(0o077)
    dest.mkdir(mode=0o700)
    source, build, backup, staged = [dest/p for p in ('source', 'build', 'backup', 'staged')]
    for p in (source, backup, staged):
        p.mkdir(mode=0o700)
    archive = dest/'source.tar'
    with archive.open('wb') as stream:
        subprocess.run(['git','-C',str(repo),'archive',commit],stdout=stream,check=True)
    with tarfile.open(archive) as stream:
        stream.extractall(source, filter='data')
    archive.unlink()
    python = Path('/home/ron/Projects/Hyprneuro/python/.venv/bin/python')
    ui = unit_identity('hyprneuro-ui.service')
    sidecar = unit_identity('hyprneuro.service')
    models=[unit_identity('lfm@'+role+'.service') for role in ('text','omni','decision')]
    check_moe_inert()
    installed = private_file(Path.home()/'.local/bin/hyprneuro-ui')
    if digest(installed) != ui['exe_sha256']:
        raise RuntimeError('Installed UI differs from running UI; do not preserve stale rollback')
    shutil.copyfile('/proc/'+str(ui['pid'])+'/exe', backup/'hyprneuro-ui')
    (backup/'hyprneuro-ui').chmod(0o500)
    assert digest(backup/'hyprneuro-ui')==ui['exe_sha256']
    units = []
    for identity in (ui, sidecar):
        for name in [identity['fragment'], *identity['dropins']]:
            file = private_file(name)
            target = backup/(str(len(units))+'-'+file.name)
            shutil.copyfile(file,target)
            units.append(dict(path=name, backup=str(target), sha256=digest(file), mode=stat.S_IMODE(file.stat().st_mode)))
    owner_baseline=backup_owner_template(Path.home()/'.config/systemd/user/hyprneuro-pi-owner@.service',
        backup,len(units),args.previous_bundle,args.previous_manifest_sha256)
    if owner_baseline:units.append(owner_baseline)
    # Only named path metadata is retained. No ambient credentials or env dump.
    env = dict(x.split(b'=',1) for x in Path('/proc',str(sidecar['pid']),'environ').read_bytes().split(b'\0') if b'=' in x)
    home = env[b'HOME'].decode()
    state = env.get(b'XDG_STATE_HOME', (home+'/.local/state').encode()).decode()
    config = env.get(b'XDG_CONFIG_HOME', (home+'/.config').encode()).decode()
    runtime = env[b'XDG_RUNTIME_DIR'].decode()
    db = private_file(Path(state)/'hyprharness/sidecar/observations.sqlite3')
    deadline = time.monotonic()+20
    def progress(*_):
        if time.monotonic()>deadline:
            raise TimeoutError('SQLite backup deadline; do not apply')
    snapshot_provenance = None
    if args.database_snapshot_bundle:
        snapshot_provenance = copy_database_snapshot(args.database_snapshot_bundle,
            args.database_snapshot_manifest_sha256,db,backup/'observations.sqlite3')
        with closing(sqlite3.connect((backup/'observations.sqlite3').as_uri()+'?mode=ro',uri=True)) as check:
            if check.execute('PRAGMA quick_check').fetchall() != [('ok',)]: raise RuntimeError('Snapshot integrity failure')
    else:
        with closing(sqlite3.connect(db.as_uri()+'?mode=ro',uri=True,timeout=5)) as src, closing(sqlite3.connect(backup/'observations.sqlite3')) as dst:
            src.backup(dst,pages=256,progress=progress,sleep=.02)
            if dst.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
                raise RuntimeError('Backup integrity failure')
    settings = Path(config)/'hyprneuro/settings.json'
    settings_receipt = None
    if settings.exists():
        private_file(settings)
        shutil.copyfile(settings,backup/'settings.json')
        settings_receipt=dict(path=str(settings),sha256=digest(settings))
        assert digest(backup/'settings.json')==settings_receipt['sha256']
    subprocess.run(['meson','setup',str(build),str(source/'ui')],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['meson','compile','-C',str(build)],check=True,stdout=subprocess.DEVNULL)
    subprocess.run(['meson','test','-C',str(build),'--print-errorlogs'],check=True,stdout=subprocess.DEVNULL)
    env_probe={**os.environ,'PYTHONPATH':str(source/'python/src'),'PYTHONDONTWRITEBYTECODE':'1'}
    probe="""import importlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); names=['hyprneuro','hyprneuro.agent','hyprneuro.models','hyprneuro.sidecar','hyprneuro.pi_desktop_bridge']
files={n:str(pathlib.Path(importlib.import_module(n).__file__).resolve()) for n in names}
assert all(pathlib.Path(p).is_relative_to(root) for p in files.values())
print(json.dumps({'executable':sys.executable,'modules':files}))"""
    origins=json.loads(run(str(python),'-c',probe,str(source/'python/src'),env=env_probe))
    bin_dir=dest/'bin';bin_dir.mkdir(mode=0o700)
    shutil.copyfile(build/'hyprneuro-ui',bin_dir/'hyprneuro-ui');(bin_dir/'hyprneuro-ui').chmod(0o500)
    # New synthetic fixture only. Descriptor preparation grants no permission.
    explicit_ui=(source/'python/src/hyprneuro/pi_managed_bridge.py').is_file()
    owner=dest/'owner'; workspace=owner/'home/workspace'
    if explicit_ui:
        task=prepare_parent_owner(source,owner,python,staged)
    else:
        workspace.mkdir(parents=True,mode=0o700)
        task='hn-ro-'+secrets.token_hex(12)
    (workspace/'fixture.txt').write_text('MAPLE_READ_ONLY_FIXTURE\n')
    if len(str(workspace))>128:
        raise RuntimeError('Workspace exceeds broker file-prefix bound')
    # Read-only collision check, never authorization or consent.
    broker_path=Path(runtime)/'hyprharness/sidecar.sock'
    if broker_path.stat().st_uid!=os.getuid():
        raise RuntimeError('Wrong broker UID')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5);client.connect(str(broker_path))
        client.sendall((json.dumps(dict(action='auth_check',task_id=task,op='read',app_id='hyprneuro-parent-read' if explicit_ui else 'hn-ro-parent-fixture',path=str(workspace/'fixture.txt')))+'\n').encode())
        packet=bytearray()
        while b'\n' not in packet:
            chunk=client.recv(4096)
            if not chunk or len(packet)+len(chunk)>65536:raise RuntimeError('Bounded broker response required')
            packet.extend(chunk)
        result=json.loads(packet.split(b'\n')[0])
        if result!={'ok':True,'result':{'allowed':False,'reason':'no_authorization'}}:
            raise RuntimeError('Task collision or incompatible broker; do not launch')
    common=f'Environment="PYTHONPATH={source}/python/src" "PYTHONDONTWRITEBYTECODE=1" "HOME={home}" "XDG_STATE_HOME={state}" "XDG_CONFIG_HOME={config}" "XDG_RUNTIME_DIR={runtime}"\nUnsetEnvironment=HYPRNEURO_RESIDENCY_DIR\n'
    if (source/'python/src/hyprneuro/trusted_control.py').is_file():
        common += prepare_trusted_launch(source,python,bin_dir/'hyprneuro-ui',staged,runtime)
    entry = '''import importlib,json,os,pathlib,sys
source=pathlib.Path(__file__).resolve().parents[1]/'source/python/src'
names=['hyprneuro','hyprneuro.agent','hyprneuro.models','hyprneuro.sidecar','hyprneuro.pi_desktop_bridge']
files={n:str(pathlib.Path(importlib.import_module(n).__file__).resolve()) for n in names}
assert all(pathlib.Path(p).is_relative_to(source) for p in files.values())
p=pathlib.Path(__file__).resolve().parents[1]/'sidecar-origin.json'
tmp=p.with_suffix('.tmp')
with tmp.open('x') as f:
    json.dump(dict(pid=os.getpid(),executable=sys.executable,modules=files),f);f.flush();os.fsync(f.fileno())
os.replace(tmp,p)
from hyprneuro.sidecar import main
main()
'''
    (staged/'sidecar-entry.py').write_text(entry);(staged/'sidecar-entry.py').chmod(0o500)
    (staged/'sidecar.conf').write_text('[Service]\nWorkingDirectory='+str(source/'python')+'\n'+common+
        'ExecStart=\nExecStart='+str(python)+' '+str(staged/'sidecar-entry.py')+' serve --allow-ingest --watch-hyprland --assistant-enabled --no-allow-capture --no-allow-on-demand --no-allow-browser --no-d1-visual --no-retention-enabled\n')
    ui_mode=(f'Environment="HYPRNEURO_PI_UI=0" "HYPRNEURO_PI_BRIDGE_PYTHON={python}"\nUnsetEnvironment=HYPRNEURO_PI_OWNER_DIR\n' if explicit_ui else
        f'Environment="HYPRNEURO_PI_UI=1" "HYPRNEURO_PI_OWNER_DIR={owner}" "HYPRNEURO_PI_BRIDGE_PYTHON={python}"\n')
    (staged/'ui.conf').write_text(ui_dropin(common,ui_mode))
    launch=f'''#!/bin/sh
set -eu
# Parent must first approve review, machine lease, source deployment and fresh
# unlocked GUI window. Never answer a consent or retry an uncertain owner.
[ "$#" = 1 ] && [ "$1" = --parent-authorized-start ] || {{ echo 'BLOCKED: explicit parent start relay required' >&2; exit 2; }}
exec env -i PATH=/usr/bin:/bin LANG=C.UTF-8 HOME='{owner}/home' XDG_RUNTIME_DIR='{runtime}' \\
 HYPRNEURO_PI_OWNER_ENABLE=1 HYPRNEURO_PI_OWNER_PROFILE=read-only HYPRNEURO_PI_OWNER_MODE=normal-only \\
 HYPRNEURO_PI_PARENT_ONLY=1 HYPRNEURO_PI_CHILD_READ=0 HYPRNEURO_PI_READ_PATHS='["fixture.txt"]' \\
 HYPRNEURO_PI_OWNER_DIR='{owner}' HYPRNEURO_WORKSPACE='{workspace}' \\
 HYPRNEURO_TASK_ID={task} HYPRNEURO_APP_ID=hn-ro-parent-fixture \\
 HYPRNEURO_PI_SDK=/home/ron/.pi/agent/install/releases/1.5.1/node_modules/@earendil-works/pi-coding-agent/dist/index.js \\
 HYPRNEURO_DURABLE_PACKAGE=/home/ron/.pi/agent/npm/node_modules/pi-durable-subagents \\
 HYPRNEURO_PI_BIN=/home/ron/.pi/agent/bin/pi /usr/bin/node '{source}/extensions/pi-owner/host.mjs'
'''
    if not explicit_ui:
        (staged/'start-owner.sh').write_text(launch);(staged/'start-owner.sh').chmod(0o500)
    for identity in (ui,sidecar,*models):
        assert unit_identity(identity['unit'])==identity, 'Running identity changed during preparation'
    check_moe_inert()
    for name in ['prepare_app_release.py','verify_app_release.py','apply_app_release.py','guard_app_release.py','wait_app_acceptance.py']:
        shutil.copyfile(repo/'scripts'/name,staged/name);(staged/name).chmod(0o500)
    # Freeze exported payload; Python runtime must never create cache files here.
    for p in source.rglob('*'):
        if p.is_symlink():
            raise RuntimeError('Unexpected release symlink')
        p.chmod(0o500 if p.is_dir() or p.stat().st_mode&0o111 else 0o400)
    source.chmod(0o500)
    manifest=dict(explicit_ui=explicit_ui,persistent_owner=explicit_ui,commit=commit,prepared_only=True,ui=ui,sidecar=sidecar,models=models,units=units,owner_template_baseline=owner_baseline,
        python=str(python),import_origins=origins,installed_ui=str(installed),installed_mode=stat.S_IMODE(installed.stat().st_mode),
        installed_sha256=digest(installed),binary=str(bin_dir/'hyprneuro-ui'),binary_sha256=digest(bin_dir/'hyprneuro-ui'),
        database=dict(path=str(db),backup=str(backup/'observations.sqlite3'),backup_sha256=digest(backup/'observations.sqlite3'),quick_check='ok',snapshot_provenance=snapshot_provenance),
        editable_metadata=dict(path='/home/ron/Projects/Hyprneuro/python/.venv/lib/python3.13/site-packages/__editable__.hyprneuro-0.1.0.pth',sha256=digest('/home/ron/Projects/Hyprneuro/python/.venv/lib/python3.13/site-packages/__editable__.hyprneuro-0.1.0.pth')),
        settings=settings_receipt,task=task,owner=str(owner),workspace=str(workspace),runtime=runtime,
        consent_journal=str(Path(state)/'hyprneuro/consent-audit/v1.jsonl'),
        owner_descriptor_sha256=digest(owner/'owner.json') if explicit_ui else None,
        owner_unit='hyprneuro-pi-owner@'+run('systemd-escape','--path',str(owner))+'.service' if explicit_ui else None,
        staged_files={p.name:digest(p) for p in staged.iterdir() if p.is_file()},
        source_files={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()},
        gate='NOT applied/started; require final review + parent start relay + fresh user unlock and independent maintained GUI checks; actual human tool consents only; child-read0/parent-only1')
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(prepared=str(dest),commit=commit,binary_sha256=manifest['binary_sha256'],backup_quick_check='ok',launched=False)))


if __name__=='__main__':
    main()
