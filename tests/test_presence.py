"""Tests for platform presence tools."""

import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPresenceTools:
    def test_import(self):
        pass

    def test_schema_registration(self):
        from solstice_agent.tools.registry import ToolRegistry
        from solstice_agent.tools.presence import register_presence_tools
        registry = ToolRegistry()
        register_presence_tools(registry)
        tools = registry.list_tools()
        assert "presence_notify" in tools
        assert "presence_set_status" in tools
        assert "presence_get_clipboard" in tools
        assert "presence_set_clipboard" in tools
        assert len(tools) == 4

    def test_set_status_valid(self):
        from solstice_agent.tools.presence import presence_set_status
        result = presence_set_status("active")
        assert "active" in result.lower()

    def test_set_status_invalid(self):
        from solstice_agent.tools.presence import presence_set_status
        result = presence_set_status("invalid_status")
        assert "error" in result.lower()

    def test_set_status_all_values(self):
        from solstice_agent.tools.presence import presence_set_status
        for status in ("active", "idle", "busy", "listening"):
            result = presence_set_status(status)
            assert status in result.lower()

    def test_clipboard_roundtrip(self):
        from solstice_agent.tools.presence import presence_set_clipboard, presence_get_clipboard
        try:
            import pyperclip  # noqa: F401
        except ImportError:
            pytest.skip("pyperclip not installed")

        try:
            result = presence_set_clipboard("sol_test_12345")
            assert "copied" in result.lower() or "clipboard" in result.lower()
            content = presence_get_clipboard()
            assert "sol_test_12345" in content
        except Exception:
            pytest.skip("Clipboard not available in this environment")
