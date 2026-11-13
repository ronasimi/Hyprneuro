"""User-initiated service connect/disconnect; legacy by default, never consent automation."""
import asyncio
import os
from pathlib import Path
import re

from .pi_desktop_bridge import DesktopBridge
from .pi_owner_service import load_config
from .session_lock import LoginSessionGuard


async def command(*args):
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(process.communicate(), 15)
        if process.returncode or len(out) > 16384:
            raise RuntimeError('Owner service operation refused; no replay')
        return out.decode().strip()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


class ManagedDesktopBridge(DesktopBridge):
    def __init__(self, send, *, connect=None, guard=None, start_service=None):
        kw = {'connect': connect} if connect else {}
        super().__init__(None, send, **kw)
        self.guard = guard
        self.start_service = start_service or self._start_service
        self.workers = []
        self.monitor = None
        self.connection_lock = asyncio.Lock()
        self.failed = False

    async def ensure_unlocked(self):
        if self.guard is None:
            session = os.environ.get('XDG_SESSION_ID') or await command('loginctl', 'show-user', str(os.getuid()), '-p', 'Display', '--value')
            self.guard = LoginSessionGuard(session=session, interval=.25, wayland_only=True)
        if not await self.guard.reconcile():
            raise PermissionError('Local active unlocked Wayland session required')

    async def _start_service(self, root):
        # Only a validated private descriptor can select the fixed service
        # template. No arbitrary unit, shell, environment or permission options.
        instance = await command('systemd-escape', '--path', str(root))
        if not re.fullmatch(r'[A-Za-z0-9_\\.\-]+', instance):
            raise ValueError('Invalid escaped owner instance')
        await self.ensure_unlocked()
        await command('systemctl', '--user', 'start', 'hyprneuro-pi-owner@' + instance + '.service')

    async def attach(self, root):
        async with self.connection_lock:
            if self.control or self.failed:
                raise ValueError('Disconnect/review before another explicit connect')
            await self.ensure_unlocked()
            config = await asyncio.to_thread(load_config, root)
            self.root = str(root)
            if not (Path(root) / 'owner.sock').exists():
                await self.start_service(root)  # once, never retry a start/mutation
                async with asyncio.timeout(10):
                    while not (Path(root) / 'owner.sock').exists():
                        await self.ensure_unlocked()
                        await asyncio.sleep(.05)
            await self.ensure_unlocked()
            control = await self.connect(self.root, trusted=True)
            try:
                status = await asyncio.wait_for(control.call('status'), 5)
                if (status.get('persistent') is not True or status.get('parent_only') is not True
                        or status.get('normal_only') is not True or status.get('tools') != ['read']
                        or status.get('owner_phase') != 'ordinary' or status.get('state') != 'unavailable'
                        or status.get('workspace') != str(Path(root) / 'home/workspace')
                        or status.get('task_id') != config['task_id'] or status.get('app_id') != 'hyprneuro-parent-read'
                        or status.get('read_paths') != sorted(str(Path(root) / 'home/workspace' / p) for p in config['read_paths'])):
                    raise ValueError('Wrong or unknown owner profile/session; no adoption')
                await self.ensure_unlocked()
            except BaseException:
                await control.close()
                raise
            self.control = control
            self.workers = [asyncio.create_task(self.events(control, host=True)), asyncio.create_task(self.poll())]
            self.monitor = asyncio.create_task(self.monitor_connection())
            await self.send({'type': 'connected'})
            await self.send({'type': 'status', 'result': status})

    async def monitor_connection(self):
        # No whole-service600s timer: verify only while this UI is connected.
        try:
            while True:
                await self.ensure_unlocked()
                if any(task.done() for task in self.workers):
                    raise ConnectionError('Owner connection ended; outcomes may be unknown')
                await asyncio.sleep(.25)
        except Exception:
            self.failed = True
            notice = asyncio.create_task(self.send({'type': 'unavailable', 'text': 'Pi disconnected/locked; inspect native checkpoint. Explicit disconnect required; no fallback or replay.'}))
            try:
                await self.detach()
            finally:
                await notice

    async def detach(self):
        async with self.connection_lock:
            monitor, self.monitor = self.monitor, None
            control, self.control = self.control, None
            chat, self.chat_client = self.chat_client, None
            timers = list(self.consents.values())
            self.consents.clear()
            workers, self.workers = self.workers, []
            # Drop BOTH transports before awaiting any task/close completion.
            # Owner-side control EOF denies pending consent and revokes scope.
            clients = [client for client in (chat, control) if client is not None]
            for client in clients:
                client.disconnect()
            tasks = set(timers + workers + [monitor, self.chat_task]) - {None, asyncio.current_task()}
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.gather(*(client.close() for client in clients))

    async def request(self, packet):
        op = packet.get('op')
        try:
            if op == 'connect' and set(packet) == {'op', 'root'}:
                if not isinstance(packet['root'], str) or len(packet['root']) > 4096:
                    raise ValueError('Bounded explicit owner root required')
                await self.attach(packet['root'])
                return
            if op == 'disconnect' and set(packet) == {'op'}:
                await self.detach()
                self.failed = False
                await self.send({'type': 'disconnected'})
                return
            if not self.control or self.failed:
                raise ConnectionError('Explicit connect required')
            # No approval or inference after a stale/locked verification.
            if not (op == 'cancel' or op == 'consent' and packet.get('allowed') is False):
                await self.ensure_unlocked()
            await super().request(packet)
        except Exception:
            await self.send({'type': 'error', 'op': op, 'error': 'Owner connect/request refused. Review service/checkpoint; no retry or fallback. Explicit disconnect returns to legacy.'})

    async def close(self):
        await self.detach()
        await super().close()
