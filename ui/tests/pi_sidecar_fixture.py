"""Disposable tool-free media endpoint for the opt-in GTK fixture. No models."""
import asyncio
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])


async def handle(reader, writer):
    try:
        request = json.loads(await reader.readline())
        with (root / 'legacy.jsonl').open('a') as log:
            log.write(json.dumps(request) + '\n')
        if request.get('action') == 'agent_chat':
            for packet in ({'type': 'delta', 'text': 'Legacy media fixture answer'}, {'type': 'done'}):
                writer.write((json.dumps(packet)+'\n').encode())
        else:
            writer.write(b'{"ok":true,"result":{}}\n')
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    # Match the real legacy route's bounded attachment frame, not asyncio's 64K default.
    server = await asyncio.start_unix_server(handle, root / 'legacy.sock', limit=10*1024*1024)
    async with server:
        await server.serve_forever()


if __name__ == '__main__':
    asyncio.run(main())
