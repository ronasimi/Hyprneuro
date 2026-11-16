"""Explicit leased actual manager/GTK/fixed-child/NodeSDK/core fixture.
SYNTHETIC consent packets, no genuine human chooser/Allow acceptance.
All units/data are unique owned private fixtures; fake local SSE only.
Run manually with HN_BOUNDARY_SDK_PROBE and reviewed PI_HARNESS paths.
"""
import os,json,sys,subprocess,hashlib,uuid,time,shutil,asyncio
from pathlib import Path
case=os.environ.get('HN_BOUNDARY_CASE','positive')
if case not in {'positive','wrong-root','delayed-cleanup','lost-receipt','cleanup-failure','proof-nonce','proof-generation','proof-duplicate','proof-reuse','proof-peer-binding','role-loss-ui','role-loss-child','role-loss-owner','persistence-intent','persistence-result','idle-helper-death','idle-clock','fresh-connect','endpoint-substitution'}:raise ValueError('Closed fixture case required')
token=uuid.uuid4().hex
E=Path('/home/ron/Workspace/hyprneuro-production-audit/boundary-source-implementation')/('sdk-'+token);E.mkdir(mode=0o700)
R=Path('/run/user')/str(os.getuid())/('hn-sdk-'+token[:12]);R.mkdir(mode=0o700)
SOURCE=Path(__file__).resolve().parents[1]/'src';sys.path.insert(0,str(SOURCE))
from hyprneuro import identity_observer as ob
from hyprneuro import identity_bootstrap,identity_session,identity_transport,identity_root,identity_credentials,identity_entry,identity_guard,sidecar,pi_owner_service,trusted_control,trusted_consent
PYTHON='/home/ron/Projects/Hyprneuro/python/.venv/bin/python'
prefix='hyprneuro-test-boundary-'+uuid.uuid4().hex[:12];runtime=Path('/run/user')/str(os.getuid());unitdir=runtime/'systemd/user';unitdir.mkdir(exist_ok=True)
names={r:prefix+'-'+r+('.socket' if r=='socket' else '.service') for r in ['ui','broker','helper','socket']}
owner=R/'owner';(owner/'home/workspace').mkdir(parents=True,mode=0o700);(owner/'home').chmod(0o700);owner.chmod(0o700)
instance=subprocess.check_output(['/usr/bin/systemd-escape','--path',str(owner)],text=True).strip();names['owner']=prefix+'-owner@'+instance+'.service'
endpoint=runtime/(prefix+'.sock');private=runtime/prefix;private.mkdir(mode=0o700);endpoint=private/'observe.sock'
code=SOURCE.parents[1];host=code/'extensions/pi-owner/host.mjs'
for directory in ['agent','durable','sessions']:(owner/directory).mkdir(mode=0o700)
(owner/'home/workspace/fixture.txt').write_text('PRIVATE_BOUNDARY_SDK_CANARY\n')
descriptor=owner/'owner.json';descriptor.write_text(json.dumps(dict(schema=pi_owner_service.SCHEMA,root=str(owner),source=str(code),node='/usr/bin/node',sdk=os.environ['PI_HARNESS_SDK'],durable=os.environ['PI_HARNESS_DURABLE'],pi='/home/ron/.pi/agent/bin/pi',read_paths=['fixture.txt'],task_id='source-observer-private')));descriptor.chmod(0o600)
entry=SOURCE/'hyprneuro/identity_bridge_entry.py'
bridge_instrumentation=Path(__file__).with_name('identity_bridge_fixture.py').resolve()
role_instrumentation=Path(__file__).with_name('identity_role_fixture.py').resolve()
persistence_instrumentation=Path(__file__).with_name('identity_persistence_fixture.py').resolve()
wrong_root=R/'other-owner'
if case=='wrong-root':
 for directory in ['home/workspace','agent','durable','sessions']:(wrong_root/directory).mkdir(mode=0o700,parents=True,exist_ok=True)
 (wrong_root/'home').chmod(0o700);wrong_root.chmod(0o700)
 other=dict(json.loads((owner/'owner.json').read_text()),root=str(wrong_root),source=str(R/'other-source'),node='/usr/bin/true')
 (wrong_root/'owner.json').write_text(json.dumps(other));(wrong_root/'owner.json').chmod(0o600)
 from hyprneuro.pi_owner_service import load_config
 load_config(wrong_root)
