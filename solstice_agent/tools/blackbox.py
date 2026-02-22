"""
Blackbox Tools
==============
Autonomous API discovery and interaction. Point Sol at any HTTP endpoint —
it probes, maps, and operates it through natural conversation.

Extracted from Solstice Artemis BlackboxConnector.
"""

import json
import logging
import re
import statistics
import time
from collections import deque
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

log = logging.getLogger("solstice.tools.blackbox")

# ---------------------------------------------------------------------------
# Module-level connection state
# ---------------------------------------------------------------------------
_client = None          # httpx.Client (sync)
_base_url: str = ""
_allow_write: bool = False
_discovered_schema: Optional[Dict] = None


def _require_connection() -> bool:
    """Check that a Blackbox connection is active."""
    return _client is not None


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def blackbox_connect(
    url: str,
    auth_token: Optional[str] = None,
    allow_write: bool = False,
    skip_tls_verify: bool = False,
) -> str:
    """
    Connect to an API endpoint. Run this first before any other blackbox tool.
    """
    global _client, _base_url, _allow_write, _discovered_schema

    from .security import validate_url

    url_err = validate_url(url)
    if url_err:
        return f"Error: {url_err}"

    try:
        import httpx
    except ImportError:
        return "Error: Blackbox tools require httpx. Install with: pip install httpx"

    # Close any existing connection
    if _client is not None:
        try:
            _client.close()
        except Exception:
            pass

    _discovered_schema = None
    _base_url = url.rstrip("/")
    _allow_write = allow_write

    headers = {"User-Agent": "Sol/0.1 (Blackbox Discovery)"}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    try:
        _client = httpx.Client(
            base_url=_base_url,
            headers=headers,
            timeout=30.0,
            verify=not skip_tls_verify,
        )
        response = _client.get("/")
        status = response.status_code
        write_mode = "read-write" if allow_write else "read-only"
        tls_mode = "TLS verification OFF" if skip_tls_verify else "TLS verified"
        return (
            f"Connected to {_base_url}. Status: {status}. "
            f"Mode: {write_mode}. {tls_mode}."
        )
    except Exception as e:
        _client = None
        log.debug(f"Blackbox connect failed: {e}")
        return f"Failed to connect to {_base_url}. Check that the URL is reachable and correct."


def blackbox_discover() -> str:
    """
    Auto-discover API structure by scanning for OpenAPI/Swagger documentation.
    Returns the schema if found, or a message indicating no docs were found.
    """
    global _discovered_schema

    if not _require_connection():
        return "Not connected. Run blackbox_connect first."

    common_paths = [
        "/openapi.json",
        "/swagger.json",
        "/api/docs",
        "/v1/docs",
        "/swagger/v1/swagger.json",
    ]

    for path in common_paths:
        try:
            response = _client.get(path)
            if response.status_code == 200:
                try:
                    schema = response.json()
                    _discovered_schema = schema

                    # Summarize what we found
                    title = schema.get("info", {}).get("title", "Unknown API")
                    version = schema.get("info", {}).get("version", "?")
                    paths = list(schema.get("paths", {}).keys())
                    endpoint_count = len(paths)
                    preview = paths[:10]

                    result = f"Found API documentation at {path}.\n"
                    result += f"  Title: {title} (v{version})\n"
                    result += f"  Endpoints: {endpoint_count}\n"
                    if preview:
                        result += f"  Sample paths: {', '.join(preview)}"
                        if endpoint_count > 10:
                            result += f" ... and {endpoint_count - 10} more"
                    return result
                except json.JSONDecodeError:
                    continue
        except Exception:
            continue

    return "No OpenAPI/Swagger documentation found. Try blackbox_fingerprint and blackbox_spider to map the API manually."


