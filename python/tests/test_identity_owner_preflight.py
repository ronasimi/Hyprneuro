"""Offline binding parser/fence negatives, SYNTHETIC replies, not SDK proof."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock
from hyprneuro.trusted_control import GrantControlClient
from hyprneuro.identity_session import boottime_ns,MAX_PROOF_NS
from hyprneuro.pi_owner_service import SCHEMA

class BindingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.root.chmod(0o700)
        (self.root/'home/workspace').mkdir(parents=True,mode=0o700);(self.root/'home').chmod(0o700)
        self.config=dict(schema=SCHEMA,root=str(self.root),source='/fixture/source',node='/fixture/node',sdk='/fixture/sdk',durable='/fixture/durable',pi='/fixture/pi',read_paths=['fixture'],task_id='fixture')
        self.path=self.root/'owner.json';self.path.write_text(json.dumps(self.config));self.path.chmod(0o600)
        self.client=GrantControlClient(asyncio.StreamReader(),Mock(is_closing=lambda:False))
        self.client.finite_session=True;self.client.generation='a'*32
        self.client.deadline_ns=boottime_ns()+30_000_000_000
        async def call(op,**fields):
            self.assertEqual(op,'prepare_owner')
            return dict(request_id=fields['request_id'],generation=self.client.generation,expires_ns=boottime_ns()+MAX_PROOF_NS,
                        descriptor_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),descriptor_mode=0o600)
        self.reply=call;self.client.call=AsyncMock(side_effect=call)
    async def asyncTearDown(self):self.tmp.cleanup()
    async def test_exact_config_then_replacement_before_start_is_denied(self):
        config,check=await self.client.prepare_owner(str(self.root));self.assertEqual(config,self.config)
        old=self.path.read_bytes();self.path.unlink();self.path.write_bytes(old);self.path.chmod(0o600)
        # SAME bytes must not authorize a replacement between parse and launch.
        # The check must retain the initial path/inode identity as well as hash.
        with self.assertRaises(PermissionError):check()
    async def test_binding_expiry_generation_nonce_mode_and_alias_fail_closed(self):
        for field,value in [('expires_ns',0),('generation','b'*32),('request_id','b'*32),('descriptor_mode',0o644),('descriptor_sha256','f'*64)]:
            async def bad(op,**fields):
                result=await self.reply(op,**fields);result[field]=value;return result
            self.client.call=AsyncMock(side_effect=bad)
            with self.subTest(field=field),self.assertRaises(PermissionError):await self.client.prepare_owner(str(self.root))
        alias=self.root/'alias';alias.symlink_to(self.root,target_is_directory=True)
        self.client.call.reset_mock()
        with self.assertRaises(PermissionError):await self.client.prepare_owner(str(alias))
        self.client.call.assert_not_called()

    async def test_response_replay_and_hardlinked_descriptor_are_denied(self):
        saved=[]
        async def first(op,**fields):
            result=await self.reply(op,**fields);saved.append(result);return result
        self.client.call=AsyncMock(side_effect=first)
        await self.client.prepare_owner(str(self.root))
        self.client.call=AsyncMock(return_value=saved[0])
        with self.assertRaises(PermissionError):await self.client.prepare_owner(str(self.root))
        self.client.call=AsyncMock(side_effect=self.reply)
        os.link(self.path,self.root/'descriptor-alias')
        with self.assertRaises(PermissionError):await self.client.prepare_owner(str(self.root))

    async def test_last_read_expiry_blocks_actual_start_dispatcher_and_control_mac(self):
        from hyprneuro.identity_bootstrap import FilePin
        from hyprneuro.pi_managed_bridge import command
        from hyprneuro.pi_owner_client import PiOwnerClient
        from unittest.mock import patch
        original_read=FilePin.read
        for consumer in ['startup','control-mac']:
            for expiry in ['proof','connect','closed','generation','failed']:
                with self.subTest(consumer=consumer,expiry=expiry):
                    now=[boottime_ns()]
                    self.client.failed=False;self.client.generation='a'*32;self.client.writer.is_closing=lambda:False
                    self.client.deadline_ns=now[0]+(500 if expiry=='connect' else 2000)
                    async def response(op,**fields):
                        return dict(request_id=fields['request_id'],generation=self.client.generation,
                                    expires_ns=now[0]+1000,descriptor_mode=0o600,
                                    descriptor_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
                    self.client.call=AsyncMock(side_effect=response)
                    with patch('hyprneuro.identity_session.boottime_ns',side_effect=lambda:now[0]):
                        _,check=await self.client.prepare_owner(str(self.root))
                        def last_read(pin,**fields):
                            result=original_read(pin,**fields)
                            if expiry=='generation':self.client.generation='b'*32
                            elif expiry=='failed':self.client.failed=True
                            elif expiry=='closed':self.client.writer.is_closing=lambda:True
                            else:now[0]+=1000 if expiry=='proof' else 500
                            return result
                        process=Mock(returncode=0,communicate=AsyncMock(return_value=(b'',b'')))
                        spawn=AsyncMock(return_value=process)
                        if consumer=='startup':
                            with patch.object(FilePin,'read',last_read),patch('asyncio.create_subprocess_exec',spawn):
                                with self.assertRaises(PermissionError):await command('/fixture/start',preflight=AsyncMock(return_value=check))
                            spawn.assert_not_awaited()
                        else:
                            # Reach the REAL production CONTROL-MAC consumer:
                            # the third preflight is after the awaited nonce.
                            (self.root/'control.key').write_bytes(b'k'*32);(self.root/'control.key').chmod(0o600)
                            reader=Mock(readexactly=AsyncMock(return_value=b'n'*32),readline=AsyncMock(side_effect=ConnectionError('Fixture stops after forbidden MAC')))
                            writer=Mock(drain=AsyncMock(),wait_closed=AsyncMock())
                            calls=0
                            async def preflight():
                                nonlocal calls
                                calls+=1
                                return check if calls==3 else lambda:None
                            with patch.object(FilePin,'read',last_read),patch('asyncio.open_unix_connection',AsyncMock(return_value=(reader,writer))):
                                error=None
                                try:await PiOwnerClient.connect(self.root,trusted=True,preflight=preflight)
                                except Exception as failure:error=failure
                            writer.write.assert_not_called();self.assertIsInstance(error,PermissionError);self.assertEqual(calls,3)
                        self.client.writer.is_closing=lambda:False
