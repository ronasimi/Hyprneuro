"""Actual desktop regression, not a headless or socket-only test.
Run from any directory: python ui/tests/interactive.py
Live path: pi-durable-subagents hold machine -- python ui/tests/interactive.py --live
Requires the user's Wayland session, wtype/wdotool/grim, and the sanitizer build
at ~/Workspace/hyprneuro-features/sanitize. Outputs only under ~/Workspace.
Temporarily stops/restores the existing UI service; never changes model services.
Normal GTK warnings are logged, not suppressed and not production acceptance.
"""
import json,os,subprocess,sys,time,socket
from pathlib import Path
root=Path.home()/'Workspace/hyprneuro-features'
repo=Path(__file__).resolve().parents[2]
live='--live' in sys.argv
run=root/(('live-' if live else 'fixture-')+time.strftime('%Y%m%d-%H%M%S'))
run.mkdir(exist_ok=True)
(run/'backend-requests.jsonl').unlink(missing_ok=True)
(run/'settings/settings.json').unlink(missing_ok=True)
def layer():
 data=json.loads(subprocess.check_output(['hyprctl','-j','layers']))
 return next(l for m in data.values() for ls in m['levels'].values() for l in ls if l['pid']==pid)
def click(x,y):
 subprocess.run(['wdotool','--backend','wlr-protocols','mousemove',str(x),str(y)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 subprocess.run(['wdotool','--backend','wlr-protocols','click','1'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
def action(name):
 l=layer();x,y,w,h=(l[k] for k in ['x','y','w','h'])
 controls={'attach':(38,h-66),'input':(230,h-66),'send':(w-118,h-66),'audio':(w-78,h-66),'vision':(w-38,h-66),'size':(w-30,30),'settings':(21,h-22),'back':(55,30),'capture':(367,h-126),'stop':(435,h-126),'screen':(502,h-126),'cancel':(575,h-126)}
 if name in ('send','audio','vision') and h < 180:
  controls[name]=(controls[name][0]-40,controls[name][1])
 dx,dy=controls[name];click(x+dx,y+dy);time.sleep(.35)
def screenshot(name):
 l=layer();p=Path.home()/'Workspace/screenshots'/time.strftime('%Y-%m-%d')/f'{run.name}-{name}.png'
 p.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['grim','-g',f"{l['x']},{l['y']} {l['w']}x{l['h']}",str(p)],check=True);print(p)

was_active=subprocess.run(['systemctl','--user','is-active','--quiet','hyprneuro-ui.service']).returncode==0
subprocess.run(['systemctl','--user','stop','hyprneuro-ui.service'],check=True)
env=dict(os.environ,PYTHONPATH=str(repo/'python/src'),PYTHONDONTWRITEBYTECODE='1')
backend_log=(run/'sidecar.log').open('w')
backend=subprocess.Popen([str(repo/'python/.venv/bin/python'),str(repo/'.dev/logs/reasoning_fixture.py'),str(run),*(['--live'] if live else [])],env=env,stdout=backend_log,stderr=subprocess.STDOUT)
ui=None
try:
 for _ in range(100):
  if (run/'sidecar.sock').exists():break
  time.sleep(.05)
 env.update(HYPHARNESS_SIDECAR=str(run/'sidecar.sock'),ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
 env.pop('G_DEBUG',None)  # normal GTK warnings: approved bounded development only
 ui_log=(run/'gui.log').open('w')
 ui=subprocess.Popen([str(root/'sanitize/hyprneuro-ui')],env=env,stdout=ui_log,stderr=subprocess.STDOUT)
 pid=ui.pid
 time.sleep(1)
 messages=['Reply with exactly MAPLE.','What word did you just reply with?'] if live else ['native','delimiters','plain','disconnect','recovered']
 for n,msg in enumerate(messages):
  action('input');subprocess.run(['wtype',msg,'-k','Return'],check=True)
  time.sleep(10 if live else 3)
  assert ui.poll() is None,(ui.returncode,(run/'gui.log').read_text())
  screenshot(f'reasoning-{run.name}-{n}')
 if not live:
  # Preserve a multiline composer across repeated real surface destruction.
  action('input')
  subprocess.run(['wtype','retained','-M','ctrl','-k','Return','-m','ctrl','draft'],check=True)
  control=Path(os.environ['XDG_RUNTIME_DIR'])/'hyprneuro/ui.sock'
  for i in range(100):
   for command in ['hide','show']:
    with socket.socket(socket.AF_UNIX) as client:
     client.connect(str(control));client.sendall((command+'\n').encode())
    time.sleep(.013 if i%2 else .07)
   assert ui.poll() is None,(ui.returncode,(run/'gui.log').read_text())
  time.sleep(.3)
  screenshot('reasoning-hideshow-retained-draft')
  action('input');subprocess.run(['wtype','-k','Return'],check=True);time.sleep(3)
  req=[json.loads(l) for l in (run/'backend-requests.jsonl').read_text().splitlines()]
  assert len(req)==6,req
  assert req[-1]['messages'][-1]['content']=='retained\ndraft',req[-1]
  expected=['Ordinary answer stays blue and upright ✓.','Delimiter answer ✓.','Plain fixture answer ✓.']
  for i,answer in enumerate(expected):
   assert req[i+1]['messages'][-2]=={'role':'assistant','content':answer},req[i+1]
  assert req[-1]['messages'][-2]=={'role':'assistant','content':expected[-1]},req[-1]
  assert all(r['chat_template_kwargs']=={'enable_thinking':False} for r in req)
  print('PASS actual GTK -> sidecar -> fragmented chunked HTTP/SSE; native reasoning, split delimiters, plain, interrupted error, recovery, answer-only history')
 else:print('LIVE GTK path completed; inspect screenshot answers before acceptance')
 if not live:
  config=run/'settings/settings.json'
  def pref_click(x,y=64):
   l=layer();click(l['x']+x,l['y']+y);time.sleep(.2)
  def choose(key):
   pref_click(170);subprocess.run(['wtype','-k',key,'-k','Return'],check=True);time.sleep(.3)
  action('settings');screenshot('settings-transcript-editor')
  choose('End');screenshot('settings-size-draft-full')
  assert not config.exists() or json.loads(config.read_text())['ui_transcript_size']=='restored'
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['ui_transcript_size']=='full'
  screenshot('settings-size-saved-full')
  choose('Home');pref_click(376);time.sleep(.5)
  screenshot('settings-size-reload-discard')
  action('back');screenshot('settings-size-full-chat')
  # UI restart must load persisted appearance, without restarting any model.
  ui.terminate();ui.wait()
  ui=subprocess.Popen([str(root/'sanitize/hyprneuro-ui')],env=env,stdout=ui_log,stderr=subprocess.STDOUT)
  pid=ui.pid
  time.sleep(1)
  action('settings');screenshot('settings-size-restarted-full')
  # Save default Restored for the following draft/history regression.
  pref_click(170);subprocess.run(['wtype','-k','Home','-k','Down','-k','Return'],check=True);time.sleep(.3)
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['ui_transcript_size']=='restored'
  action('back')

  # Autoscroll: Save off, verify new text does not move the visible viewport.
  action('input');subprocess.run(['wtype','long first','-k','Return'],check=True);time.sleep(3)
  screenshot('autoscroll-on-bottom')
  action('settings')
  pref_click(243,100);screenshot('autoscroll-draft-off')
  assert json.loads(config.read_text())['ui_autoscroll'] is True
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['ui_autoscroll'] is False
  screenshot('autoscroll-saved-off')
  action('back');action('input');subprocess.run(['wtype','long second','-k','Return'],check=True);time.sleep(3)
  screenshot('autoscroll-off-retains-viewport')
  # Restart: disabled preference must still be active, not just a draft flag.
  ui.terminate();ui.wait()
  ui=subprocess.Popen([str(root/'sanitize/hyprneuro-ui')],env=env,stdout=ui_log,stderr=subprocess.STDOUT)
  pid=ui.pid;time.sleep(1)
  action('settings');screenshot('autoscroll-restarted-off')
  pref_click(243,100);pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['ui_autoscroll'] is True
  screenshot('autoscroll-saved-on')
  print('Autoscroll GUI sequence complete; viewport screenshots must be visually checked')

  # Journal is saved independently; Save alone must not claim active intake.
  pref_click(440,125);screenshot('journal-draft-on')
  assert json.loads(config.read_text())['alert_journal'] is False
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_journal'] is True
  screenshot('journal-saved-pending-restart')
  pref_click(440,125);pref_click(376);time.sleep(.5)
  screenshot('journal-reload-discards-draft')
  backend.terminate();backend.wait()
  backend=subprocess.Popen([str(repo/'python/.venv/bin/python'),str(repo/'.dev/logs/reasoning_fixture.py'),str(run),'--journal'],env=env,stdout=backend_log,stderr=subprocess.STDOUT)
  time.sleep(2)
  children=Path(f'/proc/{backend.pid}/task/{backend.pid}/children').read_text().split()
  journal_children=[p for p in children if Path(f'/proc/{p}/comm').read_text().strip()=='journalctl']
  assert journal_children,children
  pref_click(376);time.sleep(.5);screenshot('journal-active-disposable')
  # Stop/disable cleans the actual journalctl subprocess; no leaked intake.
  pref_click(440,125);pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_journal'] is False
  backend.terminate();backend.wait()
  assert all(not Path(f'/proc/{p}').exists() for p in journal_children),journal_children
  backend=subprocess.Popen([str(repo/'python/.venv/bin/python'),str(repo/'.dev/logs/reasoning_fixture.py'),str(run)],env=env,stdout=backend_log,stderr=subprocess.STDOUT)
  time.sleep(1);pref_click(376);time.sleep(.5);screenshot('journal-disabled-cleanup')
  print('PASS journal draft/save/pending/reload, actual journalctl worker start and cleanup; fixture D1 only, live ingestion separately required')

  # Passive network control: no interface changes or active network probes.
  pref_click(446,166);screenshot('network-draft-on')
  assert json.loads(config.read_text())['alert_network'] is False
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_network'] is True
  screenshot('network-saved-pending-restart')
  backend.terminate();backend.wait()
  backend=subprocess.Popen([str(repo/'python/.venv/bin/python'),str(repo/'.dev/logs/reasoning_fixture.py'),str(run),'--network'],env=env,stdout=backend_log,stderr=subprocess.STDOUT)
  time.sleep(1)
  def fixture_health():
   with socket.socket(socket.AF_UNIX) as client:
    client.connect(str(run/'sidecar.sock'));client.sendall(b'{"action":"health"}\n')
    return json.loads(client.makefile('rb').readline(262144))['result']
  first=fixture_health()['network_monitor']['samples']
  time.sleep(5.2)
  health=fixture_health()
  assert health['collectors']['network']=='running',health
  assert health['network_monitor']['samples']>first,health
  assert health['network_monitor']['observed_at_ms'] is not None
  assert len(health['network_monitor']['interfaces'])<=64
  (run/'network-observations.json').write_text(json.dumps(health['network_monitor'],indent=2))
  pref_click(376);time.sleep(.5);screenshot('network-active-passive-observations')
  pref_click(446,166);pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_network'] is False
  print('PASS actual GUI network save/pending/startup active; real bounded sysfs polling samples increased; live fault delivery NOT exercised')

  # Sustained-resource control samples existing passive Monitor readings only.
  pref_click(446,200);screenshot('resources-draft-on')
  assert json.loads(config.read_text())['alert_resources'] is False
  pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_resources'] is True
  screenshot('resources-saved-pending-restart')
  backend.terminate();backend.wait()
  backend=subprocess.Popen([str(repo/'python/.venv/bin/python'),str(repo/'.dev/logs/reasoning_fixture.py'),str(run),'--resources'],env=env,stdout=backend_log,stderr=subprocess.STDOUT)
  time.sleep(1)
  first=fixture_health()['resource_monitor']['samples']
  time.sleep(2.5)
  health=fixture_health();status=health['resource_monitor']
  assert health['collectors']['resources']=='running',health
  assert status['samples']>first,status
  assert 0<=status['cpu_pct']<=100 and 0<=status['ram_pct']<=100,status
  assert status['root_disk_pct'] is not None
  (run/'resource-observations.json').write_text(json.dumps(status,indent=2))
  pref_click(376);time.sleep(.5);screenshot('resources-active-passive-observations')
  pref_click(446,200);pref_click(288);time.sleep(.5)
  assert json.loads(config.read_text())['alert_resources'] is False
  print('PASS actual GUI resources save/pending/startup active; real proc/sys samples increased; live sustained high-load episode NOT exercised')

finally:
 if ui is not None:
  ui.terminate();ui.wait()
 backend.terminate();backend.wait()
 if was_active:subprocess.run(['systemctl','--user','start','hyprneuro-ui.service'],check=True)
