"""Managed control tests use synthetic consent only, never live GTK or models."""
import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from hyprneuro.pi_managed_bridge import ManagedDesktopBridge


class Guard:
    unlocked=True
    async def reconcile(self):return self.unlocked


class Client:
    def __init__(self,root,status=None):
        self.events=asyncio.Queue();self.read_task=asyncio.create_task(asyncio.sleep(3600));self.closed=False
        self.status=status or dict(persistent=True,parent_only=True,normal_only=True,tools=['read'],owner_phase='ordinary',state='unavailable',workspace=str(Path(root)/'home/workspace'),task_id='fixture',app_id='hyprneuro-parent-read',read_paths=[str(Path(root)/'home/workspace/fixture.txt')])
        self.calls=[]
    async def call(self,op,**fields):
        self.calls.append((op,fields))
        return self.status
    def disconnect(self):
        self.closed=True;self.read_task.cancel()
    async def close(self):
        self.disconnect();await asyncio.gather(self.read_task,return_exceptions=True)


class ManagedBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.packets=[];self.clients=[];self.starts=[];self.guard=Guard()
        async def connect(root,*,trusted=False):
            self.assertTrue(trusted);c=Client(root);self.clients.append(c);return c
        async def send(packet):self.packets.append(packet)
        async def start(root):self.starts.append(str(root));(Path(root)/'owner.sock').touch()
        self.bridge=ManagedDesktopBridge(send,connect=connect,guard=self.guard,start_service=start)
        self.validate=patch('hyprneuro.pi_managed_bridge.load_config',return_value={'task_id':'fixture','read_paths':['fixture.txt']});self.validate.start()
    async def asyncTearDown(self):
        await self.bridge.close();self.validate.stop();self.tmp.cleanup()

    async def test_default_legacy_idle_no_service_socket_or_inference_then_explicit_connect_disconnect_reconnect(self):
        self.assertEqual(self.clients,[]);self.assertEqual(self.starts,[])
        await self.bridge.request({'op':'chat','text':'never inferred'})
        self.assertEqual(self.clients,[])
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertEqual(len(self.starts),1);self.assertTrue(self.bridge.control)
        self.assertIn('connected',[p['type'] for p in self.packets])
        await self.bridge.request({'op':'disconnect'})
        self.assertTrue(self.clients[0].closed);self.assertIsNone(self.bridge.control)
        self.assertEqual(self.packets[-1]['type'],'disconnected')
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertEqual(len(self.starts),1,'existing idle owner, no new start/replay')
        self.assertEqual(len(self.clients),2)
        self.assertFalse(any(op in ('chat','consent','on','off') for c in self.clients for op,_ in c.calls))

    async def test_locked_connect_or_approval_refused_no_boot_or_grant(self):
        self.guard.unlocked=False
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertEqual(self.starts,[]);self.assertEqual(self.clients,[])
        self.assertEqual(self.packets[-1]['type'],'error')

    async def test_lock_drops_control_without_auto_legacy_reconnect_or_approval(self):
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.guard.unlocked=False
        async with asyncio.timeout(2):
            while not any(p['type']=='unavailable' for p in self.packets):await asyncio.sleep(.02)
        self.assertTrue(self.clients[0].closed);self.assertTrue(self.bridge.failed)
        self.assertNotIn('disconnected',[p['type'] for p in self.packets])
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertEqual(len(self.clients),1)
        await self.bridge.request({'op':'disconnect'})
        self.assertFalse(self.bridge.failed)
        self.assertEqual(self.packets[-1]['type'],'disconnected')

    async def test_wrong_owner_profile_no_adoption_and_failed_start_no_retry(self):
        async def wrong(root,*,trusted):
            c=Client(root);c.status['tools']=['read','bash'];self.clients.append(c);return c
        self.bridge.connect=wrong
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertTrue(self.clients[0].closed);self.assertIsNone(self.bridge.control)
        self.assertNotIn('connected',[p['type'] for p in self.packets])
        (self.root/'owner.sock').unlink();self.starts.clear()
        async def fail(root):self.starts.append(str(root));raise RuntimeError('unknown start outcome')
        self.bridge.start_service=fail
        await self.bridge.request({'op':'connect','root':str(self.root)})
        self.assertEqual(len(self.starts),1)

    async def test_unexpected_fields_never_become_service_or_consent_authority(self):
        await self.bridge.request({'op':'connect','root':str(self.root),'approved':True})
        self.assertEqual(self.starts,[])
        self.assertEqual(self.packets[-1]['type'],'error')
