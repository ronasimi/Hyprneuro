"""External adapter: only Desktop methods reachable by the ordinary driver.
Managed db8 source stays exact. No selection, security, key or pointer additions.
"""
import os,socket,time
from pathlib import Path
from apply_app_release import desktop_safe
from command_budget import timeout

def bounded_desktop(base,session,pid,deadline):
    class BoundedDesktop(base):
        def safe(self):
            desktop_safe(self.session,deadline=deadline)
            if not Path(f'/proc/{self.pid}').exists():raise RuntimeError('UI exited')
        def wait(self,check,timeout=8):
            end=min(time.monotonic()+timeout,deadline) if deadline is not None else time.monotonic()+timeout
            return super().wait(check,timeout=max(0,end-time.monotonic()))
        def control(self,command):
            self.safe()
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(timeout(deadline))
                client.connect(str(Path(os.environ['XDG_RUNTIME_DIR'])/'hyprneuro/ui.sock'))
                client.sendall((command+'\n').encode())
            time.sleep(.2)
    return BoundedDesktop(session,pid)
