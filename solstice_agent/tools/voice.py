"""
Voice Tools
============
Text-to-speech (ElevenLabs) and speech-to-text (OpenAI Whisper).
Enables voice interaction — the agent can speak and listen.

TTS requires: pip install elevenlabs
STT requires: pip install openai
"""

import logging
import os
import tempfile
from typing import Optional

log = logging.getLogger("solstice.tools.voice")


def voice_speak(text: str, voice: str = "Josh", model: str = "eleven_turbo_v2") -> str:
    """
    Convert text to speech using ElevenLabs and play/save the audio.
    Returns the path to the saved audio file.
    """
    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        return "Error: Voice TTS requires: pip install elevenlabs"

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return "Error: Set ELEVENLABS_API_KEY environment variable."

    try:
        client = ElevenLabs(api_key=api_key)
        audio_gen = client.text_to_speech.convert(
            text=text,
            voice_id=_resolve_voice(client, voice),
            model_id=model,
            output_format="mp3_44100_128",
        )

        # Collect audio chunks
        audio_bytes = b"".join(audio_gen)

        # Save to temp file
        path = os.path.join(tempfile.gettempdir(), "sol_tts_output.mp3")
        with open(path, "wb") as f:
            f.write(audio_bytes)

        # Try to play it
        _try_play(path)

        return f"Speech saved to {path} ({len(audio_bytes)} bytes, voice: {voice})"
    except Exception:
        log.exception("TTS failed")
        return "Text-to-speech failed. Check your ElevenLabs API key and try again."


def voice_listen(audio_path: Optional[str] = None, duration: int = 5) -> str:
    """
    Transcribe speech to text. Provide a path to an audio file, or
    record from microphone for the specified duration (seconds).
    """
    try:
        from openai import OpenAI
    except ImportError:
        return "Error: Voice STT requires: pip install openai"

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "Error: Set OPENAI_API_KEY environment variable for Whisper STT."

    if audio_path and not os.path.isfile(audio_path):
        return f"Audio file not found: {audio_path}"

    # If no file provided, try to record from mic
    if not audio_path:
        audio_path = _record_mic(duration)
        if audio_path.startswith("Error"):
            return audio_path

    try:
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as f:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=f,
                response_format="text",
            )
        text = transcript.strip() if isinstance(transcript, str) else str(transcript).strip()
        return f"Transcription: {text}"
    except Exception:
        log.exception("STT failed")
        return "Speech-to-text failed. Check the audio file format and your OpenAI API key."


def voice_list_voices() -> str:
    """List available ElevenLabs voices."""
    try:
        from elevenlabs import ElevenLabs
    except ImportError:
        return "Error: Requires: pip install elevenlabs"

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return "Error: Set ELEVENLABS_API_KEY environment variable."

    try:
        client = ElevenLabs(api_key=api_key)
        voices = client.voices.get_all()
        lines = ["Available voices:"]
        for v in voices.voices[:20]:
            labels = ", ".join(f"{k}: {val}" for k, val in (v.labels or {}).items())
            lines.append(f"  {v.name} ({v.voice_id}) — {labels or 'no labels'}")
        if len(voices.voices) > 20:
            lines.append(f"  ... and {len(voices.voices) - 20} more")
        return "\n".join(lines)
    except Exception:
        log.exception("Failed to list voices")
        return "Failed to list voices. Check your API key."


def _resolve_voice(client, voice_name: str) -> str:
    """Resolve a voice name to its ID. If it looks like an ID already, return as-is."""
    if len(voice_name) > 15 and " " not in voice_name:
        return voice_name  # Already an ID

    try:
        voices = client.voices.get_all()
        for v in voices.voices:
            if v.name.lower() == voice_name.lower():
                return v.voice_id
    except Exception:
        pass

    return voice_name  # Fall back to using as ID


def _record_mic(duration: int) -> str:
    """Record audio from microphone. Returns path to WAV file or error string."""
    try:
        import sounddevice as sd
        import numpy as np  # noqa: F401 — required by sounddevice for recording
    except ImportError:
        return "Error: Microphone recording requires: pip install sounddevice numpy"

    try:
        sample_rate = 16000
        log.info(f"Recording {duration}s from microphone...")
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype="int16")
        sd.wait()

        path = os.path.join(tempfile.gettempdir(), "sol_mic_recording.wav")
        import wave
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio.tobytes())

        return path
    except Exception:
        log.exception("Mic recording failed")
        return "Error: Failed to record from microphone. Check audio input device."


def _try_play(path: str):
    """Best-effort audio playback."""
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            # Windows: use powershell to play audio
            subprocess.Popen(
                ["powershell", "-c", f"(New-Object Media.SoundPlayer '{path}').PlaySync()"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        elif sys.platform == "darwin":
            subprocess.Popen(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["aplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # Playback is best-effort


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "voice_speak": {
        "name": "voice_speak",
        "description": (
            "Convert text to speech using ElevenLabs and play/save the audio. "
            "Returns the file path. Requires ELEVENLABS_API_KEY env var."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to speak"},
                "voice": {"type": "string", "description": "Voice name (default 'Josh'). Use voice_list_voices to see options."},
                "model": {"type": "string", "description": "ElevenLabs model (default 'eleven_turbo_v2')"},
            },
            "required": ["text"],
        },
    },
    "voice_listen": {
        "name": "voice_listen",
        "description": (
            "Transcribe speech to text using OpenAI Whisper. Provide an audio file path, "
            "or omit to record from microphone. Requires OPENAI_API_KEY."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "audio_path": {"type": "string", "description": "Path to audio file (WAV, MP3, etc.). Omit to record from mic."},
                "duration": {"type": "integer", "description": "Recording duration in seconds if using mic (default 5)"},
            },
            "required": [],
        },
    },
    "voice_list_voices": {
        "name": "voice_list_voices",
        "description": "List available ElevenLabs voices with their IDs and labels.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_voice_tools(registry):
    """Register voice tools with a ToolRegistry."""
    registry.register("voice_speak", voice_speak, _SCHEMAS["voice_speak"])
    registry.register("voice_listen", voice_listen, _SCHEMAS["voice_listen"])
    registry.register("voice_list_voices", voice_list_voices, _SCHEMAS["voice_list_voices"])
