"""Opt-in read-only event producers for the observational sidecar.

This module DOES NOT call d1, Omni or LFM3, and never captures screenshots.
"""
from __future__ import annotations

import asyncio
import hashlib
import time

HYPRLAND_KINDS = frozenset({
    "activewindowv2", "workspacev2", "createworkspacev2", "destroyworkspacev2",
    "openwindow", "closewindow", "monitoradded", "monitorremoved",
})


class HyprlandSource:
    """Bounded, nonblocking ingress from the existing Hyprland socket2 adapter."""

    def __init__(self, store, *, max_queue=256):
        self.store = store
        self.queue = asyncio.Queue(maxsize=max_queue)
        self.dropped = 0
        self.stored = 0
        self.failures = 0

    async def on_event(self, name, data):
        if name not in HYPRLAND_KINDS:
            return
        if not isinstance(data, str):
            return
        # Consume only event metadata. Full window titles may contain secrets;
        # the user must explicitly enable this source and configure exclusions
        # before using it as a continuous screen-history trigger.
        value = data[:500]
        fingerprint = hashlib.sha256((name + "\0" + value).encode()).hexdigest()[:24]
        event = {"source": "hyprland", "kind": name,
                 "time_ms": int(time.time() * 1000), "message": value,
                 "event_key": "hyprland-" + fingerprint}
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.dropped += 1  # Drop rather than block compositor IPC reader.

    async def flush(self):
        """Drain queued metadata in the sidecar process, not compositor thread."""
        while True:
            item = await self.queue.get()
            try:
                self.store.record(item)
                self.stored += 1
            except (ValueError, OSError, RuntimeError):
                self.failures += 1
            finally:
                self.queue.task_done()

    async def follow(self, desktop):
        """A single optional socket2 subscription; desktop adapter reconnects."""
        await desktop.events(self.on_event)