if case!='positive':
 entry=R/'fixture-bridge.py'
 entry.write_text('import sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,'+repr(str(SOURCE))+')\nsys.path.insert(0,'+repr(str(bridge_instrumentation.parent))+')\nfrom identity_bridge_fixture import install_bridge\ninstall_bridge('+repr(str(R))+','+repr(case)+')\nfrom hyprneuro.pi_desktop_bridge import main\nraise SystemExit(main())\n')
probe=Path(os.environ['HN_BOUNDARY_SDK_PROBE']).resolve()
generation=uuid.uuid4().hex;record=R/'launch-root.json';
env=R/'bootstrap.env';manifest=R/'manifest.json';context=R/'context.json';literal=R/'MAIN-literal-context-sha.txt';driver=R/'driver.py'
# Local SYNTHETIC SSE provider, never a production/model port.
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import threading
model_calls=[]
class Model(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  body=json.loads(self.rfile.read(int(self.headers['Content-Length'])));model_calls.append(body)
  if body['messages'][-1]['role']=='user':delta={'tool_calls':[{'index':0,'id':'boundary_read_'+str(len(model_calls)),'type':'function','function':{'name':'read','arguments':'{"path":"fixture.txt"}'}}]}
  else:delta={'content':'PRIVATE_BOUNDARY_READ_DONE'}
  data=('data: '+json.dumps({'choices':[{'index':0,'delta':delta,'finish_reason':'tool_calls' if 'tool_calls' in delta else 'stop'}]})+'\n\ndata: [DONE]\n\n').encode()
  self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
model=ThreadingHTTPServer(('127.0.0.1',0),Model);thread=threading.Thread(target=model.serve_forever,daemon=True);thread.start()
runtime=R/'runtime'
for socket_path in [R/'control.sock',owner/'owner.sock',runtime/'hyprharness/sidecar.sock',endpoint]:
 if len(os.fsencode(socket_path))>103:raise ValueError('Private fixture socket geometry exceeds conservative limit')
runtime.mkdir(mode=0o700);(runtime/'hyprharness').mkdir(mode=0o700)
owner_entry=R/'owner-entry.py'
owner_entry.write_text('import sys\nsys.dont_write_bytecode=True\nimport os\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(SOURCE))+')\nfrom hyprneuro.pi_owner_service import environment,load_config,service_lock\nruntime=Path('+repr(str(runtime))+')\nconfig=load_config(Path('+repr(str(owner))+'))\nfd=service_lock(runtime)\nenv=environment(config,runtime)\nenv["HYPRNEURO_PI_TEXT_BASE_URL"]='+repr(f'http://127.0.0.1:{model.server_port}/v1')+'\nos.execve(config["node"],[config["node"],'+repr(str(host))+'],env)\n')
# This is the real root factory, core, public permission view and control server.
driver.write_text('import sys\nsys.dont_write_bytecode=True\nimport asyncio,json,os\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(SOURCE))+')\nfrom hyprneuro.identity_root import load_manager_root\nfrom hyprneuro.trusted_control import GrantControlServer,LaunchVerifier\nfrom hyprneuro.trusted_consent import ConsentJournal,TrustedConsent\nfrom hyprneuro.sidecar_store import SidecarStore\nfrom hyprneuro.sidecar import SidecarServer\nroot=Path('+repr(str(R))+')\nsys.path.insert(0,'+repr(str(bridge_instrumentation.parent))+')\nfrom identity_bridge_fixture import install_broker\nattach_core=install_broker(root,'+repr(case)+','+repr(names['helper'])+')\npolicy=asyncio.run(load_manager_root(root/"launch-root.json",'+repr(generation)+',"broker"))\nasync def main():\n store=SidecarStore(root/"broker.sqlite");journal=ConsentJournal(root/"audit.jsonl");core=TrustedConsent(store,journal);attach_core(core)\n ctl=GrantControlServer(core,LaunchVerifier(policy.launch),identity_policy=policy)\n public=SidecarServer(store,assistant_enabled=True,trusted_consent=core);public.authority_refresh=ctl.refresh_authority\n a=await asyncio.start_unix_server(ctl.handle,path=str(root/"control.sock"),limit=4097)\n b=await asyncio.start_unix_server(public.handle,path='+repr(str(runtime/'hyprharness/sidecar.sock'))+')\n (root/"broker-ready").write_text("ready")\n try:\n  end=asyncio.get_running_loop().time()+35\n  while not (root/"gtk-sdk-complete").exists() and asyncio.get_running_loop().time()<end:await asyncio.sleep(.02)\n  (root/"core-result.json").write_text(json.dumps(dict(rows=store.auth_list(),live_registrations=sum(r.live for r in core.registrations.values()),published=sum(s.published for s in core.slots.values()),observer_cleanup_confirmed=ctl.identity_client is None,failures=ctl.failures),indent=2))\n finally:\n  a.close();b.close();await a.wait_closed();await b.wait_closed()\n  tasks=list(ctl.handlers)\n  for task in tasks:task.cancel()\n  await asyncio.gather(*tasks,return_exceptions=True);journal.close();store.close()\nasyncio.run(main())\n')
helper_entry=R/'helper-entry.py'
helper_instrumentation=Path(__file__).with_name('identity_helper_fixture.py').resolve()
helper_entry.write_text('import sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,'+repr(str(SOURCE))+')\nsys.path.insert(0,'+repr(str(helper_instrumentation.parent))+')\nfrom identity_helper_fixture import main\nraise SystemExit(main())\n')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest();created=[];commands=[];rogue=None
def run(a,check=True):
 commands.append(a);return subprocess.run(a,text=True,capture_output=True,timeout=5,check=check).stdout.strip()
try:
 launch=R/'gtk-launch.json';launch.write_text(json.dumps(dict(schema='hyprneuro.trusted-launch/1',python=PYTHON,entry=str(entry),source=str(code),ui_sha256=sha(probe),entry_sha256=sha(entry))));launch.chmod(0o400)
 bodies={}
 bodies['ui']='[Service]\nType=exec\nRestart=no\nRuntimeMaxSec=35\nEnvironment=DISPLAY='+os.environ['DISPLAY']+'\nEnvironment=XAUTHORITY=/dev/null GTK_A11Y=none GIO_USE_VFS=local GDK_BACKEND=x11 HN_FIXTURE_CAPTURE_ACK='+str(R/'ack')+'\nEnvironment=HN_FIXTURE_ROOT='+str(R)+' HN_FIXTURE_BROKER_UNIT='+names['broker']+(' HN_FIXTURE_BAD_ROOT='+str(wrong_root) if case=='wrong-root' else '')+(' HN_FIXTURE_ENDPOINT_NEGATIVE=1' if case=='endpoint-substitution' else '')+(' HN_FIXTURE_RECONNECT=1' if case=='fresh-connect' else '')+(' HN_FIXTURE_IDLE=1' if case.startswith('idle-') else '')+(' HN_FIXTURE_PROOF_DENIAL=1' if case.startswith(('proof-','persistence-','idle-')) else '')+(' HN_FIXTURE_UNKNOWN_CLEANUP=1' if case in {'lost-receipt','cleanup-failure'} else '')+' XDG_RUNTIME_DIR='+str(runtime)+' XDG_SESSION_ID='+os.environ.get('XDG_SESSION_ID','2')+' DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/'+str(os.getuid())+'/bus\nEnvironment=HYPRNEURO_PI_TRUSTED_POLICY='+str(R/'gtk-launch.json')+' HYPRNEURO_PI_TRUSTED_POLICY_SHA256='+sha(R/'gtk-launch.json')+' HYPRNEURO_PI_BROKER_SOCKET='+str(R/'control.sock')+'\nExecStart='+str(probe)+'\n'
 for role in ['broker','helper']:
  bodies[role]='[Service]\nType=exec\nRestart=no\nRuntimeMaxSec=35\nTimeoutStopSec=2\nNoNewPrivileges=yes\nPrivateUsers=no\nPrivateTmp='+('yes' if role=='broker' else 'no')+'\nEnvironment=PYTHONDONTWRITEBYTECODE=1\nEnvironmentFile='+str(env)+'\nLoadCredential=main-root-sha:'+str(R/'MAIN-root.sha256')+'\nExecStart='+PYTHON+' -I '+str(driver)+' '+role+'\n'
 bodies['owner']='[Service]\nType=exec\nRestart=no\nRuntimeMaxSec=35\nTimeoutStopSec=3\nExecStart='+PYTHON+' -I '+str(owner_entry)+'\n'
 bodies['socket']='[Socket]\nAccept=no\nListenStream='+str(endpoint)+'\nSocketMode=0600\nFileDescriptorName=identity-session\nBacklog=1\nService='+names['helper']+'\n'
 bodies['helper']=bodies['helper'].replace(PYTHON+' -I '+str(driver)+' helper',PYTHON+' -I '+str(helper_entry)+' helper --root-record '+str(record)+' --generation '+generation)
 for role,body in bodies.items():
  p=unitdir/names[role];p.write_text(body);created.append(p);(R/names[role]).write_text(body)
 specs={};catalog={}
 for role,name in names.items():
  p=unitdir/name;catalog[str(p)]=sha(p)
  if role=='socket':props={};argv=[]
  else:
   args=['/usr/bin/systemctl','--user','show',name,'--all']
   for key in sorted(ob.PROPERTY_KEYS):args+=['-p',key]
   props=ob._json_pairs(run(args));
   if role in ['ui','owner']:props.setdefault('EnvironmentFiles','')
   (R/(role+'.props.json')).write_text(json.dumps(props));assert set(props)==ob.PROPERTY_KEYS,(role,props)
   argv=[str(probe)] if role=='ui' else [PYTHON,'-I',str(owner_entry)] if role=='owner' else [PYTHON,'-I',str(driver),role]
   props={k:ob.digest(v.encode()) for k,v in props.items()}
  if role=='helper':argv=[PYTHON,'-I',str(helper_entry),'helper','--root-record',str(record),'--generation',generation]
  specs[role]=dict(name=name,fragments=[str(p)],argv=argv,property_hashes=props)
 for p in [Path(PYTHON).resolve(),Path('/usr/bin/node').resolve(),probe,entry,host,descriptor,driver,owner_entry,helper_entry,helper_instrumentation,bridge_instrumentation,role_instrumentation,persistence_instrumentation,launch,*[Path(m.__file__).resolve() for m in [ob,identity_bootstrap,identity_session,identity_transport,identity_root,identity_credentials,identity_entry,identity_guard,sidecar,pi_owner_service,trusted_control,trusted_consent]]]:catalog[str(p)]=sha(p)
 manifest.write_text(json.dumps(dict(schema=identity_bootstrap.MANIFEST_SCHEMA,files=catalog,
  launch=dict(python=PYTHON,entry=str(entry),source=str(code),ui_sha256=sha(probe),entry_sha256=sha(entry)),
  node=ob.node_pin(Path('/usr/bin/node')),owner_root=str(owner),endpoint=str(endpoint),units=specs,host_user_namespace=os.readlink('/proc/self/ns/user'))));manifest.chmod(0o400)
 env.write_text(identity_bootstrap.DIGEST_VARIABLE+'='+sha(manifest)+'\n');env.chmod(0o400)
 pin=lambda p:dict(path=str(p),sha256=sha(p),uid=os.getuid(),mode=0o400)
 context.write_text(json.dumps(dict(schema=identity_bootstrap.CONTEXT_SCHEMA,bootstrap=pin(env),manifest=pin(manifest))));context.chmod(0o400)
 record.write_text(json.dumps(dict(schema=identity_root.ROOT_SCHEMA,generation=generation,context_path=str(context),context_sha256=sha(context))));record.chmod(0o400)
 asyncio.run(identity_root.guard_root(record,sha(record),generation))
 run(['/usr/bin/systemctl','--user','start',names['broker']])
 end=time.monotonic()+5
 while not (R/'broker-ready').exists() and time.monotonic()<end:time.sleep(.02)
 assert (R/'broker-ready').exists(),'Broker startup failed'
 run(['/usr/bin/systemctl','--user','start',names['ui']])
 if case=='endpoint-substitution':
  end=time.monotonic()+5
  while not (R/'endpoint-substitution-entered').exists() and time.monotonic()<end:time.sleep(.002)
  assert (R/'endpoint-substitution-entered').exists(),'No real manager endpoint post-await barrier'
  import socket,stat
  before=endpoint.lstat();assert stat.S_ISSOCK(before.st_mode) and before.st_uid==os.getuid()
  assert endpoint.parent==private and private.name==prefix and private.stat().st_uid==os.getuid()
  endpoint.rename(private/'manager-original.sock')  # retain original inode; NEVER adopt/delete marker
  rogue=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);rogue.bind(str(endpoint));endpoint.chmod(0o600);rogue.listen(1);rogue.settimeout(2)
  (R/'endpoint-swap.json').write_text(json.dumps(dict(original_inode=before.st_ino,substituted_inode=endpoint.lstat().st_ino,rogue_pid=os.getpid(),scope='owned private AF_UNIX listener; no FD transfer/hello fabrication')))
  (R/'endpoint-substitution-release').write_text('actual same-path socket replacement after manager validation')
  accepted,_=rogue.accept();accepted.settimeout(2)
  try:assert accepted.recv(1)==b'','Observer leaked hello/data to non-manager endpoint'
  finally:accepted.close()
  (R/'rogue-received-zero-bytes').write_text('no hello/credential/proof disclosed')
 else:
  end=time.monotonic()+5
  while not (R/'ui-child-host-proof.ready').exists() and time.monotonic()<end:time.sleep(.02)
  assert (R/'ui-child-host-proof.ready').exists(),'No UI/child host-positive proof before Node'
  if case!='wrong-root':run(['/usr/bin/systemctl','--user','start',names['owner']])
 if case=='fresh-connect':
  end=time.monotonic()+12
  while not (R/'reconnect-ready').exists() and time.monotonic()<end:time.sleep(.005)
  assert (R/'reconnect-ready').exists(),'First cleanup and child exit not confirmed'
  assert int(run(['/usr/bin/systemctl','--user','show',names['helper'],'--value','-p','MainPID']))==0
  import sqlite3
  db=sqlite3.connect((R/'broker.sqlite').as_uri()+'?mode=ro',uri=True,timeout=.1)
  rows=db.execute('SELECT task_id,status,approved FROM authorizations').fetchall();db.close()
  assert rows==[('source-observer-private','revoked',0)],rows
  first=json.loads((R/'connect-cohorts.jsonl').read_text());owner_pid=int(run(['/usr/bin/systemctl','--user','show',names['owner'],'--value','-p','MainPID']))
  assert owner_pid>1
  (R/'reconnect-gap.json').write_text(json.dumps(dict(rows=rows,helper_pid=0,owner_pid=owner_pid,first=first)))
  (R/'reconnect-release').write_text('SYNTHETIC new explicit fixture Connect after clean receipt/child exit')
 if case.startswith('idle-'):
  end=time.monotonic()+10
  while not (R/'idle-ready').exists() and time.monotonic()<end:time.sleep(.005)
  assert (R/'idle-ready').exists(),'SDK chat must settle before idle fault'
  before=json.loads((R/'monitor-state.json').read_text())
  assert before['live'] is True and before['published'] is True,before
  (R/'idle-before.json').write_text(json.dumps(before))
  if case=='idle-clock':(R/'idle-clock-jump').write_text('EXPLICIT7201s BOOTTIME simulation, NOTreal2h/suspend')
  else:
   import signal,select
   helper_name=names['helper'];assert helper_name.startswith(prefix)
   pid=int(run(['/usr/bin/systemctl','--user','show',helper_name,'--value','-p','MainPID']))
   assert pid>1 and pid!=os.getpid()
   path=Path('/proc',str(pid));start=path.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]
   cgroup=run(['/usr/bin/systemctl','--user','show',helper_name,'--value','-p','ControlGroup'])
   assert path.joinpath('cgroup').read_text().strip()=='0::'+cgroup
   fd=os.pidfd_open(pid)
   try:
    assert path.joinpath('stat').read_text().rsplit(') ',1)[1].split()[19]==start
    (R/'fault-injected').write_text('exact owned helper pidfd death -> idle EOF')
    signal.pidfd_send_signal(fd,signal.SIGKILL)
    assert select.select([fd],[],[],2)[0],'Owned helper did not die'
   finally:os.close(fd)
   (R/'idle-victim-dead').write_text(json.dumps(dict(unit=helper_name,pid=pid,start=start,cgroup=cgroup)))
 if case.startswith('role-loss-'):
  end=time.monotonic()+8
  while not (R/'role-await.json').exists() and time.monotonic()<end:time.sleep(.002)
  assert (R/'role-await.json').exists(),'Missing actual post-await role barrier'
  victim=json.loads((R/'role-await.json').read_text());role=case.removeprefix('role-loss-')
  expected_unit=names['ui' if role=='child' else role]
  assert victim['role']==role and victim['unit']==expected_unit and expected_unit.startswith(prefix)
  pid=victim['pid'];assert type(pid) is int and pid>1 and pid!=os.getpid()
  def start_ticks():return Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[19]
  assert start_ticks()==victim['start']
  assert Path('/proc',str(pid),'cgroup').read_text().strip()==victim['cgroup']
  current=run(['/usr/bin/systemctl','--user','show',expected_unit,'--value','-p','MainPID'])
  if role!='child':assert int(current)==pid
  else:assert Path('/proc',str(pid),'stat').read_text().rsplit(') ',1)[1].split()[1]==current
  import signal,select
  fd=os.pidfd_open(pid)
  try:
   assert start_ticks()==victim['start']
   signal.pidfd_send_signal(fd,signal.SIGKILL)  # exact owned private identity, no stale PID
   assert select.select([fd],[],[],2)[0],'Owned victim did not die'
  finally:os.close(fd)
  (R/'role-released').write_text('owned pidfd death confirmed')
  end=time.monotonic()+4
  while not (R/'authority-denied.json').exists() and time.monotonic()<end:time.sleep(.002)
  denied=json.loads((R/'authority-denied.json').read_text())
  assert denied['eligible'] is False and denied['live'] is False and denied['published'] is False,denied
  (R/'gtk-sdk-complete').write_text('NEGATIVE actual role loss; source snapshot sealed before authority action')
 if case=='delayed-cleanup':
  for phase in ['native-invalidation','helper-reap']:
   end=time.monotonic()+8
   while not (R/(phase+'-entered')).exists() and time.monotonic()<end:time.sleep(.005)
   assert (R/(phase+'-entered')).exists(),phase
   tick=lambda:int((R/'monitor-ticks').read_text() or '0') if (R/'monitor-ticks').exists() else 0
   before=tick();end=time.monotonic()+2
   while tick()<before+2 and time.monotonic()<end:time.sleep(.005)
   assert tick()>=before+2,'Monitor did not survive two deterministic barrier turns'
   assert not (R/'gtk-sdk-complete').exists(),'Receipt before owned cleanup barrier release'
   sealed=json.loads((R/'monitor-state.json').read_text())
   assert sealed['eligible'] is False and sealed['live'] is False,sealed
   (R/(phase+'-release')).write_text('release')
 end=time.monotonic()+25
 while not (R/'core-result.json').exists() and time.monotonic()<end:time.sleep(.02)
 assert (R/'gtk-sdk-complete').exists(),'GTK/SDK fixture did not complete'
 assert (R/'core-result.json').exists(),'Missing core result'
 from identity_fixture_assertions import require_clean_result,require_revoked_rows
 result=json.loads((R/'core-result.json').read_text())
 if case=='endpoint-substitution':
  assert result['rows']==[] and result['live_registrations']==0 and result['published']==0 and result['failures']>0,result
  rejection=json.loads((R/'endpoint-source-rejection.json').read_text())
  assert rejection=={'error':{'diagnostic':'NONAUTHORITATIVE','stage':'ui-identity','category':'identity'}},rejection
  assert (R/'rogue-received-zero-bytes').exists() and not (R/'ui-child-host-proof.ready').exists()
  for role in ['helper','owner']:assert int(run(['/usr/bin/systemctl','--user','show',names[role],'--value','-p','MainPID']))==0
  assert model_calls==[],model_calls
 elif case=='fresh-connect':
  require_clean_result(result,R)
  cohorts=[json.loads(line) for line in (R/'connect-cohorts.jsonl').read_text().splitlines()]
  assert len(cohorts)==2 and cohorts[0]['generation']!=cohorts[1]['generation'],cohorts
  assert cohorts[0]['ui']==cohorts[1]['ui'] and cohorts[0]['broker']==cohorts[1]['broker'],cohorts
  assert cohorts[0]['child']['pid']!=cohorts[1]['child']['pid'] and cohorts[0]['helper']['pid']!=cohorts[1]['helper']['pid'],cohorts
  assert int(run(['/usr/bin/systemctl','--user','show',names['owner'],'--value','-p','MainPID']))==json.loads((R/'reconnect-gap.json').read_text())['owner_pid']
  packets=[json.loads(line) for line in (R/'gtk-packets.jsonl').read_text().splitlines()]
  consents=[p['event'] for p in packets if p.get('type')=='host_event' and p['event'].get('type')=='consent']
  assert len(consents)==4 and len({c['id'] for c in consents})==4,consents
  assert [c['audit']['kind'] for c in consents]==['grant_create','read_decision']*2,consents
  assert consents[0]['audit']['generation']!=consents[2]['audit']['generation']
  assert len(model_calls)==4 and all('PRIVATE_BOUNDARY_SDK_CANARY' in json.dumps(model_calls[i]) for i in [1,3]),model_calls
 elif case.startswith('idle-'):
  assert result['live_registrations']==0 and result['published']==0 and result['failures']>0,result
  assert result['observer_cleanup_confirmed'] is False,result
  require_revoked_rows(result['rows'],R)
  assert (R/'negative-child-exit').read_text()=='1\n'
  if case=='idle-helper-death':assert (R/'idle-victim-dead').exists()
  assert len(model_calls)==2 and 'PRIVATE_BOUNDARY_SDK_CANARY' in json.dumps(model_calls[1]),model_calls
 elif case.startswith('persistence-'):
  blocked=json.loads((R/'blocked-fsync-denied.json').read_text())
  assert blocked['clock_injection_seconds']==7201 and blocked['event_loop_blocked'] is True and blocked['real_suspend'] is False
  assert not any(blocked[k] for k in ['current','live','published','eligible']),blocked
  assert result['live_registrations']==0 and result['published']==0 and result['failures']>0,result
  if case=='persistence-intent':assert result['rows']==[],result
  else:require_revoked_rows(result['rows'],R)
  assert model_calls==[] and (R/'negative-child-exit').read_text()=='1\n'
 elif case.startswith('role-loss-'):
  assert result['rows']==[] and result['live_registrations']==0 and result['published']==0 and result['failures']>0,result
  assert model_calls==[],model_calls
 elif case.startswith('proof-'):
  assert (R/'fault-injected').read_text()==case
  assert (R/'negative-child-exit').read_text()=='1\n'
  if case=='proof-reuse':assert (R/'proof-first-accept').exists()
  assert result['rows']==[] and result['live_registrations']==0 and result['published']==0 and result['failures']>0,result
  assert model_calls==[],model_calls
 elif case=='wrong-root':
  assert result['rows']==[] and result['live_registrations']==0 and result['published']==0,result
  assert model_calls==[] and not (R/'FORBIDDEN-start').exists() and not (R/'FORBIDDEN-auth').exists()
 elif case in {'lost-receipt','cleanup-failure'}:
  require_revoked_rows(result['rows'],R)
  assert result['live_registrations']==0 and result['published']==0,result
  assert result['observer_cleanup_confirmed'] is False and result['failures']>0,result
  assert (R/'reconnect-denied').exists()
 else:
  require_clean_result(result,R)
  assert len(model_calls)==2 and 'PRIVATE_BOUNDARY_SDK_CANARY' in json.dumps(model_calls[1]),model_calls
 print('PRIVATE CASE PASS (SYNTHETIC CONSENT ONLY)',case,R)

