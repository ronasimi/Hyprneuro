#!/usr/bin/env python3
"""Once-only apply AND acceptance-window guard; never grants human consent.

Run only the reviewed guard under the shared machine lease. The acceptance
command must span ALL intended acceptance/human-wait gates. Its exit0 is merely
command completion, NOT human acceptance/READY evidence. Failures/cancellation
stop only app UI/sidecar; no owner/model signals or automatic rollback/replay.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import subprocess
import time
from apply_app_release import main as apply, desktop_safe
from prepare_app_release import run, check_moe_inert

APPS = ('hyprneuro-ui.service', 'hyprneuro.service')


def unit_state(unit):
    return dict(line.split('=',1) for line in run('systemctl','--user','show',unit,
        '-p','ActiveState','-p','SubState','-p','MainPID','-p','Job','-p','ControlGroup',timeout=5).splitlines())


def contain():
    """Contain even when a lock/unlock check itself failed; no GUI gate here."""
    results={}
    for unit in APPS:
        item={}
        try:
            result=subprocess.run(['systemctl','--user','stop',unit],check=False,timeout=15,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            item['stop_exit']=result.returncode
        except Exception as error:
            item['stop_error']=type(error).__name__
        try:
            state=unit_state(unit);item['state']=state
            group=state.get('ControlGroup','')
            members=Path('/sys/fs/cgroup'+group)/'cgroup.procs' if group.startswith('/') else None
            empty=not group or (members is not None and (not members.exists() or not members.read_text().strip()))
            item['stopped']=(item.get('stop_exit')==0 and state.get('ActiveState')=='inactive'
                             and state.get('SubState')=='dead' and state.get('MainPID')=='0'
                             and state.get('Job')=='' and empty)
        except Exception as error:
            item.update(stopped=False,verification_error=type(error).__name__)
        results[unit]=item
    return results


def observe(bundle, manifest, session):
    desktop_safe(session)
    check_moe_inert()
    for unit in APPS:
        state=unit_state(unit)
        if (state.get('ActiveState')!='active' or state.get('SubState')!='running'
                or not state.get('MainPID','').isdigit() or int(state['MainPID'])==0 or state.get('Job')!=''):
            raise RuntimeError('App unavailable during acceptance: '+unit)
    owner=Path(manifest['owner'])
    checkpoint=owner/'checkpoint.json'
    if checkpoint.exists():
        phase=json.loads(checkpoint.read_text()).get('phase')
        if not isinstance(phase,str) or phase=='failed' or 'unknown' in phase:
            raise RuntimeError('Native owner failed/unknown during acceptance')
        if phase!='closed':
            state=unit_state(manifest['owner_unit'])
            if (state.get('ActiveState')!='active' or state.get('SubState')!='running'
                    or not state.get('MainPID','').isdigit() or int(state['MainPID'])==0 or state.get('Job')!=''):
                raise RuntimeError('Native owner exited/unavailable during acceptance')
    journals=list((owner/'sessions').glob('*.jsonl'))
    if len(journals)>32: raise RuntimeError('Native journal observation bound')
    audit=manifest.get('consent_journal')
    if audit and Path(audit).exists(): journals.append(Path(audit))
    for path in journals:
        if path.stat().st_size>64*1024*1024: raise RuntimeError('Journal observation byte bound')
        with path.open('rb') as file:
            for _ in range(100001):
                line=file.readline(1024*1024+1)
                if not line: break
                if len(line)>1024*1024 or not line.endswith(b'\n'):
                    raise RuntimeError('Journal incomplete/oversized during acceptance')
                if not isinstance(json.loads(line),dict): raise RuntimeError('Invalid journal record')
            else: raise RuntimeError('Journal observation record bound')


def execute(bundle, session, acceptance, *, authorized=False, unlocked=False):
    if not authorized or not unlocked: raise PermissionError('Reviewed parent relay and fresh actual unlock checks required')
    if (bundle/'apply.started').exists(): raise RuntimeError('Apply already started; no replay')
    # Exclusive guard marker also prevents re-entry when apply preflight failed.
    with (bundle/'operation.started').open('x') as file:
        file.write(str(time.time())+'\n');file.flush();os.fsync(file.fileno())
    state=dict(phase='starting',history=[],human_acceptance_claimed=False,owner_model_signals=False)
    def record(phase):
        state['phase']=phase;state['history'].append(dict(phase=phase,time=time.time()))
        target=bundle/'operation-state.json';temporary=bundle/'operation-state.tmp'
        with temporary.open('w') as file:
            json.dump(state,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(temporary,target)
        fd=os.open(bundle,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    child=None
    try:
        record('applying')
        apply([str(bundle),'--session',session,'--parent-authorized','--fresh-user-unlock-confirmed'])
        manifest=json.loads((bundle/'manifest.json').read_text())
        record('acceptance-window')
        observe(bundle,manifest,session)
        child=subprocess.Popen(acceptance)  # reviewed operator command, no shell
        while child.poll() is None:
            observe(bundle,manifest,session);time.sleep(.25)
        if child.returncode: raise RuntimeError('Acceptance command failed: '+str(child.returncode))
        observe(bundle,manifest,session)
        record('acceptance-command-completed')  # no invented human/READY evidence
        return 0
    except BaseException as error:
        state['failure']=dict(type=type(error).__name__,detail=str(error)[:300])
        driver_stopped=True
        if child is not None:
            try:
                if child.poll() is None:
                    child.terminate();child.wait(timeout=3)  # only owned acceptance driver
            except Exception: driver_stopped=False
        # Even phase persistence failure or lock must NOT prevent containment.
        state['acceptance_driver_stopped']=driver_stopped
        state['containment']=contain()
        contained=driver_stopped and all(v['stopped'] for v in state['containment'].values())
        try:
            record('failed-apps-stopped' if contained else 'failed-UNCONTAINED')
        except Exception:
            state['phase_persistence_failed']=True
            print(json.dumps(state),file=sys.stderr)
            return 2  # containment attempted; durable evidence itself is unknown
        return 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('bundle',type=Path);parser.add_argument('--session',required=True)
    parser.add_argument('--parent-authorized',action='store_true')
    parser.add_argument('--fresh-user-unlock-confirmed',action='store_true')
    parser.add_argument('--acceptance-command',dest='acceptance',nargs=argparse.REMAINDER,required=True,help='Reviewed command spanning ALL acceptance/human-wait gates')
    args=parser.parse_args()
    command=args.acceptance[1:] if args.acceptance[:1]==['--'] else args.acceptance
    if not command: parser.error('Explicit reviewed acceptance command required; no unguarded acceptance window')
    os.umask(0o077)
    def cancelled(signum,frame): raise InterruptedError('Guard cancelled')
    signal.signal(signal.SIGTERM,cancelled)
    return execute(args.bundle,args.session,command,authorized=args.parent_authorized,
                   unlocked=args.fresh_user_unlock_confirmed)


if __name__=='__main__':
    raise SystemExit(main())
