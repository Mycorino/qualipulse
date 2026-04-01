import openai

from app.config import settings


def transcribe_audio(audio_data: bytes, filename: str = "recording.webm") -> str:
    """Transcribe audio bytes using OpenAI Whisper and return the text."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    transcript = client.audio.transcriptions.create(
        model="whisper-1",
        file=(filename, audio_data),
    )

    return transcript.text
