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
import socket
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
    """Check if a hostname resolves to a private/reserved IP.

    Performs actual DNS resolution to catch DNS rebinding attacks where
    an attacker-controlled hostname resolves to 127.0.0.1 or other
    private addresses.
    """
    # Check for localhost aliases first
    lower = hostname.lower()
    if lower in ("localhost", "localhost.localdomain", "ip6-localhost", "ip6-loopback"):
        return True

    # Try parsing as IP literal (handles standard, hex, and octal forms)
    try:
        addr = ipaddress.ip_address(hostname)
        return _is_dangerous_addr(addr)
    except ValueError:
        pass

    # Not an IP literal — resolve hostname via DNS to catch rebinding
    try:
        results = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in results:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                if _is_dangerous_addr(addr):
                    log.warning(f"DNS rebinding blocked: {hostname} resolves to private IP {ip_str}")
                    return True
            except ValueError:
                continue
    except socket.gaierror:
        pass  # DNS resolution failed — hostname doesn't resolve, not a rebinding risk

    return False


def _is_dangerous_addr(addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IP address is private, loopback, link-local, reserved, or multicast."""
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


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
        _blocked_ports = {
            22,     # SSH
            23,     # Telnet
            25,     # SMTP
            2379,   # etcd
            3306,   # MySQL
            5432,   # PostgreSQL
            6379,   # Redis
            9200,   # Elasticsearch
            11211,  # Memcached
            27017,  # MongoDB
        }
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
