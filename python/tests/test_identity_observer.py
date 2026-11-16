"""Real process/FD/Node observations with SYNTHETIC exact manager metadata.

Not actual GTK, SDK CONTROL, systemd eligibility or human approval acceptance.
All selectors derive from a newly frozen private fixture manifest, not RPC PIDs.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro import identity_observer as observer
from hyprneuro import identity_bootstrap, identity_session, identity_transport, pi_owner_service, trusted_control, trusted_consent
from hyprneuro.identity_bootstrap import CONTEXT_SCHEMA, DIGEST_VARIABLE, MANIFEST_SCHEMA, load_reviewed_bootstrap
from hyprneuro.pi_owner_service import SCHEMA


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ObserverTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hn-observer-')
        self.root = Path(self.tmp.name)
        self.root.chmod(0o700)
        self.source = self.root/'source'
        (self.source/'extensions/pi-owner').mkdir(parents=True)
        self.host = self.source/'extensions/pi-owner/host.mjs'
        self.host.write_text('setTimeout(()=>process.exit(0),20000);\n')
        self.entry = self.root/'entry.py'
        self.entry.write_text('import sys,time\nassert sys.argv[1:]==["--explicit-connect","--broker-fd=3"]\ntime.sleep(20)\n')
        self.ui_entry = self.root/'ui.py'
        self.extra = self.root/'extra'
        self.child_ready = self.root/'child-ready'
        self.ui_entry.write_text('''import subprocess,sys,time,signal
from pathlib import Path
children=[]
def stop(*a):
 for child in children:
  if child.poll() is None:child.terminate()
 for child in children:child.wait(timeout=2)
 sys.exit(0)
signal.signal(signal.SIGTERM,stop)
children.append(subprocess.Popen('''+repr([sys.executable,'-I',str(self.entry),'--explicit-connect','--broker-fd=3'])+'''))
Path('''+repr(str(self.child_ready))+''').write_text(str(children[0].pid))
end=time.monotonic()+20
while time.monotonic()<end:
 if Path('''+repr(str(self.extra))+''').exists() and len(children)==1:
  children.append(subprocess.Popen('''+repr([sys.executable,'-I',str(self.entry),'--explicit-connect','--broker-fd=3'])+'''))
  Path('''+repr(str(self.root/'extra-ready'))+''').write_text('ready')
 time.sleep(.01)
stop()
''')
        self.owner_root=self.root/'owner'
        (self.owner_root/'home/workspace').mkdir(parents=True,mode=0o700)
        (self.owner_root/'home').chmod(0o700)
        self.owner_root.chmod(0o700)
        self.config=dict(schema=SCHEMA,source=str(self.source),node='/usr/bin/node',sdk='/private/sdk',
                         durable='/private/durable',pi='/private/pi',root=str(self.owner_root),
                         read_paths=['fixture.txt'],task_id='private-observer-test')
        self.descriptor=self.owner_root/'owner.json'
        self.descriptor.write_text(json.dumps(self.config));self.descriptor.chmod(0o600)
        self.ui = subprocess.Popen([sys.executable,str(self.ui_entry)])
        self.node = subprocess.Popen(['/usr/bin/node',str(self.host)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        end=asyncio.get_running_loop().time()+3
        while not self.child_ready.exists() and asyncio.get_running_loop().time()<end:await asyncio.sleep(.01)
        self.assertTrue(self.child_ready.exists())
        instance=subprocess.check_output(['/usr/bin/systemd-escape','--path',str(self.owner_root)],text=True).strip()
        self.names={r:'hyprneuro-test-observer-'+self.root.name+'-'+r+'.service' for r in ['ui','broker','helper']}
        self.names['owner']='hyprneuro-test-observer-owner@'+instance+'.service'
        self.names['socket']='hyprneuro-test-observer-'+self.root.name+'.socket'
        self.env=self.root/'bootstrap.env';self.manifest=self.root/'manifest.json';self.context=self.root/'context.json'
        self.values={k:'' for k in observer.PROPERTY_KEYS}
        self.values.update(Type='exec',Restart='no',NoNewPrivileges='yes',PrivateTmp='no',PrivateUsers='no',RuntimeMaxUSec='2h')
        self.specs={};files={}
        for role,name in self.names.items():
            path=self.root/name;path.write_text('[Service]\nEnvironmentFile='+str(self.env)+'\n')
            argv=[sys.executable,str(self.ui_entry)] if role=='ui' else ['/usr/bin/node',str(self.host)]
            if role in ['helper','broker']:argv=[sys.executable,'-I',str(self.ui_entry)]
            if role=='socket':argv=[]
            self.specs[role]=dict(name=name,fragments=[str(path)],argv=argv,
                                  property_hashes={k:observer.digest(v.encode()) for k,v in self.values.items()} if role!='socket' else {})
            files[str(path)]=sha(path)
        for path in [Path(sys.executable).resolve(),Path('/usr/bin/node').resolve(),self.entry,self.ui_entry,self.host,self.descriptor,
                     *[Path(m.__file__).resolve() for m in [observer,identity_bootstrap,identity_session,identity_transport,pi_owner_service,trusted_control,trusted_consent]]]:files[str(path)]=sha(path)
        for name in ['identity_root.py','identity_credentials.py','identity_entry.py','identity_guard.py','identity_unit_path.py','sidecar.py']:
            path=Path(observer.__file__).with_name(name);files[str(path)]=sha(path)
        self.document=dict(schema=MANIFEST_SCHEMA,files=files,
            launch=dict(python=sys.executable,entry=str(self.entry),source=str(self.source),
                        ui_sha256=files[str(Path(sys.executable).resolve())],entry_sha256=sha(self.entry)),
            node=observer.node_pin(Path('/usr/bin/node')),owner_root=str(self.owner_root),endpoint=str(self.root/'observer.sock'),units=self.specs,host_user_namespace=os.readlink('/proc/self/ns/user'))
        self.freeze()
        self.calls=[]

    def freeze(self):
        for p in [self.manifest,self.env,self.context]:
            if p.exists():p.chmod(0o600)
        self.manifest.write_text(json.dumps(self.document));self.manifest.chmod(0o400)
        self.env.write_text(DIGEST_VARIABLE+'='+sha(self.manifest)+'\n');self.env.chmod(0o400)
        pin=lambda p:dict(path=str(p),sha256=sha(p),uid=os.getuid(),mode=0o400)
        self.context.write_text(json.dumps(dict(schema=CONTEXT_SCHEMA,bootstrap=pin(self.env),manifest=pin(self.manifest))))
        self.context.chmod(0o400)
        self.bootstrap=load_reviewed_bootstrap(self.context,sha(self.context))

    async def asyncTearDown(self):
        for process in [self.ui,self.node]:
            if process.poll() is None:process.terminate()
            process.wait(timeout=3)
        self.tmp.cleanup()

    async def metadata(self,*args):
        self.calls.append(args)
        if args[:2]==('/usr/bin/systemd-escape','--path'):
            return subprocess.check_output(args,text=True,timeout=3).strip()
        self.assertEqual(args[:3],('/usr/bin/systemctl','--user','show'))
        name=args[3];role=next(r for r,n in self.names.items() if n==name)
        pid=self.ui.pid if role=='ui' else self.node.pid
        identity=trusted_control.process_identity(pid)
        spec=self.specs[role]
        value=dict(self.values,MainPID=str(pid),ControlGroup=identity['cgroup'].split('::',1)[1],ActiveState='active',SubState='running',
                   Job='',InvocationID='a'*32,FragmentPath=spec['fragments'][0],DropInPaths='',
                   ExecStart='{ path='+spec['argv'][0]+' ; argv[]='+' '.join(spec['argv'])+' ; ignore_errors=no ; start_time=[fixture] }')
        return '\n'.join(k+'='+v for k,v in value.items())

    async def test_closed_combined_snapshot_with_independent_child_and_actual_node(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        collector=observer.SnapshotCollector(policy)
        with patch.object(trusted_control,'metadata',side_effect=self.metadata):
            ui=await collector.observe('ui')
            self.assertEqual(set(ui),{'ui'})
            data=await collector.observe('decision')
        self.assertEqual(set(data),{'ui','child','owner'})
        self.assertEqual(data['child']['process']['parent'],self.ui.pid)
        self.assertEqual(data['owner']['process']['pid'],self.node.pid)
        self.assertEqual(data['owner']['binding']['task_id'],self.config['task_id'])
        self.assertEqual(data['owner']['binding']['ops'],['read'])
        self.assertFalse(any('control.key' in str(args) for args in self.calls))

    async def test_extra_actual_child_is_ambiguous_not_caller_selectable(self):
        collector=observer.SnapshotCollector(observer.ObserverPolicy(self.bootstrap))
        self.extra.write_text('extra')
        end=asyncio.get_running_loop().time()+2
        while not (self.root/'extra-ready').exists() and asyncio.get_running_loop().time()<end:await asyncio.sleep(.01)
        self.assertTrue((self.root/'extra-ready').exists())
        with patch.object(trusted_control,'metadata',side_effect=self.metadata):
            with self.assertRaisesRegex(PermissionError,'ambiguous'):await collector.observe('child')

    async def test_effective_config_and_unit_identity_drift_rejects(self):
        for field,value in [('PrivateTmp','yes'),('Job','123'),('MainPID','0'),('ExecStart','{ path=/foreign ; argv[]=/foreign ; ignore_errors=no ; }'),('InvocationID','bad'),('FragmentPath','/not-approved'),('DropInPaths','/extra')]:
            with self.subTest(field=field):
                async def drift(*args):
                    raw=await self.metadata(*args)
                    if args[0]=='/usr/bin/systemd-escape':return raw
                    values=observer._json_pairs(raw);values[field]=value
                    return '\n'.join(k+'='+v for k,v in values.items())
                with patch.object(trusted_control,'metadata',side_effect=drift):
                    with self.assertRaises(PermissionError):await observer.SnapshotCollector(observer.ObserverPolicy(self.bootstrap)).observe('ui')

    async def test_descriptor_task_read_policy_and_extra_manifest_profile_reject(self):
        for field,value in [('task_id','changed-task'),('read_paths',['../escape']),('schema','unsupported')]:
            with self.subTest(field=field):
                self.descriptor.write_text(json.dumps(dict(self.config,**{field:value})))
                with self.assertRaises((PermissionError,ValueError)):observer.ObserverPolicy(self.bootstrap)
                self.descriptor.write_text(json.dumps(self.config))
        self.document['profile']='unsupported-video'
        self.freeze()
        with self.assertRaisesRegex(PermissionError,'Exact closed'):observer.ObserverPolicy(self.bootstrap)

    async def test_real_owner_exit_after_last_unit_await_rejects_whole_cohort(self):
        collector=observer.SnapshotCollector(observer.ObserverPolicy(self.bootstrap));count=[0]
        async def drift(*args):
            result=await self.metadata(*args)
            if args[:3]==('/usr/bin/systemctl','--user','show'):
                count[0]+=1
                if count[0]==4:self.node.terminate();self.node.wait(timeout=2)
            return result
        with patch.object(trusted_control,'metadata',side_effect=drift):
            with self.assertRaises((PermissionError,OSError)):await collector.observe('decision')

    async def test_same_byte_catalog_replacement_and_wrong_host_namespace_reject(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        replacement=self.root/'replace.py';replacement.write_bytes(self.entry.read_bytes());os.replace(replacement,self.entry)
        with self.assertRaisesRegex(PermissionError,'replaced'):policy.check_files()
        self.document['host_user_namespace']='user:[0]';self.freeze()
        with self.assertRaises(PermissionError):
            policy=observer.ObserverPolicy(self.bootstrap)
            policy.check_namespace()

    async def test_host_node_unknown_nonroot_wrong_object_hash_and_alias_deny(self):
        # Synthetic stat mutations, NOT actual ownership changes/kernel PID reuse.
        pin=observer.node_pin(Path('/usr/bin/node'))
        actual=Path.lstat
        from types import SimpleNamespace
        for field,value in [('st_uid',65534),('st_gid',65534),('st_uid',os.getuid()),('st_ino',0),('st_mode',0o100777)]:
            with self.subTest(field=field):
                def changed(path,*args,**kwargs):
                    s=actual(path,*args,**kwargs)
                    if path==Path(pin['path']):
                        attrs={k:getattr(s,k) for k in ['st_dev','st_ino','st_uid','st_gid','st_mode','st_nlink']}
                        attrs[field]=value
                        return SimpleNamespace(**attrs)
                    return s
                with patch.object(Path,'lstat',changed):
                    with self.assertRaises(PermissionError):observer.check_node(pin,False)
        bad=dict(pin,sha256='0'*64)
        with self.assertRaises(PermissionError):observer.read_catalog_file(bad['path'],bad['sha256'],node=bad)
        alias=self.root/'node-alias';alias.symlink_to(pin['path'])
        with self.assertRaises(PermissionError):observer.check_node(dict(pin,path=str(alias)),False)

    async def test_node_host_positive_is_bound_to_same_combined_snapshot_not_cached(self):
        # Fixture validator inputs are SYNTHETIC channel/manager identities;
        # actual activation authentication is exercised in the private unit run.
        policy=observer.ObserverPolicy(self.bootstrap)
        collector=observer.SnapshotCollector(policy)
        with patch.object(trusted_control,'metadata',side_effect=self.metadata):roles=await collector.observe('ui')
        client=identity_transport.ObserverClient(policy);client.helper={'fixture':'helper'};client.broker={'fixture':'broker'}
        packet=dict(type='snapshot',operation='ui',generation='fixture',seq=1,nonce='fixture',issued_ns=0,expires_ns=1,
                    roles=roles,helper=client.helper,broker=client.broker,node=policy.node)
        expected={'ui':roles['ui']['unit']}
        client._validate_snapshot(packet,'ui',expected)
        for field,value in [('uid',False),('uid',65534),('gid',65534),('uid',os.getuid()),('inode',0),('sha256','0'*64),('path','/foreign/node')]:
            with self.subTest(field=field):
                bad=dict(packet,node=dict(policy.node,**{field:value}))
                with self.assertRaises(PermissionError):client._validate_snapshot(bad,'ui',expected)
        # No authority from construction/unknown ownership/standalone node data.
        self.assertIsNone(client.gate)
        new=self.root/'replacement';new.write_bytes(self.entry.read_bytes());os.replace(new,self.entry)
        with self.assertRaises(PermissionError):client._validate_snapshot(packet,'ui',expected)

    async def test_synchronous_parent_alias_mode_and_leaf_drift_reject(self):
        policy=observer.ObserverPolicy(self.bootstrap)
        directory=self.source/'extensions'
        directory.chmod(0o777)
        with self.assertRaises(PermissionError):policy.revalidate_configuration()
        directory.chmod(0o755)
        saved=self.source/'saved-extensions';directory.rename(saved);directory.symlink_to(saved,target_is_directory=True)
        with self.assertRaises(PermissionError):policy.revalidate_configuration()
        directory.unlink();saved.rename(directory)
        self.entry.chmod(0o600)
        with self.assertRaises(PermissionError):policy.revalidate_configuration()

    async def test_native_session_directory_after_freeze_is_parent_drift(self):
        for name in ['agent','durable']:(self.owner_root/name).mkdir(mode=0o700)
        self.assertEqual(self.owner_root.stat().st_nlink,5)
        policy=observer.ObserverPolicy(self.bootstrap)
        (self.owner_root/'sessions').mkdir(mode=0o700)
        self.assertEqual(self.owner_root.stat().st_nlink,6)
        with self.assertRaisesRegex(PermissionError,'Code/config parent changed'):
            policy.check_files()

    async def test_prepared_session_directory_keeps_frozen_parent_unchanged(self):
        for name in ['agent','durable','sessions']:(self.owner_root/name).mkdir(mode=0o700)
        policy=observer.ObserverPolicy(self.bootstrap)
        expected=dict(policy._parents)
        (self.owner_root/'sessions/fixture.jsonl').write_text('SYNTHETIC session data\n')
        (self.owner_root/'sessions/nested').mkdir(mode=0o700)
        policy.revalidate_configuration();policy.check_files()
        self.assertEqual(policy._parents,expected)
