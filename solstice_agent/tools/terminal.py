"""
Terminal Tools
==============
Run shell commands (foreground or background). The agent can execute code,
run builds, manage git, start dev servers, and monitor long-running processes.

Security: Destructive commands require explicit confirmation via a callback.
The CLI wires this to an interactive prompt. The gateway can wire it to a
channel-specific confirmation flow. If no callback is set, destructive
commands are blocked by default.
"""

import os
import re
import subprocess
import logging
import threading
import time
from collections import deque
from typing import Callable, Optional, Dict

log = logging.getLogger("solstice.tools.terminal")


# ── Command Safety ──────────────────────────────────────────────────────────

# Patterns that indicate potentially destructive operations
_DANGEROUS_PATTERNS = [
    # File deletion
    r'\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r|--force|--recursive)',  # rm -rf, rm -f
    r'\brm\s+-[a-zA-Z]*\s+/',                                   # rm anything at root
    r'\brmdir\b',
    # Disk/partition
    r'\bmkfs\b',
    r'\bformat\b',
    r'\bdd\s+',
    r'\b>\s*/dev/sd',
    # Git destructive
    r'\bgit\s+push\s+.*--force',
    r'\bgit\s+reset\s+--hard',
    r'\bgit\s+clean\s+-[a-zA-Z]*f',
    r'\bgit\s+branch\s+-[a-zA-Z]*D',
    # Database destructive
    r'\bdrop\s+(table|database)\b',
    r'\btruncate\s+table\b',
    # System control
    r'\bshutdown\b',
    r'\breboot\b',
    r'\bkill\s+-9\b',
    r'\bkillall\b',
    r'\btaskkill\s.*//IM\b',
    # Permissions
    r'\bchmod\s+777\b',
    r'\bchown\s+-R\b.*/',
    # Remote code execution pipelines
    r'\bcurl\b.*\|\s*(ba)?sh',
    r'\bwget\b.*\|\s*(ba)?sh',
    r'\bcurl\b.*\|\s*python',
    r'\bwget\b.*\|\s*python',
    r'\bcurl\b.*\|\s*perl',
    # Port killing
    r'\bnpx\s+kill-port\b',
    # System file modification
    r'\b>\s*/etc/',
    r'\bsudo\s+rm\b',
    # Interpreter-based evasion — block shell/script interpreters with inline code
    r'\bpython[23]?\s+-c\b',
    r'\bnode\s+-e\b',
    r'\bperl\s+-e\b',
    r'\bruby\s+-e\b',
    r'\bpowershell(?:\.exe)?\s+(?:-c|-command|-encodedcommand|-enc)\b',
    r'\bpwsh(?:\.exe)?\s+(?:-c|-command|-encodedcommand|-enc)\b',
    r'\bcmd(?:\.exe)?\s+(?:/c|/k)\b',
    r'\bbash\s+-c\b',
    r'\bsh\s+-c\b',
    r'\bzsh\s+-c\b',
    # Base64 decode + execute (with or without pipe)
    r'\bbase64\s+(-d|--decode)\b',
    # Network exfiltration
    r'\bnc\s+-[a-zA-Z]*\b',  # netcat
    r'\bncat\b',
    # SSH/credential access
    r'\.ssh/authorized_keys',
    r'\.ssh/id_',
    # Environment variable dumping
    r'\bprintenv\b',
    r'\benv\b\s*$',
    r'\bset\b\s*$',
    # Crontab modification
    r'\bcrontab\s+-[re]\b',
]

_DANGEROUS_RE = re.compile('|'.join(_DANGEROUS_PATTERNS), re.IGNORECASE)


def _normalize_command(command: str) -> str:
    """Normalize a command string to defeat obfuscation before safety checks.

    Handles:
    - ${IFS} and $IFS word-splitting tricks (rm${IFS}-rf)
    - $'...' ANSI-C quoting
    - Backslash insertion (r\\m -rf)
    - Variable concatenation (a=rm; $a -rf /)
    - Quote stripping (r"m" → rm)
    """
    normalized = command
    # Strip ${IFS}, $IFS (shell word-splitting trick)
    normalized = re.sub(r'\$\{?IFS\}?', ' ', normalized)
    # Strip inserted backslashes (r\m → rm)
    normalized = re.sub(r'\\(?=[a-zA-Z])', '', normalized)
    # Strip single/double quotes used to break up tokens (r"m" → rm, r''m → rm)
    normalized = re.sub(r"""(?<=[a-zA-Z])(['"])(?=[a-zA-Z])""", '', normalized)
    normalized = re.sub(r"""(['"])(?=[a-zA-Z])""", '', normalized)
    return normalized

