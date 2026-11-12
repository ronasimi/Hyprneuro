"""Opt-in actual local GTK driver; no screenshots, capture or compositor edits.

AT-SPI activations use the actual widget's public action. Keyboard entry is
verified before submission; stale accessibility trees are retried as snapshots.
Never infer a send completed from a previous turn's status label.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import time

import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi, GLib


class Desktop:
    def __init__(self, session, pid):
        self.session, self.pid = session, pid
        self.safe()

    def safe(self):
        fields = dict(line.split('=', 1) for line in subprocess.check_output(
            ['loginctl', 'show-session', self.session, '-p', 'User', '-p', 'Remote',
             '-p', 'Type', '-p', 'Active', '-p', 'LockedHint'], text=True).splitlines())
        assert fields == dict(User=str(os.getuid()), Remote='no', Type='wayland',
                              Active='yes', LockedHint='no'), fields
        assert subprocess.run(['pgrep', '-x', 'hyprlock|swaylock|waylock|gtklock'],
                              capture_output=True).returncode == 1, 'Locker present or unknown'
        assert Path(f'/proc/{self.pid}').exists(), 'UI exited'

    def wait(self, check, timeout=8):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.safe()
            try:
                value = check()
                if value:
                    return value
            except GLib.GError as exc:
                print('Stale AT-SPI snapshot; retry:', exc, flush=True)
            time.sleep(.08)
        raise AssertionError('Timed out waiting for actual GTK state')

    @staticmethod
    def nodes(pid):
        app = next((a for a in Atspi.get_desktop(0) if a.get_process_id() == pid), None)
        def walk(n):
            yield n
            for c in n:
                if c:
                    yield from walk(c)
        return list(walk(app)) if app else []

    def find(self, role, name, pid=None):
        return next((n for n in self.nodes(pid or self.pid)
                     if n.get_role_name() == role and n.get_name() == name), None)

    def labels(self):
        return [n.get_name() for n in self.nodes(self.pid) if n.get_role_name() == 'label']

    def activate(self, role, name, pid=None):
        self.safe()
        def action():
            node = self.find(role, name, pid)
            if not node:
                return False
            actions = node.get_action_iface()
            names = [actions.get_action_name(i) for i in range(actions.get_n_actions())] if actions else []
            assert len(names) == 1, (role, name, names)
            assert actions.do_action(0), (role, name)
            return True
        self.wait(action)
        time.sleep(.15)

    def click_widget(self, role, name):
        node = self.wait(lambda: self.find(role, name))
        r = node.get_component_iface().get_extents(Atspi.CoordType.WINDOW)
        l = self.layer()
        # Actual GTK WINDOW extents are panel-content-local on these layers.
        x, y = 13 + r.x + r.width // 2, 13 + r.y + r.height // 2
        assert r.width > 0 and r.height > 0 and 0 < x < l['w'] and 0 < y < l['h'], (role, name, x, y, l)
        self.pointer(l['x'] + x, l['y'] + y)

    def layer(self):
        data = json.loads(subprocess.check_output(['hyprctl', '-j', 'layers']))
        layer = next(l for m in data.values() for levels in m['levels'].values()
                     for l in levels if l['pid'] == self.pid)
        assert layer['namespace'] == 'hyprneuro', layer
        return layer

    def pointer(self, x, y):
        self.safe()
        for args in [('mousemove', str(x), str(y)), ('click', '1')]:
            subprocess.run(['wdotool', '--backend', 'wlr-protocols', *args], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(.15)

    @staticmethod
    def keys(*args):
        subprocess.run(['wtype', *args], check=True)

    def draft(self, text):
        self.safe()
        l = self.layer()
        self.pointer(l['x'] + 230, l['y'] + l['h'] - 84)
        self.keys('-M', 'ctrl', '-k', 'a', '-m', 'ctrl', '-d', '20', text)
        self.wait(lambda: Atspi.Text.get_text(self.find('text', 'Enter sends · Ctrl+Enter inserts a newline'),
                                            0, -1) == text)

    def send(self, text):
        self.draft(text)
        self.safe()
        self.keys('-k', 'Return')

    def control(self, command):
        self.safe()
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprneuro/ui.sock'))
            client.sendall((command + '\n').encode())
        time.sleep(.2)

    @staticmethod
    def clients():
        return json.loads(subprocess.check_output(['hyprctl', '-j', 'clients']))

    def picker(self):
        self.activate('button', 'Attach file')
        return self.wait(lambda: next((c for c in self.clients()
                                       if c['title'].startswith(('Select static image', 'Select attachment'))), None))

    def choose(self, path):
        dialog = self.picker()
        # Re-read after the portal's opening animation; focus is independently
        # verified. GTK3 Recent mode does not reliably expose Ctrl+L here;
        # its '/' path-entry binding is observed to create the real location box.
        time.sleep(.4)
        dialog = next(c for c in self.clients() if c['pid'] == dialog['pid'] and c['title'] == dialog['title'])
        self.pointer(dialog['at'][0] + 250, dialog['at'][1] + 180)
        self.wait(lambda: json.loads(subprocess.check_output(['hyprctl', '-j', 'activewindow']))['pid'] == dialog['pid'])
        self.keys('/')
        # Wait for GTK3's location entry, not a fixed portal timing assumption.
        def location():
            return next((n for n in self.nodes(dialog['pid'])
                         if n.get_role_name() == 'text' and n.get_state_set().contains(Atspi.StateType.FOCUSED)), None)
        self.wait(location)
        self.keys('-M', 'ctrl', '-k', 'a', '-m', 'ctrl', '-d', '15', str(path))
        self.wait(lambda: Atspi.Text.get_text(location(), 0, -1) == str(path))
        self.activate('button', 'Open', dialog['pid'])
        self.wait(lambda: not any(c['pid'] == dialog['pid'] and c['title'] == dialog['title']
                                  for c in self.clients()))

    def transcript(self):
        return next(Atspi.Text.get_text(n, 0, -1) for n in self.nodes(self.pid)
                    if n.get_role_name() == 'text' and not n.get_name())
