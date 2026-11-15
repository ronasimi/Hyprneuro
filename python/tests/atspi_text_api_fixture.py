"""Real GTK4/AT-SPI API regression, isolated Xvfb/private D-Bus ONLY.

No production UI, SDK, broker, provider, consent reply or security button exists.
Run via the private launcher; --gtk-child is an owned synthetic GTK fixture.
"""
import os
from pathlib import Path
import sys

if '--gtk-child' in sys.argv:
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk, GLib
    app=Gtk.Application(application_id='local.hyprneuro.OfflineTextAPI')
    def activate(application):
        window=Gtk.ApplicationWindow(application=application,title='OFFLINE SYNTHETIC text API fixture')
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);window.set_child(box)
        composer=Gtk.TextView();composer.update_property([Gtk.AccessibleProperty.LABEL],['Enter sends · Ctrl+Enter inserts a newline'])
        composer.get_buffer().set_text('SYNTHETIC draft\n');box.append(composer)
        answer=Gtk.TextView(editable=False);answer.get_buffer().set_text('\nyou: SYNTHETIC\n\nassistant: SYNTHETIC answer\n');box.append(answer)
        box.append(Gtk.Label(label='Legacy sidecar · tool-free'))
        window.present()
        consent=Gtk.ApplicationWindow(application=application,title='Pi host consent · fresh human decision')
        text=Gtk.TextView(editable=False);text.get_buffer().set_text('SYNTHETIC consent details; NO AUTHORITY OR HUMAN EVIDENCE')
        consent.set_child(text);consent.present()
        def instruction(source,condition):
            if sys.stdin.readline().strip()=='close-consent':consent.destroy()
            return True
        GLib.io_add_watch(sys.stdin,GLib.IO_IN,instruction)
    app.connect('activate',activate);raise SystemExit(app.run([]))

if '--isolated-bus' in sys.argv:
    import subprocess,select
    bus=subprocess.Popen(['/usr/bin/dbus-daemon','--session','--nofork','--print-address=1'],stdout=subprocess.PIPE,text=True)
    registry=None
    try:
        assert select.select([bus.stdout],[],[],3)[0], 'Private accessibility bus did not start'
        env=dict(os.environ,AT_SPI_BUS_ADDRESS=bus.stdout.readline().strip(),GIO_USE_VFS='local')
        registry=subprocess.Popen(['/usr/lib/at-spi2-registryd'],env=env)
        result=subprocess.run([sys.executable,'-W','error',__file__],env=env,timeout=30)
    finally:
        if registry is not None:
            registry.terminate();registry.wait(timeout=5)
        bus.terminate();bus.wait(timeout=5);bus.stdout.close()
    raise SystemExit(result.returncode)

import importlib.util
import subprocess
import time
import warnings
assert os.environ.get('HN_PRIVATE_ATSPI_FIXTURE')=='1'
assert os.environ['GDK_BACKEND']=='x11'
assert '/hn-atspi-' in os.environ['XDG_RUNTIME_DIR']
assert not os.environ.get('WAYLAND_DISPLAY')
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'ui/tests'))
from desktop_driver import Desktop,Atspi
spec=importlib.util.spec_from_file_location('driver',root/'scripts/ordinary_app_acceptance.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
child=subprocess.Popen([sys.executable,__file__,'--gtk-child'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,stdin=subprocess.PIPE,text=True)
try:
    end=time.monotonic()+20
    while time.monotonic()<end:
        assert child.poll() is None,'Private fixture exited'
        nodes=Desktop.nodes(child.pid)
        composer=next((n for n in nodes if n.get_role_name()=='text' and n.get_name()==driver.COMPOSER),None)
        if composer:break
        time.sleep(.05)
    else:raise AssertionError('Real AT-SPI fixture composer absent')
    # Actual installed GI binding, not a mock or FakeUI text object.
    assert Atspi.Text.get_text(composer,0,-1)=='SYNTHETIC draft\n'
    assert Atspi.Text.get_text(composer,0,9)=='SYNTHETIC'
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',DeprecationWarning)
        try:composer.get_text_iface().get_text(0,-1)
        except TypeError:pass
        else:raise AssertionError('Expected old deprecated interface collision was not reproduced')
    desktop=Desktop.__new__(Desktop);desktop.pid=child.pid
    desktop.safe=lambda: child.poll() is None  # isolated X11 fixture, not production Wayland
    ui=driver.UI.__new__(driver.UI);ui.desktop=desktop;ui.current=dict(pid=child.pid);ui.Atspi=Atspi
    ui.consent_prompts=set();observations=[];ui.record=lambda phase,**data:observations.append((phase,data))
    ui.expect_draft('SYNTHETIC draft\n')  # actual production driver method + real node
    assert ui.prompt() and len(observations)==1
    assert 'SYNTHETIC consent details' in observations[0][1]['prompt']
    child.stdin.write('close-consent\n');child.stdin.flush()
    end=time.monotonic()+3
    while ui.prompt() and time.monotonic()<end:time.sleep(.05)
    assert not ui.prompt(), 'Private synthetic window did not close'
    assert Atspi.EditableText.set_text_contents(composer,'')
    end=time.monotonic()+3
    while not ui.settled('SYNTHETIC answer',legacy=True) and time.monotonic()<end:time.sleep(.05)
    assert ui.settled('SYNTHETIC answer',legacy=True)  # real composer + transcript reads
    assert not 'get_text_iface' in (root/'scripts/ordinary_app_acceptance.py').read_text()
    print('PASS real isolated GTK4/AT-SPI: old TypeError reproduced; direct Text.get_text works; all four actual driver text-read sites pass. NOT production GTK/SDK/human acceptance.',flush=True)
finally:
    if child.poll() is None:child.terminate()
    try:out,err=child.communicate(timeout=5)
    except subprocess.TimeoutExpired:child.kill();out,err=child.communicate()
    if err:print('PRIVATE FIXTURE STDERR:',err,file=sys.stderr)
