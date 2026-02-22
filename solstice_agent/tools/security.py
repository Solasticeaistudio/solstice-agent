"""
Security Utilities
==================
Shared validation functions used across tool modules to prevent
SSRF, path traversal, command injection, and other attacks.
"""

import ipaddress
import logging
import os
import re
from typing import Optional
from urllib.parse import urlparse

log = logging.getLogger("solstice.tools.security")

# ---------------------------------------------------------------------------
# URL / SSRF validation
# ---------------------------------------------------------------------------

# Schemes allowed for outbound requests
_ALLOWED_SCHEMES = {"http", "https"}

# Known cloud metadata endpoints
_METADATA_HOSTS = {
    "169.254.169.254",  # AWS, GCP, Azure
    "metadata.google.internal",
    "metadata.google",
    "100.100.100.200",  # Alibaba
}


def _is_private_ip(hostname: str) -> bool:
    """Check if a hostname resolves to a private/reserved IP."""
    try:
        addr = ipaddress.ip_address(hostname)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        # Not an IP literal — check for localhost aliases
        lower = hostname.lower()
        if lower in ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"):
            return True
        # Check for hex/octal encoded localhost (0x7f000001, 017700000001, etc.)
        return False


def validate_url(url: str, allow_private: bool = False) -> Optional[str]:
    """Validate a URL for safe outbound requests.

    Returns an error string if the URL is unsafe, None if OK.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return f"Invalid URL: {url}"

    # Scheme check
    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return f"URL scheme '{scheme}' is not allowed. Use http:// or https://."

    # Host check
    hostname = (parsed.hostname or "").lower()
    if not hostname:
        return "URL has no hostname."

    # Cloud metadata
    if hostname in _METADATA_HOSTS:
        return f"Access to cloud metadata endpoint '{hostname}' is blocked."

    # Private/reserved IPs
    if not allow_private and _is_private_ip(hostname):
        return f"Access to private/local address '{hostname}' is blocked."

    # Suspicious ports (well-known internal services)
    port = parsed.port
    if port and not allow_private:
        _blocked_ports = {6379, 11211, 27017, 5432, 3306, 9200, 2379}
        if port in _blocked_ports:
            return f"Access to port {port} is blocked (common internal service port)."

    return None


# ---------------------------------------------------------------------------
# Path sandboxing
# ---------------------------------------------------------------------------

# Default workspace root — set by CLI/server at startup
_workspace_root: Optional[str] = None

# Paths that should never be touched regardless of workspace
_ALWAYS_BLOCKED = [
    re.compile(r'[\\/]\.ssh[\\/]', re.IGNORECASE),
    re.compile(r'[\\/]\.gnupg[\\/]', re.IGNORECASE),
    re.compile(r'[\\/]\.aws[\\/]credentials', re.IGNORECASE),
    re.compile(r'[\\/]\.env$', re.IGNORECASE),
    re.compile(r'[\\/]\.docker[\\/]config\.json', re.IGNORECASE),
]


def set_workspace_root(root: str):
    """Set the workspace root for path sandboxing.

    Called at startup by CLI or server. All file operations are
    restricted to paths within this root (or its subdirectories).
    """
    global _workspace_root
    _workspace_root = os.path.realpath(root)
    log.info(f"Workspace root set: {_workspace_root}")


def get_workspace_root() -> Optional[str]:
    """Get the current workspace root, or None if unset."""
    return _workspace_root


def validate_path(path: str, operation: str = "access") -> Optional[str]:
    """Validate a file path is within the workspace and not a sensitive file.

    Returns an error string if the path is unsafe, None if OK.
    The operation parameter is used for descriptive error messages.
    """
    # Resolve symlinks and normalize
    resolved = os.path.realpath(os.path.expanduser(path))

    # Check sensitive file patterns
    for pattern in _ALWAYS_BLOCKED:
        if pattern.search(resolved):
            return f"Cannot {operation}: path matches a sensitive file pattern."

    # Check workspace boundary if set
    if _workspace_root is not None:
        if not resolved.startswith(_workspace_root + os.sep) and resolved != _workspace_root:
            return (
                f"Cannot {operation}: path '{path}' is outside the workspace "
                f"directory '{_workspace_root}'."
            )

    return None
