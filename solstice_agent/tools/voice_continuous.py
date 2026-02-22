"""
Continuous Voice Listening + Wake Word Detection
==================================================
Always-on microphone with VAD and wake word support.
Constants ported from Iris Desktop (lib.rs lines 37-40).
Requires: pip install sounddevice numpy openai
"""

import io
import logging
import queue
import struct
import threading
import time
import wave
from typing import Callable, List, Optional

log = logging.getLogger("solstice.tools.voice_continuous")

# VAD constants (matching Iris Desktop)
SPEECH_THRESHOLD = 0.035
SILENCE_DURATION_MS = 800
MIN_RECORDING_MS = 500
MAX_RECORDING_MS = 30000
DEFAULT_WAKE_WORDS = ["hey sol", "hi sol", "okay sol"]
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_DURATION_MS = 100  # Process audio in 100ms chunks

# Module-level state
_listener_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_is_active = False
_wake_words: List[str] = list(DEFAULT_WAKE_WORDS)
_last_transcript = ""
_transcript_queue: queue.Queue = queue.Queue()
_on_command_callback: Optional[Callable[[str], None]] = None
_config = {
    "speech_threshold": SPEECH_THRESHOLD,
    "silence_duration_ms": SILENCE_DURATION_MS,
    "min_recording_ms": MIN_RECORDING_MS,
    "max_recording_ms": MAX_RECORDING_MS,
    "device": None,
}


# ---------------------------------------------------------------------------
# Wake word matching
# ---------------------------------------------------------------------------

def _matches_wake_word(transcript: str, wake_words: List[str]) -> Optional[str]:
    """Check if transcript starts with a wake word. Returns the command (sans wake word) or None."""
    lower = transcript.lower().strip()
    for ww in wake_words:
        ww_lower = ww.lower().strip()
        if lower.startswith(ww_lower):
            command = lower[len(ww_lower):].strip()
            # Strip common fillers after wake word
            for filler in [",", ".", "!"]:
                command = command.lstrip(filler).strip()
            return command if command else None
    return None


# ---------------------------------------------------------------------------
# Audio processing
# ---------------------------------------------------------------------------

def _compute_rms(samples: bytes) -> float:
    """Compute RMS of 16-bit PCM audio samples."""
    if len(samples) < 2:
        return 0.0
    n_samples = len(samples) // 2
    shorts = struct.unpack(f"<{n_samples}h", samples[:n_samples * 2])
    sum_sq = sum(s * s for s in shorts)
    rms = (sum_sq / n_samples) ** 0.5
    # Normalize to 0-1 range (16-bit max = 32768)
    return rms / 32768.0


