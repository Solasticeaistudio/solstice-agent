"""
SSH Sandbox
===========
Remote execution via SSH. Connect to remote hosts, run commands,
and transfer files. Persistent sessions survive multiple tool calls.

Requires: pip install 'solstice-agent[ssh]'
"""

import logging
import os
import threading
from typing import Dict, Optional
from uuid import uuid4

log = logging.getLogger("solstice.tools.ssh")

_MAX_SESSIONS = 10


class _SSHSession:
    """One persistent SSH connection."""

    def __init__(self, session_id: str, host: str, port: int, username: str):
        self.session_id = session_id
        self.host = host
        self.port = port
        self.username = username
        self.client = None  # paramiko.SSHClient set after connect
        self._lock = threading.Lock()

    def exec(self, command: str, timeout: int = 60) -> str:
        with self._lock:
            _, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace").strip()
            rc = stdout.channel.recv_exit_status()
            if rc != 0 and err:
                return f"[exit {rc}]\nstdout: {out}\nstderr: {err}"
            if rc != 0:
                return f"[exit {rc}]\n{out}"
            return out or f"[exit 0, no output]"


class _SSHManager:
    """Manages persistent SSH sessions (process-level singleton)."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._sessions: Dict[str, _SSHSession] = {}
                inst._sessions_lock = threading.Lock()
                cls._instance = inst
        return cls._instance

    def connect(
        self,
        host: str,
        port: int,
        username: str,
        key_path: Optional[str],
        password: Optional[str],
    ) -> str:
        try:
            import paramiko
        except ImportError:
            raise RuntimeError(
                "paramiko not installed. Run: pip install 'solstice-agent[ssh]'"
            )

        with self._sessions_lock:
            if len(self._sessions) >= _MAX_SESSIONS:
                raise RuntimeError(
                    f"Max SSH sessions ({_MAX_SESSIONS}) reached. "
                    "Use ssh_disconnect to close one first."
                )

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs: dict = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": 15,
        }
        if key_path:
            kwargs["key_filename"] = os.path.expanduser(key_path)
        elif password:
            kwargs["password"] = password
        # else: rely on ssh-agent / default keys

        client.connect(**kwargs)

        session_id = f"ssh-{uuid4().hex[:8]}"
        session = _SSHSession(session_id, host, port, username)
        session.client = client

        with self._sessions_lock:
            self._sessions[session_id] = session

        log.info(f"SSH connected: {session_id} → {username}@{host}:{port}")
        return session_id

    def get(self, session_id: str) -> _SSHSession:
        with self._sessions_lock:
            session = self._sessions.get(session_id)
        if not session:
            raise RuntimeError(
                f"SSH session '{session_id}' not found. "
                "Use ssh_connect first, then pass the returned session ID."
            )
        return session

    def disconnect(self, session_id: str) -> None:
        with self._sessions_lock:
            session = self._sessions.pop(session_id, None)
        if session and session.client:
            try:
                session.client.close()
            except Exception:
                pass
            log.info(f"SSH disconnected: {session_id}")

    def list_sessions(self) -> list:
        with self._sessions_lock:
            return [
                {
                    "id": s.session_id,
                    "host": s.host,
                    "port": s.port,
                    "user": s.username,
                }
                for s in self._sessions.values()
            ]


_manager = _SSHManager()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def ssh_connect(
    host: str,
    username: str,
    port: int = 22,
    key_path: Optional[str] = None,
    password: Optional[str] = None,
) -> str:
    """Connect to a remote host via SSH. Returns a session ID."""
    session_id = _manager.connect(host, port, username, key_path, password)
    return f"Connected. Session ID: {session_id}"


def ssh_exec(session_id: str, command: str, timeout: int = 60) -> str:
    """Execute a shell command on a connected remote host."""
    session = _manager.get(session_id)
    return session.exec(command, timeout=timeout)


def ssh_disconnect(session_id: str) -> str:
    """Close an active SSH session."""
    _manager.disconnect(session_id)
    return f"Session {session_id} disconnected."


def ssh_list() -> str:
    """List all active SSH sessions."""
    sessions = _manager.list_sessions()
    if not sessions:
        return "No active SSH sessions."
    lines = [f"Active SSH sessions ({len(sessions)}):"]
    for s in sessions:
        lines.append(f"  {s['id']}: {s['user']}@{s['host']}:{s['port']}")
    return "\n".join(lines)


def ssh_upload(session_id: str, local_path: str, remote_path: str) -> str:
    """Upload a local file to the remote host via SFTP."""
    session = _manager.get(session_id)
    sftp = session.client.open_sftp()
    try:
        sftp.put(local_path, remote_path)
        return f"Uploaded {local_path} → {remote_path}"
    finally:
        sftp.close()


def ssh_download(session_id: str, remote_path: str, local_path: str) -> str:
    """Download a file from the remote host via SFTP."""
    session = _manager.get(session_id)
    sftp = session.client.open_sftp()
    try:
        sftp.get(remote_path, local_path)
        return f"Downloaded {remote_path} → {local_path}"
    finally:
        sftp.close()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "ssh_connect": {
        "name": "ssh_connect",
        "description": (
            "Connect to a remote host via SSH. "
            "Returns a session ID to use with ssh_exec, ssh_upload, etc. "
            "Prefer key-based auth; only use password as a fallback."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Remote hostname or IP address"},
                "username": {"type": "string", "description": "SSH login username"},
                "port": {"type": "integer", "description": "SSH port (default 22)"},
                "key_path": {
                    "type": "string",
                    "description": "Path to private key file (e.g. ~/.ssh/id_rsa)",
                },
                "password": {
                    "type": "string",
                    "description": "Password — prefer key_path when possible",
                },
            },
            "required": ["host", "username"],
        },
    },
    "ssh_exec": {
        "name": "ssh_exec",
        "description": "Run a shell command on a connected remote host and return the output.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session ID returned by ssh_connect",
                },
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 60)",
                },
            },
            "required": ["session_id", "command"],
        },
    },
    "ssh_disconnect": {
        "name": "ssh_disconnect",
        "description": "Close an active SSH session and free its resources.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID to close"},
            },
            "required": ["session_id"],
        },
    },
    "ssh_list": {
        "name": "ssh_list",
        "description": "List all currently active SSH sessions.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "ssh_upload": {
        "name": "ssh_upload",
        "description": "Upload a local file to the remote host via SFTP.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID from ssh_connect"},
                "local_path": {"type": "string", "description": "Path to the local file"},
                "remote_path": {
                    "type": "string",
                    "description": "Destination path on the remote host",
                },
            },
            "required": ["session_id", "local_path", "remote_path"],
        },
    },
    "ssh_download": {
        "name": "ssh_download",
        "description": "Download a file from the remote host to local disk via SFTP.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID from ssh_connect"},
                "remote_path": {"type": "string", "description": "File path on the remote host"},
                "local_path": {
                    "type": "string",
                    "description": "Local destination path",
                },
            },
            "required": ["session_id", "remote_path", "local_path"],
        },
    },
}


def register_ssh_tools(registry):
    """Register SSH tools with a ToolRegistry."""
    registry.register("ssh_connect", ssh_connect, _SCHEMAS["ssh_connect"])
    registry.register("ssh_exec", ssh_exec, _SCHEMAS["ssh_exec"])
    registry.register("ssh_disconnect", ssh_disconnect, _SCHEMAS["ssh_disconnect"])
    registry.register("ssh_list", ssh_list, _SCHEMAS["ssh_list"])
    registry.register("ssh_upload", ssh_upload, _SCHEMAS["ssh_upload"])
    registry.register("ssh_download", ssh_download, _SCHEMAS["ssh_download"])
