"""
API Registry / Marketplace
===========================
Catalog of known APIs with semantic search, credential management, and
quality tracking. Bridges to Blackbox for one-click API connections.

Storage layout:
    ~/.solstice-agent/
        registry/
            catalog.json       # All registered APIs
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.tools.api_registry")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

_REGISTRY_DIR = Path.home() / ".solstice-agent" / "registry"
_CATALOG_FILE = "catalog.json"
_SEED_CATALOG = Path(__file__).parent / "seed_catalog.json"

_catalog: Optional[Dict[str, Dict[str, Any]]] = None


def _ensure_dir():
    _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)


def _catalog_path() -> Path:
    return _REGISTRY_DIR / _CATALOG_FILE


def _load_catalog() -> Dict[str, Dict[str, Any]]:
    global _catalog
    if _catalog is not None:
        return _catalog

    _ensure_dir()
    path = _catalog_path()

    if path.exists():
        try:
            _catalog = json.loads(path.read_text(encoding="utf-8"))
            return _catalog
        except Exception:
            log.warning("Failed to load catalog, starting fresh")

    # First run — seed from bundled catalog
    if _SEED_CATALOG.exists():
        try:
            _catalog = json.loads(_SEED_CATALOG.read_text(encoding="utf-8"))
            _save_catalog()
            log.info(f"Seeded registry with {len(_catalog)} APIs")
            return _catalog
        except Exception:
            log.warning("Failed to load seed catalog")

    _catalog = {}
    return _catalog


def _save_catalog():
    if _catalog is None:
        return
    _ensure_dir()
    _catalog_path().write_text(
        json.dumps(_catalog, indent=2, default=str), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Search engine
# ---------------------------------------------------------------------------

def _score_match(entry: Dict[str, Any], query: str, category: Optional[str] = None) -> float:
    score = 0.0
    q = query.lower().strip()
    words = set(q.split())

    name = entry.get("name", "").lower()
    desc = entry.get("description", "").lower()
    tags = [t.lower() for t in entry.get("tags", [])]
    cat = entry.get("category", "").lower()

    # Hard category filter
    if category and cat != category.lower():
        return 0.0
    if category:
        score += 30

    # Name
    if q == name:
        score += 100
    elif q in name or name in q:
        score += 50

    # Tags
    for tag in tags:
        if tag in words or tag == q:
            score += 40
        elif any(tag in w or w in tag for w in words):
            score += 20

    # Description words
    desc_words = set(desc.split())
    score += len(words & desc_words) * 10

    if q in desc:
        score += 25

    return score


def _fmt_pct(val) -> str:
    return f"{val:.1%}" if val is not None else "n/a"


def _fmt_ms(val) -> str:
    return f"{val:.0f}ms" if val is not None else "n/a"


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def registry_search(query: str, category: Optional[str] = None) -> str:
    """Search the API catalog by capability."""
    catalog = _load_catalog()
    if not catalog:
        return "API registry is empty. Use registry_add to register APIs."

    scored: List[tuple] = []
    for name, entry in catalog.items():
        s = _score_match(entry, query, category)
        if s > 0:
            scored.append((s, name, entry))

    if not scored:
        cats = sorted(set(e.get("category", "uncategorized") for e in catalog.values()))
        return (
            f"No APIs match '{query}'."
            + (f" Category '{category}' applied." if category else "")
            + f"\nAvailable categories: {', '.join(cats)}"
            + f"\nTotal APIs in registry: {len(catalog)}"
        )

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:10]

    lines = [f"Found {len(scored)} API(s) matching '{query}':"]
    for rank, (_, name, entry) in enumerate(top, 1):
        tags_str = ", ".join(entry.get("tags", [])[:5])
        pricing = entry.get("pricing", "unknown")
        stats = entry.get("stats", {})
        success = stats.get("success_rate")
        success_str = f", {success:.0%} success" if success is not None else ""
        lines.append(
            f"  {rank}. {name} ({entry.get('category', '?')}) — {entry.get('description', '')}"
            f"\n     Tags: [{tags_str}] | Pricing: {pricing}{success_str}"
        )

    if len(scored) > 10:
        lines.append(f"  ... and {len(scored) - 10} more.")

    return "\n".join(lines)


def registry_add(
    name: str,
    url: str,
    description: str,
    category: str,
    tags: str,
    auth_type: Optional[str] = None,
    auth_token: Optional[str] = None,
    pricing: Optional[str] = None,
) -> str:
    """Register a new API in the catalog."""
    catalog = _load_catalog()
    key = name.lower().strip().replace(" ", "_")

    if key in catalog:
        return f"API '{key}' already exists. Use registry_remove first to replace it."

    valid_auth = {"bearer", "basic", "api_key", "none"}
    if auth_type and auth_type.lower() not in valid_auth:
        return f"Invalid auth_type '{auth_type}'. Use: bearer, basic, api_key, or none."

    tag_list = [t.strip().lower() for t in tags.split(",") if t.strip()]

    catalog[key] = {
        "name": key,
        "url": url.rstrip("/"),
        "description": description,
        "category": category.lower().strip(),
        "tags": tag_list,
        "auth_type": (auth_type or "none").lower(),
        "auth_token": auth_token or "",
        "pricing": (pricing or "unknown").lower(),
        "endpoints_discovered": 0,
        "added_at": datetime.now(timezone.utc).isoformat(),
        "last_used": None,
        "stats": {
            "total_calls": 0,
            "success_rate": None,
            "avg_latency_ms": None,
            "last_checked": None,
        },
    }

    _save_catalog()
    return f"Registered '{key}' ({url}) in category '{category}'. Tags: {tag_list}"


def registry_get(name: str) -> str:
    """Get full details on a specific API from the registry."""
    catalog = _load_catalog()
    key = name.lower().strip().replace(" ", "_")

    entry = catalog.get(key)
    if not entry:
        matches = [k for k in catalog if key in k or k in key]
        if matches:
            return f"API '{name}' not found. Did you mean: {', '.join(matches)}?"
        return f"API '{name}' not found. Use registry_search to find APIs."

    stats = entry.get("stats", {})
    lines = [
        f"API: {entry['name']}",
        f"  URL: {entry['url']}",
        f"  Description: {entry['description']}",
        f"  Category: {entry['category']}",
        f"  Tags: {', '.join(entry.get('tags', []))}",
        f"  Auth: {entry.get('auth_type', 'none')}"
        + (" (token configured)" if entry.get("auth_token") else " (no token)"),
        f"  Pricing: {entry.get('pricing', 'unknown')}",
        f"  Endpoints discovered: {entry.get('endpoints_discovered', 0)}",
        f"  Added: {str(entry.get('added_at', '?'))[:16]}",
        f"  Last used: {entry.get('last_used') or 'never'}",
        "  Stats:",
        f"    Total calls: {stats.get('total_calls', 0)}",
        f"    Success rate: {_fmt_pct(stats.get('success_rate'))}",
        f"    Avg latency: {_fmt_ms(stats.get('avg_latency_ms'))}",
        f"    Last checked: {stats.get('last_checked') or 'never'}",
    ]
    return "\n".join(lines)


def registry_connect(name: str) -> str:
    """
    One-step connection: pull API from registry and auto-connect Blackbox
    with stored credentials. Auto-discovers the API schema.
    """
    catalog = _load_catalog()
    key = name.lower().strip().replace(" ", "_")

    entry = catalog.get(key)
    if not entry:
        matches = [k for k in catalog if key in k or k in key]
        if matches:
            return f"API '{name}' not found. Did you mean: {', '.join(matches)}?"
        return f"API '{name}' not found. Use registry_search or registry_add first."

    url = entry["url"]
    auth_token = entry.get("auth_token") or None
    auth_type = entry.get("auth_type", "none")

    from .blackbox import blackbox_connect, blackbox_discover

    effective_token = auth_token if auth_type != "none" else None

    start = time.time()
    connect_result = blackbox_connect(url=url, auth_token=effective_token, allow_write=False)
    latency_ms = (time.time() - start) * 1000

    # Update stats
    entry["last_used"] = datetime.now(timezone.utc).isoformat()
    stats = entry.setdefault("stats", {})
    stats["last_checked"] = datetime.now(timezone.utc).isoformat()
    total = stats.get("total_calls", 0) + 1
    stats["total_calls"] = total

    connected = "Connected to" in connect_result
    old_count = total - 1 if total > 1 else 0

    if connected:
        old_avg = stats.get("avg_latency_ms") or latency_ms
        stats["avg_latency_ms"] = (old_avg * old_count + latency_ms) / total

        old_rate = stats.get("success_rate") or 1.0
        stats["success_rate"] = (old_rate * old_count + 1.0) / total

        discover_result = blackbox_discover()
        ep_match = re.search(r"Endpoints:\s*(\d+)", discover_result)
        if ep_match:
            entry["endpoints_discovered"] = int(ep_match.group(1))
    else:
        old_rate = stats.get("success_rate") or 0.0
        stats["success_rate"] = (old_rate * old_count + 0.0) / total

    _save_catalog()

    lines = [connect_result]
    if connected:
        lines.append(f"(Registry: updated stats for '{key}')")
        if entry.get("endpoints_discovered", 0) > 0:
            lines.append(f"Endpoints in catalog: {entry['endpoints_discovered']}")
    else:
        lines.append(f"(Registry: marked connection failure for '{key}')")

    return "\n".join(lines)


def registry_stats(name: str) -> str:
    """Report quality metrics for a registered API."""
    catalog = _load_catalog()
    key = name.lower().strip().replace(" ", "_")

    entry = catalog.get(key)
    if not entry:
        return f"API '{name}' not found in registry."

    stats = entry.get("stats", {})
    total = stats.get("total_calls", 0)

    if total == 0:
        return (
            f"No usage data for '{key}'. "
            f"Use registry_connect to connect and start tracking metrics."
        )

    lines = [
        f"Quality report for '{key}' ({entry['url']}):",
        f"  Total API calls tracked: {total}",
        f"  Success rate: {_fmt_pct(stats.get('success_rate'))}",
        f"  Average latency: {_fmt_ms(stats.get('avg_latency_ms'))}",
        f"  Last checked: {stats.get('last_checked') or 'never'}",
        f"  Last used: {entry.get('last_used') or 'never'}",
        f"  Endpoints discovered: {entry.get('endpoints_discovered', 0)}",
    ]

    rate = stats.get("success_rate")
    avg_lat = stats.get("avg_latency_ms")

    if rate is not None:
        if rate >= 0.95:
            lines.append("  Health: EXCELLENT")
        elif rate >= 0.80:
            lines.append("  Health: GOOD")
        elif rate >= 0.50:
            lines.append("  Health: DEGRADED")
        else:
            lines.append("  Health: POOR")

    if avg_lat is not None:
        if avg_lat < 200:
            lines.append("  Speed: FAST")
        elif avg_lat < 1000:
            lines.append("  Speed: NORMAL")
        else:
            lines.append("  Speed: SLOW")

    return "\n".join(lines)


def registry_remove(name: str) -> str:
    """Remove an API from the catalog."""
    catalog = _load_catalog()
    key = name.lower().strip().replace(" ", "_")

    if key not in catalog:
        return f"API '{name}' not found in registry."

    entry = catalog.pop(key)
    _save_catalog()
    return f"Removed '{key}' ({entry.get('url', '?')}) from the registry."


# ---------------------------------------------------------------------------
# Schemas (OpenAI function-calling format)
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "registry_search": {
        "name": "registry_search",
        "description": (
            "Search the API catalog by capability. Describe what you need in plain "
            "English (e.g. 'send SMS', 'geocoding', 'payment processing') and get "
            "matching APIs ranked by relevance. Optionally filter by category."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What capability you need (e.g. 'SMS', 'weather data', 'image recognition')",
                },
                "category": {
                    "type": "string",
                    "description": "Filter by category (e.g. 'communication', 'maps', 'ai'). Optional.",
                },
            },
            "required": ["query"],
        },
    },
    "registry_add": {
        "name": "registry_add",
        "description": (
            "Register a new API in the catalog for future reuse. Provide the name, "
            "URL, description, category, and comma-separated tags. Optionally include "
            "auth configuration and pricing info."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short name for the API (e.g. 'twilio', 'stripe')",
                },
                "url": {
                    "type": "string",
                    "description": "Base URL of the API (e.g. 'https://api.twilio.com')",
                },
                "description": {
                    "type": "string",
                    "description": "What the API does, in one sentence",
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g. communication, maps, weather, payments, ai, data, devtools)",
                },
                "tags": {
                    "type": "string",
                    "description": "Comma-separated tags for search (e.g. 'sms, voice, messaging')",
                },
                "auth_type": {
                    "type": "string",
                    "description": "Authentication type",
                    "enum": ["bearer", "basic", "api_key", "none"],
                },
                "auth_token": {
                    "type": "string",
                    "description": "Auth token or API key (stored for auto-connect)",
                },
                "pricing": {
                    "type": "string",
                    "description": "Pricing model",
                    "enum": ["free", "freemium", "pay-per-use", "subscription"],
                },
            },
            "required": ["name", "url", "description", "category", "tags"],
        },
    },
    "registry_get": {
        "name": "registry_get",
        "description": (
            "Get full details on a specific API from the registry including its URL, "
            "auth configuration, discovered endpoints, and quality stats."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the API to look up",
                },
            },
            "required": ["name"],
        },
    },
    "registry_connect": {
        "name": "registry_connect",
        "description": (
            "One-step API connection: pull an API from the registry and auto-connect "
            "Blackbox to it with stored credentials. Also auto-discovers the API schema. "
            "After this, use blackbox_pull and blackbox_push on the connected API."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the API to connect to",
                },
            },
            "required": ["name"],
        },
    },
    "registry_stats": {
        "name": "registry_stats",
        "description": (
            "Report quality metrics for a registered API: average latency, success "
            "rate, total calls, and health assessment."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the API to get stats for",
                },
            },
            "required": ["name"],
        },
    },
    "registry_remove": {
        "name": "registry_remove",
        "description": "Remove an API from the catalog.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the API to remove",
                },
            },
            "required": ["name"],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_registry_tools(registry):
    """Register API registry/marketplace tools with a ToolRegistry."""
    _load_catalog()  # Ensure catalog is loaded (seeds on first run)
    registry.register("registry_search", registry_search, _SCHEMAS["registry_search"])
    registry.register("registry_add", registry_add, _SCHEMAS["registry_add"])
    registry.register("registry_get", registry_get, _SCHEMAS["registry_get"])
    registry.register("registry_connect", registry_connect, _SCHEMAS["registry_connect"])
    registry.register("registry_stats", registry_stats, _SCHEMAS["registry_stats"])
    registry.register("registry_remove", registry_remove, _SCHEMAS["registry_remove"])
