"""Tests for screen capture and annotation tools."""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestScreenTools:
    def test_import(self):
        pass

    def test_schema_registration(self):
        from solstice_agent.tools.registry import ToolRegistry
        from solstice_agent.tools.screen import register_screen_tools
        registry = ToolRegistry()
        register_screen_tools(registry)
        tools = registry.list_tools()
        assert "screen_capture" in tools
        assert "screen_capture_window" in tools
        assert "screen_list_displays" in tools
        assert "screen_annotate" in tools
        assert len(tools) == 4

    def test_screen_annotate_circle(self):
        from solstice_agent.tools.screen import screen_annotate
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.png")
            Image.new("RGB", (200, 200), "white").save(path)
            annotations = json.dumps([
                {"type": "circle", "x": 100, "y": 100, "radius": 30, "color": "red"},
            ])
            result = screen_annotate(path, annotations)
            assert "annotated" in result.lower() or "saved" in result.lower()

    def test_screen_annotate_multiple_types(self):
        from solstice_agent.tools.screen import screen_annotate
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.png")
            out = os.path.join(tmp, "out.png")
            Image.new("RGB", (400, 400), "white").save(path)
            annotations = json.dumps([
                {"type": "circle", "x": 50, "y": 50, "radius": 20, "color": "red"},
                {"type": "arrow", "x1": 10, "y1": 10, "x2": 100, "y2": 100, "color": "blue"},
                {"type": "rectangle", "x": 150, "y": 150, "width": 80, "height": 40, "color": "green"},
                {"type": "text", "x": 200, "y": 200, "text": "Hello", "color": "black"},
                {"type": "highlight", "x": 50, "y": 300, "width": 200, "height": 30, "color": "yellow", "opacity": 0.3},
            ])
            result = screen_annotate(path, annotations, output_path=out)
            assert "5 annotations" in result
            assert os.path.isfile(out)

    def test_screen_annotate_invalid_json(self):
        from solstice_agent.tools.screen import screen_annotate
        try:
            from PIL import Image
        except ImportError:
            pytest.skip("Pillow not installed")

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.png")
            Image.new("RGB", (100, 100), "white").save(path)
            result = screen_annotate(path, "not valid json")
            assert "error" in result.lower()

    def test_screen_annotate_file_not_found(self):
        from solstice_agent.tools.screen import screen_annotate
        result = screen_annotate("/nonexistent/path.png", "[]")
        assert "error" in result.lower()

    def test_screen_capture_invalid_region(self):
        from solstice_agent.tools.screen import screen_capture
        result = screen_capture(region="bad")
        assert "error" in result.lower()

    def test_screen_capture_invalid_monitor(self):
        from solstice_agent.tools.screen import screen_capture
        try:
            import mss  # noqa: F401
        except ImportError:
            pytest.skip("mss not installed")
        result = screen_capture(monitor=99)
        assert "error" in result.lower() or "not found" in result.lower()
