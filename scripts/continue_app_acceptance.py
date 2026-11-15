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
from command_budget import timeout as command_timeout


def write_state(root,state,phase):
    state['phase']=phase;state['history'].append(dict(phase=phase,time=time.time()))
    temp=root/'continuation-state.tmp'
    with temp.open('w') as file:
        json.dump(state,file,indent=2);file.flush();os.fsync(file.fileno())
    os.replace(temp,root/'continuation-state.json')
    fd=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)


def preflight(bundle,root,session,context_sha256,deadline=None):
    context=load_context(bundle,root,context_sha256,deadline=deadline)
    sys.path.insert(0,str(bundle/'staged'))
    from guard_app_release import unit_state
    from apply_app_release import desktop_safe
    from prepare_app_release import check_owner_inert,check_moe_inert,unit_identity,run
    from verify_app_release import check_unit_backups
    desktop_safe(session,deadline=deadline)
    m=json.loads((bundle/'manifest.json').read_text())
    if context['version']==1:
        assert len(m['source_files'])==301 and len(m['staged_files'])==11
    else:
        from repair_app_release import stopped_baseline
        stopped_baseline(bundle,context,m,deadline=deadline)
        if [len(m['source_files']),len(m['staged_files'])]!=context['catalog_counts']:raise RuntimeError('Repair catalog drift')
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
            '-p','FragmentPath','-p','DropInPaths',timeout=5,deadline=deadline).splitlines())
        if effective!={'FragmentPath':identity['fragment'],'DropInPaths':' '.join(identity['dropins'])}:
            raise RuntimeError('Effective app unit fragment/drop-in drift')
        for name in [identity['fragment'],*identity['dropins']]:
            if digest(name)!=baseline.get(str(Path(name).resolve())):
                raise RuntimeError('Current app unit baseline changed')
    check_unit_backups(bundle,m['units'])
    if digest(m['database']['backup'])!=m['database']['backup_sha256']:raise RuntimeError('Archived backup drift')
    if digest(bundle/'backup/hyprneuro-ui')!=m['installed_sha256']:raise RuntimeError('Archived UI drift')
    for unit in ['hyprneuro-ui.service','hyprneuro.service']:
        state=unit_state(unit,deadline=deadline)
        if state!={'ActiveState':'inactive','SubState':'dead','MainPID':'0','Job':'','ControlGroup':''}:
            raise RuntimeError('Apps must be stopped/PID0/no job/cgroup before continuation')
        if run('systemctl','--user','show',unit,'-p','NeedDaemonReload','--value',timeout=5,deadline=deadline)!='no':raise RuntimeError('App reload drift')
    from runtime_attestation import validate
    for entry in validate(context,deadline=deadline)['models']:
        identity=entry['identity']
        if dict(x.split('=',1) for x in run('systemctl','--user','show',identity['unit'],'-p','ActiveState','-p','SubState',timeout=5,deadline=deadline).splitlines())!=dict(ActiveState='active',SubState='running'):raise RuntimeError('Model state drift')
        if unit_identity(identity['unit'],deadline=deadline)!=identity:raise RuntimeError('Active model identity drift')
        if run('systemctl','--user','show',identity['unit'],'-p','Job','--value',timeout=5,deadline=deadline):raise RuntimeError('Model job')
        if run('systemctl','--user','show',identity['unit'],'-p','NeedDaemonReload','--value',timeout=5,deadline=deadline)!='no':raise RuntimeError('Model reload drift')
    for port in [8081,8082,8083]:
        with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=command_timeout(deadline,5)) as reply:
            if json.load(reply).get('status')!='ok':raise RuntimeError('Model not ready')
    check_moe_inert(deadline=deadline)
    check_owner_inert(Path.home()/'.config/systemd/user/hyprneuro-pi-owner@.service',m['owner_unit'],deadline=deadline)
    if json.loads(run('systemctl','--user','list-units','--all','--no-pager','--output=json','hyprneuro-pi-owner@*.service',timeout=5,deadline=deadline)):
        raise RuntimeError('Owner instance appeared; separate conditional authority needed')
    native=Path(m['owner']);runtime=Path(m['runtime'])
    for file in [native/'owner.guard',native/'checkpoint.json',runtime/'hyprneuro/pi-owner-service.lock',runtime/'hyprharness/grant-control.sock']:
        if file.exists() or file.is_symlink():raise RuntimeError('Owner/endpoint/guard appeared')
    if list((native/'sessions').glob('*.jsonl')):raise RuntimeError('Native work appeared')
    if Path(m['consent_journal']).stat().st_size:raise RuntimeError('Prior empty audit changed; manual review')
    workspace=json.loads(run('hyprctl','-j','activeworkspace',timeout=5,deadline=deadline))
    if workspace['id']!=context['workspace'] or workspace['windows']!=0:raise RuntimeError('Expected empty workspace required; no movement')
    # Read-only capability checks; no focus/input or production app start here.
    run('wdotool','--backend','wlr-protocols','capabilities',timeout=5,deadline=deadline)
    run('/usr/bin/python','-c',"import gi;gi.require_version('Atspi','2.0');from gi.repository import Atspi;assert Atspi.Text.get_text",timeout=5,deadline=deadline)
    desktop_safe(session,deadline=deadline)
    return context,m


