import httpx
import openai

from app.config import settings
from app.services._clients import call_openai_with_retries


def transcribe_audio(
    audio_data: bytes,
    filename: str = "recording.webm",
    language: str | None = None,
    prompt: str | None = None,
) -> tuple[str, float, list[dict]]:
    """Transcribe audio bytes using OpenAI Whisper.

    ``language`` is an ISO-639-1 hint (e.g. "fr") from the project's
    interview language. Passing it measurably lowers Whisper's error rate
    on non-English speech and prevents code-switching misdetection on
    short answers; omit/None keeps Whisper's auto-detect.

    ``prompt`` is an optional glossary (study name, brands, product terms)
    that biases Whisper's decoding toward the right spelling of proper
    nouns ("Air France" rather than "la France"). Capped to ~800 chars so
    it stays under Whisper's 224-token prompt window.

    Returns (transcript_text, duration_seconds, segments).
    Each segment is a dict with keys: start (float seconds), end (float
    seconds), text (str), no_speech_prob (float 0..1, Whisper's own
    estimate that the segment is not speech; the interview engine uses it
    to catch muted-mic clips whose text is hallucinated filler). Segments
    power sentence-level highlighting in the researcher transcript view;
    if Whisper returns no segments (very short audio), the list is empty
    and the transcript still renders without highlighting.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))

    kwargs: dict = {}
    lang = (language or "").strip().lower()[:2]
    if lang:
        kwargs["language"] = lang
    glossary = (prompt or "").strip()
    if glossary:
        kwargs["prompt"] = glossary[:800]

    transcript = call_openai_with_retries(
        lambda: client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, audio_data),
            response_format="verbose_json",
            **kwargs,
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
                "no_speech_prob": float(get("no_speech_prob") or 0.0),
            })
        except (TypeError, ValueError):
            continue

    return transcript.text, duration, segments
