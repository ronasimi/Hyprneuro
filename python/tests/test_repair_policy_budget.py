"""Watchdog-owned helpers and private guard fixture; never real host commands."""
import os,sys,time,tempfile,subprocess,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import prepare_app_release as prep
import repair_app_release as repair
import continue_app_acceptance as control
import apply_app_release as apply
import guard_app_release as guard
class BudgetTests(unittest.TestCase):
 def test_effective_restart_policy_not_text(self):
  m=dict(units=[],ui=dict(unit='synthetic',fragment='BASE',dropins=[]),sidecar=dict(unit='synthetic',fragment='BASE',dropins=[]))
  def show(*a,**kw):
   if 'FragmentPath' in a:return 'FragmentPath=BASE\nDropInPaths='
   if 'Restart' in a:return 'on-failure'
   return 'no'
  with patch.object(prep,'run',side_effect=show):
   with self.assertRaisesRegex(RuntimeError,'restart'):repair.verify_replacements(dict(replacement_files={}),m)
 def test_owned_helper_uses_remaining_deadline(self):
  with self.assertRaises(subprocess.TimeoutExpired):prep.run(sys.executable,'-B','-c','import time;time.sleep(5)',deadline=time.monotonic()+.03)
 def test_watchdog_partial_and_started_handler(self):
  for phase in ['partial','started']:
   result=subprocess.run([sys.executable,'-B','-m','unittest',__name__+'.BudgetTests.test_worker'],env=dict(os.environ,HN_BUDGET_WORKER=phase),capture_output=True,text=True,timeout=3)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
 def test_worker(self):
  phase=os.environ.get('HN_BUDGET_WORKER')
  if not phase:self.skipTest('subprocess worker only')
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);artifact=root/'artifact';artifact.write_text('OLD');ctx=dict(version=2,id='private',driver='/never');starts=[];checked=[];actual_run=subprocess.run
   def helper():
    import inspect
    kw=dict(deadline=time.monotonic()+.03) if 'deadline' in inspect.signature(prep.run).parameters else {}
    prep.run(sys.executable,'-B','-c','import time;time.sleep(5)',**kw)
   def cutover(*args,**kwargs):
    artifact.write_text('NEW')
    if phase=='partial':helper()
   def recheck(*args,**kwargs):
    checked.append(1)
    if phase=='started' and len(checked)==2:helper()
   def run(argv,*args,**kwargs):
    if argv[0]=='systemctl':starts.append(argv[-1]);return subprocess.CompletedProcess(argv,0)
    return actual_run(argv,*args,**kwargs)
   with patch.object(control,'preflight',return_value=(ctx,dict(runtime='/private'))),patch.object(control,'load_context',return_value=ctx),patch.object(repair,'cutover',side_effect=cutover),patch.object(repair,'verify_replacements',side_effect=recheck),patch.object(apply,'desktop_safe'),patch.object(control,'wait_sidecar_listener',return_value={}),patch.object(control,'recheck_sidecar_listener'),patch.object(subprocess,'run',side_effect=run),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}) as stop:
    self.assertEqual(control.execute(root,root,'private',True,True,'a'*64),1);stop.assert_called_once()
   self.assertEqual(artifact.read_text(),'NEW');self.assertEqual(starts,[] if phase=='partial' else ['hyprneuro.service'])
   self.assertEqual(json.loads((root/'continuation-state.json').read_text())['phase'],'failed-apps-stopped')
 def test_both_inherited_restart_policies_effectively_overridden(self):
  # Synthetic manager snapshot, not host systemd: an on-failure base for BOTH
  # apps, with reviewed drop-in loaded; stale manager metadata must still fail.
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);identities=[];effective={};queries=[]
   for unit in ['sidecar','ui']:
    base=root/(unit+'.service');base.write_text('[Service]\nRestart=on-failure\n')
    drop=root/(unit+'.conf');drop.write_text('[Service]\nRestart=no\n')
    values=[line.split('=',1)[1] for p in [base,drop] for line in p.read_text().splitlines() if line.startswith('Restart=')]
    effective[unit]=values[-1];identities.append(dict(unit=unit,fragment=str(base),dropins=[str(drop)]))
   m=dict(units=[],sidecar=identities[0],ui=identities[1]);ctx=dict(replacement_files={})
   def show(*args,**kw):
    unit=args[3];identity=next(i for i in identities if i['unit']==unit)
    if 'FragmentPath' in args:return 'FragmentPath='+identity['fragment']+'\nDropInPaths='+' '.join(identity['dropins'])
    if 'Restart' in args:queries.append(unit);return effective[unit]
    return 'no'
   with patch.object(prep,'run',side_effect=show):
    repair.verify_replacements(ctx,m);self.assertEqual(set(queries),{'sidecar','ui'})
    for unit in effective:
     effective[unit]='on-failure'
     with self.assertRaisesRegex(RuntimeError,'restart'):repair.verify_replacements(ctx,m)
     effective[unit]='no'
