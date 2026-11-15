"""Private synthetic driver fixtures; never connect to production GUI/models."""
import importlib.util
from pathlib import Path
import time
import unittest

spec=importlib.util.spec_from_file_location('ordinary',Path(__file__).resolve().parents[2]/'scripts/ordinary_app_acceptance.py')
driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)

class FakeUI:
    def __init__(self,fail=None):self.fail=fail;self.calls=[];self.consent_prompts={'synthetic-activation','synthetic-read'};self.fixture='synthetic canary';self.expanded=False
    def __getattr__(self,name):
        def call(*args,**kwargs):
            self.calls.append((name,args))
            if self.fail==name:raise RuntimeError('synthetic '+name)
            if name=='button' and args[0].startswith(('Expand transcript','Restore transcript')):self.expanded=not self.expanded
            if name=='size':return 'Restore transcript: Expanded → Normal' if self.expanded else 'Expand transcript: Normal → Expanded'
            return True
        return call

class DriverTests(unittest.TestCase):
    def test_only_literal_inputs_and_no_security_or_chooser_approval(self):
        ui=FakeUI();ready=[]
        driver.exercise(ui,ready.append,time.monotonic()+2)
        self.assertEqual([args[0] for name,args in ui.calls if name=='draft'],[driver.FIRST,driver.SECOND,driver.READ])
        self.assertEqual(ready[-1],True)
        self.assertTrue(all(args[0] in driver.BUTTONS for name,args in ui.calls if name=='button'))
        self.assertFalse(any('Allow' in str(args) for name,args in ui.calls if name=='button'))

    def test_failure_at_each_ordinary_or_native_check_propagates_nonzero_to_guard(self):
        for name in ['show','empty','button','size','draft','key','expect_draft','settled','hide_show','connected','record','safe']:
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):driver.exercise(FakeUI(fail=name),lambda ready:None,time.monotonic()+2)

    def test_early_completion_and_lock_failure_are_never_accepted(self):
        for reason in ['premature completion','locked']:
            def pending(ready):raise RuntimeError(reason)
            with self.assertRaises(RuntimeError):driver.exercise(FakeUI(),pending,time.monotonic()+2)

    def test_missing_genuine_prompt_observations_prevent_completion(self):
        ui=FakeUI();ui.consent_prompts=set();ready=[]
        with self.assertRaisesRegex(RuntimeError,'prompt observations missing'):
            driver.exercise(ui,ready.append,time.monotonic()+2)
        self.assertNotIn(True,ready)

class GuardIntegrationTests(unittest.TestCase):
    def test_driver_failure_before_after_checks_lock_and_early_completion_contain(self):
        import tempfile,sys
        from unittest.mock import patch
        scripts=Path(__file__).resolve().parents[2]/'scripts'
        sys.path.insert(0,str(scripts))
        import guard_app_release as guard
        for failure in ['show','settled','connected','safe','premature']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'manifest.json').write_text('{"owner":"/synthetic"}')
                code=('import sys,time;sys.path.insert(0,'+repr(str(Path(__file__).parent))+');'
                      'from test_ordinary_app_acceptance import FakeUI,driver;'
                      'driver.exercise(FakeUI(fail='+repr(failure)+'),'
                      +('(lambda ready: (_ for _ in ()).throw(RuntimeError("premature completion")))' if failure=='premature' else '(lambda ready:None)')
                      +',time.monotonic()+2)')
                with patch.object(guard,'apply'),patch.object(guard,'observe'),patch.object(guard,'contain',return_value={unit:dict(stopped=True) for unit in guard.APPS}) as contained:
                    self.assertEqual(guard.execute(root,'synthetic',[sys.executable,'-c',code],authorized=True,unlocked=True),1)
                    contained.assert_called_once()
                import json
                state=json.loads((root/'operation-state.json').read_text())
                self.assertEqual(state['phase'],'failed-apps-stopped')
                self.assertFalse(state['human_acceptance_claimed'])