def _samples_to_wav(samples: bytes, sample_rate: int) -> bytes:
    """Convert raw PCM samples to WAV bytes."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(samples)
    return buf.getvalue()


def _transcribe_audio(wav_bytes: bytes) -> str:
    """Transcribe WAV audio using OpenAI Whisper."""
    try:
        import openai
    except ImportError:
        return ""

    try:
        client = openai.OpenAI()
        buf = io.BytesIO(wav_bytes)
        buf.name = "audio.wav"
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=buf,
        )
        return result.text.strip()
    except Exception as e:
        log.error(f"Transcription failed: {e}")
        return ""


# ---------------------------------------------------------------------------
# Listener thread
# ---------------------------------------------------------------------------

def _listen_loop():
    """Main listener loop running in a background thread."""
    global _is_active, _last_transcript

    try:
        import sounddevice as sd  # noqa: F401
        import numpy as np  # noqa: F401
    except ImportError:
        log.error("Voice listening requires: pip install sounddevice numpy")
        _is_active = False
        return

    sample_rate = SAMPLE_RATE
    chunk_samples = int(sample_rate * CHUNK_DURATION_MS / 1000)
    speech_threshold = _config["speech_threshold"]
    silence_ms = _config["silence_duration_ms"]
    min_ms = _config["min_recording_ms"]
    max_ms = _config["max_recording_ms"]

    recording_buffer = bytearray()
    is_recording = False
    last_speech_time = 0.0
    recording_start_time = 0.0

    device = _config["device"]
    device_idx = None
    if device:
        # Try to find device by name
        for i, dev in enumerate(sd.query_devices()):
            if device.lower() in dev["name"].lower() and dev["max_input_channels"] > 0:
                device_idx = i
                break

    log.info(f"Starting continuous listener (threshold={speech_threshold}, device={device or 'default'})")

    try:
        stream = sd.RawInputStream(
            samplerate=sample_rate,
            channels=CHANNELS,
            dtype="int16",
            blocksize=chunk_samples,
            device=device_idx,
        )
        stream.start()
    except Exception as e:
        log.error(f"Cannot open audio stream: {e}")
        _is_active = False
        return

    try:
        while not _stop_event.is_set():
            try:
                data, overflowed = stream.read(chunk_samples)
            except Exception:
                break

            raw_bytes = bytes(data)
            rms = _compute_rms(raw_bytes)

            if rms > speech_threshold:
                if not is_recording:
                    is_recording = True
                    recording_buffer = bytearray()
                    recording_start_time = time.time()
                    log.debug("Speech detected, recording...")
                last_speech_time = time.time()
                recording_buffer.extend(raw_bytes)
            elif is_recording:
                recording_buffer.extend(raw_bytes)
                silence_elapsed_ms = (time.time() - last_speech_time) * 1000
                recording_elapsed_ms = (time.time() - recording_start_time) * 1000

                # Check if we should finalize
                should_finalize = (
                    (silence_elapsed_ms >= silence_ms and recording_elapsed_ms >= min_ms)
                    or recording_elapsed_ms >= max_ms
                )

                if should_finalize:
                    is_recording = False
                    duration_ms = recording_elapsed_ms
                    log.debug(f"Finalizing recording ({duration_ms:.0f}ms)")

                    # Transcribe in the same thread (blocking is OK, we're in bg)
                    wav_bytes = _samples_to_wav(bytes(recording_buffer), sample_rate)
                    transcript = _transcribe_audio(wav_bytes)

                    if transcript:
                        _last_transcript = transcript
                        log.info(f"Transcript: {transcript}")

                        if _wake_words:
                            command = _matches_wake_word(transcript, _wake_words)
                            if command:
                                log.info(f"Wake word matched, command: {command}")
                                _transcript_queue.put(command)
                                if _on_command_callback:
                                    _on_command_callback(command)
                        else:
                            # No wake words = push-to-talk style, every utterance is a command
                            _transcript_queue.put(transcript)
                            if _on_command_callback:
                                _on_command_callback(transcript)

                    recording_buffer = bytearray()
    finally:
        stream.stop()
        stream.close()
        _is_active = False
        log.info("Listener stopped")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def set_command_callback(callback: Optional[Callable[[str], None]]):
    """Set a callback for when a voice command is detected (for CLI integration)."""
    global _on_command_callback
    _on_command_callback = callback


def voice_start_listening(
    wake_words: Optional[str] = None,
    speech_threshold: float = SPEECH_THRESHOLD,
    silence_duration_ms: int = SILENCE_DURATION_MS,
    min_recording_ms: int = MIN_RECORDING_MS,
    max_recording_ms: int = MAX_RECORDING_MS,
    device: Optional[str] = None,
) -> str:
    """Start continuous voice listening with wake word detection and VAD."""
    global _listener_thread, _is_active, _wake_words

    try:
        import sounddevice  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return "Error: Voice listening requires: pip install sounddevice numpy"

    if _is_active:
        return "Already listening. Use voice_stop_listening first."

    if wake_words is not None:
        _wake_words = [w.strip() for w in wake_words.split(",") if w.strip()]
    else:
        _wake_words = list(DEFAULT_WAKE_WORDS)

    _config.update({
        "speech_threshold": speech_threshold,
        "silence_duration_ms": silence_duration_ms,
        "min_recording_ms": min_recording_ms,
        "max_recording_ms": max_recording_ms,
        "device": device,
    })

    _stop_event.clear()
    _is_active = True

    _listener_thread = threading.Thread(target=_listen_loop, daemon=True)
    _listener_thread.start()

    ww_str = ", ".join(f'"{w}"' for w in _wake_words) if _wake_words else "(none — all speech triggers)"
    return f"Listening started. Wake words: {ww_str}. Device: {device or 'default'}."


def voice_stop_listening() -> str:
    """Stop continuous voice listening."""
    global _listener_thread, _is_active

    if not _is_active:
        return "Not listening. Nothing to stop."

    _stop_event.set()
    if _listener_thread and _listener_thread.is_alive():
        _listener_thread.join(timeout=5)
    _listener_thread = None
    _is_active = False
    return "Listening stopped."


def voice_listening_status() -> str:
    """Get the current voice listening status."""
    if not _is_active:
        return "Status: idle (not listening)"

    ww_str = ", ".join(_wake_words) if _wake_words else "(none)"
    device = _config.get("device") or "default"
    return (
        f"Status: active\n"
        f"  Wake words: {ww_str}\n"
        f"  Device: {device}\n"
        f"  Threshold: {_config['speech_threshold']}\n"
        f"  Last transcript: {_last_transcript or '(none yet)'}"
    )


def voice_set_wake_words(wake_words: str) -> str:
    """Update wake words while listening."""
    global _wake_words
    _wake_words = [w.strip() for w in wake_words.split(",") if w.strip()]
    ww_str = ", ".join(f'"{w}"' for w in _wake_words)
    return f"Wake words updated: {ww_str}"


def voice_get_transcript() -> str:
    """Get the most recent voice transcript."""
    if not _last_transcript:
        return "(no transcript yet)"
    return _last_transcript


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "voice_start_listening": {
        "name": "voice_start_listening",
        "description": (
            "Start always-on voice listening with VAD and optional wake word. "
            "Default wake words: 'hey sol', 'hi sol', 'okay sol'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "wake_words": {
                    "type": "string",
                    "description": "Comma-separated wake words (e.g. 'hey sol,hi sol')",
                },
                "speech_threshold": {
                    "type": "number",
                    "description": "RMS threshold for speech detection (default 0.035)",
                },
                "silence_duration_ms": {
                    "type": "integer",
                    "description": "Silence duration to end recording (default 800ms)",
                },
                "min_recording_ms": {
                    "type": "integer",
                    "description": "Minimum recording duration (default 500ms)",
                },
                "max_recording_ms": {
                    "type": "integer",
                    "description": "Maximum recording duration (default 30000ms)",
                },
                "device": {
                    "type": "string",
                    "description": "Audio input device name (default: system default)",
                },
            },
            "required": [],
        },
    },
    "voice_stop_listening": {
        "name": "voice_stop_listening",
        "description": "Stop continuous voice listening and release the microphone.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "voice_listening_status": {
        "name": "voice_listening_status",
        "description": "Get the current voice listening status (active/idle, wake words, device).",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "voice_set_wake_words": {
        "name": "voice_set_wake_words",
        "description": "Update wake words while listening is active.",
        "parameters": {
            "type": "object",
            "properties": {
                "wake_words": {
                    "type": "string",
                    "description": "New comma-separated wake words",
                },
            },
            "required": ["wake_words"],
        },
    },
    "voice_get_transcript": {
        "name": "voice_get_transcript",
        "description": "Get the most recent voice transcript from the last detected speech.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}


def register_voice_continuous_tools(registry):
    """Register continuous voice / wake word tools."""
    registry.register("voice_start_listening", voice_start_listening, _SCHEMAS["voice_start_listening"])
    registry.register("voice_stop_listening", voice_stop_listening, _SCHEMAS["voice_stop_listening"])
    registry.register("voice_listening_status", voice_listening_status, _SCHEMAS["voice_listening_status"])
    registry.register("voice_set_wake_words", voice_set_wake_words, _SCHEMAS["voice_set_wake_words"])
    registry.register("voice_get_transcript", voice_get_transcript, _SCHEMAS["voice_get_transcript"])
