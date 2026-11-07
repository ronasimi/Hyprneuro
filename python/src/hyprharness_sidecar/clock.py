"""Read-only wall and monotonic clock checkpoints. No background worker."""
from datetime import datetime, timezone
from pathlib import Path
import time


def snapshot():
    """For chronology use UTC/local; for same-boot duration use monotonic_ns."""
    now = datetime.now(timezone.utc)
    try:
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    except OSError:
        boot_id = None
    return {
        "utc": now.isoformat(),
        "local": now.astimezone().isoformat(),
        "unix_seconds": now.timestamp(),
        "monotonic_ns": time.monotonic_ns(),
        "boot_id": boot_id,
    }


# TODO(clock/durable): Attach this checkpoint to pi-durable stage receipts.
# TODO(clock/tape): Pass bounded time metadata as untrusted data in existing Tape.
# Do not infer stable wall-clock durations across NTP changes or reboot.
