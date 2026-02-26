"""Tests for Artemis connector awareness in solstice-agent."""


class TestBlackboxArtemis:
    def test_check_camunda_match(self):
        from solstice_agent.tools.blackbox import _check_artemis_connectors
        result = _check_artemis_connectors("https://bru-2.zeebe.camunda.io/abc")
        assert result is not None
        assert "Camunda" in result

    def test_check_no_match(self):
        from solstice_agent.tools.blackbox import _check_artemis_connectors
        result = _check_artemis_connectors("https://api.stripe.com")
        assert result is None

    def test_hint_mentions_pip_install(self):
        from solstice_agent.tools.blackbox import _check_artemis_connectors
        result = _check_artemis_connectors("https://bru-2.zeebe.camunda.io/abc")
        assert "pip install" in result
