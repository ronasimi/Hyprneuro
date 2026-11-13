"""Async trusted-UI/chat transport for the opt-in native Pi owner. No model loop.

GTK must marshal coroutines to its asyncio bridge and render observed status.
Loading this module never starts a model, process, collector or socket server.
"""
import asyncio
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import uuid

MAX_FRAME = 65536


class PiOwnerClient:
    def __init__(self, reader, writer, trusted):
        self.reader, self.writer, self.trusted = reader, writer, trusted
        self.pending = {}
        self.events = asyncio.Queue(maxsize=64)
        self.read_task = asyncio.create_task(self._read(), name='pi-owner-ui-transport')

    @classmethod
    async def connect(cls, root, *, trusted=False):
        root = Path(root)
        def credential():
            st = root.lstat()
            if not root.is_absolute() or root != root.resolve() or not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise PermissionError('Unsafe Pi owner directory')
            fd = os.open(root / ('control.key' if trusted else 'chat.key'), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1 or st.st_mode & 0o077 or st.st_size != 32:
                    raise PermissionError('Unsafe Pi bridge credential')
                return os.read(fd, 32)
            finally:
                os.close(fd)
        key = await asyncio.to_thread(credential)
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(str(root / 'owner.sock'), limit=MAX_FRAME + 1), 3)
        try:
            nonce = await asyncio.wait_for(reader.readexactly(32), 3)
            role = b'control' if trusted else b'chat'
            mac = hmac.new(key, nonce + role, hashlib.sha256).digest()
            writer.write((b'C' if trusted else b'T') + mac)
            await writer.drain()
            ready = json.loads(await asyncio.wait_for(reader.readline(), 3))
            if ready != {'type': 'ready', 'schema': 'hyprneuro.pi-owner/1'}:
                raise ConnectionError('Pi bridge authentication failed')
            return cls(reader, writer, trusted)
        except BaseException:
            writer.transport.abort()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (TimeoutError, ConnectionError):
                pass
            raise

    async def call(self, op, **fields):
        if op not in ('chat', 'status', 'on', 'off', 'consent'):
            raise ValueError('Unknown Pi owner operation')
        allowed = {'chat': {'text', 'recommend'}, 'consent': {'answer_id', 'allowed'}, 'status': set(), 'on': set(), 'off': set()}
        if fields.keys() - allowed[op]:
            raise ValueError('Unknown Pi owner fields')
        if (op in ('on', 'off', 'consent') or op == 'chat' and fields.get('recommend') is True) and not self.trusted:
            raise PermissionError('Trusted UI control channel required')
        if self.read_task.done() or len(self.pending) >= 8:
            raise ConnectionError('Pi owner disconnected or request bound reached')
        rid = uuid.uuid4().hex
        data = (json.dumps({'op': op, 'id': rid, **fields}, ensure_ascii=False) + '\n').encode('utf-8')
        if len(data) > MAX_FRAME:
            raise ValueError('Pi owner frame exceeds bound')
        future = asyncio.get_running_loop().create_future()
        self.pending[rid] = future
        try:
            self.writer.write(data)
            await self.writer.drain()
            return await future
        finally:
            self.pending.pop(rid, None)

    async def _read(self):
        error = ConnectionError('Pi owner disconnected; outcomes may be unknown, never retry mutations')
        try:
            while line := await self.reader.readline():
                if len(line) > MAX_FRAME:
                    raise ValueError('Pi owner response exceeds bound')
                packet = json.loads(line)
                if not isinstance(packet, dict):
                    raise ValueError('Pi owner object response required')
                if packet.get('type') in ('result', 'error'):
                    future = self.pending.get(packet.get('id'))
                    if future and not future.done():
                        if packet['type'] == 'error':
                            future.set_exception(RuntimeError(packet.get('error', 'Pi owner request failed')))
                        else:
                            future.set_result(packet.get('result'))
                else:
                    self.events.put_nowait(packet)
        except (OSError, ValueError, asyncio.QueueFull, asyncio.CancelledError):
            error = ConnectionError('Pi owner stream interrupted; review native session/checkpoint')
        finally:
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(error)
            self.writer.close()

    def disconnect(self):
        # Synchronous local abort discards queued frames and drops authority;
        # neither peer acknowledgements nor wait_closed may delay revocation.
        self.writer.transport.abort()
        self.read_task.cancel()

    async def close(self, *, timeout=1):
        self.disconnect()
        try:
            async with asyncio.timeout(timeout):
                await self.writer.wait_closed()
        except (TimeoutError, ConnectionError):
            pass
        finally:
            await asyncio.gather(self.read_task, return_exceptions=True)
