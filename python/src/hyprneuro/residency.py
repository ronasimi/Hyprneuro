"""Cooperating cross-process admission and exclusive lfm handoff, not a model runtime.

Opt in with the SAME explicit HYPRNEURO_RESIDENCY_DIR in Pi and every sidecar.
No launcher/config edits. External lfm/systemctl bypass these locks; snapshots
before/after requests detect observed changes, not an impossible global lock.
"""
from __future__ import annotations

import argparse
import contextvars
import asyncio
from contextlib import contextmanager, asynccontextmanager
import fcntl
import hashlib
import http.client
import json
import mmap
import struct
import os
from pathlib import Path
import secrets
import select
import signal
import stat
import subprocess
import sys
import threading
import time

ROLES = ('text', 'omni', 'decision', 'moe')
PORTS = dict(zip(ROLES, (8081, 8082, 8083, 8080)))
HERMES = 'LFM2.5-8B-A1B-Hermes-Agentic-Coder-Abliterated-v3-Q5_K_M.gguf'


class ResidencyError(RuntimeError):
    pass


def identity(pid=None):
    pid = pid or os.getpid()
    # /proc stat's starttime, not PID alone (protect against PID reuse).
    return {'pid': pid, 'start': Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]}


def alive(owner):
    try:
        return identity(owner['pid']) == owner
    except (OSError, KeyError, ValueError, TypeError):
        return False


class State:
    def __init__(self, root):
        self.root = Path(root)
        if not self.root.is_absolute() or self.root != self.root.resolve():
            raise ResidencyError('Use canonical absolute residency directory')
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        st = self.root.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise ResidencyError('Residency directory must be private and owned by current user')

    def fd(self, name):
        fd = os.open(self.root / name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid() or st.st_mode & 0o077:
            os.close(fd)
            raise ResidencyError('Unsafe residency state/lock file')
        return fd

    @contextmanager
    def lock(self, name, *, exclusive=True, timeout=0, cancel=None):
        fd = self.fd(name)
        deadline = time.monotonic() + timeout
        try:
            while True:
                if cancel and cancel.is_set():
                    raise ResidencyError('Residency operation cancelled')
                try:
                    fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ResidencyError('Inference admission blocked or drain timed out') from None
                    time.sleep(.02)
            yield
        finally:
            os.close(fd)

    def read(self):
        try:
            fd = self.fd('state.json')
            with os.fdopen(fd, 'r') as stream:
                data = stream.read(262145)
            if len(data) > 262144:
                raise ResidencyError('Residency checkpoint exceeds bound')
            value = json.loads(data) if data else {}
            if not isinstance(value, dict):
                raise ResidencyError('Residency checkpoint must be an object')
            return value
        except (ValueError, OSError) as e:
            raise ResidencyError('Invalid residency checkpoint') from e

    def write(self, value):
        encoded = json.dumps(value).encode()
        if len(encoded) > 262144:
            raise ResidencyError('Residency checkpoint exceeds bound')
        temp = self.root / ('.state-' + secrets.token_hex(8))
        try:
            fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.root / 'state.json')
            self.publish(value)
            fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temp.unlink(missing_ok=True)

    def publish(self, value):
        # Stable private mmap: scheduling reads do not open/read files on GTK or
        # event threads. Seqlock makes partial phase/epoch writes fail closed.
        fd = self.fd('generation')
        try:
            if os.fstat(fd).st_size not in (0, 128):
                raise ResidencyError('Invalid generation page')
            os.ftruncate(fd, 128)
            with mmap.mmap(fd, 128) as page:
                seq = struct.unpack_from('Q', page)[0] & ~1
                struct.pack_into('Q', page, 0, seq + 1)
                data = json.dumps([value.get('epoch'), value.get('phase')]).encode()
                page[8:] = data.ljust(120, b'\0')
                struct.pack_into('Q', page, 0, seq + 2)
                page.flush()
        finally:
            os.close(fd)


_pages = {}


