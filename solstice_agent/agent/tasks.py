"""
Task Tracking
=============
Persistent task board for multi-step work. This gives the agent a first-class
way to track pending/in-progress/completed work instead of relying only on
conversation text.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.tasks")

_DEFAULT_ROOT = Path.home() / ".solstice-agent" / "tasks"


@dataclass
class TaskItem:
    id: str
    subject: str
    status: str = "pending"
    details: str = ""
    blocked_by: List[str] = field(default_factory=list)
    owner: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


class TaskBoard:
    """Small persistent task store with a single JSON file."""

    VALID_STATUSES = {"pending", "in_progress", "completed"}

    def __init__(self, root: Optional[str] = None):
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "board.json"
        self._tasks: Dict[str, TaskItem] = {}
        self._load()

    def upsert(
        self,
        subject: str,
        status: str = "pending",
        task_id: Optional[str] = None,
        details: str = "",
        blocked_by: Optional[List[str]] = None,
        owner: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TaskItem:
        normalized_status = (status or "pending").strip().lower()
        if normalized_status not in self.VALID_STATUSES:
            raise ValueError(
                f"Invalid task status '{status}'. Use pending, in_progress, or completed."
            )

        resolved_id = task_id or f"t-{uuid.uuid4().hex[:8]}"
        current = self._tasks.get(resolved_id)
        task = TaskItem(
            id=resolved_id,
            subject=subject or (current.subject if current else ""),
            status=normalized_status,
            details=details if details != "" else (current.details if current else ""),
            blocked_by=sorted(
                {
                    str(item).strip()
                    for item in (blocked_by if blocked_by is not None else (current.blocked_by if current else []))
                    if str(item).strip()
                }
            ),
            owner=owner if owner != "" else (current.owner if current else ""),
            metadata=metadata if metadata is not None else (current.metadata if current else {}),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )
        if not task.subject:
            raise ValueError("Task subject is required.")

        self._tasks[resolved_id] = task
        self._save()
        return task

    def list(self, status: Optional[str] = None) -> List[TaskItem]:
        items = sorted(self._tasks.values(), key=lambda item: (item.status, item.updated_at, item.id))
        if status:
            normalized = status.strip().lower()
            return [item for item in items if item.status == normalized]
        return items

    def get(self, task_id: str) -> Optional[TaskItem]:
        return self._tasks.get(task_id)

    def clear(self) -> int:
        count = len(self._tasks)
        self._tasks = {}
        self._save()
        return count

    def _load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            tasks = raw.get("tasks", [])
            for payload in tasks:
                try:
                    item = TaskItem(**payload)
                    self._tasks[item.id] = item
                except TypeError:
                    continue
        except Exception as exc:
            log.warning(f"Failed to load task board: {exc}")

    def _save(self):
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [asdict(item) for item in self.list()],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


_board: Optional[TaskBoard] = None


def _get_board() -> TaskBoard:
    global _board
    if _board is None:
        _board = TaskBoard()
    return _board


def init_task_board(root: Optional[str] = None):
    global _board
    _board = TaskBoard(root=root)


def task_upsert(
    subject: str,
    status: str = "pending",
    task_id: str = "",
    details: str = "",
    blocked_by: Optional[List[str]] = None,
    owner: str = "",
    metadata_json: str = "",
) -> str:
    """Create or update a task."""
    metadata: Optional[Dict[str, Any]] = None
    if metadata_json:
        try:
            loaded = json.loads(metadata_json)
            metadata = loaded if isinstance(loaded, dict) else {"value": loaded}
        except json.JSONDecodeError as exc:
            return f"Error: metadata_json must be valid JSON ({exc})"

    task = _get_board().upsert(
        subject=subject,
        status=status,
        task_id=task_id or None,
        details=details,
        blocked_by=blocked_by,
        owner=owner,
        metadata=metadata,
    )
    return f"Task {task.id} [{task.status}]: {task.subject}"


def task_list(status: str = "") -> str:
    """List tracked tasks."""
    items = _get_board().list(status=status or None)
    if not items:
        suffix = f" with status '{status}'" if status else ""
        return f"No tracked tasks{suffix}."

    lines = [f"Tracked tasks ({len(items)}):"]
    for item in items:
        block_suffix = f" blocked_by={', '.join(item.blocked_by)}" if item.blocked_by else ""
        owner_suffix = f" owner={item.owner}" if item.owner else ""
        details_suffix = f" :: {item.details}" if item.details else ""
        lines.append(
            f"  {item.id} [{item.status}] {item.subject}{owner_suffix}{block_suffix}{details_suffix}"
        )
    return "\n".join(lines)


def task_get(task_id: str) -> str:
    """Read one tracked task."""
    item = _get_board().get(task_id)
    if not item:
        return f"Task '{task_id}' not found."
    metadata_suffix = json.dumps(item.metadata, ensure_ascii=False) if item.metadata else "{}"
    return (
        f"{item.id} [{item.status}] {item.subject}\n"
        f"Details: {item.details or '(none)'}\n"
        f"Owner: {item.owner or '(none)'}\n"
        f"Blocked by: {', '.join(item.blocked_by) if item.blocked_by else '(none)'}\n"
        f"Metadata: {metadata_suffix}\n"
        f"Updated: {item.updated_at}"
    )


def task_clear() -> str:
    """Clear the task board."""
    count = _get_board().clear()
    return f"Cleared {count} task(s)."


_SCHEMAS = {
    "task_upsert": {
        "name": "task_upsert",
        "description": (
            "Create or update a tracked task. Use this for multi-step work so progress stays explicit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "subject": {"type": "string", "description": "Short task title"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "Task status",
                },
                "task_id": {"type": "string", "description": "Existing task ID to update"},
                "details": {"type": "string", "description": "Additional task detail"},
                "blocked_by": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Other task IDs blocking this task",
                },
                "owner": {"type": "string", "description": "Optional owner or worker name"},
                "metadata_json": {
                    "type": "string",
                    "description": "Optional JSON object with extra task metadata",
                },
            },
            "required": ["subject"],
        },
    },
    "task_list": {
        "name": "task_list",
        "description": "List tracked tasks. Optionally filter by status.",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["pending", "in_progress", "completed"],
                    "description": "Optional status filter",
                }
            },
        },
    },
    "task_get": {
        "name": "task_get",
        "description": "Get detailed information for a tracked task.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    },
    "task_clear": {
        "name": "task_clear",
        "description": "Clear all tracked tasks.",
        "parameters": {"type": "object", "properties": {}},
    },
}


def register_task_tools(registry):
    registry.register("task_upsert", task_upsert, _SCHEMAS["task_upsert"])
    registry.register("task_list", task_list, _SCHEMAS["task_list"])
    registry.register("task_get", task_get, _SCHEMAS["task_get"])
    registry.register("task_clear", task_clear, _SCHEMAS["task_clear"])
