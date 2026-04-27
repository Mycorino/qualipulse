from typing import Iterator

import httpx
import openai

from app.config import settings


def generate_speech(text: str) -> bytes:
    """Generate speech from text using OpenAI TTS and return the audio bytes.

    Kept as a synchronous fallback for tests and code paths that need the full
    bytes up front (e.g. demo seeding, batch upload).
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))

    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )

    return response.content


def generate_speech_streaming(text: str) -> Iterator[bytes]:
    """Stream TTS audio bytes from OpenAI. Yields MP3 chunks as they arrive.

    Use this for real-time playback to participants — the first chunk arrives
    in ~300-500ms vs ~2-3s for the full file via generate_speech().
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))
    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice="alloy",
        input=text,
        response_format="mp3",
    ) as response:
        for chunk in response.iter_bytes(chunk_size=4096):
            if chunk:
                yield chunk
