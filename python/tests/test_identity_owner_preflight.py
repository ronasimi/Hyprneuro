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
