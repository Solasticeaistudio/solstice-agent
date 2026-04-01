import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from solstice_agent.agent.providers.gemini_provider import GeminiProvider
from solstice_agent.cli import _first_run_needs_onboarding, _guided_quickstart_options, _run_guided_quickstart
from solstice_agent.config import CONFIG_FILENAME, Config, default_config_path
from solstice_agent.setup import _next_steps, _post_setup_checks, run_setup


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


def test_first_run_onboarding_still_runs_when_provider_keys_exist(monkeypatch):
    monkeypatch.setattr("solstice_agent.cli.find_config_path", lambda path=None: None)
    monkeypatch.setattr("solstice_agent.cli.provider_env_snapshot", lambda: {"GEMINI_API_KEY": "key"})

    with patch("sys.stdin.isatty", return_value=True):
        assert _first_run_needs_onboarding(None) is True


def test_gemini_provider_normalizes_conflicting_env_vars(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "stale-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fresh-key")

    provider = GeminiProvider(api_key="configured-key")
    provider._normalize_process_env()

    assert os.environ["GOOGLE_API_KEY"] == "configured-key"
    assert "GEMINI_API_KEY" not in os.environ


def test_run_setup_writes_profile_and_workspace_root(monkeypatch, tmp_path):
    config_path = tmp_path / "solstice-agent.yaml"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "SOLSTICE_PROVIDER",
        "SOLSTICE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    answers = iter([
        "",   # press enter to start
        "4",  # Ollama
        "",   # default model
        "y",  # Ollama already running
        "",   # default Ollama URL
        "2",  # developer profile
        str(workspace_root),
        "n",  # no custom terminal/web overrides
        "n",  # no gateway/channel setup
        "y",  # save config
    ])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("solstice_agent.setup.time.sleep", lambda _seconds: None)

    run_setup(str(config_path))

    config = Config.load(str(config_path))
    assert config.provider == "ollama"
    assert config.runtime_profile == "developer"
    assert config.workspace_root == str(workspace_root)
    assert config.ollama_base_url == "http://localhost:11434"
    assert config.enable_terminal is None
    assert config.enable_web is None


def test_run_setup_gateway_mode_persists_workspace_root(monkeypatch, tmp_path):
    config_path = tmp_path / "solstice-agent.yaml"
    workspace_root = tmp_path / "gateway-root"
    workspace_root.mkdir()
    for name in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "SOLSTICE_PROVIDER",
        "SOLSTICE_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    answers = iter([
        "",   # press enter to start
        "4",  # Ollama
        "",   # default model
        "y",  # Ollama already running
        "",   # default Ollama URL
        "3",  # gateway profile
        str(workspace_root),
        "n",  # no custom terminal/web overrides
        "n",  # do not configure channels now
        "y",  # save config
    ])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("solstice_agent.setup.time.sleep", lambda _seconds: None)

    run_setup(str(config_path))

    config = Config.load(str(config_path))
    assert config.runtime_profile == "gateway"
    assert config.workspace_root == str(workspace_root)
    assert config.gateway_enabled is False


def test_run_setup_warns_when_provider_extra_missing(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "solstice-agent.yaml"

    answers = iter([
        "",            # press enter to start
        "1",           # OpenAI
        "",            # default model
        "sk-test",     # API key
        "1",           # local_safe profile
        str(tmp_path), # workspace root
        "n",           # no custom overrides
        "n",           # no channel setup
        "n",           # do not save
    ])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("solstice_agent.setup.time.sleep", lambda _seconds: None)
    monkeypatch.setattr("solstice_agent.setup._provider_extra_installed", lambda provider: False)

    run_setup(str(config_path))

    output = capsys.readouterr().out
    assert 'pip install "solstice-agent[openai]"' in output


def test_run_setup_prints_starter_prompts(monkeypatch, tmp_path, capsys):
    config_path = tmp_path / "solstice-agent.yaml"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    answers = iter([
        "",            # press enter to start
        "1",           # OpenAI
        "",            # default model
        "sk-test",     # API key
        "1",           # everyday/local_safe
        str(workspace_root),
        "n",           # no custom overrides
        "n",           # no channel setup
        "y",           # save
    ])

    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("solstice_agent.setup.time.sleep", lambda _seconds: None)

    run_setup(str(config_path))

    output = capsys.readouterr().out
    assert "A few easy starter things you can ask me:" in output
    assert "What can you help me with on this computer?" in output


def test_guided_quickstart_options_are_plain_language():
    options = _guided_quickstart_options(Config(runtime_profile="local_safe"))
    labels = [label for label, _prompt in options]
    assert "Help around my files" in labels
    assert "Set up reminders" in labels
    assert "Learn what you can do" in labels
    assert "Connect apps or get organized" in labels


def test_guided_quickstart_can_launch_first_prompt(monkeypatch, capsys):
    class DummyProvider:
        def name(self):
            return "dummy"

    class DummyAgent:
        def __init__(self):
            self.provider = DummyProvider()
            self.prompts = []

        def chat(self, prompt):
            self.prompts.append(prompt)
            return "started"

    agent = DummyAgent()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "1")
    _run_guided_quickstart(agent, Config(runtime_profile="local_safe"), stream=False)
    output = capsys.readouterr().out
    assert "Let's get started." in output
    assert agent.prompts == ["Look through my workspace and explain what is here in simple terms."]


