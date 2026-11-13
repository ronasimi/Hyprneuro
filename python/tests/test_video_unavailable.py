"""Production IPC remains fail-closed; direct decoder tests are not activation."""
import asyncio
import base64
import json
from pathlib import Path
import tempfile
import shutil
import subprocess

from unittest.mock import patch

import pytest

from hyprneuro.sidecar import MAX_REQUEST, SidecarServer
from hyprneuro.sidecar_store import SidecarStore


def test_real_unix_video_requests_never_decode_or_infer():
    async def run():
        store = SidecarStore(':memory:')
        server = SidecarServer(store)
        root = Path.home() / 'Workspace/hyprneuro-video-recovery-evidence'
        root.mkdir(exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=root) as directory:
                if not shutil.which('ffmpeg'):
                    pytest.skip('Existing ffmpeg required for synthetic valid MP4; no install')
                clip = Path(directory) / 'valid.mp4'
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i',
                                'color=c=red:s=256x256:r=4:d=2', '-threads', '1', '-c:v', 'libx264',
                                '-pix_fmt', 'yuv420p', str(clip)], check=True)
                valid = base64.b64encode(clip.read_bytes()).decode()
                path = str(Path(directory) / 'sidecar.sock')
                async with await asyncio.start_unix_server(server.handle, path=path, limit=MAX_REQUEST+1):
                    async def request(frame):
                        reader, writer = await asyncio.open_unix_connection(path)
                        try:
                            writer.write(json.dumps(frame).encode() + b'\n')
                            await writer.drain()
                            response = json.loads(await asyncio.wait_for(reader.readline(), 2))
                            assert await asyncio.wait_for(reader.read(), 2) == b''
                            return response
                        finally:
                            writer.close()
                            await writer.wait_closed()
                    with patch('hyprneuro.agent.stream_chat') as inference, patch('hyprneuro.video.validate_video') as decode:
                        for data in (valid, 'AAAA', None, {'path': '/untrusted.mp4'}):
                            reply = await request({'action': 'video_review', 'data': data})
                            assert reply['ok'] is False and 'Video unavailable' in reply['error']
                            reply = await request({'action': 'agent_chat', 'message': 'Review video',
                                                   'media': {'mime': 'video/mp4', 'data': data}})
                            assert reply['type'] == 'error' and 'Video unavailable' in reply['error']
                        reply = await request({'action': 'video_review', 'path': '/untrusted.mp4'})
                        assert reply['ok'] is False
                        reply = await request({'action': 'agent_chat', 'message': 'Native part',
                                               'media': {'type': 'input_video', 'input_video': {'data': valid}}})
                        assert reply['type'] == 'error'
                        inference.assert_not_called()
                        decode.assert_not_called()
                    assert not server.handlers
        finally:
            store.close()
    asyncio.run(run())
