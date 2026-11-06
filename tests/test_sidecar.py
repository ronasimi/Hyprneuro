"""Functional tests only; no model benchmarks, network or real screenshots."""
import asyncio
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import time
import unittest
from zoneinfo import ZoneInfo

from hyprharness_sidecar.sidecar import serve
from hyprharness_sidecar.sidecar_client import request
from hyprharness_sidecar.sidecar_store import SidecarStore

NOW = int(time.time() * 1000)


def event(**overrides):
    value = {"source": "chrome", "kind": "tab_activated", "time_ms": NOW - 60_000,
             "title": "Arch Linux Wiki — Btrfs", "app_id": "chromium", "workspace": "2",
             "url": "https://wiki.archlinux.org/title/Btrfs?section=2#snapshots"}
    value.update(overrides)
    return value


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "private" / "observations.sqlite3"
        self.store = SidecarStore(self.path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_file_permissions(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

    def test_persistence_and_exact_url_provenance(self):
        result = self.store.record(event())
        self.assertTrue(result["stored"])
        self.assertFalse(result["deduplicated"])
        page = self.store.search(query="Btrfs")[0]
        self.assertEqual(page["source"], "chrome")
        self.assertTrue(page["url_available"])
        self.assertFalse(page["url_verified"])
        self.assertEqual(page["url_preview"], "https://wiki.archlinux.org/title/Btrfs")
        with self.assertRaises(LookupError):
            self.store.page_url(result["id"])  # Untrusted generic IPC cannot grant URL restore.
        self.store.close()
        self.store = SidecarStore(self.path)
        self.assertEqual(len(self.store.search(query="Btrfs")), 1)

    def test_internal_authenticated_browser_url(self):
        result = self.store.record(event(title="Test page"), _trusted_browser=True)
        exact = self.store.page_url(result["id"])
        self.assertEqual(exact["url"], event()["url"])
        self.assertTrue(exact["requires_approval"])

    def test_fts_and_time_windows(self):
        late = NOW - 60_000
        early = NOW - 6 * 60 * 60 * 1000
        self.store.record(event(time_ms=early, title="Old Rust docs",
                                url="https://doc.rust-lang.org/book/"))
        self.store.record(event(time_ms=late, title="New Arch docs"))
        self.assertEqual(len(self.store.search(query="Rust")), 1)
        self.assertEqual(len(self.store.search(start_ms=early + 1, end_ms=NOW)), 1)
        self.assertEqual(self.store.search(start_ms=NOW - 10_000), [])
        self.assertEqual(len(self.store.search(source="chrome")), 2)
        with self.assertRaises(ValueError):
            self.store.search(start_ms=NOW, end_ms=early)

    def test_last_night_local_time_query(self):
        # Time parsing/routing is a separate phase; the DB accepts exact Unix ms.
        zone = ZoneInfo("America/Toronto")
        start = int(datetime(2026, 11, 4, 18, tzinfo=zone).timestamp() * 1000)
        end = int(datetime(2026, 11, 5, 6, tzinfo=zone).timestamp() * 1000)
        self.store.record(event(time_ms=start + 3600_000, title="The site from last night"))
        other_time = int(datetime(2026, 11, 5, 8, tzinfo=zone).timestamp() * 1000)
        self.store.record(event(time_ms=other_time, title="Morning site"))
        rows = self.store.search(start_ms=start, end_ms=end)
        self.assertEqual([r["title"] for r in rows], ["The site from last night"])

    def test_malicious_urls_and_incognito(self):
        for bad in ("javascript:alert(1)", "file:///etc/passwd", "http://user:secret@site.test/",
                    "https://site.test/\nInjected", "https://[invalid/"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                self.store.record(event(url=bad))
        self.assertFalse(self.store.record(event(incognito=True))["stored"])
        self.assertEqual(self.store.search(), [])
        with self.assertRaises(ValueError):
            self.store.record(event(source="hyprland", url=event()["url"]))

    def test_rejects_arbitrary_fields_and_empty_records(self):
        with self.assertRaises(ValueError):
            self.store.record(event(url_verified=True))
        with self.assertRaises(ValueError):
            self.store.record(event(url=None, title="", message="", description="", ocr_text=""))
        with self.assertRaises(ValueError):
            self.store.record(event(time_ms=NOW + 10_000_000))

    def test_fts_injection_and_unicode(self):
        self.store.record(event(source="omni", kind="ocr", url=None,
                                ocr_text="écran 汉字 package installation error"))
        self.assertEqual(len(self.store.search(query="汉字")), 1)
        self.assertEqual(self.store.search(query='" OR * NEAR DROP SELECT --'), [])

    def test_deduplication_and_fts_trigger(self):
        first = self.store.record(event(source="journal", kind="warning", url=None,
                                        title="", message="Repeated Btrfs warning", event_key="btrfs-03"))
        second = self.store.record(event(source="journal", kind="warning", url=None,
                                         title="", message="Repeated Btrfs warning", event_key="btrfs-03",
                                         time_ms=NOW - 58_000))
        self.assertEqual(first["id"], second["id"])
        row = self.store.search(query="warning")[0]
        self.assertEqual(row["repeat_count"], 2)
        self.assertEqual(row["last_seen_ms"], NOW - 58_000)
        self.assertEqual(self.store.prune(before_ms=NOW - 57_000)["deleted"], 1)
        self.assertEqual(self.store.search(query="warning"), [])

    def test_context_role_limits_and_provenance(self):
        for i in range(12):
            self.store.record(event(source="omni", kind="description", url=None,
                                    title=f"App {i}", ocr_text="S" * 8000,
                                    description="D" * 4000, time_ms=NOW - i * 10_000))
        text_packet = self.store.context(role="text", query="App")
        omni_packet = self.store.context(role="omni", query="App")
        self.assertTrue(text_packet["untrusted"] and omni_packet["untrusted"])
        self.assertLessEqual(len(str(text_packet)), 4500)
        self.assertLessEqual(len(str(omni_packet)), 1650)
        self.assertTrue(all("ocr_text" not in row for row in omni_packet["records"]))
        with self.assertRaises(ValueError):
            self.store.context(role="decision")


class IpcTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        self.socket = folder / "runtime" / "sidecar.sock"
        self.db = folder / "state" / "observations.sqlite3"
        self.stop = asyncio.Event()
        self.service = asyncio.create_task(serve(allow_ingest=False, socket_path=self.socket,
                                                 db_path=self.db, shutdown=self.stop))
        for _ in range(100):
            if self.service.done():
                await self.service
            if self.socket.exists():
                break
            await asyncio.sleep(0.01)
        self.assertTrue(self.socket.exists())

    async def asyncTearDown(self):
        self.stop.set()
        await asyncio.wait_for(self.service, 3)
        self.tmp.cleanup()

    async def test_read_only_by_default(self):
        health = await request({"action": "health"}, socket_path=self.socket)
        self.assertFalse(health["ingest_enabled"])
        self.assertEqual(await request({"action": "search"}, socket_path=self.socket), [])
        with self.assertRaisesRegex(RuntimeError, "ingest disabled"):
            await request({"action": "record", "event": event()}, socket_path=self.socket)

    async def test_context_and_unknown_action(self):
        output = await request({"action": "context", "role": "omni"}, socket_path=self.socket)
        self.assertEqual(output["records"], [])
        with self.assertRaisesRegex(RuntimeError, "Unknown sidecar"):
            await request({"action": "shutdown"}, socket_path=self.socket)
        with self.assertRaises(ValueError):
            await request({"action": "search", "query": "x" * 100000}, socket_path=self.socket)

    async def test_socket_permissions(self):
        self.assertEqual(self.socket.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.socket.parent.stat().st_mode & 0o777, 0o700)


class IngestIpcTests(unittest.IsolatedAsyncioTestCase):
    async def test_explicit_opt_in_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket = root / "runtime" / "sidecar.sock"
            stop = asyncio.Event()
            task = asyncio.create_task(serve(allow_ingest=True, socket_path=socket,
                                             db_path=root / "state" / "log.db", shutdown=stop))
            try:
                for _ in range(100):
                    if socket.exists():
                        break
                    await asyncio.sleep(0.01)
                created = await request({"action": "record", "event": event()}, socket_path=socket)
                self.assertTrue(created["stored"])
                matches = await request({"action": "search", "query": "Btrfs"}, socket_path=socket)
                self.assertEqual(len(matches), 1)
                self.assertFalse(matches[0]["url_verified"])
                with self.assertRaisesRegex(RuntimeError, "authenticated"):
                    await request({"action": "page_url", "id": created["id"]}, socket_path=socket)
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)


class SourceTests(unittest.IsolatedAsyncioTestCase):
    async def test_hyprland_source_filters_and_deduplicates(self):
        from hyprharness_sidecar.sidecar_sources import HyprlandSource
        with tempfile.TemporaryDirectory() as directory:
            db = SidecarStore(Path(directory) / "db.sqlite3")
            source = HyprlandSource(db, max_queue=2)
            try:
                await source.on_event("not_a_relevant_event", "irrelevant")
                await source.on_event("workspacev2", "2")
                await source.on_event("workspacev2", "2")
                await source.on_event("workspacev2", "3")
                self.assertEqual(source.dropped, 1)
                worker = asyncio.create_task(source.flush())
                try:
                    await asyncio.wait_for(source.queue.join(), timeout=1)
                finally:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
                self.assertEqual(source.stored, 2)
                rows = db.search(source="hyprland")
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["repeat_count"], 2)
            finally:
                db.close()

    async def test_source_cannot_start_without_ingest_opt_in(self):
        with self.assertRaisesRegex(ValueError, "requires explicit"):
            await serve(allow_ingest=False, watch_hyprland=True)

    async def test_hyprland_source_socket_ingestion(self):
        class FakeDesktop:
            async def events(self, callback):
                await callback("activewindowv2", "0x42")
                await callback("workspacev2", "2")
                await asyncio.Event().wait()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            socket_path = root / "r" / "sidecar.sock"
            stop = asyncio.Event()
            task = asyncio.create_task(serve(allow_ingest=True, watch_hyprland=True,
                                             socket_path=socket_path,
                                             db_path=root / "s" / "events.sqlite3",
                                             shutdown=stop, desktop=FakeDesktop()))
            try:
                rows = []
                for _ in range(120):
                    if socket_path.exists():
                        rows = await request({"action": "search", "source": "hyprland"},
                                             socket_path=socket_path)
                        if len(rows) >= 2:
                            break
                    await asyncio.sleep(0.01)
                self.assertEqual({r["kind"] for r in rows}, {"activewindowv2", "workspacev2"})
                self.assertTrue(all(not r["url_available"] for r in rows))
            finally:
                stop.set()
                await asyncio.wait_for(task, 3)


if __name__ == "__main__":
    unittest.main()
