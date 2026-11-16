"""Finite no-frame idle vs bounded partial-frame; no GTK/real lifetime claim."""
import asyncio
import unittest
from hyprneuro.identity_session import boottime_ns
from hyprneuro.trusted_control import read_frame,MAX_FRAME

class Gate:
    def __init__(self,seconds=.5):self.deadline_ns=boottime_ns()+int(seconds*1e9);self.sealed=False
    def transport_alive(self):return not self.sealed and boottime_ns()<self.deadline_ns
    def seal(self):self.sealed=True

class IdleFrameTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_exceeds_frame_budget_then_completes(self):
        reader=asyncio.StreamReader();gate=Gate()
        task=asyncio.create_task(read_frame(reader,timeout=.02,session=gate))
        await asyncio.sleep(.04);self.assertFalse(task.done());reader.feed_data(b'{"op":"release"}\n')
        self.assertEqual(await task,{'op':'release'});self.assertFalse(gate.sealed)

    async def test_partial_frame_budget_starts_on_first_byte_not_each_byte(self):
        reader=asyncio.StreamReader();gate=Gate();reader.feed_data(b'{')
        task=asyncio.create_task(read_frame(reader,timeout=.03,session=gate))
        await asyncio.sleep(.02);reader.feed_data(b' ')
        with self.assertRaises(TimeoutError):await task
        self.assertTrue(gate.sealed)

    async def test_idle_deadline_and_legacy_timeout_are_still_bounded(self):
        gate=Gate(.02)
        with self.assertRaises(TimeoutError):await read_frame(asyncio.StreamReader(),session=gate)
        self.assertTrue(gate.sealed)
        with self.assertRaises(TimeoutError):await read_frame(asyncio.StreamReader(),timeout=.01)

    async def test_eof_malformed_oversize_and_cancel_seal(self):
        for data in [b'',b'{',b'[]\n',b'x'*(MAX_FRAME+1)+b'\n']:
            gate=Gate();reader=asyncio.StreamReader();reader.feed_data(data);reader.feed_eof()
            with self.subTest(data_length=len(data)),self.assertRaises((ValueError,TimeoutError)):
                await read_frame(reader,timeout=.01,session=gate)
            self.assertTrue(gate.sealed)
        gate=Gate();task=asyncio.create_task(read_frame(asyncio.StreamReader(),session=gate))
        await asyncio.sleep(0);task.cancel()
        with self.assertRaises(asyncio.CancelledError):await task
        self.assertTrue(gate.sealed)

    async def test_expiry_or_loss_during_last_await_refuses_complete_frame(self):
        for expire in (True,False):
            gate=Gate()
            class Reader:
                async def read(self,n):return b'{'
                async def readline(self):
                    if expire:gate.deadline_ns=boottime_ns()-1
                    else:gate.sealed=True
                    return b'"op":"release"}\n'
            with self.subTest(expire=expire),self.assertRaises(PermissionError):await read_frame(Reader(),session=gate)
            self.assertTrue(gate.sealed)

    async def test_expired_entry_seals_without_touching_reader(self):
        gate=Gate(-1)
        class Reader:
            async def read(self,n):raise AssertionError('Expired read attempted')
        with self.assertRaises(PermissionError):await read_frame(Reader(),session=gate)
        self.assertTrue(gate.sealed)
