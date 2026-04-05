import os
import tempfile

import edge_tts
from mutagen.mp3 import MP3
from pydub import AudioSegment

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

PODCAST_VOICE_A = os.environ.get("PODCAST_VOICE_A", "en-US-AndrewMultilingualNeural")
PODCAST_VOICE_B = os.environ.get("PODCAST_VOICE_B", "en-US-AvaMultilingualNeural")


async def generate_audio(text: str, output_path: str, voice: str = None) -> float:
    """Generate MP3 audio from text using edge-tts. Returns duration in seconds."""
    voice = voice or DEFAULT_VOICE
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

    audio = MP3(output_path)
    return audio.info.length


async def generate_podcast_audio(segments: list[dict], output_path: str) -> float:
    """Generate multi-voice podcast audio from script segments. Returns duration."""
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
    audio = MP3(output_path)
    return audio.info.length
