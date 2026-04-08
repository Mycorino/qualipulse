import openai

from app.config import settings


def transcribe_audio(
    audio_data: bytes, filename: str = "recording.webm"
) -> tuple[str, float]:
    """Transcribe audio bytes using OpenAI Whisper.

    Returns (transcript_text, duration_seconds).
    Uses verbose_json to obtain the audio duration for usage tracking.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, audio_data),
        response_format="verbose_json",
    )

    duration = float(getattr(transcript, "duration", 0.0) or 0.0)
    return transcript.text, duration
