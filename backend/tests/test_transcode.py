"""Tests for the audio transcode service (services/transcode.py).

Tests that actually run ffmpeg are skipped when ffmpeg isn't on PATH (e.g. a
bare CI image without it) — the production image installs it, and the
graceful-fallback behaviour is covered regardless.
"""

import shutil
import subprocess

import pytest

from app.services.transcode import needs_transcode, transcode_to_mp3

_HAS_FFMPEG = shutil.which("ffmpeg") is not None
ffmpeg_only = pytest.mark.skipif(not _HAS_FFMPEG, reason="ffmpeg not installed")


def test_needs_transcode_classifies_formats():
    # webm/opus + ogg must be transcoded for Safari playback.
    assert needs_transcode(".webm") is True
    assert needs_transcode(".ogg") is True
    assert needs_transcode("webm") is True  # missing leading dot
    assert needs_transcode(".WEBM") is True  # case-insensitive
    # Already-playable formats are left alone.
    assert needs_transcode(".mp3") is False
    assert needs_transcode(".mp4") is False
    assert needs_transcode(".m4a") is False
    assert needs_transcode(".wav") is False


def test_transcode_garbage_returns_none():
    # Non-audio bytes can't be decoded — must fail gracefully, never raise.
    assert transcode_to_mp3(b"this is not audio", ".webm") is None


def _make_webm_opus() -> bytes:
    """Generate a 1s webm/opus tone via ffmpeg for a real round-trip test."""
    out = subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:a", "libopus", "-f", "webm", "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    return out.stdout


@ffmpeg_only
def test_transcode_webm_opus_to_mp3_roundtrip():
    webm = _make_webm_opus()
    assert webm  # sanity: fixture produced bytes

    mp3 = transcode_to_mp3(webm, ".webm")
    assert mp3 is not None
    assert len(mp3) > 0
    # MP3 frames start with an ID3 tag or a frame sync (0xFF 0xFB/0xFA/...).
    assert mp3[:3] == b"ID3" or mp3[0] == 0xFF
