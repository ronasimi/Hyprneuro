"""Real product GTK construction/actions, isolated Xvfb+D-Bus+synthetic backend.
No production UI/settings/model/SDK/chooser/consent activity. No FakeUI selectors.
"""
import asyncio,importlib.util,json,os,subprocess,sys,threading,time,warnings,hashlib
warnings.filterwarnings("ignore",message=r".*asyncio\..*.*",category=DeprecationWarning)
from pathlib import Path
# Reuse existing explicit private accessibility-bus setup before importing GI.
if '--isolated-bus' in sys.argv:
    import select
    bus=subprocess.Popen(['/usr/bin/dbus-daemon','--session','--nofork','--print-address=1'],stdout=subprocess.PIPE,text=True);registry=None
    try:
        assert select.select([bus.stdout],[],[],3)[0]
        env=dict(os.environ,AT_SPI_BUS_ADDRESS=bus.stdout.readline().strip(),GIO_USE_VFS='local')
        registry=subprocess.Popen(['/usr/lib/at-spi2-registryd'],env=env)
        result=subprocess.run([sys.executable,'-W','error',__file__],env=env,timeout=35)
    finally:
        if registry:registry.terminate();registry.wait(timeout=5)
        bus.terminate();bus.wait(timeout=5);bus.stdout.close()
    raise SystemExit(result.returncode)
assert os.environ.get('HN_PRIVATE_ATSPI_FIXTURE')=='1' and os.environ['GDK_BACKEND']=='x11' and not os.environ.get('WAYLAND_DISPLAY')
root=Path(__file__).resolve().parents[2];private=Path(os.environ['XDG_RUNTIME_DIR']);release=threading.Event();requests=[]
socket=private/'backend.sock';bridge_fixture=os.environ.get('HN_BRIDGE_FIXTURE')=='1';bootstrap=[];private_broker=None;child=None;server_loop=None;stop_server=None
async def handle(reader,writer):
    request=json.loads(await reader.readline());requests.append(request);action=request.get('action')
    if action=='ui_settings_get':
        if len([r for r in requests if r.get('action')=='ui_settings_get'])==2:
            await asyncio.sleep(float(os.environ.get('HN_RELOAD_DELAY','.6')))
            if os.environ.get('HN_RELOAD_CASE')=='error':
                writer.write(b'{"ok":false,"error":"synthetic reload error"}\n');await writer.drain();writer.close();return
        while not release.is_set():await asyncio.sleep(.02)
        data=dict(ui_transcript_size='restored',ui_autoscroll=True,ui_panel_opacity=.9)
        for name in ['journal','network','resources']:data.update({name+'_active':False,name+'_task':'synthetic','alert_'+name:False})
    elif action=='agent_chat':
        writer.write((json.dumps(dict(type='delta',text='HN565D896ORDINARY'))+'\n'+json.dumps(dict(type='done'))+'\n').encode());await writer.drain();writer.close();return
    else:data={}
    writer.write((json.dumps(dict(ok=True,result=data))+'\n').encode());await writer.drain();writer.close()
async def serve():
    global private_broker,server_loop,stop_server
    server_loop=asyncio.get_running_loop();stop_server=asyncio.Event()
    server=await asyncio.start_unix_server(handle,str(socket))
    if bridge_fixture:
        await asyncio.sleep(float(os.environ.get('HN_BOOTSTRAP_DELAY','0')))
        sys.path.insert(0,str(root/'python/src'))
        from hyprneuro.trusted_control import GrantControlServer,LaunchPolicy,LaunchVerifier
        from hyprneuro.trusted_consent import ConsentJournal,TrustedConsent
        from hyprneuro.sidecar_store import SidecarStore
        store=SidecarStore(private/'fixture.sqlite3')
        journal=ConsentJournal(private/'consent.jsonl')
        class Verifier(LaunchVerifier):
            def child(self,*args):
                identity=super().child(*args)
                fds={str(fd):os.readlink('/proc/'+str(identity['pid'])+'/fd/'+str(fd)) for fd in [0,1,2,3]}
                env=dict(v.split(b'=',1) for v in Path('/proc',str(identity['pid']),'environ').read_bytes().split(b'\0') if b'=' in v)
                assert env[b'PATH']==b'/usr/bin:/bin' and b'PYTHONPATH' not in env and env[b'HOME']==os.environ['HOME'].encode()
                assert fds['3'].startswith('socket:') and fds['0']!=fds['3'] and fds['1']!=fds['3']
                bootstrap.append(dict(stage='real-child-verified',identity=identity,fd_aliases=fds,clean_environment_verified=True))
                return identity
        async def units(unit):
            assert unit=='hyprneuro-ui.service' and child is not None
            return child.pid,Path('/proc/self/cgroup').read_text().strip()[3:]
        policy=LaunchPolicy(Path('/usr/bin/python'),private/'bridge-entry.py',root,hashlib.sha256(Path(os.environ['HN_ORDINARY_WIDGET_BINARY']).read_bytes()).hexdigest(),hashlib.sha256((private/'bridge-entry.py').read_bytes()).hexdigest())
        private_broker=GrantControlServer(TrustedConsent(store,journal),Verifier(policy,units=units))
        broker=await asyncio.start_unix_server(private_broker.handle,str(private/'grant.sock'))
        (private/'grant.sock').chmod(0o600)
        bootstrap.append(dict(stage='broker-listening',pid=os.getpid(),synthetic_units=True))
        try:
            async with server,broker:await stop_server.wait()
        finally:
            tasks=list(private_broker.handlers)
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            journal.close();store.close()
    else:
        async with server:await stop_server.wait()