def verify_started(bundle,root,context_sha256,deadline=None):
    from prepare_app_release import unit_identity
    from verify_installed_continuation import verify
    deadline=min(deadline,time.monotonic()+8) if deadline is not None else time.monotonic()+8
    while time.monotonic()<deadline:
        load_context(bundle,root,context_sha256,deadline=deadline)
        origin=json.loads((bundle/'sidecar-origin.json').read_text())
        if origin['pid']==unit_identity('hyprneuro.service',deadline=deadline)['pid']:break
        time.sleep(.1)
    else:raise TimeoutError('New sidecar origin not attested')
    verify(bundle,root,context_sha256,deadline=deadline)


def sidecar_identity(deadline):
    from prepare_app_release import run
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('Sidecar readiness total deadline')
    fields=dict(x.split('=',1) for x in run('systemctl','--user','show','hyprneuro.service',
        '-p','MainPID','-p','ActiveState','-p','SubState','-p','Job','-p','NeedDaemonReload',timeout=min(3,remaining)).splitlines())
    if ({k:fields[k] for k in ['ActiveState','SubState','Job','NeedDaemonReload']}!=dict(
            ActiveState='active',SubState='running',Job='',NeedDaemonReload='no')):
        raise RuntimeError('Sidecar state/job/reload changed')
    pid=int(fields['MainPID']);proc=Path('/proc')/str(pid)
    if pid<=0 or proc.stat().st_uid!=os.getuid():raise RuntimeError('Sidecar PID/UID invalid')
    result=dict(pid=pid,start=(proc/'stat').read_text().rsplit(')',1)[1].split()[19])
    if time.monotonic()>=deadline:raise TimeoutError('Sidecar readiness total deadline')
    return result


def listener_snapshot(path,pid):
    try:info=path.lstat()
    except FileNotFoundError:return None
    if path!=path.resolve() or not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600:
        raise RuntimeError('Sidecar listener path/type/UID/mode invalid')
    owned=set()
    for fd in (Path('/proc')/str(pid)/'fd').iterdir():
        try:target=os.readlink(fd)
        except FileNotFoundError:continue  # unrelated descriptor closed
        if target.startswith('socket:[') and target.endswith(']'):owned.add(target[8:-1])
    rows=[]
    for line in (Path('/proc')/str(pid)/'net/unix').read_text().splitlines()[1:]:
        row=line.split()
        if len(row)==8 and row[7]==str(path):rows.append(row)
    if len(rows)>1:raise RuntimeError('Ambiguous/rebound sidecar socket pathname')
    valid=[r for r in rows if r[6] in owned and int(r[3],16)&0x10000 and r[4]=='0001' and r[5]=='01']
    if len(valid)>1:raise RuntimeError('Ambiguous sidecar listener')
    if not valid:return None
    return dict(filesystem_device=info.st_dev,filesystem_inode=info.st_ino,kernel_socket_inode=valid[0][6])


