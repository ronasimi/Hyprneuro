"""User-initiated service connect/disconnect; legacy by default, never consent automation."""
import asyncio
import os
from pathlib import Path
import re

from .pi_desktop_bridge import DesktopBridge
from .trusted_control import connect_failure,OwnerRegistrationRejected
from .pi_owner_service import load_config
from .session_lock import LoginSessionGuard


async def command(*args, preflight=None):
    if preflight is not None:(await preflight())()
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


class OwnerConnectError(RuntimeError):
    def __init__(self, stage, cause):
        super().__init__("Owner connect refused; no replay")
        self.stage = stage
        self.connect_diagnostic = (dict(cause.connect_diagnostic) if isinstance(cause,OwnerRegistrationRejected)
                                   else connect_failure(stage,cause))


CLEANUP_TIMEOUT = 5


class ManagedDesktopBridge(DesktopBridge):
    def __init__(self, send, *, connect=None, guard=None, start_service=None, broker=None):
        kw = {'connect': connect} if connect else {}
        super().__init__(None, send, broker=broker, **kw)
        self.guard = guard
        self.start_service = start_service or self._start_service
        self.workers = []
        self.monitor = None
        self.connection_lock = asyncio.Lock()
        self.failed = False
        self._pinned_config=None
        raw_connect=self.connect
        async def bound_connect(root,**fields):
            await self._owner_preflight(root)
            return await raw_connect(root,preflight=lambda:self._owner_preflight(root),**fields)
        self.connect=bound_connect

    async def _owner_preflight(self,root):
        if self.broker is None or not self.broker.finite_session:
            raise PermissionError('Fixed MAIN owner binding required')
        config,check=await self.broker.prepare_owner(root)
        check()
        if self._pinned_config is not None and config!=self._pinned_config:
            raise PermissionError('Owner configuration replaced; no adoption')
        self._pinned_config=dict(config)
        return check

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
        await command('systemctl', '--user', 'start', 'hyprneuro-pi-owner@' + instance + '.service',preflight=lambda:self._owner_preflight(root))

    async def attach(self, root):
        async with self.connection_lock:
            stage = 'connection'
            try:
                if self.control or self.failed:
                    raise ValueError('Disconnect/review before another explicit connect')
                stage = 'trusted-broker'
                if self.broker is None:
                    raise PermissionError('Unsupported legacy tool adapter; fixed private handoff required')
                stage = "unlock"
                await self.ensure_unlocked()
                stage = "owner-policy"
                check=await self._owner_preflight(root)
                check()
                config = dict(self._pinned_config)
                self.root = str(root)
                if not (Path(root) / 'owner.sock').exists():
                    stage = "service"
                    (await self._owner_preflight(root))()
                    await self.start_service(root)  # once, never retry a start/mutation
                    async with asyncio.timeout(10):
                        while not (Path(root) / 'owner.sock').exists():
                            await self.ensure_unlocked()
                            await asyncio.sleep(.05)
                await self.ensure_unlocked()
                stage = "authentication"
                control = await self.connect(self.root, trusted=True)
                try:
                    stage = 'profile'
                    status = await asyncio.wait_for(control.call('status'), 5)
                    if (status.get('persistent') is not True or status.get('parent_only') is not True
                            or status.get('normal_only') is not True or status.get('tools') != ['read']
                            or status.get('owner_phase') != 'ordinary' or status.get('state') != 'unavailable'
                            or status.get('workspace') != str(Path(root) / 'home/workspace')
                            or status.get('task_id') != config['task_id'] or status.get('app_id') != 'hyprneuro-parent-read'
                            or status.get('read_paths') != sorted(str(Path(root) / 'home/workspace' / p) for p in config['read_paths'])):
                        raise ValueError('Wrong or unknown owner profile/session; no adoption')
                    await self.ensure_unlocked()
                    stage = 'owner-policy'
                    (await self._owner_preflight(root))()
                    stage = 'trusted-broker'
                    if self.broker is None:
                        raise PermissionError('Fixed trusted broker handoff required')
                    await self.broker.register(root, control)
                except BaseException:
                    await control.close()
                    raise
                self.control = control
                self.workers = [asyncio.create_task(self.events(control, host=True)), asyncio.create_task(self.poll())]
                self.monitor = asyncio.create_task(self.monitor_connection())
                await self.send({'type': 'connected'})
                await self.send({'type': 'status', 'result': status})
            except Exception as error:
                self.failed=True
                raise OwnerConnectError(stage,error) from error

    async def monitor_connection(self):
        # No whole-service600s timer: verify only while this UI is connected.
        try:
            while True:
                await self.ensure_unlocked()
                if self.broker is not None and not self.broker.connected:
                    raise ConnectionError('Private verification channel lost')
                if any(task.done() for task in self.workers):
                    raise ConnectionError('Owner connection ended; outcomes may be unknown')
                await asyncio.sleep(.25)
        except Exception:
            self.failed = True
            notice = asyncio.create_task(self.send({'type': 'unavailable', 'text': 'Pi disconnected/locked; inspect native checkpoint. Explicit disconnect required; no fallback or replay.'}))
            try:
                await self.detach()
            except Exception:
                self.failed = True  # unavailable/unknown, never clean or retried
            finally:
                await notice

    async def detach(self):
        async with self.connection_lock:
            monitor, self.monitor = self.monitor, None
            control, self.control = self.control, None
            chat, self.chat_client = self.chat_client, None
            timers = list(self.consents.values())
            self.consents.clear()
            self.broker_pending.clear()
            workers, self.workers = self.workers, []
            # Drop BOTH transports before awaiting any task/close completion.
            # Owner-side control EOF denies pending consent and revokes scope.
            clients = [client for client in (chat, control) if client is not None]
            if chat is not None:
                chat.disconnect()  # seal/abort native chat before scoped cleanup
            tasks = set(timers + workers + [monitor, self.chat_task]) - {None, asyncio.current_task()}
            for task in tasks:
                task.cancel()
            try:
                if self.broker is not None:
                    async with asyncio.timeout(CLEANUP_TIMEOUT):
                        invalidated = await self.broker.invalidate()
                        if invalidated and control is not None:
                            await control.call('grants_invalidated')
            except BaseException:
                self.failed = True  # uncertain cleanup is never disconnected/clean
                raise
            finally:
                for client in clients:
                    client.disconnect()
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
                if self.broker is not None and self.broker.finite_session:
                    await self.broker.disconnect_session()  # no GUI clean claim before reap receipt
                self.failed = False
                await self.send({'type': 'disconnected'})
                return
            if not self.control or self.failed:
                raise ConnectionError('Explicit connect required')
            # No approval or inference after a stale/locked verification.
            if not (op == 'cancel' or op == 'consent' and packet.get('allowed') is False):
                await self.ensure_unlocked()
            await super().request(packet)
        except Exception as failure:
            # Static stage messages only: never expose exception paths, credentials
            # or backend bodies. GTK retains this connect failure in its route row.
            stages = {
                'unlock': 'Pi connect refused: local unlocked Wayland session required.',
                'descriptor': 'Pi connect refused: select the prepared private folder containing valid owner.json.',
                'service': 'Pi connect failed starting/waiting for the owner service; inspect service/checkpoint.',
                'authentication': 'Pi connect failed authenticating the owner socket; inspect service/checkpoint.',
                'profile': 'Pi connect refused: owner is not the exact normal-only parent READ-ONLY profile.',
            }
            error = stages.get(failure.stage) if op == 'connect' and isinstance(failure, OwnerConnectError) else None
            diagnostic = (failure.connect_diagnostic if isinstance(failure,OwnerConnectError) else connect_failure('unknown',failure))
            await self.send({'type': 'error', 'op': op, 'connect_diagnostic': diagnostic, 'error':
                             (error + ' No retry/fallback; Disconnect returns to Legacy.') if error else
                             'Owner connect/request refused. Review service/checkpoint; no retry or fallback. Explicit disconnect returns to legacy.'})

    async def close(self):
        await self.detach()
        await super().close()
