"""
Docker Sandbox Tools
====================
Isolated container execution for untrusted code and secure workflows.
Requires: pip install docker
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("solstice.tools.docker_sandbox")

_SANDBOX_PREFIX = "sol_sandbox_"
_SANDBOX_LABEL = "sol.sandbox"
_client = None


# ---------------------------------------------------------------------------
# Client management
# ---------------------------------------------------------------------------

def _ensure_client():
    """Get or create the Docker client."""
    global _client
    if _client is None:
        try:
            import docker
        except ImportError:
            return None, "Error: Docker sandbox requires: pip install docker"
        try:
            _client = docker.from_env()
            _client.ping()
        except Exception as e:
            _client = None
            return None, f"Error: Cannot connect to Docker daemon: {e}"
    return _client, None


def _validate_volumes(volumes_str: Optional[str]) -> tuple:
    """Parse and validate volume mounts. Returns (dict, error_str).

    Security: Uses os.path.realpath to resolve symlinks before checking
    that the path is within the current working directory.
    """
    if not volumes_str:
        return {}, None

    try:
        vols = json.loads(volumes_str)
        if not isinstance(vols, dict):
            return {}, "Error: volumes must be a JSON object like {\"./src\": \"/app/src\"}"
    except json.JSONDecodeError as e:
        return {}, f"Error: Invalid volumes JSON: {e}"

    cwd = os.path.realpath(os.getcwd())
    validated = {}
    for host_path, container_path in vols.items():
        # Resolve symlinks to prevent bypass
        real_host = os.path.realpath(host_path)
        # Security: reject paths outside CWD (use os.sep to prevent prefix collisions)
        if real_host != cwd and not real_host.startswith(cwd + os.sep):
            return {}, (
                f"Error: Volume mount '{host_path}' resolves to '{real_host}' "
                f"which is outside the current directory. "
                f"Only paths under '{cwd}' are allowed for security."
            )
        if not os.path.exists(real_host):
            return {}, f"Error: Host path does not exist: {real_host}"
        validated[real_host] = {"bind": container_path, "mode": "rw"}

    return validated, None


def _gen_name() -> str:
    """Generate a unique sandbox container name."""
    return f"{_SANDBOX_PREFIX}{int(time.time() * 1000) % 100000}"


def _get_sandbox_container(client, container_ref: str):
    """Get a container by name/ID, verifying it has our sandbox label.

    Returns (container, None) on success or (None, error_str) on failure.
    """
    try:
        ctr = client.containers.get(container_ref)
    except Exception as e:
        return None, f"Error: Container '{container_ref}' not found: {e}"

    labels = ctr.labels or {}
    if labels.get(_SANDBOX_LABEL) != "true":
        return None, (
            f"Error: Container '{container_ref}' is not a Solstice sandbox. "
            f"Only containers created by sandbox_start/sandbox_run can be managed."
        )
    return ctr, None


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def sandbox_run(
    command: str,
    image: str = "python:3.12-slim",
    timeout: int = 60,
    volumes: Optional[str] = None,
    network: bool = False,
    memory_limit: str = "512m",
    cpu_limit: float = 1.0,
) -> str:
    """Run a command in an isolated Docker container. Returns stdout + stderr."""
    client, err = _ensure_client()
    if err:
        return err

    vols, vol_err = _validate_volumes(volumes)
    if vol_err:
        return vol_err

    name = _gen_name()
    try:
        output = client.containers.run(
            image=image,
            command=["sh", "-c", command],
            name=name,
            remove=True,
            network_disabled=not network,
            mem_limit=memory_limit,
            nano_cpus=int(cpu_limit * 1e9),
            volumes=vols or None,
            labels={_SANDBOX_LABEL: "true"},
            security_opt=["no-new-privileges"],
            stdout=True,
            stderr=True,
            detach=False,
            timeout=timeout,
        )
        decoded = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)
        return decoded if decoded.strip() else "(no output)"
    except Exception as e:
        err_str = str(e)
        if "404" in err_str or "not found" in err_str.lower():
            return f"Error: Image '{image}' not found. Try: docker pull {image}"
        return f"Error: {err_str}"


def sandbox_start(
    image: str = "python:3.12-slim",
    name: Optional[str] = None,
    volumes: Optional[str] = None,
    network: bool = False,
    memory_limit: str = "512m",
    cpu_limit: float = 1.0,
) -> str:
    """Start a persistent sandbox container."""
    client, err = _ensure_client()
    if err:
        return err

    vols, vol_err = _validate_volumes(volumes)
    if vol_err:
        return vol_err

    cname = name or _gen_name()
    try:
        container = client.containers.run(
            image=image,
            command="tail -f /dev/null",
            name=cname,
            network_disabled=not network,
            mem_limit=memory_limit,
            nano_cpus=int(cpu_limit * 1e9),
            labels={_SANDBOX_LABEL: "true"},
            security_opt=["no-new-privileges"],
            volumes=vols or None,
            detach=True,
        )
        return f"Sandbox started: {cname} (ID: {container.short_id}, image: {image})"
    except Exception as e:
        return f"Error: {e}"


def sandbox_exec(
    container: str,
    command: str,
    timeout: int = 60,
) -> str:
    """Execute a command in a running sandbox container."""
    client, err = _ensure_client()
    if err:
        return err

    ctr, ctr_err = _get_sandbox_container(client, container)
    if ctr_err:
        return ctr_err

    try:
        exit_code, output = ctr.exec_run(
            ["sh", "-c", command],
            demux=True,
            timeout=timeout,
        )
        stdout = output[0].decode("utf-8", errors="replace") if output[0] else ""
        stderr = output[1].decode("utf-8", errors="replace") if output[1] else ""
        result = stdout + stderr
        if exit_code != 0:
            result += f"\n(exit code: {exit_code})"
        return result.strip() if result.strip() else "(no output)"
    except Exception as e:
        return f"Error: {e}"


def sandbox_stop(container: str) -> str:
    """Stop and remove a sandbox container."""
    client, err = _ensure_client()
    if err:
        return err

    ctr, ctr_err = _get_sandbox_container(client, container)
    if ctr_err:
        return ctr_err

    try:
        ctr.stop(timeout=5)
        ctr.remove(force=True)
        return f"Sandbox stopped and removed: {container}"
    except Exception as e:
        return f"Error: {e}"


def sandbox_list() -> str:
    """List all running sandbox containers."""
    client, err = _ensure_client()
    if err:
        return err

    try:
        containers = client.containers.list(
            filters={"label": _SANDBOX_LABEL}
        )
        if not containers:
            return "No sandbox containers running."

        lines = [f"Sandbox containers ({len(containers)}):"]
        for ctr in containers:
            created = ctr.attrs.get("Created", "?")[:19]
            lines.append(
                f"  {ctr.name} | {ctr.short_id} | "
                f"{ctr.image.tags[0] if ctr.image.tags else '?'} | "
                f"{ctr.status} | created: {created}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def sandbox_copy_in(
    container: str,
    host_path: str,
    container_path: str,
) -> str:
    """Copy a file from the host into a sandbox container."""
    client, err = _ensure_client()
    if err:
        return err

    # Restrict to CWD
    cwd = os.path.realpath(os.getcwd())
    real_host = os.path.realpath(host_path)
    if real_host != cwd and not real_host.startswith(cwd + os.sep):
        return f"Error: Can only copy files from within the current directory '{cwd}'."

    if not os.path.isfile(host_path):
        return f"Error: File not found: {host_path}"

    ctr, ctr_err = _get_sandbox_container(client, container)
    if ctr_err:
        return ctr_err

    try:
        import tarfile
        import io

        # Create a tar archive with the file
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(host_path, arcname=os.path.basename(container_path))
        tar_stream.seek(0)

        dest_dir = str(Path(container_path).parent) or "/"
        ctr.put_archive(dest_dir, tar_stream)
        return f"Copied {host_path} → {container}:{container_path}"
    except Exception as e:
        return f"Error: {e}"


def sandbox_copy_out(
    container: str,
    container_path: str,
    host_path: str,
) -> str:
    """Copy a file from a sandbox container to the host."""
    client, err = _ensure_client()
    if err:
        return err

    # Restrict output to CWD
    cwd = os.path.realpath(os.getcwd())
    real_host = os.path.realpath(os.path.dirname(os.path.abspath(host_path)))
    if real_host != cwd and not real_host.startswith(cwd + os.sep):
        return f"Error: Can only copy files into the current directory '{cwd}'."

    ctr, ctr_err = _get_sandbox_container(client, container)
    if ctr_err:
        return ctr_err

    try:
        import tarfile
        import io

        bits, stat = ctr.get_archive(container_path)

        tar_stream = io.BytesIO()
        for chunk in bits:
            tar_stream.write(chunk)
        tar_stream.seek(0)

        with tarfile.open(fileobj=tar_stream, mode="r") as tar:
            # Extract the single file
            member = tar.getmembers()[0]
            f = tar.extractfile(member)
            if f is None:
                return f"Error: Cannot read {container_path} from container (is it a directory?)"
            Path(host_path).parent.mkdir(parents=True, exist_ok=True)
            with open(host_path, "wb") as out:
                out.write(f.read())

        return f"Copied {container}:{container_path} → {host_path}"
    except Exception as e:
        return f"Error: {e}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "sandbox_run": {
        "name": "sandbox_run",
        "description": (
            "Run a command in an isolated Docker container. Secure defaults: "
            "no network, capped memory/CPU, auto-removed after execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
                "image": {"type": "string", "description": "Docker image (default 'python:3.12-slim')"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
                "volumes": {"type": "string", "description": "JSON object of host:container mounts"},
                "network": {"type": "boolean", "description": "Enable network access (default false)"},
                "memory_limit": {"type": "string", "description": "Memory limit (default '512m')"},
                "cpu_limit": {"type": "number", "description": "CPU limit in cores (default 1.0)"},
            },
            "required": ["command"],
        },
    },
    "sandbox_start": {
        "name": "sandbox_start",
        "description": (
            "Start a persistent Docker sandbox container for multi-step workflows. "
            "Use sandbox_exec to run commands in it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "Docker image (default 'python:3.12-slim')"},
                "name": {"type": "string", "description": "Container name (auto-generated if omitted)"},
                "volumes": {"type": "string", "description": "JSON object of host:container mounts"},
                "network": {"type": "boolean", "description": "Enable network (default false)"},
                "memory_limit": {"type": "string", "description": "Memory limit (default '512m')"},
                "cpu_limit": {"type": "number", "description": "CPU limit in cores (default 1.0)"},
            },
            "required": [],
        },
    },
    "sandbox_exec": {
        "name": "sandbox_exec",
        "description": "Execute a command inside a running sandbox container.",
        "parameters": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name or ID"},
                "command": {"type": "string", "description": "Command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
            },
            "required": ["container", "command"],
        },
    },
    "sandbox_stop": {
        "name": "sandbox_stop",
        "description": "Stop and remove a sandbox container.",
        "parameters": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name or ID"},
            },
            "required": ["container"],
        },
    },
    "sandbox_list": {
        "name": "sandbox_list",
        "description": "List all running sandbox containers.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "sandbox_copy_in": {
        "name": "sandbox_copy_in",
        "description": "Copy a file from the host into a running sandbox container.",
        "parameters": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name or ID"},
                "host_path": {"type": "string", "description": "Path on the host"},
                "container_path": {"type": "string", "description": "Destination inside container"},
            },
            "required": ["container", "host_path", "container_path"],
        },
    },
    "sandbox_copy_out": {
        "name": "sandbox_copy_out",
        "description": "Copy a file from a sandbox container to the host.",
        "parameters": {
            "type": "object",
            "properties": {
                "container": {"type": "string", "description": "Container name or ID"},
                "container_path": {"type": "string", "description": "Path inside container"},
                "host_path": {"type": "string", "description": "Destination on host"},
            },
            "required": ["container", "container_path", "host_path"],
        },
    },
}


def register_docker_tools(registry):
    """Register Docker sandbox tools."""
    registry.register("sandbox_run", sandbox_run, _SCHEMAS["sandbox_run"])
    registry.register("sandbox_start", sandbox_start, _SCHEMAS["sandbox_start"])
    registry.register("sandbox_exec", sandbox_exec, _SCHEMAS["sandbox_exec"])
    registry.register("sandbox_stop", sandbox_stop, _SCHEMAS["sandbox_stop"])
    registry.register("sandbox_list", sandbox_list, _SCHEMAS["sandbox_list"])
    registry.register("sandbox_copy_in", sandbox_copy_in, _SCHEMAS["sandbox_copy_in"])
    registry.register("sandbox_copy_out", sandbox_copy_out, _SCHEMAS["sandbox_copy_out"])
