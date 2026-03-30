import openai

from app.config import settings


def transcribe_audio(file_path: str) -> str:
    """Transcribe an audio file using OpenAI Whisper and return the text."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )

    return transcript.text