class AtomicPublicationTests(unittest.TestCase):
    def test_human_event_is_operation_bound_private_and_never_a_coordinator_result(self):
        import tempfile,os,json,hashlib
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);marker=root/'operation.started';marker.write_text('SYNTHETIC');marker.chmod(0o600)
            ui=driver.UI.__new__(driver.UI);ui.bundle=root;ui.events=[];ui.m=dict(owner_descriptor_sha256='synthetic')
            previous=os.umask(0o077)
            try:ui.record('HUMAN-NEEDED',prompt='SYNTHETIC actual prompt fixture NOT HUMAN')
            finally:os.umask(previous)
            event=json.loads((root/'acceptance-human-gate.json').read_text())
            self.assertEqual(event['seq'],1);self.assertEqual(event['operation_sha256'],hashlib.sha256(marker.read_bytes()).hexdigest())
            self.assertEqual((root/'acceptance-human-gate.json').stat().st_mode&0o777,0o600)
            self.assertFalse((root/'acceptance-result.json').exists())
            self.assertNotIn('approved',event)

class ActualCoordinatorTests(unittest.TestCase):
    def test_actual_existing_coordinator_completed_before_checks_is_rejected(self):
        import tempfile,hashlib,json,sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
        for result in ['completed','failed','cancelled']:
            with self.subTest(result=result),tempfile.TemporaryDirectory() as d:
                root=Path(d);marker=root/'operation.started';marker.write_text('SYNTHETIC');marker.chmod(0o600)
                target=root/'acceptance-result.json';target.write_text(json.dumps(dict(operation_started_sha256=hashlib.sha256(marker.read_bytes()).hexdigest(),result=result)));target.chmod(0o600)
                with self.assertRaises(RuntimeError):driver.coordinator(root,time.monotonic()+1,False)
                if result=='completed':driver.coordinator(root,time.monotonic()+1,True)
                else:
                    with self.assertRaises(RuntimeError):driver.coordinator(root,time.monotonic()+1,True)

class TranscriptProofTests(unittest.TestCase):
    def test_user_prompt_and_prior_answer_are_not_current_answer_evidence(self):
        text='\nyou: marker\n\nassistant: MARKER\n\nyou: MARKER\n\nassistant: wrong\n'
        self.assertNotIn('MARKER',driver.current_answer(text))
        self.assertEqual(driver.current_answer(text),'wrong\n')
        self.assertIn('MARKER',driver.current_answer(text+'\nyou: next\n\nassistant: MARKER\n'))

class FolderChooserContractTests(unittest.TestCase):
    def test_both_human_notices_target_owner_directory_not_json_file(self):
        import json
        from unittest.mock import Mock
        ui=driver.UI.__new__(driver.UI)
        ui.m=dict(owner='/synthetic/private/owner',owner_descriptor_sha256='synthetic-pinned-sha')
        ui.record=Mock();ui.chooser_notice()
        ui.prompt=lambda:False;ui.events=[]
        ui.command=lambda *args:json.dumps([dict(title='Select prepared private Pi owner root — not personal files')])
        self.assertFalse(ui.connected())
        self.assertEqual(len(ui.record.call_args_list),2)
        for call in ui.record.call_args_list:
            self.assertEqual(call.kwargs['owner_directory'],ui.m['owner'])
            self.assertEqual(call.kwargs['descriptor_sha256'],ui.m['owner_descriptor_sha256'])
            self.assertIn('DIRECTORY',call.kwargs['action']);self.assertIn('NOT the JSON file',call.kwargs['action'])
        picker=(Path(__file__).resolve().parents[2]/'ui/src/pi-picker.inc').read_text()
        self.assertIn('gtk_file_dialog_select_folder(',picker)
        self.assertIn('gtk_file_dialog_select_folder_finish(',picker)

    def test_published_chooser_event_keeps_directory_and_descriptor_hash_binding(self):
        import tempfile,os,json
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'operation.started').write_text('synthetic')
            ui=driver.UI.__new__(driver.UI);ui.bundle=root;ui.events=[]
            ui.m=dict(owner='/synthetic/private/owner',owner_descriptor_sha256='synthetic-pinned-sha')
            old=os.umask(0o077)
            try:ui.record('HUMAN-NEEDED-CHOOSER',prompt='SYNTHETIC chooser',owner_directory=ui.m['owner'])
            finally:os.umask(old)
            event=json.loads((root/'acceptance-human-gate.json').read_text())
            self.assertIn('DIRECTORY '+ui.m['owner'],event['prompt'])
            self.assertIn('Do NOT select the JSON file',event['prompt'])
            self.assertEqual(event['descriptor_sha256'],ui.m['owner_descriptor_sha256'])
