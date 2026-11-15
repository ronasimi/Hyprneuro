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
  ui=m.UI.__new__(m.UI);ui.deadline=0;ui.keys_inflight=False;ui.current={'pid':123};ui.m={'runtime':'/private'}
  ui.ordinary=lambda:None
  ui.Atspi=types.SimpleNamespace(StateType=types.SimpleNamespace(FOCUSED=1))
  ui.composer=lambda:types.SimpleNamespace(get_state_set=lambda:types.SimpleNamespace(contains=lambda state:True))
  ui.status_reader=lambda *args:{'mode':'legacy','connected':False}
  return ui
 def test_expired_operation_still_spawns_one_exact_bounded_release(self):
  ui=self.ui();original=subprocess.TimeoutExpired('key',.01)
  ui.command=lambda *args:(_ for _ in ()).throw(original)
  with patch.object(m.subprocess,'check_output',return_value='') as release:
   with self.assertRaises(subprocess.TimeoutExpired) as caught:ui.key('ctrl+Return')
  self.assertIs(caught.exception,original);self.assertFalse(ui.keys_inflight)
  release.assert_called_once_with(('wdotool','--backend','wlr-protocols','keyup','ctrl+Return'),text=True,timeout=5)
 def test_release_failure_preserves_chain_original_error_and_blocks_input(self):
  for error in [subprocess.TimeoutExpired('keyup',5),OSError('private error')]:
   with self.subTest(error=type(error).__name__):
    ui=self.ui();original=subprocess.TimeoutExpired('key',.01);ui.command=lambda *args:(_ for _ in ()).throw(original)
    with patch.object(m.subprocess,'check_output',side_effect=error) as release:
     with self.assertRaises(subprocess.TimeoutExpired) as caught:ui.key('ctrl+Return')
    self.assertIs(caught.exception,original);self.assertTrue(ui.keys_inflight);self.assertEqual(ui.pending_key_chain,'ctrl+Return');self.assertTrue(ui.key_cleanup_error)
    self.assertEqual(release.call_count,1)
    del ui.ordinary
    with self.assertRaisesRegex(RuntimeError,'uncertain'):ui.ordinary()
 def test_release_failure_after_success_is_explicit_failure(self):
  ui=self.ui();ui.command=lambda *args:''
  with patch.object(m.subprocess,'check_output',side_effect=OSError('private error')):
   with self.assertRaisesRegex(RuntimeError,'release uncertain'):ui.key('Return')
  self.assertTrue(ui.keys_inflight);self.assertEqual(ui.pending_key_chain,'Return')
