"""Audio transcoding — normalise participant recordings to MP3 for playback.

Browsers disagree on which recording formats they can *play back*. Chrome,
Firefox and Android record `audio/webm;codecs=opus`, which Safari/iOS cannot
decode — so a researcher reviewing on a Mac sees "Audio unavailable" even
though the clip is safely stored. MP3 plays in every browser, and Whisper
transcribes it just as happily as WebM, so we transcode the participant's
recording to MP3 once at upload time and store only that.

Transcoding requires `ffmpeg` on PATH (installed in the backend Docker image).
Every failure path returns None so the caller can fall back to the original
bytes — a missing/broken ffmpeg must never break an interview.
"""

import logging
import os
import subprocess
import tempfile

logger = logging.getLogger(__name__)

# Formats that already play in every target browser — no transcode needed.
_PLAYABLE_EXTENSIONS = {".mp3", ".mp4", ".m4a", ".aac", ".wav"}


def needs_transcode(ext: str) -> bool:
    """True if a file with this extension should be transcoded for playback."""
    return ext.lower() not in _PLAYABLE_EXTENSIONS


def transcode_to_mp3(data: bytes, src_ext: str) -> bytes | None:
    """Transcode arbitrary audio bytes to MP3.

    Returns the MP3 bytes, or None if ffmpeg is unavailable or the conversion
    fails (callers fall back to the original recording).
    """
    if not src_ext.startswith("."):
        src_ext = "." + src_ext
    in_path = out_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=src_ext, delete=False) as fin:
            fin.write(data)
            in_path = fin.name
        out_path = in_path + ".mp3"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", in_path,
                "-vn",                      # drop any video/album-art stream
                "-acodec", "libmp3lame",
                "-q:a", "5",                # VBR ~130kbps — ample for speech
                out_path,
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
        with open(out_path, "rb") as f:
            result = f.read()
        if not result:
            logger.warning("transcode produced an empty file (src_ext=%s)", src_ext)
            return None
        return result
    except FileNotFoundError:
        logger.warning("ffmpeg not found on PATH — skipping transcode")
        return None
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or b"").decode("utf-8", "replace")[:500]
        logger.warning("ffmpeg transcode failed: %s", stderr)
        return None
    except Exception as e:  # timeout, disk, anything — never break the interview
        logger.warning("audio transcode error: %s", e)
        return None
    finally:
        for p in (in_path, out_path):
            if p:
                try:
                    os.remove(p)
                except OSError:
                    pass