def wait_sidecar_listener(path,deadline):
    expected=sidecar_identity(deadline)
    while time.monotonic()<deadline:
        if sidecar_identity(deadline)!=expected:raise RuntimeError('Sidecar PID/start replaced')
        snapshot=listener_snapshot(path,expected['pid'])
        if snapshot:
            if sidecar_identity(deadline)!=expected:raise RuntimeError('Sidecar changed during readiness observation')
            return dict(identity=expected,path=str(path),snapshot=snapshot)
        time.sleep(min(.05,max(0,deadline-time.monotonic())))
    raise TimeoutError('Sidecar listener readiness deadline; UI NOT started')


def recheck_sidecar_listener(proof,deadline):
    if (sidecar_identity(deadline)!=proof['identity'] or
            listener_snapshot(Path(proof['path']),proof['identity']['pid'])!=proof['snapshot'] or
            sidecar_identity(deadline)!=proof['identity']):
        raise RuntimeError('Sidecar listener changed before UI start')


def execute(bundle,root,session,authorized=False,unlocked=False,context_sha256=None):
    if not authorized or not unlocked:raise PermissionError('Actual reviewed parent relay/fresh unlock checks required')
    # Preflight failure never starts/stops an unrelated app. No failed marker replay.
    deadline=time.monotonic()+7200
    context,m=preflight(bundle,root,session,context_sha256,deadline=deadline)
    for name in ['operation.started','continuation-state.json','continuation-state.tmp','acceptance-result.json','acceptance-human-gate.json','acceptance-human-gate.tmp','ordinary-acceptance.json']:
        if (root/name).exists() or (root/name).is_symlink():raise RuntimeError('Continuation already used; no replay')
    marker=dict(id=context['id'],context_sha256=context_sha256,pid=os.getpid(),start=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
    with (root/'operation.started').open('x') as file:
        json.dump(marker,file);file.flush();os.fsync(file.fileno())
    from guard_app_release import contain,observe
    from apply_app_release import desktop_safe
    state=dict(history=[],human_acceptance_claimed=False,owner_model_signals=False,continuation_id=context['id'])
    child=None
    try:
        if context['version']==2:
            from repair_app_release import cutover
            write_state(root,state,'repairing-stopped-artifacts')
            cutover(bundle,context,m,session,lambda:load_context(bundle,root,context_sha256,deadline=deadline),deadline=deadline)
        write_state(root,state,'starting-installed-sidecar')
        desktop_safe(session,deadline=deadline);load_context(bundle,root,context_sha256,deadline=deadline)
        if context['version']==2:
            from repair_app_release import verify_replacements
            verify_replacements(context,m,deadline)
        subprocess.run(['systemctl','--user','start','hyprneuro.service'],check=True,timeout=command_timeout(deadline,15))
        write_state(root,state,'waiting-sidecar-control-listener')
        readiness_deadline=min(deadline,time.monotonic()+8)  # ONE budget including final post-await recheck
        proof=wait_sidecar_listener(Path(m['runtime'])/'hyprharness/grant-control.sock',readiness_deadline)
        write_state(root,state,'starting-installed-UI')
        desktop_safe(session,deadline=readiness_deadline);load_context(bundle,root,context_sha256,deadline=readiness_deadline)
        if context['version']==2:verify_replacements(context,m,readiness_deadline)
        recheck_sidecar_listener(proof,readiness_deadline)  # after context/unlock awaits, immediately before UI start
        subprocess.run(['systemctl','--user','start','hyprneuro-ui.service'],check=True,timeout=command_timeout(deadline,15))
        write_state(root,state,'verifying-installed')
        verify_started(bundle,root,context_sha256,deadline=deadline)
        write_state(root,state,'acceptance-window')
        observe(bundle,m,session,deadline=deadline);load_context(bundle,root,context_sha256,deadline=deadline)
        child=subprocess.Popen(['/usr/bin/python',context['driver'],str(bundle),'--continuation',str(root),'--context-sha256',context_sha256,'--deadline',str(deadline)])
        while child.poll() is None:
            if time.monotonic()>=deadline:raise TimeoutError('Continuation acceptance deadline')
            observe(bundle,m,session,deadline=deadline);load_context(bundle,root,context_sha256,deadline=deadline);time.sleep(.25)
        if child.returncode:raise RuntimeError('Acceptance driver failed')
        observe(bundle,m,session,deadline=deadline);load_context(bundle,root,context_sha256,deadline=deadline)
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
