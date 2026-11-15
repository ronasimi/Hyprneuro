"""Opt-in actual widget fixture; run from repository root under machine lease."""
from pathlib import Path
import os,subprocess,tempfile
with tempfile.TemporaryDirectory(prefix='hn-widgets-',dir='/home/ron/Workspace') as d:
 root=Path(d);env=dict(os.environ)
 for name in list(env):
  if name.startswith(('HYPRNEURO_','HYPHARNESS_')):env.pop(name)
 for name in ['DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE','SWAYSOCK','DISPLAY']:env.pop(name,None)
 for name,folder in [('XDG_RUNTIME_DIR','runtime'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state'),('HOME','home')]:p=root/folder;p.mkdir(mode=0o700);env[name]=str(p)
 flags=subprocess.check_output(['pkg-config','--cflags','--libs','gtk4','gtk4-layer-shell-0','json-glib-1.0','gio-unix-2.0'],text=True).split()
 wrappers=['init_for_window','set_namespace','set_layer','set_exclusive_zone','set_anchor','set_margin','set_keyboard_mode']
 binary=root/'fixture-ui'
 subprocess.run(['cc','-O0','-o',str(binary),'ui/tests/ordinary_widgets.c',*flags,'-lm','-lX11','-Wl,--wrap=g_dbus_connection_call_sync','-Wl,--wrap=g_subprocess_launcher_new',*['-Wl,--wrap=gtk_layer_'+x for x in wrappers]],check=True,timeout=40)
 env.update(GDK_BACKEND='x11',GSK_RENDERER='cairo',GTK_A11Y='atspi',HN_PRIVATE_ATSPI_FIXTURE='1',HN_ORDINARY_WIDGET_BINARY=str(binary),PYTHONDONTWRITEBYTECODE='1')
 result=subprocess.run(['/usr/bin/dbus-run-session','--','/usr/bin/xvfb-run','-a','/usr/bin/python','python/tests/ordinary_widgets_fixture.py','--isolated-bus'],env=env,timeout=45)
 raise SystemExit(result.returncode)
