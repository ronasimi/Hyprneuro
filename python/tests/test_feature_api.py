import asyncio
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.event_stream import EventIntake, MonitorEvent
from hyprneuro.settings import Settings
from hyprneuro.sidecar import serve
from hyprneuro.sidecar_client import request
from test_alerting import _FakeModels


class FeatureApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_granular_collectors_without_notifications_and_status_details(self):
        calls = []
        emitted = asyncio.Event()
        async def network(intake, deliver):
            calls.append('network')
            await deliver(MonitorEvent('network','network_alert','link down','error','now'))
            emitted.set()
            await asyncio.Event().wait()
        async def resources(intake, deliver):
            calls.append('resources')
            await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sock = root/'runtime/sidecar.sock'
            stop = asyncio.Event()
            with patch.object(EventIntake,'network_alerts',network), patch.object(EventIntake,'resource_alerts',resources), \
                 patch.object(EventIntake,'follow_journal') as journal, patch('hyprneuro.notify.Notifier') as notifier:
                task = asyncio.create_task(serve(allow_ingest=True,alert_network=True,alert_resources=True,
                    models=_FakeModels(),socket_path=sock,db_path=root/'state/log.db',shutdown=stop))
                try:
                    await asyncio.wait_for(emitted.wait(),2)
                    health = await request({'action':'health'},socket_path=sock)
                    self.assertTrue(health['active_settings']['alert_network'])
                    self.assertFalse(health['active_settings']['alert_journal'])
                    self.assertFalse(health['active_settings']['notifications'])
                    self.assertEqual(health['collectors'],{'network':'running','resources':'running'})
                    rows = await request({'action':'alerts'},socket_path=sock)
                    self.assertEqual(rows[0]['notification_status'],'disabled')
                    detail = await request({'action':'details','id':rows[0]['id']},socket_path=sock)
                    self.assertEqual(detail['alert_state']['d1_score'],.9)
                    self.assertTrue(detail['untrusted'])
                    notifier.assert_not_called()
                    journal.assert_not_called()
                finally:
                    stop.set()
                    await asyncio.wait_for(task,2)

    async def test_semantic_startup_probe_failure_and_truthful_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sock = root/'runtime/sidecar.sock'
            stop = asyncio.Event()
            async def embed(client, texts):
                return [[1.,0.] for _ in texts]
            with patch('hyprneuro.semantic.Embeddings.embed',embed):
                task = asyncio.create_task(serve(semantic_enabled=True, embeddings_url='http://127.0.0.1:9000/v1/embeddings',
                    embeddings_model='real-embedding-id',socket_path=sock,db_path=root/'state/log.db',shutdown=stop))
                try:
                    for _ in range(100):
                        if sock.exists(): break
                        await asyncio.sleep(.01)
                    health = await request({'action':'health'},socket_path=sock)
                    self.assertNotIn('models_invoked',health)
                    self.assertFalse(health['ingest_enabled'])
                    rows = await request({'action':'search','semantic':True,'query':'hi'},socket_path=sock)
                    self.assertEqual(rows,[])
                finally:
                    stop.set()
                    await asyncio.wait_for(task,2)
            with patch('hyprneuro.semantic.Embeddings.embed',side_effect=RuntimeError('Local embeddings unavailable')):
                with self.assertRaisesRegex(RuntimeError,'unavailable'):
                    await serve(semantic_enabled=True,embeddings_url='http://127.0.0.1:9000/v1/embeddings',
                        embeddings_model='real-id',socket_path=sock,db_path=root/'state/log.db')
            self.assertFalse(sock.exists())

    async def test_actual_cli_subprocess_config_overrides_rpc_and_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root/'config/settings.json'
            Settings(allow_ingest=True).save(settings)
            env = {**os.environ,'XDG_RUNTIME_DIR':tmp,'XDG_STATE_HOME':tmp,
                   'PYTHONPATH':str(Path(__file__).resolve().parents[1]/'src')}
            proc = await asyncio.create_subprocess_exec(sys.executable,'-m','hyprneuro','serve','--config',str(settings),
                '--no-allow-ingest',env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            sock = root/'hyprharness/sidecar.sock'
            try:
                for _ in range(100):
                    if sock.exists(): break
                    await asyncio.sleep(.01)
                health = await request({'action':'health'},socket_path=sock)
                self.assertFalse(health['ingest_enabled'])
                self.assertEqual(health['settings_file'],str(settings))
                self.assertEqual(health['collectors'],{})
                with self.assertRaisesRegex(RuntimeError,'disabled'):
                    await request({'action':'record','event':{}},socket_path=sock)
            finally:
                if proc.returncode is None:
                    proc.terminate()
                stdout, stderr = await asyncio.wait_for(proc.communicate(),3)
            self.assertEqual(proc.returncode,0,stderr.decode())
            self.assertFalse(sock.exists())
