"""
Modal Sandbox
=============
Serverless execution via Modal (modal.com).

Run Python code on cloud CPUs or GPUs without managing infrastructure.
Scales to zero when idle — no cost for unused capacity.

Requires: pip install 'solstice-agent[modal]'
Then authenticate once: modal token new
"""

import logging
import os
import subprocess
import sys
import tempfile
import threading
from typing import Dict, List, Optional
from uuid import uuid4

log = logging.getLogger("solstice.tools.modal")

_deployments: Dict[str, Dict] = {}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_modal():
    try:
        import modal  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "modal not installed. Run: pip install 'solstice-agent[modal]'\n"
            "Then authenticate: modal token new"
        )


def _build_modal_script(
    code: str,
    image: str,
    gpu: Optional[str],
    cpu: float,
    memory: int,
    secrets: List[str],
    app_name: str = "sol-ephemeral",
    schedule: Optional[str] = None,
) -> str:
    """Produce a self-contained Modal app Python file."""

    # Image spec
    if any(image.startswith(p) for p in ("docker://", "ghcr.io/", "gcr.io/", "registry.")):
        uri = image.removeprefix("docker://")
        image_spec = f'modal.Image.from_registry("{uri}")'
    else:
        _presets = {
            "debian-slim": "modal.Image.debian_slim()",
            "ubuntu": 'modal.Image.from_registry("ubuntu:22.04")',
        }
        image_spec = _presets.get(image, "modal.Image.debian_slim()")

    # Optional decorator args
    extras: List[str] = []
    if gpu:
        extras.append(f'    gpu="{gpu}",')
    if secrets:
        secret_args = ", ".join(f'modal.Secret.from_name("{s}")' for s in secrets)
        extras.append(f"    secrets=[{secret_args}],")
    extras_str = "\n".join(extras)

    sched_decorator = ""
    if schedule:
        sched_decorator = f'@app.function(schedule=modal.Cron("{schedule}"))\n'

    # Wrap plain script in a function
    if code.strip().startswith("def "):
        wrapped = code
        entrypoint_body = "    main()"
    else:
        indented = "\n".join("    " + line for line in code.splitlines())
        wrapped = f"def main():\n{indented}"
        entrypoint_body = "    main()"

    return f"""import modal

app = modal.App("{app_name}")

@app.function(
    image={image_spec},
    cpu={cpu},
    memory={memory},
{extras_str}
)
{sched_decorator}def sol_task():
    {wrapped.replace(chr(10), chr(10) + "    ")}

@app.local_entrypoint()
def _entrypoint():
{entrypoint_body}
"""


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def modal_run(
    code: str,
    image: str = "debian-slim",
    gpu: Optional[str] = None,
    cpu: float = 1.0,
    memory: int = 512,
    timeout: int = 300,
    secrets: Optional[List[str]] = None,
) -> str:
    """
    Run Python code on Modal (ephemeral, blocking).
    Returns stdout from the function.

    image: 'debian-slim', 'ubuntu', or a Docker/OCI URI.
    gpu:   Optional GPU type, e.g. 'T4', 'A10G', 'A100'.
    """
    _require_modal()

    run_id = f"sol-{uuid4().hex[:8]}"
    script = _build_modal_script(code, image, gpu, cpu, memory, secrets or [], app_name=run_id)
    script_path = os.path.join(tempfile.gettempdir(), f"{run_id}.py")

    with open(script_path, "w") as fh:
        fh.write(script)

    try:
        result = subprocess.run(
            [sys.executable, "-m", "modal", "run", script_path],
            capture_output=True,
            text=True,
            timeout=timeout + 60,
        )
        os.unlink(script_path)
        if result.returncode != 0:
            return f"Modal run failed (exit {result.returncode}):\n{result.stderr[-2000:]}"
        return result.stdout or "[Modal run completed, no stdout]"
    except subprocess.TimeoutExpired:
        try:
            os.unlink(script_path)
        except OSError:
            pass
        return f"[timed out after {timeout}s]"


