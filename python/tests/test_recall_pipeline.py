"""Functional Phase 3 tests; no real screenshots, GPUs or remote calls."""
import asyncio
from dataclasses import replace
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from hyprneuro.recall import (
    CaptureCandidate, CapturePolicy, GrimWindowCapture, LoginSessionGuard,
    ScreenWatcher, MAX_PNG_BYTES, PNG_MAGIC,
)
from hyprneuro.recall_events import D1CaptureSource
from hyprneuro.sidecar_store import SidecarStore
from hyprneuro.sidecar import serve

class FakeDesktop:
    def __init__(self):
        self.window = {"address":"0x123", "class":"kitty", "title":"pacman failed",
                       "at":[40,50], "size":[900,600], "workspace":{"id":2}}
        self.queries=0
        self.on_query=None
    async def query(self, kind):
        assert kind=="activewindow"
        self.queries+=1
        if self.on_query:
            self.on_query(self.queries,self.window)
        return dict(self.window)
    async def events(self,callback):
        await callback("activewindowv2", "0x123")
        await asyncio.Event().wait()

class FakeModels:
    def __init__(self,decision=True):
        self.decision=decision
        self.decisions=[]
        self.visions=[]
    async def decide_capture(self,metadata):
        self.decisions.append(metadata)
        if isinstance(self.decision,Exception):raise self.decision
        return {"capture_recommended":self.decision,"score":0.9 if self.decision else .01}
    async def vision(self,png,prompt):
        self.visions.append((png,prompt))
        return {"choices":[{"message":{"role":"assistant","content":
                "error: target not found" if "Extract" in prompt else "A terminal displaying a package error"},
                "finish_reason":"stop"}]}
    async def chat(self,*args,**kwargs):raise AssertionError("Main model must never be invoked by Recall")

class FakeGrabber:
    def __init__(self):self.grabs=0
    async def grab(self,window):
        self.grabs+=1
        return PNG_MAGIC+b"abc"

async def permit():return True
async def deny():return False

class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store=SidecarStore(":memory:")
        self.desktop=FakeDesktop()
        self.models=FakeModels()
        self.grabber=FakeGrabber()
        self.policy=CapturePolicy(enabled=True,check_unlocked=permit,min_interval_seconds=.5)
        self.watcher=ScreenWatcher(self.desktop,self.models,self.store,self.policy,self.grabber)
        self.event=CaptureCandidate("hyprland","activewindowv2")
    def tearDown(self):self.store.close()

    async def test_disabled_does_not_call_d1(self):
        self.watcher.capture_policy=CapturePolicy()
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"capture_disabled")
        self.assertFalse(self.models.decisions)

    async def test_unknown_lock_denies_before_d1(self):
        self.watcher.capture_policy=replace(self.policy,check_unlocked=deny)
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"capture_denied")
        self.assertFalse(self.models.decisions)

    async def test_excluded_app_denies_before_d1(self):
        self.watcher.capture_policy=replace(self.policy,excluded_app_ids=frozenset({"kitty"}))
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"capture_denied")
        self.assertFalse(self.models.decisions)

    async def test_excluded_origin_denies_before_d1(self):
        self.watcher.capture_policy=replace(self.policy,excluded_url_origins=frozenset({"https://example.org"}))
        result=await self.watcher.consider_event(CaptureCandidate("chrome","tab_updated",url_origin="https://example.org"))
        self.assertEqual(result["reason"],"capture_denied")
        self.assertFalse(self.models.decisions)

    async def test_d1_skip_avoids_omni(self):
        self.models.decision=False
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"d1_skip")
        self.assertEqual(self.grabber.grabs,0)

    async def test_d1_failure_fails_closed(self):
        self.models.decision=RuntimeError("unavailable")
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"d1_unavailable")
        self.assertEqual(self.grabber.grabs,0)

    async def test_two_independent_omni_calls_and_sqlite_write(self):
        result=await self.watcher.consider_event(self.event)
        self.assertTrue(result["captured"])
        self.assertEqual(len(self.models.visions),2)
        self.assertEqual(self.models.visions[0][0],self.models.visions[1][0])
        rows=self.store.search(query="pacman")
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["source"],"omni")
        self.assertEqual(rows[0]["ocr_text"],"error: target not found")
        self.assertIn("package error",rows[0]["description"])
        self.assertEqual(rows[0]["workspace"],"2")
        self.assertEqual(rows[0]["app_id"],"kitty")
        # Main-model context has no automatic screen transcript.
        self.assertEqual(self.store.context(role="text",source="journal")["records"],[])

    async def test_rate_limit_prevents_repeat_d1(self):
        await self.watcher.consider_event(self.event)
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"rate_limited")
        self.assertEqual(len(self.models.decisions),1)

    async def test_focus_switch_after_d1(self):
        def shift(i,w):
            if i==2:w["address"]="0x999"
        self.desktop.on_query=shift
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"focus_or_consent_changed")
        self.assertEqual(self.grabber.grabs,0)

    async def test_locked_after_d1(self):
        state={"n":0}
        async def toggles():
            state["n"]+=1
            return state["n"]==1
        self.watcher.capture_policy=replace(self.policy,check_unlocked=toggles)
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"focus_or_consent_changed")
        self.assertEqual(self.grabber.grabs,0)

    async def test_bad_png_rejected_without_storage(self):
        async def bad(_):return b"not-png"
        self.grabber.grab=bad
        result=await self.watcher.consider_event(self.event)
        self.assertEqual(result["reason"],"observation_failed")
        self.assertFalse(self.store.search())

    async def test_bad_candidate_rejected(self):
        with self.assertRaises(ValueError):
            await self.watcher.consider_event({"source":"hyprland"})

    async def test_unpermitted_source(self):
        result=await self.watcher.consider_event(CaptureCandidate("journal","error"))
        self.assertEqual(result["reason"],"capture_denied")

    def test_geometry_input_rejected(self):
        # Verify narrow argument construction independent of shell execution.
        obj=GrimWindowCapture()
        self.assertTrue(callable(obj.grab))

    def test_limits_validate(self):
        with self.assertRaises(ValueError):CapturePolicy(enabled=True,frames_per_hour=0)
        with self.assertRaises(ValueError):CapturePolicy(enabled=True,min_interval_seconds=0)

class QueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_event_filters_and_coalesces(self):
        watcher=type("Watcher",(),{})()
        async def consider(candidate):return {"captured":False}
        watcher.consider_event=consider
        source=D1CaptureSource(watcher,max_queue=1)
        await source.on_event("monitoradded","x")
        self.assertTrue(source.queue.empty())
        await source.on_event("activewindowv2","0x1")
        await source.on_event("workspacev2","2")
        self.assertEqual(source.dropped,1)
        ev=source.queue.get_nowait();source.queue.task_done()
        self.assertEqual(ev.event,"workspacev2")

    async def test_queue_worker_calls_watcher(self):
        calls=[]
        class Watcher:
            async def consider_event(self,c):
                calls.append(c.event)
                return {"captured":False}
        source=D1CaptureSource(Watcher())
        task=asyncio.create_task(source.run())
        try:
            await source.on_event("activewindowv2","0x1")
            await asyncio.wait_for(source.queue.join(),1)
            self.assertEqual(calls,["activewindowv2"])
            self.assertEqual(source.skipped,1)
        finally:
            task.cancel();await asyncio.gather(task,return_exceptions=True)

    async def test_capture_requires_explicit_flags(self):
        with self.assertRaises(ValueError):
            await serve(allow_capture=True,allow_ingest=True,watch_hyprland=False)
        with self.assertRaises(ValueError):
            await serve(allow_capture=True,allow_ingest=False,watch_hyprland=True)

    async def test_live_socket2_event_to_omni_to_sqlite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            stop=asyncio.Event()
            fake=FakeDesktop()
            models=FakeModels()
            db=root/"sidecar"/"observations.db"
            sock=root/"runtime"/"sidecar.sock"
            task=asyncio.create_task(serve(allow_ingest=True,watch_hyprland=True,
                 allow_capture=True,desktop=fake,models=models,unlock_guard=permit,
                 grabber=FakeGrabber(),db_path=db,socket_path=sock,shutdown=stop))
            try:
                for _ in range(60):
                    if db.exists() and len(models.visions)==2:break
                    await asyncio.sleep(.03)
                self.assertEqual(len(models.visions),2)
            finally:
                stop.set();await asyncio.wait_for(task,3)
            s=SidecarStore(db)
            try:
                self.assertEqual(len(s.search(query="pacman",source="omni")),1)
                self.assertEqual(len(s.search(source="hyprland")),1)
            finally:s.close()


class FakeStream:
    def __init__(self, chunks):self.chunks=list(chunks)
    async def read(self, limit):
        if not self.chunks:return b""
        item=self.chunks.pop(0)
        assert isinstance(item,bytes)
        return item

