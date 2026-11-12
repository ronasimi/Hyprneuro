"""Opt-in actual native WAV playback/review/snapshot/send workflows.
Usage: python ui/tests/audio_file_interactive.py SESSION BINARY [--service]
--service uses the actual installed UI/sidecar and real Omni: machine lease required.
Only the previously audited synthetic speech fixture is played/sent; no recording.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time

from desktop_driver import Atspi, Desktop

repo = Path(__file__).resolve().parents[2]
root = Path.home() / 'Workspace/hyprneuro-audio' / time.strftime('native-%Y%m%d-%H%M%S')
root.mkdir(parents=True)
session, binary = sys.argv[1:3]
service = '--service' in sys.argv
unit = 'hyprneuro-ui.service'
installed = Path.home() / '.local/bin/hyprneuro-ui'
oldhash = hashlib.sha256(installed.read_bytes()).hexdigest()
pid = int(subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value']))
Desktop(session, pid).safe()
backend = ui = None
try:
    if not service:
        subprocess.run(['systemctl', '--user', 'stop', unit], check=True)
        env = dict(os.environ, PYTHONPATH=str(repo / 'python/src'), PYTHONDONTWRITEBYTECODE='1',
                   ASAN_OPTIONS='detect_leaks=0:abort_on_error=1', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                   GDK_WAYLAND_DISABLE='ext_background_effect_manager_v1')
        env.pop('G_DEBUG', None)
        backend = subprocess.Popen([str(repo / 'python/.venv/bin/python'), str(repo / '.dev/logs/reasoning_fixture.py'), str(root)],
                                   env=env, stdout=(root / 'sidecar.log').open('w'), stderr=subprocess.STDOUT)
        for _ in range(100):
            assert backend.poll() is None
            if (root / 'sidecar.sock').exists():
                break
            time.sleep(.05)
        env['HYPHARNESS_SIDECAR'] = str(root / 'sidecar.sock')
        ui = subprocess.Popen([binary], env=env, stdout=(root / 'gui.log').open('w'), stderr=subprocess.STDOUT)
        pid = ui.pid
    d = Desktop(session, pid)
    sha = hashlib.sha256(Path(f'/proc/{pid}/exe').read_bytes()).hexdigest()
    assert sha == hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    print('EXECUTED', binary, sha, root, flush=True)
    d.wait(lambda: d.find('button', 'Attach file'))
    provenance = json.loads((Path.home() / 'Workspace/hyprneuro-repair/capabilities/speech-provenance.json').read_text())
    original = Path(provenance['source']).read_bytes()
    assert hashlib.sha256(original).hexdigest() == provenance['sha256']
    source = root / 'reviewed-synthetic.wav'
    review = 'Use reviewed audio (play first; Send is separate)'
    editor = 'Enter sends · Ctrl+Enter inserts a newline'
    remove = 'Remove attachment (also removes it from submission)'

    def requests():
        path = root / 'backend-requests.jsonl'
        return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []

    def attach():
        source.write_bytes(original)
        d.choose(source)
        d.wait(lambda: any(s.startswith('Audio ready · 0.00 / 3.12 s') for s in d.labels()))
        node = d.find('check box', review)
        assert node and not node.get_state_set().contains(Atspi.StateType.SENSITIVE)
        assert any('24000 Hz · 1 ch · 74880 frames · 3.12 s' in s for s in d.labels()), d.labels()

    def sink_inputs():
        return [s for s in json.loads(subprocess.check_output(['pactl', '-f', 'json', 'list', 'sink-inputs']))
                if s.get('properties', {}).get('application.process.id') == str(pid) and not s.get('corked')]

    def play_review():
        d.activate('button', 'Play')
        d.wait(lambda: any(s.startswith('Playing audio · ') and not s.startswith('Playing audio · 0.00') for s in d.labels()))
        outputs = d.wait(sink_inputs, timeout=3)
        (root / 'actual-output-sink.json').write_text(json.dumps(outputs, indent=2))
        d.wait(lambda: d.find('check box', review).get_state_set().contains(Atspi.StateType.SENSITIVE))
        # Installed GTK labels its non-seekable memory-stream pause action Stop.
        d.activate('button', 'Stop')
        d.wait(lambda: any(s.startswith('Audio ready · ') and not s.startswith('Audio ready · 0.00') for s in d.labels()))
        d.click_widget('check box', review)
        assert d.find('check box', review).get_state_set().contains(Atspi.StateType.CHECKED)

    def no_audio():
        return not any('audio/wav' in s for s in d.labels()) and not d.find('check box', review)

    attach()
    time.sleep(.4)
    assert any(s.startswith('Audio ready · 0.00') for s in d.labels()), 'No autoplay allowed'
    d.send('Transcribe this audio exactly. Only output the spoken words.')
    d.wait(lambda: any(s.startswith('Play to review the prepared audio') for s in d.labels()))
    assert not requests()
    assert Atspi.Text.get_text(d.find('text', editor), 0, -1) == 'Transcribe this audio exactly. Only output the spoken words.'
    # Native decoder and payload both own immutable bytes; path now invalid.
    source.write_bytes(b'changed after review; never send or decode these bytes')
    play_review()
    assert not requests(), 'Playback/review is never submission'
    # Picker Cancel pauses playback, preserves the immutable reviewed snapshot/draft.
    dialog = d.picker()
    d.activate('button', 'Cancel', dialog['pid'])
    d.wait(lambda: not any(c['title'] == dialog['title'] for c in d.clients()))
    assert not no_audio() and d.find('check box', review).get_state_set().contains(Atspi.StateType.CHECKED)
    before = d.transcript()
    d.send('Transcribe this audio exactly. Only output the spoken words.')
    d.wait(lambda: 'Hyprneuro - Local' in d.labels() and no_audio() and d.transcript() != before, timeout=40)
    if service:
        assert 'The quick brown fox jumps over the lazy dog.' in d.transcript()[len(before):], d.transcript()
    else:
        req = requests()
        assert len(req) == 1
        assert req[-1]['messages'][-1]['content'][1] == {
            'type': 'input_audio', 'input_audio': {'data': base64.b64encode(original).decode(), 'format': 'wav'}}
        assert all('image_url' not in p for p in req[-1]['messages'][-1]['content'])
    print('PASS actual playback timestamp + uncorked sink, pause/review, no autoplay/send, picker Cancel, immutable native payload', flush=True)

    # Actual native memory-stream EOS resets position to zero and enables Play;
    # it does not leave the final timestamp at duration. Check two real replays.
    attach()
    for _ in range(2):
        d.activate('button', 'Play')
        d.wait(lambda: any(s.startswith('Playing audio') and not s.startswith('Playing audio · 0.00') for s in d.labels()))
        d.wait(lambda: d.find('button', 'Play') and any(s.startswith('Audio ready · 0.00') for s in d.labels()), timeout=6)
    d.activate('button', remove);d.wait(no_audio)
    attach();d.activate('button', 'Play')
    d.wait(lambda: any(s.startswith('Playing audio') for s in d.labels()))
    d.control('hide');d.control('show')
    d.wait(no_audio)
    d.wait(lambda: not sink_inputs())
    assert not d.find('check box', review)
    if not service:
        # Real sidecar receives no media after remove/hide, exact error cleanup.
        d.send('removed audio');d.wait(lambda: len(requests()) == 2 and 'Hyprneuro - Local' in d.labels())
        assert isinstance(requests()[-1]['messages'][-1]['content'], str)
        attach();play_review();d.send('disconnect')
        d.wait(lambda: 'Hyprneuro · error' in d.labels() and no_audio())
        d.send('recovered');d.wait(lambda: len(requests()) == 4 and 'Hyprneuro - Local' in d.labels())
        assert isinstance(requests()[-1]['messages'][-1]['content'], str)
    # Actual picker malformed/type/duration refusal, no recording or synthesis.
    invalid = root / 'invalid.wav'
    for data in [original[:-1], original[:24] + struct.pack('<I', 7999) + original[28:],
                 original[:20] + b'\x03\x00' + original[22:]]:
        invalid.write_bytes(data);d.choose(invalid)
        d.wait(lambda: any(s.startswith('Rejected: static PNG') for s in d.labels()))
        assert no_audio()
    (root / 'transcript.txt').write_text(d.transcript())
    (root / 'final-labels.json').write_text(json.dumps(d.labels(), indent=2))
    assert service or ui.poll() is None
    print('PASS native WAV actual GTK', 'INSTALLED LOCAL OMNI' if service else 'SANITIZED FIXTURE',
          'remove/hide/sink cleanup, malformed/rate/codec rejection; error/recovery tested in fixture mode', flush=True)
finally:
    if ui is not None:
        ui.terminate();ui.wait(timeout=10)
    if backend is not None:
        backend.terminate();backend.wait(timeout=10)
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == oldhash
    if not service:
        subprocess.run(['systemctl', '--user', 'start', unit], check=True)
