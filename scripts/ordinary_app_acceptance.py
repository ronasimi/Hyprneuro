#!/usr/bin/python
"""External review-pinned acceptance driver; run ONLY as the guard's child.

No lease acquisition, service operation, chooser approval or security action.
Only literal synthetic text reaches the own-app composer. Never writes coordinator
results. Real human prompts remain pending; completion files are NOT consent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

MANIFEST='44bf0c8d3a41aa402253e5a8548b1b834d1062b0635343c0f271ba854da3a857'
COMPOSER='Enter sends · Ctrl+Enter inserts a newline'
MARKER='HN565D896ORDINARY'
FIRST='Reply with exactly '+MARKER+'.'
SECOND='What exact marker did you just reply with? Reply with that marker only.'
READ='Read fixture.txt exactly once using the read tool, then quote its complete contents. Do not use any other tool.'
BUTTONS={'Settings','Reload','← Back','Expand transcript: Normal → Expanded',
         'Restore transcript: Expanded → Normal','Connect Pi owner…','Send'}


def current_answer(transcript):
    return transcript.rsplit('\nyou: ',1)[-1].partition('\nassistant: ')[2]


def exercise(ui, pending, deadline):
    """One explicit sequence. No replay/retry of submissions or activations."""
    def until(check, limit=90):
        end=min(deadline,time.monotonic()+limit)
        while time.monotonic()<end:
            pending(False)  # rejects early completion; observes cancellation
            ui.safe()
            if check():return
            time.sleep(.1)
        raise RuntimeError('Acceptance check timed out; no replay')
    ui.show()
    ui.empty()
    ui.button('Settings');ui.button('Reload');ui.button('← Back')
    size=ui.size()
    ui.button(size);ui.button(ui.size())
    if ui.size()!=size:raise RuntimeError('Normal/Expanded did not restore')
    ui.draft(FIRST);ui.key('ctrl+Return')
    ui.expect_draft(FIRST+'\n')  # Ctrl+Enter MUST NOT send
    ui.key('Return')
    until(lambda:ui.settled(MARKER,legacy=True))
    ui.draft(SECOND);ui.key('Return')
    until(lambda:ui.settled(MARKER,legacy=True))  # own new-turn history canary
    ui.hide_show();ui.empty()
    ui.record('ordinary-checks-completed')
    ui.button('Connect Pi owner…')  # opens chooser; NEVER selects/approves it
    ui.chooser_notice()
    until(ui.connected,limit=7200)  # human selects ONLY pinned owner.json
    ui.empty();ui.draft(READ);ui.button('Send')  # single scoped native request
    until(lambda:ui.settled(ui.fixture,legacy=False),limit=7200)
    if len(ui.consent_prompts)<2:
        raise RuntimeError('Activation AND exact-read prompt observations missing')
    ui.record('native-read-ui-check-completed-not-human-attestation')
    pending(True)  # only NOW may the existing coordinator report completion


class UI:
    def __init__(self,bundle,continuation=None):
        self.bundle=bundle
        self.runtime=continuation or bundle
        if hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()!=MANIFEST:
            raise RuntimeError('Wrong reviewed bundle')
        self.m=json.loads((bundle/'manifest.json').read_text())
        sys.path.insert(0,str(bundle/'staged'))
        from prepare_app_release import unit_identity
        from verify_app_release import verify,ui_status
        self.identity=unit_identity;self.status_reader=ui_status
        verify(bundle,installed=True,legacy=True)  # post-cutover metadata, no SQL
        self.current=unit_identity('hyprneuro-ui.service')
        if self.current['pid']==self.m['ui']['pid']:raise RuntimeError('Old UI still running')
        sys.path.insert(0,str(bundle/'source/ui/tests'))
        from desktop_driver import Desktop,Atspi
        self.Atspi=Atspi
        self.desktop=Desktop(os.environ['HN_ACCEPTANCE_SESSION'],self.current['pid'])
        self.consent_prompts=set();self.events=[];self.keys_inflight=False
        fixture=Path(self.m['workspace'])/'fixture.txt'
        self.fixture=fixture.read_text().strip()
        if not self.fixture or len(self.fixture)>256:raise RuntimeError('Unexpected synthetic fixture')
        self.safe()

    def record(self,phase,**metadata):
        self.events.append(dict(phase=phase,**metadata))
        runtime=getattr(self,'runtime',self.bundle)
        target=runtime/'ordinary-acceptance.json'
        with target.open('w') as file:
            json.dump(dict(events=self.events,human_acceptance_claimed=False),file,indent=2)
            file.flush();os.fsync(file.fileno())
        if phase in ['HUMAN-NEEDED','HUMAN-NEEDED-CHOOSER']:
            self.gate_seq=getattr(self,'gate_seq',0)+1
            event=runtime/'acceptance-human-gate.json'
            if self.gate_seq==1 and event.exists():raise RuntimeError('Preexisting human event; no stale overwrite')
            packet=dict(version=1,operation_sha256=hashlib.sha256((runtime/'operation.started').read_bytes()).hexdigest(),
                        seq=self.gate_seq,kind='consent' if phase=='HUMAN-NEEDED' else 'chooser',
                        prompt=(metadata['prompt'] if phase=='HUMAN-NEEDED' else metadata['prompt']+'\nHuman action: select owner DIRECTORY '+metadata['owner_directory']+' containing owner.json SHA256 '+self.m['owner_descriptor_sha256']+'. Do NOT select the JSON file.'),
                        descriptor_sha256=self.m['owner_descriptor_sha256'])
            temporary=runtime/'acceptance-human-gate.tmp'
            with temporary.open('x') as file:
                json.dump(packet,file);file.flush();os.fsync(file.fileno())
            os.replace(temporary,event)
            fd=os.open(runtime,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        print(phase,flush=True)

    def nodes(self):return self.desktop.nodes(self.current['pid'])

    def prompt(self):
        nodes=self.nodes()
        windows=[n for n in nodes if n.get_name()=='Pi host consent · fresh human decision']
        if not windows:return False
        # Read ONLY this exact own-app consent subtree. Never touch its actions.
        parts=[]
        def walk(node):
            role=node.get_role_name()
            if role=='label':parts.append(node.get_name())
            elif role=='text':parts.append(self.Atspi.Text.get_text(node,0,16000))
            for child in node:
                if child:walk(child)
        walk(windows[0]);detail='\n'.join(parts)[:20000]
        token=hashlib.sha256(detail.encode()).hexdigest()
        if token not in self.consent_prompts:
            self.consent_prompts.add(token)
            self.record('HUMAN-NEEDED',prompt=detail,action='Human inspect exact prompt; Allow exact action once ONLY if intended. Driver supplies no answer.')
        return True

    def safe(self):
        self.desktop.safe()
        if self.identity('hyprneuro-ui.service')!=self.current:raise RuntimeError('UI identity changed')

    @staticmethod
    def command(*args):
        return subprocess.check_output(args,text=True,timeout=5)

    def ordinary(self):
        self.safe()
        if self.prompt():raise RuntimeError('Unexpected human gate during ordinary input')
        workspace=json.loads(self.command('hyprctl','-j','activeworkspace'))
        if workspace['windows']!=0:raise RuntimeError('Need empty own-overlay workspace; no automatic workspace movement')
        layers=json.loads(self.command('hyprctl','-j','layers'))
        entries=[(int(level),node) for monitor in layers.values() for level,items in monitor['levels'].items() for node in items]
        own=[node for level,node in entries if node.get('pid')==self.current['pid'] and node.get('namespace')=='hyprneuro']
        if len(own)!=1:raise RuntimeError('Own layer identity ambiguous')
        ours=own[0]
        for level,node in entries:
            if node is ours or level<2:continue
            if (max(ours['x'],node['x'])<min(ours['x']+ours['w'],node['x']+node['w'])
                    and max(ours['y'],node['y'])<min(ours['y']+ours['h'],node['y']+node['h'])):
                raise RuntimeError('Overlapping foreground layer; no input')

    def composer(self):
        node=self.desktop.find('text',COMPOSER)
        if node is None:raise RuntimeError('Exact composer absent')
        return node

    def expect_draft(self,text):
        self.desktop.wait(lambda:self.Atspi.Text.get_text(self.composer(),0,-1)==text,timeout=3)

    def empty(self):self.ordinary();self.expect_draft('')

    def draft(self,text):
        if text not in [FIRST,SECOND,READ]:raise RuntimeError('Nonliteral input prohibited')
        self.empty()
        node=self.composer()
        if not node.get_editable_text_iface().set_text_contents(text):raise RuntimeError('Composer edit failed')
        if not node.get_component_iface().grab_focus():raise RuntimeError('Composer focus failed')
        self.expect_draft(text)

    def key(self,key):
        if key not in ['ctrl+Return','Return']:raise RuntimeError('Unapproved key')
        self.ordinary()
        if not self.composer().get_state_set().contains(self.Atspi.StateType.FOCUSED):raise RuntimeError('Composer lacks verified focus')
        status=self.status_reader(Path(self.m['runtime'])/'hyprneuro/ui.sock',self.current['pid'])
        if status['mode']!='legacy' or status['connected']:
            raise RuntimeError('Global keyboard tests are Legacy-only; native uses exact Send action')
        self.keys_inflight=True
        try:self.command('wdotool','--backend','wlr-protocols','key',key)
        finally:
            # Release only this driver's injected chain, even on termination.
            try:self.command('wdotool','--backend','wlr-protocols','keyup',key)
            finally:self.keys_inflight=False

    def button(self,name):
        if name not in BUTTONS:raise RuntimeError('Unapproved button (security/chooser actions prohibited)')
        self.ordinary()
        matches=[node for node in self.nodes() if node.get_role_name()=='button' and node.get_name()==name
                 and node.get_state_set().contains(self.Atspi.StateType.SHOWING)
                 and node.get_state_set().contains(self.Atspi.StateType.SENSITIVE)]
        if len(matches)!=1:raise RuntimeError('Exact visible/enabled button ambiguous or absent')
        self.desktop.activate('button',name)

    def size(self):
        for name in ['Expand transcript: Normal → Expanded','Restore transcript: Expanded → Normal']:
            if self.desktop.find('button',name):return name
        raise RuntimeError('Size selector absent')

    def show(self):self.desktop.control('show');self.ordinary()
    def hide_show(self):self.ordinary();self.desktop.control('hide');self.desktop.control('show');self.ordinary()

    def chooser_notice(self):
        self.record('CHOOSER-EXPECTED-NOT-YET-OBSERVED',
                    prompt='Select prepared private Pi owner root — not personal files',
                    owner_directory=str(Path(self.m['owner'])),
                    descriptor_sha256=self.m['owner_descriptor_sha256'],
                    action='Human select ONLY the owner DIRECTORY containing pinned owner.json, NOT the JSON file. Driver never selects or approves chooser.')

    def connected(self):
        if self.prompt():return False
        title='Select prepared private Pi owner root — not personal files'
        clients=json.loads(self.command('hyprctl','-j','clients'))
        if any(client.get('title')==title for client in clients):
            if not any(event['phase']=='HUMAN-NEEDED-CHOOSER' for event in self.events):
                self.record('HUMAN-NEEDED-CHOOSER',prompt=title,
                            owner_directory=str(Path(self.m['owner'])),
                            descriptor_sha256=self.m['owner_descriptor_sha256'],
                            action='Human select ONLY the owner DIRECTORY containing pinned owner.json, NOT the JSON file; no driver chooser approval')
            return False
        status=self.status_reader(Path(self.m['runtime'])/'hyprneuro/ui.sock',self.current['pid'])
        return status['mode']=='pi' and status['connected'] and status['read_callable']

    def settled(self,expected,legacy):
        if self.prompt():return False
        labels=self.desktop.labels()
        if 'Hyprneuro · error' in labels:raise RuntimeError('Actual GUI turn error')
        status='Legacy sidecar · tool-free' if legacy else 'Pi owner · settled (not tool success)'
        if status not in labels:return False
        if self.Atspi.Text.get_text(self.composer(),0,-1):return False
        texts=[n for n in self.nodes() if n.get_role_name()=='text' and not n.get_name()
               and n.get_state_set().contains(self.Atspi.StateType.SHOWING)]
        if len(texts)!=1:raise RuntimeError('Transcript selector ambiguous')
        # Never persist existing text; only validate own synthetic suffix canary.
        if expected not in current_answer(self.Atspi.Text.get_text(texts[0],0,-1)):
            raise RuntimeError('Current settled answer failed own canary (not prior/user text)')
        return True


def coordinator(bundle,deadline,ready):
    from wait_app_acceptance import wait
    if ready or (bundle/'acceptance-result.json').exists():
        result=wait(bundle,timeout=max(0,deadline-time.monotonic()))
        if result or not ready:raise RuntimeError('Failed/cancelled/premature coordinator completion')


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('bundle',type=Path)
    parser.add_argument('--continuation',type=Path);args=parser.parse_args()
    bundle=args.bundle;runtime=args.continuation or bundle;deadline=time.monotonic()+7200
    sys.path.insert(0,str(bundle/'staged'))
    def pending(ready):coordinator(runtime,deadline,ready)
    def terminate(signum,frame):raise InterruptedError('Acceptance driver terminated')
    signal.signal(signal.SIGTERM,terminate)
    parent=Path('/proc')/str(os.getppid())/'cmdline'
    argv=parent.read_bytes().rstrip(b'\0').decode().split('\0')
    if args.continuation:
        from continuation_context import require_parent
        pid=os.getppid();start=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
        require_parent(bundle,runtime,argv,pid,start)
    else:
        if len(argv)<3 or argv[1]!=str(bundle/'staged/guard_app_release.py') or argv[2]!=str(bundle):
            raise RuntimeError('Driver must be direct child of the reviewed guard, not standalone/nested lease')
        if not (bundle/'operation.started').exists() or not (bundle/'apply.completed').exists():
            raise RuntimeError('No current guarded applied operation')
    ui=None
    try:
        ui=UI(bundle,args.continuation);exercise(ui,pending,deadline)
        ui.record('coordinator-ended-not-human-or-READY-evidence')
    except BaseException as error:
        if ui:ui.record('FAILED',error=type(error).__name__)
        raise


if __name__=='__main__':main()
