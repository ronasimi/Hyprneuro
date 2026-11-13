"""DEFERRED until parent/user authorizes an unlocked offline GTK window.

HYPRNEURO_GTK_OFFLINE_TEST=1 /usr/bin/python3 ui/tests/pi_owner_interactive.py SESSION BINARY
No capture, service manipulation, live owners/providers/models or installed config.
All sockets/data are disposable; the existing UI's control socket is never touched.
"""
import base64
import struct
import wave
import zlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

from desktop_driver import Atspi, Desktop


def safe(session):
    fields = dict(line.split('=', 1) for line in subprocess.check_output(
        ['loginctl', 'show-session', session, '-p', 'User', '-p', 'Remote',
         '-p', 'Type', '-p', 'Active', '-p', 'LockedHint'], text=True).splitlines())
    if fields != dict(User=str(os.getuid()), Remote='no', Type='wayland', Active='yes', LockedHint='no'):
        raise RuntimeError(f'Unsafe desktop session: {fields}')
    if subprocess.run(['pgrep', '-x', 'hyprlock|swaylock|waylock|gtklock'], capture_output=True).returncode != 1:
        raise RuntimeError('Locker present/unknown')


class IsolatedDesktop(Desktop):
    def safe(self):
        safe(self.session)
        if not Path(f'/proc/{self.pid}').exists():
            raise RuntimeError('UI exited')

    def keys(self, *args):
        self.safe()
        super().keys(*args)

    def draft(self, text):
        self.safe()
        editor = 'Enter sends · Ctrl+Enter inserts a newline'
        self.click_widget('text', editor)
        self.keys('-M', 'ctrl', '-k', 'a', '-m', 'ctrl', '-d', '20', text)
        self.wait(lambda: Atspi.Text.get_text(self.find('text', editor), 0, -1) == text)

    def control(self, command):
        self.safe()
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(str(root / 'ui.sock'))
            client.sendall((command+'\n').encode())
        time.sleep(.2)


