import importlib.util,subprocess,unittest
from pathlib import Path
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
