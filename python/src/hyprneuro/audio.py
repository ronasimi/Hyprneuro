"""Bounded file-only PCM WAV contract, independent of filenames and MIME guesses.

No compressed/float/extensible WAV, URLs, recording, or decoder subprocesses.
PCM16 has no compressed expansion: every complete 2-byte sample is decodable.
"""
import struct

MAX_AUDIO_BYTES = 2_880_044  # 15 s * 48000 Hz * 2 channels * 2 bytes + header


def validate_wav(data: bytes) -> tuple[int, int, int]:
    """Return (rate, channels, frames), requiring a canonical 44-byte PCM header.

    Reject extra chunks rather than permit ambiguous parser/decoder interpretations.
    GTK separately prepares these exact bytes before enabling explicit review/send.
    """
    if not 44 < len(data) <= MAX_AUDIO_BYTES:
        raise ValueError("WAV size exceeds the bounded PCM audio contract")
    riff, size, wave, fmt, fmt_size, codec, channels, rate, byte_rate, align, bits, chunk, n = struct.unpack_from(
        '<4sI4s4sIHHIIHH4sI', data)
    if (riff, size, wave, fmt, fmt_size, codec, bits, chunk, n) != (
            b'RIFF', len(data) - 8, b'WAVE', b'fmt ', 16, 1, 16, b'data', len(data) - 44):
        raise ValueError("Only canonical PCM16 WAV (no extra chunks) is enabled")
    if channels not in (1, 2) or not 8000 <= rate <= 48000 or align != channels * 2 or byte_rate != rate * align:
        raise ValueError("WAV requires 1–2 channels, 8000–48000 Hz and consistent PCM16 layout")
    frames, partial = divmod(n, align)
    if partial or not 0 < frames <= rate * 15:
        raise ValueError("WAV must contain complete PCM frames and at most 15 seconds")
    return rate, channels, frames
