#!/usr/bin/python
"""Once-only post-INSTALL acceptance; NEVER calls apply/reload/restore/owner ops.

Run only after independent entrypoint/operations approval via MAIN, holding machine
lease. Original failed apply markers remain immutable. New context/marker binds
this child, watcher and existing coordinator to a distinct private attempt.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time
import urllib.request
from continuation_context import load_context,digest


def write_state(root,state,phase):
    state['phase']=phase;state['history'].append(dict(phase=phase,time=time.time()))
    temp=root/'continuation-state.tmp'
    with temp.open('w') as file:
        json.dump(state,file,indent=2);file.flush();os.fsync(file.fileno())
    os.replace(temp,root/'continuation-state.json')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def preflight(bundle,root,session,context_sha256):
    context=load_context(bundle,root,context_sha256)
    sys.path.insert(0,str(bundle/'staged'))
    from guard_app_release import unit_state
    from apply_app_release import desktop_safe
    from prepare_app_release import check_owner_inert,check_moe_inert,unit_identity,run
    from verify_app_release import check_unit_backups
    desktop_safe(session)
    m=json.loads((bundle/'manifest.json').read_text())
    assert len(m['source_files'])==301 and len(m['staged_files'])==11
    for folder,entries in [('source',m['source_files']),('staged',m['staged_files'])]:
        for name,sha in entries.items():
            if digest(bundle/folder/name)!=sha:raise RuntimeError('Immutable bundle drift')
    for path,sha in context['installed_files'].items():
        if digest(path)!=sha:raise RuntimeError('Already-installed NEW release drift')
        file=Path(path);info=file.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=context['installed_modes'][path] or file!=file.resolve():raise RuntimeError('Installed mode/canonical identity drift')
    for path,sha in context['preserved_files'].items():
        if digest(path)!=sha:raise RuntimeError('Settings/model config baseline drift')
    # Archive validation is NOT a live base/effective unit baseline check.
    baseline={str(Path(item['path']).resolve()):item['sha256'] for item in m['units']}
    baseline.update(context['installed_files'])  # reviewed NEW replacement hashes
    for identity in [m['sidecar'],m['ui']]:
        effective=dict(x.split('=',1) for x in run('systemctl','--user','show',identity['unit'],
            '-p','FragmentPath','-p','DropInPaths',timeout=5).splitlines())
        if effective!={'FragmentPath':identity['fragment'],'DropInPaths':' '.join(identity['dropins'])}:
            raise RuntimeError('Effective app unit fragment/drop-in drift')
        for name in [identity['fragment'],*identity['dropins']]:
            if digest(name)!=baseline.get(str(Path(name).resolve())):
                raise RuntimeError('Current app unit baseline changed')
    check_unit_backups(bundle,m['units'])
    if digest(m['database']['backup'])!=m['database']['backup_sha256']:raise RuntimeError('Archived backup drift')
    if digest(bundle/'backup/hyprneuro-ui')!=m['installed_sha256']:raise RuntimeError('Archived UI drift')
    for unit in ['hyprneuro-ui.service','hyprneuro.service']:
        state=unit_state(unit)
        if state!={'ActiveState':'inactive','SubState':'dead','MainPID':'0','Job':'','ControlGroup':''}:
            raise RuntimeError('Apps must be stopped/PID0/no job/cgroup before continuation')
        if run('systemctl','--user','show',unit,'-p','NeedDaemonReload','--value',timeout=5)!='no':raise RuntimeError('App reload drift')
    from runtime_attestation import validate
    for entry in validate(context)['models']:
        identity=entry['identity']
        if dict(x.split('=',1) for x in run('systemctl','--user','show',identity['unit'],'-p','ActiveState','-p','SubState',timeout=5).splitlines())!=dict(ActiveState='active',SubState='running'):raise RuntimeError('Model state drift')
        if unit_identity(identity['unit'])!=identity:raise RuntimeError('Active model identity drift')
        if run('systemctl','--user','show',identity['unit'],'-p','Job','--value',timeout=5):raise RuntimeError('Model job')
        if run('systemctl','--user','show',identity['unit'],'-p','NeedDaemonReload','--value',timeout=5)!='no':raise RuntimeError('Model reload drift')
    for port in [8081,8082,8083]:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=5) as reply:
            if json.load(reply).get('status')!='ok':raise RuntimeError('Model not ready')
    check_moe_inert()
    check_owner_inert(Path.home()/'.config/systemd/user/hyprneuro-pi-owner@.service',m['owner_unit'])
    if json.loads(run('systemctl','--user','list-units','--all','--no-pager','--output=json','hyprneuro-pi-owner@*.service',timeout=5)):
        raise RuntimeError('Owner instance appeared; separate conditional authority needed')
    native=Path(m['owner']);runtime=Path(m['runtime'])
    for file in [native/'owner.guard',native/'checkpoint.json',runtime/'hyprneuro/pi-owner-service.lock',runtime/'hyprharness/grant-control.sock']:
        if file.exists() or file.is_symlink():raise RuntimeError('Owner/endpoint/guard appeared')
    if list((native/'sessions').glob('*.jsonl')):raise RuntimeError('Native work appeared')
    if Path(m['consent_journal']).stat().st_size:raise RuntimeError('Prior empty audit changed; manual review')
    workspace=json.loads(run('hyprctl','-j','activeworkspace',timeout=5))
    if workspace['id']!=context['workspace'] or workspace['windows']!=0:raise RuntimeError('Expected empty workspace required; no movement')
    # Read-only capability checks; no focus/input or production app start here.
    run('wdotool','--backend','wlr-protocols','capabilities',timeout=5)
    run('/usr/bin/python','-c',"import gi;gi.require_version('Atspi','2.0');from gi.repository import Atspi;assert Atspi.Text.get_text",timeout=5)
    desktop_safe(session)
    return context,m


def verify_started(bundle,root,context_sha256):
    from prepare_app_release import unit_identity
    from verify_installed_continuation import verify
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        load_context(bundle,root,context_sha256)
        origin=json.loads((bundle/'sidecar-origin.json').read_text())
        if origin['pid']==unit_identity('hyprneuro.service')['pid']:break
        time.sleep(.1)
    else:raise TimeoutError('New sidecar origin not attested')
    verify(bundle,root,context_sha256)


def execute(bundle,root,session,authorized=False,unlocked=False,context_sha256=None):
    if not authorized or not unlocked:raise PermissionError('Actual reviewed parent relay/fresh unlock checks required')
    # Preflight failure never starts/stops an unrelated app. No failed marker replay.
    context,m=preflight(bundle,root,session,context_sha256)
    for name in ['operation.started','continuation-state.json','continuation-state.tmp','acceptance-result.json','acceptance-human-gate.json','acceptance-human-gate.tmp','ordinary-acceptance.json']:
        if (root/name).exists() or (root/name).is_symlink():raise RuntimeError('Continuation already used; no replay')
    marker=dict(id=context['id'],context_sha256=context_sha256,pid=os.getpid(),start=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
    with (root/'operation.started').open('x') as file:
        json.dump(marker,file);file.flush();os.fsync(file.fileno())
    from guard_app_release import contain,observe
    from apply_app_release import desktop_safe
    state=dict(history=[],human_acceptance_claimed=False,owner_model_signals=False,continuation_id=context['id'])
    child=None;deadline=time.monotonic()+7200
    try:
        write_state(root,state,'starting-installed-sidecar')
        desktop_safe(session);load_context(bundle,root,context_sha256)
        subprocess.run(['systemctl','--user','start','hyprneuro.service'],check=True,timeout=15)
        write_state(root,state,'starting-installed-UI')
        desktop_safe(session);load_context(bundle,root,context_sha256)
        subprocess.run(['systemctl','--user','start','hyprneuro-ui.service'],check=True,timeout=15)
        write_state(root,state,'verifying-installed')
        verify_started(bundle,root,context_sha256)
        write_state(root,state,'acceptance-window')
        observe(bundle,m,session);load_context(bundle,root,context_sha256)
        child=subprocess.Popen(['/usr/bin/python',context['driver'],str(bundle),'--continuation',str(root),'--context-sha256',context_sha256])
        while child.poll() is None:
            if time.monotonic()>=deadline:raise TimeoutError('Continuation acceptance deadline')
            observe(bundle,m,session);load_context(bundle,root,context_sha256);time.sleep(.25)
        if child.returncode:raise RuntimeError('Acceptance driver failed')
        observe(bundle,m,session);load_context(bundle,root,context_sha256)
        write_state(root,state,'acceptance-command-completed-NOT-human-READY-evidence')
        return 0
    except BaseException as error:
        state['failure']=dict(type=type(error).__name__,detail=str(error)[:300]);driver_stopped=True
        if child is not None:
            try:
                if child.poll() is None:child.terminate();child.wait(timeout=3)
            except Exception:driver_stopped=False
        state['acceptance_driver_stopped']=driver_stopped
        state['containment']=contain()  # reviewed bounded app-only stop; NO unlock gate
        phase='failed-apps-stopped' if driver_stopped and all(x['stopped'] for x in state['containment'].values()) else 'failed-UNCONTAINED'
        try:write_state(root,state,phase)
        except Exception:
            state['phase_persistence_failed']=True;print(json.dumps(state),file=sys.stderr);return 2
        return 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('bundle',type=Path)
    p.add_argument('--continuation',type=Path,required=True);p.add_argument('--session',required=True)
    p.add_argument('--context-sha256',required=True)
    p.add_argument('--parent-authorized',action='store_true');p.add_argument('--fresh-user-unlock-confirmed',action='store_true')
    a=p.parse_args();os.umask(0o077)
    def cancelled(signum,frame):raise InterruptedError('Continuation cancelled')
    signal.signal(signal.SIGTERM,cancelled)
    return execute(a.bundle,a.continuation,a.session,a.parent_authorized,a.fresh_user_unlock_confirmed,a.context_sha256)


if __name__=='__main__':raise SystemExit(main())