def blackbox_fingerprint() -> str:
    """
    Profile an API by probing supported HTTP methods, response times,
    error patterns, and authentication requirements.
    """
    if not _require_connection():
        return "Not connected. Run blackbox_connect first."

    supported_verbs = []
    latencies: List[float] = []
    error_shapes: Dict[int, Any] = {}
    content_types = set()

    verbs = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

    for verb in verbs:
        start = time.time()
        try:
            response = _client.request(verb, "/")
            latency_ms = (time.time() - start) * 1000
            latencies.append(latency_ms)

            if response.status_code != 405:
                supported_verbs.append(verb)

            ct = response.headers.get("content-type", "unknown")
            content_types.add(ct)

            if response.status_code >= 400:
                try:
                    error_body = response.json()
                    error_shapes[response.status_code] = list(error_body.keys())
                except Exception:
                    error_shapes[response.status_code] = "non-json"

        except Exception:
            log.debug(f"Verb probe {verb} failed")

    # Build readable report
    lines = [f"Fingerprint for {_base_url}:"]
    lines.append(f"  Supported methods: {', '.join(supported_verbs) or 'none detected'}")

    if latencies:
        lines.append(
            f"  Latency: min={min(latencies):.0f}ms, "
            f"avg={statistics.mean(latencies):.0f}ms, "
            f"max={max(latencies):.0f}ms"
        )

    if error_shapes:
        for code, shape in error_shapes.items():
            lines.append(f"  Error {code}: keys={shape}")

    if content_types:
        lines.append(f"  Content types: {', '.join(content_types)}")

    lines.append(f"  Write access: {'enabled' if _allow_write else 'disabled'}")

    return "\n".join(lines)


def blackbox_spider(max_pages: int = 50, max_depth: int = 3) -> str:
    """
    Crawl the API to discover endpoints. Follows links found in JSON
    responses and HTML pages, staying within the target domain.
    """
    if not _require_connection():
        return "Not connected. Run blackbox_connect first."

    visited = set()
    queue = deque([(_base_url, 0)])
    endpoints = set()
    pages_crawled = 0

    while queue and pages_crawled < max_pages:
        current_url, depth = queue.popleft()

        if current_url in visited or depth > max_depth:
            continue

        visited.add(current_url)
        pages_crawled += 1

        try:
            target_path = current_url
            if current_url.startswith(_base_url):
                target_path = current_url[len(_base_url):] or "/"

            response = _client.get(target_path)
            endpoints.add(target_path)
            content = response.text

            # JSON link extraction
            try:
                json_data = response.json()

                def find_paths(obj):
                    if isinstance(obj, dict):
                        for v in obj.values():
                            find_paths(v)
                    elif isinstance(obj, list):
                        for v in obj:
                            find_paths(v)
                    elif isinstance(obj, str):
                        if obj.startswith("/") or obj.startswith("http"):
                            full_url = urljoin(_base_url, obj)
                            if full_url.startswith(_base_url):
                                queue.append((full_url, depth + 1))

                find_paths(json_data)
            except Exception:
                pass

            # HTML link extraction
            links = re.findall(r'(?:href|src)=["\'](.*?)["\']', content)
            for link in links:
                full_url = urljoin(_base_url, link)
                if full_url.startswith(_base_url):
                    queue.append((full_url, depth + 1))

        except Exception:
            log.debug(f"Spider failed at {current_url}")

    sorted_endpoints = sorted(endpoints)
    lines = [f"Spider mapped {len(sorted_endpoints)} endpoints (crawled {pages_crawled} pages):"]
    for ep in sorted_endpoints:
        lines.append(f"  {ep}")

    return "\n".join(lines)


def blackbox_pull(endpoint: str, params: Optional[str] = None) -> str:
    """
    GET data from an API endpoint. Optionally pass query params as a
    JSON string, e.g. '{"page": 1, "limit": 10}'.
    """
    if not _require_connection():
        return "Not connected. Run blackbox_connect first."

    parsed_params = None
    if params:
        try:
            parsed_params = json.loads(params)
        except json.JSONDecodeError:
            return "Invalid params — must be a JSON string like '{\"key\": \"value\"}'."

    try:
        response = _client.get(endpoint, params=parsed_params)
        status = response.status_code

        try:
            data = json.dumps(response.json(), indent=2)
        except Exception:
            data = response.text

        # Truncate large responses
        if len(data) > 8000:
            data = data[:8000] + "\n... (truncated)"

        return f"GET {endpoint} — {status}\n\n{data}"
    except Exception as e:
        log.debug(f"Pull failed for {endpoint}: {e}")
        return f"Request to {endpoint} failed. Check the endpoint path and try again."


