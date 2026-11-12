"""Explicit-click Screenshot-portal capability/cancellation probe, NOT a feature.
No image is displayed or sent. Portal-owned files are deleted on response.
Outputs: stdout under ~/Workspace. Never invokes grim/PipeWire directly.
"""
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
from urllib.parse import unquote, urlparse
import uuid

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk

runtime = Path(os.environ['XDG_RUNTIME_DIR'])
session = os.environ.get('XDG_SESSION_ID', '')
loop = GLib.MainLoop()
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
request_path = None
subscription = None
start = 0
baseline = None


def scene():
    if not session.isalnum():
        raise RuntimeError('Missing trusted session')
    out = subprocess.check_output(['loginctl', 'show-session', session, '-p', 'User', '-p', 'Remote', '-p', 'Type', '-p', 'Active', '-p', 'LockedHint'], timeout=3, text=True)
    values = dict(line.split('=', 1) for line in out.splitlines())
    if values != {'User': str(os.getuid()), 'Remote': 'no', 'Type': 'wayland', 'Active': 'yes', 'LockedHint': 'no'}:
        raise RuntimeError('Session protection not established')
    def query(name):
        return json.loads(subprocess.check_output(['hyprctl', '-j', name], timeout=3))
    monitors = query('monitors')
    workspaces = {m[k]['address'] for m in monitors for k in ('activeWorkspace', 'specialWorkspace') if m.get(k, {}).get('address')}
    visible = [c for c in query('clients') if c.get('mapped') and not c.get('hidden') and (c.get('workspace', {}).get('address') in workspaces or c.get('pinned'))]
    excluded = {'keepassxc','org.keepassxc.keepassxc','bitwarden','1password','seahorse','hyprlock','swaylock','waylock','gtklock'}
    settings = Path.home()/'.config/hyprneuro/settings.json'
    if settings.exists():
        excluded.update(json.loads(settings.read_text()).get('excluded_apps', []))
    for c in visible:
        app = c.get('class', '').lower()
        title = c.get('title', '').lower()
        if not app or any(e in app for e in excluded) or any(t in title for t in ('incognito', 'private browsing', 'password', 'unlock')):
            raise RuntimeError('Sensitive/unknown visible client; capture denied')
    return [(c['address'], c['class'], c.get('title'), c.get('at'), c.get('size')) for c in visible]


def cleanup(uri):
    parsed = urlparse(uri)
    if parsed.scheme != 'file' or parsed.netloc:
        raise RuntimeError('Unsafe portal URI, not deleting arbitrary file')
    path = Path(unquote(parsed.path))
    if path.parent not in (runtime, runtime/'hypr') or not path.name.startswith('xdph_screenshot_') or path.suffix != '.png':
        raise RuntimeError(f'Unrecognized portal temp file; cleanup BLOCKED: {path}')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError('Unsafe portal file')
    path.unlink()
    print('DELETED', path, flush=True)


def response(connection, sender, path, iface, sig, parameters):
    global request_path
    code, results = parameters.unpack()
    print('RESPONSE', code, results, flush=True)
    if results.get('uri'):
        try:
            print('SCENE_STABLE', scene() == baseline, flush=True)
        finally:
            cleanup(results['uri'])
    request_path = None
    label.set_text(f'Portal response {code}; any returned image deleted. Not an enabled feature.')


def close_request(*args):
    if request_path:
        print('CLOSE_REQUEST', request_path, flush=True)
        try:
            reply = bus.call_sync('org.freedesktop.portal.Desktop', request_path,
                'org.freedesktop.portal.Request', 'Close', None, None, Gio.DBusCallFlags.NONE, 2000, None)
            print('CLOSE_REPLY', reply, flush=True)
        except GLib.Error as error:
            print('CLOSE_ERROR', error.message, flush=True)
        label.set_text('Request.Close sent. Probe cancellation/child/file cleanup externally.')
    return GLib.SOURCE_REMOVE


def clicked(button, cancel):
    global request_path, subscription, start, baseline
    if request_path:
        return
    try:
        baseline = scene()
    except Exception as error:
        label.set_text(str(error));print('DENIED', str(error), flush=True);return
    start = time.time()
    token = 'hyprneuro_probe_' + uuid.uuid4().hex
    sender = bus.get_unique_name()[1:].replace('.', '_')
    request_path = f'/org/freedesktop/portal/desktop/request/{sender}/{token}'
    if subscription:
        bus.signal_unsubscribe(subscription)
    subscription = bus.signal_subscribe('org.freedesktop.portal.Desktop',
        'org.freedesktop.portal.Request', 'Response', request_path, None,
        Gio.DBusSignalFlags.NONE, response)
    options = {'handle_token': GLib.Variant('s', token), 'interactive': GLib.Variant('b', True), 'modal': GLib.Variant('b', False)}
    def called(connection, result):
        try:
            returned = connection.call_finish(result).unpack()[0]
            print('HANDLE', returned, flush=True)
            if returned != request_path:
                print('HANDLE_MISMATCH', flush=True)
                close_request()
        except GLib.Error as error:
            print('REQUEST_ERROR', error.message, flush=True)
    bus.call('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
        'org.freedesktop.portal.Screenshot', 'Screenshot', GLib.Variant('(sa{sv})', ('', options)),
        GLib.VariantType.new('(o)'), Gio.DBusCallFlags.NONE, 5000, None, called)
    label.set_text('Interactive Screenshot portal requested; no image exposure or inference.')
    print('CLICKED', 'auto-cancel' if cancel else 'interactive', flush=True)
    if cancel:
        GLib.timeout_add_seconds(3, close_request)


Gtk.init()
window = Gtk.Window(title='Hyprneuro explicit Screenshot portal probe')
window.set_default_size(720, 180)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
box.set_margin_top(12);box.set_margin_bottom(12);box.set_margin_start(12);box.set_margin_end(12)
label = Gtk.Label(label='Capability probe only. Explicit click required. No image exposed/sent.')
box.append(label)
for title, cancel in [('Request interactive Screenshot portal', False), ('Request; auto-Cancel in 3 seconds (cleanup probe)', True)]:
    button = Gtk.Button(label=title)
    button.connect('clicked', clicked, cancel)
    box.append(button)
button = Gtk.Button(label='Cancel current portal request')
button.connect('clicked', close_request)
box.append(button)
window.set_child(box)
def quit_probe(*args):
    close_request()
    loop.quit()
    return True
window.connect('close-request', quit_probe)
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, quit_probe)
window.present()
print('READY', os.getpid(), flush=True)
loop.run()
