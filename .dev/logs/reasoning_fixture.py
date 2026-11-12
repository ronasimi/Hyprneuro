"""Disposable real sidecar + HTTP/SSE backend; no collectors or model changes.
Run: PYTHONPATH=python/src python .dev/logs/reasoning_fixture.py OUTPUT_DIR
Use --live to keep the real supported text/Omni endpoints instead of fixtures.
"""
import asyncio
import json
import sys
from pathlib import Path

from hyprneuro import agent
from hyprneuro.sidecar import serve


async def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(parents=True, exist_ok=True)
    async def backend(reader, writer):
        try:
            first = await reader.readline()
            if first.startswith(b'GET /health '):
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}')
                await writer.drain()
                return
            headers = {}
            while (line := await reader.readline()) != b'\r\n':
                k, v = line.decode().split(':', 1)
                headers[k.lower()] = v.strip()
            req = json.loads(await reader.readexactly(int(headers['content-length'])))
            with (root / 'backend-requests.jsonl').open('a') as log:
                log.write(json.dumps(req, ensure_ascii=False) + '\n')
            message = req['messages'][-1]['content']
            if message == 'native':
                deltas = [{'reasoning_content': 'Fixture: checking α and β. '},
                          {'reasoning_content': 'Thinking remains grey and italic.'},
                          {'content': 'Ordinary answer stays blue and upright ✓.'}]
            elif message == 'delimiters':
                raw = '<think>Fixture delimiter reasoning α.</think>Delimiter answer ✓.'
                deltas = [{'content': raw[i:i+3]} for i in range(0, len(raw), 3)]
            elif message.startswith('long '):
                deltas = [{'content': '\n'.join(f'{message} line {i:02}' for i in range(40))}]
            elif message == 'disconnect':
                deltas = [{'content': '<think>Interrupted fixture reasoning'}]
            else:
                deltas = [{'content': 'Plain fixture answer ✓.'}]
            writer.write(b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n')
            for delta in deltas:
                body = ('data: ' + json.dumps({'choices': [{'delta': delta}]}, ensure_ascii=False) + '\n\n').encode()
                for i in range(0, len(body), 7):
                    chunk = body[i:i+7]
                    writer.write(f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                await writer.drain()
                await asyncio.sleep(.06)
            if message != 'disconnect':
                body = b'data: [DONE]\n\n'
                writer.write(f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n')
                await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
    if '--live' not in sys.argv:
        server = await asyncio.start_server(backend, '127.0.0.1', 0)
        agent.ENDPOINTS['text'] = (server.sockets[0].getsockname()[1], 'fixture')
    class FixtureModels:
        async def decide_alert(self, *args, **kwargs):
            return {"score": 0.0, "notify_recommended": False}
    journal = '--journal' in sys.argv
    network = '--network' in sys.argv
    resources = '--resources' in sys.argv
    await serve(socket_path=root/'sidecar.sock', db_path=root/'state/db.sqlite3',
                settings_file=root/'settings/settings.json',
                allow_ingest=journal or network or resources, alert_journal=journal, alert_network=network,
                alert_resources=resources,
                models=FixtureModels() if journal or network or resources else None)


asyncio.run(main())
