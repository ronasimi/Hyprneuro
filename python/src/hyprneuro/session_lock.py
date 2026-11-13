"""Fail-closed logind reconciliation and explicit same-session lock notifications."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import re
import time


class LoginSessionGuard:
    LOCKERS = frozenset({"hyprlock", "swaylock", "swaylock-effects", "waylock",
                         "gtklock", "i3lock", "i3lock-color", "betterlockscreen"})

    def __init__(self, *, session=None, uid=None, proc_root=Path('/proc'), interval=1.0):
        self.session = os.environ.get('XDG_SESSION_ID', '') if session is None else session
        self.uid = os.getuid() if uid is None else uid
        self.proc_root = Path(proc_root)
        if not .1 <= interval <= 5:
            raise ValueError('Invalid reconciliation interval')
        self.interval = interval
        self._verified = False
        self._expires = 0.0
        self._revision = 0
        self._explicit_lock = False
        self._listeners = []
        self._wake = asyncio.Event()
        self._reconcile_lock = asyncio.Lock()
        self._path = None

    def subscribe(self, callback):
        self._listeners.append(callback)
        callback(False)

    def _publish(self, verified):
        self._verified = verified
        for callback in self._listeners:
            callback(verified)

    def invalidate(self):
        self._revision += 1
        self._expires = 0
        self._publish(False)
        self._wake.set()

    def session_lock_hint(self, session, locked):
        """Untrusted RPC: revoke/recheck only; never clear a trusted latch."""
        if session != self.session or not self._valid_session():
            return False
        if locked is not False:
            self._explicit_lock = True
        self.invalidate()
        return True

    async def follow_trusted_producer(self, producer):
        """Startup-injected host code receives the clearing capability.

        This callable is never supplied through RPC or inferred from a UID or
        session string. Its lifetime must cover the actual event connection;
        termination/failure leaves lock state unknown and latched closed.
        """
        active = True
        def publish(session, locked):
            return self.session_lock_event(session, locked) if active else False
        self.session_lock_event(self.session, None)
        try:
            await producer(publish)
        finally:
            active = False  # discard callbacks arriving after producer disconnect
            self.session_lock_event(self.session, None)

    def session_lock_event(self, session, locked):
        """Trusted host capability, never exposed to ordinary RPC clients.

        Call on the sidecar asyncio loop (other threads: call_soon_threadsafe).
        Only the configured session is relevant. None means unknown/paused.
        A compositor lock remains latched until its explicit unlock notification;
        even that notification must pass independent logind + proc verification.
        """
        if session != self.session or not self._valid_session():
            return False
        self._explicit_lock = locked is not False
        self.invalidate()
        return True

    def _valid_session(self):
        return isinstance(self.session, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', self.session)

    async def unlocked(self):
        # No subprocess/procfs scan on an event/frame path. A dead monitor or
        # stalled reconciler loses its short-lived verification automatically.
        if time.monotonic() >= self._expires:
            if self._verified:
                self.invalidate()
            return False
        return self._verified and not self._explicit_lock

    async def _command(self, *argv):
        proc = await asyncio.create_subprocess_exec(
            *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), 2)
            if proc.returncode or len(out) > 16384:
                raise RuntimeError('Session query failed')
            return out.decode()
        finally:
            if proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def _snapshot(self):
        out = await self._command('loginctl', 'show-session', self.session,
            '-p', 'Id', '-p', 'User', '-p', 'Active', '-p', 'LockedHint',
            '-p', 'Remote', '-p', 'Type', '-p', 'Class', '-p', 'Seat', '-p', 'Leader')
        return dict(line.split('=', 1) for line in out.splitlines() if '=' in line)

    def _no_locker(self, leader):
        """Bounded procfs sample, no ps/pgrep. None/ambiguity is denial.

        logind cgroup scope is authoritative; POSIX session ID supports launchers
        whose descendants are outside that scope. Unmapped same-UID lockers
        cannot be proven unrelated and therefore also deny.
        """
        deadline = time.monotonic() + .25
        count = 0
        try:
            with os.scandir(self.proc_root) as entries:
                for entry in entries:
                    if not entry.name.isdigit():
                        continue
                    count += 1
                    if count > 8192 or time.monotonic() > deadline:
                        return False
                    path = Path(entry.path)
                    try:
                        if path.stat().st_uid != self.uid:
                            continue
                        comm = (path / 'comm').read_text()[:128].strip().lower()
                        # Linux comm truncates to 15 bytes (betterlockscreen).
                        if not any(comm == n or (len(comm) == 15 and n.startswith(comm))
                                   for n in self.LOCKERS):
                            continue
                        cgroup = (path / 'cgroup').read_text()[:16384]
                        scopes = re.findall(r'(?:^|/)session-([^/\n]+)\.scope(?:/|$)', cgroup)
                        sid = int((path / 'stat').read_text().rsplit(')', 1)[1].split()[3])
                        if self.session in scopes or sid == leader or not scopes:
                            return False
                    except FileNotFoundError:
                        continue  # process exited while sampling
                    except (OSError, ValueError, IndexError):
                        return False
            return True
        except OSError:
            return False

    async def reconcile(self):
        async with self._reconcile_lock:
            revision = self._revision
            verified = False
            try:
                if self._valid_session() and not self._explicit_lock:
                    row = await self._snapshot()
                    leader = int(row.get('Leader', '0'))
                    verified = (row.get('Id') == self.session and row.get('User') == str(self.uid)
                        and row.get('Active') == 'yes' and row.get('LockedHint') == 'no'
                        and row.get('Remote') == 'no' and row.get('Type') in ('wayland', 'x11')
                        and row.get('Class') == 'user' and bool(row.get('Seat')) and leader > 0)
                    if verified:
                        verified = await asyncio.to_thread(self._no_locker, leader)
            except (OSError, ValueError, RuntimeError, asyncio.TimeoutError):
                pass
            # A notification during IO invalidates the entire verification.
            if revision != self._revision:
                return False
            self._expires = time.monotonic() + self.interval * 2.5 if verified else 0
            self._publish(bool(verified))
            return bool(verified)

    def properties_changed(self, packet):
        """Consume busctl JSON for the resolved session path; never trust unlock."""
        if (not self._path or not isinstance(packet, dict) or packet.get('path') != self._path
                or packet.get('interface') != 'org.freedesktop.DBus.Properties'
                or packet.get('member') != 'PropertiesChanged'):
            return
        body = packet.get('payload')
        payload = body.get('data') if isinstance(body, dict) else None
        if isinstance(payload, list) and payload and payload[0] == 'org.freedesktop.login1.Session':
            self.invalidate()  # includes invalidated properties and Active changes

    async def _monitor(self):
        proc = None
        try:
            if not self._valid_session():
                return
            result = json.loads(await self._command('busctl', '--system', '--json=short',
                'call', 'org.freedesktop.login1', '/org/freedesktop/login1',
                'org.freedesktop.login1.Manager', 'GetSession', 's', self.session))
            self._path = result['data'][0]
            if not isinstance(self._path, str) or not self._path.startswith('/org/freedesktop/login1/session/'):
                raise ValueError('Invalid session object')
            proc = await asyncio.create_subprocess_exec('busctl', '--system', '--json=short',
                "--match=type='signal',sender='org.freedesktop.login1',interface='org.freedesktop.DBus.Properties',member='PropertiesChanged',path='" + self._path + "'",
                'monitor', 'org.freedesktop.login1', stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=65536)
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                self.properties_changed(json.loads(line))
        except (OSError, ValueError, KeyError, IndexError, TypeError, RuntimeError):
            pass  # bounded reconciler remains available when monitoring isn't
        finally:
            self.invalidate()  # disconnect is unknown, never an unlock
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()

    async def run(self):
        monitor = asyncio.create_task(self._monitor(), name='logind_properties')
        try:
            while True:
                self._wake.clear()
                await self.reconcile()
                try:
                    await asyncio.wait_for(self._wake.wait(), self.interval)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.invalidate()
            monitor.cancel()
            await asyncio.gather(monitor, return_exceptions=True)
