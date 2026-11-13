"""Explicit leased normal-stack compatibility probes, NOT Pi-owner acceptance.

No initialization, lifecycle, execution, installed data, capture or providers.
Run only under `pi-durable-subagents hold machine -- ...` after parent approval.
"""
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import time
import zlib

if os.environ.get('HYPRNEURO_NORMAL_PROBE') != '1':
    raise SystemExit('BLOCKED: explicit leased normal-stack probe authorization required')
if os.environ.get('HYPRNEURO_RESIDENCY_DIR') or os.environ.get('HYPRNEURO_PI_OWNER_ENABLE'):
    raise SystemExit('BLOCKED: this legacy compatibility probe must not alter/adopt admission or an owner')

from hyprneuro.config import Config
from hyprneuro.models import Models
from hyprneuro.sidecar import SidecarServer
from hyprneuro.sidecar_store import SidecarStore

root = Path(sys.argv[1]).resolve(strict=True)
if not root.is_relative_to(Path.home()/'Workspace'):
    raise SystemExit('Disposable evidence directory must be under Workspace')
os.umask(0o077)
models = Models(Config(model_timeout=8, max_tokens=96))  # no ambient config load


def resources():
    fields = dict((l.split(':', 1)[0], int(l.split()[1])) for l in Path('/proc/meminfo').read_text().splitlines() if l.startswith(('MemTotal:', 'MemAvailable:', 'SwapFree:')))
    if fields['MemAvailable'] < 1024*1024:
        raise RuntimeError('Less than1GiB available; stop bounded trials')
    return fields


def record(name, **fields):
    row = dict(probe=name, time=time.time(), **fields)
    with (root/'application.jsonl').open('a') as f:
        f.write(json.dumps(row, ensure_ascii=False)+'\n')
    print(json.dumps(row, ensure_ascii=False), flush=True)


async def trial(name, call):
    before, started = resources(), time.monotonic()
    try:
        result = await asyncio.wait_for(call(), 25)
        record(name, status='observed', seconds=time.monotonic()-started, result=result,
               resources_before=before, resources_after=resources())
        return result
    except Exception as exc:
        record(name, status='failed', seconds=time.monotonic()-started,
               error_type=type(exc).__name__, error=str(exc)[:300], resources_before=before)


class Sink:
    def __init__(self): self.data = bytearray()
    def write(self, data):
        if len(self.data)+len(data)>131072:
            raise ValueError('Probe output exceeds128KiB')
        self.data.extend(data)
    async def drain(self): pass


async def main():
    record('source-identity', source=str(Path(__file__).resolve()), package=str(Path(__import__('hyprneuro').__file__).resolve()),
           admission_mode='existing optional legacy normal path; NOT all-client cooperation',
           tool_execution=False, resources=resources())
    # Metadata through the actual application HTTP client, not raw curl.
    for role in ('text','omni','decision'):
        health = await models.call(role, '/health')
        if health.get('status') != 'ok': raise RuntimeError('Normal stack unhealthy; no trial')
        entries = await models.call(role, '/v1/models')
        props = await models.call(role, '/props')
        record('model-identity', role=role, health=health,
               ids=[r.get('id') for r in entries.get('data', [])],
               metadata={k:props[k] for k in ('model_path','modalities','total_slots') if k in props},
               chat_template_sha256=hashlib.sha256(str(props.get('chat_template','')).encode()).hexdigest(),
               context=props.get('default_generation_settings',{}).get('n_ctx'))
    await trial('D1-application-noul-string-state', lambda: models.decide_alert({
        'source':'resource','kind':'synthetic_fixture','severity':'info',
        'message':'Synthetic successful routine test; no real alert or action.'}))
    prompt = [{'role':'system','content':'This is a synthetic compatibility test. No actions. Be concise.'},
              {'role':'user','content':'Reply with exactly MAPLE.'}]
    await trial('text-application-plain', lambda: models.chat(prompt, False))
    fixture = root/'fixture.txt'; fixture.write_text('SYNTHETIC_READ_ONLY_MAPLE\n')
    tool = {'type':'function','function':{'name':'read_fixture','description':'Propose reading the dedicated synthetic fixture; executor is disabled in this probe.',
        'parameters':{'type':'object','properties':{'path':{'type':'string','enum':['fixture.txt']}},'required':['path'],'additionalProperties':False}}}
    tool_prompt = [{'role':'system','content':'Request exactly one read_fixture tool for fixture.txt. Do not guess its contents. This schema probe never executes a tool.'},
                   {'role':'user','content':'Use read_fixture with path fixture.txt to inspect the synthetic fixture.'}]
    raw = await trial('text-application-read-tool-SCHEMA-ONLY', lambda: models.chat(tool_prompt, False, [tool]))
    if raw:
        calls=raw.get('choices',[{}])[0].get('message',{}).get('tool_calls',[])
        valid=False
        try:
            valid=len(calls)==1 and calls[0]['function']['name']=='read_fixture' and json.loads(calls[0]['function']['arguments'])=={'path':'fixture.txt'}
        except (KeyError,TypeError,ValueError): pass
        record('text-tool-schema-validation', exact_structured_call=valid, execution=False,
               fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest())
    # Invoke actual sidecar media framing with a disposable store; no daemon,
    # metadata subscription, broker, installed DB/settings or capture is enabled.
    store=SidecarStore(root/'disposable.sqlite3')
    server=SidecarServer(store)
    async def media(data, mime, prompt):
        sink=Sink()
        await server._stream_agent_chat(sink,dict(action='agent_chat', message=prompt,
            max_tokens=64, media={'mime':mime,'data':base64.b64encode(data).decode()}))
        frames=[json.loads(l) for l in sink.data.splitlines()]
        return dict(frames=frames, input_sha256=hashlib.sha256(data).hexdigest(), mime=mime,
                    route='source SidecarServer -> agent.stream_chat -> existing Omni; NOT installed IPC or GTK')
    try:
        def chunk(kind,data):
            body=kind+data
            return struct.pack('>I',len(data))+body+struct.pack('>I',zlib.crc32(body))
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',128,128,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\x00'+b'\xff\x00\x00'*128)*128))+chunk(b'IEND',b'')
        (root/'synthetic-red.png').write_bytes(png)
        await trial('omni-source-application-synthetic-image',lambda:media(png,'image/png','What single color fills this synthetic image? Reply one word.'))
        # Exact previously approved synthetic speech, not microphone/user audio.
        speech=Path('/home/ron/Workspace/jeevus-verification/scored-1793817090252/speech-d5bab0bb-5713-432c-9494-6d0dddf89684.wav')
        wav=speech.read_bytes()
        if hashlib.sha256(wav).hexdigest()!='3670e2c4b0f3f70c15d8fc85f496589a3fa7029526df33a73ee815ffc59adafc':
            raise ValueError('Synthetic speech provenance mismatch; refuse audio trial')
        (root/'synthetic-reviewed.wav').write_bytes(wav)
        await trial('omni-source-application-synthetic-WAV',lambda:media(wav,'audio/wav','Transcribe this synthetic audio exactly. Output only the spoken words.'))
    finally: store.close()


asyncio.run(asyncio.wait_for(main(),140))
