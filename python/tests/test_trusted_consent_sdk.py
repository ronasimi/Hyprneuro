"""Actual SDK + real broker + inherited private channel + managed adapter.

Synthetic GTK-parent/Allow packets and fixture unit metadata, NOT actual GTK,
logind/systemd attestation acceptance or live human consent. Model HTTP is local
synthetic SSE on a fresh port; never contacts production/model port8081.
"""
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import unittest

from hyprneuro.pi_owner_service import SCHEMA, environment
from hyprneuro.sidecar import SidecarServer
from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.trusted_consent import ConsentJournal, TrustedConsent
from hyprneuro.trusted_control import GrantControlServer, LaunchPolicy, LaunchVerifier, process_identity


@unittest.skipUnless(os.environ.get('PI_HARNESS_SDK') and os.environ.get('PI_HARNESS_DURABLE'),
                     'Explicit installed reviewed SDK/Durable paths required')
class PrivateSDKConsentTests(unittest.IsolatedAsyncioTestCase):
    async def test_activation_exact_read_continuation_then_owned_disconnect(self):
        await self.workflow(allow_read=True, reconnect=True)

    async def test_denied_exact_read_never_reaches_model_then_owned_disconnect(self):
        await self.workflow(allow_read=False)

    async def test_lost_owned_cleanup_reply_retains_native_unknown_without_retry(self):
        await self.workflow(allow_read=True, lost_cleanup_reply=True)

    async def workflow(self, *, allow_read, reconnect=False, lost_cleanup_reply=False):
        source = Path(__file__).resolve().parents[2]
        root = Path(tempfile.mkdtemp(prefix='tg-sdk-'))  # retain full fixture on failure
        owner = root / 'owner'
        (owner / 'home/workspace').mkdir(parents=True, mode=0o700)
        (owner / 'home').chmod(0o700)
        owner.chmod(0o700)
        (owner / 'home/workspace/fixture.txt').write_text('PRIVATE_CHANNEL_CANARY\n')
        runtime = root / 'runtime'; runtime.mkdir(mode=0o700)
        (runtime / 'hyprharness').mkdir(mode=0o700)
        config = dict(schema=SCHEMA, root=str(owner), source=str(source), node='/usr/bin/node',
                      sdk=os.environ['PI_HARNESS_SDK'], durable=os.environ['PI_HARNESS_DURABLE'],
                      pi='/home/ron/.pi/agent/bin/pi', read_paths=['fixture.txt'], task_id='fixture-private')
        descriptor = owner / 'owner.json'
        descriptor.write_text(json.dumps(config)); descriptor.chmod(0o600)
        calls = []
        class Model(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                calls.append(body)
                if body['messages'][-1]['role'] == 'user':
                    delta = {'tool_calls':[{'index':0,'id':'private_sdk_read_'+str(len(calls)),'type':'function',
                              'function':{'name':'read','arguments':'{"path":"fixture.txt"}'}}]}
                else:
                    delta = {'content':'PRIVATE_SDK_READ_DONE'}
                data = ('data: '+json.dumps({'choices':[{'index':0,'delta':delta,
                        'finish_reason':'tool_calls' if 'tool_calls' in delta else 'stop'}]})+'\n\ndata: [DONE]\n\n').encode()
                self.send_response(200); self.send_header('Content-Type','text/event-stream')
                self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
        model = ThreadingHTTPServer(('127.0.0.1',0), Model)
        thread = threading.Thread(target=model.serve_forever, daemon=True); thread.start()
        log = (root / 'owner.log').open('wb')
        env = environment(config, runtime)
        env['HYPRNEURO_PI_TEXT_BASE_URL'] = f'http://127.0.0.1:{model.server_port}/v1'
        node = bridge = None
        servers = []; tasks = []; ctl = None
        journal = ConsentJournal(root / 'audit.jsonl')
        store = SidecarStore(root / 'broker.sqlite')
        core = TrustedConsent(store, journal)
        public = SidecarServer(store, assistant_enabled=True, trusted_consent=core)
        try:
            servers.append(await asyncio.start_unix_server(public.handle, path=str(runtime/'hyprharness/sidecar.sock')))
            node = await asyncio.create_subprocess_exec(config['node'],str(source/'extensions/pi-owner/host.mjs'),
                                                        env=env, stdout=log, stderr=log)
            async with asyncio.timeout(10):
                while not (owner/'owner.sock').exists():
                    if node.returncode is not None: self.fail('Fixture owner startup failed; '+str(root))
                    await asyncio.sleep(.02)
            entry = root / 'entry.py'
            entry.write_text('import sys\nsys.path.insert(0,'+repr(str(source/'python/src'))+')\n'
                             'from hyprneuro.pi_desktop_bridge import main\nraise SystemExit(main())\n')
            async def units(unit):
                # Explicit fixture replacement of systemd metadata ONLY. All
                # PID/start/argv/UID/ancestry/cgroup/hash and HMAC checks are real.
                pid = os.getpid() if unit == 'hyprneuro-ui.service' else node.pid
                ident = process_identity(pid)
                return pid, ident['cgroup'].split('::',1)[1]
            policy = LaunchPolicy(Path(sys.executable),entry,source,
                                  hashlib.sha256(Path('/proc/self/exe').read_bytes()).hexdigest(),
                                  hashlib.sha256(entry.read_bytes()).hexdigest())
            verifier = LaunchVerifier(policy, units=units)
            await verifier.owner(owner)  # expose exact metadata failure, not generic UI error
            ctl = GrantControlServer(core,verifier)
            private = root/'control.sock'
            servers.append(await asyncio.start_unix_server(ctl.handle,path=str(private),limit=4097))
            connection = socket.socket(socket.AF_UNIX); connection.setblocking(False)
            loop = asyncio.get_running_loop(); await loop.sock_connect(connection,str(private))
            challenge = b''
            while not challenge.endswith(b'\n'): challenge += await loop.sock_recv(connection,4096)
            nonce = json.loads(challenge)['nonce']; fd = connection.fileno()
            child_env = {'PATH':'/usr/bin:/bin','HOME':str(root),'XDG_RUNTIME_DIR':str(runtime),
                         'XDG_SESSION_ID':os.environ.get('XDG_SESSION_ID','2'),'PYTHONDONTWRITEBYTECODE':'1'}
            bridge = await asyncio.create_subprocess_exec(sys.executable,'-I',str(entry),'--explicit-connect','--broker-fd=3',
                        pass_fds=tuple(set([fd,3])),preexec_fn=lambda:os.dup2(fd,3),env=child_env,
                        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=log)
            attestation = dict(op='launch',nonce=nonce,child_pid=bridge.pid,child_start=process_identity(bridge.pid)['start'])
            await loop.sock_sendall(connection,(json.dumps(attestation)+'\n').encode());connection.close()
            async def send(packet):
                bridge.stdin.write((json.dumps(packet)+'\n').encode());await bridge.stdin.drain()
            packets=[]
            async def until(predicate, *, allow_error=False):
                async with asyncio.timeout(20):
                    while True:
                        raw=await bridge.stdout.readline()
                        self.assertTrue(raw,'Bridge EOF; fixture '+str(root))
                        packet=json.loads(raw);packets.append(packet)
                        if not allow_error:
                            self.assertNotIn(packet.get('type'),('error','unavailable'),str(packet)+' fixture '+str(root))
                        if predicate(packet): return packet
            await until(lambda p:p.get('type')=='bridge_ready')
            # Public self-grant denial is exercised against the SAME real broker.
            with self.assertRaisesRegex(PermissionError,'Trusted grant capability required'):
                public.dispatch(dict(action='auth_create',task_id=config['task_id'],app_id='hyprneuro-parent-read',
                                     file_prefix=str(owner/'home/workspace'),ops=['read'],approved=True))
            await send(dict(op='connect',root=str(owner)))
            await until(lambda p:p.get('type')=='connected')
            await send(dict(op='chat',text='Synthetic private-channel read fixture only.'))
            consent_ids=[]
            for kind in ['grant_create','read_decision']:
                packet=await until(lambda p:p.get('event',{}).get('type')=='consent')
                event=packet['event'];self.assertEqual(event['audit']['kind'],kind);consent_ids.append(event['id'])
                # SYNTHETIC fixture input, never an automated real human Allow.
                await send(dict(op='consent',answer_id=event['id'],allowed=kind=='grant_create' or allow_read))
            await until(lambda p:p.get('type')=='result' and p.get('op')=='chat')
            self.assertEqual(len(calls),2)
            if allow_read:
                self.assertIn('PRIVATE_CHANNEL_CANARY',json.dumps(calls[1]['messages']))
            else:
                self.assertNotIn('PRIVATE_CHANNEL_CANARY',json.dumps(calls[1]['messages']))
                self.assertIn('Trusted human approval required',json.dumps(calls[1]['messages']))
            self.assertTrue(core.broker.check(config['task_id'],'read',app_id='hyprneuro-parent-read',
                                              path=str(owner/'home/workspace/fixture.txt'))['allowed'])
            records=[json.loads(line) for line in (root/'audit.jsonl').read_text().splitlines()]
            self.assertEqual([r['event']['consent_id'] for r in records if r['event']['kind']=='request'],consent_ids)
            session_id = next(iter(core.registrations.values())).binding['owner_session']
            cleanup_calls=[]
            if lost_cleanup_reply:
                release=core.release
                def committed_then_lost(*args):
                    cleanup_calls.append(args)
                    release(*args)  # real exact SQL update + durable release
                    raise OSError('Synthetic reply lost AFTER committed owned cleanup')
                core.release=committed_then_lost
            checkpoint=owner/'checkpoint.json'
            before=checkpoint.stat().st_mtime_ns
            await send(dict(op='disconnect'))
            if lost_cleanup_reply:
                await until(lambda p:p.get('type')=='error' and p.get('op')=='disconnect',allow_error=True)
                async with asyncio.timeout(3):
                    while json.loads(checkpoint.read_text()).get('phase')!='detach-unknown':
                        await asyncio.sleep(.01)
                self.assertEqual(len(cleanup_calls),1,'no automatic retry after lost cleanup result')
                self.assertTrue((owner/'owner.guard').exists())
                self.assertEqual(len(calls),2,'no model replay after cleanup ambiguity')
            else:
                await until(lambda p:p.get('type')=='disconnected')
                async with asyncio.timeout(3):
                    while checkpoint.stat().st_mtime_ns<=before:
                        await asyncio.sleep(.01)
                await asyncio.sleep(.02)  # observe completion; never retry registration/grant
            self.assertFalse(core.broker.check(config['task_id'],'read',app_id='hyprneuro-parent-read')['allowed'])
            self.assertEqual(store.auth_get(config['task_id'])['status'],'revoked')
            if reconnect:
                await send(dict(op='connect',root=str(owner)))
                await until(lambda p:p.get('type')=='connected')
                self.assertEqual(next(iter(core.registrations.values())).binding['owner_session'],session_id)
                await send(dict(op='chat',text='Separate synthetic fresh activation and exact read fixture.'))
                for kind in ['grant_create','read_decision']:
                    packet=await until(lambda p:p.get('event',{}).get('type')=='consent')
                    event=packet['event'];self.assertEqual(event['audit']['kind'],kind)
                    self.assertNotIn(event['id'],consent_ids);consent_ids.append(event['id'])
                    await send(dict(op='consent',answer_id=event['id'],allowed=True))
                await until(lambda p:p.get('type')=='result' and p.get('op')=='chat')
                self.assertEqual(len(calls),4)
                self.assertIn('PRIVATE_CHANNEL_CANARY',json.dumps(calls[3]['messages'][-1]))
                await send(dict(op='disconnect'));await until(lambda p:p.get('type')=='disconnected')
                self.assertEqual(store.auth_get(config['task_id'])['status'],'revoked')
            (root/'packets.json').write_text(json.dumps(packets,indent=2))
            print('PRIVATE SDK/BROKER FIXTURE:',root,flush=True)
        finally:
            if bridge:
                bridge.stdin.close()
                try: await asyncio.wait_for(bridge.wait(),5)
                except TimeoutError:
                    bridge.terminate();await bridge.wait()  # only owned private fixture
            for server in servers:server.close();await server.wait_closed()
            if ctl:tasks=list(ctl.handlers)
            for task in tasks:task.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
            if node:
                if node.returncode is None:
                    node.terminate()
                await asyncio.wait_for(node.wait(),10)  # only this owned synthetic SDK fixture
            model.shutdown();model.server_close();thread.join(timeout=2)
            journal.close();store.close();log.close()
