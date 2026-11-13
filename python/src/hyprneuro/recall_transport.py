"""Recall-only cancellable loopback HTTP; no detached screenshot HTTP threads.

Reuse Models' payloads/parsers, but own asyncio streams for the frame lifetime.
Other model clients and metadata/alert policy are intentionally unchanged.
"""
import asyncio
import json
from .models import Models, ModelError
from .residency import async_inference_admission

MAX_RESPONSE = 8 * 1024 * 1024


class RecallModels(Models):
    check_admission = None  # bound by the owning ScreenWatcher, never a grant

    async def call(self, role, endpoint, payload=None):
        if role not in ('decision', 'omni'):
            raise ModelError('Recall cannot call a text model')
        async with async_inference_admission(role):
            if self.check_admission is not None:
                await self.check_admission()
            try:
                async with asyncio.timeout(self.c.model_timeout):
                    return await self._request(role, endpoint, payload)
            except (OSError, ValueError, IndexError, asyncio.IncompleteReadError,
                    asyncio.LimitOverrunError) as exc:
                raise ModelError(str(exc)) from exc

    async def _request(self, role, endpoint, payload):
        writer = None
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', getattr(self.c, role + '_port'))
            if self.check_admission is not None:
                await self.check_admission()
            body = b'' if payload is None else json.dumps(payload).encode()
            request = (f"{'GET' if payload is None else 'POST'} {endpoint} HTTP/1.1\r\n"
                       'Host: localhost\r\nContent-Type: application/json\r\n'
                       f'Content-Length: {len(body)}\r\nConnection: close\r\n\r\n').encode()
            writer.write(request + body)
            await writer.drain()
            header = await reader.readuntil(b'\r\n\r\n')
            lines = header.decode('ascii').split('\r\n')
            status = int(lines[0].split()[1])
            headers = dict(line.lower().split(':', 1) for line in lines[1:] if ':' in line)
            if headers.get('transfer-encoding', '').strip() == 'chunked':
                parts, size = [], 0
                while True:
                    length = int((await reader.readline()).split(b';')[0], 16)
                    size += length
                    if length < 0 or size > MAX_RESPONSE:
                        raise ModelError('Model response exceeds limit')
                    if not length:
                        break
                    parts.append(await reader.readexactly(length))
                    if await reader.readexactly(2) != b'\r\n':
                        raise ModelError('Malformed chunk')
                raw = b''.join(parts)
            elif 'content-length' in headers:
                length = int(headers['content-length'])
                if not 0 <= length <= MAX_RESPONSE:
                    raise ModelError('Model response exceeds limit')
                raw = await reader.readexactly(length)
            else:
                parts, size = [], 0
                while chunk := await reader.read(min(65536, MAX_RESPONSE + 1 - size)):
                    parts.append(chunk)
                    size += len(chunk)
                    if size > MAX_RESPONSE:
                        raise ModelError('Model response exceeds limit')
                raw = b''.join(parts)
            data = json.loads(raw)
            if status != 200 or not isinstance(data, dict) or 'error' in data:
                raise ModelError(f'{role} HTTP {status}')
            return data
        finally:
            if writer is not None:
                writer.close()
                # Local close is immediate; do not let a peer stall cleanup.
                try:
                    await asyncio.wait_for(writer.wait_closed(), .2)
                except (OSError, asyncio.TimeoutError):
                    pass