# Maximum number of concurrent background processes
_MAX_BACKGROUND_PROCESSES = 10

# Global confirmation callback. Set by CLI/gateway.
# Signature: (command: str, reason: str) -> bool
_confirm_callback: Optional[Callable[[str, str], bool]] = None


def set_confirm_callback(callback: Optional[Callable[[str, str], bool]]):
    """
    Set a callback for confirming dangerous commands.

    Args:
        callback: Function(command, reason) -> bool. Return True to allow.
                  If None, dangerous commands are blocked.
    """
    global _confirm_callback
    _confirm_callback = callback


def check_command_safety(command: str) -> Optional[str]:
    """
    Check if a command matches dangerous patterns.
    Returns a warning string if dangerous, None if safe.

    Checks both the raw command and a normalized version (to defeat
    obfuscation like ${IFS}, backslash insertion, quote splitting).
    Also splits on shell metacharacters (;, |, &&, ||) to check each
    segment independently — prevents hiding dangerous commands behind
    benign prefixes in a chain.
    """
    # Check the raw command first
    match = _DANGEROUS_RE.search(command)
    if match:
        return f"Potentially destructive pattern detected: {match.group()}"

    # Normalize and check again (defeats IFS, backslash, quote tricks)
    normalized = _normalize_command(command)
    if normalized != command:
        match = _DANGEROUS_RE.search(normalized)
        if match:
            return f"Potentially destructive pattern detected (obfuscated): {match.group()}"

    # Split on shell metacharacters and check each segment
    # This catches: "echo hi; rm -rf /", "cat file | bash", "safe && dangerous"
    segments = re.split(r'\s*(?:;|&&|\|\||\|)\s*', command)
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        match = _DANGEROUS_RE.search(segment)
        if match:
            return f"Potentially destructive pattern in chained command: {match.group()}"
        norm_seg = _normalize_command(segment)
        if norm_seg != segment:
            match = _DANGEROUS_RE.search(norm_seg)
            if match:
                return f"Potentially destructive pattern in chained command (obfuscated): {match.group()}"

    # Check for $() and backtick command substitution containing dangerous patterns
    subcommands = re.findall(r'\$\((.+?)\)', command) + re.findall(r'`(.+?)`', command)
    for sub in subcommands:
        match = _DANGEROUS_RE.search(sub)
        if match:
            return f"Potentially destructive pattern in subcommand: {match.group()}"

    return None


def _confirm_or_block(command: str, reason: str) -> Optional[str]:
    """
    Ask for confirmation or block the command.
    Returns an error string if blocked, None if allowed.
    """
    if _confirm_callback:
        allowed = _confirm_callback(command, reason)
        if not allowed:
            return f"Command blocked by user: {command}"
        return None
    else:
        # No callback set — block by default
        return f"Blocked: {reason}. Command: {command}"


# ── Background Process Manager ─────────────────────────────────────────────

class _BackgroundSession:
    """A background shell process with captured output."""

    def __init__(self, sid: str, command: str, process: subprocess.Popen, cwd: str):
        self.sid = sid
        self.command = command
        self.process = process
        self.cwd = cwd
        self.started = time.time()
        self._output = deque(maxlen=5000)  # Rolling buffer of lines
        self._lock = threading.Lock()

        # Reader threads for stdout and stderr
        self._threads = []
        for stream, label in [(process.stdout, ""), (process.stderr, "[stderr] ")]:
            if stream:
                t = threading.Thread(target=self._reader, args=(stream, label), daemon=True)
                t.start()
                self._threads.append(t)

    def _reader(self, stream, prefix: str):
        """Read lines from a stream into the output buffer."""
        try:
            for line in stream:
                with self._lock:
                    self._output.append(prefix + line)
        except (ValueError, OSError):
            pass  # Stream closed

    @property
    def alive(self) -> bool:
        return self.process.poll() is None

    @property
    def exit_code(self) -> Optional[int]:
        return self.process.poll()

    @property
    def elapsed(self) -> float:
        return time.time() - self.started

    def get_output(self, last_n: int = 100) -> str:
        """Get the last N lines of output."""
        with self._lock:
            lines = list(self._output)[-last_n:]
        return "".join(lines)

    def write_stdin(self, text: str) -> bool:
        """Write text to the process's stdin."""
        if not self.alive or not self.process.stdin:
            return False
        try:
            self.process.stdin.write(text)
            self.process.stdin.flush()
            return True
        except (BrokenPipeError, OSError):
            return False

    def kill(self):
        """Kill the process."""
        try:
            self.process.kill()
        except OSError:
            pass


