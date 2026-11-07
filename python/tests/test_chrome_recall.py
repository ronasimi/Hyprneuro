"""Phase 4 browser event and exact page restoration, entirely offline."""
from __future__ import annotations

import asyncio
import io
import json
import os
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

from hyprneuro.browser_ingest import BrowserIngress, create_token, read_token, EXTENSION_ID
from hyprneuro.chrome_host import read_frame, write_frame, run_host, install, expected_origin
from hyprneuro.sidecar import serve
from hyprneuro.sidecar_client import request
from hyprneuro.sidecar_store import SidecarStore

ID = "a" * 32
URL = "https://example.com/docs/path?token=PRIVATE#section"


def event(**changes):
    value = {"event": "tab_activated", "time_ms": int(time.time() * 1000),
             "tab_id": 10, "window_id": 20, "frame_id": 0,
             "url": URL, "title": "Documentation page", "active": True,
             "incognito": False, "window_focused": True}
    value.update(changes)
    return value


class BrowserIngressTests(unittest.TestCase):
    def setUp(self):
        self.store = SidecarStore(":memory:")
        self.ingress = BrowserIngress(self.store, token="b" * 64)

    def tearDown(self):
        self.store.close()

    def post(self, value=None, token=None):
        return self.ingress.record({"action": "browser_record", "token": token if token is not None else "b" * 64,
                                    "event": value or event()})

    def test_authenticated_url_search_and_provenance(self):
        row, candidate = self.post()
        self.assertTrue(row["stored"])
        self.assertEqual(candidate.source, "chrome")
        self.assertEqual(candidate.url_origin, "https://example.com")
        found = self.store.search(query="documentation", source="chrome")
        self.assertEqual(found[0]["id"], row["id"])
        self.assertTrue(found[0]["url_verified"])
        self.assertEqual(found[0]["url_preview"], "https://example.com/docs/path")
        self.assertNotIn("PRIVATE", json.dumps(found))
        self.assertEqual(self.store.page_url(row["id"])["url"], URL)

    def test_other_source_cannot_forge_verified_url(self):
        plain = self.store.record({"source": "chrome", "kind": "tab_updated",
                                   "url": URL, "time_ms": int(time.time() * 1000)})
        with self.assertRaises(LookupError):
            self.store.page_url(plain["id"])

    def test_bad_token_rejected(self):
        with self.assertRaises(PermissionError):self.post(token="c" * 64)
        with self.assertRaises(PermissionError):self.post(token="")

    def test_inactive_incognito_subframe_skipped(self):
        for changed in ({"incognito": True}, {"active": False},
                        {"window_focused": False}, {"frame_id": 3}):
            value = event(**changed)
            result, candidate = self.post(value)
            self.assertFalse(result["stored"])
            self.assertIsNone(candidate)
        self.assertEqual(self.store.search(source="chrome"), [])

    def test_invalid_fields_and_unsafe_urls(self):
        for changed in ({"url": "javascript:alert(1)"},
                        {"url": "https://user:pass@example.com/"},
                        {"title": 1}, {"tab_id": True}, {"event": "unknown_event"},
                        {"url": None}):
            with self.subTest(changed=changed), self.assertRaises((ValueError, TypeError, AttributeError)):
                self.post(event(**changed))
        bad = event(); bad["extraneous"] = "x"
        with self.assertRaises(ValueError):self.post(bad)

    def test_origin_excluded_before_db_write(self):
        ingress = BrowserIngress(self.store, token="b" * 64,
                                excluded_origins=["https://example.com"])
        result, candidate = ingress.record({"action": "browser_record", "token": "b" * 64,
                                            "event": event()})
        self.assertFalse(result["stored"])
        self.assertIsNone(candidate)

    def test_dedupe_and_rate_limit(self):
        self.assertTrue(self.post()[0]["stored"])
        self.assertEqual(self.post()[0]["reason"], "duplicate")
        ingress = BrowserIngress(self.store, token="b" * 64, max_per_minute=1)
        ingress.record({"action": "browser_record", "token": "b" * 64, "event": event(url="https://sample.test/a")})
        result, _ = ingress.record({"action": "browser_record", "token": "b" * 64,
                                   "event": event(url="https://sample.test/b")})
        self.assertEqual(result["reason"], "rate_limited")

    def test_verified_navigation_needs_new_matching_event(self):
        initial = self.post()[0]["id"]
