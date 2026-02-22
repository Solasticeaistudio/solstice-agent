"""Tests for screen and camera recording tools."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestRecording:
    def test_import(self):
        pass

    def test_schema_registration(self):
        from solstice_agent.tools.registry import ToolRegistry
        from solstice_agent.tools.recording import register_recording_tools
        registry = ToolRegistry()
        register_recording_tools(registry)
        tools = registry.list_tools()
        assert "recording_start" in tools
        assert "recording_stop" in tools
        assert "recording_status" in tools
        assert "camera_capture" in tools
        assert "camera_list" in tools
        assert len(tools) == 5

    def test_status_when_idle(self):
        from solstice_agent.tools.recording import recording_status
        result = recording_status()
        assert "idle" in result.lower() or "not recording" in result.lower()

    def test_stop_when_not_recording(self):
        from solstice_agent.tools.recording import recording_stop
        result = recording_stop()
        assert "not recording" in result.lower() or "nothing" in result.lower()

    def test_quality_presets(self):
        from solstice_agent.tools.recording import _QUALITY_PRESETS
        assert "low" in _QUALITY_PRESETS
        assert "medium" in _QUALITY_PRESETS
        assert "high" in _QUALITY_PRESETS
        assert _QUALITY_PRESETS["low"]["fps"] < _QUALITY_PRESETS["high"]["fps"]
        assert _QUALITY_PRESETS["low"]["scale"] < _QUALITY_PRESETS["high"]["scale"]

    def test_start_without_deps(self):
        from solstice_agent.tools.recording import recording_start
        import solstice_agent.tools.recording as mod
        # If deps aren't installed, should return error string
        result = recording_start()
        assert isinstance(result, str)
        # Clean up if it actually started
        if "started" in result.lower():
            mod.recording_stop()
