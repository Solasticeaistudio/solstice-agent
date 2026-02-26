"""
Camunda Tools
=============
Artemis Camunda 8 connector — the first marketplace connector for Sol.
Deep BPMN orchestration: OAuth2, deploy, process lifecycle, user tasks,
incidents, offline BPMN parsing and validation.

Pattern matches blackbox.py: module-level state, _SCHEMAS dict,
register_camunda_tools(registry).
"""

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.tools.camunda")

# ---------------------------------------------------------------------------
# BPMN XML namespaces
# ---------------------------------------------------------------------------
BPMN_NS = {
    "bpmn": "http://www.omg.org/spec/BPMN/20100524/MODEL",
    "bpmndi": "http://www.omg.org/spec/BPMN/20100524/DI",
    "dc": "http://www.omg.org/spec/DD/20100524/DC",
    "di": "http://www.omg.org/spec/DD/20100524/DI",
    "camunda": "http://camunda.org/schema/1.0/bpmn",
    "zeebe": "http://camunda.org/schema/zeebe/1.0",
}

# Default OAuth2 endpoints
_CLOUD_TOKEN_URL = "https://login.cloud.camunda.io/oauth/token"
_CLOUD_AUDIENCE = "zeebe.camunda.io"
_SM_TOKEN_PATH = "/auth/realms/camunda-platform/protocol/openid-connect/token"

# BPMN element types to parse
_BPMN_ELEMENT_TYPES = [
    "startEvent", "endEvent", "intermediateCatchEvent", "intermediateThrowEvent",
    "serviceTask", "userTask", "scriptTask", "sendTask", "receiveTask",
    "businessRuleTask", "manualTask", "callActivity",
    "exclusiveGateway", "parallelGateway", "inclusiveGateway", "eventBasedGateway",
    "subProcess", "transaction",
]

# ---------------------------------------------------------------------------
# Module-level connection state (matches blackbox.py pattern)
# ---------------------------------------------------------------------------
_client = None           # httpx.Client (sync)
_base_url: str = ""
_access_token: Optional[str] = None
_token_expires_at: float = 0
_token_url: str = ""
_client_id: str = ""
_client_secret: str = ""
_audience: str = ""


def _require_connection() -> bool:
    return _client is not None


