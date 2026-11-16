"""Offline enum/capacity/site tests; NOT authority or human acceptance."""
import asyncio
import contextlib
import io
import json
import unittest
from unittest.mock import AsyncMock,patch
import identity_helper_fixture as fixture
from hyprneuro.trusted_control import GrantControlClient,OwnerRegistrationRejected
from hyprneuro.pi_managed_bridge import OwnerConnectError

class DiagnosticTests(unittest.IsolatedAsyncioTestCase):
    async def test_info_flood_cannot_consume_error_or_terminal_reservations(self):
        fixture._info=fixture._errors=0;fixture._terminal=False
        output=[]
        with patch.object(fixture.os,'write',side_effect=lambda fd,data:output.append(data)):
            for _ in range(300):fixture.emit('readhash','ok')
            for _ in range(300):fixture.emit('role-cohort','reject',PermissionError('SECRET_PATH_TOKEN'))
            for _ in range(300):fixture.emit('entry','terminal',PermissionError('SECRET_PATH_TOKEN'))
        records=[json.loads(line) for line in output]
        self.assertEqual(len(records),73)
        self.assertEqual(records[-1]['result'],'terminal')
        self.assertNotIn('SECRET',str(records));self.assertLess(sum(map(len,output)),16384)

    async def test_register_failure_sites_and_original_exception_preserved(self):
        for site in ['owner-challenge','challenge-frame','native-proof','registration-rpc','registration-frame']:
            client=object.__new__(GrantControlClient);client.registration=None
            original=PermissionError('SECRET_PATH_TOKEN')
            challenge={} if site=='challenge-frame' else {'nonce':'a'*64}
            registration={} if site=='registration-frame' else {'registration':'fixture'}
            client.call=AsyncMock(side_effect=[original if site=='owner-challenge' else challenge,
                                               original if site=='registration-rpc' else registration])
            control=type('Control',(),{'call':AsyncMock(side_effect=original if site=='native-proof' else None,return_value={})})()
            with self.assertRaises(OwnerRegistrationRejected) as caught:await client.register('/fixture',control)
            self.assertEqual(caught.exception.connect_diagnostic['site'],site)
            self.assertEqual(caught.exception.connect_diagnostic['category'],'permission')
            self.assertEqual(caught.exception.connect_diagnostic['error_class'],'PermissionError')
            self.assertNotIn('SECRET',str(caught.exception.connect_diagnostic))
            wrapped=OwnerConnectError('trusted-broker',caught.exception)
            self.assertEqual(wrapped.connect_diagnostic,caught.exception.connect_diagnostic)
            self.assertIsNone(client.registration)

    async def test_diagnostic_sink_failure_does_not_replace_original_failure(self):
        fixture._info=fixture._errors=0;fixture._terminal=False
        def fail():raise PermissionError('PRIVATE')
        with patch.object(fixture.os,'write',side_effect=BlockingIOError):
            with self.assertRaisesRegex(PermissionError,'PRIVATE'):fixture.sync_stage(fail,'readhash')()
