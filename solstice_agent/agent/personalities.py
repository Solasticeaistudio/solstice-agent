"""
Personality Registry
====================
Resolve personality specifications from config.

Supports:
  - Built-in names: "default", "coder"
  - Inline definitions: {"name": "Nova", "role": "research analyst", ...}
"""

from .personality import Personality, DEFAULT, CODER

# Built-in personality registry
PERSONALITIES = {
    "default": DEFAULT,
    "coder": CODER,
}


def resolve_personality(spec) -> Personality:
    """
    Resolve a personality from a config specification.

    Args:
        spec: Either a string name ("default", "coder") or a dict with
              Personality fields (name, role, tone, rules, context).

    Returns:
        A Personality instance.
    """
    if isinstance(spec, str):
        return PERSONALITIES.get(spec, DEFAULT)
    elif isinstance(spec, dict):
        return Personality(
            name=spec.get("name", "Sol"),
            role=spec.get("role", "AI assistant"),
            tone=spec.get("tone", "Direct, helpful, concise"),
            rules=spec.get("rules", []),
            context=spec.get("context", ""),
        )
    elif isinstance(spec, Personality):
        return spec
    return DEFAULT


def register_personality(name: str, personality: Personality):
    """Register a custom personality by name."""
    PERSONALITIES[name] = personality


def list_personalities() -> list:
    """List all registered personality names."""
    return list(PERSONALITIES.keys())
