"""Explicit, disposable GTK IPC fixture; never touches models or the real DB.
Usage: python gui_fixture.py SOCKET LOG
"""
import asyncio
import json
import sys
from pathlib import Path

socket_path, log_path = map(Path, sys.argv[1:])

async def handle(reader, writer):
    try:
        request = json.loads(await reader.readline())
        with log_path.open('a') as log:
            log.write(json.dumps(request, ensure_ascii=False) + '\n')
        action = request.get('action')
        if action == 'agent_chat':
            message = request['message']
            if message == 'disconnect':
                return
            if message == 'error':
                frames = [{'type': 'error', 'error': 'fixture refusal'}]
            elif message == 'oversized':
                writer.write(b'x' * (1024 * 1024 + 1))
                await writer.drain()
                return
            else:
                if message == 'slow':
                    await asyncio.sleep(4)
                frames = [{'type': 'delta', 'text': f'fixture {message} ✓\n'},
                          {'type': 'done'}, {'type': 'error', 'error': 'ignore after done'}]
            for frame in frames:
                data = (json.dumps(frame, ensure_ascii=False) + '\n').encode()
                # Split UTF-8 and JSON across socket reads.
                for i in range(0, len(data), 7):
                    writer.write(data[i:i+7])
                    await writer.drain()
                    await asyncio.sleep(.001)
        else:
            await asyncio.sleep(3)  # both status requests must not stall GTK
            result = ({'models': {'text': False, 'omni': False}, 'pid': 123}
                      if action == 'ui_status' else
                      {'cpu_pct': 12.5, 'ram': {'pct': 50, 'total_mb': 1024},
                       'apps': {'focused': {'app_class': 'audit-fixture'}}})
            writer.write((json.dumps({'ok': True, 'result': result}) + '\n').encode())
            await writer.drain()
    except (ConnectionError, ValueError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()

async def main():
    if socket_path.exists():
        raise SystemExit('Refusing to replace existing socket')
    server = await asyncio.start_unix_server(handle, str(socket_path))
    async with server:
        await server.serve_forever()

asyncio.run(main())