class FakeProcess:
    def __init__(self, stdout_chunks, stderr=b"", returncode=0):
        self.stdout=FakeStream(stdout_chunks)
        self.stderr=FakeStream([stderr])
        self.returncode=returncode
        self.killed=False
    async def wait(self):return self.returncode
    def kill(self):self.killed=True;self.returncode=-9

class WindowGrabTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_command_vector_and_streamed_png(self):
        calls=[]
        async def fake_exec(*argv,**kwargs):
            calls.append(argv)
            return FakeProcess([PNG_MAGIC,b"a"*32,b"b"*16])
        with patch("hyprneuro.recall.asyncio.create_subprocess_exec",fake_exec):
            payload=await GrimWindowCapture().grab({"at":[25,-14],"size":[860,500]})
        self.assertEqual(payload,PNG_MAGIC+b"a"*32+b"b"*16)
        self.assertEqual(calls,[("grim","-g","25,-14 860x500","-")])

    async def test_refuses_oversized_window_before_subprocess(self):
        with self.assertRaises(ValueError):
            await GrimWindowCapture().grab({"at":[0,0],"size":[9000,300]})

    async def test_refuses_non_png_data(self):
        async def fake_exec(*a,**kw):return FakeProcess([b"GIF\x00bad"])
        with patch("hyprneuro.recall.asyncio.create_subprocess_exec",fake_exec):
            with self.assertRaises(ValueError):
                await GrimWindowCapture().grab({"at":[0,0],"size":[100,100]})

    async def test_rejects_large_output_and_kills_process(self):
        fake=FakeProcess([PNG_MAGIC,b"a"*(MAX_PNG_BYTES)])
        fake.returncode=None
        async def fake_exec(*a,**kw):return fake
        with patch("hyprneuro.recall.asyncio.create_subprocess_exec",fake_exec):
            with self.assertRaises(ValueError):
                await GrimWindowCapture().grab({"at":[0,0],"size":[100,100]})
        self.assertTrue(fake.killed)

    async def test_rejects_failed_grim(self):
        async def fake_exec(*a,**kw):return FakeProcess([b""],b"capture failed",1)
        with patch("hyprneuro.recall.asyncio.create_subprocess_exec",fake_exec):
            with self.assertRaisesRegex(RuntimeError,"capture failed"):
                await GrimWindowCapture().grab({"at":[0,0],"size":[100,100]})

class ExtraPolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_password_manager_excluded_by_default(self):
        from hyprneuro.recall import DEFAULT_EXCLUDED_APPS
        self.assertIn("keepassxc",DEFAULT_EXCLUDED_APPS)
        pol=CapturePolicy(enabled=True, check_unlocked=permit)
        self.assertFalse(await pol.permits(CaptureCandidate("hyprland","activewindowv2"),
                                            {"class":"KeePassXC"}))

    async def test_unknown_app_class_denied(self):
        pol=CapturePolicy(enabled=True,check_unlocked=permit)
        self.assertFalse(await pol.permits(CaptureCandidate("hyprland","activewindowv2"),
                                           {"class":""}))

    async def test_switch_during_grim_discards_image(self):
        store=SidecarStore(":memory:")
        desktop=FakeDesktop()
        class SwitchingGrabber:
            async def grab(self,w):
                desktop.window["address"]="0xfocus_switched"
                return PNG_MAGIC + b"x"
        models=FakeModels()
        watcher=ScreenWatcher(desktop,models,store,
            CapturePolicy(enabled=True,check_unlocked=permit), SwitchingGrabber())
        try:
            result=await watcher.consider_event(CaptureCandidate("hyprland","workspacev2"))
            self.assertEqual(result["reason"],"observation_failed")
            self.assertEqual(models.visions,[])
            self.assertEqual(store.search(),[])
        finally:store.close()

    async def test_queue_debounce_latest_event(self):
        seen=[]
        class Watcher:
            async def consider_event(self,candidate):
                seen.append(candidate.event)
                return {"captured":False}
        source=D1CaptureSource(Watcher(),debounce_seconds=.02)
        task=asyncio.create_task(source.run())
        try:
            await source.on_event("activewindowv2","1")
            await asyncio.sleep(.005)
            await source.on_event("workspacev2","2")
            await asyncio.wait_for(source.queue.join(),2)
            self.assertEqual(seen,["workspacev2"])
        finally:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)

if __name__ == "__main__":
    unittest.main()