class _ProcessManager:
    """Manages all background sessions."""

    def __init__(self):
        self._sessions: Dict[str, _BackgroundSession] = {}
        self._counter = 0
        self._lock = threading.Lock()

    def start(self, command: str, cwd: str = None) -> _BackgroundSession:
        """Start a new background process."""
        work_dir = cwd or os.getcwd()

        with self._lock:
            self._counter += 1
            sid = f"bg_{self._counter}"

        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            cwd=work_dir,
            env=os.environ.copy(),
            bufsize=1,  # Line-buffered
        )

        session = _BackgroundSession(sid, command, process, work_dir)
        with self._lock:
            self._sessions[sid] = session

        log.info(f"Background process started: {sid} (PID {process.pid})")
        return session

    def get(self, sid: str) -> Optional[_BackgroundSession]:
        with self._lock:
            return self._sessions.get(sid)

    def list_all(self) -> list:
        with self._lock:
            return list(self._sessions.values())

    def remove(self, sid: str):
        with self._lock:
            session = self._sessions.pop(sid, None)
        if session and session.alive:
            session.kill()


# Global process manager
_manager = _ProcessManager()


# ── Foreground Command ──────────────────────────────────────────────────────

def run_command(command: str, timeout: int = 60, cwd: str = None) -> str:
    """
    Run a shell command and return stdout + stderr.
    Times out after 60 seconds by default.
    Destructive commands require confirmation.
    """
    try:
        # Safety check
        warning = check_command_safety(command)
        if warning:
            blocked = _confirm_or_block(command, warning)
            if blocked:
                return blocked

        work_dir = cwd or os.getcwd()
        shell = True
        env = os.environ.copy()

        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
            env=env,
        )

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")
        if result.returncode != 0:
            output_parts.append(f"[exit code: {result.returncode}]")

        output = "\n".join(output_parts).strip()

        # Truncate long output
        if len(output) > 10000:
            output = output[:5000] + "\n\n... (truncated) ...\n\n" + output[-3000:]

        return output if output else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout}s: {command}"
    except Exception as e:
        return f"Error running command: {e}"


# ── Background Commands ─────────────────────────────────────────────────────

def run_background(command: str, cwd: str = None) -> str:
    """Start a command in the background. Returns a session ID for monitoring."""
    try:
        # Enforce process limit
        active = [s for s in _manager.list_all() if s.alive]
        if len(active) >= _MAX_BACKGROUND_PROCESSES:
            return (
                f"Error: Maximum of {_MAX_BACKGROUND_PROCESSES} concurrent background "
                f"processes reached. Kill existing sessions with bg_kill first."
            )

        # Safety check
        warning = check_command_safety(command)
        if warning:
            blocked = _confirm_or_block(command, warning)
            if blocked:
                return blocked

        session = _manager.start(command, cwd)
        # Give it a moment to potentially fail fast
        time.sleep(0.3)
        if not session.alive:
            output = session.get_output()
            return (f"Process exited immediately (code {session.exit_code}).\n"
                    f"Session: {session.sid}\n"
                    f"Output:\n{output}" if output else
                    f"Process exited immediately (code {session.exit_code}). Session: {session.sid}")
        return (f"Started background process.\n"
                f"  Session: {session.sid}\n"
                f"  PID: {session.process.pid}\n"
                f"  Command: {command}\n"
                f"Use bg_log(\"{session.sid}\") to check output.")
    except Exception as e:
        return f"Error starting background process: {e}"


