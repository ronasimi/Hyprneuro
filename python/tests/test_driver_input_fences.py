import importlib.util,subprocess,unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('ordinary',Path(__file__).resolve().parents[2]/'scripts/ordinary_app_acceptance.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class InputFences(unittest.TestCase):
 def test_scope_drift_zero_click(self):
  for drift in ['identity','context','layer','workspace','dialog']:
   with self.subTest(drift=drift):
    ui=m.UI.__new__(m.UI);layer=dict(x=0,y=0,w=100,h=100);calls=[]
    def ordinary():
     if calls:
      if drift=='layer':return dict(layer,w=99)
      raise RuntimeError(drift)
     return layer
    ui.ordinary=ordinary
    with patch.object(m.subprocess,'check_output',side_effect=lambda argv,**kw:calls.append((argv,kw)) or ''):
     with self.assertRaises(RuntimeError):ui.focus_pointer(layer,20,30)
    self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],('wdotool','--backend','wlr-protocols','mousemove','20','30'));self.assertEqual(calls[0][1]['timeout'],5)
 def test_move_timeout_zero_click(self):
  ui=m.UI.__new__(m.UI);ui.ordinary=lambda:{}
  with patch.object(m.subprocess,'check_output',side_effect=subprocess.TimeoutExpired('mousemove',5)) as command:
   with self.assertRaises(subprocess.TimeoutExpired):ui.focus_pointer({},1,2)
   self.assertEqual(command.call_count,1)
 def test_success_bounded_arrays(self):
  ui=m.UI.__new__(m.UI);ui.ordinary=lambda:{}
  with patch.object(m.subprocess,'check_output',return_value='') as command:
   ui.focus_pointer({},1,2)
   self.assertEqual(command.call_args_list[-1].args[0],('wdotool','--backend','wlr-protocols','click','1'))
   for call in command.call_args_list:self.assertEqual(call.kwargs,dict(text=True,timeout=5))
class KeyCleanupFences(unittest.TestCase):
 def ui(self):
  import types
  ui=m.UI.__new__(m.UI);ui.deadline=__import__('time').monotonic()+5;ui.keys_inflight=False;ui.current={'pid':123};ui.m={'runtime':'/private'}
  ui.ordinary=lambda:None
  ui.Atspi=types.SimpleNamespace(StateType=types.SimpleNamespace(FOCUSED=1))
  ui.composer=lambda:types.SimpleNamespace(get_state_set=lambda:types.SimpleNamespace(contains=lambda state:True))
  ui.status_reader=lambda *args:{'mode':'legacy','connected':False}
  return ui
 def test_expired_operation_still_spawns_one_exact_bounded_release(self):
  ui=self.ui();original=subprocess.TimeoutExpired('key',.01)
  def command(argv,**kwargs):
   if argv[-2]=='key':ui.deadline=0;raise original
   return ''
  with patch.object(m.subprocess,'check_output',side_effect=command) as release:
   with self.assertRaises(subprocess.TimeoutExpired) as caught:ui.key('ctrl+Return')
  self.assertIs(caught.exception,original);self.assertFalse(ui.keys_inflight)
  self.assertEqual(release.call_count,2)
  release.assert_called_with(('wdotool','--backend','wlr-protocols','keyup','ctrl+Return'),text=True,timeout=5)
 def test_release_failure_preserves_chain_original_error_and_blocks_input(self):
  for error in [subprocess.TimeoutExpired('keyup',5),OSError('private error')]:
   with self.subTest(error=type(error).__name__):
    ui=self.ui();original=subprocess.TimeoutExpired('key',.01);ui.deadline=__import__('time').monotonic()+5
    def command(argv,**kwargs):
     if argv[-2]=='key':ui.deadline=0;raise original
     raise error
    with patch.object(m.subprocess,'check_output',side_effect=command) as release:
     with self.assertRaises(subprocess.TimeoutExpired) as caught:ui.key('ctrl+Return')
    self.assertIs(caught.exception,original);self.assertTrue(ui.keys_inflight);self.assertEqual(ui.pending_key_chain,'ctrl+Return');self.assertTrue(ui.key_cleanup_error)
    self.assertEqual(release.call_count,2)
    del ui.ordinary
    with self.assertRaisesRegex(RuntimeError,'uncertain'):ui.ordinary()
 def test_release_failure_after_success_is_explicit_failure(self):
  ui=self.ui()
  def command(argv,**kwargs):
   if argv[-2]=='keyup':raise OSError('private error')
   return ''
  with patch.object(m.subprocess,'check_output',side_effect=command):
   with self.assertRaisesRegex(RuntimeError,'release uncertain'):ui.key('Return')
  self.assertTrue(ui.keys_inflight);self.assertEqual(ui.pending_key_chain,'Return')
 def test_private_executable_release_spawns_after_key_timeout(self):
  import os,tempfile,time,json
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);log=root/'argv.jsonl';tool=root/'wdotool'
   tool.write_text('#!'+sys.executable+'\nimport sys,time,json\nwith open('+repr(str(log))+',"a") as f:f.write(json.dumps(sys.argv[1:])+"\\n")\nif sys.argv[-2]=="key":time.sleep(5)\n');tool.chmod(0o700)
   ui=self.ui();ui.deadline=time.monotonic()+.15
   with patch.dict(os.environ,PATH=str(root)+os.pathsep+os.environ.get('PATH','')):
    with self.assertRaises(subprocess.TimeoutExpired):ui.key('ctrl+Return')
   calls=[json.loads(line) for line in log.read_text().splitlines()]
   self.assertEqual(calls,[['--backend','wlr-protocols','key','ctrl+Return'],['--backend','wlr-protocols','keyup','ctrl+Return']])
   self.assertFalse(ui.keys_inflight);self.assertIsNone(ui.pending_key_chain)
 def test_expired_before_attempt_spawns_neither_key_nor_release(self):
  ui=self.ui();ui.deadline=0
  with patch.object(m.subprocess,'check_output') as command:
   with self.assertRaises(TimeoutError):ui.key('ctrl+Return')
   command.assert_not_called()
  self.assertFalse(ui.keys_inflight)

