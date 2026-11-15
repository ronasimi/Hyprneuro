"""Offline continuation failure injection; never starts production services."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import continue_app_acceptance as continuation
import guard_app_release as guard
import apply_app_release as apply
import continuation_context as binding

class ContinuationTests(unittest.TestCase):
    def test_each_start_verify_driver_lock_cancel_timeout_and_persistence_failure_contain(self):
        for failure in ['sidecar','ui','verify','driver','lock','cancel','timeout','persist','persist-after-start']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'continuation-context.json').write_text('SYNTHETIC')
                context=dict(id='synthetic',driver='/synthetic/driver');calls=[]
                def control(argv,**kwargs):
                    calls.append(argv)
                    if (failure=='sidecar' and argv[-1]=='hyprneuro.service') or (failure=='ui' and argv[-1]=='hyprneuro-ui.service'):raise RuntimeError('Synthetic AFTER successful start')
                def verified(bundle):
                    if failure=='verify':raise RuntimeError('Installed verify failed')
                def observed(*args):
                    if failure=='lock':raise RuntimeError('Locked')
                    if failure=='cancel':raise KeyboardInterrupt()
                process=Mock();process.poll.return_value=None if failure=='timeout' else 1;process.returncode=1
                persist=continuation.write_state
                def state(*args):
                    if failure=='persist' or (failure=='persist-after-start' and args[2]=='verifying-installed'):raise OSError('fsync failure')
                    return persist(*args)
                with patch.object(continuation,'preflight',return_value=(context,{})),patch.object(continuation,'load_context',return_value=context),patch.object(continuation.subprocess,'run',side_effect=control),patch.object(continuation,'verify_started',side_effect=verified),patch.object(continuation,'write_state',side_effect=state),patch.object(guard,'observe',side_effect=observed),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}) as contained,patch.object(apply,'desktop_safe'),patch.object(continuation.subprocess,'Popen',return_value=process),patch.object(continuation.time,'monotonic',side_effect=[0,8000] if failure=='timeout' else None):
                    self.assertEqual(continuation.execute(root,root,'synthetic',True,True,'a'*64),2 if failure=='persist' else 1)
                    contained.assert_called_once()
                self.assertTrue(all(c[:3]==['systemctl','--user','start'] and c[-1] in guard.APPS for c in calls))
                self.assertTrue((root/'operation.started').exists())
                if failure!='persist':self.assertEqual(json.loads((root/'continuation-state.json').read_text())['phase'],'failed-apps-stopped')

    def test_stop_failure_honest_uncontained_and_no_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'continuation-context.json').write_text('SYNTHETIC')
            context=dict(id='synthetic',driver='/synthetic/driver')
            with patch.object(continuation,'preflight',return_value=(context,{})),patch.object(continuation.subprocess,'run',side_effect=RuntimeError('start')),patch.object(apply,'desktop_safe'),patch.object(guard,'contain',return_value={u:dict(stopped=False) for u in guard.APPS}):
                self.assertEqual(continuation.execute(root,root,'synthetic',True,True,'a'*64),1)
                self.assertEqual(json.loads((root/'continuation-state.json').read_text())['phase'],'failed-UNCONTAINED')
                with self.assertRaisesRegex(RuntimeError,'already used'):continuation.execute(root,root,'synthetic',True,True,'a'*64)

    def test_preflight_failure_never_starts_or_stops(self):
        with patch.object(continuation,'preflight',side_effect=RuntimeError('unknown owner')),patch.object(continuation.subprocess,'run') as commands:
            with self.assertRaises(RuntimeError):continuation.execute(Path('/synthetic'),Path('/synthetic'),'synthetic',True,True)
            commands.assert_not_called()

    def test_context_ancestry_and_new_generation_are_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'continuation-context.json').write_text('SYNTHETIC')
            context=dict(id='synthetic',entry='/synthetic/continue')
            marker=dict(id='synthetic',context_sha256=binding.digest(root/'continuation-context.json'),pid=42,start='123')
            (root/'operation.started').write_text(json.dumps(marker))
            argv=['python','/synthetic/continue','/synthetic/bundle','--continuation',str(root),'--session','synthetic','--context-sha256',binding.digest(root/'continuation-context.json')]
            with patch.object(binding,'load_context',return_value=context):
                binding.require_parent(Path('/synthetic/bundle'),root,argv,42,'123',binding.digest(root/'continuation-context.json'))
                for pid,start in [(43,'123'),(42,'124')]:
                    with self.assertRaises(RuntimeError):binding.require_parent(Path('/synthetic/bundle'),root,argv,pid,start,binding.digest(root/'continuation-context.json'))
                argv[1]='/synthetic/original/guard'
                with self.assertRaises(RuntimeError):binding.require_parent(Path('/synthetic/bundle'),root,argv,42,'123',binding.digest(root/'continuation-context.json'))

    def test_uncertain_driver_stop_is_uncontained_even_when_apps_stopped(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'continuation-context.json').write_text('SYNTHETIC')
            context=dict(id='synthetic',driver='/synthetic/driver');process=Mock();process.poll.return_value=None;process.terminate.side_effect=RuntimeError('unknown')
            with patch.object(continuation,'preflight',return_value=(context,{})),patch.object(continuation,'load_context',return_value=context),patch.object(continuation.subprocess,'run'),patch.object(continuation,'verify_started'),patch.object(apply,'desktop_safe'),patch.object(guard,'observe'),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}),patch.object(continuation.subprocess,'Popen',return_value=process),patch.object(continuation.time,'monotonic',side_effect=[0,8000]):
                self.assertEqual(continuation.execute(root,root,'synthetic',True,True,'a'*64),1)
            self.assertEqual(json.loads((root/'continuation-state.json').read_text())['phase'],'failed-UNCONTAINED')

    def test_success_is_command_completion_not_human_or_ready_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'continuation-context.json').write_text('SYNTHETIC')
            context=dict(id='synthetic',driver='/synthetic/driver');process=Mock();process.poll.return_value=0;process.returncode=0
            with patch.object(continuation,'preflight',return_value=(context,{})),patch.object(continuation,'load_context',return_value=context),patch.object(continuation.subprocess,'run'),patch.object(continuation,'verify_started'),patch.object(apply,'desktop_safe'),patch.object(guard,'observe'),patch.object(continuation.subprocess,'Popen',return_value=process):
                self.assertEqual(continuation.execute(root,root,'synthetic',True,True,'a'*64),0)
            state=json.loads((root/'continuation-state.json').read_text());self.assertFalse(state['human_acceptance_claimed'])
            self.assertIn('NOT-human-READY',state['phase'])

class ContinuationRoutingTests(unittest.TestCase):
    def test_watcher_ignores_original_events_and_uses_new_operation_generation(self):
        import hashlib
        import watch_app_acceptance as watcher
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);bundle=base/'bundle';root=base/'continuation';bundle.mkdir(mode=0o700);root.mkdir(mode=0o700)
            manifest=bundle/'manifest.json';manifest.write_text('{"owner_descriptor_sha256":"synthetic"}');manifest.chmod(0o600)
            pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
            for path,text in [(bundle/'operation.started','ORIGINAL FAILED'),(root/'operation.started','NEW GENERATION')]:path.write_text(text);path.chmod(0o600)
            event=dict(version=1,seq=1,kind='consent',prompt='SYNTHETIC',descriptor_sha256='synthetic',operation_sha256=hashlib.sha256((bundle/'operation.started').read_bytes()).hexdigest())
            original=bundle/watcher.EVENT;original.write_text(json.dumps(event));original.chmod(0o600)
            with patch.object(binding,'load_context',return_value={}):
                with self.assertRaises(TimeoutError):watcher.watch(bundle,0,.01,pin,root)
                target=root/watcher.EVENT;target.write_text(json.dumps(event));target.chmod(0o600)
                with self.assertRaises(ValueError):watcher.watch(bundle,0,.01,pin,root)
                event['operation_sha256']=hashlib.sha256((root/'operation.started').read_bytes()).hexdigest();target.write_text(json.dumps(event))
                result=watcher.watch(bundle,0,1,pin,root);self.assertEqual(result['event']['operation_sha256'],event['operation_sha256'])
            self.assertEqual((bundle/'operation.started').read_text(),'ORIGINAL FAILED')

    def test_driver_events_and_coordinator_write_read_only_new_root(self):
        import ordinary_app_acceptance as driver
        import hashlib,os,time
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);bundle=base/'bundle';root=base/'continuation';bundle.mkdir(mode=0o700);root.mkdir(mode=0o700)
            for path,text in [(bundle/'operation.started','ORIGINAL FAILED'),(root/'operation.started','NEW GENERATION')]:path.write_text(text);path.chmod(0o600)
            ui=driver.UI.__new__(driver.UI);ui.bundle=bundle;ui.runtime=root;ui.events=[];ui.m=dict(owner_descriptor_sha256='synthetic')
            old=os.umask(0o077)
            try:ui.record('HUMAN-NEEDED',prompt='SYNTHETIC no authority')
            finally:os.umask(old)
            self.assertFalse((bundle/'acceptance-human-gate.json').exists())
            event=json.loads((root/'acceptance-human-gate.json').read_text());self.assertEqual(event['operation_sha256'],hashlib.sha256((root/'operation.started').read_bytes()).hexdigest())
            result=dict(operation_started_sha256=hashlib.sha256((bundle/'operation.started').read_bytes()).hexdigest(),result='completed')
            file=root/'acceptance-result.json';file.write_text(json.dumps(result));file.chmod(0o600)
            with self.assertRaises(RuntimeError):driver.coordinator(root,time.monotonic()+1,True)

class ImmutableContextTests(unittest.TestCase):
    def test_changed_failed_attempt_code_or_context_mode_cannot_be_adopted(self):
        import hashlib
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);bundle=base/'bundle';root=base/'continuation-synthetic';bundle.mkdir(mode=0o700);root.mkdir(mode=0o700)
            manifest=bundle/'manifest.json';manifest.write_text('SYNTHETIC manifest');pin=hashlib.sha256(manifest.read_bytes()).hexdigest()
            original=bundle/'operation.started';original.write_text('FAILED ORIGINAL')
            entry=base/'entry.py';entry.write_text('SYNTHETIC code')
            context=dict(version=1,id=root.name,bundle=str(bundle),manifest_sha256=pin,entry=str(entry),driver=str(entry),external_files={str(entry):binding.digest(entry)},original_failed_files={str(original):binding.digest(original)})
            file=root/'continuation-context.json';file.write_text(json.dumps(context));file.chmod(0o400);context_pin=binding.digest(file)
            with patch.object(binding,'MANIFEST',pin):
                binding.load_context(bundle,root,context_pin)
                original.write_text('CHANGED')
                with self.assertRaises(RuntimeError):binding.load_context(bundle,root,context_pin)
                original.write_text('FAILED ORIGINAL');entry.write_text('CHANGED')
                with self.assertRaises(RuntimeError):binding.load_context(bundle,root,context_pin)
                entry.write_text('SYNTHETIC code');file.chmod(0o600)
                with self.assertRaises(PermissionError):binding.load_context(bundle,root,context_pin)
