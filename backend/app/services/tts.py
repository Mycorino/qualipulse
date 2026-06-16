import httpx
import openai

from app.config import settings
from app.services._clients import call_openai_with_retries


def generate_speech(text: str) -> bytes:
    """Generate speech from text using OpenAI TTS and return the audio bytes."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))

    response = call_openai_with_retries(
        lambda: client.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=text,
        ),
        label="openai tts",
    )

    return response.content
