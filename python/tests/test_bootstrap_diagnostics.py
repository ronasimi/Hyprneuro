"""Diagnostic-only fault injection: no production services, DB, grants or inference."""
import asyncio,io,json,sys,unittest
from unittest.mock import patch
from hyprneuro import pi_desktop_bridge as bridge
from hyprneuro import trusted_control as control
class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
 async def test_each_startup_stage_redacted_original_failure_and_sink_error(self):
  for stage in ['broker-inherited','stdio-setup','managed-import','managed-init','SECRET_NONCE']:
   for sink_error in [False,True]:
    with self.subTest(stage=stage,sink_error=sink_error):
     original=RuntimeError('SECRET_NONCE /private/config')
     async def fail(state):state[0]=stage;raise original
     output=io.StringIO()
     if sink_error:output.write=lambda text:(_ for _ in ()).throw(OSError('sink'))
     with patch.object(bridge,'_run',side_effect=fail),patch.object(sys,'stdout',output):
      with self.assertRaises(RuntimeError) as caught:await bridge.run()
     self.assertIs(caught.exception,original)
     if not sink_error:
      text=output.getvalue();self.assertNotIn('SECRET',text);self.assertLess(len(text),256)
      value=json.loads(text);self.assertEqual(set(value),{'type','stage','category'});self.assertEqual(value['stage'],'unknown' if stage=='SECRET_NONCE' else stage)
 def test_broker_cap_redaction_and_broken_sink(self):
  output=io.StringIO()
  with patch.object(sys,'stderr',output):
   for count in range(100):control.diagnostic_rejection('SECRET_NONCE',PermissionError('/private/token'),count)
  records=output.getvalue().splitlines();self.assertEqual(len(records),16)
  for text in records:self.assertLess(len(text),256);self.assertNotIn('SECRET',text);self.assertNotIn('/private',text)
  with patch.object(sys,'stderr',None):control.diagnostic_rejection('peer',RuntimeError('secret'),0)