finally:
 if rogue is not None:rogue.close()
 model.shutdown();thread.join(timeout=2);model.server_close();(R/'model-calls.json').write_text(json.dumps(model_calls,indent=2))
 states={}
 for role in ['socket','helper','broker','ui','owner']:
  run(['/usr/bin/systemctl','--user','stop',names[role]],False)
  states[role]=run(['/usr/bin/systemctl','--user','show',names[role],'-p','MainPID','-p','ActiveState','-p','Job','-p','ControlGroup'],False)
  journal=run(['/usr/bin/journalctl','--user','-u',names[role],'-n','35','--no-pager','-o','json'],False);(R/(role+'.journal.jsonl')).write_text(journal+'\n')
 (R/'states.json').write_text(json.dumps(states,indent=2));(R/'commands.json').write_text(json.dumps(commands,indent=2))
 for p in created:
  state=states[next(r for r,n in names.items() if n==p.name)]
  if 'MainPID=0' in state or p.suffix=='.socket':p.unlink()
 # Retain exact runtime-root paths in receipts; archive regular evidence only
 # after all owned units stop. Socket metadata is retained, not copied/rebound.
 nonregular={}
 def ignore_special(directory,names):
  skipped=[]
  for name in names:
   path=Path(directory)/name
   if path.is_socket() or path.is_fifo():
    info=path.lstat();nonregular[str(path)]=dict(mode=info.st_mode,uid=info.st_uid,inode=info.st_ino);skipped.append(name)
  return skipped
 shutil.copytree(R,E/'runtime-snapshot',ignore=ignore_special)
 (E/'runtime-path.txt').write_text(str(R)+'\n');(E/'nonregular.json').write_text(json.dumps(nonregular,indent=2))
 print('EVIDENCE',E,'RUNTIME',R)
