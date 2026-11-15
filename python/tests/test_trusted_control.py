"""Real Unix/kernel/isolated child handoff; no actual GTK/model/grant claim."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest

from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.trusted_consent import ConsentJournal, TrustedConsent
from hyprneuro.trusted_control import (GrantControlServer, LaunchPolicy, LaunchVerifier,
                                      process_identity, read_frame, send_frame)


class ManagedHandoffTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.entry = self.root / 'entry.py'
        # Fixed fixture entry accepts only fd3 launch. It has no human Allow.
        self.entry.write_text('''import json,os,socket,sys
assert sys.argv[1:]==['--explicit-connect','--broker-fd=3']
s=socket.socket(fileno=3)
s.setblocking(True)
f=s.makefile('rwb',buffering=0)
ready=json.loads(f.readline())
assert ready=={'type':'launch_ready'}
f.write(b'{"op":"decision","request":"forged","allowed":true}\\n')
answer=json.loads(f.readline())
assert 'error' in answer
''')
        self.journal = ConsentJournal(self.root / 'audit.jsonl')
        self.store = SidecarStore(':memory:')
        self.core = TrustedConsent(self.store, self.journal)
        parent = process_identity(os.getpid())
        async def units(unit):
            self.assertEqual(unit, 'hyprneuro-ui.service')
            return parent['pid'], parent['cgroup'].split('::', 1)[1]
        policy = LaunchPolicy(Path(sys.executable), self.entry, self.root,
                              hashlib.sha256(Path('/proc/self/exe').read_bytes()).hexdigest(),
                              hashlib.sha256(self.entry.read_bytes()).hexdigest())
        self.verifier = LaunchVerifier(policy, units=units)
        self.control = GrantControlServer(self.core, self.verifier)
        self.path = self.root / 'private.sock'
        self.server = await asyncio.start_unix_server(self.control.handle, str(self.path), limit=4097)
        self.child = None

    async def asyncTearDown(self):
        if self.child is not None:
            if self.child.returncode is None:
                self.child.terminate()  # only this owned private fixture child
            await self.child.wait()
        self.server.close()
        await self.server.wait_closed()
        handlers = list(self.control.handlers)
        for task in handlers:
            task.cancel()
        await asyncio.gather(*handlers, return_exceptions=True)
        self.journal.close()
        self.store.close()
        self.tmp.cleanup()

    async def test_fixed_child_intentional_handoff_then_forged_decision_no_grant(self):
        # Kernel establishment peer is this parent, deliberately a GTK stand-in.
        connection = socket.socket(socket.AF_UNIX)
        connection.setblocking(False)
        await asyncio.get_running_loop().sock_connect(connection, str(self.path))
        raw = b''
        while not raw.endswith(b'\n'):
            raw += await asyncio.get_running_loop().sock_recv(connection, 4096)
        nonce = json.loads(raw)['nonce']
        # Fixture shell-free launch duplicates only this endpoint to fd3. preexec
        # is test-only; production uses GSubprocessLauncher.take_fd.
        fd = connection.fileno()
        self.child = await asyncio.create_subprocess_exec(
            sys.executable, '-I', str(self.entry), '--explicit-connect', '--broker-fd=3',
            pass_fds=tuple(set([fd, 3])), preexec_fn=lambda: os.dup2(fd, 3),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        identity = process_identity(self.child.pid)
        launch = dict(op='launch', nonce=nonce, child_pid=self.child.pid, child_start=identity['start'])
        await asyncio.get_running_loop().sock_sendall(connection, (json.dumps(launch)+'\n').encode())
        connection.close()  # child now holds intentional inherited connection
        out, error = await asyncio.wait_for(self.child.communicate(), 3)
        self.assertEqual(self.child.returncode, 0, error.decode())
        self.assertEqual(self.store.auth_list(), [])
        self.assertEqual(self.core.registrations, {})

    async def test_wrong_launch_nonce_closes_without_registration(self):
        reader, writer = await asyncio.open_unix_connection(str(self.path))
        await read_frame(reader)
        await send_frame(writer, dict(op='launch', nonce='wrong', child_pid=os.getpid(), child_start='wrong'))
        self.assertIn('error', await read_frame(reader))
        self.assertEqual(self.store.auth_list(), [])
        writer.close()
        await writer.wait_closed()

    async def test_child_metadata_is_consistency_not_loaded_code_attestation(self):
        ui = process_identity(os.getpid())
        with self.assertRaises(PermissionError):
            self.verifier.child(ui, os.getpid(), ui['start'])  # not its own child/argv


class CredentialLimitTests(unittest.TestCase):
    def test_transferred_socket_retains_establishment_peer_not_current_sender(self):
        left, right = socket.socketpair()
        try:
            established, uid, _ = struct.unpack('3i', right.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            self.assertEqual(established, os.getpid())
            pid = os.fork()
            if pid == 0:
                right.close()
                left.sendall(str(os.getpid()).encode())
                os._exit(0)
            left.close()
            actual_sender = int(right.recv(64))
            os.waitpid(pid, 0)
            observed, _, _ = struct.unpack('3i', right.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            self.assertEqual(observed, established)
            self.assertNotEqual(observed, actual_sender)  # explicitly NOT transfer detection
        finally:
            left.close()
            right.close()


class DecisionRevalidationTests(unittest.IsolatedAsyncioTestCase):
    """Real frame/state/core/broker; fixture verifier epochs, not owner attestation."""
    async def test_owner_drift_and_post_await_child_drift_before_allow(self):
        from unittest.mock import patch
        import hyprneuro.trusted_control as transport
        for drift in ['exit', 'epoch', 'descriptor', 'child']:
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                store=SidecarStore(':memory:');journal=ConsentJournal(root/'audit.jsonl')
                core=TrustedConsent(store,journal)
                binding=dict(owner_root=str(root),owner_pid=os.getpid(),owner_start='fixture-start',
                    owner_session='fixture-session',control_generation='fixture-control',
                    descriptor_sha256='a'*64,task_id='test',app_id='fixture',workspace=str(root/'workspace'),
                    read_policy_sha256='b'*64,ops=['read'])
                class Verifier:
                    calls=0
                    child_changed=False
                    async def ui(self,pid): return dict(pid=pid)
                    def child(self,ui,pid,start):
                        if self.child_changed: raise PermissionError('Fixture child drift')
                        return dict(pid=pid,start=start)
                    async def owner(self,path):
                        self.calls+=1
                        config=dict(root=str(root),descriptor='original')
                        owner=dict(pid=os.getpid(),start='fixture-start',cgroup='fixture-cgroup')
                        if self.calls>=3:
                            await asyncio.sleep(0)  # child MUST be checked after this await
                            if drift=='exit': raise PermissionError('Fixture owner exited')
                            if drift=='epoch': owner['start']='replacement-epoch'
                            if drift=='descriptor': config['descriptor']='changed'
                            if drift=='child': self.child_changed=True
                        return config,owner
                    def registration(self,*args): return binding
                verifier=Verifier();handler=GrantControlServer(core,verifier)
                server=await asyncio.start_unix_server(handler.handle,path=str(root/'private.sock'))
                writer=None;record=None
                original_send=transport.send_frame
                async def checked_send(writer,value):
                    if 'error' in value and record is not None:
                        self.assertFalse(record.live,'Invalidation must precede error response I/O')
                    await original_send(writer,value)
                try:
                    with patch.object(transport,'send_frame',checked_send), patch.object(store,'auth_upsert',wraps=store.auth_upsert) as writes:
                        reader,writer=await asyncio.open_unix_connection(str(root/'private.sock'))
                        launch=await read_frame(reader)
                        await send_frame(writer,dict(op='launch',nonce=launch['nonce'],child_pid=os.getpid(),child_start='fixture-child'))
                        self.assertEqual(await read_frame(reader),{'type':'launch_ready'})
                        await send_frame(writer,dict(op='owner_challenge',root=str(root)))
                        await read_frame(reader)
                        await send_frame(writer,dict(op='register',proof={}))
                        reg=(await read_frame(reader))['registration'];record=core.registrations[reg]
                        scope=dict(task_id='test',app_id='fixture',file_prefix=binding['workspace'],ops=['read'])
                        await send_frame(writer,dict(op='request',kind='grant_create',scope=scope,generation='fixture-gen',
                            native_call_id='fixture-native',consent_id='fixture-consent',arguments_sha256='c'*64))
                        pending=await read_frame(reader)
                        await send_frame(writer,dict(op='decision',allowed=True,**pending))
                        result=await read_frame(reader)
                        self.assertIn('error',result,'Stale owner/child must never publish Allow')
                        self.assertFalse(record.live)
                        self.assertEqual(writes.call_count,0);self.assertEqual(core.slots,{})
                        self.assertEqual(store.auth_list(),[]);self.assertEqual(core.pending,{})
                        with self.assertRaises(PermissionError):
                            core.request(reg,'grant_create',scope,generation='replay',native_call_id='replay')
                finally:
                    if writer:
                        writer.close();await writer.wait_closed()
                    server.close();await server.wait_closed()
                    tasks=list(handler.handlers)
                    for task in tasks:task.cancel()
                    await asyncio.gather(*tasks,return_exceptions=True)
                    journal.close();store.close()
