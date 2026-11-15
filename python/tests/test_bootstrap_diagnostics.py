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
  import os
  r,w=os.pipe2(os.O_NONBLOCK)
  dup=os.dup
  try:
   with patch.object(control.os,'dup',side_effect=lambda fd:dup(w)):
    for count in range(100):control.diagnostic_rejection('SECRET_NONCE',PermissionError('/private/token'),count)
   records=os.read(r,8192).decode().splitlines();self.assertEqual(len(records),16)
   for text in records:self.assertLess(len(text),256);self.assertNotIn('SECRET',text);self.assertNotIn('/private',text)
   with patch.object(control.os,'dup',side_effect=lambda fd:dup(w)),patch.object(control.os,'write',side_effect=OSError('sink')):
    control.diagnostic_rejection('peer',RuntimeError('secret'),0)
   with patch.object(sys,'stderr',None),patch.object(control.os,'dup') as opened:
    control.diagnostic_rejection('peer',RuntimeError('secret'),0);opened.assert_not_called()
   with patch.object(control.os,'dup') as opened:
    control.diagnostic_rejection('peer',RuntimeError('secret'),16);opened.assert_not_called()
  finally:os.close(r);os.close(w)
 def test_unsupported_destinations_drop_without_opening_or_writing(self):
  import os,socket,tempfile
  dup=os.dup
  left,right=socket.socketpair()
  try:
   with tempfile.TemporaryFile() as regular:
    for fd in [regular.fileno(),left.fileno()]:
     with patch.object(control.os,'dup',side_effect=lambda original:dup(fd)),patch.object(control.os,'open') as opened,patch.object(control.os,'write') as written,patch.object(control.os,'fstat') as metadata:
      control.diagnostic_rejection('peer',RuntimeError('secret'),0)
      opened.assert_not_called();written.assert_not_called();metadata.assert_not_called()
  finally:left.close();right.close()

class BackpressureTests(unittest.TestCase):
 def test_registered_full_undrained_stderr_does_not_delay_invalidation(self):
  import os,subprocess
  from pathlib import Path
  fixture=Path(__file__).with_name('broker_backpressure_fixture.py')
  try:
   result=subprocess.run([sys.executable,'-B',str(fixture)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=4,env=dict(os.environ))
  except subprocess.TimeoutExpired as error:
   self.fail(f'Watchdog killed blocked broker; checkpoint={error.stdout!r}')
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  self.assertIn('handler terminated WITHOUT draining',result.stdout)