def observation_epoch():
    """Nonblocking scheduling stamp; None means drop ordinary visual/model work.

    Shared-page setup must be primed off the UI thread (ManualSwitch/async
    admission do so). A fresh/unconfigured page is closed, never implicitly idle.
    No inference, network, polling or collection is initiated here.
    """
    root = os.environ.get('HYPRNEURO_RESIDENCY_DIR')
    if not root:
        return 'legacy'
    page = _pages.get(root)
    if page is None:
        # First mapping only; sidecar scheduling is off GTK. Hosts must prime
        # through asyncio.to_thread before attaching a GUI switch/subscribers.
        try:
            state = State(root)
            fd = os.open(state.root / 'generation', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            try:
                st = os.fstat(fd)
                if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077 or st.st_nlink != 1 or st.st_size != 128:
                    return None
                page = mmap.mmap(fd, 128, access=mmap.ACCESS_READ)
            finally:
                os.close(fd)
            _pages[root] = page
        except (OSError, ResidencyError):
            return None
    for _ in range(3):
        seq = struct.unpack_from('Q', page)[0]
        data = page[8:]
        if seq & 1 or seq != struct.unpack_from('Q', page)[0]:
            continue
        try:
            epoch, phase = json.loads(data.rstrip(b'\0'))
            return epoch if phase == 'idle' and isinstance(epoch, str) else None
        except (ValueError, TypeError):
            return None
    return None


def require_observation_epoch(epoch):
    if epoch is None or observation_epoch() != epoch:
        raise ResidencyError('Visual observation paused/stale; do not retry old capture')


class Services:
    """Only documented installed launcher verbs; never shell or model-path arguments."""
    def __init__(self, home=None):
        self.home = Path(home or Path.home())
        self.launcher = self.home / '.bin/lfm'

    def command(self, argv, timeout=20):
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ResidencyError('Service control failed or timed out; outcome unknown') from e
        if result.returncode or len(result.stdout) > 65536:
            raise ResidencyError('Service control returned error; inspect actual residency')
        return result.stdout.decode()

    def preflight(self):
        if os.environ.get('LFM_MOE_MODEL'):
            raise ResidencyError('LFM_MOE_MODEL override refused; persisted designated model required')
        paths = [self.launcher, self.home / '.config/systemd/user/lfm@.service',
                 self.home / '.config/systemd/user/lfm@moe.service.d/10-exclusive.conf']
        if any(not p.is_file() for p in paths) or not os.access(self.launcher, os.X_OK):
            raise ResidencyError('lfm setup missing; refusing launcher auto-setup')
        effective = dict(line.split('=', 1) for line in self.command([
            'systemctl', '--user', 'show', 'lfm@moe.service',
            '--property=Conflicts,Restart,NeedDaemonReload']).splitlines() if '=' in line)
        if (not {f'lfm@{r}.service' for r in ROLES[:3]} <= set(effective.get('Conflicts', '').split())
                or effective.get('Restart') != 'no' or effective.get('NeedDaemonReload') != 'no'):
            raise ResidencyError('Effective loaded systemd exclusivity not verified')
        selected = Path(os.environ.get('XDG_STATE_HOME', self.home / '.local/state')) / 'lfm/moe-model'
        model = Path(selected.read_text().strip())
        if model.name != HERMES or not model.is_absolute() or not model.is_file():
            raise ResidencyError('Persisted model is not designated Hermes v3 Q5_K_M')
        self.model = model.resolve(strict=True)
        paths += [selected]
        # Only metadata state; never read MCP credential configuration or weights.
        for name in ('preset', 'mcp', 'ui-path'):
            p = selected.parent / name
            if p.exists():
                paths.append(p)
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}

    def snapshot(self):
        raw = self.command(['systemctl', '--user', 'show', *[f'lfm@{r}.service' for r in ROLES],
                            '--property=Id,ActiveState,SubState,MainPID,InvocationID'])
        result = {}
        for block in raw.strip().split('\n\n'):
            row = dict(line.split('=', 1) for line in block.splitlines() if '=' in line)
            role = row.get('Id', '').removeprefix('lfm@').removesuffix('.service')
            if role in ROLES:
                if (row.get('ActiveState'), row.get('SubState')) not in (('active', 'running'), ('inactive', 'dead')):
                    raise ResidencyError('Service transitional/failed state; admission refused')
                if row['ActiveState'] == 'active' and (not row.get('MainPID', '').isdigit() or int(row['MainPID']) <= 0 or not row.get('InvocationID')):
                    raise ResidencyError('Active service identity not verified')
                result[role] = row
        if set(result) != set(ROLES):
            raise ResidencyError('Incomplete actual service snapshot')
        return result

    def active(self, snapshot):
        return {r for r in ROLES if snapshot[r]['ActiveState'] == 'active'}

    def ready(self, role):
        conn = http.client.HTTPConnection('127.0.0.1', PORTS[role], timeout=2)
        try:
            conn.request('GET', '/health')
            response = conn.getresponse()
            return response.status == 200
        except OSError:
            return False
        finally:
            conn.close()

    def verify_hermes(self, snapshot):
        pid = int(snapshot['moe']['MainPID'])
        args = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        try:
            model = Path(os.fsdecode(args[args.index(b'-m') + 1]))
        except (ValueError, IndexError):
            raise ResidencyError('Cannot verify actual Hermes model command') from None
        if model.name != HERMES or model.resolve() != self.model:
            raise ResidencyError('Actual running model is not designated Hermes')

    def launch(self, *args):
        if args not in (('moe',), ('stop', 'moe')) and not (len(args) == 2 and args[0] == 'start' and args[1] in ROLES[:3]):
            raise ResidencyError('Unsupported launcher operation')
        self.command([str(self.launcher), *args], timeout=60)


