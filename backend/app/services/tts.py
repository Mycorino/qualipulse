import openai

from app.config import settings


def generate_speech(text: str, output_path: str) -> str:
    """Generate speech from text using OpenAI TTS and save to output_path.

    Returns the output_path for convenience.
    """
    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    response = client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=text,
    )

    response.stream_to_file(output_path)

    return output_path
