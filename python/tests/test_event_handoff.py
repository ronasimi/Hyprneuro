"""Functional tests for foreground scheduling, visual D1 and Pi-to-Omni IPC."""
from __future__ import annotations
import asyncio
from dataclasses import replace
from io import BytesIO
import struct
import zlib
import os
from pathlib import Path
import tempfile
import unittest
try:
    from PIL import Image
except ImportError:
    Image = None

from hyprharness_sidecar.model_dispatch import ModelLane, ScheduledModels
from hyprharness_sidecar.d1_visual import decide_visual, preview_png
from hyprharness_sidecar.recall import CaptureCandidate, CapturePolicy, ScreenWatcher, PNG_MAGIC
from hyprharness_sidecar.sidecar_store import SidecarStore
from hyprharness_sidecar.sidecar import serve
from hyprharness_sidecar.sidecar_client import request
from hyprharness_sidecar.temporary_capture import capture_output, remove_screenshot, PREFIX


def picture():
    """Valid PNG from the standard library, even when Pillow is absent."""
    width, height = 1100, 850
    raw = (b"\0" + bytes((100, 110, 120)) * width) * height
    def chunk(kind, payload):
        return (struct.pack("!I", len(payload)) + kind + payload +
                struct.pack("!I", zlib.crc32(kind + payload) & 0xffffffff))
    return (PNG_MAGIC + chunk(b"IHDR", struct.pack("!IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class DecisionStub:
    def __init__(self, score=0.9):
        self.score=score
        self.calls=[]
    async def call(self, role, endpoint, payload):
        self.calls.append((role, endpoint, payload))
        return {"answers":{"visual_delta":{"noul":self.score}}}


class LaneTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_admission_precedes_pending_background(self):
        lane=ModelLane("test")
        active=asyncio.Event()
        release=asyncio.Event()
        order=[]
        async def first():
            order.append("running-background"); active.set(); await release.wait()
            return "first"
        async def follow(name):
            order.append(name); return name
        start=lane.submit(first, key="first")
        await asyncio.wait_for(active.wait(),1)
        bg=lane.submit(lambda: follow("queued-background"), key="more")
        fg=lane.submit(lambda: follow("foreground"),foreground=True)
        release.set()
        try:
            self.assertEqual(await fg,"foreground")
            self.assertEqual(await bg,"queued-background")
            self.assertEqual(await start,"first")
            self.assertEqual(order,["running-background", "foreground", "queued-background"])
        finally:await lane.stop()

    async def test_background_coalescing_and_bounded_queue(self):
        lane=ModelLane("tiny",max_background=1)
        busy=asyncio.Event(); release=asyncio.Event()
        async def running():busy.set();await release.wait()
        first=lane.submit(running, key="start")
        await busy.wait()
        old=lane.submit(lambda: asyncio.sleep(0),key="same")
        new=lane.submit(lambda: asyncio.sleep(0),key="same")
        self.assertIsNone(await old)
        self.assertEqual(lane.coalesced,1)
        replaced=lane.submit(lambda: asyncio.sleep(0),key="other")
        self.assertIsNone(await new)
        self.assertEqual(lane.dropped,1)
        release.set()
        await first;await replaced
        await lane.stop()

    async def test_wait_timeout_does_not_block_event_loop(self):
        lane=ModelLane("timeout")
        try:
            async def blocked():await asyncio.sleep(1)
            with self.assertRaises(asyncio.TimeoutError):
                await lane.request(blocked,foreground=True,timeout=.03)
            # No compositor state or GTK event loop is blocked by pending D1.
            self.assertTrue(asyncio.get_running_loop().is_running())
        finally:await lane.stop()

    async def test_stop_cancels_pending(self):
        lane=ModelLane("stop")
        active=asyncio.Event()
        async def sleep():active.set();await asyncio.sleep(2)
        running=lane.submit(sleep)
        await active.wait()
        pending=lane.submit(sleep,foreground=True)
        await lane.stop()
        self.assertTrue(pending.cancelled())
        self.assertTrue(running.cancelled())


class VisualTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipUnless(Image is not None, "Pillow optional for d1 visual gate")
    async def test_d1_preview_stays_small_and_uses_image_data_url(self):
        original=picture()
        m=DecisionStub()
        result=await decide_visual(m,original,{"source":"hyprland","event":"activewindowv2",
                                              "app_id":"kitty", "url":"https://example.test/?private=1"})
        self.assertTrue(result["capture_recommended"])
        self.assertLess(result["preview_bytes"], len(original))
        role,path,payload=m.calls[0]
        self.assertEqual((role,path),("decision","/v1/systemone"))
        self.assertTrue(payload["images"][0].startswith("data:image/png;base64,"))
        self.assertNotIn("private=1",str(payload))
        from base64 import b64decode
        frame=b64decode(payload["images"][0].split(",",1)[1])
        with Image.open(BytesIO(frame)) as im:
            self.assertLessEqual(max(im.size),512)

    async def test_visual_skip_does_not_call_omni(self):
        from test_recall_pipeline import FakeDesktop, FakeGrabber, FakeModels, permit
        class VisualModels(FakeModels):
            def __init__(self):super().__init__();self.visuals=0
            async def decide_visual(self,png,details):
                self.visuals+=1
                return {"capture_recommended":False,"score":.1}
        store=SidecarStore(":memory:")
        try:
            models=VisualModels()
            watcher=ScreenWatcher(FakeDesktop(),models,store,
                CapturePolicy(enabled=True,visual_d1=True,check_unlocked=permit),FakeGrabber())
            result=await watcher.consider_event(CaptureCandidate("hyprland","workspacev2"))
            self.assertEqual(result["reason"],"d1_visual_skip")
            self.assertEqual(models.visuals,1)
            self.assertEqual(models.visions,[])
            self.assertEqual(store.search(),[])
        finally:store.close()

    async def test_duplicate_frame_avoids_second_visual_pass(self):
        from test_recall_pipeline import FakeDesktop, FakeGrabber, FakeModels, permit
        store=SidecarStore(":memory:")
        try:
            models=FakeModels()
            watcher=ScreenWatcher(FakeDesktop(),models,store,
                CapturePolicy(enabled=True,check_unlocked=permit),FakeGrabber())
            await watcher.consider_event(CaptureCandidate("hyprland","workspacev2"))
            watcher._last_capture = -999.0
            result=await watcher.consider_event(CaptureCandidate("hyprland","workspacev2"))
            self.assertEqual(result["reason"],"identical_frame")
            self.assertEqual(len(models.visions),2)
        finally:store.close()


class ForegroundTests(unittest.IsolatedAsyncioTestCase):
    async def test_foreground_ipc_returns_only_requested_short_context(self):
        from test_recall_pipeline import FakeDesktop, FakeGrabber, FakeModels, permit
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            sock=root/"runtime"/"sidecar.sock"
            db=root/"state"/"observations.sqlite3"
            stop=asyncio.Event()
            models=FakeModels()
            service=asyncio.create_task(serve(allow_ingest=True,allow_on_demand=True,
                    socket_path=sock,db_path=db,models=models,desktop=FakeDesktop(),
                    unlock_guard=permit,grabber=FakeGrabber(),shutdown=stop))
            try:
                for _ in range(100):
                    if sock.exists():break
                    await asyncio.sleep(.01)
                reply=await request({"action":"omni_observe","purpose":"describe"},
                                    socket_path=sock,timeout=10)
                self.assertEqual(reply["source"],"omni")
                self.assertIn("package error", reply["description"])
                self.assertNotIn("ocr_excerpt",reply)
                self.assertEqual(len(models.visions),2)
                self.assertEqual(list(root.rglob("*.png")),[])
            finally:
                stop.set();await asyncio.wait_for(service,5)

    async def test_disabled_foreground_rejects_without_capture(self):
        from hyprharness_sidecar.sidecar import SidecarServer
        store=SidecarStore(":memory:")
        try:
            server=SidecarServer(store,allow_ingest=True)
            with self.assertRaises(PermissionError):
                await server.dispatch_async({"action":"omni_observe","purpose":"both"})
        finally:store.close()


class TempCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_tmp_capture_and_del_after_use(self):
        async def fake_grim(argv,timeout):
            self.assertEqual(argv[0],"grim")
            Path(argv[-1]).write_bytes(picture())
        path=await capture_output("eDP-1",fake_grim)
        self.assertEqual(path.parent,Path("/tmp"))
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        try:self.assertTrue(path.read_bytes().startswith(PNG_MAGIC))
        finally:remove_screenshot(path)
        self.assertFalse(path.exists())

    async def test_tmp_cleanup_on_exception(self):
        paths=[]
        async def failure(argv,timeout):
            paths.append(Path(argv[-1]));raise RuntimeError("grim failed")
        with self.assertRaises(RuntimeError):await capture_output("eDP-1",failure)
        self.assertFalse(paths[0].exists())

    async def test_tmp_cleanup_on_cancel(self):
        paths = []
        started = asyncio.Event()
        async def blocked(argv, timeout):
            paths.append(Path(argv[-1]))
            started.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(capture_output("eDP-1", blocked))
        try:
            await asyncio.wait_for(started.wait(), 1)
            self.assertTrue(paths[0].exists())
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        self.assertFalse(paths[0].exists())
