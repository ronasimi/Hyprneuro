"""Private actual GTK/fixed child + broker. No production units/DB/authority.

Probe wraps ONLY GTK's sidecar D-Bus metadata. Broker uses production
unit_metadata with a synthetic EXACT systemctl stdout cohort, not a shortcut
units(pid,cgroup) callback; commands, PID/start/UID/cgroup/hash are checked.
"""
import asyncio,hashlib,json,os,socket,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from hyprneuro import trusted_control as c

class RejectionRecords(unittest.IsolatedAsyncioTestCase):
 async def test_unit_predicates_and_safe_envelope(self):
  for field,value,stage in [('ActiveState','activating','unit-state'),('Job','1','unit-job'),('MainPID','0','unit-pid'),('MainPID','SECRET','unit-metadata')]:
   raw={'ActiveState':'active','Job':'','MainPID':str(os.getpid()),'ControlGroup':'/private'};raw[field]=value
   with patch.object(c,'metadata',return_value='\n'.join(k+'='+v for k,v in raw.items())):
    with self.assertRaises(c.LaunchRejected) as error:await c.unit_metadata('hyprneuro-ui.service')
   self.assertEqual(c.rejection_record('ui-identity',error.exception)['stage'],stage)
  self.assertEqual(c.rejection_record('SECRET',RuntimeError('/private/secret')),{'diagnostic':'NONAUTHORITATIVE','stage':'unknown','category':'failure'})

