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

    def remember(
        self,
        key: str,
        value: str,
        category: str = "general",
        tags: Optional[List[str]] = None,
    ) -> str:
        """Store a key fact that persists across sessions."""
        normalized_tags = sorted({str(tag).strip() for tag in (tags or []) if str(tag).strip()})
        self._notes[key] = {
            "value": value,
            "category": category or "general",
            "tags": normalized_tags,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "session": self.session_id,
        }
        self._save_notes()
        category_suffix = f" [{category}]" if category else ""
        return f"Remembered{category_suffix}: {key} = {value}"

    def recall(self, key: Optional[str] = None, category: Optional[str] = None) -> str:
        """Recall a specific fact or list all remembered facts."""
        if not self._notes:
            return "No saved memories."

        if category:
            filtered = {
                k: entry for k, entry in self._notes.items()
                if (entry.get("category") or "general").lower() == category.lower()
            }
        else:
            filtered = self._notes

        if not filtered:
            return f"No saved memories in category '{category}'."

        if key:
            entry = filtered.get(key)
            if not entry:
                # Fuzzy search
                matches = [
                    k for k, value in filtered.items()
                    if key.lower() in k.lower() or key.lower() in str(value.get("value", "")).lower()
                ]
                if matches:
                    lines = [f"No exact match for '{key}'. Similar:"]
                    for m in matches:
                        entry = filtered[m]
                        category_label = entry.get("category", "general")
                        lines.append(f"  {m} [{category_label}]: {entry['value']}")
                    return "\n".join(lines)
                return f"No memory found for '{key}'."
            category_label = entry.get("category", "general")
            tag_text = f", tags={', '.join(entry.get('tags', []))}" if entry.get("tags") else ""
            return f"{key} [{category_label}]: {entry['value']} (saved {entry['saved_at'][:10]}{tag_text})"

        # List all
        heading = f"Saved memories in '{category}'" if category else "Saved memories"
        lines = [f"{heading} ({len(filtered)}):"]
        for k, entry in filtered.items():
            category_label = entry.get("category", "general")
            tag_text = f" [{', '.join(entry.get('tags', []))}]" if entry.get("tags") else ""
            lines.append(f"  {k} ({category_label}){tag_text}: {entry['value']}")
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
            "preview": self._conversation_preview(history),
            "messages": history,
        }
        path = self.conversations_dir / f"{self.session_id}.json"
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return f"Conversation saved ({len(history)} messages) to {path.name}"

    def load_conversation(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load conversation history. Defaults to most recent session."""
        data = self._load_conversation_data(session_id)
        return data.get("messages", [])

    def resume_conversation(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load an existing conversation and continue saving into the same session."""
        data = self._load_conversation_data(session_id)
        resumed_id = data.get("session_id")
        if resumed_id:
            self.session_id = resumed_id
            log.info(f"Resumed conversation session: {self.session_id}")
        return data.get("messages", [])

    def search(self, query: str, scope: str = "all", limit: int = 10) -> str:
        """Search notes and/or conversations for a query string."""
        q = (query or "").strip().lower()
        if not q:
            return "Provide a query to search memory."

        lines: List[str] = []

        if scope in ("all", "notes"):
            note_hits = []
            for key, entry in self._notes.items():
                haystack = " ".join(
                    [
                        key,
                        str(entry.get("value", "")),
                        str(entry.get("category", "")),
                        " ".join(entry.get("tags", [])),
                    ]
                ).lower()
                if q in haystack:
                    note_hits.append((key, entry))

            if note_hits:
                lines.append(f"Notes matches ({len(note_hits)}):")
                for key, entry in note_hits[:limit]:
                    category_label = entry.get("category", "general")
                    lines.append(f"  {key} [{category_label}]: {entry.get('value', '')}")

        if scope in ("all", "conversations"):
            convo_hits = []
            for path in sorted(self.conversations_dir.glob("s-*.json"), key=os.path.getmtime, reverse=True):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                preview = data.get("preview", "")
                for msg in data.get("messages", []):
                    content = msg.get("content", "")
                    text = content if isinstance(content, str) else json.dumps(content, default=str)
                    if q in text.lower():
                        convo_hits.append((path.stem, preview or text[:120]))
                        break

            if convo_hits:
                if lines:
                    lines.append("")
                lines.append(f"Conversation matches ({len(convo_hits)}):")
                for session_id, preview in convo_hits[:limit]:
                    lines.append(f"  {session_id}: {preview}")

        if not lines:
            return f"No memory matches for '{query}'."
        return "\n".join(lines)

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
            preview = data.get("preview", "")
            suffix = f" | {preview}" if preview else ""
            lines.append(f"  {f.stem}: {count} messages (saved {saved}){suffix}")

        if len(files) > 20:
            lines.append(f"  ... and {len(files) - 20} more")
        return "\n".join(lines)

    # --- Internal ---

    def _load_conversation_data(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Load saved conversation metadata and messages."""
        if session_id:
            # Sanitize session_id to prevent path traversal
            safe_id = os.path.basename(session_id).replace("..", "")
            if not safe_id or safe_id != session_id:
                log.warning(f"Rejected suspicious session_id: {session_id!r}")
                return {}
            path = self.conversations_dir / f"{safe_id}.json"
            # Verify resolved path is within conversations_dir
            resolved = path.resolve()
            if not str(resolved).startswith(str(self.conversations_dir.resolve())):
                log.warning(f"Path traversal blocked: {session_id!r}")
                return {}
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))
            return {}

        # Find most recent
        files = sorted(self.conversations_dir.glob("s-*.json"), key=os.path.getmtime, reverse=True)
        if not files:
            return {}

        data = json.loads(files[0].read_text(encoding="utf-8"))
        log.info(f"Loaded previous conversation: {files[0].name}")
        return data

    def _conversation_preview(self, history: List[Dict[str, Any]]) -> str:
        """Extract a short preview from the first user message."""
        for msg in history:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                compact = " ".join(content.strip().split())
                return compact[:80] + ("..." if len(compact) > 80 else "")
        return ""

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


def memory_remember(
    key: str,
    value: str,
    category: str = "general",
    tags: Optional[List[str]] = None,
) -> str:
    """Save a fact that persists across sessions. Key is the topic, value is the detail."""
    return _get_memory().remember(key, value, category=category, tags=tags)


def memory_recall(key: Optional[str] = None, category: Optional[str] = None) -> str:
    """Recall a saved fact by key, or list all saved memories if no key given."""
    return _get_memory().recall(key, category=category)


def memory_search(query: str, scope: str = "all", limit: int = 10) -> str:
    """Search saved notes and/or conversation history."""
    return _get_memory().search(query, scope=scope, limit=limit)


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
                "category": {"type": "string", "description": "Memory category (default 'general')"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags for later search/filtering",
                },
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
    "memory_search": {
        "name": "memory_search",
        "description": "Search saved notes and conversation history for a query string.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text"},
                "scope": {
                    "type": "string",
                    "enum": ["all", "notes", "conversations"],
                    "description": "Where to search (default all)",
                },
                "limit": {"type": "integer", "description": "Max matches to show (default 10)"},
            },
            "required": ["query"],
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
    registry.register("memory_search", memory_search, _SCHEMAS["memory_search"])
    registry.register("memory_list_conversations", memory_list_conversations, _SCHEMAS["memory_list_conversations"])
