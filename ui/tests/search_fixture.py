"""Disposable real sidecar/store for actual read-only GTK workflow tests.
Synthetic observations only; no collector, model, egress or browser action.
"""
import asyncio
import json
from pathlib import Path
import sys
import time

from hyprneuro import agent
from hyprneuro.sidecar import SidecarServer, serve
from hyprneuro.sidecar_store import SidecarStore

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
now = int(time.time() * 1000)
store = SidecarStore(root / 'db.sqlite3')
for i in range(12):
    store.record(dict(source='manual', kind='note', time_ms=now - i * 1000,
                      title=f'Fixture record {i}', message=f'Literal stored text {i}'))
store.record(dict(source='chrome', kind='page', time_ms=now - 100,
                  title='needle recent <b>untrusted</b>', url='https://example.test/docs?secret=NEVER_EXPOSE#hidden',
                  description='Do not execute or open this text'))
store.record(dict(source='manual', kind='note', time_ms=now - 3 * 86400000,
                  title='needle old <b>untrusted</b>', message='Old synthetic observation'))
(root / 'expected.json').write_text(json.dumps(store.search(query='needle')))
store.close()
original = SidecarServer.dispatch_async


async def dispatch(self, request):
    if request.get('action') in ('search', 'details'):
        with (root / 'requests.jsonl').open('a') as f:
            f.write(json.dumps(request) + '\n')
        await asyncio.sleep(1)
        mode = (root / 'mode.txt').read_text() if (root / 'mode.txt').exists() else ''
        if mode == 'malformed':
            return {'not': 'an array'}
        if mode == 'missing-details' and request['action'] == 'details':
            raise LookupError('Observation not found (fixture)')
    return await original(self, request)


async def health(role):
    return False

SidecarServer.dispatch_async = dispatch
agent.health = health
asyncio.run(serve(socket_path=root / 'sidecar.sock', db_path=root / 'db.sqlite3',
                  settings_file=root / 'settings.json'))
