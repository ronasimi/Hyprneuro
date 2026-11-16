"""Fixed manager activation channel. Observer is read-only; broker supervises it.

No public RPC, model selectors, authority booleans or server capabilities. Caller
must supply ObserverPolicy from MAIN-rooted bootstrap, NEVER a peer's manifest
claim. Same-UID cooperative scope; intentional FD handoff is not transfer detection.
"""
import asyncio
import json
import os
import re
from pathlib import Path
import socket
import stat
import struct

from .identity_bootstrap import _json
from .identity_observer import (ObserverPolicy, SnapshotCollector, process_snapshot, read_service,
                                _json_pairs)
from .identity_session import IdentitySession, MAX_CONNECT_SECONDS, MAX_PROOF_NS, REQUIRED_ROLES, boottime_ns

FRAME_MAX = 16384
RPC_SECONDS = 3


async def _metadata(*args):
    from .trusted_control import metadata
    return await metadata(*args)


async def _read(reader):
    async with asyncio.timeout(RPC_SECONDS):
        raw = await reader.readline()
    if len(raw) > FRAME_MAX or not raw.endswith(b'\n'):
        raise PermissionError('Bounded observer frame required')
    return _json(raw)


async def _send(writer, value):
    raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)+'\n').encode()
    if len(raw) > FRAME_MAX:
        raise PermissionError('Observer frame exceeds bound')
    writer.write(raw)
    async with asyncio.timeout(RPC_SECONDS):
        await writer.drain()


async def _socket_contract(policy, *, active):
    spec = policy.units['socket']
    keys = ['FragmentPath','DropInPaths','ActiveState','Job','Listen','Accept',
            'FileDescriptorName','SocketMode','Triggers']
    args = ['/usr/bin/systemctl','--user','show',spec.name,'--all']
    for key in keys:
        args += ['-p',key]
    value = _json_pairs(await _metadata(*args))
    if set(value) != set(keys) or value['Job']:
        raise PermissionError('Incomplete or busy observer admission unit')
    if (value['FragmentPath'],*value['DropInPaths'].split()) != spec.fragments:
        raise PermissionError('Wrong observer socket fragments')
    if (value['ActiveState'] != ('active' if active else 'inactive')
            or value['Listen'] != str(policy.endpoint)+' (Stream)' or value['Accept'] != 'no'
            or value['FileDescriptorName'] != 'identity-session' or value['SocketMode'] != '0600'
            or value['Triggers'] != policy.units['helper'].name):
        raise PermissionError('Wrong fixed observer socket configuration')
    return value


def _peer(connection):
    return struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))


async def _close_writer(writer):
    writer.close()
    try:
        async with asyncio.timeout(1):
            await writer.wait_closed()
    except (OSError,TimeoutError):
        pass