def blackbox_push(endpoint: str, data: str, method: str = "POST") -> str:
    """
    Write data to an API endpoint. Requires allow_write=True on connect.
    Pass data as a JSON string. Method can be POST, PUT, PATCH, or DELETE.
    """
    if not _require_connection():
        return "Not connected. Run blackbox_connect first."

    if not _allow_write:
        return "Write access is disabled. Reconnect with allow_write=True to enable writes."

    method = method.upper()
    if method not in ("POST", "PUT", "PATCH", "DELETE"):
        return f"Unsupported method: {method}. Use POST, PUT, PATCH, or DELETE."

    parsed_data = None
    if method != "DELETE":
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            return "Invalid data — must be a JSON string."

    try:
        if method == "DELETE":
            response = _client.delete(endpoint)
        elif method == "PUT":
            response = _client.put(endpoint, json=parsed_data)
        elif method == "PATCH":
            response = _client.patch(endpoint, json=parsed_data)
        else:
            response = _client.post(endpoint, json=parsed_data)

        status = response.status_code
        try:
            body = json.dumps(response.json(), indent=2)
        except Exception:
            body = response.text or "(empty response)"

        if len(body) > 8000:
            body = body[:8000] + "\n... (truncated)"

        return f"{method} {endpoint} — {status}\n\n{body}"
    except Exception as e:
        log.debug(f"Push failed for {endpoint}: {e}")
        return f"{method} request to {endpoint} failed. Check the endpoint and payload."


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "blackbox_connect": {
        "name": "blackbox_connect",
        "description": (
            "Connect to an API endpoint for autonomous discovery and interaction. "
            "Run this before any other blackbox tool. Provide the base URL. "
            "Optionally pass a Bearer auth token and enable write access."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Base URL of the API (e.g. https://api.example.com)",
                },
                "auth_token": {
                    "type": "string",
                    "description": "Bearer token for authentication (optional)",
                },
                "allow_write": {
                    "type": "boolean",
                    "description": "Enable POST/PUT/PATCH/DELETE operations (default false)",
                },
                "skip_tls_verify": {
                    "type": "boolean",
                    "description": "Skip TLS certificate verification — only for self-signed certs (default false)",
                },
            },
            "required": ["url"],
        },
    },
    "blackbox_discover": {
        "name": "blackbox_discover",
        "description": (
            "Auto-discover API structure by scanning for OpenAPI/Swagger documentation. "
            "Returns endpoint count, API title, and sample paths if docs are found."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "blackbox_fingerprint": {
        "name": "blackbox_fingerprint",
        "description": (
            "Profile the connected API — probe supported HTTP methods, measure latency, "
            "analyze error response shapes, and detect authentication patterns."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "blackbox_spider": {
        "name": "blackbox_spider",
        "description": (
            "Crawl the connected API to discover endpoints. Follows links in JSON responses "
            "and HTML pages. Stays within the target domain. Returns a list of discovered paths."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_pages": {
                    "type": "integer",
                    "description": "Maximum pages to crawl (default 50)",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum link-follow depth (default 3)",
                },
            },
            "required": [],
        },
    },
    "blackbox_pull": {
        "name": "blackbox_pull",
        "description": (
            "GET data from an API endpoint. Returns the response status and body. "
            "Optionally pass query parameters as a JSON string."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint path (e.g. /users, /api/v1/products)",
                },
                "params": {
                    "type": "string",
                    "description": 'Query parameters as JSON string (e.g. \'{"page": 1}\')',
                },
            },
            "required": ["endpoint"],
        },
    },
    "blackbox_push": {
        "name": "blackbox_push",
        "description": (
            "Write data to an API endpoint. Requires allow_write=True on connect. "
            "Pass the request body as a JSON string. Supports POST, PUT, PATCH, DELETE."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "endpoint": {
                    "type": "string",
                    "description": "API endpoint path (e.g. /users, /api/v1/products)",
                },
                "data": {
                    "type": "string",
                    "description": 'Request body as JSON string (e.g. \'{"name": "test"}\')',
                },
                "method": {
                    "type": "string",
                    "description": "HTTP method: POST (default), PUT, PATCH, or DELETE",
                    "enum": ["POST", "PUT", "PATCH", "DELETE"],
                },
            },
            "required": ["endpoint", "data"],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_blackbox_tools(registry):
    """Register Blackbox API tools with a ToolRegistry."""
    registry.register("blackbox_connect", blackbox_connect, _SCHEMAS["blackbox_connect"])
    registry.register("blackbox_discover", blackbox_discover, _SCHEMAS["blackbox_discover"])
    registry.register("blackbox_fingerprint", blackbox_fingerprint, _SCHEMAS["blackbox_fingerprint"])
    registry.register("blackbox_spider", blackbox_spider, _SCHEMAS["blackbox_spider"])
    registry.register("blackbox_pull", blackbox_pull, _SCHEMAS["blackbox_pull"])
    registry.register("blackbox_push", blackbox_push, _SCHEMAS["blackbox_push"])
