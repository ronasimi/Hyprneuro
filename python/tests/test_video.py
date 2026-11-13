"""Actual bounded decoder + adversarial contracts; synthetic files, never capture."""
import asyncio
import base64
import copy
import os
import re
from pathlib import Path
import signal
import shutil
import struct
import subprocess
import tempfile
import time
from unittest.mock import patch

import pytest

from hyprneuro import video


@pytest.fixture(scope='module')
def clips():
    if not all(shutil.which(p) for p in ('ffmpeg', 'ffprobe', 'prlimit')):
        pytest.skip('Existing local ffmpeg/ffprobe/prlimit required; no install')
    root = Path.home() / 'Workspace/hyprneuro-video-recovery-evidence'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root, prefix='unit-') as directory:
        runtime = Path(directory) / 'runtime'
        runtime.mkdir(mode=0o700)
        previous_runtime = os.environ.get('XDG_RUNTIME_DIR')
        os.environ['XDG_RUNTIME_DIR'] = str(runtime)
        out = {}
        try:
            for name, size, fps, duration, audio in [
                    ('valid', '256x256', 4, 4, False), ('dimensions', '642x360', 2, 2, False),
                    ('frames', '256x256', 6, 6, False), ('duration', '256x256', 2, 7, False),
                    ('fps', '256x256', 8, 2, False), ('audio', '256x256', 2, 2, True)]:
                path = Path(directory) / (name + '.mp4')
                command = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', f'color=c=red:s={size}:r={fps}:d={duration}']
                if audio:
                    command += ['-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', '-t', str(duration), '-c:a', 'aac']
                subprocess.run(command + ['-threads', '1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(path)], check=True)
                out[name] = base64.b64encode(path.read_bytes()).decode()
            yield out
        finally:
            if previous_runtime is None:
                os.environ.pop('XDG_RUNTIME_DIR', None)
            else:
                os.environ['XDG_RUNTIME_DIR'] = previous_runtime


def test_actual_decode_and_policy_rejections(clips):
    async def run():
        result = await video.validate_video(clips['valid'])
        assert result == dict(schema='hyprneuro.video_review/1', width=256, height=256, frames=16,
                              duration_us=4000000, bytes=len(base64.b64decode(clips['valid'])))
        for name in ('dimensions', 'frames', 'duration', 'fps', 'audio'):
            with pytest.raises(ValueError):
                await video.validate_video(clips[name])
        corrupt = bytearray(base64.b64decode(clips['valid']))
        i = corrupt.index(b'mdat') + 4
        end = i - 8 + struct.unpack_from('>I', corrupt, i - 8)[0]
        corrupt[i:end] = bytes(end - i)  # keep container/movie; corrupt actual H.264 packets
        with pytest.raises(ValueError, match='full decode'):
            await video.validate_video(base64.b64encode(corrupt).decode())
        assert not list((Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprneuro-video').iterdir())
    asyncio.run(run())

@pytest.mark.parametrize('value', [None, False, 1, [], '', 'not base64', 'AAAA',
                                  'A' * (4 * ((video.MAX_VIDEO_BYTES + 2) // 3) + 1)])
def test_bytes_types_and_bounds(value):
    with pytest.raises(ValueError):
        video.video_bytes(value)


def test_container_integrity(clips):
    raw = base64.b64decode(clips['valid'])
    url = raw.index(b'url ') + 4
    external = raw[:url] + bytes(4) + raw[url+4:]
    for value in [external, raw[:-1], raw + b'x', b'\0\0\0\0' + raw[4:], b'\0\0\0\1' + raw[4:],
                  raw[:8] + b'qt  ' + raw[12:], raw + raw[:32], raw + bytes(video.MAX_VIDEO_BYTES)]:
        with pytest.raises(ValueError):
            video.video_bytes(base64.b64encode(value).decode())


def test_decoded_every_frame_and_timing_contract():
    report = {'streams': [dict(codec_type='video', codec_name='h264', codec_tag_string='avc1', width=256,
                               height=256, duration='1', r_frame_rate='2/1', nb_frames='2')],
              'format': {'duration': '1'}, 'frames': [dict(width=256, height=256, pix_fmt='yuv420p',
                                best_effort_timestamp_time=str(i / 2), duration_time='0.5') for i in range(2)]}
    assert video.decoded_report(report)['frames'] == 2
    for field, value in [('width', 4096), ('height', 4096), ('pix_fmt', 'yuv420p10le'),
                         ('best_effort_timestamp_time', 'NaN'), ('duration_time', '-1')]:
        mutated = copy.deepcopy(report)
        mutated['frames'][1][field] = value
        with pytest.raises(ValueError):
            video.decoded_report(mutated)
    for field, value in [('r_frame_rate', '1/0'), ('nb_frames', '999'), ('duration', 'inf'), ('width', True)]:
        mutated = copy.deepcopy(report); mutated['streams'][0][field] = value
        with pytest.raises(ValueError):
            video.decoded_report(mutated)


def test_real_decoder_wall_timeout_cancel_limits_and_cleanup(clips):
    async def run():
        real_spawn = asyncio.create_subprocess_exec
        children = []
        async def stop_decoder(*args, **kwargs):
            proc = await real_spawn(*args, **kwargs)
            children.append(proc)
            # Stop the REAL ffprobe after exec, not a fake sleeper/backend.
            for _ in range(1000):
                try:
                    if Path(f'/proc/{proc.pid}/exe').resolve().name == 'ffprobe':
                        os.kill(proc.pid, signal.SIGSTOP)
                        limits = Path(f'/proc/{proc.pid}/limits').read_text()
                        for name, value in [('Max cpu time', 2), ('Max file size', 131072),
                                            ('Max open files', 64), ('Max address space', 536870912)]:
                            assert re.search(rf'^{name}\s+{value}\s+{value}\s', limits, re.MULTILINE)
                        snapshot = Path(args[-1])
                        assert snapshot.read_bytes() == base64.b64decode(clips['valid'])
                        assert snapshot.parent.stat().st_mode & 0o777 == 0o700
                        assert snapshot.parent.parent.stat().st_mode & 0o777 == 0o700
                        for file in snapshot.parent.iterdir():
                            assert file.stat().st_mode & 0o777 == 0o600
                        return proc
                except FileNotFoundError:
                    pass
                await asyncio.sleep(.0001)
            proc.kill(); await proc.wait()
            raise AssertionError('Could not stop actual decoder after exec')
        started = time.monotonic()
        with patch('hyprneuro.video.asyncio.create_subprocess_exec', stop_decoder):
            with pytest.raises(ValueError, match='timed out'):
                await video.validate_video(clips['valid'])
        assert 5 <= time.monotonic() - started < 8
        assert children[-1].returncode == -signal.SIGKILL
        assert not Path(f'/proc/{children[-1].pid}').exists()
        with patch('hyprneuro.video.asyncio.create_subprocess_exec', stop_decoder):
            task = asyncio.create_task(video.validate_video(clips['valid']))
            while len(children) < 2 or not Path(f'/proc/{children[-1].pid}/exe').exists():
                await asyncio.sleep(.001)
            await asyncio.sleep(.05)
            with pytest.raises(ValueError, match='busy'):
                await video.validate_video(clips['valid'])
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not Path(f'/proc/{children[-1].pid}').exists()
        assert not list((Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprneuro-video').iterdir())
        assert (await video.validate_video(clips['valid']))['frames'] == 16
    asyncio.run(run())


@pytest.mark.parametrize('value', ['1e999999999', '1e-99999999', 'NaN', 'inf', '1/0', '1_000', '9'*33, None, True])
def test_timing_parser_cannot_expand_unbounded_exponents(value):
    with pytest.raises(ValueError):
        video._number(value)


def test_runtime_directory_refusal(clips, monkeypatch):
    async def run():
        for runtime in (None, '', 'relative'):
            if runtime is None:
                monkeypatch.delenv('XDG_RUNTIME_DIR', raising=False)
            else:
                monkeypatch.setenv('XDG_RUNTIME_DIR', runtime)
            with pytest.raises(ValueError, match='runtime directory'):
                await video.validate_video(clips['valid'])
            assert video._busy is False
    asyncio.run(run())


def test_repeated_cancel_during_real_spawn_reaps_child(clips):
    async def run():
        real_spawn = asyncio.create_subprocess_exec
        child = None
        created, release = asyncio.Event(), asyncio.Event()
        async def delayed_handle(*args, **kwargs):
            nonlocal child
            child = await real_spawn(*args, **kwargs)
            os.kill(child.pid, signal.SIGSTOP)
            created.set()
            await release.wait()  # withhold the real stopped child's handle
            return child
        try:
            with patch('hyprneuro.video.asyncio.create_subprocess_exec', delayed_handle):
                task = asyncio.create_task(video.validate_video(clips['valid']))
                await asyncio.wait_for(created.wait(), 2)
                task.cancel()
                await asyncio.sleep(0)  # enter cancellation cleanup, still awaiting handle
                task.cancel()  # disconnect + shutdown may cancel the same owner twice
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert child.returncode == -signal.SIGKILL
            assert not Path(f'/proc/{child.pid}').exists()
        finally:
            release.set()
            if child is not None and child.returncode is None:
                child.kill()
                await child.wait()
        assert not video._busy
        assert not list((Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprneuro-video').iterdir())
        assert (await video.validate_video(clips['valid']))['frames'] == 16
    asyncio.run(run())


def test_private_root_refusals(clips, monkeypatch):
    async def run():
        with tempfile.TemporaryDirectory(dir=Path(os.environ['XDG_RUNTIME_DIR'])) as directory:
            monkeypatch.setenv('XDG_RUNTIME_DIR', directory)
            root = Path(directory) / 'hyprneuro-video'
            target = Path(directory) / 'target'
            target.mkdir(mode=0o700)
            root.symlink_to(target, target_is_directory=True)
            with pytest.raises(ValueError, match='Unsafe'):
                await video.validate_video(clips['valid'])
            root.unlink(); root.mkdir(mode=0o755)
            with pytest.raises(ValueError, match='Unsafe'):
                await video.validate_video(clips['valid'])
            assert not list(target.iterdir()) and not list(root.iterdir())
    asyncio.run(run())


def test_unavailable_decoder_cleans_snapshot_and_single_flight(clips):
    async def run():
        with patch('hyprneuro.video.asyncio.create_subprocess_exec', side_effect=FileNotFoundError):
            with pytest.raises(ValueError, match='decoder unavailable'):
                await video.validate_video(clips['valid'])
        assert not video._busy
        assert not list((Path(os.environ['XDG_RUNTIME_DIR']) / 'hyprneuro-video').iterdir())
        assert (await video.validate_video(clips['valid']))['frames'] == 16
    asyncio.run(run())


def test_structural_rejection_never_launches_decoder(clips):
    async def run():
        with patch('hyprneuro.video.asyncio.create_subprocess_exec') as decode:
            for data in ('AAAA', clips['audio']):
                with pytest.raises(ValueError):
                    await video.validate_video(data)
            decode.assert_not_called()
    asyncio.run(run())


def test_report_types_and_every_frame_are_strict():
    report = {'streams': [dict(codec_type='video', codec_name='h264', codec_tag_string='avc1', width=1,
                               height=1, duration='1', r_frame_rate='2/1', nb_frames='2')],
              'format': {'duration': '1'}, 'frames': [dict(width=1, height=1, pix_fmt='yuv420p',
                                best_effort_timestamp_time=str(i / 2), duration_time='0.5') for i in range(2)]}
    assert video.decoded_report(report)['frames'] == 2
    for value in (None, [], {}, {'streams': []}, {'streams': report['streams'], 'frames': []}):
        with pytest.raises(ValueError):
            video.decoded_report(value)
    for field in ('width', 'height'):
        malformed = copy.deepcopy(report)
        malformed['frames'][1][field] = True  # Python bool==1 is NOT a decoded integer dimension
        with pytest.raises(ValueError):
            video.decoded_report(malformed)
    for field, value in [('codec_name', 'hevc'), ('codec_tag_string', 'avc3'), ('codec_type', 'audio')]:
        malformed = copy.deepcopy(report)
        malformed['streams'][0][field] = value
        with pytest.raises(ValueError):
            video.decoded_report(malformed)
