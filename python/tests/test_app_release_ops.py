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
