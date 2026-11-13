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


def run(*args, **kw):
    return subprocess.check_output(args, text=True, **kw).strip()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def private_file(path):
    p = Path(path)
    st = p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1:
        raise RuntimeError('Unsafe regular file: ' + str(p))
    return p


def unit_identity(name):
    fields = dict(line.split('=', 1) for line in run('systemctl', '--user', 'show', name,
        '-p', 'MainPID', '-p', 'ActiveState', '-p', 'FragmentPath', '-p', 'DropInPaths').splitlines())
    pid = int(fields['MainPID'])
    if not pid or fields['ActiveState'] != 'active':
        raise RuntimeError('Expected active unit: ' + name)
    proc = Path('/proc') / str(pid)
    if proc.stat().st_uid != os.getuid():
        raise RuntimeError('Wrong process UID')
    return dict(unit=name, pid=pid, start=proc.joinpath('stat').read_text().rsplit(')', 1)[1].split()[19],
        exe=str(proc.joinpath('exe').resolve()), exe_sha256=digest(proc/'exe'),
        fragment=fields['FragmentPath'], dropins=fields['DropInPaths'].split())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
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
            units.append(dict(path=name, backup=str(target), sha256=digest(file)))
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
    # New fixture only. No scope, owner, model, credentials or consent is created.
    owner=dest/'owner'; workspace=owner/'home/workspace';workspace.mkdir(parents=True,mode=0o700)
    (workspace/'fixture.txt').write_text('MAPLE_READ_ONLY_FIXTURE\n')
    if len(str(workspace))>128:
        raise RuntimeError('Workspace exceeds broker file-prefix bound')
    task='hn-ro-'+secrets.token_hex(12)
    # Read-only collision check, never authorization or consent.
    broker_path=Path(runtime)/'hyprharness/sidecar.sock'
    if broker_path.stat().st_uid!=os.getuid():
        raise RuntimeError('Wrong broker UID')
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(5);client.connect(str(broker_path))
        client.sendall((json.dumps(dict(action='auth_check',task_id=task,op='read',app_id='hn-ro-parent-fixture',path=str(workspace/'fixture.txt')))+'\n').encode())
        packet=bytearray()
        while b'\n' not in packet:
            chunk=client.recv(4096)
            if not chunk or len(packet)+len(chunk)>65536:raise RuntimeError('Bounded broker response required')
            packet.extend(chunk)
        result=json.loads(packet.split(b'\n')[0])
        if result!={'ok':True,'result':{'allowed':False,'reason':'no_authorization'}}:
            raise RuntimeError('Task collision or incompatible broker; do not launch')
    common=f'Environment="PYTHONPATH={source}/python/src" "PYTHONDONTWRITEBYTECODE=1" "HOME={home}" "XDG_STATE_HOME={state}" "XDG_CONFIG_HOME={config}" "XDG_RUNTIME_DIR={runtime}"\nUnsetEnvironment=HYPRNEURO_RESIDENCY_DIR\n'
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
    (staged/'ui.conf').write_text('[Service]\n'+common+
        f'Environment="HYPRNEURO_PI_UI=1" "HYPRNEURO_PI_OWNER_DIR={owner}" "HYPRNEURO_PI_BRIDGE_PYTHON={python}"\n')
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
    (staged/'start-owner.sh').write_text(launch);(staged/'start-owner.sh').chmod(0o500)
    for identity in (ui,sidecar,*models):
        assert unit_identity(identity['unit'])==identity, 'Running identity changed during preparation'
    if run('systemctl','--user','show','lfm@moe.service','-p','MainPID','--value')!='0' or run('systemctl','--user','show','lfm@moe.service','-p','ActiveState','--value')!='inactive':
        raise RuntimeError('MoE active; stop preparation without model operation')
    for name in ['prepare_app_release.py','verify_app_release.py','apply_app_release.py']:
        shutil.copyfile(repo/'scripts'/name,staged/name);(staged/name).chmod(0o500)
    # Freeze exported payload; Python runtime must never create cache files here.
    for p in source.rglob('*'):
        if p.is_symlink():
            raise RuntimeError('Unexpected release symlink')
        p.chmod(0o500 if p.is_dir() or p.stat().st_mode&0o111 else 0o400)
    source.chmod(0o500)
    manifest=dict(commit=commit,prepared_only=True,ui=ui,sidecar=sidecar,models=models,units=units,
        python=str(python),import_origins=origins,installed_ui=str(installed),installed_mode=stat.S_IMODE(installed.stat().st_mode),
        installed_sha256=digest(installed),binary=str(bin_dir/'hyprneuro-ui'),binary_sha256=digest(bin_dir/'hyprneuro-ui'),
        database=dict(path=str(db),backup=str(backup/'observations.sqlite3'),backup_sha256=digest(backup/'observations.sqlite3'),quick_check='ok'),
        editable_metadata=dict(path='/home/ron/Projects/Hyprneuro/python/.venv/lib/python3.13/site-packages/__editable__.hyprneuro-0.1.0.pth',sha256=digest('/home/ron/Projects/Hyprneuro/python/.venv/lib/python3.13/site-packages/__editable__.hyprneuro-0.1.0.pth')),
        settings=settings_receipt,task=task,owner=str(owner),workspace=str(workspace),runtime=runtime,
        staged_files={p.name:digest(p) for p in staged.iterdir() if p.is_file()},
        source_files={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()},
        gate='NOT applied/started; require final review + parent start relay + fresh user unlock and independent maintained GUI checks; actual human tool consents only; child-read0/parent-only1')
    (dest/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(prepared=str(dest),commit=commit,binary_sha256=manifest['binary_sha256'],backup_quick_check='ok',launched=False)))


if __name__=='__main__':
    main()
