"""Opt-in real Wayland GTK -> sidecar -> fragmented SSE regression.
No screenshots except this test's UI rectangle, no captures for inference.
Requires an explicitly identified active unlocked local session (argument 1).
Run: python ui/tests/metrics_interactive.py SESSION_ID BINARY [--thinking]
--thinking runs telemetry/thinking/MDI size control only, not the separate portal media workflow.
--no-screenshots skips captures (attribute/payload assertions still run).
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import gi

gi.require_version('Atspi', '2.0')
from gi.repository import Atspi, GLib

repo = Path(__file__).resolve().parents[2]
root = Path.home() / 'Workspace/hyprneuro-repair' / time.strftime('gui-%Y%m%d-%H%M%S')
root.mkdir(parents=True)
session, binary = sys.argv[1:3]

def unlocked():
    fields = dict(line.split('=', 1) for line in subprocess.check_output(
        ['loginctl', 'show-session', session, '-p', 'User', '-p', 'Remote', '-p', 'Type',
         '-p', 'Active', '-p', 'LockedHint'], text=True).splitlines())
    assert fields == {'User': str(os.getuid()), 'Remote': 'no', 'Type': 'wayland',
                      'Active': 'yes', 'LockedHint': 'no'}, fields
    lockers = subprocess.run(['pgrep', '-x', 'hyprlock|swaylock|waylock|gtklock'], capture_output=True)
    assert lockers.returncode == 1, 'Locker present or unknown process check'

def wait(check, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        assert ui.poll() is None, (ui.returncode, (root / 'gui.log').read_text())
        try:
            result = check()
        except GLib.GError as exc:
            # GTK invalidates accessibility objects when attachment rows disappear.
            # Retry the whole bounded snapshot, never count a stale row as success.
            print("Atspi snapshot invalidated; retry:", exc, flush=True)
            time.sleep(.08)
            continue
        if result:
            return result
        time.sleep(.08)
    raise AssertionError('Timeout: ' + str(labels()))

def nodes():
    app = next((a for a in Atspi.get_desktop(0) if a.get_process_id() == ui.pid), None)
    def walk(node):
        yield node
        for child in node:
            if child:
                yield from walk(child)
    return list(walk(app)) if app else []

def labels():
    return [n.get_name() for n in nodes() if n.get_role_name() == 'label']

def find(role, name):
    return next((n for n in nodes() if n.get_role_name() == role and n.get_name() == name), None)

def click(node):
    unlocked()
    data = json.loads(subprocess.check_output(['hyprctl', '-j', 'layers']))
    layer = next(l for m in data.values() for ls in m['levels'].values()
                 for l in ls if l['pid'] == ui.pid)
    assert layer['namespace'] == 'hyprneuro'
    # GTK/Wayland Atspi exposes zero global coordinates for layer surfaces.
    # Hit-test only this PID's compositor-reported rectangle, never the desktop.
    dx, dy = {'Enter sends · Ctrl+Enter inserts a newline': (230, layer['h'] - 84),
              'Settings': (21, layer['h'] - 30),
              'Attach file': (38, layer['h'] - 84),
              '← Back': (55, 30),
              'arrow': (layer['w'] - 21, 21)}['arrow' if 'transcript:' in node.get_name() else node.get_name()]
    subprocess.run(['wdotool', '--backend', 'wlr-protocols', 'mousemove',
                    str(layer['x'] + dx), str(layer['y'] + dy)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(['wdotool', '--backend', 'wlr-protocols', 'click', '1'], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(.15)

def send(text):
    unlocked()
    click(wait(lambda: find('text', 'Enter sends · Ctrl+Enter inserts a newline')))
    subprocess.run(['wtype', '-M', 'ctrl', '-k', 'a', '-m', 'ctrl', '-d', '30', text], check=True)
    editor = find('text', 'Enter sends · Ctrl+Enter inserts a newline')
    wait(lambda: Atspi.Text.get_text(editor, 0, -1) == text, timeout=3)
    subprocess.run(['wtype', '-k', 'Return'], check=True)

def shot(name):
    if '--no-screenshots' in sys.argv:
        return
    unlocked()
    data = json.loads(subprocess.check_output(['hyprctl', '-j', 'layers']))
    layer = next(l for m in data.values() for levels in m['levels'].values()
                 for l in levels if l['pid'] == ui.pid)
    assert layer['namespace'] == 'hyprneuro', layer
    assert layer['w'] < 1000 and layer['y'] >= 0 and layer['h'] <= 1080, layer
    subprocess.run(['wdotool', '--backend', 'wlr-protocols', 'mousemove', str(layer['x'] + layer['w'] // 2), str(layer['y'] + layer['h'] - 140)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(.2)
    path = Path.home() / 'Workspace/screenshots' / time.strftime('%Y-%m-%d') / f'{root.name}-{name}.png'
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['grim', '-g', f"{layer['x']},{layer['y']} {layer['w']}x{layer['h']}", str(path)], check=True)
    print(path, flush=True)

unlocked()
was_active = subprocess.run(['systemctl', '--user', 'is-active', '--quiet', 'hyprneuro-ui.service']).returncode == 0
subprocess.run(['systemctl', '--user', 'stop', 'hyprneuro-ui.service'], check=True)
env = dict(os.environ, PYTHONPATH=str(repo / 'python/src'), PYTHONDONTWRITEBYTECODE='1')
backend = subprocess.Popen([sys.executable, str(repo / '.dev/logs/reasoning_fixture.py'), str(root)],
                           env=env, stdout=(root / 'sidecar.log').open('w'), stderr=subprocess.STDOUT)
ui = None
try:
    for _ in range(100):
        if (root / 'sidecar.sock').exists():
            break
        time.sleep(.05)
    env.update(HYPHARNESS_SIDECAR=str(root / 'sidecar.sock'),
               ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    env.pop('G_DEBUG', None)  # Existing GTK warnings remain logged, not hidden.
    ui = subprocess.Popen([binary], env=env, stdout=(root / 'gui.log').open('w'), stderr=subprocess.STDOUT)
    import hashlib
    executed = hashlib.sha256(Path(f'/proc/{ui.pid}/exe').read_bytes()).hexdigest()
    assert executed == hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    print('EXECUTED BINARY SHA256', executed, binary, flush=True)
    wait(lambda: find('button', 'Send'))
    wait(lambda: any('cpu ' in s for s in labels()))
    settings = find('button', 'Settings')
    arrow = next(n for n in nodes() if n.get_role_name() == 'button' and 'transcript:' in n.get_name())
    def size(node):
        rect = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
        return rect.width, rect.height
    assert size(settings) == size(arrow) == (16, 16), (size(settings), size(arrow))
    assert arrow.get_name() in ('Expand transcript: Normal → Expanded', 'Restore transcript: Expanded → Normal')
    click(find('text', 'Enter sends · Ctrl+Enter inserts a newline'))
    for expected in ('Restore transcript: Expanded → Normal', 'Expand transcript: Normal → Expanded'):
        unlocked()
        subprocess.run(['wtype','-M','ctrl','-k','Tab','-m','ctrl'],check=True)
        arrow = wait(lambda: find('button',expected))
        # Both states must retain an actual visible transcript text node.
        assert any(n.get_role_name()=='text' and not n.get_name() and n.get_state_set().contains(Atspi.StateType.VISIBLE) for n in nodes())
    for _ in range(4):
        before = arrow.get_name()
        click(arrow)
        arrow = wait(lambda: next((n for n in nodes() if n.get_role_name() == 'button' and 'transcript:' in n.get_name() and n.get_name() != before), None))
    shot('matching-transparent-icon-actions')
    assert arrow.get_name() == 'Expand transcript: Normal → Expanded'
    print('PASS MDI size control/Settings 16x16 geometry and Normal/Expanded overlay cycle (glyph/color require rendered inspection)', flush=True)
    for message, expected in [
        ('metrics-zero', 'Prefill 12.5 t/s · Decode 7.0 t/s · Hit 0.0% · Full —'),
        ('metrics-hit', 'Prefill 12.5 t/s · Decode 7.0 t/s · Hit 80.0% · Full —'),
        ('metrics-unknown', 'Prefill — · Decode — · Hit — · Full —'),
        ('disconnect', 'Inference failed · Full —'),
        ('metrics-zero', 'Prefill 12.5 t/s · Decode 7.0 t/s · Hit 0.0% · Full —')]:
        send(message)
        if message.startswith('metrics-'):
            wait(lambda: 'Inference pending · Full —' in labels())
        wait(lambda: expected in labels())
        if message == 'metrics-zero':
            assert 'Prompt total 20 · evaluated 20 · cached 0' in find('label', expected).get_description()
        time.sleep(2.3)  # monitoring must poll again without replacing metrics
        assert expected in labels(), labels()
        assert any('cpu ' in s for s in labels()), labels()
        shot(message)
        print('PASS', message, expected, flush=True)
    def transcript():
        candidates = [(n, Atspi.Text.get_text(n, 0, -1)) for n in nodes()
                      if n.get_role_name() == 'text' and not n.get_name()]
        return candidates[0]
    for message, answer, reasoning in [
        ('native', 'Ordinary answer stays blue and upright ✓.', 'Fixture: checking α and β.'),
        ('delimiters', 'Delimiter answer ✓.', 'Fixture delimiter reasoning α.'),
        ('reasoning-only', '', 'Only fixture reasoning α.'),
        ('orphan-close', 'BeforeAfter', ''),
        ('disconnect', None, 'Interrupted fixture reasoning'),
        ('plain', 'Plain fixture answer ✓.', '')]:
        send(message)
        wait(lambda: ('Hyprneuro · error' if answer is None else 'Hyprneuro - Local') in labels())
        node, content = transcript()
        assert '<think>' not in content and '</think>' not in content, content
        if reasoning:
            assert reasoning in content, content
            offset = content.rfind(reasoning)
            attrs = Atspi.Text.get_attribute_run(node, offset, False)
            print('REASONING ATTRIBUTES', message, attrs, flush=True)
            # GTK's exported attributes are independently checked where available.
            attributes = attrs[0]
            assert attributes.get('style') == 'italic', attributes
            assert attributes.get('weight') == '400', attributes
            assert attributes.get('fg-color') == '47288,47288,47288', attributes
        user_attrs = Atspi.Text.get_attribute_run(node, content.rfind('you: '), False)[0]
        assert user_attrs.get('style', 'normal') == 'normal', user_attrs
        if answer is None:
            error_attrs = Atspi.Text.get_attribute_run(node, content.rfind('[error:'), False)[0]
            assert error_attrs.get('style', 'normal') == 'normal', error_attrs
        if answer:
            assert answer in content, content
            attrs = Atspi.Text.get_attribute_run(node, content.rfind(answer), False)[0]
            assert attrs.get('style', 'normal') == 'normal', attrs
            assert attrs.get('fg-color') != '47288,47288,47288', attrs
        shot('thinking-' + message)
    req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
    native = next(i for i, r in enumerate(req) if r['messages'][-1]['content'] == 'native')
    assert req[native + 1]['messages'][-2]['content'] == 'Ordinary answer stays blue and upright ✓.'
    assert req[native + 2]['messages'][-2]['content'] == 'Delimiter answer ✓.'
    assert req[native + 3]['messages'][-2]['content'] == ''  # reasoning-only answer
    assert req[-1]['messages'][-2]['content'] == 'BeforeAfter'  # failed turn excluded
    print('PASS thinking native/split delimiters/only/orphan/error/reset; exact GTK attributes; answer-only history', flush=True)
    if '--thinking' in sys.argv:
        print('PASS focused telemetry/thinking/MDI-size suite; media workflow not selected', flush=True)
        raise SystemExit(0)
    # Actual Ctrl+Return and Return path, exact backend payload independently checked.
    click(find('text', 'Enter sends · Ctrl+Enter inserts a newline'))
    subprocess.run(['wtype', 'line one', '-M', 'ctrl', '-k', 'Return', '-m', 'ctrl', 'line two', '-k', 'Return'], check=True)
    wait(lambda: 'Hyprneuro - Local' in labels())
    req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
    assert req[-1]['messages'][-1]['content'] == 'line one\nline two', req[-1]
    # Native reasoning remains visually distinct; answers alone enter history.
    send('native');wait(lambda: 'Hyprneuro - Local' in labels());shot('reasoning')
    click(find('button', 'Settings'));time.sleep(.4);shot('settings')
    click(wait(lambda: find('button', '← Back')))
    send('metrics-zero');wait(lambda: 'Hit 0.0%' in ' '.join(labels()))
    req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
    assert req[-1]['messages'][-2]['content'] == 'Ordinary answer stays blue and upright ✓.'
    import base64
    def choose(path):
        click(find('button', 'Attach file'))
        time.sleep(.6)
        clients = json.loads(subprocess.check_output(['hyprctl', '-j', 'clients']))
        dialog = next(c for c in clients if c['title'].startswith(('Select static image', 'Select attachment')))
        x, y = dialog['at']; w, h = dialog['size']
        subprocess.run(['wdotool', '--backend', 'wlr-protocols', 'mousemove', str(x + 250), str(y + 180)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['wdotool', '--backend', 'wlr-protocols', 'click', '1'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(['wtype', '-M', 'ctrl', '-k', 'l', '-m', 'ctrl', '-s', '300',
                        '-M', 'ctrl', '-k', 'a', '-m', 'ctrl', '-s', '200',
                        '-d', '15', str(path), '-s', '500', '-k', 'Return'], check=True)
        wait(lambda: not any(c['title'].startswith(('Select static image', 'Select attachment')) for c in
                             json.loads(subprocess.check_output(['hyprctl', '-j', 'clients']))), timeout=8)
        time.sleep(.3)
    fixtures = Path.home() / 'Workspace/hyprneuro-audit/fixtures'
    for name in ['unsupported.mp4']:
        unlocked(); choose(fixtures / name)
        wait(lambda: any(s.startswith('Rejected: static PNG') for s in labels()))
        send('rejected ' + name);wait(lambda: 'Hyprneuro - Local' in labels())
        req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
        assert isinstance(req[-1]['messages'][-1]['content'], str)
    for extension, mime in [('png', 'image/png'), ('jpg', 'image/jpeg'), ('webp', 'image/webp')]:
        path = fixtures / ('red.' + extension)
        unlocked();choose(path)
        wait(lambda: any(mime in s for s in labels()))
        shot('reviewed-' + extension)
        send('reviewed ' + extension);wait(lambda: 'Hyprneuro - Local' in labels())
        req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
        url = req[-1]['messages'][-1]['content'][1]['image_url']['url']
        assert url.startswith('data:' + mime + ';base64,')
        assert base64.b64decode(url.split(',', 1)[1]) == path.read_bytes()
    print('PASS actual portal MP4 rejection and PNG/JPEG/WebP previews -> exact snapshot bytes through real sidecar', flush=True)
    print('PASS actual GTK keyboard, reasoning/history, Settings/Back, persistent separate telemetry; root', root, flush=True)
finally:
    if ui is not None:
        ui.terminate();ui.wait(timeout=10)
    backend.terminate();backend.wait(timeout=10)
    if was_active:
        subprocess.run(['systemctl', '--user', 'start', 'hyprneuro-ui.service'], check=True)
