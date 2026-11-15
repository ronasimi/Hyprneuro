"""Real product GTK construction/actions, isolated Xvfb+D-Bus+synthetic backend.
No production UI/settings/model/SDK/chooser/consent activity. No FakeUI selectors.
"""
import asyncio,importlib.util,json,os,subprocess,sys,threading,time,warnings
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
socket=private/'backend.sock'
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
    server=await asyncio.start_unix_server(handle,str(socket))
    async with server:await server.serve_forever()
thread=threading.Thread(target=lambda:asyncio.run(serve()),daemon=True);thread.start()
while not socket.exists():time.sleep(.01)
sys.path.insert(0,str(root/'ui/tests'));from desktop_driver import Desktop,Atspi
spec=importlib.util.spec_from_file_location('driver',Path(os.environ.get('HN_WIDGET_DRIVER',str(root/'scripts/ordinary_app_acceptance.py'))));driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
env=dict(os.environ,HYPHARNESS_SIDECAR=str(socket),HYPRNEURO_UI_SOCKET=str(private/'hyprneuro/ui.sock'),HYPRNEURO_PI_UI='0')
child=subprocess.Popen([os.environ['HN_ORDINARY_WIDGET_BINARY']],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
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
    ui.ordinary=ordinary;ui.consent_prompts=set();ui.safe=safe;ui.m={'runtime':str(private)}
    sys.path.insert(0,str(root/'scripts'))
    from verify_app_release import ui_status
    ui.status_reader=ui_status
    case=os.environ.get('HN_RELOAD_CASE','success')
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
        if phase=='ordinary-checks-completed':raise ExerciseComplete()
        raise AssertionError('Unexpected native/human gate')
    ui.record=record
    threading.Timer(.3,release.set).start()
    try:driver.exercise(ui,lambda ready:None,time.monotonic()+15)
    except ExerciseComplete:assert case in ['success','sync-return']
    except (RuntimeError,InterruptedError,AssertionError) as error:
        assert case in ['error','cancel','missing'],str(error)
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
