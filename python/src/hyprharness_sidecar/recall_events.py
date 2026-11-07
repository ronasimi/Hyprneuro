"""Bounded Hyprland socket2 -> d1 candidate bridge; callback never blocks IPC."""
import asyncio
from .recall import CaptureCandidate

CAPTURE_EVENT_NAMES = frozenset({"activewindowv2", "workspacev2", "openwindow"})

class D1CaptureSource:
    def __init__(self, watcher, *, max_queue=4, debounce_seconds=0.25):
        self.watcher = watcher
        if not 0 <= debounce_seconds <= 5:
            raise ValueError("Invalid event debounce")
        self.debounce_seconds = debounce_seconds
        self.queue = asyncio.Queue(maxsize=max_queue)
        self.dropped = 0
        self.processed = 0
        self.skipped = 0
        self.errors = 0

    async def on_event(self, name, data):
        if name not in CAPTURE_EVENT_NAMES or not isinstance(data, str):
            return
        # Latest-state wins; background captures always inspect present focus.
        candidate = CaptureCandidate(source="hyprland", event=name)
        await self.on_candidate(candidate)

    async def on_candidate(self, candidate: CaptureCandidate):
        if candidate.source not in ("hyprland", "chrome"):
            return
        try:
            self.queue.put_nowait(candidate)
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            self.queue.put_nowait(candidate)

    async def run(self):
        while True:
            event = await self.queue.get()
            try:
                # Coalesce compositor bursts; latest focus/workspace wins.
                if self.debounce_seconds:
                    await asyncio.sleep(self.debounce_seconds)
                while True:
                    try:
                        newer = self.queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    self.queue.task_done()
                    self.dropped += 1
                    event = newer
                outcome = await self.watcher.consider_event(event)
                self.processed += 1
                if not outcome.get("captured"):
                    self.skipped += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors += 1
            finally:
                self.queue.task_done()
