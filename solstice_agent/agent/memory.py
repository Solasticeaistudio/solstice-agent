"""
Persistent Memory
=================
Save conversation history and key facts to disk. Survives restarts.

Storage layout:
    ~/.solstice-agent/
        memory/
            conversations/
                {session_id}.json    # Conversation histories
            notes.json               # Key facts the agent remembers
        config.yaml                  # (handled by config.py)
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.memory")

# Default storage root
_DEFAULT_ROOT = Path.home() / ".solstice-agent" / "memory"


class Memory:
    """
    Persistent memory for the agent. Stores:
    - Conversation history (per session)
    - Key facts / notes (cross-session)
    """

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.conversations_dir = self.root / "conversations"
        self.notes_path = self.root / "notes.json"

        # Ensure dirs exist
        self.conversations_dir.mkdir(parents=True, exist_ok=True)

        # Current session
        self.session_id = f"s-{uuid.uuid4().hex[:8]}"
        self._notes: Dict[str, Any] = self._load_notes()

        log.info(f"Memory initialized at {self.root} (session: {self.session_id})")

    # --- Notes (cross-session facts) ---

    def remember(self, key: str, value: str) -> str:
        """Store a key fact that persists across sessions."""
        self._notes[key] = {
            "value": value,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "session": self.session_id,
        }
        self._save_notes()
        return f"Remembered: {key} = {value}"

    def recall(self, key: Optional[str] = None) -> str:
        """Recall a specific fact or list all remembered facts."""
        if not self._notes:
            return "No saved memories."

        if key:
            entry = self._notes.get(key)
            if not entry:
                # Fuzzy search
                matches = [k for k in self._notes if key.lower() in k.lower()]
                if matches:
                    lines = [f"No exact match for '{key}'. Similar:"]
                    for m in matches:
                        lines.append(f"  {m}: {self._notes[m]['value']}")
                    return "\n".join(lines)
                return f"No memory found for '{key}'."
            return f"{key}: {entry['value']} (saved {entry['saved_at'][:10]})"

        # List all
        lines = [f"Saved memories ({len(self._notes)}):"]
        for k, entry in self._notes.items():
            lines.append(f"  {k}: {entry['value']}")
        return "\n".join(lines)

    def forget(self, key: str) -> str:
        """Remove a remembered fact."""
        if key in self._notes:
            del self._notes[key]
            self._save_notes()
            return f"Forgot: {key}"
        return f"No memory found for '{key}'."

    # --- Conversation history (per session) ---

    def save_conversation(self, history: List[Dict[str, Any]]) -> str:
        """Save conversation history for the current session."""
        if not history:
            return "Nothing to save."

        data = {
            "session_id": self.session_id,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "message_count": len(history),
            "messages": history,
        }
        path = self.conversations_dir / f"{self.session_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return f"Conversation saved ({len(history)} messages) to {path.name}"

    def load_conversation(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load conversation history. Defaults to most recent session."""
        if session_id:
            # Sanitize session_id to prevent path traversal
            safe_id = os.path.basename(session_id).replace("..", "")
            if not safe_id or safe_id != session_id:
                log.warning(f"Rejected suspicious session_id: {session_id!r}")
                return []
            path = self.conversations_dir / f"{safe_id}.json"
            # Verify resolved path is within conversations_dir
            resolved = path.resolve()
            if not str(resolved).startswith(str(self.conversations_dir.resolve())):
                log.warning(f"Path traversal blocked: {session_id!r}")
                return []
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("messages", [])
            return []

        # Find most recent
        files = sorted(self.conversations_dir.glob("s-*.json"), key=os.path.getmtime, reverse=True)
        if not files:
            return []

        data = json.loads(files[0].read_text(encoding="utf-8"))
        log.info(f"Loaded previous conversation: {files[0].name}")
        return data.get("messages", [])

    def list_conversations(self) -> str:
        """List all saved conversations."""
        files = sorted(self.conversations_dir.glob("s-*.json"), key=os.path.getmtime, reverse=True)
        if not files:
            return "No saved conversations."

        lines = [f"Saved conversations ({len(files)}):"]
        for f in files[:20]:
            data = json.loads(f.read_text(encoding="utf-8"))
            count = data.get("message_count", "?")
            saved = data.get("saved_at", "?")[:16]
            lines.append(f"  {f.stem}: {count} messages (saved {saved})")

        if len(files) > 20:
            lines.append(f"  ... and {len(files) - 20} more")
        return "\n".join(lines)

    # --- Internal ---

    def _load_notes(self) -> Dict[str, Any]:
        if self.notes_path.exists():
            try:
                return json.loads(self.notes_path.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Failed to load notes, starting fresh")
        return {}

    def _save_notes(self):
        self.notes_path.write_text(
            json.dumps(self._notes, indent=2, default=str),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Tool functions (stateless wrappers around a module-level Memory instance)
# ---------------------------------------------------------------------------

_memory: Optional[Memory] = None


def _get_memory() -> Memory:
    global _memory
    if _memory is None:
        _memory = Memory()
    return _memory


def memory_remember(key: str, value: str) -> str:
    """Save a fact that persists across sessions. Key is the topic, value is the detail."""
    return _get_memory().remember(key, value)


def memory_recall(key: Optional[str] = None) -> str:
    """Recall a saved fact by key, or list all saved memories if no key given."""
    return _get_memory().recall(key)


def memory_forget(key: str) -> str:
    """Remove a saved memory by key."""
    return _get_memory().forget(key)


def memory_save_conversation(history_json: str) -> str:
    """Save the current conversation to disk. Pass history as JSON string."""
    try:
        history = json.loads(history_json)
    except json.JSONDecodeError:
        return "Invalid JSON. Pass the conversation history as a JSON array."
    return _get_memory().save_conversation(history)


def memory_list_conversations() -> str:
    """List all saved conversation sessions."""
    return _get_memory().list_conversations()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "memory_remember": {
        "name": "memory_remember",
        "description": (
            "Save a fact that persists across sessions. Use this when the user says "
            "'remember that...' or when important context should be retained."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Topic/label for the memory (e.g. 'preferred_language', 'project_name')"},
                "value": {"type": "string", "description": "The detail to remember"},
            },
            "required": ["key", "value"],
        },
    },
    "memory_recall": {
        "name": "memory_recall",
        "description": (
            "Recall a previously saved memory by key, or list all saved memories. "
            "Supports fuzzy matching on key names."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key to look up (optional — omit to list all)"},
            },
            "required": [],
        },
    },
    "memory_forget": {
        "name": "memory_forget",
        "description": "Remove a saved memory by key.",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Key of the memory to remove"},
            },
            "required": ["key"],
        },
    },
    "memory_list_conversations": {
        "name": "memory_list_conversations",
        "description": "List all previously saved conversation sessions with message counts and dates.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_memory_tools(registry):
    """Register persistent memory tools with a ToolRegistry."""
    registry.register("memory_remember", memory_remember, _SCHEMAS["memory_remember"])
    registry.register("memory_recall", memory_recall, _SCHEMAS["memory_recall"])
    registry.register("memory_forget", memory_forget, _SCHEMAS["memory_forget"])
    registry.register("memory_list_conversations", memory_list_conversations, _SCHEMAS["memory_list_conversations"])
