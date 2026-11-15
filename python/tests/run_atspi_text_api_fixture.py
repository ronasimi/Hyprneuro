"""Opt-in private GTK API regression: run under hold machine from repository root.
No production UI restart/input or inference. Existing Xvfb/D-Bus tools only.
"""
from pathlib import Path
import os,subprocess,tempfile,sys
sys.path.insert(0,'/home/ron/Workspace/hn-grant-565d896/staged')
from apply_app_release import desktop_safe
session=subprocess.check_output(['loginctl','show-user',str(os.getuid()),'-p','Display','--value'],text=True).strip();desktop_safe(session)
with tempfile.TemporaryDirectory(prefix='hn-atspi-',dir='/home/ron/Workspace') as d:
 root=Path(d);env=dict(os.environ)
 for name in ['DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE','SWAYSOCK','DISPLAY']:env.pop(name,None)
 for name,folder in [('XDG_RUNTIME_DIR','runtime'),('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_STATE_HOME','state')]:
  path=root/folder;path.mkdir(mode=0o700);env[name]=str(path)
 env.update(GDK_BACKEND='x11',GSK_RENDERER='cairo',GTK_USE_PORTAL='0',GIO_USE_VFS='local',GTK_A11Y='atspi',HN_PRIVATE_ATSPI_FIXTURE='1',PYTHONDONTWRITEBYTECODE='1')
 command=['/usr/bin/dbus-run-session','--','/usr/bin/xvfb-run','-a','/usr/bin/python','-W','error','python/tests/atspi_text_api_fixture.py','--isolated-bus']
 result=subprocess.run(command,env=env,timeout=40)
 desktop_safe(session);raise SystemExit(result.returncode)
