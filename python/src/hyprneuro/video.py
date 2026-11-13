"""File-only silent H.264 MP4 validation. No models, URLs or capture.

QUARANTINED: direct validator tests only. No UI, review RPC or native inference
route imports this module. Passing validation does not enable video.
One bounded child, private snapshots, kill+wait on timeout/cancellation;
prlimit/ffprobe are existing local executables.
"""
import asyncio
import base64
import binascii
from fractions import Fraction
import json
import os
import re
from pathlib import Path
import struct
import tempfile

MAX_VIDEO_BYTES = 3 * 1024 * 1024
DECODE_SECONDS = 5
REPORT_BYTES = 128 * 1024
_busy = False


def video_bytes(b64):
    if not isinstance(b64, str) or not b64 or len(b64) > 4 * ((MAX_VIDEO_BYTES + 2) // 3):
        raise ValueError('Invalid or oversized MP4 attachment')
    try:
        data = base64.b64decode(b64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('Invalid MP4 base64') from exc
    if not 32 <= len(data) <= MAX_VIDEO_BYTES:
        raise ValueError('MP4 must be at most 3 MiB')
    counts = {}
    movie = None
    offset = 0
    while offset < len(data):
        if offset + 8 > len(data):
            raise ValueError('Truncated MP4 box')
        size, kind = struct.unpack_from('>I4s', data, offset)
        if size < 8 or size > len(data) - offset or kind not in (b'ftyp', b'moov', b'mdat', b'free'):
            raise ValueError('Validator accepts only bounded nonfragmented MP4 boxes')
        counts[kind] = counts.get(kind, 0) + 1
        if counts[kind] > 1:
            raise ValueError('Duplicate MP4 box')
        if offset == 0 and kind != b'ftyp':
            raise ValueError('MP4 must start with ftyp')
        if kind == b'moov':
            movie = (offset + 8, offset + size)
        if kind == b'ftyp':
            if not 16 <= size <= 64 or size % 4:
                raise ValueError('Invalid MP4 brands')
            brands = [data[offset+8:offset+12]] + [data[i:i+4] for i in range(offset+16, offset+size, 4)]
            if any(b not in (b'isom', b'iso2', b'avc1', b'mp41', b'mp42') for b in brands):
                raise ValueError('Unsupported MP4 brand')
        offset += size
    if any(counts.get(k) != 1 for k in (b'ftyp', b'moov', b'mdat')):
        raise ValueError('Incomplete MP4 container')
    # Ignore-external-reference ffprobe options alone are insufficient: GTK and
    # Omni must never follow a different dref when decoding the reviewed bytes.
    start, end = movie
    for container in (b'trak', b'mdia', b'minf', b'dinf', b'dref'):
        matches = []
        pos = start
        count = 0
        while pos < end:
            if pos + 8 > end:
                raise ValueError('Truncated MP4 movie box')
            size, kind = struct.unpack_from('>I4s', data, pos)
            count += 1
            if size < 8 or pos + size > end or count > 256:
                raise ValueError('Unsupported MP4 movie structure')
            if kind == container:
                matches.append((pos + 8, pos + size))
            pos += size
        if len(matches) != 1:
            raise ValueError('MP4 requires exactly one self-contained video track')
        start, end = matches[0]
    # FullBox v0/flags0, one entry: url FullBox v0/self-contained=1, no URL.
    if data[start:end] != struct.pack('>III4sI', 0, 1, 12, b'url ', 1):
        raise ValueError('External MP4 data references are forbidden')
    return data


def _number(value):
    if not isinstance(value, str) or not re.fullmatch(r'-?[0-9]{1,12}(?:\.[0-9]{1,9}|/[0-9]{1,12})?', value):
        raise ValueError('Missing video timing')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise ValueError('Invalid video timing') from exc


def decoded_report(report):
    """Inspect dimensions/pixel format/timing of EVERY actually decoded frame."""
    if not isinstance(report, dict):
        raise ValueError('Invalid video report')
    streams, frames = report.get('streams'), report.get('frames')
    if not isinstance(streams, list) or len(streams) != 1 or not isinstance(streams[0], dict):
        raise ValueError('MP4 requires one video stream and no audio/other tracks')
    s = streams[0]
    if (s.get('codec_type'), s.get('codec_name'), s.get('codec_tag_string')) != ('video', 'h264', 'avc1'):
        raise ValueError('Validator accepts only silent H.264 avc1 MP4')
    w, h = s.get('width'), s.get('height')
    if type(w) is not int or type(h) is not int or not 1 <= w <= 640 or not 1 <= h <= 360:
        raise ValueError('Video dimensions must be at most 640×360')
    if not isinstance(frames, list) or not 2 <= len(frames) <= 24:
        raise ValueError('Video must decode 2–24 frames')
    fps, duration = _number(s.get('r_frame_rate')), _number(s.get('duration'))
    if not 0 < fps <= 6 or not 0 < duration <= 6 or abs(duration - len(frames) / fps) > Fraction(1, 1000):
        raise ValueError('Video requires constant rate ≤6 fps and duration ≤6 s')
    if s.get('nb_frames') != str(len(frames)):
        raise ValueError('Declared/decoded frame count mismatch')
    for i, f in enumerate(frames):
        if (not isinstance(f, dict) or type(f.get('width')) is not int or type(f.get('height')) is not int or
                (f.get('width'), f.get('height'), f.get('pix_fmt')) != (w, h, 'yuv420p')):
            raise ValueError('Decoded frame dimensions/format changed or are unsupported')
        if (abs(_number(f.get('best_effort_timestamp_time')) - i / fps) > Fraction(1, 1000) or
                abs(_number(f.get('duration_time')) - 1 / fps) > Fraction(1, 1000)):
            raise ValueError('Unsupported decoded frame timing')
    fmt = report.get('format', {})
    if not isinstance(fmt, dict) or abs(_number(fmt.get('duration')) - duration) > Fraction(1, 1000):
        raise ValueError('Container/decoded duration mismatch')
    return dict(width=w, height=h, frames=len(frames), duration_us=int(duration * 1000000))


async def _decode(path, output, errors):
    with output.open('xb') as out, errors.open('xb') as err:
        os.fchmod(out.fileno(), 0o600)
        os.fchmod(err.fileno(), 0o600)
        # Shield spawn so cancellation cannot lose a child before its handle
        # is returned. Even that race must finish spawning, then kill + reap.
        spawning = asyncio.create_task(asyncio.create_subprocess_exec(
            '/usr/bin/prlimit', '--as=536870912', '--cpu=2', f'--fsize={REPORT_BYTES}', '--nofile=64', '--',
            '/usr/bin/ffprobe', '-v', 'error', '-threads', '1', '-err_detect', 'explode',
            '-protocol_whitelist', 'file,pipe', '-f', 'mov', '-enable_drefs', '0', '-use_absolute_path', '0',
            '-show_frames', '-show_streams', '-show_format', '-show_entries',
            'frame=width,height,best_effort_timestamp_time,duration_time,pix_fmt:'
            'stream=codec_type,codec_name,codec_tag_string,width,height,duration,nb_frames,r_frame_rate:'
            'format=format_name,duration', '-of', 'json', '-i', str(path), stdout=out, stderr=err,
            stdin=asyncio.subprocess.DEVNULL))
        proc = None
        try:
            proc = await asyncio.shield(spawning)
            await asyncio.wait_for(proc.wait(), DECODE_SECONDS)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            async def stop():
                child = proc if proc is not None else await spawning
                if child.returncode is None:
                    try:
                        child.kill()
                    except ProcessLookupError:
                        pass
                await child.wait()
            # A second cancellation (e.g. disconnect + shutdown) must not
            # interrupt handle delivery or reaping and orphan a stopped child.
            stopping = asyncio.create_task(stop())
            while not stopping.done():
                try:
                    await asyncio.shield(stopping)
                except asyncio.CancelledError:
                    continue
            stopping.result()
            raise
    if proc.returncode or errors.stat().st_size or output.stat().st_size >= REPORT_BYTES:
        raise ValueError('MP4 full decode failed or exceeded resource limits')
    try:
        report = json.loads(output.read_bytes())
        if not isinstance(report, dict):
            raise ValueError('Invalid video report')
        return decoded_report(report)
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid video decode report') from exc


async def validate_video(b64):
    global _busy
    data = video_bytes(b64)
    if _busy:
        raise ValueError('Video decoder busy; retry explicitly')
    _busy = True
    try:
        # Same-UID private runtime storage, never a pathname supplied by IPC.
        runtime = os.environ.get('XDG_RUNTIME_DIR')
        if not runtime or not Path(runtime).is_absolute():
            raise ValueError('Private runtime directory unavailable')
        root = Path(runtime) / 'hyprneuro-video'
        root.mkdir(mode=0o700, exist_ok=True)
        if root.is_symlink() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o077:
            raise ValueError('Unsafe video decoder directory')
        with tempfile.TemporaryDirectory(prefix='review-', dir=root) as directory:
            path = Path(directory) / 'snapshot.mp4'
            path.write_bytes(data)
            path.chmod(0o600)
            result = await _decode(path, Path(directory) / 'report.json', Path(directory) / 'errors.txt')
            return dict(schema='hyprneuro.video_review/1', bytes=len(data), **result)
    except asyncio.TimeoutError as exc:
        raise ValueError('Video decoder timed out (5 s); snapshot removed') from exc
    except OSError as exc:
        raise ValueError('Local video decoder unavailable') from exc
    finally:
        _busy = False
