import fcntl
import json
import os
from pathlib import Path
import tempfile
import unittest

from hyprneuro.pi_owner_service import SCHEMA, load_config, environment, service_lock, unit_template


class ServiceDescriptorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root/'home/workspace').mkdir(parents=True, mode=0o700)
        (self.root/'home').chmod(0o700)
        self.config = dict(schema=SCHEMA,root=str(self.root),source='/reviewed/source',node='/usr/bin/node',sdk='/installed/sdk.mjs',durable='/installed/durable',pi='/installed/pi',read_paths=['fixture.txt'],task_id='private-read')
        self.save()

    def tearDown(self):
        self.tmp.cleanup()

    def save(self):
        (self.root/'owner.json').write_text(json.dumps(self.config))
        (self.root/'owner.json').chmod(0o600)

    def test_private_explicit_descriptor_env_has_no_ambient_grants(self):
        config=load_config(self.root)
        env=environment(config,self.root)
        self.assertEqual(env['HYPRNEURO_PI_PARENT_ONLY'],'1')
        self.assertEqual(env['HYPRNEURO_PI_PERSISTENT'],'1')
        self.assertEqual(env['HYPRNEURO_PI_CHILD_READ'],'0')
        self.assertNotIn('HYPRNEURO_RESIDENCY_DIR',env)
        self.assertNotIn('DSA_HOME',env)
        self.assertEqual(env['HOME'],str(self.root/'home'))
        self.assertNotIn('API_KEY',env)
        self.assertEqual(env['HYPRNEURO_PI_READ_PATHS'],'["fixture.txt"]')

    def test_scope_cannot_come_from_settings_or_expand_to_parent_absolute_directory(self):
        for paths in [[],['..'],['../private'],['/etc/passwd'],['.'],['a/../b'],['a/'],['a','a'],[{}],['\x00']]:
            self.config['read_paths']=paths;self.save()
            with self.assertRaises(ValueError):load_config(self.root)
        self.config['read_paths']=['fixture.txt'];self.config['approved']=True;self.save()
        with self.assertRaises(ValueError):load_config(self.root)

    def test_links_permissions_and_wrong_root_refused(self):
        (self.root/'owner.json').chmod(0o644)
        with self.assertRaises(ValueError):load_config(self.root)
        self.save();os.link(self.root/'owner.json',self.root/'alias')
        with self.assertRaises(ValueError):load_config(self.root)
        (self.root/'alias').unlink();(self.root/'owner.json').rename(self.root/'real')
        (self.root/'owner.json').symlink_to(self.root/'real')
        with self.assertRaises(OSError):load_config(self.root)

    def test_single_service_lock_across_owner_roots_and_kernel_release(self):
        one=service_lock(self.root)
        try:
            with self.assertRaises(BlockingIOError):service_lock(self.root)
            self.assertTrue(os.get_inheritable(one))
        finally:os.close(one)
        two=service_lock(self.root);os.close(two)
        self.assertEqual((self.root/'hyprneuro/pi-owner-service.lock').stat().st_mode&0o077,0)

    def test_unit_is_explicit_no_autostart_or_restart_and_pins_source(self):
        text=unit_template('/private/python','/reviewed/source')
        for token in ['Type=exec','Restart=no','UMask=0077','TimeoutStopSec=30','KillMode=control-group','ExecStart=:"/private/python"','PYTHONPATH=/reviewed/source/python/src',' %f']:
            self.assertIn(token,text)
        self.assertNotIn('[Install]',text);self.assertNotIn('WantedBy',text)
        with self.assertRaises(ValueError):unit_template('/bad\npath','/source')
        self.assertIn('%%',unit_template('/python%value','/source'))


@unittest.skipUnless(os.environ.get('PI_HARNESS_SDK') and os.environ.get('PI_HARNESS_DURABLE'),
                     'Explicit reviewed installed SDK/Durable paths required')
class ActualSDKServiceShutdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_real_broker_detach_then_clean_process_shutdown_releases_inherited_lock(self):
        """Private fixture only: actual SDK/broker/SQLite/flock, no production unit."""
        import asyncio
        import shutil
        import signal
        import sys
        from hyprneuro.sidecar import SidecarServer
        from hyprneuro.sidecar_store import SidecarStore
        from hyprneuro.pi_owner_client import PiOwnerClient

        root = Path(tempfile.mkdtemp(prefix='hn-sdk-service-'))
        runtime = root/'runtime'; runtime.mkdir(mode=0o700)
        (runtime/'hyprharness').mkdir(mode=0o700)
        owner = root/'owner'; owner.mkdir(mode=0o700)
        (owner/'home').mkdir(mode=0o700)
        workspace = owner/'home/workspace'; workspace.mkdir(mode=0o700)
        source = Path(__file__).resolve().parents[2]
        store = SidecarStore(root/'broker.sqlite3')
        worker = SidecarServer(store, assistant_enabled=True)
        actions = []
        dispatch = worker.dispatch
        def recorded(request):
            actions.append(request['action'])
            return dispatch(request)
        worker.dispatch = recorded
        server = await asyncio.start_unix_server(worker.handle, path=str(runtime/'hyprharness/sidecar.sock'))
        inference = []
        async def reject_inference(reader, writer):
            inference.append(True)
            writer.close(); await writer.wait_closed()
        model = await asyncio.start_server(reject_inference, '127.0.0.1', 0)
        options = dict(root=str(owner), workspace=str(workspace),
                       sdkPath=os.environ['PI_HARNESS_SDK'], durableDir=os.environ['PI_HARNESS_DURABLE'],
                       piBin='/home/ron/.pi/agent/bin/pi', taskId='idle-service-fixture', appId='hyprneuro-parent-read',
                       profile='read-only', normalOnly=True, parentOnly=True, persistent=True,
                       childRead=False, readPaths=['fixture.txt'],
                       textBaseUrl=f'http://127.0.0.1:{model.sockets[0].getsockname()[1]}/v1')
        # The API driver pins a mock endpoint; it exercises the same close path
        # as host.mjs's SIGTERM handler without ever configuring a production URL.
        driver = """
const {createHost}=await import(process.argv[1]);
const host=await createHost(JSON.parse(process.argv[2]));
let closing=false;
process.on('SIGTERM',()=>{if(!closing){closing=true;host.close().then(()=>process.exit(0),()=>process.exit(1));}});
"""
        launcher = """
import os,sys
from pathlib import Path
from hyprneuro.pi_owner_service import service_lock
fd=service_lock(Path(sys.argv[1]))
os.execv('/usr/bin/node',['/usr/bin/node','--input-type=module','-e',sys.argv[2],sys.argv[3],sys.argv[4]])
"""
        config = dict(root=str(owner), source=str(source), sdk=options['sdkPath'], durable=options['durableDir'],
                      pi=options['piBin'], task_id=options['taskId'], read_paths=['fixture.txt'])
        env = environment(config, runtime)
        env['PYTHONPATH'] = str(source/'python/src')
        proc = None; control = None; sent = False; passed = False
        async def until(predicate):
            async with asyncio.timeout(10):
                while not predicate():
                    if proc.returncode is not None:
                        raise AssertionError('SDK fixture exited before readiness')
                    await asyncio.sleep(.02)
        try:
            proc = await asyncio.create_subprocess_exec(sys.executable, '-c', launcher,
                str(runtime), driver, (source/'extensions/pi-owner/host.mjs').as_uri(), json.dumps(options),
                env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await until(lambda: (owner/'owner.sock').exists() and (owner/'checkpoint.json').exists())
            lock = runtime/'hyprneuro/pi-owner-service.lock'
            inode = lock.stat().st_ino
            with self.assertRaises(BlockingIOError): service_lock(runtime)
            control = await PiOwnerClient.connect(owner, trusted=True)
            status = await control.call('status')
            self.assertEqual(status['tool_permission'], 'activation_required')
            self.assertTrue(status['persistent'])
            checkpoint_time = (owner/'checkpoint.json').stat().st_mtime_ns
            await control.close(); control = None
            def detached():
                try:
                    return ((owner/'checkpoint.json').stat().st_mtime_ns != checkpoint_time
                            and json.loads((owner/'checkpoint.json').read_text())['phase'] == 'ordinary')
                except (FileNotFoundError, json.JSONDecodeError):
                    return False
            await until(detached)
            self.assertEqual(json.loads((owner/'checkpoint.json').read_text())['phase'], 'ordinary')
            with self.assertRaises(BlockingIOError): service_lock(runtime)
            self.assertEqual(worker.broker.list(), [])
            proc.send_signal(signal.SIGTERM); sent = True
            out, err = await asyncio.wait_for(proc.communicate(), 12)
            self.assertEqual(proc.returncode, 0, (out+err).decode(errors='replace'))
            self.assertEqual(json.loads((owner/'checkpoint.json').read_text())['phase'], 'closed')
            self.assertFalse((owner/'owner.guard').exists())
            self.assertEqual(actions.count('auth_revoke'), 0, 'Idle owner has no owned grant; never fixed-task revoke')
            self.assertEqual(worker.broker.list(), [])
            self.assertEqual(inference, [])
            self.assertEqual(list((owner/'sessions').glob('**/*.jsonl')), [])
            fd = service_lock(runtime)
            try: self.assertEqual(lock.stat().st_ino, inode)
            finally: os.close(fd)
            passed = True
        finally:
            if control: await control.close()
            if proc and proc.returncode is None:
                if not sent: proc.send_signal(signal.SIGTERM)
                await asyncio.wait_for(proc.communicate(), 12)
            if proc:
                out, err = await proc.communicate()
                (root/'process.log').write_bytes(out+err)
            server.close(); await server.wait_closed()
            model.close(); await model.wait_closed()
            store.close()
            if passed: shutil.rmtree(root)
            else: print('Actual SDK service failure fixture retained:', root)