async def serve_activated(policy):
    """ONE helper invocation, fd3 supplied only by the reviewed manager unit.

    No start/stop, consent, CONTROL credential, SQL or diagnostic emission here.
    Closing the accepted endpoint revokes the broker's local gate independently
    of observer metadata progress. Manager runtime limit is a separate watchdog.
    """
    if not isinstance(policy,ObserverPolicy):
        raise PermissionError('Reviewed observer policy required')
    policy.bootstrap.check_process_environment(os.environ)
    policy.check_namespace()
    policy.check_files()
    if (os.environ.get('LISTEN_PID') != str(os.getpid()) or os.environ.get('LISTEN_FDS') != '1'
            or os.environ.get('LISTEN_FDNAMES') != 'identity-session'):
        raise PermissionError('Wrong manager activation descriptors')
    listener=socket.socket(fileno=3)
    listener.set_inheritable(False)
    writer=None
    connection=None
    timer=None
    try:
        if (listener.family != socket.AF_UNIX or listener.type != socket.SOCK_STREAM
                or listener.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN) != 1
                or listener.getsockname() != str(policy.endpoint)):
            raise PermissionError('Substituted observer activation endpoint')
        # Consume activation metadata so no child could treat it as fresh.
        for key in ['LISTEN_PID','LISTEN_FDS','LISTEN_FDNAMES','LISTEN_PIDFDID']:
            os.environ.pop(key,None)
        own=await read_service(policy,'helper')
        self_identity=process_snapshot(os.getpid(),policy,policy.launch.python)
        if own['pid'] != os.getpid() or self_identity['argv'] != list(policy.units['helper'].argv):
            raise PermissionError('Wrong actual helper launch')
        await _socket_contract(policy,active=True)
        listener.setblocking(False)  # owned manager listening description, not broker channel
        async with asyncio.timeout(RPC_SECONDS):
            connection,_=await asyncio.get_running_loop().sock_accept(listener)
        listener.close()  # only ONE accepted connection; no queued helper daemon
        pid,uid,_=_peer(connection)
        if uid != os.getuid():
            connection.close()
            raise PermissionError('Wrong observer client owner')
        broker=await read_service(policy,'broker')
        broker_identity=process_snapshot(pid,policy,policy.launch.python)
        if (pid != broker['pid'] or broker_identity['argv'] != list(policy.units['broker'].argv)
                or broker_identity['cgroup'] != '0::'+broker['cgroup']):
            connection.close()
            raise PermissionError('Wrong observer client process')
        reader,writer=await asyncio.open_unix_connection(sock=connection,limit=FRAME_MAX+1)
        hello=await _read(reader)
        if (set(hello) != {'type','generation','deadline_ns','context_sha256','manifest_sha256'}
                or hello['type'] != 'hello' or not isinstance(hello['generation'],str)
                or len(hello['generation']) != 32 or any(c not in '0123456789abcdef' for c in hello['generation'])
                or type(hello['deadline_ns']) is not int
                or hello['context_sha256'] != policy.bootstrap.context.sha256
                or hello['manifest_sha256'] != policy.bootstrap.manifest.sha256):
            raise PermissionError('Wrong observer session binding')
        generation=hello['generation']
        deadline=min(hello['deadline_ns'],boottime_ns()+MAX_CONNECT_SECONDS*1_000_000_000)
        if deadline <= boottime_ns():
            raise PermissionError('Expired observer Connect')
        collector=SnapshotCollector(policy)
        await collector.observe('ui')  # launcher liveness exists before child/owner
        def alive():
            from .trusted_control import process_identity
            if boottime_ns() >= deadline:
                return False
            try:
                policy.revalidate_configuration()
                current=process_identity(pid)
                if current != {k:broker_identity[k] for k in current}:
                    return False
                for role,value in collector._slots.items():
                    current=process_identity(value['process']['pid'])
                    if current != {k:value['process'][k] for k in current}:
                        return False
            except (OSError,ValueError):
                return False
            return True
        def watch():
            nonlocal timer
            if not alive():
                writer.close()
                return
            timer=asyncio.get_running_loop().call_later(.05,watch)
        watch()
        await _send(writer,dict(type='hello',generation=generation,helper=own,broker=broker,
                                cap_seconds=MAX_CONNECT_SECONDS))
        sequence=0
        registered=False
        while alive():
            # Idle is bounded by local watcher, not the per-message RPC timer.
            async with asyncio.timeout(max(.001,(deadline-boottime_ns())/1e9)):
                raw=await reader.readline()
            if not raw:
                break
            if len(raw)>FRAME_MAX or not raw.endswith(b'\n'):
                raise PermissionError('Invalid observer request frame')
            value=_json(raw)
            if value=={'type':'disconnect','generation':generation}:
                break
            if (set(value) != {'type','operation','generation','seq','nonce'} or value['type'] != 'snapshot'
                    or value['operation'] not in REQUIRED_ROLES or value['generation'] != generation
                    or type(value['seq']) is not int or value['seq'] != sequence+1
                    or not isinstance(value['nonce'],str) or len(value['nonce']) != 64
                    or any(c not in '0123456789abcdef' for c in value['nonce'])):
                raise PermissionError('Invalid closed observer request')
            if value['operation']=='register' and registered:
                raise PermissionError('Duplicate observer registration')
            sequence=value['seq']
            roles=await collector.observe(value['operation'])
            if not alive():
                raise PermissionError('Observer role lost before response')
            if value['operation']=='register':
                registered=True
            issued=boottime_ns()
            await _send(writer,dict(type='snapshot',operation=value['operation'],generation=generation,
                seq=sequence,nonce=value['nonce'],issued_ns=issued,expires_ns=min(issued+MAX_PROOF_NS,deadline),
                roles=roles,broker=broker,helper=own,node=policy.node))
    finally:
        if timer is not None:
            timer.cancel()
        listener.close()
        if writer is not None:
            await _close_writer(writer)
        elif connection is not None:
            connection.close()


