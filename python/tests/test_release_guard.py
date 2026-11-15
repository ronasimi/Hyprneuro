"""Offline containment fault injection ONLY. No real units/DB/models/GUI."""
import importlib.util
from contextlib import closing
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch,Mock

SCRIPTS=Path(__file__).resolve().parents[2]/'scripts'
sys.path.insert(0,str(SCRIPTS))
import guard_app_release as guard
import apply_app_release as apply
import prepare_app_release as prepare


class ReleaseGuardTests(unittest.TestCase):
    def test_apply_each_service_start_and_verification_failure_contained_even_locked(self):
        for failure in ['sidecar-start','ui-start','post-verify','lock','journal','owner','cancel','acceptance-exit']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory)
                (root/'manifest.json').write_text(json.dumps(dict(owner=str(root/'owner'))))
                stops=[]
                def stopped(unit):return dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',ControlGroup='')
                def control(command,**kwargs):
                    self.assertEqual(command[:3],['systemctl','--user','stop'])
                    stops.append(command[3]);return Mock(returncode=0)
                def applying(*args):
                    (root/'apply.started').write_text('exclusive fixture marker')
                    if failure in ['sidecar-start','ui-start','post-verify']:
                        raise RuntimeError('Synthetic failure after '+failure)
                driver=Mock();driver.poll.return_value=1 if failure=='acceptance-exit' else None;driver.returncode=1
                error=KeyboardInterrupt() if failure=='cancel' else RuntimeError(failure)
                with patch.object(guard,'apply',side_effect=applying),patch.object(guard,'observe',side_effect=error),patch.object(guard,'unit_state',side_effect=stopped),patch.object(guard.subprocess,'run',side_effect=control),patch.object(guard.subprocess,'Popen',return_value=driver),patch.object(guard,'desktop_safe',side_effect=AssertionError('Containment must not check unlock')):
                    self.assertEqual(guard.execute(root,'fixture',['fixture-driver'],authorized=True,unlocked=True),1)
                self.assertEqual(stops,list(guard.APPS))
                state=json.loads((root/'operation-state.json').read_text())
                self.assertEqual(state['phase'],'failed-apps-stopped');self.assertFalse(state['human_acceptance_claimed'])
                self.assertTrue((root/'apply.started').exists())
                with self.assertRaises(RuntimeError):guard.execute(root,'fixture',['no-replay'],authorized=True,unlocked=True)

    def test_stop_failure_reports_uncontained_and_still_attempts_both_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);calls=[]
            def stop(command,**kwargs):calls.append(command);return Mock(returncode=1)
            with patch.object(guard,'apply',side_effect=RuntimeError('post-start')),patch.object(guard.subprocess,'run',side_effect=stop),patch.object(guard,'unit_state',return_value=dict(ActiveState='active',SubState='running',MainPID='42',Job='',ControlGroup='')):
                self.assertEqual(guard.execute(root,'fixture',['driver'],authorized=True,unlocked=True),1)
            self.assertEqual(len(calls),2)
            self.assertEqual(json.loads((root/'operation-state.json').read_text())['phase'],'failed-UNCONTAINED')

    def test_acceptance_driver_failure_after_start_and_completion_not_human_proof(self):
        for code in [0,1]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'manifest.json').write_text('{"owner":"/fixture"}')
                driver=Mock();driver.poll.side_effect=itertools.chain([None],itertools.repeat(code));driver.returncode=code
                with patch.object(guard,'apply'),patch.object(guard,'observe'),patch.object(guard.subprocess,'Popen',return_value=driver),patch.object(guard,'contain',return_value={u:dict(stopped=True) for u in guard.APPS}):
                    self.assertEqual(guard.execute(root,'fixture',['driver'],authorized=True,unlocked=True),code)
                state=json.loads((root/'operation-state.json').read_text());self.assertFalse(state['human_acceptance_claimed'])
                self.assertEqual(state['phase'],'failed-apps-stopped' if code else 'acceptance-command-completed')

    def test_observer_detects_owner_and_journal_failure(self):
        for kind in ['owner','journal']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'sessions').mkdir()
                if kind=='owner':(root/'checkpoint.json').write_text('{"phase":"chat-unknown"}')
                else:(root/'sessions/session.jsonl').write_text('CORRUPT\n')
                live=dict(ActiveState='active',SubState='running',MainPID='42',Job='',ControlGroup='')
                with patch.object(guard,'desktop_safe'),patch.object(guard,'check_moe_inert'),patch.object(guard,'unit_state',return_value=live):
                    with self.assertRaises((RuntimeError,ValueError)):guard.observe(root,dict(owner=str(root)),'fixture')