@unittest.skipUnless(os.environ.get('HN_CHALLENGE_PROBE'),'Run via private Xvfb/dbus with compiled GTK probe')
class ActualChallenge(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  # Dedicated accessibility daemon, not dbus-broker's systemd activation and
  # NEVER the production desktop registry. Both owned children are reaped.
  self.bus=await asyncio.create_subprocess_exec('dbus-daemon','--nofork','--config-file=/usr/share/defaults/at-spi2/accessibility.conf','--print-address=1',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
  self.address=(await asyncio.wait_for(self.bus.stdout.readline(),3)).decode().strip()
  self.old_address=os.environ.get('AT_SPI_BUS_ADDRESS');os.environ['AT_SPI_BUS_ADDRESS']=self.address
  self.registry=await asyncio.create_subprocess_exec('/usr/lib/at-spi2-registryd',env=dict(os.environ),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
 async def asyncTearDown(self):
  for process in [self.registry,self.bus]:
   if process.returncode is None:process.terminate()
   await asyncio.wait_for(process.wait(),3)
  if self.old_address is None:os.environ.pop('AT_SPI_BUS_ADDRESS',None)
  else:os.environ['AT_SPI_BUS_ADDRESS']=self.old_address
 async def test_exact_metadata_rejections_transport_and_fixed_success(self):
  probe=Path(os.environ['HN_CHALLENGE_PROBE']).resolve()
  cases=['success','peer','peer-uid','unit-state','unit-job','unit-pid','unit-metadata','unit-command','unit-timeout','ui-peer-pid','ui-uid','ui-cgroup','ui-exe-hash','ui-process','eof','partial','json','schema','oversize','timeout','unknown','injection','legacy','spoof-success']
  for case in cases:
   with self.subTest(case=case),tempfile.TemporaryDirectory(prefix='hn-private-challenge-') as tmp:
    root=Path(tmp);entry=root/'fixed.py';marker=root/'child-ran'
    entry.write_text("import json,socket,sys\nfrom pathlib import Path\nassert sys.argv[1:]==['--explicit-connect','--broker-fd=3']\ns=socket.socket(fileno=3);f=s.makefile('rwb',buffering=0)\nassert json.loads(f.readline())=={'type':'launch_ready'}\nPath("+repr(str(marker))+").write_text('private child; no owner or grant')\n")
    policy=c.LaunchPolicy(Path(os.environ.get('HN_FIXED_PYTHON',sys.executable)),entry,root,hashlib.sha256(probe.read_bytes()).hexdigest(),hashlib.sha256(entry.read_bytes()).hexdigest())
    if case=='ui-exe-hash':policy=c.LaunchPolicy(policy.python,entry,root,'0'*64,policy.entry_sha256)
    policy_file=root/'policy.json';policy_file.write_text(json.dumps(dict(schema='hyprneuro.trusted-launch/1',python=str(policy.python),entry=str(entry),source=str(root),ui_sha256=policy.ui_sha256,entry_sha256=policy.entry_sha256)));policy_file.chmod(0o600)
    class NoAuthority:
     def register(self,*args):raise AssertionError('No authority in diagnostic fixture')
    control=c.GrantControlServer(NoAuthority(),c.LaunchVerifier(policy));pid=None;actual_identity=c.process_identity;commands=[];frames=[]
    async def metadata(*args):
     commands.append(args);self.assertEqual(args,('/usr/bin/systemctl','--user','show','hyprneuro-ui.service','-p','MainPID','-p','ControlGroup','-p','ActiveState','-p','Job'))
     if case=='unit-command':raise c.LaunchRejected('unit-command')
     if case=='unit-timeout':raise TimeoutError('SECRET')
     ident=actual_identity(pid);raw=dict(MainPID=str(pid),ControlGroup=ident['cgroup'].split('::',1)[1],ActiveState='active',Job='')
     if case=='unit-state':raw['ActiveState']='activating'
     if case=='unit-job':raw['Job']='77'
     if case=='unit-pid':raw['MainPID']='0'
     if case=='unit-metadata':raw['MainPID']='SECRET'
     if case=='ui-cgroup':raw['ControlGroup']='/wrong-private-cohort'
     if case=='ui-peer-pid':raw['MainPID']=str(os.getpid())
     return '\n'.join(k+'='+v for k,v in raw.items())
    def identity(target):
     if case=='ui-process' and target==pid:raise PermissionError('SECRET')
     result=actual_identity(target)
     if case=='ui-uid' and target==pid:result['uid']+=1
     return result
    async def send(writer,frame):frames.append(frame);await original_send(writer,frame)
    original_send=c.send_frame
    async def handle(reader,writer):
     if case in ['eof','partial','json','schema','oversize','timeout','unknown','injection','legacy','spoof-success']:
      try:
       payload={'eof':b'','partial':b'{','json':b'not-json\n','schema':b'[]\n','oversize':b'x'*4097,'unknown':b'{"error":{"diagnostic":"NONAUTHORITATIVE","stage":"SECRET","category":"SECRET"}}\n','legacy':b'{"error":"SECRET"}\n','spoof-success':json.dumps({'type':'launch_challenge','nonce':'a'*64,'error':{'diagnostic':'NONAUTHORITATIVE','stage':'ui-uid','category':'identity'}}).encode()+b'\n','injection':b'{"error":{"diagnostic":"NONAUTHORITATIVE","stage":"ui-uid","category":"identity","nonce":"SECRET"}}\n'}.get(case,b'')
       if payload:writer.write(payload);await writer.drain()
       if case=='timeout':await asyncio.sleep(3.3)
      finally:writer.close();await writer.wait_closed()
     else:await control.handle(reader,writer)
    server=await asyncio.start_unix_server(handle,path=str(root/'broker.sock'),limit=4097)
    env={k:v for k,v in os.environ.items() if k in ['PATH','DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','ASAN_OPTIONS','UBSAN_OPTIONS']};env.update(HOME=tmp,XDG_RUNTIME_DIR=tmp,GDK_BACKEND='x11',GTK_A11Y='atspi',GIO_USE_VFS='local',GSETTINGS_BACKEND='memory',HN_FIXTURE_CAPTURE_ACK=str(root/'capture.ack'),HN_FIXTURE_BROKER_PID=str(os.getpid()),HYPRNEURO_PI_TRUSTED_POLICY=str(policy_file),HYPRNEURO_PI_TRUSTED_POLICY_SHA256=hashlib.sha256(policy_file.read_bytes()).hexdigest(),HYPRNEURO_PI_BROKER_SOCKET=str(root/'broker.sock'))
    original_unpack=c.struct.unpack
    def credentials(fmt,raw):
     result=original_unpack(fmt,raw)
     if fmt!='3i' or len(raw)!=12:return result
     if case=='peer':raise OSError('SECRET')
     peer,uid,gid=result
     return peer,uid+1 if case=='peer-uid' else uid,gid
    with patch.object(c,'metadata',side_effect=metadata),patch.object(c,'process_identity',side_effect=identity),patch.object(c,'send_frame',side_effect=send),patch.object(c.struct,'unpack',side_effect=credentials):
     process=await asyncio.create_subprocess_exec(str(probe),env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE);pid=process.pid
     try:
      first=await asyncio.wait_for(process.stdout.readline(),7)
      if case!='success':
       from test_driver_input_fences import m
       sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ui/tests'))
       from desktop_driver import Desktop,Atspi
       ui=m.UI.__new__(m.UI);ui.current={'pid':pid};ui.Atspi=Atspi;ui.nodes=lambda:Desktop.nodes(pid)
       cohort=actual_identity(pid)
       def safe():self.assertEqual(actual_identity(pid),cohort)
       ui.safe=safe;ui.runtime=root;ui.bundle=root;ui.events=[]
       snapshot=None
       for attempt in range(30):
        snapshot=ui.bootstrap_diagnostic()
        if snapshot['stage']!='unknown':break
        await asyncio.sleep(.04)
       expected=json.loads(first);self.assertEqual((snapshot['stage'],snapshot['category']),(expected['stage'],expected['category']))
       ui.record('FAILED',bootstrap=snapshot,error='RuntimeError')
       self.assertEqual(json.loads((root/'ordinary-acceptance.json').read_text())['events'][0]['bootstrap'],snapshot)
       (root/'capture.ack').touch()
      rest,err=await asyncio.wait_for(process.communicate(),7);out=first+rest
     except BaseException:
      if process.returncode is None:process.kill();await process.wait()
      raise
     finally:
      server.close();await server.wait_closed()
      for task in list(control.handlers):task.cancel()
      await asyncio.gather(*list(control.handlers),return_exceptions=True)
    self.assertEqual(process.returncode,0,err.decode());result=json.loads(out)
    self.assertNotIn('SECRET',out.decode()+err.decode())
    if case=='success':
     self.assertEqual(result,{'result':'spawned'});self.assertTrue(marker.exists());self.assertTrue(commands)
     self.assertEqual(set(frames[0]),{'type','nonce'});self.assertEqual(frames[0]['type'],'launch_challenge');self.assertEqual(len(frames[0]['nonce']),64)
     self.assertEqual(frames[1],{'type':'launch_ready'})
    else:
     self.assertEqual(result['result'],'failed');self.assertFalse(marker.exists())
     stage='challenge' if case in ['eof','partial','json','schema','oversize','timeout','injection','legacy','spoof-success'] else 'broker-unknown' if case=='unknown' else 'broker-ui-identity' if case=='unit-timeout' else 'broker-peer-check' if case=='peer' else 'broker-'+case
     category={'peer':'failure','eof':'eof','partial':'framing','json':'json','schema':'schema','oversize':'framing','timeout':'timeout','unit-timeout':'timeout','unknown':'unknown','injection':'schema','legacy':'schema','spoof-success':'schema'}.get(case,'identity')
     self.assertEqual((result['stage'],result['category']),(stage,category))
     records=[json.loads(line) for line in err.decode().splitlines() if 'NONAUTHORITATIVE' in line];self.assertEqual(len(records),1);self.assertEqual(records[0]['stage'],stage);self.assertEqual(records[0]['category'],category)
     if frames:self.assertEqual(set(frames[0]),{'error'});self.assertEqual(set(frames[0]['error']),{'diagnostic','stage','category'})
