"""Real product GTK construction/actions, isolated Xvfb+D-Bus+synthetic backend.
No production UI/settings/model/SDK/chooser/consent activity. No FakeUI selectors.
"""
import asyncio,importlib.util,json,os,subprocess,sys,threading,time
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
        if len([r for r in requests if r.get('action')=='ui_settings_get'])==2:await asyncio.sleep(.6)
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
        else:assert args[3:]==('click','1');pointer(*command.position)
        return ''
    ui.command=command
    ui.ordinary=ordinary;ui.consent_prompts=set()
    ui.button('Settings')
    desktop.wait(lambda:any(n.get_role_name()=='button' and n.get_name()=='← Back' and n.get_state_set().contains(Atspi.StateType.SHOWING) for n in Desktop.nodes(child.pid)),timeout=3)
    inventory=[dict(name=n.get_name(),showing=n.get_state_set().contains(Atspi.StateType.SHOWING),sensitive=n.get_state_set().contains(Atspi.StateType.SENSITIVE)) for n in Desktop.nodes(child.pid) if n.get_role_name()=='button' and n.get_name() in driver.BUTTONS]
    print('ACTUAL WIDGET INVENTORY',json.dumps(inventory),flush=True)
    # Actual request_preferences sets prefs_busy; Reload exists but insensitive.
    reload=desktop.find('button','Reload');assert reload and not reload.get_state_set().contains(Atspi.StateType.SENSITIVE)
    threading.Timer(.3,release.set).start()
    ui.button('Reload')  # OLD selector fails here; corrected bounded wait must pass
    assert len([r for r in requests if r.get('action')=='ui_settings_get'])==2
    assert desktop.find('button','Reload').get_state_set().contains(Atspi.StateType.SENSITIVE), 'Reload returned before completion'
    ui.button('← Back')
    original=ui.size();ui.button(original);ui.button(ui.size());assert ui.size()==original
    ui.draft(driver.FIRST)
    # Private Xvfb's standard XKB keycodes: Control_L37, Return36.
    # Private registry injects ONLY into the private X server, not host Wayland.
    Atspi.generate_keyboard_event(37,None,Atspi.KeySynthType.PRESS)
    try:Atspi.generate_keyboard_event(36,None,Atspi.KeySynthType.PRESSRELEASE)
    finally:Atspi.generate_keyboard_event(37,None,Atspi.KeySynthType.RELEASE)
    ui.expect_draft(driver.FIRST+'\n')
    Atspi.generate_keyboard_event(36,None,Atspi.KeySynthType.PRESSRELEASE)
    desktop.wait(lambda:ui.settled(driver.MARKER,legacy=True),timeout=5)
    ui.draft(driver.SECOND)
    ui.button('Send')
    desktop.wait(lambda:ui.settled(driver.MARKER,legacy=True),timeout=5)
    chats=[x for x in requests if x.get('action')=='agent_chat'];assert len(chats)==2
    assert any(m.get('role')=='assistant' and m.get('content')==driver.MARKER for m in chats[1].get('history',[])), 'Actual assistant history not retained'
    desktop.control('hide');desktop.control('show');ui.expect_draft('')
    for name in ['Settings','Send','Connect Pi owner…',ui.size()]:assert desktop.find('button',name),name
    before=len([r for r in requests if r.get('action')=='ui_settings_get'])
    try:ui.button('Reload')
    except AssertionError:pass
    else:raise AssertionError('Hidden settings Reload accepted')
    assert len([r for r in requests if r.get('action')=='ui_settings_get'])==before
    try:ui.button('Allow')
    except RuntimeError:pass
    else:raise AssertionError('Security action accepted')
    print('PASS actual product Settings→busy Reload wait→Reload→Back→Normal/Expanded restore→CtrlEnter/Enter→synthetic chat/history→hide/show selectors. NOT production inference/SDK/human acceptance.',flush=True)
finally:
    release.set()
    if child.poll() is None:child.terminate()
    try:out,err=child.communicate(timeout=5)
    except subprocess.TimeoutExpired:child.kill();out,err=child.communicate()
    if err:print('PRIVATE GTK STDERR',err,file=sys.stderr)