def bg_status() -> str:
    """List all background sessions and their status."""
    sessions = _manager.list_all()
    if not sessions:
        return "No background sessions."

    lines = []
    for s in sessions:
        status = "running" if s.alive else f"exited ({s.exit_code})"
        elapsed = s.elapsed
        if elapsed < 60:
            time_str = f"{elapsed:.0f}s"
        elif elapsed < 3600:
            time_str = f"{elapsed/60:.0f}m"
        else:
            time_str = f"{elapsed/3600:.1f}h"
        lines.append(f"  {s.sid}  {status:<16}  {time_str:<8}  PID {s.process.pid}  {s.command[:60]}")

    header = f"{'ID':<8}  {'Status':<16}  {'Time':<8}  {'PID':<10}  Command"
    return f"{len(sessions)} session(s):\n  {header}\n" + "\n".join(lines)


def bg_log(session_id: str, lines: int = 50) -> str:
    """Read the last N lines of output from a background session."""
    session = _manager.get(session_id)
    if not session:
        available = [s.sid for s in _manager.list_all()]
        return f"Session '{session_id}' not found. Available: {', '.join(available) or 'none'}"

    output = session.get_output(last_n=lines)
    status = "running" if session.alive else f"exited ({session.exit_code})"
    header = f"[{session.sid}] {status} | {session.command[:60]}"

    if not output:
        return f"{header}\n(no output yet)"
    return f"{header}\n{output}"


def bg_write(session_id: str, text: str) -> str:
    """Send text to a background session's stdin. Adds a newline automatically."""
    session = _manager.get(session_id)
    if not session:
        return f"Session '{session_id}' not found."
    if not session.alive:
        return f"Session '{session_id}' is not running (exit code {session.exit_code})."

    if not text.endswith("\n"):
        text += "\n"

    if session.write_stdin(text):
        return f"Sent to {session_id}: {text.strip()}"
    else:
        return f"Failed to write to {session_id} (stdin closed or broken pipe)."


def bg_kill(session_id: str) -> str:
    """Kill a background session."""
    session = _manager.get(session_id)
    if not session:
        return f"Session '{session_id}' not found."

    pid = session.process.pid
    was_alive = session.alive
    _manager.remove(session_id)

    if was_alive:
        return f"Killed session {session_id} (PID {pid})."
    else:
        return f"Removed session {session_id} (was already exited, code {session.exit_code})."


# --- Schemas ---

_SCHEMAS = {
    "run_command": {
        "name": "run_command",
        "description": "Run a shell command and return output. Blocks until complete. Use for quick commands (git, npm, pip, builds, tests). For long-running processes (dev servers, watchers), use run_background instead.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 60)"},
                "cwd": {"type": "string", "description": "Working directory (default: current dir)"},
            },
            "required": ["command"],
        },
    },
    "run_background": {
        "name": "run_background",
        "description": "Start a command in the background. Returns a session ID. Use for dev servers, file watchers, long builds, or any process you want to keep running. Check output with bg_log, send input with bg_write, stop with bg_kill.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run in the background"},
                "cwd": {"type": "string", "description": "Working directory (default: current dir)"},
            },
            "required": ["command"],
        },
    },
    "bg_status": {
        "name": "bg_status",
        "description": "List all background sessions with their status, PID, elapsed time, and command.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    "bg_log": {
        "name": "bg_log",
        "description": "Read the latest output from a background session. Use to check if a dev server started, monitor build progress, or read logs.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID (e.g. 'bg_1')"},
                "lines": {"type": "integer", "description": "Number of lines to return (default 50)"},
            },
            "required": ["session_id"],
        },
    },
    "bg_write": {
        "name": "bg_write",
        "description": "Send text to a background session's stdin. For interactive processes that need input. A newline is added automatically.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID (e.g. 'bg_1')"},
                "text": {"type": "string", "description": "Text to send (newline added automatically)"},
            },
            "required": ["session_id", "text"],
        },
    },
    "bg_kill": {
        "name": "bg_kill",
        "description": "Kill a background session and clean it up.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session ID (e.g. 'bg_1')"},
            },
            "required": ["session_id"],
        },
    },
}


def register_terminal_tools(registry):
    """Register terminal tools with a ToolRegistry."""
    registry.register("run_command", run_command, _SCHEMAS["run_command"])
    registry.register("run_background", run_background, _SCHEMAS["run_background"])
    registry.register("bg_status", bg_status, _SCHEMAS["bg_status"])
    registry.register("bg_log", bg_log, _SCHEMAS["bg_log"])
    registry.register("bg_write", bg_write, _SCHEMAS["bg_write"])
    registry.register("bg_kill", bg_kill, _SCHEMAS["bg_kill"])
