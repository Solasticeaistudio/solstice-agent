"""Tests for continuous voice listening and wake word tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestVoiceContinuous:
    def test_import(self):
        pass

    def test_schema_registration(self):
        from solstice_agent.tools.registry import ToolRegistry
        from solstice_agent.tools.voice_continuous import register_voice_continuous_tools
        registry = ToolRegistry()
        register_voice_continuous_tools(registry)
        tools = registry.list_tools()
        assert "voice_start_listening" in tools
        assert "voice_stop_listening" in tools
        assert "voice_listening_status" in tools
        assert "voice_set_wake_words" in tools
        assert "voice_get_transcript" in tools
        assert len(tools) == 5

    def test_status_when_idle(self):
        from solstice_agent.tools.voice_continuous import voice_listening_status
        result = voice_listening_status()
        assert "idle" in result.lower() or "not listening" in result.lower()

    def test_stop_when_not_listening(self):
        from solstice_agent.tools.voice_continuous import voice_stop_listening
        result = voice_stop_listening()
        assert "not listening" in result.lower() or "nothing" in result.lower()

    def test_wake_word_matching(self):
        from solstice_agent.tools.voice_continuous import _matches_wake_word
        # Positive matches
        assert _matches_wake_word("hey sol what time is it", ["hey sol", "hi sol"]) == "what time is it"
        assert _matches_wake_word("hi sol check email", ["hey sol", "hi sol"]) == "check email"
        assert _matches_wake_word("okay sol, do something", ["okay sol"]) == "do something"
        # No match
        assert _matches_wake_word("random speech", ["hey sol"]) is None
        # Wake word only (no command)
        assert _matches_wake_word("hey sol", ["hey sol"]) is None

    def test_set_wake_words(self):
        from solstice_agent.tools.voice_continuous import voice_set_wake_words
        result = voice_set_wake_words("hey agent, hi agent")
        assert "hey agent" in result.lower()
        assert "hi agent" in result.lower()

    def test_get_transcript_empty(self):
        from solstice_agent.tools.voice_continuous import voice_get_transcript
        import solstice_agent.tools.voice_continuous as mod
        mod._last_transcript = ""
        result = voice_get_transcript()
        assert "no transcript" in result.lower()

    def test_compute_rms(self):
        from solstice_agent.tools.voice_continuous import _compute_rms
        import struct
        # Silence
        silence = struct.pack("<4h", 0, 0, 0, 0)
        assert _compute_rms(silence) == 0.0
        # Loud signal
        loud = struct.pack("<4h", 32000, 32000, 32000, 32000)
        assert _compute_rms(loud) > 0.9

    def test_constants_match_iris(self):
        from solstice_agent.tools.voice_continuous import (
            SPEECH_THRESHOLD, SILENCE_DURATION_MS,
            MIN_RECORDING_MS, MAX_RECORDING_MS,
        )
        assert SPEECH_THRESHOLD == 0.035
        assert SILENCE_DURATION_MS == 800
        assert MIN_RECORDING_MS == 500
        assert MAX_RECORDING_MS == 30000
