import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class DummyResponse:
    def __init__(self, status=200):
        self.status = status


class DummyPage:
    def __init__(self, final_url="https://example.com/"):
        self.url = final_url
        self.goto_calls = []

    def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append((url, wait_until, timeout))
        if url == "about:blank":
            self.url = "about:blank"
        return DummyResponse(status=200)

    def title(self):
        return "Example"


def test_browser_navigate_blocks_private_and_metadata_urls(monkeypatch):
    from solstice_agent.tools import browser

    monkeypatch.setattr(browser, "_ensure_browser", lambda: True)

    for url in (
        "http://localhost:8080/",
        "http://127.0.0.1/",
        "http://10.0.0.5/admin",
        "http://169.254.169.254/latest/meta-data/",
    ):
        page = DummyPage()
        monkeypatch.setattr(browser, "_page", page)
        result = browser.browser_navigate(url)
        assert result.startswith("Error:")
        assert page.goto_calls == []


def test_browser_navigate_allows_public_https(monkeypatch):
    from solstice_agent.tools import browser

    page = DummyPage(final_url="https://example.com/docs")
    monkeypatch.setattr(browser, "_ensure_browser", lambda: True)
    monkeypatch.setattr(browser, "_page", page)

    result = browser.browser_navigate("https://example.com/docs")
    assert "Navigated to https://example.com/docs" in result
    assert page.goto_calls[0][0] == "https://example.com/docs"


def test_browser_navigate_blocks_unsafe_redirect_target(monkeypatch):
    from solstice_agent.tools import browser

    page = DummyPage(final_url="http://127.0.0.1:8080/")
    monkeypatch.setattr(browser, "_ensure_browser", lambda: True)
    monkeypatch.setattr(browser, "_page", page)

    result = browser.browser_navigate("https://example.com/redirect")
    assert result.startswith("Error:")
    assert page.goto_calls[-1][0] == "about:blank"


def test_server_workspace_root_is_required(tmp_path):
    from solstice_agent.config import Config
    from solstice_agent.server import _configure_gateway_workspace
    from solstice_agent.tools.file_ops import read_file
    from solstice_agent.tools.security import get_workspace_root, is_workspace_required, set_workspace_root

    inside = tmp_path / "inside.txt"
    outside = tmp_path.parent / "outside.txt"
    inside.write_text("inside", encoding="utf-8")
    outside.write_text("outside", encoding="utf-8")

    try:
        _configure_gateway_workspace(Config(workspace_root=str(tmp_path)))
        assert get_workspace_root() == str(tmp_path.resolve())
        assert is_workspace_required() is True
        assert "inside" in read_file(str(inside))
        blocked = read_file(str(outside))
        assert "outside the workspace" in blocked.lower()

        _configure_gateway_workspace(Config())
        no_workspace = read_file(str(inside))
        assert "no workspace" in no_workspace.lower()
    finally:
        set_workspace_root(None, required=False)


def test_server_tool_flags_default_to_safe_profile():
    from solstice_agent.config import Config
    from solstice_agent.server import _server_tool_flags

    flags = _server_tool_flags(Config())
    assert flags["enable_terminal"] is False
    assert flags["enable_web"] is False
    assert flags["enable_browser"] is False
    assert flags["enable_screen"] is False
    assert flags["enable_docker"] is False
    assert flags["enable_recording"] is False
    assert flags["enable_outreach"] is False


def test_cli_outreach_push_crm_loads_config_before_branch(monkeypatch, capsys):
    from solstice_agent.cli import main
    from solstice_agent.config import Config

    calls = []

    monkeypatch.setattr(
        sys,
        "argv",
        ["sol", "--outreach-push-crm", "camp-1"],
    )
    monkeypatch.setattr(
        "solstice_agent.cli.Config.load",
        lambda path=None: Config(outreach_crm_webhook="https://example.com/crm"),
    )
    monkeypatch.setattr(
        "solstice_agent.outreach.sync_queue.outreach_push_crm",
        lambda campaign_id="", webhook_url="": calls.append((campaign_id, webhook_url)) or "crm pushed",
    )

    main()
    assert capsys.readouterr().out.strip() == "crm pushed"
    assert calls == [("camp-1", "https://example.com/crm")]


def test_cli_outreach_push_meetings_loads_config_before_branch(monkeypatch, capsys):
    from solstice_agent.cli import main
    from solstice_agent.config import Config

    calls = []

    monkeypatch.setattr(
        sys,
        "argv",
        ["sol", "--outreach-push-meetings", "camp-2"],
    )
    monkeypatch.setattr(
        "solstice_agent.cli.Config.load",
        lambda path=None: Config(outreach_meeting_webhook="https://example.com/meetings"),
    )
    monkeypatch.setattr(
        "solstice_agent.outreach.sync_queue.outreach_push_meeting_queue",
        lambda campaign_id="", webhook_url="": calls.append((campaign_id, webhook_url)) or "meetings pushed",
    )

    main()
    assert capsys.readouterr().out.strip() == "meetings pushed"
    assert calls == [("camp-2", "https://example.com/meetings")]
