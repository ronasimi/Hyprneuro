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


async def metadata(*args):
    process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                  stderr=asyncio.subprocess.DEVNULL)
    try:
        async with asyncio.timeout(3):
            out = await process.stdout.read(16385)
            await process.wait()
        if process.returncode or len(out) > 16384:
            raise PermissionError('Uncertain unit metadata')
        return out.decode().strip()
    finally:
        if process.returncode is None:
            process.terminate()  # only this owned metadata subprocess, never a service
            await process.wait()


async def unit_metadata(unit):
    out = await metadata('/usr/bin/systemctl', '--user', 'show', unit,
                         '-p', 'MainPID', '-p', 'ControlGroup', '-p', 'ActiveState', '-p', 'Job')
    value = dict(line.split('=', 1) for line in out.splitlines())
    if value['ActiveState'] != 'active' or value['Job'] or int(value['MainPID']) <= 0:
        raise PermissionError('Expected exact active unit without pending job')
    return int(value['MainPID']), value['ControlGroup']


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
        identity = process_identity(pid)
        if (pid != peer_pid or identity['uid'] != os.getuid()
                or identity['cgroup'] != '0::' + cgroup
                or hashlib.sha256(Path(f'/proc/{pid}/exe').read_bytes()).hexdigest() != self.policy.ui_sha256):
            raise PermissionError('Wrong reviewed GTK peer')
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
    stages = {'peer', 'ui-identity', 'launch-frame', 'child-identity', 'launch-ready', 'private-operation'}
    category = 'timeout' if isinstance(error, TimeoutError) else 'identity' if isinstance(error, PermissionError) else 'failure'
    pinned = owned = None
    try:
        payload = (json.dumps({'diagnostic': 'NONAUTHORITATIVE',
                              'stage': stage if stage in stages else 'unknown',
                              'category': category}, ensure_ascii=True) + '\n').encode('ascii')
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
    def __init__(self, core, verifier):
        self.core, self.verifier = core, verifier
        self.handlers = set()
        self.failures = 0
        self.diagnostic_count = 0

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
        try:
            sock = writer.get_extra_info('socket')
            peer, uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != os.getuid():
                raise PermissionError('Wrong private peer UID')
            async with asyncio.timeout(3):
                stage = 'ui-identity'
                ui = await self.verifier.ui(peer)
                nonce = os.urandom(32).hex()
                await send_frame(writer, {'type': 'launch_challenge', 'nonce': nonce})
                stage = 'launch-frame'
                launch = await read_frame(reader, timeout=3)
                if (set(launch) != {'op', 'nonce', 'child_pid', 'child_start'} or launch['op'] != 'launch'
                        or launch['nonce'] != nonce or type(launch['child_pid']) is not int):
                    raise PermissionError('Wrong trusted launch attestation')
                stage = 'child-identity'
                child = self.verifier.child(ui, launch['child_pid'], launch['child_start'])
                stage = 'launch-ready'
                await send_frame(writer, {'type': 'launch_ready'})
            stage = 'private-operation'
            challenge = None
            while True:
                value = await read_frame(reader)
                self.verifier.child(ui, child['pid'], child['start'])
                op = value.get('op')
                if op == 'owner_challenge' and set(value) == {'op', 'root'} and registration is None:
                    config, owner = await self.verifier.owner(value['root'])
                    challenge = config, owner, os.urandom(32).hex()
                    await send_frame(writer, {'nonce': challenge[2]})
                elif op == 'register' and set(value) == {'op', 'proof'} and registration is None and challenge:
                    config, owner, nonce = challenge
                    challenge = None  # consumed, including failed proof
                    current_config, current_owner = await self.verifier.owner(config['root'])
                    if current_config != config or current_owner != owner:
                        raise PermissionError('Owner changed during registration')
                    binding = self.verifier.registration(config, owner, nonce, value['proof'])
                    registration = self.core.register(binding)
                    cleanup_started = False
                    await send_frame(writer, {'registration': registration})
                elif op == 'request' and registration and set(value) == {'op', 'kind', 'scope', 'generation', 'native_call_id', 'consent_id', 'arguments_sha256'}:
                    result = self.core.request(registration, value['kind'], value['scope'],
                                               generation=value['generation'], native_call_id=value['native_call_id'],
                                               consent_id=value['consent_id'], arguments_sha256=value['arguments_sha256'])
                    await send_frame(writer, result)
                elif op == 'decision' and registration and set(value) == {'op', 'request', 'nonce', 'body_hash', 'allowed'}:
                    current_config, current_owner = await self.verifier.owner(config['root'])
                    if current_config != config or current_owner != owner:
                        raise PermissionError('Registered owner changed before decision')
                    self.verifier.child(ui, child['pid'], child['start'])
                    # No await between final child/owner snapshot fence and the
                    # one-use core decision; the core rechecks its own gates.
                    try:
                        result = self.core.decide(registration, value['request'], value['nonce'], value['body_hash'], value['allowed'])
                    except ConsentDenied:
                        result = {'accepted': False, 'request': value['request'], 'decision': 'denied'}
                    await send_frame(writer, result)
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
            raise
        except Exception as error:
            self.failures += 1
            if registration:
                try:
                    self.core.invalidate(registration)  # eligibility BEFORE response I/O
                except Exception:
                    self.failures += 1  # invalidate seals before audit even if audit fails
            diagnostic_rejection(stage, error, self.diagnostic_count)
            self.diagnostic_count = min(16, self.diagnostic_count + 1)
            try:
                await send_frame(writer, {'error': str(error)[:300]})
            except (OSError, ConnectionError, TimeoutError):
                pass
        finally:
            # Eligibility drops before any potentially blocking cleanup/audit.
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
            if await read_frame(reader, timeout=3) != {'type': 'launch_ready'}:
                raise PermissionError('No reviewed launch handoff')
            return cls(reader, writer)
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
        challenge = await self.call('owner_challenge', root=str(root))
        if set(challenge) != {'nonce'} or not re.fullmatch('[0-9a-f]{64}', challenge['nonce']):
            raise PermissionError('Invalid server owner challenge')
        proof = await control.call('broker_proof', nonce=challenge['nonce'])
        result = await self.call('register', proof=proof)
        if set(result) != {'registration'} or not isinstance(result['registration'], str):
            raise PermissionError('No exact broker registration')
        self.registration = result['registration']

    async def invalidate(self):
        if self.registration is not None:
            result = await self.call('invalidate')
            if result != {'invalidated': True}:
                raise PermissionError('Uncertain scoped cleanup; no replay')
            self.registration = None
            return True
        return False

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
