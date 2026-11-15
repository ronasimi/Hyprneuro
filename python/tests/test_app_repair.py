"""Private filesystem cutover + guard failure injection; zero production operations."""
import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import repair_app_release as repair
import continue_app_acceptance as control
import prepare_app_release as prep
import apply_app_release as apply
import guard_app_release as guard
class RepairTests(unittest.TestCase):
 def test_actual_atomic_replacements_and_each_boundary_failure_no_restore(self):
  for failure in ['none','source','alias',0,1,2,3,'reload','loaded','lock','context']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    root=Path(d);bundle=root/'bundle';bundle.mkdir();stage=bundle/'staged';stage.mkdir();home=root/'home';home.mkdir()
    units=home/'.config/systemd/user';units.mkdir(parents=True)
    targets=[];installed={};replacements={}
    for name in ['sidecar.conf','ui.conf','hyprneuro-pi-owner@.service','binary']:
     src=stage/name;src.write_text('NEW-'+name);dst=home/name;dst.write_text('OLD-'+name)
     targets.append((src,dst));installed[str(dst)]=repair.digest(dst);replacements[str(dst)]=dict(sha256=repair.digest(src),mode=0o600)
    m=dict(binary=str(targets[-1][0]),installed_ui=str(targets[-1][1]),ui=dict(unit='ui',fragment='BASE',dropins=[]),sidecar=dict(unit='sidecar',fragment='BASE',dropins=[]))
    context=dict(installed_files=installed,replacement_files=replacements);calls=[];copies=[];atomic=apply.atomic_copy
    def copy(src,dst,mode):
     if failure==len(copies):raise OSError('Private replacement failure')
     atomic(src,dst,mode);copies.append(dst)
    def manager(*args,**kwargs):
     calls.append(args)
     if 'daemon-reload' in args:
      if failure=='reload':raise RuntimeError('Reload failed')
      return ''
     if 'FragmentPath' in args:return 'FragmentPath='+('DRIFT' if failure=='loaded' else 'BASE')+'\nDropInPaths='
     return 'no'
    if failure=='source':targets[2][0].write_text('DRIFT')
    if failure=='alias':targets[1][1].unlink();targets[1][1].symlink_to(targets[0][1])
    with patch.object(repair,'stopped_baseline'),patch('verify_app_release.release_targets',return_value=targets[:-1]),patch.object(Path,'home',return_value=home),patch.object(apply,'atomic_copy',side_effect=copy),patch.object(prep,'run',side_effect=manager),patch.object(apply,'desktop_safe',side_effect=RuntimeError('Lock') if failure=='lock' else None):
     check=Mock(side_effect=RuntimeError('Context drift') if failure=='context' else None)
     if failure=='none':repair.cutover(bundle,context,m,'private',check)
     else:
      with self.assertRaises((RuntimeError,OSError)):repair.cutover(bundle,context,m,'private',check)
    if failure=='none':self.assertEqual(len(copies),4)
    if failure in ['source','alias','lock','context']:self.assertFalse(copies)
    # No rollback: already written prefix remains NEW; never start/stop/model ops.
    for dst in copies:self.assertTrue(dst.read_text().startswith('NEW-'))
    self.assertFalse(any('start' in c or 'stop' in c for c in calls))
 def test_repair_guard_failure_containment_and_once_only(self):
  for failure in ['replacement','sidecar','ui','verify','driver','lock','cancel','timeout','persist','uncontained']:
   with self.subTest(failure=failure),tempfile.TemporaryDirectory() as d:
    root=Path(d);context=dict(version=2,id='private',driver='/private/driver');calls=[]
    def run(argv,**kw):
     calls.append(argv)
     if (failure=='sidecar' and argv[-1]=='hyprneuro.service') or (failure=='ui' and argv[-1]=='hyprneuro-ui.service'):raise RuntimeError('Failed start')
    process=Mock();process.poll.return_value=None if failure=='timeout' else 1;process.returncode=1
    def observed(*args):
     if failure=='lock':raise RuntimeError('Locked')
     if failure=='cancel':raise KeyboardInterrupt()
    original=control.write_state
    def persist(*args):
     if failure=='persist':raise OSError('State failure')
     original(*args)
    with patch.object(control,'preflight',return_value=(context,dict(runtime='/private'))),patch.object(control,'load_context',return_value=context),patch.object(repair,'cutover',side_effect=RuntimeError('Cutover failed') if failure=='replacement' else None),patch.object(repair,'verify_replacements'),patch.object(control,'wait_sidecar_listener',return_value={}),patch.object(control,'recheck_sidecar_listener'),patch.object(control.subprocess,'run',side_effect=run),patch.object(control.subprocess,'Popen',return_value=process),patch.object(control,'verify_started',side_effect=RuntimeError('Verify') if failure=='verify' else None),patch.object(apply,'desktop_safe'),patch.object(guard,'observe',side_effect=observed),patch.object(guard,'contain',return_value={u:dict(stopped=failure!='uncontained') for u in guard.APPS}) as contained,patch.object(control,'write_state',side_effect=persist),patch.object(control.time,'monotonic',side_effect=[0,0,0,8000] if failure=='timeout' else None):
     self.assertIn(control.execute(root,root,'private',True,True,'a'*64),[1,2]);contained.assert_called_once()
     with self.assertRaisesRegex(RuntimeError,'already used'):control.execute(root,root,'private',True,True,'a'*64)
    if failure=='replacement':self.assertFalse(calls)
    self.assertTrue(all(c[:3]==['systemctl','--user','start'] and c[-1] in guard.APPS for c in calls))
    if failure!='persist':self.assertEqual(json.loads((root/'continuation-state.json').read_text())['phase'],'failed-UNCONTAINED' if failure=='uncontained' else 'failed-apps-stopped')
 def test_v2_context_new_manifest_exact_lineage_and_pin_required(self):
  import continuation_context as binding
  for fault in ['none','lineage','source','manifest','context','version']:
   with self.subTest(fault=fault),tempfile.TemporaryDirectory() as d:
    base=Path(d);old=base/'old';old.mkdir(mode=0o700);bundle=base/'bundle';bundle.mkdir(mode=0o700);root=base/'repair';root.mkdir(mode=0o700)
    (old/'manifest.json').write_text('PRIVATE LEGACY');oldpin=binding.digest(old/'manifest.json')
    entry=base/'entry';entry.write_text('PRIVATE CODE')
    m=dict(commit='db8fedae8f4baa35f0ed8193914169eceb7bbe22',repair_from=dict(bundle=str(old),manifest_sha256=oldpin))
    if fault=='lineage':m['repair_from']['manifest_sha256']='0'*64
    if fault=='source':m['commit']='UNREVIEWED'
    (bundle/'manifest.json').write_text(json.dumps(m))
    data=dict(version=2,id=root.name,bundle=str(bundle),previous_bundle=str(old),manifest_sha256=binding.digest(bundle/'manifest.json'),entry=str(entry),driver=str(entry),external_files={str(entry):binding.digest(entry)},original_failed_files={})
    if fault=='manifest':data['manifest_sha256']='0'*64
    if fault=='version':data['version']=True
    file=root/'continuation-context.json';file.write_text(json.dumps(data));file.chmod(0o400);pin=binding.digest(file)
    if fault=='context':pin='0'*64
    with patch.object(binding,'MANIFEST',oldpin),patch('runtime_attestation.validate',return_value={}):
     if fault=='none':self.assertEqual(binding.load_context(bundle,root,pin)['version'],2)
     else:
      with self.assertRaises((RuntimeError,ValueError)):binding.load_context(bundle,root,pin)
 def test_fresh_postreplacement_drift_rejects_before_start(self):
  for fault in ['artifact','mode','base','loaded','reload']:
   with self.subTest(fault=fault),tempfile.TemporaryDirectory() as d:
    root=Path(d);file=root/'replacement';file.write_text('NEW');file.chmod(0o600);base=root/'base';base.write_text('BASE');base.chmod(0o600)
    context=dict(replacement_files={str(file):dict(sha256=repair.digest(file),mode=0o600)})
    identity=dict(unit='private',fragment=str(base),dropins=[str(file)])
    m=dict(units=[dict(path=str(base),sha256=repair.digest(base)),dict(path=str(file),sha256='OLD')],ui=identity,sidecar=identity)
    if fault=='artifact':file.write_text('DRIFT')
    if fault=='mode':file.chmod(0o400)
    if fault=='base':base.write_text('DRIFT')
    def show(*args,**kw):
     if 'FragmentPath' in args:return 'FragmentPath='+('DRIFT' if fault=='loaded' else str(base))+'\nDropInPaths='+str(file)
     return 'yes' if fault=='reload' else 'no'
    with patch.object(prep,'run',side_effect=show),patch.object(control.subprocess,'run') as effects:
     with self.assertRaises(RuntimeError):repair.verify_replacements(context,m)
     effects.assert_not_called()
