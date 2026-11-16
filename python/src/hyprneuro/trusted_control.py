"""Private managed-GTK launch handoff; never a public sidecar RPC.

SO_PEERCRED authenticates establishment, not every message after FD handoff.
Reviewed GTK deliberately transfers this connection to its exact fixed child.
No FD-transfer detection or loaded-Python-code/same-UID sandbox claim is made.
"""
import asyncio
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import socket
import stat
import struct
import sys
from dataclasses import dataclass

from .pi_owner_service import load_config
from .trusted_consent import canonical, ConsentDenied

MAX_FRAME = 4096


def process_identity(pid):
    path = Path('/proc') / str(pid)
    fields = (path / 'stat').read_text().rsplit(') ', 1)[1].split()
    identity = {'pid': pid, 'start': fields[19], 'parent': int(fields[1]),
                'uid': path.stat().st_uid, 'exe': os.readlink(path / 'exe'),
                'cgroup': (path / 'cgroup').read_text().strip(),
                'argv': (path / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')}
    if (path / 'stat').read_text().rsplit(') ', 1)[1].split()[19] != identity['start']:
        raise PermissionError('Process identity changed')
    return identity


REJECTION_STAGES = frozenset({
    'identity-root', 'peer', 'peer-uid', 'ui-identity', 'unit-command', 'unit-metadata',
    'unit-state', 'unit-job', 'unit-pid', 'ui-process', 'ui-peer-pid',
    'ui-uid', 'ui-cgroup', 'ui-exe-hash', 'launch-frame', 'child-identity',
    'launch-ready', 'private-operation', 'unknown',
})


class LaunchRejected(PermissionError):
    """Static diagnostic location only; never eligibility or a public capability."""
    def __init__(self, stage):
        super().__init__('Private launch rejected')
        self.stage = stage if stage in REJECTION_STAGES else 'unknown'


def rejection_record(stage, error):
    stage = error.stage if isinstance(error, LaunchRejected) else stage
    return {'diagnostic': 'NONAUTHORITATIVE',
            'stage': stage if stage in REJECTION_STAGES else 'unknown',
            'category': 'timeout' if isinstance(error, TimeoutError) else
                        'identity' if isinstance(error, PermissionError) else 'failure'}


CONNECT_SITES=frozenset({'connection','trusted-broker','unlock','descriptor','service','authentication','profile',
                         'owner-challenge','challenge-frame','native-proof','registration-rpc','registration-frame'})

def connect_failure(site,error):
    error_class=next((kind.__name__ for kind in [LaunchRejected,TimeoutError,ConnectionError,PermissionError,ValueError,OSError,RuntimeError] if isinstance(error,kind)),'Other')
    return {'diagnostic':'NONAUTHORITATIVE','site':site if site in CONNECT_SITES else 'unknown','error_class':error_class,
            'category':'permission' if isinstance(error,PermissionError) else
                       'timeout' if isinstance(error,TimeoutError) else
                       'connection' if isinstance(error,ConnectionError) else
                       'value' if isinstance(error,ValueError) else
                       'os' if isinstance(error,OSError) else 'other'}

class OwnerRegistrationRejected(PermissionError):
    def __init__(self,site,error):
        super().__init__('Owner registration rejected; no replay')
        self.connect_diagnostic=connect_failure(site,error)


async def metadata(*args):
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(3):
            out = await process.stdout.read(16385)
            await process.wait()
        if process.returncode or len(out) > 16384:
            raise LaunchRejected('unit-command')
        return out.decode().strip()
    finally:
        if process.returncode is None:
            process.terminate()  # only this owned metadata subprocess, never a service
            await process.wait()


async def unit_metadata(unit):
    try:
        out = await metadata('/usr/bin/systemctl', '--user', 'show', unit,
                             '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'ActiveState', '-p', 'Job')
        value = dict(line.split('=', 1) for line in out.splitlines())
        if value['ActiveState'] != 'active':
            raise LaunchRejected('unit-state')
        if value['Job']:
            raise LaunchRejected('unit-job')
        if int(value['MainPID']) <= 0:
            raise LaunchRejected('unit-pid')
        return int(value['MainPID']), value['ControlGroup']
    except (KeyError, ValueError):
        raise LaunchRejected('unit-metadata') from None


@dataclass(frozen=True)
class LaunchPolicy:
    python: Path
    entry: Path
    source: Path
    ui_sha256: str
    entry_sha256: str
    # Explicit immutable startup policy, never a public request parameter.

    def __post_init__(self):
        for path in [self.python, self.entry, self.source]:
            if not path.is_absolute():
                raise ValueError('Absolute reviewed launch paths required')
        if any(not re.fullmatch('[0-9a-f]{64}', value) for value in [self.ui_sha256, self.entry_sha256]):
            raise ValueError('Exact reviewed executable/entry hashes required')


class LaunchVerifier:
    def __init__(self, policy, *, units=unit_metadata):
        self.policy, self.units = policy, units

    async def ui(self, peer_pid):
        pid, cgroup = await self.units('hyprneuro-ui.service')
        try:
            identity = process_identity(pid)
        except (OSError, ValueError):
            raise LaunchRejected('ui-process') from None
        if pid != peer_pid:
            raise LaunchRejected('ui-peer-pid')
        if identity['uid'] != os.getuid():
            raise LaunchRejected('ui-uid')
        if identity['cgroup'] != '0::' + cgroup:
            raise LaunchRejected('ui-cgroup')
        if hashlib.sha256(Path(f'/proc/{pid}/exe').read_bytes()).hexdigest() != self.policy.ui_sha256:
            raise LaunchRejected('ui-exe-hash')
        return identity

    def child(self, ui, pid, start):
        current_ui, child = process_identity(ui['pid']), process_identity(pid)
        expected = [str(self.policy.python), '-I', str(self.policy.entry),
                    '--explicit-connect', '--broker-fd=3']
        if (current_ui['start'] != ui['start'] or current_ui['exe'] != ui['exe']
                or child['start'] != start or child['uid'] != os.getuid()
                or child['parent'] != ui['pid'] or child['cgroup'] != ui['cgroup']
                or child['exe'] != str(self.policy.python.resolve()) or child['argv'] != expected
                or hashlib.sha256(self.policy.entry.read_bytes()).hexdigest() != self.policy.entry_sha256):
            raise PermissionError('Wrong fixed GTK child launch')
        return child

    async def owner(self, root):
        config = load_config(root)
        if Path(config['source']) != self.policy.source:
            raise PermissionError('Owner source differs from reviewed launch')
        instance = await metadata('/usr/bin/systemd-escape', '--path', config['root'])
        if not re.fullmatch(r'[A-Za-z0-9_\\.\-]+', instance):
            raise PermissionError('Invalid exact owner instance')
        pid, cgroup = await self.units('hyprneuro-pi-owner@' + instance + '.service')
        identity = process_identity(pid)
        if (identity['uid'] != os.getuid() or identity['cgroup'] != '0::' + cgroup
                or identity['exe'] != str(Path(config['node']).resolve())
                or identity['argv'] != [config['node'], str(self.policy.source / 'extensions/pi-owner/host.mjs')]):
            raise PermissionError('Wrong exact owner process')
        return config, identity

    def registration(self, config, owner, nonce, proof):
        fields = {'owner_root', 'owner_pid', 'owner_start', 'owner_session', 'control_generation',
                  'descriptor_sha256', 'task_id', 'app_id', 'workspace', 'read_policy_sha256', 'ops', 'nonce', 'mac'}
        if set(proof) != fields or proof['nonce'] != nonce:
            raise PermissionError('Wrong CONTROL registration challenge')
        body = {key: value for key, value in proof.items() if key != 'mac'}
        path = Path(config['root']) / 'control.key'
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != 32):
                raise PermissionError('Unsafe existing CONTROL credential')
            key = os.read(fd, 32)
        finally:
            os.close(fd)
        wire = json.dumps(body, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
        mac = hmac.new(key, b'hyprneuro.grant-registration/1\0' + wire, hashlib.sha256).hexdigest()
        paths = sorted(str(Path(config['root']) / 'home/workspace' / p) for p in config['read_paths'])
        expected = {'owner_root': config['root'], 'owner_pid': owner['pid'], 'owner_start': owner['start'],
                    'descriptor_sha256': hashlib.sha256((Path(config['root']) / 'owner.json').read_bytes()).hexdigest(),
                    'task_id': config['task_id'], 'app_id': 'hyprneuro-parent-read',
                    'workspace': str(Path(config['root']) / 'home/workspace'), 'ops': ['read'],
                    'read_policy_sha256': hashlib.sha256('\0'.join(paths).encode()).hexdigest()}
        if (not isinstance(proof['mac'], str) or not hmac.compare_digest(mac, proof['mac'])
                or any(proof.get(k) != v for k, v in expected.items())
                or any(not isinstance(proof[k], str) or not 1 <= len(proof[k]) <= 128
                       for k in ['owner_session', 'control_generation'])):
            raise PermissionError('Wrong owner CONTROL binding')
        return {k: v for k, v in body.items() if k != 'nonce'}


async def read_frame(reader, *, timeout=125):
    async with asyncio.timeout(timeout):
        raw = await reader.readline()
    if not raw.endswith(b'\n') or len(raw) > MAX_FRAME:
        raise ValueError('Bounded private control frame required')
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError('Private control object required')
    return value


async def send_frame(writer, value):
    raw = (canonical(value) + '\n').encode()
    if len(raw) > MAX_FRAME:
        raise ValueError('Private response exceeds bound')
    writer.write(raw)
    async with asyncio.timeout(3):
        await writer.drain()


def diagnostic_rejection(stage, error, counter):
    """Best-effort Linux FIFO only; no buffered I/O, shared flag change or fallback."""
    if counter >= 16 or sys.stderr is None or sys.platform != 'linux':
        return
    pinned = owned = None
    try:
        payload = (json.dumps(rejection_record(stage, error), ensure_ascii=True) + '\n').encode('ascii')
        if len(payload) > 512:  # <= Linux minimum PIPE_BUF; atomic or EAGAIN
            return
        pinned = os.dup(2)  # pin destination; NEVER change this shared description's flags
        fcntl.fcntl(pinned, fcntl.F_GETPIPE_SZ)  # kernel pipe check; no file metadata I/O
        original = os.fstat(pinned)
        if not stat.S_ISFIFO(original.st_mode):  # sockets, files, terminals: DROP
            return
        # Reopening the pinned FIFO creates an INDEPENDENT open file description.
        owned = os.open(f'/proc/self/fd/{pinned}', os.O_WRONLY | os.O_NONBLOCK | os.O_CLOEXEC)
        target = os.fstat(owned)
        if not stat.S_ISFIFO(target.st_mode) or (original.st_dev, original.st_ino) != (target.st_dev, target.st_ino):
            return
        os.write(owned, payload)  # one atomic nonblocking attempt; full/no reader => DROP
    except Exception:
        pass
    finally:
        for fd in (owned, pinned):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


class GrantControlServer:
    """No public socket dispatch; endpoint is bound only by its trusted host."""
    def __init__(self, core, verifier, *, identity_policy=None):
        self.core, self.verifier = core, verifier
        self.identity_policy = identity_policy
        self.identity_client = None  # single writer/CAS before any Connect await
        self.handlers = set()
        self.failures = 0
        self.diagnostic_count = 0

    async def refresh_authority(self, task_id):
        """Host-only authorization dispatch fence, never a consent operation.

        Refresh only an already PUBLISHED exact owned slot; no pending grant,
        caller task or raw SQL row can create eligibility through this hook.
        """
        boundary = self.identity_client
        if boundary is None or boundary.state != 'connected':
            return
        slot = self.core.slots.get(task_id)
        registration = self.core.registrations.get(slot.registration) if slot else None
        if (not slot or not slot.published or registration is None or not registration.live
                or registration.verification is not boundary.gate):
            return
        await boundary.snapshot('authorize')
        boundary.gate.enter_operation('authorize')

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        if len(self.handlers) >= 8:
            writer.close()
            await writer.wait_closed()
            return
        self.handlers.add(task)
        registration = None
        cleanup_started = False
        stage = 'peer'
        boundary = monitor = None
        try:
            sock = writer.get_extra_info('socket')
            peer, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise LaunchRejected('peer-uid')
            async with asyncio.timeout(3):
                stage = 'ui-identity'
                if self.identity_policy is not None:
                    from .identity_transport import ObserverClient
                    if self.identity_client is not None:
                        raise PermissionError('Previous observer cleanup not confirmed')
                    boundary = ObserverClient(self.identity_policy)
                    self.identity_client = boundary  # explicit Connect CAS BEFORE await
                    await boundary.start()
                    ui = (await boundary.snapshot('ui'))['ui']['process']
                    if ui['pid'] != peer:
                        raise LaunchRejected('ui-peer-pid')
                    boundary.gate.enter_operation('ui')  # Node host positive BEFORE launch challenge
                    async def watch_boundary():
                        while boundary.gate._alive():
                            await asyncio.sleep(.05)
                        boundary.gate.seal()
                        writer.close()  # notification only AFTER synchronous authority seal
                    monitor = asyncio.create_task(watch_boundary())
                else:
                    ui = await self.verifier.ui(peer)
                nonce = os.urandom(32).hex()
                await send_frame(writer, {'type': 'launch_challenge', 'nonce': nonce})
                stage = 'launch-frame'
                launch = await read_frame(reader, timeout=3)
                if (set(launch) != {'op', 'nonce', 'child_pid', 'child_start'} or launch['op'] != 'launch'
                        or launch['nonce'] != nonce or type(launch['child_pid']) is not int):
                    raise PermissionError('Wrong trusted launch attestation')
                stage = 'child-identity'
                if boundary is not None:
                    roles = await boundary.snapshot('child')
                    child = roles['child']['process']  # independently discovered, not request-selected
                    if child['pid'] != launch['child_pid'] or child['start'] != launch['child_start']:
                        raise PermissionError('Launch report differs from discovered fixed child')
                    boundary.gate.enter_operation('child')
                else:
                    child = self.verifier.child(ui, launch['child_pid'], launch['child_start'])
                stage = 'launch-ready'
                ready = {'type': 'launch_ready'}
                if boundary is not None:
                    ready.update(finite_session=True,deadline_ns=boundary.gate.deadline_ns)
                await send_frame(writer, ready)
            stage = 'private-operation'
            challenge = None
            while True:
                value = await read_frame(reader)
                op = value.get('op')
                if boundary is None and op not in {'release', 'invalidate', 'disconnect'}:
                    self.verifier.child(ui, child['pid'], child['start'])
                if op == 'owner_challenge' and set(value) == {'op', 'root'} and registration is None:
                    if boundary is not None:
                        if value['root'] != str(self.identity_policy.owner_root):
                            raise PermissionError('Owner root differs from closed role policy')
                        roles = await boundary.snapshot('owner_challenge')
                        config, owner = dict(self.identity_policy.config), roles['owner']['process']
                        boundary.gate.enter_operation('owner_challenge')
                    else:
                        config, owner = await self.verifier.owner(value['root'])
                    challenge = config, owner, os.urandom(32).hex()
                    await send_frame(writer, {'nonce': challenge[2]})
                elif op == 'register' and set(value) == {'op', 'proof'} and registration is None and challenge:
                    config, owner, nonce = challenge
                    challenge = None  # consumed, including failed proof
                    if boundary is not None:
                        roles = await boundary.snapshot('register')
                        current_config, current_owner = dict(self.identity_policy.config), roles['owner']['process']
                    else:
                        current_config, current_owner = await self.verifier.owner(config['root'])
                    if current_config != config or current_owner != owner:
                        raise PermissionError('Owner changed during registration')
                    binding = self.verifier.registration(config, owner, nonce, value['proof'])
                    registration = self.core.register(binding, verification=boundary.gate) if boundary is not None else self.core.register(binding)
                    cleanup_started = False
                    await send_frame(writer, {'registration': registration})
                elif op == 'request' and registration and set(value) == {'op', 'kind', 'scope', 'generation', 'native_call_id', 'consent_id', 'arguments_sha256'}:
                    if boundary is not None:
                        await boundary.snapshot('request')
                    result = self.core.request(registration, value['kind'], value['scope'],
                                               generation=value['generation'], native_call_id=value['native_call_id'],
                                               consent_id=value['consent_id'], arguments_sha256=value['arguments_sha256'])
                    await send_frame(writer, result)
                elif op == 'decision' and registration and set(value) == {'op', 'request', 'nonce', 'body_hash', 'allowed'}:
                    if boundary is not None:
                        roles = await boundary.snapshot('decision')
                        current_config, current_owner = dict(self.identity_policy.config), roles['owner']['process']
                    else:
                        current_config, current_owner = await self.verifier.owner(config['root'])
                        self.verifier.child(ui, child['pid'], child['start'])
                    if current_config != config or current_owner != owner:
                        raise PermissionError('Registered owner changed before decision')
                    # No await between final child/owner snapshot fence and the
                    # one-use core decision; the core rechecks its own gates.
                    try:
                        result = self.core.decide(registration, value['request'], value['nonce'], value['body_hash'], value['allowed'])
                    except ConsentDenied:
                        result = {'accepted': False, 'request': value['request'], 'decision': 'denied'}
                    await send_frame(writer, result)
                elif op == 'disconnect' and set(value) == {'op'} and boundary is not None:
                    boundary.gate.seal()  # seal before audit/CAS/manager I/O
                    if registration is not None:
                        self.core.invalidate(registration)
                        for slot in list(self.core.slots.values()):
                            if slot.registration == registration:
                                self.core.release(registration, slot.request)
                        registration = None
                    await boundary.close()
                    if self.identity_client is boundary:
                        self.identity_client = None
                    await send_frame(writer, {'disconnected': True})  # only AFTER confirmed reap
                    break
                elif op == 'release' and registration and set(value) == {'op', 'request'}:
                    await send_frame(writer, self.core.release(registration, value['request']))
                elif op == 'invalidate' and registration and set(value) == {'op'}:
                    cleanup_started = True
                    self.core.invalidate(registration)
                    for slot in list(self.core.slots.values()):
                        if slot.registration == registration:
                            self.core.release(registration, slot.request)
                    registration = None
                    await send_frame(writer, {'invalidated': True})
                else:
                    raise PermissionError('Unsupported private operation/state')
        except asyncio.CancelledError:
            if boundary is not None and boundary.gate is not None:
                boundary.gate.seal()
            raise
        except Exception as error:
            if boundary is not None and boundary.gate is not None:
                boundary.gate.seal()  # before diagnostics, persistence or response I/O
            self.failures += 1
            if registration:
                try:
                    self.core.invalidate(registration)  # eligibility BEFORE response I/O
                except Exception:
                    self.failures += 1  # invalidate seals before audit even if audit fails
            diagnostic_rejection(stage, error, self.diagnostic_count)
            self.diagnostic_count = min(16, self.diagnostic_count + 1)
            try:
                await send_frame(writer, {'error': rejection_record(stage, error)})
            except (OSError, ConnectionError, TimeoutError):
                pass
        finally:
            # Eligibility drops before any potentially blocking cleanup/audit.
            if boundary is not None and boundary.gate is not None:
                boundary.gate.seal()
            if monitor is not None:
                monitor.cancel()
            if registration and not cleanup_started:
                try:
                    self.core.invalidate(registration)
                except Exception:
                    self.failures += 1
                for slot in list(self.core.slots.values()):
                    if slot.registration == registration:
                        try:
                            self.core.release(registration, slot.request)
                        except Exception:
                            self.failures += 1  # unknown; never retry or broaden cleanup
            if boundary is not None:
                try:
                    await boundary.close()
                except BaseException:
                    self.failures += 1  # retain ownership cell, no retry/adoption
                else:
                    if self.identity_client is boundary:
                        self.identity_client = None  # exact ownership CAS; never clear a newer cell
            self.handlers.discard(task)
            writer.close()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (OSError, ConnectionError, TimeoutError):
                pass


class GrantControlClient:
    """Only accepts the intentionally inherited broker fd, never public RPC.

    One outstanding private request; timeout/error closes the connection and
    thereby invalidates registration. No replay after an uncertain response.
    """
    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer
        self.lock = asyncio.Lock()
        self.registration = None
        self.failed = False
        self.finite_session = False
        self.deadline_ns = None

    @property
    def connected(self):
        return not self.failed and not self.reader.at_eof() and not self.writer.is_closing()

    @classmethod
    async def inherited(cls, fd):
        if fd != 3:
            raise PermissionError('Exact reviewed inherited broker fd required')
        sock = socket.socket(fileno=fd)
        if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
            sock.close()
            raise PermissionError('Private Unix broker connection required')
        reader, writer = await asyncio.open_unix_connection(sock=sock, limit=MAX_FRAME + 1)
        try:
            ready = await read_frame(reader, timeout=3)
            client = cls(reader, writer)
            if ready != {'type': 'launch_ready'}:
                from .identity_session import boottime_ns, MAX_CONNECT_SECONDS
                if (set(ready) != {'type','finite_session','deadline_ns'} or ready['type'] != 'launch_ready'
                        or ready['finite_session'] is not True or type(ready['deadline_ns']) is not int
                        or not boottime_ns() < ready['deadline_ns'] <= boottime_ns()+MAX_CONNECT_SECONDS*1_000_000_000):
                    raise PermissionError('No reviewed finite launch handoff')
                client.finite_session = True
                client.deadline_ns = ready['deadline_ns']
            return client
        except BaseException:
            writer.close()
            await writer.wait_closed()
            raise

    async def call(self, op, **fields):
        async with self.lock:
            if self.failed:
                raise PermissionError('Private channel failed; no replay/reconnect')
            try:
                await send_frame(self.writer, dict(op=op, **fields))
                result = await read_frame(self.reader, timeout=5)
                if 'error' in result:
                    raise PermissionError('Private consent operation refused; no replay')
                return result
            except BaseException:
                self.failed = True
                self.writer.close()
                raise

    async def register(self, root, control):
        if self.registration is not None:
            raise PermissionError('Disconnect old broker registration first')
        site='owner-challenge'
        try:
            challenge = await self.call('owner_challenge', root=str(root))
            site='challenge-frame'
            if set(challenge) != {'nonce'} or not re.fullmatch('[0-9a-f]{64}', challenge['nonce']):
                raise PermissionError('Invalid server owner challenge')
            site='native-proof'
            proof = await control.call('broker_proof', nonce=challenge['nonce'])
            site='registration-rpc'
            result = await self.call('register', proof=proof)
            site='registration-frame'
            if set(result) != {'registration'} or not isinstance(result['registration'], str):
                raise PermissionError('No exact broker registration')
            self.registration = result['registration']
        except Exception as error:
            raise OwnerRegistrationRejected(site,error) from error

    async def invalidate(self):
        if self.registration is not None:
            result = await self.call('invalidate')
            if result != {'invalidated': True}:
                raise PermissionError('Uncertain scoped cleanup; no replay')
            self.registration = None
            return True
        return False

    async def disconnect_session(self):
        if not self.finite_session:
            raise PermissionError('No finite observer session')
        if await self.call('disconnect') != {'disconnected': True}:
            raise PermissionError('Observer cleanup unconfirmed; no replay')
        self.writer.close()

    async def close(self):
        self.writer.close()  # eligibility drops on EOF even if later cleanup fails
        try:
            async with asyncio.timeout(1):
                await self.writer.wait_closed()
        except (OSError, ConnectionError, TimeoutError):
            pass


def load_launch_policy(path, expected_sha256):
    path = Path(path)
    if not path.is_absolute() or path != path.resolve() or not re.fullmatch('[0-9a-f]{64}', expected_sha256):
        raise PermissionError('Canonical hash-pinned launch policy required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_nlink != 1
                or info.st_mode & 0o077 or info.st_size > 4096):
            raise PermissionError('Unsafe launch policy')
        raw = os.read(fd, 4097)
    finally:
        os.close(fd)
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise PermissionError('Changed launch policy')
    data = json.loads(raw)
    if set(data) != {'schema', 'python', 'entry', 'source', 'ui_sha256', 'entry_sha256'} or data.pop('schema') != 'hyprneuro.trusted-launch/1':
        raise PermissionError('Unknown launch policy')
    for field in ['python', 'entry', 'source']:
        data[field] = Path(data[field])
    policy = LaunchPolicy(**data)
    if (policy.entry != policy.entry.resolve() or policy.source != policy.source.resolve()
            or hashlib.sha256(policy.entry.read_bytes()).hexdigest() != policy.entry_sha256):
        raise PermissionError('Changed reviewed entry/source path')
    return policy
