"""No model, playback, recording or decoder package needed for PCM bounds."""
import struct

import pytest

from hyprneuro.audio import MAX_AUDIO_BYTES, validate_wav


def wav(rate=24000, channels=1, frames=24):
    n = frames * channels * 2
    return struct.pack('<4sI4s4sIHHIIHH4sI', b'RIFF', n + 36, b'WAVE', b'fmt ',
                       16, 1, channels, rate, rate * channels * 2, channels * 2,
                       16, b'data', n) + bytes(n)


@pytest.mark.parametrize('rate,channels', [(8000, 1), (24000, 1), (48000, 2)])
def test_pcm_frames_and_duration(rate, channels):
    data = wav(rate, channels, rate * 15)
    assert validate_wav(data) == (rate, channels, rate * 15)
    assert len(data) <= MAX_AUDIO_BYTES


@pytest.mark.parametrize('data', [b'', b'RIFF', wav()[:-1], wav() + b'\0', wav(frames=0),
                                  wav(rate=7999), wav(rate=48001), wav(channels=3),
                                  wav(frames=24000 * 15 + 1),
                                  wav(rate=48000, channels=2, frames=48000 * 15 + 1)])
def test_bounds(data):
    with pytest.raises(ValueError):
        validate_wav(data)


@pytest.mark.parametrize('offset', [0, 4, 8, 12, 16, 20, 22, 24, 28, 32, 34, 36, 40])
def test_header_integrity(offset):
    data = bytearray(wav())
    data[offset] ^= 0x80
    with pytest.raises(ValueError):
        validate_wav(data)