if bridge_fixture:
    entry=private/'bridge-entry.py';entry.write_text('import sys\nsys.path.insert(0,'+repr(str(root/'python/src'))+')\nfrom hyprneuro.pi_desktop_bridge import main\nraise SystemExit(main())\n');entry.chmod(0o500)
    if os.environ.get('HN_BOOTSTRAP_FAULT')=='import':entry.chmod(0o600);entry.write_text('raise ModuleNotFoundError("synthetic fixture import failure")\n');entry.chmod(0o500)
    policy=private/'launch.json';policy.write_text(json.dumps(dict(schema='hyprneuro.trusted-launch/1',python='/usr/bin/python',entry=str(entry),entry_sha256=hashlib.sha256(entry.read_bytes()).hexdigest(),source=str(root),ui_sha256=hashlib.sha256(Path(os.environ['HN_ORDINARY_WIDGET_BINARY']).read_bytes()).hexdigest())));policy.chmod(0o400)
thread=threading.Thread(target=lambda:asyncio.run(serve()),daemon=True);thread.start()
while not socket.exists():time.sleep(.01)
sys.path.insert(0,str(root/'ui/tests'));from desktop_driver import Desktop,Atspi
spec=importlib.util.spec_from_file_location('driver',Path(os.environ.get('HN_WIDGET_DRIVER',str(root/'scripts/ordinary_app_acceptance.py'))));driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
env=dict(os.environ,HYPHARNESS_SIDECAR=str(socket),HYPRNEURO_UI_SOCKET=str(private/'hyprneuro/ui.sock'),HYPRNEURO_PI_UI='0')
if bridge_fixture:
    if os.environ.get('HN_PASSIVE_GATE')=='1':
        sys.path.insert(0,str(root/'scripts'))
        import continue_app_acceptance as controller
        from unittest.mock import patch
        identity=dict(pid=os.getpid(),start=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19])
        with patch.object(controller,'sidecar_identity',return_value=identity):  # ONLY private unit metadata
            proof=controller.wait_sidecar_listener(private/'grant.sock',time.monotonic()+3)
            controller.recheck_sidecar_listener(proof,time.monotonic()+3)
        print('PASS actual controller passive gate before UI spawn',json.dumps(proof),flush=True)
    elif float(os.environ.get('HN_BOOTSTRAP_DELAY','0'))==0:
        until=time.monotonic()+3
        while not (private/'grant.sock').exists():
            assert time.monotonic()<until;time.sleep(.01)
    env.update(HN_PRIVATE_BROKER_PID=str(os.getpid()),HYPRNEURO_PI_TRUSTED_POLICY=str(private/'launch.json'),HYPRNEURO_PI_TRUSTED_POLICY_SHA256=hashlib.sha256((private/'launch.json').read_bytes()).hexdigest(),HYPRNEURO_PI_BROKER_SOCKET=str(private/'grant.sock'))
