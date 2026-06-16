import httpx
import openai

from app.config import settings
from app.services._clients import call_openai_with_retries


def transcribe_audio(
    audio_data: bytes, filename: str = "recording.webm"
) -> tuple[str, float, list[dict]]:
    """Transcribe audio bytes using OpenAI Whisper.

    Returns (transcript_text, duration_seconds, segments).
    Each segment is a dict with keys: start (float seconds), end (float
    seconds), text (str). Segments power sentence-level highlighting in
    the researcher transcript view; if Whisper returns no segments
    (very short audio), the list is empty and the transcript still
    renders without highlighting.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))

    transcript = call_openai_with_retries(
        lambda: client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_data),
            response_format="verbose_json",
        ),
        label="whisper transcribe",
    )

    duration = float(getattr(transcript, "duration", 0.0) or 0.0)

    raw_segments = getattr(transcript, "segments", None) or []
    segments: list[dict] = []
    for seg in raw_segments:
        # The OpenAI SDK returns Pydantic objects in newer versions and
        # dicts in older ones. Handle both.
        get = (lambda k: getattr(seg, k, None)) if hasattr(seg, "start") else seg.get
        try:
            segments.append({
                "start": float(get("start") or 0.0),
                "end": float(get("end") or 0.0),
                "text": str(get("text") or "").strip(),
            })
        except (TypeError, ValueError):
            continue

    return transcript.text, duration, segments
