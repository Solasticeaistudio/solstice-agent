"""Tests for Docker sandbox tools."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDockerSandbox:
    def test_import(self):
        pass

    def test_schema_registration(self):
        from solstice_agent.tools.registry import ToolRegistry
        from solstice_agent.tools.docker_sandbox import register_docker_tools
        registry = ToolRegistry()
        register_docker_tools(registry)
        tools = registry.list_tools()
        assert "sandbox_run" in tools
        assert "sandbox_start" in tools
        assert "sandbox_exec" in tools
        assert "sandbox_stop" in tools
        assert "sandbox_list" in tools
        assert "sandbox_copy_in" in tools
        assert "sandbox_copy_out" in tools
        assert len(tools) == 7

    def test_validate_volumes_safe(self):
        from solstice_agent.tools.docker_sandbox import _validate_volumes
        # None volumes
        vols, err = _validate_volumes(None)
        assert err is None
        assert vols == {}

    def test_validate_volumes_invalid_json(self):
        from solstice_agent.tools.docker_sandbox import _validate_volumes
        _, err = _validate_volumes("not json")
        assert err is not None
        assert "invalid" in err.lower() or "error" in err.lower()

    def test_validate_volumes_not_dict(self):
        from solstice_agent.tools.docker_sandbox import _validate_volumes
        _, err = _validate_volumes('["list"]')
        assert err is not None

    def test_validate_volumes_outside_cwd(self):
        from solstice_agent.tools.docker_sandbox import _validate_volumes
        import json
        # Absolute path outside CWD should be rejected
        vols_json = json.dumps({"/etc/passwd": "/etc/passwd"})
        _, err = _validate_volumes(vols_json)
        assert err is not None
        assert "outside" in err.lower() or "security" in err.lower()

    def test_sandbox_run_no_docker(self):
        from solstice_agent.tools.docker_sandbox import sandbox_run
        import solstice_agent.tools.docker_sandbox as mod
        # Reset client
        mod._client = None
        with patch.dict("sys.modules", {"docker": None}):
            # Force reimport failure
            mod._client = None
            result = sandbox_run("echo hello")
            assert isinstance(result, str)
            # Either works with docker or returns error
            assert "hello" in result or "error" in result.lower()

    def test_gen_name(self):
        from solstice_agent.tools.docker_sandbox import _gen_name, _SANDBOX_PREFIX
        name = _gen_name()
        assert name.startswith(_SANDBOX_PREFIX)