if bridge_fixture and os.environ.get('HN_BOOTSTRAP_FAULT')=='policy':env['HYPRNEURO_PI_TRUSTED_POLICY_SHA256']='0'*64
child=subprocess.Popen([os.environ['HN_ORDINARY_WIDGET_BINARY']],env=env,cwd=os.environ['HOME'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
ui_process_start=Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
try:
    desktop=Desktop.__new__(Desktop);desktop.pid=child.pid;desktop.session='PRIVATE-X11'
    def safe():assert child.poll() is None,'Owned private GTK fixture exited'
    desktop.safe=safe
    desktop.wait(lambda:desktop.find('button','Settings'),timeout=10)
    ui=driver.UI.__new__(driver.UI);ui.desktop=desktop;ui.Atspi=Atspi;ui.current=dict(pid=child.pid)
    def ordinary():
        safe()
        frame=next(n for n in Desktop.nodes(child.pid) if n.get_role_name()=='frame')
        rect=Atspi.Component.get_extents(frame,Atspi.CoordType.SCREEN)
        return dict(x=rect.x,y=rect.y,w=rect.width,h=rect.height)
    def pointer(x,y):
        safe();assert Atspi.generate_mouse_event(x,y,'b1c');time.sleep(.15)
    def command(*args):
        assert args[:3]==('wdotool','--backend','wlr-protocols')
        if args[3]=='mousemove':command.position=(int(args[4]),int(args[5]))
        elif args[3]=='click':assert args[3:]==('click','1');pointer(*command.position)
        else:
            assert args[3] in ['key','keyup'] and args[4] in ['ctrl+Return','Return']
            if args[3]=='keyup':
                Atspi.generate_keyboard_event(36,None,Atspi.KeySynthType.RELEASE)
                if args[4]=='ctrl+Return':Atspi.generate_keyboard_event(37,None,Atspi.KeySynthType.RELEASE)
            else:
                if args[4]=='ctrl+Return':Atspi.generate_keyboard_event(37,None,Atspi.KeySynthType.PRESS)
                Atspi.generate_keyboard_event(36,None,Atspi.KeySynthType.PRESSRELEASE)
        return ''
    ui.command=command
    ui.ordinary=ordinary;ui.consent_prompts=set();ui.safe=safe;ui.m={'runtime':str(private),'owner':str(private/'prepared-owner'),'owner_descriptor_sha256':'0'*64}
    sys.path.insert(0,str(root/'scripts'))
    from verify_app_release import ui_status
    ui.status_reader=ui_status
    if bridge_fixture:
        prepared=private/'prepared-owner';prepared.mkdir(mode=0o700)
        descriptor=prepared/'owner.json';descriptor.write_text('{"fixture_only_not_authority":true}\n');descriptor.chmod(0o400)
        ui.m['owner_descriptor_sha256']=hashlib.sha256(descriptor.read_bytes()).hexdigest()
        ui.runtime=private/'notice-attempt';ui.runtime.mkdir(mode=0o700);ui.bundle=private;ui.events=[]
        (ui.runtime/'operation.started').write_text('PRIVATE FIXTURE NO AUTHORITY')
    case=os.environ.get('HN_RELOAD_CASE','success')
    if bridge_fixture and ((float(os.environ.get('HN_BOOTSTRAP_DELAY','0'))>0 and os.environ.get('HN_PASSIVE_GATE')!='1') or os.environ.get('HN_BOOTSTRAP_FAULT')):case='bootstrap-unavailable'
    if case=='sync-return':
        # Transport-latency injection: actual GTK completion/events occur before
        # the ONE action RPC returns to production code. No post-action crutch.
        from gi.repository import GLib
        class Action:
            get_n_actions=Atspi.Action.get_n_actions
            @staticmethod
            def do_action(node,index):
                result=Atspi.Action.do_action(node,index)
                if node.get_name()=='Reload':
                    until=time.monotonic()+3
                    while time.monotonic()<until:
                        context=GLib.MainContext.default()
                        while context.pending():context.iteration(False)
                        if len([r for r in requests if r.get('action')=='ui_settings_get'])==2 and node.get_state_set().contains(Atspi.StateType.SENSITIVE):break
                        time.sleep(.01)
                    else:raise AssertionError('Synchronous-return injection timed out')
                    print('ACTUAL GTK completion/events BEFORE action RPC return',flush=True)
                return result
        class SyncAPI:
            def __getattr__(self,name):return Action if name=='Action' else getattr(Atspi,name)
        ui.Atspi=SyncAPI()
    if case=='missing':
        class DropEvents:
            @staticmethod
            def new(callback):return Atspi.EventListener.new(lambda *args:None)
        class API:
            EventListener=DropEvents
            def __getattr__(self,name):return getattr(Atspi,name)
        ui.Atspi=API()  # explicit delivery-loss injection; GTK/action remain real
    if case=='cancel':
        def cancelled():
            if len([r for r in requests if r.get('action')=='ui_settings_get'])==2:raise InterruptedError('Synthetic cancellation')
            return ordinary()
        ui.ordinary=cancelled
    class ExerciseComplete(Exception):pass
    def record(phase,**kwargs):
        if phase=='ordinary-checks-completed':
            if not bridge_fixture:raise ExerciseComplete()
            node=desktop.find('button','Connect Pi owner…')
            print('ACTUAL CONNECT INVENTORY',json.dumps(dict(exists=node is not None,showing=node.get_state_set().contains(Atspi.StateType.SHOWING) if node else False,sensitive=node.get_state_set().contains(Atspi.StateType.SENSITIVE) if node else False,bootstrap=bootstrap)),flush=True)
            return
        if phase=='CHOOSER-EXPECTED-NOT-YET-OBSERVED':
            desktop.wait(lambda:any(n.get_name()=='Select prepared private Pi owner root — not personal files' and n.get_state_set().contains(Atspi.StateType.SHOWING) for n in Desktop.nodes(child.pid)),timeout=5)
            assert kwargs['owner_directory']==str(private/'prepared-owner')
            driver.UI.record(ui,'HUMAN-NEEDED-CHOOSER',**kwargs)
            packet=json.loads((ui.runtime/'acceptance-human-gate.json').read_text())
            assert packet['descriptor_sha256']==ui.m['owner_descriptor_sha256']
            assert packet['operation_sha256']==hashlib.sha256((ui.runtime/'operation.started').read_bytes()).hexdigest()
            assert 'owner DIRECTORY '+str(private/'prepared-owner') in packet['prompt']
            assert not desktop.find('button','Connect Pi owner…').get_state_set().contains(Atspi.StateType.SENSITIVE),'Selecting did not disable Connect'
            print('PASS actual eligible Connect→real chooser opened→DIRECTORY notice; NO selection/security action',flush=True)
            raise ExerciseComplete()
        raise AssertionError('Unexpected native/human gate')
    ui.record=record
    threading.Timer(.3,release.set).start()
    try:driver.exercise(ui,lambda ready:None,time.monotonic()+15)
    except ExerciseComplete:assert case in ['success','sync-return']
    except (RuntimeError,InterruptedError,AssertionError) as error:
        assert case in ['error','cancel','missing','bootstrap-unavailable'],str(error)
        if case=='bootstrap-unavailable':
            node=desktop.find('button','Connect Pi owner…');assert node and node.get_state_set().contains(Atspi.StateType.SHOWING) and not node.get_state_set().contains(Atspi.StateType.SENSITIVE)
            print('PROVEN PRIVATE failure visible INSENSITIVE Connect, NOT absent/not Settings; live cause remains UNKNOWN',flush=True)
        if case=='error':assert str(error)=='Reload completion reports error/unknown status'
        if case=='cancel':assert isinstance(error,InterruptedError)
        if case=='missing':assert str(error)=='Timed out waiting for actual GTK state'
        assert len([r for r in requests if r.get('action')=='ui_settings_get'])==2
        print('PASS exact production exercise fail-closed',case,'single Reload; no retry',flush=True)
        raise SystemExit(0)
    else:raise AssertionError('Exercise passed through human boundary')
    assert len([r for r in requests if r.get('action')=='ui_settings_get'])==2
    chats=[r for r in requests if r.get('action')=='agent_chat'];assert len(chats)==2
    assert any(m.get('role')=='assistant' and m.get('content')==driver.MARKER for m in chats[1]['history'])
    assert not ui.keys_inflight
    print('PASS exact production exercise ordinary sequence fast/delayed Reload; no fixture completion waits',flush=True)
    if bridge_fixture:raise SystemExit(0)  # human picker boundary: NO further input
    # Additional explicit Send selector coverage (exercise uses Return in Legacy).
    ui.draft(driver.FIRST);ui.button('Send')
    desktop.wait(lambda:ui.settled(driver.MARKER,legacy=True),timeout=5)
    desktop.control('hide');desktop.control('show');ui.expect_draft('')
    raise SystemExit(0)
finally:
    release.set()
    if child.poll() is None:child.terminate()
    try:out,err=child.communicate(timeout=5)
    except subprocess.TimeoutExpired:child.kill();out,err=child.communicate()
    if err:print('PRIVATE GTK STDERR',err,file=sys.stderr)
    if bridge_fixture:
        print('PRIVATE BOOTSTRAP FINAL',json.dumps(bootstrap),'failures',private_broker.failures if private_broker else None,flush=True)
        for item in bootstrap:
            if item['stage']=='real-child-verified':
                until=time.monotonic()+3
                while Path('/proc',str(item['identity']['pid'])).exists() and time.monotonic()<until:time.sleep(.02)
                assert not Path('/proc',str(item['identity']['pid'])).exists(),'Owned bridge did not exit'
        assert (private/'consent.jsonl').stat().st_size==0
    if server_loop and stop_server:
        server_loop.call_soon_threadsafe(stop_server.set);thread.join(timeout=3);assert not thread.is_alive(),'Private server thread did not drain'
    print('PRIVATE OWNED CHILD MAP',json.dumps(dict(before=[dict(role='ui',pid=child.pid,start=ui_process_start)]+[dict(role='bridge',pid=item['identity']['pid'],start=item['identity']['start']) for item in bootstrap if item['stage']=='real-child-verified'],after=[],server_thread_alive=thread.is_alive())),flush=True)
    print('PRIVATE CLEAN EXIT UI/bridge/server; no owned children remain',flush=True)
