"""Bounded Hyprland socket2 -> d1 candidate bridge; callback never blocks IPC."""
import asyncio
from .recall import CaptureCandidate
from .residency import observation_epoch

CAPTURE_EVENT_NAMES = frozenset({"activewindowv2", "workspacev2", "openwindow"})

class D1CaptureSource:
    def __init__(self, watcher, *, max_queue=4, debounce_seconds=0.25):
        self.watcher = watcher
        if type(max_queue) is not int or not 1 <= max_queue <= 64:
            raise ValueError("Invalid capture queue bound")
        if not 0 <= debounce_seconds <= 5:
            raise ValueError("Invalid event debounce")
        self.debounce_seconds = debounce_seconds
        self.queue = asyncio.Queue(maxsize=max_queue)
        self.dropped = 0
        self.processed = 0
        self.skipped = 0
        self.errors = 0
        if hasattr(watcher, 'subscribe_pause'):
            watcher.subscribe_pause(self.drop_pending)

    def drop_pending(self):
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
            self.dropped += 1

    def _visual_epoch(self):
        return getattr(self.watcher, 'visual_epoch', 'legacy')

    async def on_event(self, name, data):
        if name not in CAPTURE_EVENT_NAMES or not isinstance(data, str):
            return
        # Latest-state wins; background captures always inspect present focus.
        candidate = CaptureCandidate(source="hyprland", event=name)
        await self.on_candidate(candidate)

    async def on_candidate(self, candidate: CaptureCandidate):
        if candidate.source not in ("hyprland", "chrome"):
            return
        epoch = observation_epoch()
        visual_epoch = self._visual_epoch()
        if epoch is None or visual_epoch is None:
            self.dropped += 1
            return
        item = (epoch, candidate, visual_epoch)
        try:
            self.queue.put_nowait(item)
        except asyncio.QueueFull:
            try:
                self.queue.get_nowait()
                self.queue.task_done()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            self.queue.put_nowait(item)

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
                epoch, candidate, visual_epoch = event
                if epoch != observation_epoch() or visual_epoch != self._visual_epoch():
                    self.dropped += 1
                    continue
                outcome = await asyncio.create_task(self.watcher.consider_event(candidate))
                if asyncio.current_task().cancelling():
                    raise asyncio.CancelledError
                self.processed += 1
                if not outcome.get("captured"):
                    self.skipped += 1
            except asyncio.CancelledError:
                raise
            except Exception:
                self.errors += 1
            finally:
                self.queue.task_done()