def test_guided_quickstart_accepts_keyword_input(monkeypatch):
    class DummyProvider:
        def name(self):
            return "dummy"

    class DummyAgent:
        def __init__(self):
            self.provider = DummyProvider()
            self.prompts = []

        def chat(self, prompt):
            self.prompts.append(prompt)
            return "started"

    agent = DummyAgent()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "reminders")
    _run_guided_quickstart(agent, Config(runtime_profile="local_safe"), stream=False)
    assert agent.prompts == ["Help me set up a daily reminder or recurring check."]


def test_guided_quickstart_accepts_calendar_input(monkeypatch):
    class DummyProvider:
        def name(self):
            return "dummy"

    class DummyAgent:
        def __init__(self):
            self.provider = DummyProvider()
            self.prompts = []

        def chat(self, prompt):
            self.prompts.append(prompt)
            return "started"

    agent = DummyAgent()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "calendar")
    _run_guided_quickstart(agent, Config(runtime_profile="local_safe"), stream=False)
    assert agent.prompts == ["Help me set up a daily reminder or recurring check."]


def test_guided_quickstart_accepts_email_input(monkeypatch):
    class DummyProvider:
        def name(self):
            return "dummy"

    class DummyAgent:
        def __init__(self):
            self.provider = DummyProvider()
            self.prompts = []

        def chat(self, prompt):
            self.prompts.append(prompt)
            return "started"

    agent = DummyAgent()
    monkeypatch.setattr("builtins.input", lambda _prompt="": "email")
    _run_guided_quickstart(agent, Config(runtime_profile="local_safe"), stream=False)
    assert agent.prompts == ["Help me connect email or messaging apps, or get organized and suggest a useful first task."]


def test_next_steps_tailors_guidance_for_gateway():
    steps = _next_steps("ollama", "gateway", "C:/work/sol", False)
    assert steps[0].startswith("ollama serve")
    assert 'sol-gateway --profile gateway --workspace-root "C:/work/sol"' in steps[1]
    assert steps[2].startswith("sol")


def test_next_steps_tailors_guidance_for_local_setup():
    steps = _next_steps("openai", "developer", "C:/work/sol", False)
    assert steps == [
        "sol                         # Start a conversation",
        'sol "hello"                 # Quick one-liner',
    ]


def test_post_setup_checks_for_ollama(monkeypatch, tmp_path):
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()

    class Response:
        status_code = 200

    monkeypatch.setattr("solstice_agent.setup.httpx.get", lambda *_args, **_kwargs: Response())

    checks = _post_setup_checks(
        provider="ollama",
        workspace_root=str(workspace_root),
        has_api_key=False,
        ollama_url="http://localhost:11434",
    )

    assert checks[0][0] == "ok"
    assert checks[1] == ("ok", "Ollama selected. No cloud API key required.")
    assert checks[2] == ("ok", "Ollama is reachable at http://localhost:11434.")


def test_post_setup_checks_warn_for_missing_workspace_and_provider_package(monkeypatch, tmp_path):
    missing_root = tmp_path / "missing"
    monkeypatch.setattr("solstice_agent.setup._provider_extra_installed", lambda provider: False)

    checks = _post_setup_checks(
        provider="openai",
        workspace_root=str(missing_root),
        has_api_key=True,
    )

    assert checks[0][0] == "warn"
    assert 'does not exist yet' in checks[0][1]
    assert checks[1][0] == "warn"
    assert 'solstice-agent[openai]' in checks[1][1]