class Admission:
    def __init__(self, root, *, services=None):
        self.state = State(root)
        self.services = services or Services()

    @contextmanager
    def enter(self, role, *, token=None):
        role = 'moe' if role == 'hermes' else role
        if role not in ROLES:
            raise ResidencyError('Unknown inference role')
        hermes = role == 'moe'
        lock = 'hermes.lock' if hermes else 'inference.lock'
        # Owner holds inference.lock EX during Hermes; separate lane drains its requests.
        with self.state.lock(lock, exclusive=False):
            current = self.state.read()
            if not current or current.get('phase') != ('hermes' if hermes else 'idle'):
                raise ResidencyError('Residency admission closed')
            if hermes and (not token or not secrets.compare_digest(token, current.get('token', '')) or not alive(current.get('owner', {}))):
                raise ResidencyError('Valid live handoff token required for Hermes')
            actual = self.services.snapshot()
            if actual != current.get('expected') or role not in self.services.active(actual) or (hermes and self.services.active(actual) != {'moe'}):
                raise ResidencyError('External or stale residency change; fail closed')
            try:
                yield
            finally:
                # Check at request boundaries, never per delta. Lock held until actual HTTP completion.
                if self.services.snapshot() != actual:
                    raise ResidencyError('Residency changed during inference; outcomes require review')


@contextmanager
def inference_admission(role):
    """Legacy behavior untouched unless explicitly configured as a participant.

    Coordinator activation is forbidden until ALL actual clients use this same
    directory. The installed, unmodified service is not magically cooperating.
    """
    root = os.environ.get('HYPRNEURO_RESIDENCY_DIR')
    if not root:
        yield
        return
    with Admission(root).enter(role, token=os.environ.get('HYPRNEURO_HANDOFF_TOKEN')):
        yield


@asynccontextmanager
async def async_inference_admission(role):
    admission = inference_admission(role)
    entered = asyncio.create_task(asyncio.to_thread(admission.__enter__))
    try:
        await asyncio.shield(entered)
    except asyncio.CancelledError:
        async def cleanup():
            try:
                await entered
            except BaseException:
                return
            await asyncio.to_thread(admission.__exit__, None, None, None)
        # Shield cleanup even if the caller is cancelled again while entering.
        await asyncio.shield(asyncio.create_task(cleanup()))
        raise
    try:
        yield
    finally:
        await asyncio.shield(asyncio.to_thread(admission.__exit__, None, None, None))


