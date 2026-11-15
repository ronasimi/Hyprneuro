import copy,hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import runtime_attestation as runtime
import verify_installed_continuation as external
class RuntimeTests(unittest.TestCase):
 def test_exact_pinned_current_and_every_drift(self):
  with tempfile.TemporaryDirectory() as directory:
   file=Path(directory)/'runtime.json';models=[dict(identity=dict(unit='lfm@'+r+'.service',pid=10,start='20',exe_sha256='NEW'),argv=['server','--port',str(8081+i)],selected_files={'unit':'HASH'},libraries={'lib':'HASH'},state='active',health={'status':'ok'},identifiers={'data':[{'id':r}]}) for i,r in enumerate(['text','omni','decision'])]
   file.write_text(json.dumps(dict(version=1,continuation_id='new',models=models)));file.chmod(0o400);context=dict(id='new',runtime_attestation=dict(path=str(file),sha256=runtime.digest(file)))
   with patch.object(runtime,'observe',side_effect=lambda u:copy.deepcopy(next(m for m in models if m['identity']['unit']==u))):self.assertEqual(runtime.validate(context)['models'],models)
   for key in ['pid','start','exe_sha256','argv','selected_files','libraries','state','health','identifiers']:
    changed=copy.deepcopy(models[0])
    if key in changed['identity']:changed['identity'][key]='STALE'
    else:changed[key]='DRIFT'
    with self.subTest(key=key),patch.object(runtime,'observe',return_value=changed):
     with self.assertRaisesRegex(RuntimeError,'drift'):runtime.validate(context)
   file.chmod(0o600);file.write_text('{}');file.chmod(0o400)
   with self.assertRaisesRegex(RuntimeError,'digest'):runtime.validate(context)
 def test_no_missing_or_old_scope_fallback_or_apply_route(self):
  with self.assertRaises(KeyError):runtime.validate({})
  with self.assertRaises(TypeError):external.verify(Path('/none'),installed=False)
 def test_nonruntime_verifier_body_contract(self):
  root=Path(__file__).resolve().parents[2]/'scripts'
  original=(root/'verify_app_release.py').read_text();actual=(root/'verify_installed_continuation.py').read_text()
  original=original[original.index('    if legacy and not installed:'):original.index("if __name__=='__main__':")].strip()
  actual=actual[actual.index('    if legacy and not installed:'):].strip()
  actual=actual.replace("for identity in [entry['identity'] for entry in runtime['models']]:","for identity in m['models']:")
  actual=actual.replace('    load_context(bundle,root,context_sha256)\n','')
  self.assertEqual(actual,original)
 def test_api_creation_time_not_identifier(self):
  self.assertEqual(runtime.identifiers({'data':[{'id':'x','created':1}]}),{'data':[{'id':'x'}]})
