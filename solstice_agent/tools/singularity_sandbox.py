"""
Singularity / Apptainer Sandbox
================================
HPC container execution via Singularity or Apptainer (its successor).

Ideal for HPC clusters where Docker requires root or is unavailable.
Supports blocking runs and background async jobs with output streaming.

No Python dependencies — wraps the 'singularity' or 'apptainer' CLI.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import threading
from typing import Dict, Optional
from uuid import uuid4

log = logging.getLogger("solstice.tools.singularity")

_MAX_JOBS = 20

_jobs: Dict[str, Dict] = {}
_jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bin() -> str:
    """Return the available Singularity/Apptainer binary name."""
    for name in ("apptainer", "singularity"):
        if shutil.which(name):
            return name
    raise RuntimeError(
        "Neither 'apptainer' nor 'singularity' found in PATH.\n"
        "Install from https://apptainer.org or https://sylabs.io/singularity"
    )


def _build_cmd(image: str, command: str, bind: Optional[str], env: Optional[Dict[str, str]]) -> list:
    cmd = [_bin(), "exec"]
    if bind:
        cmd += ["--bind", bind]
    if env:
        for k, v in env.items():
            cmd += ["--env", f"{k}={v}"]
    cmd += [image, "sh", "-c", command]
    return cmd


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def singularity_run(
    image: str,
    command: str,
    bind: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: int = 300,
) -> str:
    """
    Run a command inside a Singularity/Apptainer container (blocking).

    image: SIF file path or a pull URI such as docker://ubuntu:22.04,
           library://sylabs/hello-world/hello-world:latest, or oras://...
    bind:  Optional host:container path bind (e.g. '/scratch:/mnt/scratch').
    """
    cmd = _build_cmd(image, command, bind, env)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = result.stdout
        err = result.stderr.strip()
        if result.returncode != 0:
            return f"[exit {result.returncode}]\nstdout: {out}\nstderr: {err}"
        return out or "[exit 0, no output]"
    except subprocess.TimeoutExpired:
        return f"[timed out after {timeout}s]"
    except FileNotFoundError as exc:
        return f"Error: {exc}"


def singularity_run_async(
    image: str,
    command: str,
    bind: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
) -> str:
    """
    Start a Singularity job in the background. Returns a job ID.
    Use singularity_status to check progress and retrieve output.
    """
    with _jobs_lock:
        if len(_jobs) >= _MAX_JOBS:
            return f"Max concurrent jobs ({_MAX_JOBS}) reached. Check singularity_list."

    cmd = _build_cmd(image, command, bind, env)
    job_id = f"sng-{uuid4().hex[:8]}"
    log_path = os.path.join(tempfile.gettempdir(), f"{job_id}.log")

    def _run():
        with open(log_path, "w") as fh:
            proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, text=True)
            with _jobs_lock:
                _jobs[job_id]["pid"] = proc.pid
            rc = proc.wait()
            with _jobs_lock:
                if job_id in _jobs:
                    _jobs[job_id]["status"] = "done"
                    _jobs[job_id]["exit_code"] = rc

    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "image": image,
            "command": command,
            "status": "running",
            "pid": None,
            "exit_code": None,
            "log_path": log_path,
        }

    threading.Thread(target=_run, daemon=True).start()
    log.info(f"Singularity async job started: {job_id}")
    return f"Job started. ID: {job_id}\nUse singularity_status('{job_id}') to check progress."


def singularity_status(job_id: str) -> str:
    """Check status and tail output of an async Singularity job."""
    with _jobs_lock:
        job = dict(_jobs.get(job_id, {}))
    if not job:
        return f"Job '{job_id}' not found."

    output = ""
    log_path = job.get("log_path", "")
    if log_path and os.path.exists(log_path):
        with open(log_path) as fh:
            raw = fh.read()
        output = raw[-3000:] if len(raw) > 3000 else raw

    lines = [
        f"Job:     {job_id}",
        f"Status:  {job['status']}",
        f"Image:   {job['image']}",
        f"Command: {job['command']}",
    ]
    if job.get("exit_code") is not None:
        lines.append(f"Exit:    {job['exit_code']}")
    if output:
        lines.append(f"\n--- Output (last 3 KB) ---\n{output}")
    return "\n".join(lines)


def singularity_list() -> str:
    """List all Singularity jobs (running and completed)."""
    with _jobs_lock:
        jobs = list(_jobs.values())
    if not jobs:
        return "No Singularity jobs in this session."
    lines = [f"Singularity jobs ({len(jobs)}):"]
    for j in jobs:
        ec = f" exit={j['exit_code']}" if j.get("exit_code") is not None else ""
        lines.append(f"  {j['job_id']}  [{j['status']}{ec}]  {j['image']} — {j['command'][:60]}")
    return "\n".join(lines)


def singularity_pull(uri: str, dest: Optional[str] = None) -> str:
    """
    Pull a container image from a registry into a local SIF file.
    uri: e.g. 'docker://ubuntu:22.04' or 'library://sylabs/hello-world/hello-world:latest'
    dest: optional local SIF path; if omitted, Singularity picks the name.
    """
    cmd = [_bin(), "pull"]
    if dest:
        cmd.append(dest)
    cmd.append(uri)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return f"Pull failed (exit {result.returncode}):\n{result.stderr}"
        return result.stdout or f"Pulled {uri}" + (f" → {dest}" if dest else "")
    except subprocess.TimeoutExpired:
        return "[pull timed out after 300s — image may still be downloading in background]"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "singularity_run": {
        "name": "singularity_run",
        "description": (
            "Run a command inside a Singularity/Apptainer container (blocking). "
            "Use for HPC workloads where Docker is unavailable or requires root. "
            "image can be a local SIF file or a pull URI like docker://ubuntu:22.04."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image": {
                    "type": "string",
                    "description": "SIF file path or image URI (docker://, library://, oras://)",
                },
                "command": {
                    "type": "string",
                    "description": "Shell command to run inside the container",
                },
                "bind": {
                    "type": "string",
                    "description": "Host:container bind mount (e.g. '/scratch:/mnt/scratch')",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout in seconds (default 300)",
                },
            },
            "required": ["image", "command"],
        },
    },
    "singularity_run_async": {
        "name": "singularity_run_async",
        "description": (
            "Start a Singularity container job in the background. "
            "Returns a job ID. Use singularity_status to poll progress."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image": {"type": "string", "description": "SIF file or image URI"},
                "command": {"type": "string", "description": "Shell command to run"},
                "bind": {"type": "string", "description": "Optional bind mount"},
            },
            "required": ["image", "command"],
        },
    },
    "singularity_status": {
        "name": "singularity_status",
        "description": "Check the status and tail output of an async Singularity job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "Job ID from singularity_run_async",
                },
            },
            "required": ["job_id"],
        },
    },
    "singularity_list": {
        "name": "singularity_list",
        "description": "List all Singularity jobs started in this session.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "singularity_pull": {
        "name": "singularity_pull",
        "description": "Pull a container image from a registry into a local SIF file.",
        "parameters": {
            "type": "object",
            "properties": {
                "uri": {
                    "type": "string",
                    "description": "Image URI (e.g. 'docker://ubuntu:22.04')",
                },
                "dest": {
                    "type": "string",
                    "description": "Optional local destination path for the SIF file",
                },
            },
            "required": ["uri"],
        },
    },
}


def register_singularity_tools(registry):
    """Register Singularity tools with a ToolRegistry."""
    registry.register("singularity_run", singularity_run, _SCHEMAS["singularity_run"])
    registry.register("singularity_run_async", singularity_run_async, _SCHEMAS["singularity_run_async"])
    registry.register("singularity_status", singularity_status, _SCHEMAS["singularity_status"])
    registry.register("singularity_list", singularity_list, _SCHEMAS["singularity_list"])
    registry.register("singularity_pull", singularity_pull, _SCHEMAS["singularity_pull"])