class Coordinator:
    def __init__(self, root, *, services=None):
        self.state = State(root)
        self.services = services or Services()

    def checkpoint(self, phase, **fields):
        value = self.state.read()
        value.update(phase=phase, **fields)
        self.state.write(value)
        return value

    def initialize(self, *, cooperation_confirmed=False):
        if cooperation_confirmed is not True:
            raise ResidencyError('Trusted confirmation that all clients cooperate is required')
        with self.state.lock('transaction.lock'):
            old = self.state.read()
            if old and old.get('phase') != 'idle':
                raise ResidencyError('Unfinished/unknown transaction: manual recovery required')
            self.services.preflight()
            snapshot = self.services.snapshot()
            if 'moe' in self.services.active(snapshot):
                raise ResidencyError('Existing Hermes may serve other clients; do not adopt or stop it')
            if old and old.get('expected') != snapshot:
                raise ResidencyError('Stale checkpoint: inspect actual services before manual recovery')
            self.state.write({'phase': 'idle', 'expected': snapshot, 'epoch': old.get('epoch') or secrets.token_hex(16)})

    def status(self):
        value = self.state.read()
        phase = value.get('phase', 'uninitialized')
        result = {'phase': phase, 'state': 'failed', 'visual_paused': phase != 'idle',
                  'prior': value.get('prior') or []}
        if phase == 'uninitialized':
            result['state'] = 'uninitialized'
            return result
        try:
            actual = self.services.snapshot()
            result['active'] = sorted(self.services.active(actual))
            if phase == 'idle' and actual == value.get('expected'):
                result['state'] = 'off'
            elif phase == 'hermes' and actual == value.get('expected') and alive(value.get('owner', {})):
                result['state'] = 'on'
            elif phase in ('draining', 'launching', 'restoring') and alive(value.get('owner', {})):
                result['state'] = 'transition'
        except (OSError, ResidencyError):
            pass
        if result['state'] == 'failed':
            result['visual_paused'] = True
        return result

    def verify(self, expected, config):
        if self.services.preflight() != config or self.services.snapshot() != expected:
            raise ResidencyError('External service/configuration change detected')

    def wait_ready(self, roles, *, cancel=None, timeout=120, expected=None):
        deadline = time.monotonic() + timeout
        while True:
            if cancel and cancel.is_set():
                raise ResidencyError('Handoff cancelled')
            actual = self.services.snapshot()
            if self.services.active(actual) != set(roles):
                raise ResidencyError('Unexpected actual residency; do not start opposite stack')
            if expected is not None and actual != expected:
                raise ResidencyError('External restart while waiting for readiness')
            expected = actual
            if all(self.services.ready(r) for r in roles):
                return actual
            if time.monotonic() >= deadline:
                raise ResidencyError('Actual HTTP readiness timeout')
            time.sleep(.02)

    @contextmanager
    def handoff(self, *, approve, task_id, checkpoint, release_lease, cancel=None, timeout=120):
        """Host calls after Pi settles. Pi/Durable retains conversations and tool results.

        approve/checkpoint/release_lease are trusted host callbacks, NOT model input.
        Lease callback must reject another owner's lease and release only with its
        valid token; no force release. Once transition may have started, failure
        remains closed unless restoration actually verifies.
        """
        with self.state.lock('transaction.lock'):
            old = self.state.read()
            if old.get('phase') != 'idle':
                raise ResidencyError('Residency not idle; manual review required')
            config = self.services.preflight()
            prior = self.services.snapshot()
            self.verify(old['expected'], config)
            subset = self.services.active(prior)
            if 'moe' in subset:
                raise ResidencyError('Cannot take over existing Hermes')
            if approve({'task_id': task_id, 'model': HERMES, 'prior': sorted(subset)}) is not True:
                raise ResidencyError('Trusted exclusive handoff approval required')
            self.checkpoint('draining', prior=sorted(subset), owner=identity(), config=config, epoch=secrets.token_hex(16))
            switched = False
            try:
                with self.state.lock('inference.lock', timeout=timeout, cancel=cancel):
                    self.verify(prior, config)
                    checkpoint()  # native Pi transcript + tool outcomes persisted before release
                    release_lease()  # ownership/token checked by existing broker/lease manager
                    if cancel and cancel.is_set():
                        raise ResidencyError('Handoff cancelled')
                    self.checkpoint('launching')
                    switched = True  # command error/cancel may still have changed services
                    hermes_snapshot = None
                    try:
                        self.services.launch('moe')  # NEVER pass a model path
                        # Only successful control completion + verified identity may
                        # establish ownership. Unknown launch outcomes are never adopted.
                        hermes_snapshot = self.services.snapshot()
                        if self.services.active(hermes_snapshot) != {'moe'}:
                            hermes_snapshot = None
                            raise ResidencyError('Exclusive launched generation not verified')
                        try:
                            self.services.verify_hermes(hermes_snapshot)
                        except BaseException:
                            hermes_snapshot = None
                            raise
                        actual = self.wait_ready({'moe'}, cancel=cancel, timeout=timeout, expected=hermes_snapshot)
                        if self.services.preflight() != config:
                            raise ResidencyError('Configuration changed during launch')
                        token = secrets.token_hex(32)
                        self.checkpoint('hermes', expected=actual, token=token)
                        yield token
                    finally:
                        if hermes_snapshot is None:
                            raise ResidencyError('Launch ownership unknown; no automatic stop/restore')
                        self.checkpoint('restoring', token=None)
                        # Stop admission, drain running Hermes before stopping its server.
                        with self.state.lock('hermes.lock', timeout=timeout):
                            actual = self.services.snapshot()
                            if hermes_snapshot is not None and actual != hermes_snapshot:
                                raise ResidencyError('External Hermes change; automatic restore blocked')
                            if self.services.active(actual) - {'moe'}:
                                raise ResidencyError('External ordinary stack appeared; restore blocked')
                            if 'moe' in self.services.active(actual):
                                self.services.launch('stop', 'moe')
                            stopped = self.services.snapshot()
                            if self.services.active(stopped):
                                raise ResidencyError('MOE stop not verified; restore blocked')
                            if self.services.preflight() != config:
                                raise ResidencyError('Configuration changed; restore blocked')
                            for role in sorted(subset):
                                self.services.launch('start', role)
                            restored = self.wait_ready(subset, timeout=timeout)
                            self.checkpoint('idle', expected=restored, owner=None, prior=None, config=None)
            except BaseException:
                current = self.state.read()
                if not switched and current.get('phase') == 'draining':
                    try:
                        self.verify(prior, config)
                        self.checkpoint('idle', expected=prior, owner=None)
                    except BaseException:
                        self.checkpoint('blocked')
                elif current.get('phase') != 'idle':
                    self.checkpoint('blocked', token=None)
                raise