class BootstrapSnapshot(unittest.TestCase):
 def ui(self,text,pid=123,role='label',showing=True):
  import types
  ui=m.UI.__new__(m.UI);ui.current={'pid':123};ui.safe=lambda:None
  ui.Atspi=types.SimpleNamespace(StateType=types.SimpleNamespace(SHOWING=1))
  node=types.SimpleNamespace(get_process_id=lambda:pid,get_role_name=lambda:role,get_name=lambda:text,get_description=lambda:'hyprneuro-bootstrap-status',get_state_set=lambda:types.SimpleNamespace(contains=lambda state:showing))
  ui.nodes=lambda:[node];return ui
 def test_owned_exact_status_only_no_raw_projection(self):
  good='Pi bridge unavailable · diagnostic broker-unit-job/identity · no authority/retry'
  ui=self.ui(good);self.assertEqual(ui.bootstrap_diagnostic(),{'diagnostic':'NONAUTHORITATIVE','stage':'broker-unit-job','category':'identity'})
  for text in [good.replace('broker-unit-job','SECRET_NONCE'),good.replace('identity','/private/credential'),good+'SECRET','x'*10000]:
   result=self.ui(text).bootstrap_diagnostic();self.assertEqual(result['stage'],'unknown');self.assertNotIn('SECRET',str(result));self.assertLess(len(str(result)),100)
  for options in [dict(pid=999),dict(role='button'),dict(showing=False)]:self.assertEqual(self.ui(good,**options).bootstrap_diagnostic()['stage'],'unknown')
  ui.nodes=lambda:[];self.assertEqual(ui.bootstrap_diagnostic()['stage'],'unknown')
 def test_ambiguous_drift_and_failure_preserve_original(self):
  ui=self.ui('Pi bridge unavailable · diagnostic challenge/eof · no authority/retry');node=ui.nodes()[0];ui.nodes=lambda:[node,node]
  self.assertEqual(ui.bootstrap_diagnostic()['stage'],'unknown')
  ui.safe=lambda:(_ for _ in ()).throw(RuntimeError('identity drift SECRET'))
  self.assertEqual(ui.bootstrap_diagnostic()['stage'],'unknown')
