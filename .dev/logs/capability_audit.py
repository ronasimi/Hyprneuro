"""Opt-in localhost-only capability probe. No capture, playback or service changes.
Usage: PYTHONPATH=python/src python .dev/logs/capability_audit.py OUTPUT_DIR SYNTHETIC_WAV
The caller supplies a known synthetic speech fixture, never microphone input.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
speech = Path(sys.argv[2]).resolve()

def request(name, path, payload=None, port=8082):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f'http://127.0.0.1:{port}{path}', data=data,
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read()
            result = {'status': response.status, 'body': json.loads(raw)}
    except urllib.error.HTTPError as exc:
        result = {'status': exc.code, 'body': exc.read().decode()}
    (root / f'{name}.json').write_text(json.dumps(result, indent=2))
    print(name, json.dumps(result)[:2200], flush=True)
    return result

request('props', '/props')
for first, second in [('red', 'blue'), ('blue', 'red')]:
    path = root / f'{first}-{second}.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f'color=c={first}:s=256x256:r=4:d=2', '-f', 'lavfi', '-i',
                    f'color=c={second}:s=256x256:r=4:d=2', '-filter_complex',
                    '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-c:v',
                    'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
    data = base64.b64encode(path.read_bytes()).decode()
    request(path.stem, '/v1/chat/completions', {
        'model': 'lfm-omni', 'temperature': 0, 'max_tokens': 80,
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': 'Describe the background color at the start and at the end of this clip, in time order.'},
            {'type': 'input_video', 'input_video': {'data': data}}]}]})
    (root / f'{path.stem}-sha256.txt').write_text(hashlib.sha256(path.read_bytes()).hexdigest())
request('speech', '/v1/chat/completions', {
    'model': 'lfm-omni', 'temperature': 0, 'max_tokens': 100,
    'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Transcribe this audio exactly. Only output the spoken words.'},
        {'type': 'input_audio', 'input_audio': {'data': base64.b64encode(speech.read_bytes()).decode(), 'format': 'wav'}}]}]})
(root / 'speech-provenance.json').write_text(json.dumps({'source': str(speech),
    'sha256': hashlib.sha256(speech.read_bytes()).hexdigest()}, indent=2))
request('invalid-audio', '/v1/chat/completions', {
    'model': 'lfm-omni', 'max_tokens': 8, 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': 'Transcribe.'}, {'type': 'input_audio',
         'input_audio': {'data': base64.b64encode(b'not an audio file').decode()}}]}]})
# Repeat identical short requests to independently measure actual counters.
for i in range(2):
    request(f'cache-{i}', '/v1/chat/completions', {'model': 'lfm-text',
        'messages': [{'role': 'user', 'content': 'Reply with exactly CEDAR.'}],
        'max_tokens': 10, 'temperature': 0, 'cache_prompt': True,
        'chat_template_kwargs': {'enable_thinking': False}}, port=8081)
