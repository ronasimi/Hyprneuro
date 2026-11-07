"""Foreground-first, bounded async admission for local Vulkan d1 and Omni.

There is one bounded worker per model service. Event callbacks never wait for it;
background jobs can be dropped/coalesced. Foreground requests have priority at
next admission, but running requests cannot be preempted by this module.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
import itertools
from typing import Awaitable, Callable, Any


class ModelQueueFull(RuntimeError):
    pass


@dataclass
class _Request:
    priority: int
    sequence: int
    operation: Callable[[], Awaitable[Any]]
    result: asyncio.Future
    key: str | None


class ModelLane:
    """One Vulkan server admission lane, with no hidden model processes."""

    def __init__(self, name: str, *, max_background: int = 8):
        if not name or max_background < 1:
            raise ValueError("Invalid model lane")
        self.name = name
        self.max_background = max_background
        self._pending_foreground: list[_Request] = []
        self._pending_background: OrderedDict[str, _Request] = OrderedDict()
        self._sequence = itertools.count()
        self._wake = asyncio.Event()
        self._closed = False
        self._worker: asyncio.Task | None = None
        self.coalesced = 0
        self.dropped = 0
        self.completed = 0

    def start(self):
        if self._closed:
            raise RuntimeError("Model lane stopped")
        if not self._worker:
            self._worker = asyncio.create_task(self._run(), name="hyprneuro-"+self.name)
        return self

    async def stop(self):
        self._closed = True
        for task in self._pending_foreground:
            if not task.result.done():
                task.result.cancel()
        for task in self._pending_background.values():
            if not task.result.done():
                task.result.cancel()
        self._pending_foreground.clear()
        self._pending_background.clear()
        self._wake.set()
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
            self._worker = None

    def submit(self, operation: Callable[[], Awaitable[Any]], *, foreground=False,
               key: str | None = None) -> asyncio.Future:
        """Admission is synchronous and never blocks event callbacks."""
        if self._closed:
            raise RuntimeError("Model lane stopped")
        if not self._worker:
            self.start()
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        seq = next(self._sequence)
        if foreground:
            # Cap foreground callers to keep producer mistakes from filling RAM.
            if len(self._pending_foreground) >= 16:
                raise ModelQueueFull("Too many foreground model requests")
            self._pending_foreground.append(_Request(0, seq, operation, future, None))
        else:
            if key is None:
                key = f"{self.name}-{seq}"
            old = self._pending_background.pop(key, None)
            if old:
                if not old.result.done():
                    old.result.set_result(None)
                self.coalesced += 1
            elif len(self._pending_background) >= self.max_background:
                _, stale = self._pending_background.popitem(last=False)
                if not stale.result.done():
                    stale.result.set_result(None)
                self.dropped += 1
            self._pending_background[key] = _Request(1, seq, operation, future, key)
        self._wake.set()
        return future

    async def request(self, operation: Callable[[], Awaitable[Any]], *, foreground=False,
                      key: str | None = None, timeout: float = 20):
        future = self.submit(operation, foreground=foreground, key=key)
        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            future.cancel()
            raise

    async def _run(self):
        try:
            while not self._closed:
                if self._pending_foreground:
                    item = self._pending_foreground.pop(0)
                elif self._pending_background:
                    _, item = self._pending_background.popitem(last=False)
                else:
                    self._wake.clear()
                    await self._wake.wait()
                    continue
                if item.result.done():
                    continue
                try:
                    value = await item.operation()
                except asyncio.CancelledError:
                    if not item.result.done():
                        item.result.cancel()
                    raise
                except Exception as exc:
                    if not item.result.done():
                        item.result.set_exception(exc)
                else:
                    if not item.result.done():
                        item.result.set_result(value)
                finally:
                    self.completed += 1
        finally:
            self._closed = True


class ScheduledModels:
    """Model facade for Recall; all requests use existing Vulkan endpoints."""

    def __init__(self, models, *, decision_lane=None, omni_lane=None):
        self.models = models
        self.decision_lane = decision_lane or ModelLane("d1")
        self.omni_lane = omni_lane or ModelLane("omni")

    async def stop(self):
        await self.decision_lane.stop()
        await self.omni_lane.stop()

    async def decide_capture(self, details, *, foreground=False):
        return await self.decision_lane.request(
            lambda: self.models.decide_capture(details), foreground=foreground,
            key="recall-meta", timeout=5 if not foreground else 12)

    async def decide_visual(self, png, details, *, foreground=False):
        from .d1_visual import decide_visual
        return await self.decision_lane.request(
            lambda: decide_visual(self.models, png, details), foreground=foreground,
            key="recall-visual", timeout=8 if not foreground else 12)

    async def vision(self, png, prompt, *, foreground=False):
        return await self.omni_lane.request(
            lambda: self.models.vision(png, prompt), foreground=foreground,
            key="recall-omni-" + ("ocr" if "Extract" in prompt else "description"),
            timeout=45 if not foreground else 60)
