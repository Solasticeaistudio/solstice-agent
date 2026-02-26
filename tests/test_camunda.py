"""Tests for Camunda tools."""

import os
import pytest
from unittest.mock import MagicMock

SAMPLE_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                  id="Definitions_1">
  <bpmn:process id="order_process" name="Order Processing" isExecutable="true">
    <bpmn:startEvent id="start_1" name="Order Received"/>
    <bpmn:userTask id="review_1" name="Review Order"/>
    <bpmn:serviceTask id="fulfill_1" name="Fulfill Order"/>
    <bpmn:exclusiveGateway id="gw_1" name="Approved?"/>
    <bpmn:endEvent id="end_1" name="Done"/>
    <bpmn:sequenceFlow id="f1" sourceRef="start_1" targetRef="review_1"/>
    <bpmn:sequenceFlow id="f2" sourceRef="review_1" targetRef="gw_1"/>
    <bpmn:sequenceFlow id="f3" sourceRef="gw_1" targetRef="fulfill_1" name="Yes">
      <bpmn:conditionExpression>approved == true</bpmn:conditionExpression>
    </bpmn:sequenceFlow>
    <bpmn:sequenceFlow id="f4" sourceRef="gw_1" targetRef="end_1" name="No"/>
    <bpmn:sequenceFlow id="f5" sourceRef="fulfill_1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>"""

INVALID_BPMN = """<?xml version="1.0" encoding="UTF-8"?>
<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL" id="D1">
  <bpmn:process id="bad" name="Bad" isExecutable="true">
    <bpmn:userTask id="t1" name="Lonely"/>
    <bpmn:endEvent id="end_1"/>
    <bpmn:sequenceFlow id="f1" sourceRef="t1" targetRef="end_1"/>
  </bpmn:process>
</bpmn:definitions>"""


class TestBpmnParse:
    def test_parse(self, tmp_path):
        f = tmp_path / "test.bpmn"
        f.write_text(SAMPLE_BPMN)
        from solstice_agent.tools.camunda import bpmn_parse
        result = bpmn_parse(str(f))
        assert "order_process" in result
        assert "startEvent" in result
        assert "userTask" in result

    def test_parse_missing_file(self):
        from solstice_agent.tools.camunda import bpmn_parse
        result = bpmn_parse("/no/such/file.bpmn")
        assert "Error" in result


class TestBpmnValidate:
    def test_valid(self, tmp_path):
        f = tmp_path / "ok.bpmn"
        f.write_text(SAMPLE_BPMN)
        from solstice_agent.tools.camunda import bpmn_validate
        result = bpmn_validate(str(f))
        assert "VALID" in result

    def test_invalid(self, tmp_path):
        f = tmp_path / "bad.bpmn"
        f.write_text(INVALID_BPMN)
        from solstice_agent.tools.camunda import bpmn_validate
        result = bpmn_validate(str(f))
        assert "INVALID" in result
        assert "no start event" in result.lower()


class TestRegistration:
    def test_register_all_15(self):
        from solstice_agent.tools.camunda import register_camunda_tools, _SCHEMAS
        mock_reg = MagicMock()
        register_camunda_tools(mock_reg)
        assert mock_reg.register.call_count == 15

    def test_schemas_complete(self):
        from solstice_agent.tools.camunda import _SCHEMAS
        for name, schema in _SCHEMAS.items():
            assert schema["parameters"]["type"] == "object"
            assert "description" in schema

    def test_load_builtins_includes_camunda(self):
        from solstice_agent.tools.registry import ToolRegistry
        reg = ToolRegistry()
        reg.load_builtins(
            enable_terminal=False, enable_web=False, enable_blackbox=False,
            enable_browser=False, enable_voice=False, enable_memory=False,
            enable_skills=False, enable_cron=False, enable_registry=False,
            enable_screen=False, enable_docker=False, enable_voice_continuous=False,
            enable_presence=False, enable_recording=False, enable_outreach=False,
            enable_camunda=True,
        )
        tools = reg.list_tools()
        # file_ops are always loaded + 15 camunda tools
        assert "camunda_connect" in tools
        assert "bpmn_parse" in tools
        assert "bpmn_validate" in tools


class TestNotConnected:
    def test_status_without_connect(self):
        import solstice_agent.tools.camunda as mod
        mod._client = None
        result = mod.camunda_status()
        assert "Error" in result or "Not connected" in result


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