def modal_deploy(
    code: str,
    app_name: str,
    image: str = "debian-slim",
    gpu: Optional[str] = None,
    schedule: Optional[str] = None,
) -> str:
    """
    Deploy a persistent Modal app.
    schedule: optional cron string, e.g. '0 9 * * *' for daily at 09:00 UTC.
    Returns the Modal dashboard URL.
    """
    _require_modal()

    script = _build_modal_script(code, image, gpu, 1.0, 512, [], app_name=app_name, schedule=schedule)
    script_path = os.path.join(tempfile.gettempdir(), f"{app_name}.py")

    with open(script_path, "w") as fh:
        fh.write(script)

    result = subprocess.run(
        [sys.executable, "-m", "modal", "deploy", script_path],
        capture_output=True,
        text=True,
        timeout=120,
    )

    if result.returncode != 0:
        return f"Deploy failed:\n{result.stderr[-2000:]}"

    with _lock:
        _deployments[app_name] = {
            "app_name": app_name,
            "script_path": script_path,
            "schedule": schedule,
        }

    return result.stdout or f"App '{app_name}' deployed."


def modal_list() -> str:
    """List Modal apps on your account."""
    _require_modal()
    result = subprocess.run(
        [sys.executable, "-m", "modal", "app", "list"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"Failed to list apps:\n{result.stderr}"
    return result.stdout or "No apps found."


def modal_stop(app_name: str) -> str:
    """Stop a deployed Modal app."""
    _require_modal()
    result = subprocess.run(
        [sys.executable, "-m", "modal", "app", "stop", app_name],
        capture_output=True,
        text=True,
        timeout=30,
    )
    with _lock:
        _deployments.pop(app_name, None)
    if result.returncode != 0:
        return f"Failed to stop '{app_name}':\n{result.stderr}"
    return f"App '{app_name}' stopped."


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "modal_run": {
        "name": "modal_run",
        "description": (
            "Run Python code serverlessly on Modal (blocking, ephemeral). "
            "Ideal for GPU workloads, heavy computation, or tasks that need "
            "cloud resources without managing infrastructure. "
            "Scales to zero — no cost when idle."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to run (plain script or a 'def main()' function)",
                },
                "image": {
                    "type": "string",
                    "description": "Base image: 'debian-slim', 'ubuntu', or a Docker URI",
                },
                "gpu": {
                    "type": "string",
                    "description": "Optional GPU type: 'T4', 'A10G', 'A100', 'H100'",
                },
                "cpu": {"type": "number", "description": "CPU count (default 1.0)"},
                "memory": {"type": "integer", "description": "RAM in MB (default 512)"},
                "timeout": {
                    "type": "integer",
                    "description": "Max wall-clock seconds to wait (default 300)",
                },
                "secrets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Modal secret names to inject as environment variables",
                },
            },
            "required": ["code"],
        },
    },
    "modal_deploy": {
        "name": "modal_deploy",
        "description": (
            "Deploy a persistent Modal app. "
            "Optionally provide a cron schedule for recurring execution."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code for the app function",
                },
                "app_name": {
                    "type": "string",
                    "description": "Unique app name (used in Modal dashboard)",
                },
                "image": {"type": "string", "description": "Base image (default 'debian-slim')"},
                "gpu": {"type": "string", "description": "Optional GPU spec"},
                "schedule": {
                    "type": "string",
                    "description": "Cron expression for recurring runs (e.g. '0 9 * * *')",
                },
            },
            "required": ["code", "app_name"],
        },
    },
    "modal_list": {
        "name": "modal_list",
        "description": "List all Modal apps on your account.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "modal_stop": {
        "name": "modal_stop",
        "description": "Stop and remove a deployed Modal app.",
        "parameters": {
            "type": "object",
            "properties": {
                "app_name": {"type": "string", "description": "App name to stop"},
            },
            "required": ["app_name"],
        },
    },
}


def register_modal_tools(registry):
    """Register Modal tools with a ToolRegistry."""
    registry.register("modal_run", modal_run, _SCHEMAS["modal_run"])
    registry.register("modal_deploy", modal_deploy, _SCHEMAS["modal_deploy"])
    registry.register("modal_list", modal_list, _SCHEMAS["modal_list"])
    registry.register("modal_stop", modal_stop, _SCHEMAS["modal_stop"])
