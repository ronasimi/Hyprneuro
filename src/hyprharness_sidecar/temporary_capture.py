"""Legacy one-shot screenshot lifetime: /tmp only, delete after consumption.

The modern sidecar reads grim's stdout directly into RAM and writes no image.
This compatibility helper exists for older broker-based screen_observe stages.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile

PREFIX = "hyprharness-capture-"
MAX_CAPTURE = 8 * 1024 * 1024


def remove_screenshot(path):
    """Delete only a capture generated in /tmp; never follow a symlink."""
    p = Path(path)
    if p.parent != Path("/tmp") or not p.name.startswith(PREFIX) or p.suffix != ".png":
        raise ValueError("Refusing to remove a path outside Hyprharness /tmp captures")
    try:
        metadata = p.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise RuntimeError("Unsafe capture file")
    p.unlink()


async def capture_output(monitor_name, runner):
    """Create 0600 PNG in /tmp, unlink immediately if grim fails/cancels."""
    if not isinstance(monitor_name, str) or not monitor_name or len(monitor_name) > 120:
        raise ValueError("Invalid monitor name")
    fd, name = tempfile.mkstemp(prefix=PREFIX, suffix=".png", dir="/tmp")
    os.close(fd)
    path = Path(name)
    try:
        await runner(["grim", "-s", "0.5", "-o", monitor_name, str(path)], timeout=15)
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("Screenshot file invalid")
        path.chmod(0o600)
        if not 0 < path.stat().st_size <= MAX_CAPTURE:
            raise RuntimeError("Empty or oversized screenshot")
        return path
    except BaseException:
        remove_screenshot(path)
        raise