_in_callback = contextvars.ContextVar('residency_host_callback', default=False)


class ManualSwitch:
    """Async trusted-host API for a future GTK/controller bridge, never a tool.

    One long-lived owner handles BOTH UI and /moe requests. Other processes use
    that owner's authenticated RPC; they cannot adopt/stop another owner's live
    transaction. This class neither installs RPC handlers nor starts on import.
    Construct with await create(); call off() on orderly host shutdown. Status is observed, not
    a persisted user preference. GTK callbacks must be awaitable UI marshals.
    """
    def __init__(self, root, *, services=None):
        self.coordinator = Coordinator(root, services=services)
        self._context = None
        self._on_task = None
        self._stopping = False
        self._cancel = None
        self._task_id = None
        self.hermes_token = None  # trusted host capability; NEVER return to model/UI JSON

    @classmethod
    async def create(cls, root, *, services=None):
        owner = await asyncio.to_thread(cls, root, services=services)
        await asyncio.to_thread(observation_epoch)
        return owner

    async def status(self):
        return await asyncio.to_thread(self.coordinator.status)

    async def on(self, *, task_id, approve, checkpoint, release_lease):
        if _in_callback.get() or self._on_task or self._stopping:
            raise ResidencyError('Reentrant/concurrent manual on refused')
        self._cancel = threading.Event()
        transition = asyncio.create_task(self._on(task_id=task_id, approve=approve,
            checkpoint=checkpoint, release_lease=release_lease))
        self._on_task = transition
        try:
            return await transition
        finally:
            if self._on_task is transition:
                self._on_task = None

    async def _on(self, *, task_id, approve, checkpoint, release_lease):
        if self._context:
            if task_id != self._task_id:
                raise ResidencyError('Another task owns this manual handoff')
            return await self.status()
        loop = asyncio.get_running_loop()
        async def invoke(callback, *args):
            mark = _in_callback.set(True)
            try:
                return await callback(*args)
            finally:
                _in_callback.reset(mark)
        def bridge(callback):
            def call(*args):
                future = asyncio.run_coroutine_threadsafe(invoke(callback, *args), loop)
                try:
                    return future.result(timeout=120)
                finally:
                    if not future.done():
                        future.cancel()
            return call
        context = self.coordinator.handoff(task_id=task_id, approve=bridge(approve),
            checkpoint=bridge(checkpoint), release_lease=bridge(release_lease), cancel=self._cancel)
        entering = asyncio.create_task(asyncio.to_thread(context.__enter__))
        try:
            await asyncio.to_thread(observation_epoch)  # prime shared page off GTK
            token = await asyncio.shield(entering)
            self._context = context
            self._task_id = task_id
            self.hermes_token = token
            return await self.status()
        except asyncio.CancelledError:
            self._cancel.set()
            async def cleanup():
                try:
                    await entering
                except BaseException:
                    return
                await asyncio.to_thread(context.__exit__, None, None, None)
                self._context = None
                self.hermes_token = None
            await asyncio.shield(asyncio.create_task(cleanup()))
            raise

    async def off(self):
        if _in_callback.get() or self._stopping:
            raise ResidencyError('Reentrant/concurrent manual off refused')
        if self._on_task:
            self._cancel.set()
            try:
                await asyncio.shield(self._on_task)
            except (ResidencyError, asyncio.CancelledError):
                pass
        if not self._context:
            status = await self.status()
            if status['state'] not in ('off', 'uninitialized'):
                raise ResidencyError('No owned transaction: manual review/owner RPC required')
            return status
        self._stopping = True
        context, self._context = self._context, None
        self.hermes_token = None
        self._task_id = None
        restoring = asyncio.create_task(asyncio.to_thread(context.__exit__, None, None, None))
        try:
            await asyncio.shield(restoring)
        except asyncio.CancelledError:
            await asyncio.shield(restoring)
            raise
        finally:
            self._stopping = False
        return await self.status()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('admit', 'initialize', 'handoff', 'status'))
    parser.add_argument('role', nargs='?', choices=(*ROLES, 'hermes'))
    args = parser.parse_args()
    root = os.environ.get('HYPRNEURO_RESIDENCY_DIR')
    if not root:
        raise ResidencyError('HYPRNEURO_RESIDENCY_DIR required')
    cancelled = threading.Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: cancelled.set())

    def send(value):
        print(json.dumps(value), flush=True)

    incoming = bytearray()

    def receive(timeout=120):
        deadline = time.monotonic() + timeout if timeout is not None else float("inf")
        while time.monotonic() < deadline:
            if cancelled.is_set():
                raise ResidencyError('Host cancelled')
            if b'\n' in incoming:
                line, _, tail = incoming.partition(b'\n')
                incoming[:] = tail
                packet = json.loads(line)
                if not isinstance(packet, dict):
                    raise ResidencyError('Expected host control object')
                return packet
            ready, _, _ = select.select([sys.stdin], [], [], .05)
            if ready:
                chunk = os.read(sys.stdin.fileno(), 4097 - len(incoming))
                if not chunk:
                    raise ResidencyError('Host disconnected')
                incoming.extend(chunk)
                if len(incoming) > 4096:
                    raise ResidencyError('Host control frame exceeds bound')
        raise ResidencyError('Host control timeout')

    def callback(kind, detail=None):
        send({'type': kind, 'detail': detail})
        return receive().get('ok') is True

    if args.action == 'admit':
        if not args.role:
            raise ResidencyError('Admission role required')
        with Admission(root).enter(args.role, token=os.environ.get('HYPRNEURO_HANDOFF_TOKEN')):
            send({'admitted': True})
            receive(timeout=None)  # EOF/parent death releases; never expire a live HTTP lease
        send({'released': True})
    elif args.action == 'status':
        send(Coordinator(root).status())
    elif args.action == 'initialize':
        if not callback('cooperation_approval'):
            raise ResidencyError('Trusted cooperation confirmation denied')
        Coordinator(root).initialize(cooperation_confirmed=True)
        send({'initialized': True})
    else:
        task_id = receive().get('task_id')
        if not isinstance(task_id, str) or not task_id or len(task_id) > 128:
            raise ResidencyError('Invalid task id')
        def checkpoint():
            if not callback('checkpoint'):
                raise ResidencyError('Pi checkpoint failed')
        def release():
            if not callback('release_lease'):
                raise ResidencyError('Owned desktop lease release failed')
        with Coordinator(root).handoff(approve=lambda detail: callback('handoff_approval', detail),
                task_id=task_id, checkpoint=checkpoint, release_lease=release, cancel=cancelled):
            state = State(root).read()
            send({'type': 'hermes_ready', 'token': state['token']})
            if receive(timeout=None).get('finish') is not True:
                raise ResidencyError('Host requested cancellation')
        send({'restored': True})


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, ResidencyError) as exc:
        print(json.dumps({'error': str(exc)}), file=sys.stderr)
        raise SystemExit(1)
