import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solstice_agent.agent.providers.gemini_provider import GeminiProvider
from solstice_agent.cli import _first_run_needs_onboarding
from solstice_agent.config import CONFIG_FILENAME, default_config_path


def test_default_config_path_prefers_user_config_home(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    expected = tmp_path / ".config" / "solstice-agent" / CONFIG_FILENAME
    assert default_config_path() == expected


def test_first_run_onboarding_requires_tty_and_no_config(monkeypatch, tmp_path):
    monkeypatch.setattr("solstice_agent.cli.find_config_path", lambda path=None: None)
    monkeypatch.setattr("solstice_agent.cli.provider_env_snapshot", lambda: {})

    with patch("sys.stdin.isatty", return_value=True):
        assert _first_run_needs_onboarding(None) is True

    with patch("sys.stdin.isatty", return_value=False):
        assert _first_run_needs_onboarding(None) is False


def test_gemini_provider_normalizes_conflicting_env_vars(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "stale-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fresh-key")

    provider = GeminiProvider(api_key="configured-key")
    provider._normalize_process_env()

    assert os.environ["GOOGLE_API_KEY"] == "configured-key"
    assert "GEMINI_API_KEY" not in os.environ