class MoeProfileGateTests(unittest.TestCase):
    def test_each_actual_and_legacy_profile_rejects_active_pid_or_queued_job(self):
        for unit in prepare.MOE_UNITS:
            for field,value in [('ActiveState','active'),('SubState','running'),('MainPID','42'),('Job','37 /job/37'),('NeedDaemonReload','yes')]:
                with self.subTest(unit=unit,field=field):
                    def metadata(*args,**kwargs):
                        state=dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='',NeedDaemonReload='no')
                        if args[3]==unit:state[field]=value
                        return '\n'.join(k+'='+v for k,v in state.items())
                    with patch.object(prepare,'run',side_effect=metadata):
                        with self.assertRaisesRegex(RuntimeError,'MoE profile'):prepare.check_moe_inert()

    def test_all_inert_and_snapshot_copy_never_opens_production_database(self):
        with patch.object(prepare,'run',return_value='ActiveState=inactive\nSubState=dead\nMainPID=0\nJob=\nNeedDaemonReload=no') as calls:
            prepare.check_moe_inert();self.assertEqual(calls.call_count,3)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);snapshot=root/'old.sqlite';snapshot.write_bytes(b'synthetic pinned backup')
            manifest=root/'manifest.json';manifest.write_text(json.dumps(dict(database=dict(path='/must-not-open-production',backup=str(snapshot),backup_sha256=prepare.digest(snapshot)))))
            with patch.object(prepare.sqlite3,'connect',side_effect=AssertionError('No SQLite open')):
                result=prepare.copy_database_snapshot(root,prepare.digest(manifest),Path('/must-not-open-production'),root/'copy.sqlite')
            self.assertFalse(result['current_database_read'])
            self.assertEqual(snapshot.read_bytes(),(root/'copy.sqlite').read_bytes())

class ActualApplyContainmentTests(unittest.TestCase):
    def test_real_apply_faults_after_each_start_and_installed_verification(self):
        import sqlite3
        for failure in ['hyprneuro.service','hyprneuro-ui.service','installed-verification']:
            with self.subTest(failure=failure),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'backup').mkdir()
                db=root/'fixture.sqlite'
                with closing(sqlite3.connect(db)) as conn:conn.execute('CREATE TABLE fixture (v)');conn.commit()
                binary=root/'candidate';binary.write_bytes(b'candidate')
                (root/'manifest.json').write_text(json.dumps(dict(database=dict(path=str(db)),binary=str(binary),installed_ui=str(root/'installed'),installed_mode=0o700,owner=str(root/'owner'))))
                (root/'sidecar-origin.json').write_text('{}')
                active=set();starts=[];stops=[]
                def control(command,**kwargs):
                    op=command[2]
                    if op=='start':
                        active.add(command[3]);starts.append(command[3])
                        if command[3]==failure:raise RuntimeError('Synthetic AFTER successful start')
                    elif op=='stop':
                        for unit in command[3:]:active.discard(unit);stops.append(unit)
                    return Mock(returncode=0)
                def verify(bundle,installed=False):
                    if installed and failure=='installed-verification':raise RuntimeError('Synthetic installed verification failure')
                def status(unit):
                    return dict(ActiveState='active' if unit in active else 'inactive',SubState='running' if unit in active else 'dead',MainPID='42' if unit in active else '0',Job='',ControlGroup='')
                with patch.object(apply,'verify',side_effect=verify),patch.object(apply,'release_targets',return_value=[]),patch.object(apply,'desktop_safe'),patch.object(guard.subprocess,'run',side_effect=control),patch.object(guard,'unit_state',side_effect=status):
                    self.assertEqual(guard.execute(root,'fixture',['never-started-driver'],authorized=True,unlocked=True),1)
                self.assertFalse(active)
                self.assertEqual(stops[-2:],list(guard.APPS))
                self.assertTrue(starts)
                state=json.loads((root/'operation-state.json').read_text())
                self.assertEqual(state['phase'],'failed-apps-stopped')
                self.assertTrue((root/'apply.started').exists());self.assertFalse((root/'apply.completed').exists())
                self.assertTrue(db.exists());self.assertTrue((root/'installed').exists())


class AcceptanceCoordinatorTests(unittest.TestCase):
    def test_operation_bound_results_timeout_and_stale_results(self):
        import wait_app_acceptance as waiter
        for result,expected in [('completed',0),('failed',1),('cancelled',1),('absent',1),('stale',None)]:
            with self.subTest(result=result),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);root.chmod(0o700)
                started=root/'operation.started';started.write_text('synthetic operation');started.chmod(0o600)
                if result!='absent':
                    target=root/'acceptance-result.json'
                    target.write_text(json.dumps(dict(operation_started_sha256='stale' if result=='stale' else prepare.digest(started),result=result)));target.chmod(0o600)
                if result=='stale':
                    with self.assertRaises(RuntimeError):waiter.wait(root,timeout=1)
                else:self.assertEqual(waiter.wait(root,timeout=.01),expected)


class OwnerExitObservationTests(unittest.TestCase):
    def test_owner_exit_with_last_ordinary_checkpoint_is_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'checkpoint.json').write_text('{"phase":"ordinary"}')
            live=dict(ActiveState='active',SubState='running',MainPID='42',Job='')
            dead=dict(ActiveState='inactive',SubState='dead',MainPID='0',Job='')
            with patch.object(guard,'desktop_safe'),patch.object(guard,'check_moe_inert'),patch.object(guard,'unit_state',side_effect=[live,live,dead]):
                with self.assertRaisesRegex(RuntimeError,'Native owner exited'):
                    guard.observe(root,dict(owner=str(root),owner_unit='synthetic-owner.service'),'fixture')
