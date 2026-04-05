import os
import tempfile

import edge_tts
from mutagen.mp3 import MP3
from pydub import AudioSegment

from .settings import get_setting

DEFAULT_VOICE = os.environ.get("TTS_VOICE", "en-US-GuyNeural")

VOICE_OPTIONS = [
    ("en-US-AndrewMultilingualNeural", "Andrew (US Male)"),
    ("en-US-AvaMultilingualNeural", "Ava (US Female)"),
    ("en-US-BrianMultilingualNeural", "Brian (US Male)"),
    ("en-US-EmmaMultilingualNeural", "Emma (US Female)"),
    ("en-US-GuyNeural", "Guy (US Male)"),
    ("en-US-JennyNeural", "Jenny (US Female)"),
    ("en-US-AriaNeural", "Aria (US Female)"),
    ("en-US-ChristopherNeural", "Christopher (US Male)"),
    ("en-US-MichelleNeural", "Michelle (US Female)"),
    ("en-US-RogerNeural", "Roger (US Male)"),
    ("en-GB-RyanNeural", "Ryan (British Male)"),
    ("en-GB-SoniaNeural", "Sonia (British Female)"),
    ("en-GB-ThomasNeural", "Thomas (British Male)"),
    ("en-GB-LibbyNeural", "Libby (British Female)"),
    ("en-AU-WilliamMultilingualNeural", "William (Australian Male)"),
    ("en-AU-NatashaNeural", "Natasha (Australian Female)"),
]

OPENAI_VOICE_OPTIONS = [
    ("alloy", "Alloy"),
    ("ash", "Ash"),
    ("ballad", "Ballad"),
    ("coral", "Coral"),
    ("echo", "Echo"),
    ("fable", "Fable"),
    ("nova", "Nova"),
    ("onyx", "Onyx"),
    ("sage", "Sage"),
    ("shimmer", "Shimmer"),
]

PODCAST_VOICE_A = os.environ.get("PODCAST_VOICE_A", "en-US-AndrewMultilingualNeural")
PODCAST_VOICE_B = os.environ.get("PODCAST_VOICE_B", "en-US-AvaMultilingualNeural")

OPENAI_PODCAST_VOICE_A = "ash"
OPENAI_PODCAST_VOICE_B = "nova"


def get_voice_options() -> list:
    """Return voice options for the active TTS engine."""
    engine = get_setting("tts_engine", "edge")
    if engine == "openai":
        return OPENAI_VOICE_OPTIONS
    return VOICE_OPTIONS


async def generate_audio(text: str, output_path: str, voice: str = None) -> float:
    """Generate MP3 audio from text. Returns duration in seconds."""
    engine = get_setting("tts_engine", "edge")
    if engine == "openai":
        return await _generate_openai(text, output_path, voice)
    return await _generate_edge(text, output_path, voice)


async def generate_podcast_audio(segments: list[dict], output_path: str) -> float:
    """Generate multi-voice podcast audio from script segments. Returns duration."""
    engine = get_setting("tts_engine", "edge")
    if engine == "openai":
        return await _generate_podcast_openai(segments, output_path)
    return await _generate_podcast_edge(segments, output_path)


# --- Edge TTS ---

async def _generate_edge(text: str, output_path: str, voice: str = None) -> float:
    voice = voice or DEFAULT_VOICE
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)
    return MP3(output_path).info.length


async def _generate_podcast_edge(segments: list[dict], output_path: str) -> float:
    voices = {"A": PODCAST_VOICE_A, "B": PODCAST_VOICE_B}
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, seg in enumerate(segments):
            voice = voices.get(seg["speaker"], voices["A"])
            tmp_path = os.path.join(tmpdir, f"seg_{i}.mp3")
            communicate = edge_tts.Communicate(seg["text"], voice)
            await communicate.save(tmp_path)
            combined += AudioSegment.from_mp3(tmp_path) + pause

    combined.export(output_path, format="mp3")
    return MP3(output_path).info.length


# --- OpenAI TTS ---

def _get_openai_client():
    from openai import AsyncOpenAI
    api_key = get_setting("openai_api_key")
    if not api_key:
        raise ValueError("OpenAI API key not configured — set it in Settings")
    return AsyncOpenAI(api_key=api_key)


async def _generate_openai(text: str, output_path: str, voice: str = None) -> float:
    client = _get_openai_client()
    voice = voice or "alloy"
    # OpenAI TTS has a ~4096 char limit per request, chunk if needed
    chunks = _chunk_text(text, 4000)
    combined = AudioSegment.empty()

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, chunk in enumerate(chunks):
            tmp_path = os.path.join(tmpdir, f"chunk_{i}.mp3")
            response = await client.audio.speech.create(
                model=get_setting("openai_tts_model", "tts-1"),
                voice=voice,
                input=chunk,
                response_format="mp3",
            )
            await response.astream_to_file(tmp_path)
            combined += AudioSegment.from_mp3(tmp_path)

    combined.export(output_path, format="mp3")
    return MP3(output_path).info.length


async def _generate_podcast_openai(segments: list[dict], output_path: str) -> float:
    client = _get_openai_client()
    voices = {"A": OPENAI_PODCAST_VOICE_A, "B": OPENAI_PODCAST_VOICE_B}
    model = get_setting("openai_tts_model", "tts-1")
    combined = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)

    with tempfile.TemporaryDirectory() as tmpdir:
        for i, seg in enumerate(segments):
            voice = voices.get(seg["speaker"], voices["A"])
            tmp_path = os.path.join(tmpdir, f"seg_{i}.mp3")
            response = await client.audio.speech.create(
                model=model,
                voice=voice,
                input=seg["text"],
                response_format="mp3",
            )
            await response.astream_to_file(tmp_path)
            combined += AudioSegment.from_mp3(tmp_path) + pause

    combined.export(output_path, format="mp3")
    return MP3(output_path).info.length


def _chunk_text(text: str, max_chars: int) -> list[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= max_chars:
        return [text]
    chunks = []
    current = ""
    for sentence in text.replace(". ", ".\n").split("\n"):
        if len(current) + len(sentence) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = ""
        current += sentence + " "
    if current.strip():
        chunks.append(current.strip())
    return chunks
