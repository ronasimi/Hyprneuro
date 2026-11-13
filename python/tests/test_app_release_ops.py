"""Operator metadata/mode regressions; no services, GUI, model or consent calls."""
import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module
ops=load('prepare_app_release')
with patch.dict(sys.modules,{'prepare_app_release':ops}):
    verifier=load('verify_app_release')
    with patch.dict(sys.modules,{'verify_app_release':verifier}):
        apply=load('apply_app_release')


class ReleaseOpsTests(unittest.TestCase):
    def test_startup_proc_permission_race_retries_metadata_only(self):
        fields=f'MainPID={os.getpid()}\nActiveState=active\nFragmentPath=/synthetic.service\nDropInPaths='
        with patch.object(ops,'run',return_value=fields),patch.object(ops,'digest',side_effect=[PermissionError('exec pending'),'verified-hash']) as digest,patch.object(ops.time,'sleep') as sleep:
            result=ops.unit_identity('synthetic.service')
        self.assertEqual(result['pid'],os.getpid());self.assertEqual(result['exe_sha256'],'verified-hash')
        self.assertEqual(digest.call_count,2);sleep.assert_called_once_with(.02)

    def test_permanent_proc_denial_is_bounded_not_restart(self):
        fields=f'MainPID={os.getpid()}\nActiveState=active\nFragmentPath=/synthetic.service\nDropInPaths='
        with patch.object(ops,'run',return_value=fields) as run,patch.object(ops,'digest',side_effect=PermissionError('denied')) as digest,patch.object(ops.time,'sleep'):
            with self.assertRaises(PermissionError):ops.unit_identity('synthetic.service')
        self.assertEqual(digest.call_count,50);self.assertEqual(run.call_count,1)

    def test_explicit_legacy_mode_rejects_optin_or_stale_owner(self):
        with self.assertRaises(ValueError):verifier.verify(Path('/synthetic'),legacy=True)
        m={'owner':'/synthetic/owner','python':'/synthetic/python'}
        verifier.check_ui_mode({b'HYPRNEURO_PI_UI':b'0'},m,True)
        for env in [{},{b'HYPRNEURO_PI_UI':b'1'},{b'HYPRNEURO_PI_UI':b'0',b'HYPRNEURO_PI_OWNER_DIR':b'/synthetic/owner'}]:
            with self.assertRaises(RuntimeError):verifier.check_ui_mode(env,m,True)

    def test_owner_mode_cannot_pass_legacy_or_wrong_binding(self):
        m={'owner':'/synthetic/owner','python':'/synthetic/python'}
        good={b'HYPRNEURO_PI_UI':b'1',b'HYPRNEURO_PI_OWNER_DIR':b'/synthetic/owner',b'HYPRNEURO_PI_BRIDGE_PYTHON':b'/synthetic/python'}
        verifier.check_ui_mode(good,m,False)
        for env in [{b'HYPRNEURO_PI_UI':b'0'},{**good,b'HYPRNEURO_PI_OWNER_DIR':b'/wrong'},{**good,b'HYPRNEURO_PI_BRIDGE_PYTHON':b'/wrong'}]:
            with self.assertRaises(RuntimeError):verifier.check_ui_mode(env,m,False)

    def test_explicit_connect_ui_launch_ignores_startup_optin_but_requires_pinned_adapter(self):
        m={'explicit_ui':True,'python':'/synthetic/python'}
        good={b'HYPRNEURO_PI_UI':b'0',b'HYPRNEURO_PI_BRIDGE_PYTHON':b'/synthetic/python'}
        verifier.check_ui_mode(good,m,True)
        verifier.check_ui_mode(good,m,False)  # active mode is checked via real peer metadata
        for env in [{**good,b'HYPRNEURO_PI_UI':b'1'},{**good,b'HYPRNEURO_PI_OWNER_DIR':b'/stale'},{}]:
            with self.assertRaises(RuntimeError):verifier.check_ui_mode(env,m,True)

    def test_readonly_ui_metadata_bound_to_running_pid_no_control_or_permission_action(self):
        import socket
        import tempfile
        import threading
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'ui.sock'
            for expected in [os.getpid(),os.getpid()+100000]:
                with socket.socket(socket.AF_UNIX) as server:
                    server.bind(str(path));server.listen(1);received=[]
                    def serve():
                        with server.accept()[0] as client:
                            data=client.recv(1024);received.append(data)
                            if data:client.sendall(b'{"mode":"legacy","connected":false,"read_callable":false,"fresh_consent_required":true}\n')
                    thread=threading.Thread(target=serve);thread.start()
                    try:
                        if expected==os.getpid():self.assertEqual(verifier.ui_status(path,expected)['mode'],'legacy')
                        else:
                            with self.assertRaises(RuntimeError):verifier.ui_status(path,expected)
                    finally:thread.join(3)
                    self.assertFalse(thread.is_alive());self.assertIn(received[0],[b'pi-status\n',b''])
                path.unlink()


    def test_persistent_preparation_creates_private_descriptor_and_inert_template_only(self):
        import tempfile
        from hyprneuro.pi_owner_service import load_config
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);staged=base/'staged';staged.mkdir()
            task=ops.prepare_parent_owner(ROOT,base/'owner',Path(sys.executable),staged)
            config=load_config(base/'owner')
            self.assertEqual(config['task_id'],task)
            self.assertEqual(config['source'],str(ROOT))
            self.assertEqual(config['read_paths'],['fixture.txt'])
            self.assertEqual(list((base/'owner/home/workspace').iterdir()),[])
            self.assertFalse((base/'owner/owner.guard').exists())
            unit=(staged/'hyprneuro-pi-owner@.service').read_text()
            self.assertNotIn('[Install]',unit)
            self.assertIn('Restart=no',unit)
            self.assertEqual({p.name for p in staged.iterdir()},{'hyprneuro-pi-owner@.service'})

    def test_cutover_targets_preserve_only_verified_existing_app_override_and_inert_unit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);home=base/'units';home.mkdir()
            override=home/'hyprneuro-ui.service.d/95-reviewed-readonly-release.conf'
            override.parent.mkdir();override.write_text('current installed release')
            manifest={'persistent_owner':True,'units':[{'path':str(override),'sha256':ops.digest(override)}]}
            targets=apply.release_targets(base,manifest,home)
            self.assertEqual([dst for _,dst in targets],[home/'hyprneuro.service.d/95-reviewed-readonly-release.conf',override,home/'hyprneuro-pi-owner@.service'])
            self.assertEqual(override.read_text(),'current installed release')
            self.assertFalse(targets[-1][1].exists(),'Selection never installs or starts')
            override.write_text('unreviewed edit')
            with self.assertRaises(RuntimeError):apply.release_targets(base,manifest,home)
            override.unlink();override.symlink_to(base/'missing')
            with self.assertRaises(RuntimeError):apply.release_targets(base,manifest,home)
            override.unlink()
            owner=home/'hyprneuro-pi-owner@.service';owner.write_text('ambient unit')
            with self.assertRaises(RuntimeError):apply.release_targets(base,manifest,home)
            owner.unlink();owner.symlink_to(base/'missing')
            with self.assertRaises(RuntimeError):apply.release_targets(base,manifest,home)


    def test_app_cutover_installs_template_but_never_starts_or_enables_owner(self):
        import json
        import sqlite3
        import tempfile
        from contextlib import closing
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);staged=base/'staged';staged.mkdir();(base/'backup').mkdir()
            (base/'.config/systemd/user').mkdir(parents=True)
            for file in ['sidecar.conf','ui.conf','hyprneuro-pi-owner@.service']:
                (staged/file).write_text('reviewed '+file)
            binary=base/'candidate';binary.write_bytes(b'verified binary')
            db=base/'fixture.sqlite3'
            with closing(sqlite3.connect(db)) as conn:conn.execute('CREATE TABLE fixture (id)');conn.commit()
            manifest={'persistent_owner':True,'units':[],'database':{'path':str(db)},'binary':str(binary),
                      'installed_ui':str(base/'installed-ui'),'installed_mode':0o700}
            (base/'manifest.json').write_text(json.dumps(manifest));(base/'sidecar-origin.json').write_text('{}')
            argv=['apply',str(base),'--session','synthetic','--parent-authorized','--fresh-user-unlock-confirmed']
            with patch.object(sys,'argv',argv),patch.object(Path,'home',return_value=base),patch.object(apply,'desktop_safe'),patch.object(apply,'verify'),patch.object(apply.subprocess,'run') as run:
                apply.main()
            self.assertEqual([call.args[0] for call in run.call_args_list],[
                ['systemctl','--user','stop','hyprneuro-ui.service','hyprneuro.service'],
                ['systemctl','--user','daemon-reload'],
                ['systemctl','--user','start','hyprneuro.service'],
                ['systemctl','--user','start','hyprneuro-ui.service']])
            self.assertTrue((base/'.config/systemd/user/hyprneuro-pi-owner@.service').is_file())
            self.assertEqual(db.stat().st_size,(base/'backup/pre-apply.sqlite3').stat().st_size)
            self.assertTrue((base/'apply.completed').is_file())


    def test_installed_owner_unit_requires_exact_fragment_no_effective_dropins(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            unit=Path(directory)/'hyprneuro-pi-owner@.service';unit.write_text('reviewed template')
            sha=ops.digest(unit);instance='hyprneuro-pi-owner@synthetic.service'
            with patch.object(verifier,'run',return_value=f'FragmentPath={unit}\nDropInPaths=') as run:
                verifier.check_owner_unit(unit,sha,instance)
                self.assertEqual(run.call_args.args,('systemctl','--user','show',instance,'-p','FragmentPath','-p','DropInPaths'))
            for effective in [f'FragmentPath={unit}\nDropInPaths=/unexpected.conf',
                              'FragmentPath=/ambient.service\nDropInPaths=']:
                with patch.object(verifier,'run',return_value=effective):
                    with self.assertRaises(RuntimeError):verifier.check_owner_unit(unit,sha,instance)
            unit.write_text('unreviewed edit')
            with patch.object(verifier,'run') as run:
                with self.assertRaises(RuntimeError):verifier.check_owner_unit(unit,sha,instance)
                run.assert_not_called()