def _refresh_token_if_needed() -> Optional[str]:
    """Refresh OAuth2 token if expired or about to expire (30s buffer)."""
    global _access_token, _token_expires_at

    if _access_token and time.time() < (_token_expires_at - 30):
        return _access_token

    if not _client or not _token_url:
        return None

    try:
        resp = _client.post(
            _token_url,
            data={
                "grant_type": "client_credentials",
                "client_id": _client_id,
                "client_secret": _client_secret,
                "audience": _audience,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        _access_token = data["access_token"]
        _token_expires_at = time.time() + data.get("expires_in", 300)
        log.info(f"Camunda token acquired, expires in {data.get('expires_in', 300)}s")
        return _access_token
    except Exception as e:
        log.error(f"Token refresh failed: {e}")
        return None


def _api(method: str, path: str, json_body=None, files=None, retry_401=True) -> Dict[str, Any]:
    """Central API request handler with auto-token and 401 retry."""
    if not _require_connection():
        raise RuntimeError("Not connected. Run camunda_connect first.")

    token = _refresh_token_if_needed()
    if not token:
        raise RuntimeError("Failed to acquire token.")

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{_base_url}{path}"

    kwargs: Dict[str, Any] = {"headers": headers}
    if json_body is not None:
        kwargs["json"] = json_body
    if files is not None:
        kwargs["files"] = files

    resp = _client.request(method, url, **kwargs)

    # 401 retry
    if resp.status_code == 401 and retry_401:
        global _access_token, _token_expires_at
        _access_token = None
        _token_expires_at = 0
        token = _refresh_token_if_needed()
        if token:
            kwargs["headers"] = {"Authorization": f"Bearer {token}"}
            resp = _client.request(method, url, **kwargs)

    resp.raise_for_status()
    if resp.status_code == 204:
        return {"success": True}
    return resp.json()


def _fmt(data: Any) -> str:
    if isinstance(data, dict):
        return json.dumps(data, indent=2, default=str)
    return str(data)


# ---------------------------------------------------------------------------
# Tool 1: camunda_connect (P0)
# ---------------------------------------------------------------------------
def camunda_connect(
    client_id: str,
    client_secret: str,
    cluster_id: str = "",
    region: str = "bru-2",
    deployment: str = "cloud",
    base_url: str = "",
    keycloak_url: str = "",
) -> str:
    """Connect to a Camunda 8 cluster with OAuth2 credentials."""
    global _client, _base_url, _access_token, _token_expires_at
    global _token_url, _client_id, _client_secret, _audience

    try:
        import httpx
    except ImportError:
        return "Error: httpx required. Install with: pip install httpx"

    # Close existing
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass

    _access_token = None
    _token_expires_at = 0
    _client_id = client_id
    _client_secret = client_secret
    is_cloud = deployment == "cloud"

    if is_cloud:
        _token_url = _CLOUD_TOKEN_URL
        _audience = _CLOUD_AUDIENCE
        _base_url = f"https://{region}.zeebe.camunda.io/{cluster_id}"
    else:
        kc = keycloak_url or "http://localhost:18080"
        _token_url = kc + _SM_TOKEN_PATH
        _audience = "zeebe-api"
        _base_url = (base_url or "http://localhost:8080").rstrip("/")

    try:
        _client = httpx.Client(timeout=30.0)
        token = _refresh_token_if_needed()
        if not token:
            _client = None
            return "Connection failed: could not acquire OAuth2 token."

        # Test with topology
        result = _api("GET", "/v2/topology")
        brokers = len(result.get("brokers", []))
        version = result.get("gatewayVersion", "?")
        return (
            f"Connected to Camunda 8 ({_base_url}).\n"
            f"  Brokers: {brokers}, Gateway: v{version}\n"
            f"  Mode: {'Cloud' if is_cloud else 'Self-Managed'}"
        )
    except Exception as e:
        _client = None
        return f"Connection failed: {e}"


# ---------------------------------------------------------------------------
# Tool 2: camunda_status (P0)
# ---------------------------------------------------------------------------
def camunda_status() -> str:
    """Get cluster topology, broker count, and token health."""
    try:
        result = _api("GET", "/v2/topology")
        result["token_healthy"] = _access_token is not None and time.time() < _token_expires_at
        return _fmt(result)
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Tool 3: camunda_deploy (P0)
# ---------------------------------------------------------------------------
def camunda_deploy(file_path: str, resource_name: str = "") -> str:
    """Deploy a BPMN or DMN file to Camunda."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        name = resource_name or os.path.basename(file_path)
        with open(file_path, "rb") as f:
            content = f.read()
        result = _api("POST", "/v2/deployments", files={"resources": (name, content, "application/octet-stream")})
        deployments = result.get("deployments", [])
        if deployments:
            keys = [str(d.get("processDefinitionKey", d.get("decisionKey", "?"))) for d in deployments]
            return f"Deployed successfully. Keys: {', '.join(keys)}\n{_fmt(result)}"
        return f"Deployment result:\n{_fmt(result)}"
    except Exception as e:
        return f"Deploy failed: {e}"


# ---------------------------------------------------------------------------
# Tool 4: camunda_start_process (P0)
# ---------------------------------------------------------------------------
def camunda_start_process(bpmn_process_id: str, variables: str = "{}", version: int = -1) -> str:
    """Start a new process instance by BPMN process ID."""
    try:
        body: Dict[str, Any] = {"bpmnProcessId": bpmn_process_id}
        if variables and variables != "{}":
            body["variables"] = json.loads(variables)
        if version >= 0:
            body["version"] = version
        result = _api("POST", "/v2/process-instances", json_body=body)
        key = result.get("processInstanceKey", "?")
        return f"Process instance started. Key: {key}\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'variables' must be valid JSON"
    except Exception as e:
        return f"Start process failed: {e}"


# ---------------------------------------------------------------------------
# Tool 5: camunda_search_instances (P0)
# ---------------------------------------------------------------------------
def camunda_search_instances(bpmn_process_id: str = "", state: str = "", limit: int = 20) -> str:
    """Search process instances. Filter by process ID and/or state."""
    try:
        body: Dict[str, Any] = {"size": limit}
        f = {}
        if bpmn_process_id:
            f["bpmnProcessId"] = bpmn_process_id
        if state:
            f["state"] = state
        if f:
            body["filter"] = f
        result = _api("POST", "/v2/process-instances/search", json_body=body)
        items = result.get("items", [])
        return f"Found {len(items)} instance(s).\n{_fmt(result)}"
    except Exception as e:
        return f"Search failed: {e}"


# ---------------------------------------------------------------------------
# Tool 6: camunda_cancel_process (P0)
# ---------------------------------------------------------------------------
def camunda_cancel_process(process_instance_key: int) -> str:
    """Cancel a running process instance by key."""
    try:
        _api("POST", f"/v2/process-instances/{process_instance_key}/cancellation")
        return f"Process instance {process_instance_key} cancelled."
    except Exception as e:
        return f"Cancel failed: {e}"


# ---------------------------------------------------------------------------
# Tool 7: camunda_search_tasks (P1)
# ---------------------------------------------------------------------------
def camunda_search_tasks(assignee: str = "", state: str = "", process_instance_key: int = -1, limit: int = 20) -> str:
    """Search user tasks. Filter by assignee, state, or process instance."""
    try:
        body: Dict[str, Any] = {"size": limit}
        f = {}
        if assignee:
            f["assignee"] = assignee
        if state:
            f["state"] = state
        if process_instance_key >= 0:
            f["processInstanceKey"] = process_instance_key
        if f:
            body["filter"] = f
        result = _api("POST", "/v2/user-tasks/search", json_body=body)
        items = result.get("items", [])
        return f"Found {len(items)} task(s).\n{_fmt(result)}"
    except Exception as e:
        return f"Search tasks failed: {e}"


# ---------------------------------------------------------------------------
# Tool 8: camunda_complete_task (P1)
# ---------------------------------------------------------------------------
def camunda_complete_task(task_key: int, variables: str = "{}") -> str:
    """Complete a user task, optionally passing output variables."""
    try:
        body = {}
        if variables and variables != "{}":
            body["variables"] = json.loads(variables)
        _api("POST", f"/v2/user-tasks/{task_key}/completion", json_body=body)
        return f"Task {task_key} completed."
    except json.JSONDecodeError:
        return "Error: 'variables' must be valid JSON"
    except Exception as e:
        return f"Complete task failed: {e}"


# ---------------------------------------------------------------------------
# Tool 9: camunda_assign_task (P1)
# ---------------------------------------------------------------------------
def camunda_assign_task(task_key: int, assignee: str) -> str:
    """Assign a user task to a specific person."""
    try:
        _api("POST", f"/v2/user-tasks/{task_key}/assignment", json_body={"assignee": assignee})
        return f"Task {task_key} assigned to '{assignee}'."
    except Exception as e:
        return f"Assign task failed: {e}"


# ---------------------------------------------------------------------------
# Tool 10: camunda_fail_job (P1)
# ---------------------------------------------------------------------------
def camunda_fail_job(job_key: int, retries: int = 0, error_message: str = "", retry_back_off: int = 0) -> str:
    """Fail a job. Set retries > 0 for retry, 0 for terminal failure."""
    try:
        _api("POST", f"/v2/jobs/{job_key}/failure", json_body={
            "retries": retries, "errorMessage": error_message, "retryBackOff": retry_back_off,
        })
        action = "will retry" if retries > 0 else "terminal failure"
        return f"Job {job_key} failed ({action}). Retries remaining: {retries}"
    except Exception as e:
        return f"Fail job failed: {e}"


# ---------------------------------------------------------------------------
# Tool 11: camunda_publish_message (P1)
# ---------------------------------------------------------------------------
def camunda_publish_message(name: str, correlation_key: str, variables: str = "{}", time_to_live: int = 300000) -> str:
    """Publish a BPMN message for event correlation."""
    try:
        body: Dict[str, Any] = {"name": name, "correlationKey": correlation_key, "timeToLive": time_to_live}
        if variables and variables != "{}":
            body["variables"] = json.loads(variables)
        result = _api("POST", "/v2/messages/publication", json_body=body)
        return f"Message '{name}' published with correlationKey '{correlation_key}'.\n{_fmt(result)}"
    except json.JSONDecodeError:
        return "Error: 'variables' must be valid JSON"
    except Exception as e:
        return f"Publish message failed: {e}"


# ---------------------------------------------------------------------------
# Tool 12: camunda_search_incidents (P1)
# ---------------------------------------------------------------------------
def camunda_search_incidents(process_instance_key: int = -1, state: str = "", limit: int = 20) -> str:
    """Search for incidents (errors in process execution)."""
    try:
        body: Dict[str, Any] = {"size": limit}
        f = {}
        if process_instance_key >= 0:
            f["processInstanceKey"] = process_instance_key
        if state:
            f["state"] = state
        if f:
            body["filter"] = f
        result = _api("POST", "/v2/incidents/search", json_body=body)
        items = result.get("items", [])
        return f"Found {len(items)} incident(s).\n{_fmt(result)}"
    except Exception as e:
        return f"Search incidents failed: {e}"


# ---------------------------------------------------------------------------
# Tool 13: camunda_resolve_incident (P1)
# ---------------------------------------------------------------------------
def camunda_resolve_incident(incident_key: int) -> str:
    """Resolve an incident after fixing the root cause."""
    try:
        _api("POST", f"/v2/incidents/{incident_key}/resolution")
        return f"Incident {incident_key} resolved."
    except Exception as e:
        return f"Resolve incident failed: {e}"


# ---------------------------------------------------------------------------
# Tool 14: bpmn_parse (P2 — offline, no connection needed)
# ---------------------------------------------------------------------------
def bpmn_parse(file_path: str) -> str:
    """Parse a local .bpmn file and return its process structure. No connection needed."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            xml = f.read()
        parsed = _parse_bpmn_string(xml)
        lines = []
        for proc in parsed.get("processes", []):
            lines.append(f"Process: {proc['id']} ({proc.get('name', 'unnamed')})")
            lines.append(f"  Executable: {proc.get('isExecutable', False)}")
            elements = proc.get("elements", [])
            lines.append(f"  Elements ({len(elements)}):")
            for el in elements:
                n = f" — {el['name']}" if el.get("name") else ""
                lines.append(f"    [{el['type']}] {el['id']}{n}")
            flows = proc.get("sequence_flows", [])
            lines.append(f"  Flows ({len(flows)}):")
            for fl in flows:
                c = f" [{fl['condition']}]" if fl.get("condition") else ""
                lines.append(f"    {fl['sourceRef']} -> {fl['targetRef']}{c}")
            lanes = proc.get("lanes", [])
            if lanes:
                lines.append(f"  Lanes ({len(lanes)}):")
                for lane in lanes:
                    lines.append(f"    {lane['name']}: {len(lane['flowNodeRefs'])} nodes")
        if parsed.get("participants"):
            lines.append(f"Participants: {len(parsed['participants'])}")
        return "\n".join(lines)
    except Exception as e:
        return f"BPMN parse error: {e}"


# ---------------------------------------------------------------------------
# Tool 15: bpmn_validate (P2 — offline, no connection needed)
# ---------------------------------------------------------------------------
def bpmn_validate(file_path: str) -> str:
    """Validate a local .bpmn file for common issues. No connection needed."""
    try:
        if not os.path.exists(file_path):
            return f"Error: File not found: {file_path}"
        with open(file_path, "r", encoding="utf-8") as f:
            xml = f.read()
        result = _validate_bpmn_string(xml)
        lines = []
        if result["valid"]:
            lines.append("VALID — no errors found.")
        else:
            lines.append(f"INVALID — {len(result['errors'])} error(s) found.")
        if result["errors"]:
            lines.append("Errors:")
            for e in result["errors"]:
                lines.append(f"  - {e}")
        if result["warnings"]:
            lines.append("Warnings:")
            for w in result["warnings"]:
                lines.append(f"  - {w}")
        return "\n".join(lines)
    except Exception as e:
        return f"BPMN validate error: {e}"


# ---------------------------------------------------------------------------
# BPMN parsing internals
# ---------------------------------------------------------------------------

def _parse_bpmn_string(xml_content: str) -> Dict[str, Any]:
    from defusedxml import ElementTree as ET
    root = ET.fromstring(xml_content)
    result: Dict[str, Any] = {"processes": [], "participants": [], "message_flows": []}

    for process in root.findall("bpmn:process", BPMN_NS):
        result["processes"].append(_parse_process(process))

    if not result["processes"]:
        for process in root.findall("process"):
            result["processes"].append(_parse_process(process))

    for collab in root.findall("bpmn:collaboration", BPMN_NS):
        for p in collab.findall("bpmn:participant", BPMN_NS):
            result["participants"].append({
                "id": p.get("id", ""), "name": p.get("name", ""), "processRef": p.get("processRef", ""),
            })
        for mf in collab.findall("bpmn:messageFlow", BPMN_NS):
            result["message_flows"].append({
                "id": mf.get("id", ""), "name": mf.get("name", ""),
                "sourceRef": mf.get("sourceRef", ""), "targetRef": mf.get("targetRef", ""),
            })
    return result


def _parse_process(process) -> Dict[str, Any]:
    proc = {
        "id": process.get("id", ""), "name": process.get("name", ""),
        "isExecutable": process.get("isExecutable", "false").lower() == "true",
        "elements": [], "sequence_flows": [], "lanes": [],
    }
    for etype in _BPMN_ELEMENT_TYPES:
        for el in process.findall(f"bpmn:{etype}", BPMN_NS):
            elem = {"id": el.get("id", ""), "name": el.get("name", ""), "type": etype}
            td = el.find("zeebe:taskDefinition", BPMN_NS)
            if td is not None:
                elem["taskType"] = td.get("type", "")
            proc["elements"].append(elem)
        if not proc["elements"]:
            for el in process.findall(etype):
                proc["elements"].append({"id": el.get("id", ""), "name": el.get("name", ""), "type": etype})

    for flow in process.findall("bpmn:sequenceFlow", BPMN_NS):
        fd = {"id": flow.get("id", ""), "name": flow.get("name", ""),
              "sourceRef": flow.get("sourceRef", ""), "targetRef": flow.get("targetRef", "")}
        cond = flow.find("bpmn:conditionExpression", BPMN_NS)
        if cond is not None and cond.text:
            fd["condition"] = cond.text.strip()
        proc["sequence_flows"].append(fd)
    if not proc["sequence_flows"]:
        for flow in process.findall("sequenceFlow"):
            fd = {"id": flow.get("id", ""), "name": flow.get("name", ""),
                  "sourceRef": flow.get("sourceRef", ""), "targetRef": flow.get("targetRef", "")}
            cond = flow.find("conditionExpression")
            if cond is not None and cond.text:
                fd["condition"] = cond.text.strip()
            proc["sequence_flows"].append(fd)

    for ls in process.findall("bpmn:laneSet", BPMN_NS):
        for lane in ls.findall("bpmn:lane", BPMN_NS):
            ld = {"id": lane.get("id", ""), "name": lane.get("name", ""), "flowNodeRefs": []}
            for ref in lane.findall("bpmn:flowNodeRef", BPMN_NS):
                if ref.text:
                    ld["flowNodeRefs"].append(ref.text.strip())
            proc["lanes"].append(ld)
    return proc


def _validate_bpmn_string(xml_content: str) -> Dict[str, Any]:
    errors, warnings = [], []
    try:
        parsed = _parse_bpmn_string(xml_content)
    except Exception as e:
        return {"valid": False, "errors": [f"XML parse error: {e}"], "warnings": []}

    if not parsed["processes"]:
        return {"valid": False, "errors": ["No <process> element found"], "warnings": []}

    for proc in parsed["processes"]:
        pid = proc.get("id", "unknown")
        starts = [e for e in proc.get("elements", []) if e["type"] == "startEvent"]
        ends = [e for e in proc.get("elements", []) if e["type"] == "endEvent"]
        if not starts:
            errors.append(f"Process '{pid}' has no start event")
        if not ends:
            errors.append(f"Process '{pid}' has no end event")
        if not proc.get("isExecutable"):
            warnings.append(f"Process '{pid}' is not marked as executable")

        element_ids = {e["id"] for e in proc.get("elements", [])}
        has_incoming, has_outgoing = set(), set()
        for fl in proc.get("sequence_flows", []):
            src, tgt = fl.get("sourceRef", ""), fl.get("targetRef", "")
            has_outgoing.add(src)
            has_incoming.add(tgt)
            if src not in element_ids:
                errors.append(f"Flow '{fl.get('id')}' references unknown source '{src}'")
            if tgt not in element_ids:
                errors.append(f"Flow '{fl.get('id')}' references unknown target '{tgt}'")

        for elem in proc.get("elements", []):
            eid, etype = elem["id"], elem["type"]
            if etype == "startEvent" and eid not in has_outgoing:
                warnings.append(f"Start event '{eid}' has no outgoing flow")
            elif etype == "endEvent" and eid not in has_incoming:
                warnings.append(f"End event '{eid}' has no incoming flow")
            elif etype not in ("startEvent", "endEvent") and eid not in has_incoming and eid not in has_outgoing:
                errors.append(f"Element '{eid}' ({etype}) is orphaned — no flows")

        gateways = [e for e in proc.get("elements", []) if "Gateway" in e["type"]]
        for gw in gateways:
            gw_out = [fl for fl in proc.get("sequence_flows", []) if fl["sourceRef"] == gw["id"]]
            if len(gw_out) > 1:
                uncond = [fl for fl in gw_out if not fl.get("condition")]
                if len(uncond) > 1:
                    warnings.append(f"Gateway '{gw['id']}' has {len(uncond)} unconditioned outgoing flows")

    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format — lowercase "object")
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "camunda_connect": {
        "name": "camunda_connect",
        "description": (
            "Connect to a Camunda 8 cluster using OAuth2 credentials. "
            "Supports Cloud (SaaS) and Self-Managed deployments. "
            "This is an Artemis premium connector — run this first to unlock all camunda_* tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "cluster_id": {"type": "string", "description": "Camunda Cloud cluster ID (Cloud only)"},
                "region": {"type": "string", "description": "Cloud region (default: bru-2)"},
                "deployment": {"type": "string", "description": "'cloud' or 'self-managed'", "enum": ["cloud", "self-managed"]},
                "base_url": {"type": "string", "description": "Base URL for Self-Managed (e.g. http://localhost:8080)"},
                "keycloak_url": {"type": "string", "description": "Keycloak URL for Self-Managed (e.g. http://localhost:18080)"},
            },
            "required": ["client_id", "client_secret"],
        },
    },
    "camunda_status": {
        "name": "camunda_status",
        "description": "Get Camunda cluster status: topology, broker count, partition info, and token health.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "camunda_deploy": {
        "name": "camunda_deploy",
        "description": "Deploy a BPMN or DMN file to Camunda for execution.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the .bpmn or .dmn file"},
                "resource_name": {"type": "string", "description": "Optional resource name override"},
            },
            "required": ["file_path"],
        },
    },
    "camunda_start_process": {
        "name": "camunda_start_process",
        "description": "Start a new process instance in Camunda by BPMN process ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "bpmn_process_id": {"type": "string", "description": "The BPMN process ID to start"},
                "variables": {"type": "string", "description": "JSON string of process variables"},
                "version": {"type": "integer", "description": "Specific version (-1 for latest)"},
            },
            "required": ["bpmn_process_id"],
        },
    },
    "camunda_search_instances": {
        "name": "camunda_search_instances",
        "description": "Search process instances. Filter by process ID or state (ACTIVE, COMPLETED, CANCELED).",
        "parameters": {
            "type": "object",
            "properties": {
                "bpmn_process_id": {"type": "string", "description": "Filter by BPMN process ID"},
                "state": {"type": "string", "description": "Filter by state", "enum": ["ACTIVE", "COMPLETED", "CANCELED"]},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "camunda_cancel_process": {
        "name": "camunda_cancel_process",
        "description": "Cancel a running process instance by its key.",
        "parameters": {
            "type": "object",
            "properties": {
                "process_instance_key": {"type": "integer", "description": "The process instance key to cancel"},
            },
            "required": ["process_instance_key"],
        },
    },
    "camunda_search_tasks": {
        "name": "camunda_search_tasks",
        "description": "Search user tasks. Filter by assignee, state (CREATED, COMPLETED), or process instance.",
        "parameters": {
            "type": "object",
            "properties": {
                "assignee": {"type": "string", "description": "Filter by assignee"},
                "state": {"type": "string", "description": "Filter by state", "enum": ["CREATED", "COMPLETED"]},
                "process_instance_key": {"type": "integer", "description": "Filter by process instance key"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "camunda_complete_task": {
        "name": "camunda_complete_task",
        "description": "Complete a user task, optionally passing output variables.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_key": {"type": "integer", "description": "The user task key"},
                "variables": {"type": "string", "description": "JSON string of output variables"},
            },
            "required": ["task_key"],
        },
    },
    "camunda_assign_task": {
        "name": "camunda_assign_task",
        "description": "Assign a user task to a specific person.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_key": {"type": "integer", "description": "The user task key"},
                "assignee": {"type": "string", "description": "Username to assign to"},
            },
            "required": ["task_key", "assignee"],
        },
    },
    "camunda_fail_job": {
        "name": "camunda_fail_job",
        "description": "Fail a job. Set retries > 0 to retry, 0 for terminal failure.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_key": {"type": "integer", "description": "The job key"},
                "retries": {"type": "integer", "description": "Remaining retries (0 = terminal)"},
                "error_message": {"type": "string", "description": "Error message"},
                "retry_back_off": {"type": "integer", "description": "Backoff in ms before retry"},
            },
            "required": ["job_key"],
        },
    },
    "camunda_publish_message": {
        "name": "camunda_publish_message",
        "description": "Publish a BPMN message for event correlation.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Message name (must match BPMN definition)"},
                "correlation_key": {"type": "string", "description": "Correlation key for targeting instance"},
                "variables": {"type": "string", "description": "JSON string of message variables"},
                "time_to_live": {"type": "integer", "description": "TTL in ms (default 300000)"},
            },
            "required": ["name", "correlation_key"],
        },
    },
    "camunda_search_incidents": {
        "name": "camunda_search_incidents",
        "description": "Search for incidents (execution errors) in Camunda processes.",
        "parameters": {
            "type": "object",
            "properties": {
                "process_instance_key": {"type": "integer", "description": "Filter by process instance"},
                "state": {"type": "string", "description": "Filter by state", "enum": ["ACTIVE", "RESOLVED"]},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
            "required": [],
        },
    },
    "camunda_resolve_incident": {
        "name": "camunda_resolve_incident",
        "description": "Resolve an incident after fixing the root cause.",
        "parameters": {
            "type": "object",
            "properties": {
                "incident_key": {"type": "integer", "description": "The incident key to resolve"},
            },
            "required": ["incident_key"],
        },
    },
    "bpmn_parse": {
        "name": "bpmn_parse",
        "description": (
            "Parse a local .bpmn file and extract its process structure "
            "(elements, flows, lanes). No Camunda connection needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the .bpmn file"},
            },
            "required": ["file_path"],
        },
    },
    "bpmn_validate": {
        "name": "bpmn_validate",
        "description": (
            "Validate a local .bpmn file for common issues (missing start/end events, "
            "orphan nodes, dangling flows). No Camunda connection needed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the .bpmn file"},
            },
            "required": ["file_path"],
        },
    },
}

# Map names to functions
_HANDLERS = {
    "camunda_connect": camunda_connect,
    "camunda_status": camunda_status,
    "camunda_deploy": camunda_deploy,
    "camunda_start_process": camunda_start_process,
    "camunda_search_instances": camunda_search_instances,
    "camunda_cancel_process": camunda_cancel_process,
    "camunda_search_tasks": camunda_search_tasks,
    "camunda_complete_task": camunda_complete_task,
    "camunda_assign_task": camunda_assign_task,
    "camunda_fail_job": camunda_fail_job,
    "camunda_publish_message": camunda_publish_message,
    "camunda_search_incidents": camunda_search_incidents,
    "camunda_resolve_incident": camunda_resolve_incident,
    "bpmn_parse": bpmn_parse,
    "bpmn_validate": bpmn_validate,
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_camunda_tools(registry):
    """Register all 15 Camunda/BPMN tools with a ToolRegistry."""
    for name, handler in _HANDLERS.items():
        registry.register(name, handler, _SCHEMAS[name])
