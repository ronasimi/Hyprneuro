#!/usr/bin/python
"""New db8 artifact bundle from STOPPED565; prepare only, no live DB or starts."""
import argparse,hashlib,json,os,shutil,stat,subprocess,sys,tarfile,uuid
from pathlib import Path
from continuation_context import MANIFEST,digest
from prepare_app_release import private_file,prepare_parent_owner,prepare_trusted_launch,run,check_owner_inert,check_moe_inert
COMMIT='db8fedae8f4baa35f0ed8193914169eceb7bbe22'

def prepare(dest,oldroot):
    os.umask(0o077)
    if not dest.is_absolute() or dest!=dest.resolve() or dest.exists():raise ValueError('New canonical bundle required')
    oldctx=json.loads(private_file(oldroot/'continuation-context.json').read_text());old=Path(oldctx['bundle'])
    if digest(old/'manifest.json')!=MANIFEST:raise RuntimeError('Wrong installed565 baseline')
    m=json.loads((old/'manifest.json').read_text())
    from runtime_attestation import validate
    validate(oldctx)  # EXACT approved prospective baseline, never recapture/rebaseline
    for p,h in {**oldctx['installed_files'],**oldctx['preserved_files']}.items():
        if digest(p)!=h:raise RuntimeError('Installed/preserved baseline drift')
    from guard_app_release import unit_state
    for unit in ['hyprneuro.service','hyprneuro-ui.service']:
        if unit_state(unit)!=dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',ControlGroup=''):raise RuntimeError('Prepare requires STOPPED apps')
    check_owner_inert(Path.home()/'.config/systemd/user/hyprneuro-pi-owner@.service',m['owner_unit']);check_moe_inert()
    for folder,key,n in [('source','source_files',301),('staged','staged_files',11)]:
        if len(m[key])!=n:raise RuntimeError('Original catalog drift')
        for name,h in m[key].items():
            if digest(old/folder/name)!=h:raise RuntimeError('Original artifact drift')
    dest.mkdir(mode=0o700)
    for name in ['source','staged','backup','bin']:(dest/name).mkdir(mode=0o700)
    repo=Path(__file__).resolve().parents[1]
    archive=dest/'source.tar'
    with archive.open('xb') as f:subprocess.run(['git','-C',str(repo),'archive',COMMIT],stdout=f,check=True)
    with tarfile.open(archive) as f:f.extractall(dest/'source',filter='data')
    archive.unlink()
    source=dest/'source';staged=dest/'staged';backup=dest/'backup'
    subprocess.run(['meson','setup',str(dest/'build'),str(source/'ui')],check=True)
    subprocess.run(['meson','compile','-C',str(dest/'build')],check=True)
    subprocess.run(['meson','test','-C',str(dest/'build'),'--print-errorlogs'],check=True)
    binary=dest/'bin/hyprneuro-ui';shutil.copyfile(dest/'build/hyprneuro-ui',binary);binary.chmod(0o500)
    shutil.copyfile(private_file(m['installed_ui']),backup/'hyprneuro-ui');(backup/'hyprneuro-ui').chmod(0o500)
    if digest(backup/'hyprneuro-ui')!=oldctx['installed_files'][m['installed_ui']]:raise RuntimeError('Installed backup drift')
    units=[]
    for entry in m['units']:
        p=private_file(entry['path']);h=oldctx['installed_files'].get(str(p),entry['sha256'])
        if digest(p)!=h:raise RuntimeError('Stopped unit baseline drift')
        target=backup/(str(len(units))+'-'+p.name);shutil.copyfile(p,target);target.chmod(0o400)
        value=dict(path=str(p),backup=str(target),sha256=h,mode=stat.S_IMODE(p.stat().st_mode))
        if entry.get('role')=='owner-template':value.update(role='owner-template',previous_bundle=str(old),previous_manifest_sha256=MANIFEST)
        units.append(value)
    # Historical archives COPY ONLY; never open production SQLite/settings for restore.
    if digest(m['database']['backup'])!=m['database']['backup_sha256']:raise RuntimeError('Historical DB archive drift')
    shutil.copyfile(m['database']['backup'],backup/'observations.sqlite3');(backup/'observations.sqlite3').chmod(0o400)
    if m['settings']:
        shutil.copyfile(m['settings']['path'],backup/'settings.json');(backup/'settings.json').chmod(0o400)
    python=Path(m['python']);owner=dest/'owner'
    task=prepare_parent_owner(source,owner,python,staged);workspace=owner/'home/workspace'
    (workspace/'fixture.txt').write_text('MAPLE_READ_ONLY_FIXTURE\n')
    if len(str(workspace))>128:raise RuntimeError('Workspace bound')
    prepare_trusted_launch(source,python,binary,staged,m['runtime'])
    for name in m['staged_files']:
        if (staged/name).exists():continue
        src=repo/'scripts'/name if name.endswith('.py') and (repo/'scripts'/name).exists() else old/'staged'/name
        body=src.read_bytes()
        if name in ['ui.conf','sidecar.conf']:
            body=body.replace(str(old).encode(),str(dest).encode()).replace(digest(old/'staged/trusted-launch.json').encode(),digest(staged/'trusted-launch.json').encode())
        if name in ['ui.conf','sidecar.conf']:body+=b'\nRestart=no\n'
        (staged/name).write_bytes(body);(staged/name).chmod(0o500 if name.endswith('.py') else 0o400)
    shutil.copyfile(repo/'scripts/command_budget.py',staged/'command_budget.py');(staged/'command_budget.py').chmod(0o400)
    origins=dict(m['import_origins']);origins['modules']={n:p.replace(str(old),str(dest)) for n,p in origins['modules'].items()}
    m.update(commit=COMMIT,prepared_only=True,repair_from=dict(bundle=str(old),manifest_sha256=MANIFEST),
        historical_app_identities=True,installed_sha256=digest(backup/'hyprneuro-ui'),binary=str(binary),binary_sha256=digest(binary),units=units,
        owner_template_baseline=next(e for e in units if e.get('role')=='owner-template'),import_origins=origins,
        task=task,owner=str(owner),workspace=str(workspace),owner_descriptor_sha256=digest(owner/'owner.json'),
        owner_unit='hyprneuro-pi-owner@'+run('systemd-escape','--path',str(owner))+'.service',
        database={**m['database'],'backup':str(backup/'observations.sqlite3'),'historical_archive_not_live_backup':True})
    for p in source.rglob('*'):
        if p.is_symlink():raise RuntimeError('Unexpected source symlink')
        p.chmod(0o500 if p.is_dir() or p.stat().st_mode&0o111 else 0o400)
    source.chmod(0o500)
    m.update(source_files={str(p.relative_to(source)):digest(p) for p in source.rglob('*') if p.is_file()},staged_files={p.name:digest(p) for p in staged.iterdir() if p.is_file()})
    approved=Path('/home/ron/Workspace/hn-bootstrap-diagnostic-source-db8feda/source-files.json')
    if digest(approved)!='ea4e908f4cd72f6f98fa6a084137be18d12535e4602a57544edf0544051e9256':raise RuntimeError('Approved db8 source catalog drift')
    if m['source_files']!=json.loads(approved.read_text()):raise RuntimeError('Export is not exact approved db8 source')
    m['managed_app_source_catalog']={p:h for p,h in m['source_files'].items() if p.startswith(('ui/src/','python/src/','extensions/'))}
    (dest/'manifest.json').write_text(json.dumps(m,indent=2)+'\n');(dest/'manifest.json').chmod(0o400)
    validate(oldctx)
    print(json.dumps(dict(bundle=str(dest),manifest_sha256=digest(dest/'manifest.json'),binary_sha256=digest(binary),started=False)))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('output',type=Path);parser.add_argument('--installed-context',type=Path,required=True);a=parser.parse_args()
    # SQL forbidden even accidentally during preparation; descriptor staging uses no SQL.
    sys.addaudithook(lambda event,args:(_ for _ in ()).throw(RuntimeError('No SQL during repair preparation')) if event=='sqlite3.connect' else None)
    prepare(a.output,a.installed_context)