def main():
    if os.environ.get('HYPRNEURO_GTK_OFFLINE_TEST') != '1':
        raise SystemExit('BLOCKED: parent/user authorization required before any GUI fixture')
    session, binary = sys.argv[1:3]
    safe(session)  # before launching ANY fixture or GUI, even if logind says unlocked
    repo = Path(__file__).resolve().parents[2]
    global root
    root = Path.home() / 'Workspace/hyprneuro-pi-gtk-acceptance' / time.strftime('%Y%m%d-%H%M%S')
    root.mkdir(parents=True, mode=0o700)
    children, logs = [], []
    env = dict(os.environ, PYTHONPATH=str(repo/'python/src'), HYPRNEURO_PI_UI='1',
               HYPRNEURO_PI_OWNER_DIR=str(root/'owner'), HYPRNEURO_UI_SOCKET=str(root/'ui.sock'),
               HYPHARNESS_SIDECAR=str(root/'legacy.sock'), ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    # No ambient owner opt-in/activation inputs are needed by these fixtures.
    env.pop('HYPRNEURO_PI_OWNER_ENABLE', None)
    env.pop('G_DEBUG', None)

    def launch(args, name):
        safe(session)
        log = (root / name).open('w'); logs.append(log)
        p = subprocess.Popen(args, env=env, stdout=log, stderr=subprocess.STDOUT)
        children.append(p)
        return p

    def records(name):
        path = root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    try:
        launch(['node', str(repo/'ui/tests/pi_owner_fixture.mjs'), str(root/'owner'), str(root/'owner.jsonl')], 'owner.log')
        launch(['/usr/bin/python3', str(repo/'ui/tests/pi_sidecar_fixture.py'), str(root)], 'sidecar.log')
        for _ in range(100):
            safe(session)
            if (root/'owner/owner.sock').exists() and (root/'legacy.sock').exists(): break
            time.sleep(.05)
        assert (root/'owner/owner.sock').exists() and (root/'legacy.sock').exists()
        ui = launch([binary], 'gui.log')
        d = IsolatedDesktop(session, ui.pid)
        d.wait(lambda: 'MoE · off' in d.labels())
        switch = lambda: d.find('toggle button', 'MoE observed switch') or d.find('switch', 'MoE observed switch')
        assert d.wait(switch)
        # Use the actual accessible switch action, not /moe parsing, for first on.
        d.activate(switch().get_role_name(), 'MoE observed switch')
        d.wait(lambda: any('request pending' in s for s in d.labels()))
        d.wait(lambda: d.find('button', 'Deny'))
        assert 'fixture-task' in '\n'.join(Atspi.Text.get_text(n, 0, -1) for n in d.nodes(ui.pid) if n.get_role_name() == 'text')
        d.activate('button', 'Deny')
        d.wait(lambda: 'MoE · off' in d.labels())
        d.send('/moe on')
        d.wait(lambda: d.find('button', 'Allow exact action once'))
        d.activate('button', 'Allow exact action once')
        d.wait(lambda: 'MoE · on' in d.labels())
        d.send('/moe off')
        d.wait(lambda: 'MoE · off' in d.labels())
        d.send('tool')
        d.wait(lambda: d.find('button', 'Deny'))
        d.activate('button', 'Deny')
        d.wait(lambda: 'Fixture answer: tool' in d.transcript())
        assert 'tool_execution_end · FAILED' in d.transcript()
        assert 'Thinking: Fixture reasoning α' in d.transcript()
        # Assistant /moe text must not cause another control transaction.
        before = sum(r['op'] == 'on' for r in records('owner.jsonl'))
        d.send('injection')
        d.wait(lambda: '/moe on' in d.transcript())
        assert sum(r['op'] == 'on' for r in records('owner.jsonl')) == before
        # Ctrl+Enter is newline, Return submits; only one native prompt.
        d.draft('keyboard'); d.keys('-M', 'ctrl', '-k', 'Return', '-m', 'ctrl', 'second', '-k', 'Return')
        d.wait(lambda: any(r.get('text') == 'keyboard\nsecond' for r in records('owner.jsonl')))
        d.wait(lambda: 'Fixture answer: keyboard\nsecond' in d.transcript())
        # Existing native image picker/snapshot stays on legacy route, not Pi.
        image = root / 'pixel.png'
        def chunk(kind, data):
            body = kind + data
            return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body))
        image.write_bytes(b'\x89PNG\r\n\x1a\n' +
                          chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)) +
                          chunk(b'IDAT', zlib.compress(b'\x00\xff\x00\x00')) + chunk(b'IEND', b''))
        d.choose(image)
        d.wait(lambda: any('Attachment → legacy sidecar' in s for s in d.labels()))
        d.send('image baseline')
        d.wait(lambda: 'Legacy media fixture answer' in d.transcript())
        media = [r for r in records('legacy.jsonl') if r.get('action') == 'agent_chat'][-1]
        assert media['media']['mime'] == 'image/png'
        assert base64.b64decode(media['media']['data']) == image.read_bytes()
        assert not any('Fixture answer' in json.dumps(h) for h in media['history'])
        # Synthetic silent PCM WAV: native decode/play/review still gates Send.
        audio = root / 'silent.wav'
        with wave.open(str(audio), 'wb') as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(24000)
            wav.writeframes(bytes(24000 * 2 * 2))
        snapshot = audio.read_bytes()
        d.choose(audio)
        d.wait(lambda: any(s.startswith('Audio ready') for s in d.labels()))
        d.send('wav baseline')
        d.wait(lambda: any(s.startswith('Play to review') for s in d.labels()))
        assert not any(r.get('message') == 'wav baseline' for r in records('legacy.jsonl'))
        d.activate('button', 'Play')
        review = 'Use reviewed audio (play first; Send is separate)'
        d.wait(lambda: d.find('check box', review).get_state_set().contains(Atspi.StateType.SENSITIVE))
        d.wait(lambda: any(s.startswith('Audio ready') for s in d.labels()))
        d.click_widget('check box', review)
        # Replacing the source cannot mutate the reviewed in-memory snapshot.
        audio.write_bytes(b'changed source after review')
        d.send('wav baseline')
        d.wait(lambda: any(r.get('message') == 'wav baseline' for r in records('legacy.jsonl')))
        wav_request = [r for r in records('legacy.jsonl') if r.get('message') == 'wav baseline'][-1]
        assert wav_request['media']['mime'] == 'audio/wav'
        assert base64.b64decode(wav_request['media']['data']) == snapshot
        # Cancel pending on via explicit off button closes, rather than reuses, consent.
        d.send('/moe on'); d.wait(lambda: d.find('button', 'Deny'))
        d.activate('button', 'MoE off / cancel on')
        d.wait(lambda: not d.find('button', 'Deny'))
        d.wait(lambda: 'MoE · off' in d.labels())
        # Failed native turn is not presented as a successful settled answer.
        d.send('error'); d.wait(lambda: '[error: Native turn failed/aborted' in d.transcript())
        d.send('slow'); d.wait(lambda: d.find('button', 'Cancel Pi chat').get_state_set().contains(Atspi.StateType.SENSITIVE))
        d.activate('button', 'Cancel Pi chat')
        d.wait(lambda: 'MoE · failed' in d.labels())
        # Last owner socket loss is unavailable, never optimistic off/fallback.
        children[0].terminate(); children[0].wait(timeout=4)
        d.wait(lambda: 'MoE · unavailable' in d.labels())
        assert ui.poll() is None
        print('PASS actual GTK offline owner/consent/control/chat/image/keyboard/cancel/disconnect; no capture', root)
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try: p.wait(timeout=5)
                except subprocess.TimeoutExpired: p.kill(); p.wait(timeout=2)
        for log in logs: log.close()


if __name__ == '__main__':
    main()
