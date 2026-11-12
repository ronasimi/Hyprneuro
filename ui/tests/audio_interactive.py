"""Actual GTK missing-decoder gate + image regression, not an audio success claim.
Usage: python ui/tests/audio_interactive.py SESSION BINARY [--live]
Live requires a machine lease. No packages/capture/model configuration changes.
Outputs retained under Workspace, including failed runs. Cleanup only restarts the
current installed service; it never replaces the installed executable.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from desktop_driver import Desktop

repo = Path(__file__).resolve().parents[2]
root = Path.home() / 'Workspace/hyprneuro-audio' / time.strftime('gui-%Y%m%d-%H%M%S')
root.mkdir(parents=True)
session, binary = sys.argv[1:3]
service = '--service' in sys.argv
live = '--live' in sys.argv or service
original_pid = int(subprocess.check_output(['systemctl', '--user', 'show', 'hyprneuro-ui.service', '-p', 'MainPID', '--value']))
Desktop(session, original_pid).safe()
installed = Path.home() / '.local/bin/hyprneuro-ui'
installed_before = hashlib.sha256(installed.read_bytes()).hexdigest()
if not service:
    subprocess.run(['systemctl', '--user', 'stop', 'hyprneuro-ui.service'], check=True)

env = dict(os.environ, PYTHONPATH=str(repo / 'python/src'), PYTHONDONTWRITEBYTECODE='1')
backend = None if service else subprocess.Popen([str(repo / 'python/.venv/bin/python'), str(repo / '.dev/logs/reasoning_fixture.py'), str(root),
                            *(['--live'] if live else [])], env=env, stdout=(root / 'sidecar.log').open('w'), stderr=subprocess.STDOUT)
ui = None
try:
    for _ in range(0 if service else 100):
        if (root / 'sidecar.sock').exists():
            break
        assert backend.poll() is None
        time.sleep(.05)
    env.update(HYPHARNESS_SIDECAR=str(root / 'sidecar.sock'), ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
               GDK_WAYLAND_DISABLE='ext_background_effect_manager_v1')
    env.pop('G_DEBUG', None)  # Existing GTK warnings logged, not suppressed.
    if not service:
        ui = subprocess.Popen([binary], env=env, stdout=(root / 'gui.log').open('w'), stderr=subprocess.STDOUT)
    pid = original_pid if service else ui.pid
    d = Desktop(session, pid)
    sha = hashlib.sha256(Path(f'/proc/{pid}/exe').read_bytes()).hexdigest()
    assert sha == hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    print('EXECUTED', sha, binary, 'root', root, flush=True)
    d.wait(lambda: d.find('button', 'Send'))
    provenance = json.loads((Path.home() / 'Workspace/hyprneuro-repair/capabilities/speech-provenance.json').read_text())
    speech = Path(provenance['source'])
    assert hashlib.sha256(speech.read_bytes()).hexdigest() == provenance['sha256']
    d.draft('retained draft')
    d.choose(speech)
    d.wait(lambda: any(s.startswith('WAV playback unavailable:') for s in d.labels()))
    assert not d.find('check box', 'Use reviewed audio (play first; Send is separate)')
    assert not any('audio/wav' in s for s in d.labels())
    # Actual Enter cannot sneak rejected audio into the sidecar/model payload.
    d.send('rejected audio fixture' if not live else 'Reply with exactly CEDAR.')
    d.wait(lambda: 'Hyprneuro - Local' in d.labels(), timeout=40)
    assert '[error:' not in d.transcript(), d.transcript()
    if not live:
        req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
        assert len(req) == 1 and isinstance(req[-1]['messages'][-1]['content'], str), req
    else:
        assert 'CEDAR' in d.transcript(), d.transcript()
    fixtures = Path.home() / 'Workspace/hyprneuro-audit/fixtures'
    path = fixtures / 'green.jpg'
    expected = path.read_bytes()
    d.choose(path)
    d.wait(lambda: any('image/jpeg' in s for s in d.labels()))
    # Native picker Cancel must preserve a reviewed image and composer.
    d.draft('image draft')
    dialog = d.picker()
    d.activate('button', 'Cancel', dialog['pid'])
    d.wait(lambda: not any(c['title'] == dialog['title'] for c in d.clients()))
    assert any('image/jpeg' in s for s in d.labels())
    d.draft('image draft')  # verifies the input driver before any send
    # Valid WAV attempts must not falsely preserve/label an old image as audio.
    d.choose(speech)
    d.wait(lambda: any(s.startswith('WAV playback unavailable:') for s in d.labels()))
    assert not any('image/jpeg' in s or 'audio/wav' in s for s in d.labels())
    # Hide while picker pending, then recreate actual toplevel: no late attachment.
    dialog = d.picker()
    d.control('hide')
    d.wait(lambda: not any(c['title'] == dialog['title'] for c in d.clients()))
    d.control('show')
    d.wait(lambda: d.find('button', 'Attach file'))
    assert not any('image/jpeg' in s or 'audio/wav' in s for s in d.labels())
    # Remove remains a true payload removal, not a visual-only row dismissal.
    d.choose(path)
    d.wait(lambda: any('image/jpeg' in s for s in d.labels()))
    d.activate('button', 'Remove attachment (also removes it from submission)')
    d.wait(lambda: 'Hyprneuro · attachment removed' in d.labels())
    # One actual reviewed image -> actual sidecar -> native image_url regression.
    d.choose(path)
    d.wait(lambda: any('image/jpeg' in s for s in d.labels()))
    before = d.transcript()
    d.send('Name the image background color in one word.' if live else 'reviewed jpeg')
    d.wait(lambda: 'Hyprneuro - Local' in d.labels() and d.transcript() != before, timeout=40)
    d.wait(lambda: not any('image/jpeg' in s for s in d.labels()))
    if live:
        assert 'Green' in d.transcript() or 'green' in d.transcript(), d.transcript()
    else:
        req = [json.loads(l) for l in (root / 'backend-requests.jsonl').read_text().splitlines()]
        assert len(req) == 2, req
        url = req[-1]['messages'][-1]['content'][1]['image_url']['url']
        assert url.startswith('data:image/jpeg;base64,')
        assert base64.b64decode(url.split(',', 1)[1]) == expected
    (root / 'transcript.txt').write_text(d.transcript())
    (root / 'labels.json').write_text(json.dumps(d.labels(), indent=2))
    assert service or ui.poll() is None
    print('PASS missing-decoder refusal/cleanup; picker Cancel/hide; image remove/review/send', 'LIVE' if live else 'FIXTURE', flush=True)
    print('BLOCKED audio playback/inference GUI; no audio success claim', flush=True)
finally:
    if ui is not None:
        ui.terminate(); ui.wait(timeout=10)
    if backend is not None:
        backend.terminate(); backend.wait(timeout=10)
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == installed_before
    if not service:
        subprocess.run(['systemctl', '--user', 'start', 'hyprneuro-ui.service'], check=True)
