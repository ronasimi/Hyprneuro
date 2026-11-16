"""Offline instrumentation sanity only; actual helper cases are separate."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock,Mock,patch
from hyprneuro import identity_transport
from identity_bridge_fixture import install_broker

class ProofPerturbationTests(unittest.TestCase):
    def test_received_packet_is_changed_in_place_once_after_real_validator(self):
        for case,field,value in [('proof-nonce','nonce','0'*64),('proof-generation','generation','0'*32),('proof-duplicate','seq',6)]:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);observations=[]
                def validate(client,packet,operation,expected):observations.append(dict(packet))
                with patch.object(identity_transport.ObserverClient,'_validate_snapshot',validate),patch.object(identity_transport,'_metadata',AsyncMock()),patch.object(asyncio,'sleep',asyncio.sleep):
                    install_broker(root,case,'hyprneuro-test-boundary-fixture-helper.service')
                    packet=dict(nonce='a'*64,generation='b'*32,seq=7)
                    identity_transport.ObserverClient._validate_snapshot(Mock(),packet,'decision',{})
                    self.assertEqual(observations[0],dict(nonce='a'*64,generation='b'*32,seq=7))
                    self.assertEqual(packet[field],value)
                    self.assertEqual((root/'fault-injected').read_text(),case)
                    packet2=dict(nonce='c'*64,generation='d'*32,seq=8);expected=dict(packet2)
                    identity_transport.ObserverClient._validate_snapshot(Mock(),packet2,'decision',{})
                    self.assertEqual(packet2,expected)
