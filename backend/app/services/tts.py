import logging

import httpx
import openai

from app.config import settings
from app.services._clients import call_openai_with_retries

logger = logging.getLogger("app.tts")

_LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Mandarin Chinese",
}


def _voice_instructions(language: str | None) -> str:
    """Steering for gpt-4o-mini-tts: native accent + interviewer tone."""
    lang_name = _LANGUAGE_NAMES.get((language or "en")[:2].lower(), "English")
    return (
        f"Speak {lang_name} like a native speaker, with a natural {lang_name} accent. "
        "You are a warm, professional research interviewer: conversational, unhurried, "
        "genuinely curious. No radio-host energy, no exaggerated enthusiasm."
    )


def generate_speech(text: str, language: str | None = None) -> bytes:
    """Generate speech from text using OpenAI TTS and return the audio bytes.

    Uses the model/voice pinned in settings (default gpt-4o-mini-tts + coral,
    with per-language accent instructions). If the newer model fails, e.g. the
    account lacks access, falls back to tts-1/alloy so an interview never dies
    on a voice upgrade.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY, timeout=httpx.Timeout(60.0))

    model = settings.TTS_MODEL or "tts-1"
    voice = settings.TTS_VOICE or "alloy"
    kwargs: dict = {"model": model, "voice": voice, "input": text}
    # `instructions` is only supported by the gpt-4o-mini-tts family.
    if model.startswith("gpt-"):
        kwargs["instructions"] = _voice_instructions(language)

    try:
        response = call_openai_with_retries(
            lambda: client.audio.speech.create(**kwargs),
            label="openai tts",
        )
        return response.content
    except Exception:
        if model == "tts-1":
            raise
        logger.warning("TTS model %s failed; falling back to tts-1/alloy", model)
        response = call_openai_with_retries(
            lambda: client.audio.speech.create(model="tts-1", voice="alloy", input=text),
            label="openai tts fallback",
        )
        return response.content
