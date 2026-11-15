"""STOPPED565 -> new db8 diagnostic artifacts only; no SQL, restore or starts.
Called exclusively inside reviewed continuation's once-only guard/containment.
"""
import json,os,stat
from pathlib import Path
from continuation_context import digest,MANIFEST

def stopped_baseline(bundle,context,m):
    from guard_app_release import unit_state
    from prepare_app_release import private_file,run
    from verify_app_release import check_unit_backups
    for folder,key in [('source','source_files'),('staged','staged_files')]:
        actual={str(p.relative_to(bundle/folder)) for p in (bundle/folder).rglob('*') if p.is_file()}
        if actual!=set(m[key]):raise RuntimeError('Repair file catalog changed')
        for name,sha in m[key].items():
            if digest(private_file(bundle/folder/name))!=sha:raise RuntimeError('Repair payload changed')
    if digest(private_file(m['binary']))!=m['binary_sha256']:raise RuntimeError('Repair binary drift')
    old=Path(context['previous_bundle']);previous=json.loads((old/'manifest.json').read_text())
    if digest(old/'manifest.json')!=MANIFEST:raise RuntimeError('Previous immutable manifest changed')
    for folder,key,n in [('source','source_files',301),('staged','staged_files',11)]:
        if len(previous[key])!=n:raise RuntimeError('Previous catalog changed')
        for name,sha in previous[key].items():
            if digest(old/folder/name)!=sha:raise RuntimeError('Previous release changed')
    for unit in ['hyprneuro.service','hyprneuro-ui.service']:
        if unit_state(unit)!=dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',ControlGroup=''):raise RuntimeError('Repair requires stopped apps')
        if run('systemctl','--user','show',unit,'-p','NeedDaemonReload','--value',timeout=5)!='no':raise RuntimeError('Unreviewed app reload')
    check_unit_backups(bundle,m['units'])
    for path,sha in context['installed_files'].items():
        file=private_file(path)
        if file!=Path(path) or digest(file)!=sha or stat.S_IMODE(file.stat().st_mode)!=context['installed_modes'][path]:raise RuntimeError('Stopped installed565 drift')
    if context['installed_files'].get(m['installed_ui'])!=previous['binary_sha256']:raise RuntimeError('Wrong previous installed UI')
    # Canonical destinations are a closed set, NEVER taken from arbitrary manifest paths.
    home=(Path.home()/'.config/systemd/user').resolve()
    expected={str(home/'hyprneuro.service.d/95-reviewed-readonly-release.conf'),str(home/'hyprneuro-ui.service.d/95-reviewed-readonly-release.conf'),str(home/'hyprneuro-pi-owner@.service'),str(Path.home()/'.local/bin/hyprneuro-ui')}
    if set(context['replacement_files'])!=expected:raise RuntimeError('Wrong repair target set')
    for identity in [m['ui'],m['sidecar']]:
        effective=dict(x.split('=',1) for x in run('systemctl','--user','show',identity['unit'],'-p','FragmentPath','-p','DropInPaths',timeout=5).splitlines())
        if effective!={'FragmentPath':identity['fragment'],'DropInPaths':' '.join(identity['dropins'])}:raise RuntimeError('Effective stopped units drift')
    for entry in m['units']:
        if digest(private_file(entry['path']))!=entry['sha256']:raise RuntimeError('Stopped unit hash drift')
    if digest(bundle/'backup/hyprneuro-ui')!=previous['binary_sha256']:raise RuntimeError('Stopped UI backup drift')

def cutover(bundle,context,m,session,check_context):
    from apply_app_release import atomic_copy,desktop_safe
    from prepare_app_release import run,private_file
    from verify_app_release import release_targets
    stopped_baseline(bundle,context,m)
    targets=release_targets(bundle,m,(Path.home()/'.config/systemd/user').resolve())
    targets.append((Path(m['binary']),Path(m['installed_ui'])))
    if {str(dst) for _,dst in targets}!=set(context['replacement_files']):raise RuntimeError('Repair target mismatch')
    # Validate EVERY source/destination before first mutation; no backup restoration.
    for src,dst in targets:
        src=private_file(src);private_file(dst)
        if dst!=dst.resolve() or digest(src)!=context['replacement_files'][str(dst)]['sha256']:raise RuntimeError('Repair source/canonical target drift')
    for src,dst in targets:
        desktop_safe(session);check_context()
        if digest(private_file(dst))!=context['installed_files'][str(dst)]:raise RuntimeError('Replacement baseline changed')
        atomic_copy(src,dst,context['replacement_files'][str(dst)]['mode'])
        if digest(dst)!=context['replacement_files'][str(dst)]['sha256']:raise RuntimeError('Replacement verification failed')
    desktop_safe(session);check_context()
    run('systemctl','--user','daemon-reload',timeout=15)
    for identity in [m['ui'],m['sidecar']]:
        effective=dict(x.split('=',1) for x in run('systemctl','--user','show',identity['unit'],'-p','FragmentPath','-p','DropInPaths',timeout=5).splitlines())
        if effective!={'FragmentPath':identity['fragment'],'DropInPaths':' '.join(identity['dropins'])}:raise RuntimeError('Replacement effective units changed')
        if run('systemctl','--user','show',identity['unit'],'-p','NeedDaemonReload','--value',timeout=5)!='no':raise RuntimeError('Replacement not loaded')
