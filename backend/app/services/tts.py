import openai

from app.config import settings


def generate_speech(text: str) -> bytes:
    """Generate speech from text using OpenAI TTS and return the audio bytes."""
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )

    return response.content
