"""Authenticated local Chrome event intake; no screenshots or model calls.

The extension's native host authenticates the extension origin, and this sidecar
endpoint requires an independent per-service token. Both use same-UID access;
not a defense against code already running as the user.
"""
from __future__ import annotations

from collections import deque
import hmac
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import urlsplit

from .sidecar_store import _url, public_url

# Protocol identity is stable across the Hyprneuro branding rename.
HOST_NAME = "org.ronasimi.hyprharness"
EVENTS = frozenset({
    "tab_activated", "tab_updated", "navigation_committed",
    "history_state_updated", "fragment_updated", "window_focus_changed",
})
EVENT_KEYS = frozenset({"event", "time_ms", "tab_id", "window_id", "title", "url",
                        "active", "incognito", "window_focused", "frame_id"})
EXTENSION_ID = re.compile(r"[a-p]{32}\Z")


def token_path():
    runtime = os.environ.get("XDG_RUNTIME_DIR", "")
    if not runtime or not Path(runtime).is_absolute():
        raise RuntimeError("XDG_RUNTIME_DIR unavailable")
    return Path(runtime) / "hyprharness" / "chrome-ingest.token"


def create_token(path):
    """Generate a fresh, private token each sidecar start; reject unsafe paths."""
    path = Path(path)
    if path.is_symlink() or (path.exists() and path.stat().st_uid != os.getuid()):
        raise PermissionError("Unsafe Chrome ingest token path")
    # The service socket is already exclusively bound before this operation.
    if path.exists():
        path.unlink()
    token = secrets.token_hex(32)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, token.encode("ascii"))
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)
    return token


def read_token(path=None):
    path = Path(path) if path is not None else token_path()
    if path.is_symlink() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o077:
        raise PermissionError("Unsafe browser token")
    value = path.read_text(encoding="ascii")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("Invalid Chrome ingest token")
    return value


class BrowserIngress:
    """Verify host identity token and format; record active, focused pages only."""

    def __init__(self, store, *, token, excluded_origins=(), max_per_minute=180):
        self.store = store
        self.token = token
        self.excluded_origins = frozenset(x.lower().rstrip("/") for x in excluded_origins)
        self.recent = deque()
        self.last_event = {}
        self.max_per_minute = max_per_minute

    def record(self, request):
        from .recall import CaptureCandidate
        if not isinstance(request, dict) or set(request) != {"action", "token", "event"}:
            raise ValueError("Invalid browser ingestion request")
        supplied = request.get("token")
        if not isinstance(supplied, str) or len(supplied) != len(self.token) or not hmac.compare_digest(supplied, self.token):
            raise PermissionError("Invalid browser ingestion capability")
        data = request.get("event")
        if not isinstance(data, dict) or set(data) != EVENT_KEYS:
            raise ValueError("Invalid browser event fields")
        if data["event"] not in EVENTS:
            raise ValueError("Unsupported browser event")
        for key in ("active", "incognito", "window_focused"):
            if type(data[key]) is not bool:
                raise ValueError("Invalid browser state")
        for key in ("tab_id", "window_id", "frame_id"):
            if type(data[key]) is not int or data[key] < 0:
                raise ValueError("Invalid browser frame/tab/window")
        if data["frame_id"] != 0:
            return {"stored": False, "reason": "subframe"}, None
        if data["incognito"] or not data["active"] or not data["window_focused"]:
            return {"stored": False, "reason": "inactive_or_private"}, None
        if not isinstance(data["title"], str) or len(data["title"]) > 300:
            raise ValueError("Invalid browser title")
        url = _url(data["url"])
        if url is None:
            raise ValueError("Browser event requires an HTTP(S) URL")
        parsed = urlsplit(url)
        origin = parsed.scheme + "://" + parsed.netloc
        if origin.lower() in self.excluded_origins:
            return {"stored": False, "reason": "excluded_origin"}, None
        now = time.monotonic()
        while self.recent and now - self.recent[0] >= 60:
            self.recent.popleft()
        if len(self.recent) >= self.max_per_minute:
            return {"stored": False, "reason": "rate_limited"}, None
        # Coalesce redundant update/navigation events but retain later revisits.
        key = (data["tab_id"], url, data["title"])
        if now - self.last_event.get(key, float("-inf")) < 0.75:
            return {"stored": False, "reason": "duplicate"}, None
        item = {
            "source": "chrome", "kind": data["event"], "time_ms": data["time_ms"],
            "app_id": "chrome", "title": data["title"], "url": url,
            "message": public_url(url),
        }
        result = self.store.record(item, _trusted_browser=True)
        self.last_event = {k: t for k, t in self.last_event.items() if now - t < 60}
        self.last_event[key] = now
        self.recent.append(now)
        candidate = CaptureCandidate(source="chrome", event=data["event"],
                                     window_title=data["title"], url_origin=origin)
        return result, candidate