class ObserverClient:
    """Broker-owned connection; must not be constructed from a peer's policy."""
    def __init__(self,policy):
        if not isinstance(policy,ObserverPolicy):
            raise PermissionError('Main-rooted observer policy required')
        self.policy=policy
        self.state='new'
        self.gate=None
        self.reader=self.writer=None
        self.helper=None
        self.broker=None
        self._admission=False
        self._cleanup_attempted=False
        self._rpc_lock=asyncio.Lock()

    async def start(self):
        if self.state!='new':
            raise PermissionError('Connect already attempted')
        self.state='connecting'  # CAS BEFORE any await; no automatic retry
        started=boottime_ns()
        try:
            return await self._start(started)
        except BaseException:
            if self.gate is not None:
                self.gate.seal()
            self.state='revoking'
            raise

    async def _start(self,started):
        policy=self.policy
        policy.bootstrap.check_process_environment(os.environ)
        policy.check_files()
        cold_helper=await read_service(policy,'helper',live=False)  # authenticate BEFORE start
        if cold_helper['pid'] != 0:
            raise PermissionError('Existing helper; no adoption')
        await _socket_contract(policy,active=False)
        self.broker=await read_service(policy,'broker')
        if self.broker['pid'] != os.getpid():
            raise PermissionError('Client is not the fixed broker')
        policy.check_files()
        self._admission=True  # a timed-out start may still have queued a job
        await _metadata('/usr/bin/systemctl','--user','start',policy.units['socket'].name)
        await _socket_contract(policy,active=True)
        manager=_json(await _metadata('/usr/bin/busctl','--user','--json=short','call',
            'org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus',
            'GetConnectionUnixProcessID','s','org.freedesktop.systemd1'))
        if manager.get('type')!='u' or not isinstance(manager.get('data'),list) or len(manager['data'])!=1 or type(manager['data'][0]) is not int:
            raise PermissionError('Unknown manager identity')
        endpoint=policy.endpoint.lstat()
        parent=policy.endpoint.parent.stat()
        if (not stat.S_ISSOCK(endpoint.st_mode) or endpoint.st_uid!=os.getuid()
                or stat.S_IMODE(endpoint.st_mode)!=0o600 or parent.st_uid!=os.getuid()
                or stat.S_IMODE(parent.st_mode)!=0o700):
            raise PermissionError('Wrong manager-created endpoint')
        connection=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            connection.setblocking(False)
            async with asyncio.timeout(RPC_SECONDS):
                await asyncio.get_running_loop().sock_connect(connection,str(policy.endpoint))
            pid,uid,_=_peer(connection)
            if pid!=manager['data'][0] or uid!=os.getuid() or connection.getpeername()!=str(policy.endpoint):
                raise PermissionError('Substituted observer listener')
            self.gate=IdentitySession(connection,started_ns=started)
            self.gate._configuration_fence=policy.revalidate_configuration
            self.reader,self.writer=await asyncio.open_unix_connection(sock=connection,limit=FRAME_MAX+1)
        except BaseException:
            connection.close()
            raise
        await _send(self.writer,dict(type='hello',generation=self.gate.generation,
            deadline_ns=self.gate.deadline_ns,context_sha256=policy.bootstrap.context.sha256,
            manifest_sha256=policy.bootstrap.manifest.sha256))
        hello=await _read(self.reader)
        self.helper=await read_service(policy,'helper')
        if (set(hello)!={'type','generation','helper','broker','cap_seconds'} or hello['type']!='hello'
                or hello['generation']!=self.gate.generation or hello['helper']!=self.helper
                or hello['broker']!=self.broker or type(hello['cap_seconds']) is not int
                or hello['cap_seconds']!=MAX_CONNECT_SECONDS):
            raise PermissionError('Wrong manager-launched helper')
        policy.check_files()
        await _metadata('/usr/bin/systemctl','--user','stop',policy.units['socket'].name)
        await _socket_contract(policy,active=False)
        self._admission=False
        policy.check_files()
        self.gate.watch()
        self.state='connected'
        return self

    async def snapshot(self,operation):
        if self.gate is not None:
            self.gate._expires=0  # BEFORE waiting for another in-flight operation
        async with self._rpc_lock:
            return await self._snapshot(operation)

    async def _snapshot(self,operation):
        if self.state!='connected' or self.gate is None:
            raise PermissionError('No explicit observer Connect')
        challenge=self.gate.begin_snapshot(operation)
        try:
            expected={'ui':await read_service(self.policy,'ui')}
            if 'owner' in REQUIRED_ROLES[operation]:
                expected['owner']=await read_service(self.policy,'owner')
            helper=await read_service(self.policy,'helper')
            broker=await read_service(self.policy,'broker')
            if helper!=self.helper or broker!=self.broker:
                raise PermissionError('Observer launch generation changed')
            await _send(self.writer,dict(type='snapshot',**challenge))
            packet=await _read(self.reader)  # LAST await before full final fences
            self._validate_snapshot(packet,operation,expected)
            self.gate._accept_checked_snapshot(packet)
            return packet['roles']
        except BaseException:
            self.gate.seal()  # eligibility BEFORE caller logging or cleanup I/O
            self.state='revoking'
            raise

    def _validate_snapshot(self,packet,operation,expected):
        if (set(packet)!={'type','operation','generation','seq','nonce','issued_ns','expires_ns','roles','broker','helper','node'}
                or packet['type']!='snapshot' or packet['operation']!=operation
                or json.dumps(packet['node'],sort_keys=True,separators=(',',':'))!=json.dumps(self.policy.node,sort_keys=True,separators=(',',':'))
                or packet['broker']!=self.broker or packet['helper']!=self.helper
                or not isinstance(packet['roles'],dict) or set(packet['roles'])!=REQUIRED_ROLES[operation]):
            raise PermissionError('Wrong combined observer snapshot')
        self.policy.check_files()
        ui=packet['roles']['ui']['process']
        for role,item in packet['roles'].items():
            p=item['process']
            if (set(p)!={'pid','start','parent','uid','exe','cgroup','argv','exe_sha256','exe_inode','exe_uid','exe_gid','exe_mode','exe_nlink','namespaces'}
                    or p['uid']!=os.getuid() or type(p['uid']) is not int
                    or not isinstance(p['namespaces'],dict) or set(p['namespaces'])!={'user','pid','mnt','time'}
                    or type(p['parent']) is not int or p['parent'] <= 0
                    or any(type(p[k]) is not int for k in ['exe_uid','exe_gid','exe_mode','exe_nlink'])
                    or not isinstance(p['exe_inode'],list) or len(p['exe_inode'])!=2
                    or any(type(n) is not int or n<0 for n in p['exe_inode'])):
                raise PermissionError('Wrong process snapshot schema')
            for name,value in p['namespaces'].items():
                if not isinstance(value,str) or not re.fullmatch(name+r':\[[0-9]+\]',value):
                    raise PermissionError('Invalid process namespace identity')
            if p['namespaces']['user']!=self.policy.host_namespace or p['namespaces']['time']!=os.readlink('/proc/self/ns/time'):
                raise PermissionError('Wrong declared role namespace')
            executable=self.policy.launch.python if role=='child' else self.policy.config['node'] if role=='owner' else self.policy.units['ui'].argv[0]
            canonical=str(Path(executable).resolve())
            inode=self.policy._files[canonical][:2]
            if p['exe']!=canonical or p['exe_sha256']!=self.policy.catalog[canonical] or p['exe_inode']!=list(inode):
                raise PermissionError('Wrong executable snapshot')
            if role=='child':
                argv=[str(self.policy.launch.python),'-I',str(self.policy.launch.entry),'--explicit-connect','--broker-fd=3']
                if set(item)!={'process'} or p['parent']!=ui['pid'] or p['cgroup']!=ui['cgroup']:
                    raise PermissionError('Wrong independent child parent chain')
            else:
                if item['unit']!=expected[role] or p['pid']!=expected[role]['pid'] or p['cgroup']!='0::'+expected[role]['cgroup']:
                    raise PermissionError('Wrong exact role unit')
                argv=list(self.policy.units['ui'].argv) if role=='ui' else [self.policy.config['node'],str(self.policy.host_entry)]
                if set(item)!=({'process','unit'} if role=='ui' else {'process','unit','binding'}):
                    raise PermissionError('Extra role data')
            local=self.policy._files[canonical]
            expected_owner=(0,0,self.policy.node['mode'],1) if role=='owner' else (local[5],local[6],stat.S_IMODE(local[7]),local[8])
            if tuple(p[k] for k in ['exe_uid','exe_gid','exe_mode','exe_nlink'])!=expected_owner:
                raise PermissionError('Wrong host executable ownership')
            if p['argv']!=argv:
                raise PermissionError('Wrong fixed role argv')
            if role=='owner':
                config=self.policy.config
                paths=sorted(str(self.policy.owner_root/'home/workspace'/p) for p in config['read_paths'])
                from .identity_observer import digest
                binding=dict(owner_root=str(self.policy.owner_root),descriptor_sha256=self.policy.catalog[str(self.policy.owner_root/'owner.json')],
                    task_id=config['task_id'],app_id='hyprneuro-parent-read',workspace=str(self.policy.owner_root/'home/workspace'),
                    read_policy_sha256=digest('\0'.join(paths).encode()),ops=['read'])
                if item['binding']!=binding:
                    raise PermissionError('Wrong immutable parent read policy')

    async def close(self):
        if self.gate is not None:
            self.gate.close()  # revoke FIRST, independent of all helper/manager I/O
        if self._cleanup_attempted:
            if self.state!='closed':
                raise PermissionError('Observer cleanup unknown; no automatic retry')
            return
        self._cleanup_attempted=True
        self.state='revoking'
        try:
            if self.writer is not None:
                await _close_writer(self.writer)
            if self._admission:
                await _metadata('/usr/bin/systemctl','--user','stop',self.policy.units['socket'].name)
                await _socket_contract(self.policy,active=False)
                self._admission=False
            if self.helper is not None:
                # Do not stop a substituted generation. Read only ownership fields;
                # cleanup must remain possible after config/bootstrap drift.
                name=self.policy.units['helper'].name
                raw=_json_pairs(await _metadata('/usr/bin/systemctl','--user','show',name,'-p','MainPID','-p','InvocationID'))
                if raw['MainPID']!='0' and (raw['MainPID']!=str(self.helper['pid']) or raw['InvocationID']!=self.helper['invocation']):
                    raise PermissionError('Helper cleanup ownership changed')
                await _metadata('/usr/bin/systemctl','--user','stop',name)
                raw=_json_pairs(await _metadata('/usr/bin/systemctl','--user','show',name,
                                               '-p','MainPID','-p','Job','-p','ControlGroup'))
                if raw!={'MainPID':'0','Job':'','ControlGroup':''}:
                    raise PermissionError('Helper stop/reap unconfirmed')
            elif self.gate is not None:
                raw=_json_pairs(await _metadata('/usr/bin/systemctl','--user','show',self.policy.units['helper'].name,
                                               '-p','MainPID','-p','Job','-p','ControlGroup'))
                if raw!={'MainPID':'0','Job':'','ControlGroup':''}:
                    raise PermissionError('Unclaimed helper cleanup unknown')
            self.state='closed'
        except BaseException:
            self.state='cleanup-unknown'
            raise
