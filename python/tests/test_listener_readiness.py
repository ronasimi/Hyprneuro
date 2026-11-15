import os,socket,sys,tempfile,time,unittest,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import continue_app_acceptance as c
import guard_app_release as guard
import apply_app_release as apply
class ReadinessTests(unittest.TestCase):
 def test_real_passive_listen_not_bound_and_rebound(self):
  with tempfile.TemporaryDirectory() as d,socket.socket(socket.AF_UNIX) as first,socket.socket(socket.AF_UNIX) as second:
   p=Path(d)/'broker.sock';first.bind(str(p));p.chmod(0o600)
   self.assertIsNone(c.listener_snapshot(p,os.getpid()))
   first.listen();proof=c.listener_snapshot(p,os.getpid());self.assertTrue(proof)
   self.assertNotEqual(str(proof['filesystem_inode']),proof['kernel_socket_inode'])
   p.unlink();second.bind(str(p));p.chmod(0o600);second.listen()
   with self.assertRaisesRegex(RuntimeError,'rebound'):c.listener_snapshot(p,os.getpid())
 def test_negative_zero_ui_and_containment(self):
  for case in ['pid','stale','different-process','uid','mode','path','not-listening','reload','job','timeout']:
   with self.subTest(case=case),tempfile.TemporaryDirectory() as d:
    root=Path(d);context=dict(id='synthetic',driver='/synthetic');calls=[]
    def wait(path,deadline):
     identity=dict(pid=os.getpid(),start='SYNTHETIC');path.parent.mkdir()
     sock=socket.socket(socket.AF_UNIX);other=None
     try:
      if case=='path':path.write_text('not socket')
      elif case=='different-process':
       other=subprocess.Popen([sys.executable,'-c','import socket,sys;s=socket.socket(socket.AF_UNIX);s.bind(sys.argv[1]);s.listen();print("READY",flush=True);sys.stdin.readline()',str(path)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
       assert other.stdout.readline().strip()=='READY';path.chmod(0o600)
      else:
       sock.bind(str(path));path.chmod(0o666 if case=='mode' else 0o600)
       if case=='stale':sock.close()
       elif case not in ['not-listening','timeout']:sock.listen()
      if case in ['reload','job']:
       from prepare_app_release import run
       fields=dict(MainPID=str(os.getpid()),ActiveState='active',SubState='running',Job='pending' if case=='job' else '',NeedDaemonReload='yes' if case=='reload' else 'no')
       with patch('prepare_app_release.run',return_value='\n'.join(k+'='+v for k,v in fields.items())):return original(path,time.monotonic()+.01)
      if case=='uid':
       uid=os.getuid()
       with patch.object(c,'sidecar_identity',return_value=identity),patch.object(c.os,'getuid',return_value=uid+1):return original(path,time.monotonic()+.01)
      with patch.object(c,'sidecar_identity',side_effect=[identity,dict(identity,start='REPLACED')] if case=='pid' else lambda deadline:identity):
       return original(path,time.monotonic()+.01)
     finally:
      sock.close()
      if other:
       other.stdin.close();other.wait(timeout=3);other.stdout.close()
    original=c.wait_sidecar_listener
    with patch.object(c,'preflight',return_value=(context,dict(runtime=str(root)))),patch.object(c,'load_context',return_value=context),patch.object(c,'wait_sidecar_listener',side_effect=wait),patch.object(c.subprocess,'run',side_effect=lambda argv,**kw:calls.append(argv)),patch.object(apply,'desktop_safe'),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}) as contain:
     self.assertEqual(c.execute(root,root,'synthetic',True,True,'a'*64),1)
    self.assertEqual(calls,[['systemctl','--user','start','hyprneuro.service']]);contain.assert_called_once()
 def test_recheck_after_await_rejects_changed_snapshot(self):
  proof=dict(identity=dict(pid=1,start='x'),path='/synthetic',snapshot={'kernel_socket_inode':'1'})
  with patch.object(c,'sidecar_identity',return_value=proof['identity']),patch.object(c,'listener_snapshot',return_value={'kernel_socket_inode':'2'}):
   with self.assertRaises(RuntimeError):c.recheck_sidecar_listener(proof,time.monotonic()+1)
 def test_real_uid_mode_and_path_rejected(self):
  with tempfile.TemporaryDirectory() as d,socket.socket(socket.AF_UNIX) as sock:
   p=Path(d)/'socket';sock.bind(str(p));sock.listen();p.chmod(0o666)
   with self.assertRaises(RuntimeError):c.listener_snapshot(p,os.getpid())
   p.chmod(0o600);alias=Path(d)/'alias';alias.symlink_to(p)
   with self.assertRaises(RuntimeError):c.listener_snapshot(alias,os.getpid())

 def test_expired_total_budget_and_pid_swap_after_await(self):
  with self.assertRaises(TimeoutError):c.sidecar_identity(time.monotonic()-1)
  proof=dict(identity=dict(pid=1,start='x'),path='/synthetic',snapshot={})
  with patch.object(c,'sidecar_identity',return_value=dict(pid=1,start='new')):
   with self.assertRaises(RuntimeError):c.recheck_sidecar_listener(proof,time.monotonic()+1)
 def test_literal_diagnostic_categories_do_not_click(self):
  import ordinary_app_acceptance as driver
  from types import SimpleNamespace
  ui=driver.UI.__new__(driver.UI);ui.current={'pid':123};ui.safe=lambda:None
  ui.Atspi=SimpleNamespace(StateType=SimpleNamespace(SHOWING='showing',SENSITIVE='sensitive'))
  class Node:
   def __init__(self,states):self.states=states
   def get_role_name(self):return 'button'
   def get_name(self):return 'Connect Pi owner…'
   def get_state_set(self):return SimpleNamespace(contains=lambda flag:flag in self.states)
  for nodes,state in [([], 'absent'),([Node([])],'hidden'),([Node(['showing'])],'insensitive'),([Node(['showing']),Node(['showing'])],'ambiguous')]:
   ui.nodes=lambda:nodes
   text=ui.button_diagnostic('Connect Pi owner…');self.assertIn('pid=123',text);self.assertIn('state='+state,text);self.assertIn('bootstrap-stage=unobserved',text)
