"""
Sub-agent Support
=================
Async-capable child agent execution with lifecycle tracking.
"""

from __future__ import annotations

import json
import logging
import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .core import AgentExecutionCancelled

log = logging.getLogger("solstice.subagents")
_DEFAULT_ROOT = Path.home() / ".solstice-agent" / "subagents"


@dataclass
class SubagentRun:
    run_id: str
    prompt: str
    tools: List[str] = field(default_factory=list)
    status: str = "pending"
    result: str = ""
    error: str = ""
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str = ""
    details: str = ""
    progress: List[str] = field(default_factory=list)
    execution_config: Dict[str, Any] = field(default_factory=dict)
    parent_run_id: str = ""
    resume_count: int = 0
    order: int = 0
    spawned_by_run_id: str = ""
    child_run_ids: List[str] = field(default_factory=list)
    dependency_run_ids: List[str] = field(default_factory=list)
    dependency_policies: Dict[str, str] = field(default_factory=dict)
    aggregate_status: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list)
    priority: int = 0
    retry_policy: str = "never"
    max_retries: int = 0
    retry_count: int = 0
    workflow_id: str = ""
    workflow_node_id: str = ""


@dataclass
class WorkflowRecord:
    workflow_id: str
    name: str = ""
    node_run_ids: Dict[str, str] = field(default_factory=dict)
    disabled_node_ids: List[str] = field(default_factory=list)
    removed_node_ids: List[str] = field(default_factory=list)
    events: List[Dict[str, Any]] = field(default_factory=list)
    revision: int = 0
    spec_versions: List[Dict[str, Any]] = field(default_factory=list)
    snapshots: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SubagentManager:
    TERMINAL_STATUSES = {"completed", "failed", "interrupted", "cancelled"}
    RETRY_POLICIES = {"never", "on_failure"}
    DEPENDENCY_POLICIES = {"block", "ignore_failure"}

    def __init__(self, root: Optional[str] = None, max_runs: int = 200, max_concurrency: int = 2):
        self.root = Path(root) if root else _DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "runs.json"
        self.max_runs = max_runs
        self.max_concurrency = max(1, int(max_concurrency))
        self._runs: Dict[str, SubagentRun] = {}
        self._workflows: Dict[str, WorkflowRecord] = {}
        self._lock = threading.Lock()
        self._watchers: Dict[str, List[queue.Queue[Dict[str, Any]]]] = {}
        self._workflow_watchers: Dict[str, List[queue.Queue[Dict[str, Any]]]] = {}
        self._global_watchers: List[Callable[[str, str], None]] = []
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._next_order: int = 1
        self._launcher: Optional[Callable[[str], None]] = None
        self._running = True
        self._claimed_run_ids: set[str] = set()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            daemon=True,
            name="solstice-subagent-scheduler",
        )
        self._load()
        self._mark_interrupted_runs()
        self._scheduler_thread.start()

    def create(
        self,
        prompt: str,
        tools: Optional[List[str]] = None,
        details: str = "",
        execution_config: Optional[Dict[str, Any]] = None,
        parent_run_id: str = "",
        resume_count: int = 0,
        spawned_by_run_id: str = "",
        dependency_run_ids: Optional[List[str]] = None,
        dependency_policies: Optional[Dict[str, str]] = None,
        priority: int = 0,
        retry_policy: str = "never",
        max_retries: int = 0,
        retry_count: int = 0,
        workflow_id: str = "",
        workflow_node_id: str = "",
    ) -> SubagentRun:
        normalized_retry_policy = retry_policy if retry_policy in self.RETRY_POLICIES else "never"
        normalized_dependency_policies = {
            str(dep_id).strip(): (
                policy if policy in self.DEPENDENCY_POLICIES else "block"
            )
            for dep_id, policy in (dependency_policies or {}).items()
            if str(dep_id).strip()
        }
        run = SubagentRun(
            run_id=f"sa-{uuid.uuid4().hex[:8]}",
            prompt=prompt,
            tools=list(tools or []),
            status="pending",
            details=details,
            execution_config=dict(execution_config or {}),
            parent_run_id=parent_run_id,
            resume_count=resume_count,
            order=self._next_order,
            spawned_by_run_id=spawned_by_run_id,
            dependency_run_ids=sorted({str(item).strip() for item in (dependency_run_ids or []) if str(item).strip()}),
            dependency_policies=normalized_dependency_policies,
            priority=int(priority or 0),
            retry_policy=normalized_retry_policy,
            max_retries=max(0, int(max_retries or 0)),
            retry_count=max(0, int(retry_count or 0)),
            workflow_id=workflow_id,
            workflow_node_id=workflow_node_id,
        )
        with self._lock:
            self._next_order += 1
            self._runs[run.run_id] = run
            self._cancel_flags[run.run_id] = threading.Event()
            if workflow_id:
                workflow = self._workflows.setdefault(
                    workflow_id,
                    WorkflowRecord(workflow_id=workflow_id),
                )
                if workflow_node_id:
                    workflow.node_run_ids[workflow_node_id] = run.run_id
                workflow.updated_at = datetime.now(timezone.utc).isoformat()
            if spawned_by_run_id and spawned_by_run_id in self._runs:
                parent = self._runs[spawned_by_run_id]
                if run.run_id not in parent.child_run_ids:
                    parent.child_run_ids.append(run.run_id)
                    parent.aggregate_status = self._aggregate_status_for_run_locked(parent)
            self._prune_locked()
            self._save_locked()
        return run

    def update(self, run_id: str, **changes):
        with self._lock:
            run = self._runs[run_id]
            for key, value in changes.items():
                setattr(run, key, value)
            if run.status in self.TERMINAL_STATUSES and not run.finished_at:
                run.finished_at = datetime.now(timezone.utc).isoformat()
            if run.status in self.TERMINAL_STATUSES:
                run.order = self._next_order
                self._next_order += 1
                self._claimed_run_ids.discard(run_id)
            if run.spawned_by_run_id and run.spawned_by_run_id in self._runs:
                parent = self._runs[run.spawned_by_run_id]
                parent.aggregate_status = self._aggregate_status_for_run_locked(parent)
            if run.workflow_id and run.workflow_id in self._workflows:
                self._workflows[run.workflow_id].updated_at = datetime.now(timezone.utc).isoformat()
            self._prune_locked()
            self._save_locked()

    def append_progress(self, run_id: str, entry: str):
        self.append_event(run_id, "progress", entry)

    def append_event(self, run_id: str, event_type: str, message: str, **payload):
        with self._lock:
            run = self._runs[run_id]
            event = {
                "type": event_type,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **payload,
            }
            run.events.append(event)
            if len(run.events) > 100:
                run.events = run.events[-100:]
            run.progress.append(message)
            if len(run.progress) > 50:
                run.progress = run.progress[-50:]
            run.details = message
            watchers = list(self._watchers.get(run_id, []))
            workflow_watchers = list(self._workflow_watchers.get(run.workflow_id, [])) if run.workflow_id else []
            global_watchers = list(self._global_watchers)
            workflow_event = None
            if run.workflow_id:
                workflow_event = {
                    "type": event_type,
                    "message": message,
                    "timestamp": event["timestamp"],
                    "workflow_id": run.workflow_id,
                    "workflow_node_id": run.workflow_node_id,
                    "run_id": run_id,
                    **payload,
                }
                workflow = self._workflows.get(run.workflow_id)
                if workflow is not None:
                    workflow.events.append(workflow_event)
                    if len(workflow.events) > 200:
                        workflow.events = workflow.events[-200:]
                    workflow.updated_at = event["timestamp"]
            self._save_locked()
        for watcher in watchers:
            try:
                watcher.put_nowait(event)
            except Exception:
                pass
        for watcher in workflow_watchers:
            try:
                watcher.put_nowait(workflow_event)
            except Exception:
                pass
        for callback in global_watchers:
            try:
                callback(run_id, message)
            except Exception:
                pass

    def get(self, run_id: str) -> Optional[SubagentRun]:
        with self._lock:
            return self._runs.get(run_id)

    def list(self) -> List[SubagentRun]:
        with self._lock:
            return sorted(self._runs.values(), key=lambda item: (item.order, item.started_at), reverse=True)

    def subscribe(self, run_id: str) -> queue.Queue[Dict[str, Any]]:
        q: queue.Queue[Dict[str, Any]] = queue.Queue()
        with self._lock:
            self._watchers.setdefault(run_id, []).append(q)
            run = self._runs.get(run_id)
            if run:
                for event in run.events:
                    q.put_nowait(event)
        return q

    def unsubscribe(self, run_id: str, watcher: queue.Queue[Dict[str, Any]]):
        with self._lock:
            watchers = self._watchers.get(run_id, [])
            if watcher in watchers:
                watchers.remove(watcher)
            if not watchers and run_id in self._watchers:
                self._watchers.pop(run_id, None)

    def subscribe_workflow(self, workflow_id: str) -> queue.Queue[Dict[str, Any]]:
        q: queue.Queue[Dict[str, Any]] = queue.Queue()
        with self._lock:
            self._workflow_watchers.setdefault(workflow_id, []).append(q)
            workflow = self._workflows.get(workflow_id)
            if workflow:
                for event in workflow.events:
                    q.put_nowait(event)
        return q

    def unsubscribe_workflow(self, workflow_id: str, watcher: queue.Queue[Dict[str, Any]]):
        with self._lock:
            watchers = self._workflow_watchers.get(workflow_id, [])
            if watcher in watchers:
                watchers.remove(watcher)
            if not watchers and workflow_id in self._workflow_watchers:
                self._workflow_watchers.pop(workflow_id, None)

    def add_global_progress_callback(self, callback: Callable[[str, str], None]):
        with self._lock:
            self._global_watchers.append(callback)

    def request_cancel(self, run_id: str) -> Optional[SubagentRun]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None
            flag = self._cancel_flags.setdefault(run_id, threading.Event())
            flag.set()
            if run.status == "pending":
                run.status = "cancelled"
                run.finished_at = datetime.now(timezone.utc).isoformat()
                run.error = "Cancelled before execution started."
                run.details = "Cancelled"
                run.progress.append("Cancelled")
                if len(run.progress) > 50:
                    run.progress = run.progress[-50:]
                run.order = self._next_order
                self._next_order += 1
                self._claimed_run_ids.discard(run_id)
                self._prune_locked()
                self._save_locked()
            return run

    def request_cancel_tree(self, run_id: str) -> Optional[SubagentRun]:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return None
            targets = [run_id]
            seen = set()
            while targets:
                current_id = targets.pop()
                if current_id in seen:
                    continue
                seen.add(current_id)
                current = self._runs.get(current_id)
                if not current:
                    continue
                flag = self._cancel_flags.setdefault(current_id, threading.Event())
                flag.set()
                targets.extend(current.child_run_ids)
                if current.status == "pending":
                    current.status = "cancelled"
                    current.finished_at = datetime.now(timezone.utc).isoformat()
                    current.error = "Cancelled before execution started."
                    current.details = "Cancelled"
                    current.progress.append("Cancelled")
                    if len(current.progress) > 50:
                        current.progress = current.progress[-50:]
                    current.order = self._next_order
                    self._next_order += 1
                    self._claimed_run_ids.discard(current_id)
                if current.spawned_by_run_id and current.spawned_by_run_id in self._runs:
                    parent = self._runs[current.spawned_by_run_id]
                    parent.aggregate_status = self._aggregate_status_for_run_locked(parent)
            self._save_locked()
            return run

    def is_cancel_requested(self, run_id: str) -> bool:
        with self._lock:
            flag = self._cancel_flags.get(run_id)
            return bool(flag and flag.is_set())

    def _load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            for payload in raw.get("workflows", []):
                try:
                    workflow = WorkflowRecord(**payload)
                except TypeError:
                    continue
                self._workflows[workflow.workflow_id] = workflow
            for payload in raw.get("runs", []):
                try:
                    run = SubagentRun(**payload)
                except TypeError:
                    continue
                self._runs[run.run_id] = run
                self._cancel_flags[run.run_id] = threading.Event()
                self._next_order = max(self._next_order, int(getattr(run, "order", 0) or 0) + 1)
            for run in self._runs.values():
                run.aggregate_status = self._aggregate_status_for_run_locked(run)
        except Exception as exc:
            log.warning(f"Failed to load sub-agent runs: {exc}")

    def _save_locked(self):
        payload = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "workflows": [
                asdict(item)
                for item in sorted(
                    self._workflows.values(),
                    key=lambda item: item.updated_at,
                    reverse=True,
                )
            ],
            "runs": [
                asdict(item)
                for item in sorted(
                    self._runs.values(),
                    key=lambda item: (item.order, item.started_at),
                    reverse=True,
                )
            ],
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _mark_interrupted_runs(self):
        interrupted = False
        finished_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            for run in self._runs.values():
                if run.status not in {"pending", "running"}:
                    continue
                run.status = "interrupted"
                run.error = run.error or "Process restarted before the sub-agent finished."
                run.finished_at = run.finished_at or finished_at
                run.details = "Interrupted by restart"
                run.progress.append("Interrupted by restart")
                if len(run.progress) > 50:
                    run.progress = run.progress[-50:]
                interrupted = True
                if run.spawned_by_run_id and run.spawned_by_run_id in self._runs:
                    parent = self._runs[run.spawned_by_run_id]
                    parent.aggregate_status = self._aggregate_status_for_run_locked(parent)
            if interrupted:
                self._save_locked()

    def _prune_locked(self):
        terminal_runs = sorted(
            [run for run in self._runs.values() if run.status in self.TERMINAL_STATUSES],
            key=lambda item: (item.order, item.finished_at or item.started_at),
            reverse=True,
        )
        keep_ids = {run.run_id for run in terminal_runs[: self.max_runs]}
        for run_id, run in list(self._runs.items()):
            if run.status in self.TERMINAL_STATUSES and run_id not in keep_ids:
                self._runs.pop(run_id, None)
                self._watchers.pop(run_id, None)
                self._cancel_flags.pop(run_id, None)

    def _aggregate_status_for_run_locked(self, run: SubagentRun) -> str:
        if not run.child_run_ids:
            return ""
        children = [self._runs[child_id] for child_id in run.child_run_ids if child_id in self._runs]
        if not children:
            return ""
        statuses = {child.status for child in children}
        if any(status in {"failed", "interrupted", "cancelled"} for status in statuses):
            return "degraded"
        if any(status in {"pending", "running"} for status in statuses):
            return "in_progress"
        if statuses == {"completed"}:
            return "completed"
        return "mixed"

    def dependency_state(self, run_id: str) -> Dict[str, List[str]]:
        with self._lock:
            run = self._runs.get(run_id)
            return self._dependency_state_for_run_locked(run)

    def _dependency_state_for_run_locked(self, run: Optional[SubagentRun]) -> Dict[str, List[str]]:
        if not run:
            return {"blocked": [], "failed": [], "ignored_failures": [], "ready": []}
        blocked: List[str] = []
        failed: List[str] = []
        ignored_failures: List[str] = []
        ready: List[str] = []
        for dep_id in run.dependency_run_ids:
            dep = self._runs.get(dep_id)
            policy = run.dependency_policies.get(dep_id, "block")
            if dep is None:
                if policy == "ignore_failure":
                    ignored_failures.append(dep_id)
                else:
                    failed.append(dep_id)
            elif dep.status == "completed":
                ready.append(dep_id)
            elif dep.status in {"failed", "interrupted", "cancelled"}:
                if policy == "ignore_failure":
                    ignored_failures.append(dep_id)
                else:
                    failed.append(dep_id)
            else:
                blocked.append(dep_id)
        return {"blocked": blocked, "failed": failed, "ignored_failures": ignored_failures, "ready": ready}

    def set_launcher(self, launcher: Callable[[str], None]):
        with self._lock:
            self._launcher = launcher

    def stop(self):
        self._running = False
        if self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=1)

    def scheduler_summary(self) -> Dict[str, int]:
        with self._lock:
            return {
                "pending": sum(1 for run in self._runs.values() if run.status == "pending"),
                "running": sum(1 for run in self._runs.values() if run.status == "running"),
                "claimed": len(self._claimed_run_ids),
                "max_concurrency": self.max_concurrency,
            }

    def list_workflows(self) -> List[WorkflowRecord]:
        with self._lock:
            return sorted(self._workflows.values(), key=lambda item: item.updated_at, reverse=True)

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowRecord]:
        with self._lock:
            return self._workflows.get(workflow_id)

    def workflow_status_summary(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return None
            runs = [
                self._runs[run_id]
                for run_id in workflow.node_run_ids.values()
                if run_id in self._runs
            ]
            counts: Dict[str, int] = {}
            for run in runs:
                counts[run.status] = counts.get(run.status, 0) + 1
            statuses = set(counts.keys())
            if not statuses:
                aggregate = "empty"
            elif any(status in {"failed", "interrupted", "cancelled"} for status in statuses):
                aggregate = "degraded"
            elif any(status in {"pending", "running"} for status in statuses):
                aggregate = "in_progress"
            elif statuses == {"completed"}:
                aggregate = "completed"
            else:
                aggregate = "mixed"
            return {
                "workflow_id": workflow.workflow_id,
                "name": workflow.name,
                "revision": workflow.revision,
                "created_at": workflow.created_at,
                "updated_at": workflow.updated_at,
                "aggregate_status": aggregate,
                "counts": counts,
                "node_run_ids": dict(workflow.node_run_ids),
                "disabled_node_ids": list(workflow.disabled_node_ids),
                "removed_node_ids": list(workflow.removed_node_ids),
                "snapshot_count": len(workflow.snapshots),
            }

    def cancel_workflow(self, workflow_id: str) -> bool:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False
            run_ids = list(workflow.node_run_ids.values())
        for run_id in run_ids:
            self.request_cancel_tree(run_id)
        return True

    def append_workflow_event(self, workflow_id: str, event_type: str, message: str, **payload):
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return
            event = {
                "type": event_type,
                "message": message,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "workflow_id": workflow_id,
                **payload,
            }
            workflow.events.append(event)
            if len(workflow.events) > 200:
                workflow.events = workflow.events[-200:]
            workflow.updated_at = event["timestamp"]
            watchers = list(self._workflow_watchers.get(workflow_id, []))
            self._save_locked()
        for watcher in watchers:
            try:
                watcher.put_nowait(event)
            except Exception:
                pass

    def workflow_events(self, workflow_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            return list(workflow.events) if workflow else []

    def _workflow_spec_locked(self, workflow: WorkflowRecord) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        for node_id, run_id in sorted(workflow.node_run_ids.items()):
            run = self._runs.get(run_id)
            if not run:
                nodes.append({"id": node_id, "run_id": run_id, "missing": True})
                continue
            config = dict(run.execution_config or {})
            dep_node_ids: List[str] = []
            dep_policies: Dict[str, str] = {}
            for dep_run_id in run.dependency_run_ids:
                dep_node_id = ""
                for candidate_node_id, candidate_run_id in workflow.node_run_ids.items():
                    if candidate_run_id == dep_run_id:
                        dep_node_id = candidate_node_id
                        break
                dep_node_ids.append(dep_node_id or dep_run_id)
                dep_policies[dep_node_id or dep_run_id] = run.dependency_policies.get(dep_run_id, "block")
            node_payload = {
                "id": node_id,
                "run_id": run.run_id,
                "status": run.status,
                "prompt": config.get("prompt", run.prompt),
                "tools": list(config.get("tools") or run.tools),
                "extra_instructions": config.get("extra_instructions", ""),
                "include_parent_history": bool(config.get("include_parent_history", False)),
                "allowed_command_prefixes": list(config.get("allowed_command_prefixes") or []),
                "denied_command_prefixes": list(config.get("denied_command_prefixes") or []),
                "workspace_root": config.get("workspace_root") or "",
                "workspace_required": config.get("workspace_required"),
                "model_override": config.get("model_override", ""),
                "max_tool_iterations": config.get("max_tool_iterations"),
                "task_subject": config.get("task_subject", ""),
                "depends_on": dep_node_ids,
                "dependency_policies": dep_policies,
                "priority": int(config.get("priority", run.priority) or 0),
                "retry_policy": config.get("retry_policy", run.retry_policy),
                "max_retries": int(config.get("max_retries", run.max_retries) or 0),
            }
            nodes.append(node_payload)
        return {
            "workflow_id": workflow.workflow_id,
            "name": workflow.name,
            "revision": workflow.revision,
            "disabled_node_ids": list(workflow.disabled_node_ids),
            "removed_node_ids": list(workflow.removed_node_ids),
            "nodes": nodes,
        }

    def _record_workflow_revision_locked(self, workflow: WorkflowRecord, action: str, **details):
        workflow.revision += 1
        snapshot = {
            "revision": workflow.revision,
            "action": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": details,
            "spec": self._workflow_spec_locked(workflow),
        }
        workflow.spec_versions.append(snapshot)
        if len(workflow.spec_versions) > 50:
            workflow.spec_versions = workflow.spec_versions[-50:]
        workflow.updated_at = snapshot["timestamp"]

    def workflow_snapshot(self, workflow_id: str, label: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return None
            snapshot = {
                "snapshot_id": f"wfs-{uuid.uuid4().hex[:8]}",
                "label": str(label or "").strip(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "spec": self._workflow_spec_locked(workflow),
            }
            workflow.snapshots.append(snapshot)
            if len(workflow.snapshots) > 25:
                workflow.snapshots = workflow.snapshots[-25:]
            workflow.updated_at = snapshot["timestamp"]
            self._save_locked()
            return snapshot

    def workflow_export(self, workflow_id: str, snapshot_id: str = "") -> Optional[Dict[str, Any]]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return None
            if snapshot_id:
                for snapshot in workflow.snapshots:
                    if snapshot.get("snapshot_id") == snapshot_id:
                        return {
                            "workflow_id": workflow_id,
                            "name": workflow.name,
                            "snapshot": snapshot,
                            "revision": workflow.revision,
                        }
                return {"error": f"Snapshot '{snapshot_id}' not found."}
            return {
                "workflow_id": workflow_id,
                "name": workflow.name,
                "revision": workflow.revision,
                "current": self._workflow_spec_locked(workflow),
                "snapshots": list(workflow.snapshots),
                "recent_revisions": list(workflow.spec_versions[-10:]),
            }

    def workflow_remove_node(self, workflow_id: str, node_id: str) -> tuple[bool, str]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False, f"Workflow '{workflow_id}' not found."
            normalized_node_id = str(node_id).strip()
            run_id = workflow.node_run_ids.get(normalized_node_id)
            if not run_id:
                return False, f"Workflow node '{node_id}' not found in '{workflow_id}'."
            run = self._runs.get(run_id)
            if not run:
                return False, f"Workflow node '{node_id}' run is missing."
            if run.status != "pending":
                return False, f"Workflow node '{node_id}' can only be removed while pending."
            for other_node_id, other_run_id in workflow.node_run_ids.items():
                if other_node_id == normalized_node_id:
                    continue
                other_run = self._runs.get(other_run_id)
                if not other_run:
                    continue
                if run_id in other_run.dependency_run_ids:
                    return False, f"Workflow node '{node_id}' still has downstream dependencies."
            workflow.node_run_ids.pop(normalized_node_id, None)
            if normalized_node_id not in workflow.removed_node_ids:
                workflow.removed_node_ids.append(normalized_node_id)
            workflow.disabled_node_ids = [item for item in workflow.disabled_node_ids if item != normalized_node_id]
            self._runs.pop(run_id, None)
            self._watchers.pop(run_id, None)
            self._cancel_flags.pop(run_id, None)
            self._claimed_run_ids.discard(run_id)
            self._record_workflow_revision_locked(workflow, "node_removed", workflow_node_id=normalized_node_id)
            self._save_locked()
        self.append_workflow_event(workflow_id, "node_removed", f"Removed node {normalized_node_id}", workflow_node_id=normalized_node_id)
        return True, f"Workflow node '{normalized_node_id}' removed."

    def workflow_disable_node(self, workflow_id: str, node_id: str) -> tuple[bool, str]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False, f"Workflow '{workflow_id}' not found."
            normalized_node_id = str(node_id).strip()
            run_id = workflow.node_run_ids.get(normalized_node_id)
            if not run_id:
                return False, f"Workflow node '{node_id}' not found in '{workflow_id}'."
            run = self._runs.get(run_id)
            if not run:
                return False, f"Workflow node '{node_id}' run is missing."
            if run.status != "pending":
                return False, f"Workflow node '{node_id}' can only be disabled while pending."
            if normalized_node_id not in workflow.disabled_node_ids:
                workflow.disabled_node_ids.append(normalized_node_id)
            self._record_workflow_revision_locked(workflow, "node_disabled", workflow_node_id=normalized_node_id)
            self._save_locked()
        self.append_workflow_event(workflow_id, "node_disabled", f"Disabled node {normalized_node_id}", workflow_node_id=normalized_node_id, run_id=run_id)
        return True, f"Workflow node '{normalized_node_id}' disabled."

    def workflow_enable_node(self, workflow_id: str, node_id: str) -> tuple[bool, str]:
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False, f"Workflow '{workflow_id}' not found."
            normalized_node_id = str(node_id).strip()
            if normalized_node_id not in workflow.disabled_node_ids:
                return False, f"Workflow node '{node_id}' is not disabled."
            workflow.disabled_node_ids = [item for item in workflow.disabled_node_ids if item != normalized_node_id]
            self._record_workflow_revision_locked(workflow, "node_enabled", workflow_node_id=normalized_node_id)
            self._save_locked()
        self.append_workflow_event(workflow_id, "node_enabled", f"Enabled node {normalized_node_id}", workflow_node_id=normalized_node_id)
        return True, f"Workflow node '{normalized_node_id}' enabled."

    def workflow_rewire_dependency(
        self,
        workflow_id: str,
        node_id: str,
        dependency_node_id: str,
        action: str,
        policy: str = "block",
    ) -> tuple[bool, str]:
        normalized_action = str(action or "").strip().lower()
        normalized_policy = str(policy or "block").strip()
        if normalized_action not in {"add", "remove"}:
            return False, "Error: action must be 'add' or 'remove'."
        if normalized_policy not in self.DEPENDENCY_POLICIES:
            return False, "Error: policy must be one of block or ignore_failure."
        with self._lock:
            workflow = self._workflows.get(workflow_id)
            if not workflow:
                return False, f"Workflow '{workflow_id}' not found."
            normalized_node_id = str(node_id).strip()
            normalized_dependency_node_id = str(dependency_node_id).strip()
            if normalized_node_id == normalized_dependency_node_id:
                return False, "Error: a workflow node cannot depend on itself."
            node_run_id = workflow.node_run_ids.get(normalized_node_id)
            dependency_run_id = workflow.node_run_ids.get(normalized_dependency_node_id)
            if not node_run_id or not dependency_run_id:
                return False, f"Workflow edge '{dependency_node_id} -> {node_id}' not found in '{workflow_id}'."
            run = self._runs.get(node_run_id)
            if not run:
                return False, f"Workflow node '{node_id}' run is missing."
            if normalized_action == "add":
                if dependency_run_id not in run.dependency_run_ids:
                    run.dependency_run_ids.append(dependency_run_id)
                    run.dependency_run_ids = sorted(set(run.dependency_run_ids))
                run.dependency_policies[dependency_run_id] = normalized_policy
            else:
                if dependency_run_id not in run.dependency_run_ids:
                    return False, f"Workflow edge '{dependency_node_id} -> {node_id}' not found in '{workflow_id}'."
                run.dependency_run_ids = [item for item in run.dependency_run_ids if item != dependency_run_id]
                run.dependency_policies.pop(dependency_run_id, None)
            run.execution_config["depends_on_run_ids"] = list(run.dependency_run_ids)
            run.execution_config["dependency_policies"] = dict(run.dependency_policies)
            self._record_workflow_revision_locked(
                workflow,
                "dependency_rewired",
                workflow_node_id=normalized_node_id,
                dependency_node_id=normalized_dependency_node_id,
                edge_action=normalized_action,
                policy=normalized_policy,
            )
            self._save_locked()
        self.append_workflow_event(
            workflow_id,
            "dependency_rewired",
            f"{normalized_action.title()}ed dependency {dependency_node_id} -> {node_id}",
            workflow_node_id=normalized_node_id,
            dependency_node_id=normalized_dependency_node_id,
            action=normalized_action,
            policy=normalized_policy,
        )
        return True, f"Workflow dependency {normalized_action}ed for {dependency_node_id} -> {node_id}."

    def requeue_for_retry(self, run_id: str, error: str) -> bool:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return False
            if run.retry_policy != "on_failure" or run.retry_count >= run.max_retries:
                return False
            run.retry_count += 1
            run.status = "pending"
            run.error = ""
            run.finished_at = ""
            run.details = f"Retry scheduled after failure: {error}"
            run.order = self._next_order
            self._next_order += 1
            self._claimed_run_ids.discard(run_id)
            self._save_locked()
            return True

    def _scheduler_loop(self):
        while self._running:
            launcher = None
            ready_run_ids: List[str] = []
            with self._lock:
                launcher = self._launcher
                running_count = sum(1 for run in self._runs.values() if run.status == "running")
                available_slots = max(0, self.max_concurrency - running_count - len(self._claimed_run_ids))
                if launcher and available_slots > 0:
                    ready_candidates: List[SubagentRun] = []
                    for run in self._runs.values():
                        if run.status != "pending" or run.run_id in self._claimed_run_ids:
                            continue
                        if run.workflow_id:
                            workflow = self._workflows.get(run.workflow_id)
                            if workflow and run.workflow_node_id in workflow.disabled_node_ids:
                                continue
                        state = self._dependency_state_for_run_locked(run)
                        if state["failed"] or state["blocked"]:
                            continue
                        ready_candidates.append(run)
                    ready_candidates.sort(key=lambda item: (item.priority, item.order), reverse=True)
                    for run in ready_candidates[:available_slots]:
                        self._claimed_run_ids.add(run.run_id)
                        ready_run_ids.append(run.run_id)
            if launcher:
                for run_id in ready_run_ids:
                    try:
                        launcher(run_id)
                    except Exception:
                        with self._lock:
                            self._claimed_run_ids.discard(run_id)
            threading.Event().wait(0.05)


_manager: Optional[SubagentManager] = None


def _get_manager() -> SubagentManager:
    global _manager
    if _manager is None:
        _manager = SubagentManager()
    return _manager


def init_subagent_manager(root: Optional[str] = None, max_concurrency: int = 2):
    global _manager
    if _manager is not None:
        _manager.stop()
    _manager = SubagentManager(root=root, max_concurrency=max_concurrency)


def register_subagent_tools(agent):
    def _build_execution_config(
        prompt: str,
        tools: Optional[List[str]],
        extra_instructions: str,
        include_parent_history: bool,
        allowed_command_prefixes: Optional[List[str]],
        denied_command_prefixes: Optional[List[str]],
        workspace_root: Optional[str],
        workspace_required: Optional[bool],
        model_override: str,
        max_tool_iterations: Optional[int],
        task_subject: str,
        spawned_by_run_id: str,
        depends_on_run_ids: Optional[List[str]],
        dependency_policies: Optional[Dict[str, str]],
        priority: int,
        retry_policy: str,
        max_retries: int,
        workflow_id: str,
        workflow_node_id: str,
    ) -> Dict[str, Any]:
        return {
            "prompt": prompt,
            "tools": list(tools or []),
            "extra_instructions": extra_instructions,
            "include_parent_history": include_parent_history,
            "allowed_command_prefixes": list(allowed_command_prefixes or []),
            "denied_command_prefixes": list(denied_command_prefixes or []),
            "workspace_root": workspace_root or "",
            "workspace_required": workspace_required,
            "model_override": model_override,
            "max_tool_iterations": max_tool_iterations,
            "task_subject": task_subject,
            "spawned_by_run_id": spawned_by_run_id,
            "depends_on_run_ids": list(depends_on_run_ids or []),
            "dependency_policies": dict(dependency_policies or {}),
            "priority": int(priority or 0),
            "retry_policy": retry_policy,
            "max_retries": int(max_retries or 0),
            "workflow_id": workflow_id,
            "workflow_node_id": workflow_node_id,
        }

    def _start_run_thread(run_id: str):
        manager = _get_manager()
        run = manager.get(run_id)
        if not run:
            return
        config = dict(run.execution_config or {})
        thread = threading.Thread(
            target=_execute_child,
            args=(
                run_id,
                str(config.get("prompt", "")),
                config.get("tools") or [],
                str(config.get("extra_instructions", "")),
                bool(config.get("include_parent_history", False)),
                config.get("allowed_command_prefixes") or [],
                config.get("denied_command_prefixes") or [],
                config.get("workspace_root") or None,
                config.get("workspace_required"),
                str(config.get("model_override", "")),
                config.get("max_tool_iterations"),
                str(config.get("task_subject", "")),
                config.get("depends_on_run_ids") or [],
            ),
            daemon=True,
        )
        thread.start()

    def _launch_subagent(
        execution_config: Dict[str, Any],
        async_mode: bool,
        parent_run_id: str = "",
        resume_count: int = 0,
    ) -> str:
        prompt = str(execution_config.get("prompt", ""))
        tools = execution_config.get("tools") or []
        extra_instructions = str(execution_config.get("extra_instructions", ""))
        include_parent_history = bool(execution_config.get("include_parent_history", False))
        allowed_command_prefixes = execution_config.get("allowed_command_prefixes") or []
        denied_command_prefixes = execution_config.get("denied_command_prefixes") or []
        workspace_root = execution_config.get("workspace_root") or None
        workspace_required = execution_config.get("workspace_required")
        model_override = str(execution_config.get("model_override", ""))
        max_tool_iterations = execution_config.get("max_tool_iterations")
        task_subject = str(execution_config.get("task_subject", ""))
        spawned_by_run_id = str(execution_config.get("spawned_by_run_id", ""))
        depends_on_run_ids = [str(item) for item in (execution_config.get("depends_on_run_ids") or []) if str(item)]
        dependency_policies = {
            str(dep_id): str(policy)
            for dep_id, policy in (execution_config.get("dependency_policies") or {}).items()
        }
        priority = int(execution_config.get("priority", 0) or 0)
        retry_policy = str(execution_config.get("retry_policy", "never") or "never")
        max_retries = int(execution_config.get("max_retries", 0) or 0)
        workflow_id = str(execution_config.get("workflow_id", ""))
        workflow_node_id = str(execution_config.get("workflow_node_id", ""))

        run = _get_manager().create(
            prompt=prompt,
            tools=tools,
            details=extra_instructions,
            execution_config=execution_config,
            parent_run_id=parent_run_id,
            resume_count=resume_count,
            spawned_by_run_id=spawned_by_run_id,
            dependency_run_ids=depends_on_run_ids,
            dependency_policies=dependency_policies,
            priority=priority,
            retry_policy=retry_policy,
            max_retries=max_retries,
            workflow_id=workflow_id,
            workflow_node_id=workflow_node_id,
        )

        if async_mode:
            queued_message = "Queued for execution"
            if depends_on_run_ids:
                queued_message = f"Waiting on dependencies: {', '.join(depends_on_run_ids)}"
            _get_manager().append_event(
                run.run_id,
                "queued",
                queued_message,
                priority=priority,
                retry_policy=retry_policy,
                max_retries=max_retries,
                dependencies=depends_on_run_ids,
            )
            return (
                f"Sub-agent started.\n"
                f"Run ID: {run.run_id}\n"
                f"Use subagent_status('{run.run_id}') or subagent_result('{run.run_id}') to inspect it."
            )

        _execute_child(
            run.run_id,
            prompt,
            tools,
            extra_instructions,
            include_parent_history,
            allowed_command_prefixes,
            denied_command_prefixes,
            workspace_root,
            workspace_required,
            model_override,
            max_tool_iterations,
            task_subject,
            depends_on_run_ids,
        )
        current = _get_manager().get(run.run_id)
        if current and current.status == "completed":
            return current.result
        if current and current.status == "cancelled":
            return f"Sub-agent cancelled.\n{current.error or 'Cancelled by request.'}"
        return f"Sub-agent failed.\n{current.error if current else 'Unknown error'}"

    def _execute_child(
        run_id: str,
        prompt: str,
        tools: Optional[List[str]],
        extra_instructions: str,
        include_parent_history: bool,
        allowed_command_prefixes: Optional[List[str]],
        denied_command_prefixes: Optional[List[str]],
        workspace_root: Optional[str],
        workspace_required: Optional[bool],
        model_override: str,
        max_tool_iterations: Optional[int],
        task_subject: str,
        depends_on_run_ids: Optional[List[str]],
    ):
        def _progress(event: Dict[str, object]):
            event_type = str(event.get("type", "progress"))
            if event_type == "request_started":
                text = "Request started"
            elif event_type == "model_iteration":
                tool_names = event.get("tool_calls") or []
                text = f"Model iteration {event.get('iteration')}"
                if tool_names:
                    text += f" -> tools: {', '.join(str(item) for item in tool_names)}"
            elif event_type == "tool_started":
                text = f"Tool started: {event.get('tool')}"
            elif event_type == "tool_completed":
                text = f"Tool completed: {event.get('tool')}"
            elif event_type == "tool_failed":
                text = f"Tool failed: {event.get('tool')} ({event.get('error')})"
            elif event_type == "request_completed":
                text = "Request completed"
            else:
                text = event_type.replace("_", " ")
            _get_manager().append_event(run_id, event_type, text, payload=event)

        if task_subject:
            try:
                from .tasks import task_upsert

                task_upsert(subject=task_subject, status="in_progress", metadata_json='{"subagent_run": "%s"}' % run_id)
            except Exception:
                pass

        manager = _get_manager()
        manager.update(run_id, status="running", details="Child agent running")
        manager.append_event(run_id, "lifecycle", "Child agent running")
        dependency_ids = [str(item).strip() for item in (depends_on_run_ids or []) if str(item).strip()]
        if dependency_ids:
            manager.append_event(run_id, "dependencies_declared", f"Waiting on {len(dependency_ids)} dependenc(ies)", dependencies=dependency_ids)
            while True:
                if manager.is_cancel_requested(run_id):
                    raise AgentExecutionCancelled("Agent execution was cancelled.")
                state = manager.dependency_state(run_id)
                if state["failed"]:
                    raise RuntimeError(f"Dependency failure: {', '.join(state['failed'])}")
                if not state["blocked"]:
                    break
                manager.update(run_id, status="pending", details=f"Waiting on dependencies: {', '.join(state['blocked'])}")
                manager.append_event(run_id, "dependencies_waiting", f"Waiting on dependencies: {', '.join(state['blocked'])}", blocked=state["blocked"])
                threading.Event().wait(0.05)
            manager.update(run_id, status="running", details="Dependencies satisfied")
            manager.append_event(run_id, "dependencies_ready", "Dependencies satisfied", dependencies=dependency_ids)
        try:
            child = agent.clone_with_tools(
                tool_names=tools,
                extra_instructions=extra_instructions,
                include_history=include_parent_history,
                allowed_command_prefixes=allowed_command_prefixes,
                denied_command_prefixes=denied_command_prefixes,
                workspace_root=workspace_root,
                workspace_required=workspace_required,
                model_override=model_override,
                max_tool_iterations=max_tool_iterations,
            )
            child.progress_callback = _progress
            child.should_continue_callback = lambda: not manager.is_cancel_requested(run_id)
            response = child.chat(prompt)
            visible_tools = ", ".join(child.list_tool_names())
            result = (
                f"Sub-agent completed.\n"
                f"Tools: {visible_tools or '(none)'}\n"
                f"Response:\n{response}"
            )
            manager.update(
                run_id,
                status="completed",
                result=result,
                finished_at=datetime.now(timezone.utc).isoformat(),
                details="Completed",
            )
            manager.append_event(run_id, "lifecycle", "Completed")
            if task_subject:
                try:
                    from .tasks import task_upsert

                    task_upsert(subject=task_subject, status="completed", metadata_json='{"subagent_run": "%s"}' % run_id)
                except Exception:
                    pass
        except AgentExecutionCancelled as exc:
            manager.update(
                run_id,
                status="cancelled",
                error=str(exc),
                finished_at=datetime.now(timezone.utc).isoformat(),
                details="Cancelled",
            )
            manager.append_event(run_id, "lifecycle", "Cancelled")
            if task_subject:
                try:
                    from .tasks import task_upsert

                    task_upsert(
                        subject=task_subject,
                        status="completed",
                        details=f"Sub-agent cancelled: {exc}",
                        metadata_json='{"subagent_run": "%s", "cancelled": true}' % run_id,
                    )
                except Exception:
                    pass
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            if manager.requeue_for_retry(run_id, error_msg):
                manager.append_event(run_id, "retry_scheduled", f"Retry scheduled after failure: {error_msg}")
                return
            manager.update(
                run_id,
                status="failed",
                error=error_msg,
                finished_at=datetime.now(timezone.utc).isoformat(),
                details="Failed",
            )
            manager.append_event(run_id, "lifecycle", f"Failed: {error_msg}", error=error_msg)
            if task_subject:
                try:
                    from .tasks import task_upsert

                    task_upsert(
                        subject=task_subject,
                        status="completed",
                        details=f"Sub-agent failed: {type(exc).__name__}: {exc}",
                        metadata_json='{"subagent_run": "%s", "failed": true}' % run_id,
                    )
                except Exception:
                    pass

    def run_subagent(
        prompt: str,
        tools: Optional[List[str]] = None,
        extra_instructions: str = "",
        include_parent_history: bool = False,
        async_mode: bool = True,
        allowed_command_prefixes: Optional[List[str]] = None,
        denied_command_prefixes: Optional[List[str]] = None,
        workspace_root: Optional[str] = None,
        workspace_required: Optional[bool] = None,
        model_override: str = "",
        max_tool_iterations: Optional[int] = None,
        task_subject: str = "",
        spawned_by_run_id: str = "",
        depends_on_run_ids: Optional[List[str]] = None,
        dependency_policies_json: str = "",
        priority: int = 0,
        retry_policy: str = "never",
        max_retries: int = 0,
        workflow_id: str = "",
        workflow_node_id: str = "",
    ) -> str:
        dependency_policies: Dict[str, str] = {}
        if dependency_policies_json:
            try:
                loaded = json.loads(dependency_policies_json)
                if isinstance(loaded, dict):
                    dependency_policies = {str(k): str(v) for k, v in loaded.items()}
            except json.JSONDecodeError as exc:
                return f"Error: dependency_policies_json must be valid JSON ({exc})"
        execution_config = _build_execution_config(
            prompt=prompt,
            tools=tools,
            extra_instructions=extra_instructions,
            include_parent_history=include_parent_history,
            allowed_command_prefixes=allowed_command_prefixes,
            denied_command_prefixes=denied_command_prefixes,
            workspace_root=workspace_root,
            workspace_required=workspace_required,
            model_override=model_override,
            max_tool_iterations=max_tool_iterations,
            task_subject=task_subject,
            spawned_by_run_id=spawned_by_run_id,
            depends_on_run_ids=depends_on_run_ids,
            dependency_policies=dependency_policies,
            priority=priority,
            retry_policy=retry_policy,
            max_retries=max_retries,
            workflow_id=workflow_id,
            workflow_node_id=workflow_node_id,
        )
        return _launch_subagent(execution_config, async_mode=async_mode)

    def submit_workflow(workflow_json: str, workflow_name: str = "") -> str:
        try:
            payload = json.loads(workflow_json)
        except json.JSONDecodeError as exc:
            return f"Error: workflow_json must be valid JSON ({exc})"

        nodes = payload.get("nodes") if isinstance(payload, dict) else None
        if not isinstance(nodes, list) or not nodes:
            return "Error: workflow_json must include a non-empty 'nodes' array."

        workflow_id = f"wf-{uuid.uuid4().hex[:8]}"
        created: Dict[str, str] = {}
        results: List[str] = []
        manager = _get_manager()
        manager._workflows[workflow_id] = WorkflowRecord(
            workflow_id=workflow_id,
            name=workflow_name,
        )
        with manager._lock:
            workflow = manager._workflows[workflow_id]
            manager._record_workflow_revision_locked(workflow, "workflow_created", workflow_name=workflow_name)
            manager._save_locked()
        manager.append_workflow_event(
            workflow_id,
            "workflow_submitted",
            f"Workflow submitted: {workflow_name or workflow_id}",
            workflow_name=workflow_name,
        )

        for node in nodes:
            if not isinstance(node, dict):
                return "Error: each workflow node must be an object."
            node_id = str(node.get("id", "")).strip()
            prompt = str(node.get("prompt", "")).strip()
            if not node_id or not prompt:
                return "Error: each workflow node requires 'id' and 'prompt'."
            depends_on_nodes = [str(item).strip() for item in (node.get("depends_on") or []) if str(item).strip()]
            unresolved = [item for item in depends_on_nodes if item not in created]
            if unresolved:
                return f"Error: workflow node '{node_id}' depends on unknown or later node(s): {', '.join(unresolved)}"
            dependency_policies = {
                created[str(dep_id)]: str(policy)
                for dep_id, policy in (node.get('dependency_policies') or {}).items()
                if str(dep_id) in created
            }
            depends_on_run_ids = [created[item] for item in depends_on_nodes]
            response = run_subagent(
                prompt=prompt,
                tools=node.get("tools"),
                extra_instructions=str(node.get("extra_instructions", "")),
                include_parent_history=bool(node.get("include_parent_history", False)),
                async_mode=bool(node.get("async_mode", True)),
                allowed_command_prefixes=node.get("allowed_command_prefixes"),
                denied_command_prefixes=node.get("denied_command_prefixes"),
                workspace_root=node.get("workspace_root"),
                workspace_required=node.get("workspace_required"),
                model_override=str(node.get("model_override", "")),
                max_tool_iterations=node.get("max_tool_iterations"),
                task_subject=str(node.get("task_subject", workflow_name or node_id)),
                spawned_by_run_id=str(node.get("spawned_by_run_id", "")),
                depends_on_run_ids=depends_on_run_ids,
                dependency_policies_json=json.dumps(dependency_policies),
                priority=int(node.get("priority", 0) or 0),
                retry_policy=str(node.get("retry_policy", "never") or "never"),
                max_retries=int(node.get("max_retries", 0) or 0),
                workflow_id=workflow_id,
                workflow_node_id=node_id,
            )
            if "Run ID: " in response:
                run_id = response.split("Run ID: ", 1)[1].splitlines()[0].strip()
            else:
                return f"Error: failed to create workflow node '{node_id}'.\n{response}"
            created[node_id] = run_id
            run = manager.get(run_id)
            if run:
                manager.append_event(
                    run_id,
                    "workflow_registered",
                    f"Registered workflow node {node_id}",
                    workflow_id=workflow_id,
                    workflow_node_id=node_id,
                    workflow_name=workflow_name,
                )
            results.append(f"  {node_id} -> {run_id}")

        header = workflow_name or workflow_id
        return "Workflow submitted.\n" + f"Workflow: {header} ({workflow_id})\n" + "\n".join(results)

    def resume_subagent(run_id: str, async_mode: bool = True, task_subject: str = "") -> str:
        current = _get_manager().get(run_id)
        if not current:
            return f"Sub-agent '{run_id}' not found."
        if current.status not in {"interrupted", "failed", "cancelled"}:
            return f"Sub-agent '{run_id}' is {current.status} and cannot be resumed."
        execution_config = dict(current.execution_config or {})
        if not execution_config:
            return f"Sub-agent '{run_id}' cannot be resumed because its execution config was not saved."
        if task_subject:
            execution_config["task_subject"] = task_subject
        return _launch_subagent(
            execution_config,
            async_mode=async_mode,
            parent_run_id=run_id,
            resume_count=current.resume_count + 1,
        )

    def cancel_subagent(run_id: str) -> str:
        run = _get_manager().request_cancel_tree(run_id)
        if not run:
            return f"Sub-agent '{run_id}' not found."
        if run.status == "cancelled":
            return f"Sub-agent '{run_id}' cancelled with descendants."
        return f"Cancellation requested for '{run_id}' and its descendants."

    def subagent_status(run_id: str) -> str:
        manager = _get_manager()
        run = manager.get(run_id)
        if not run:
            return f"Sub-agent '{run_id}' not found."
        lines = [
            f"{run.run_id} [{run.status}]",
            f"Started: {run.started_at}",
            f"Finished: {run.finished_at or '(running)'}",
            f"Prompt: {run.prompt}",
        ]
        if run.details:
            lines.append(f"Details: {run.details}")
        if run.tools:
            lines.append(f"Tools: {', '.join(run.tools)}")
        if run.spawned_by_run_id:
            lines.append(f"Spawned by: {run.spawned_by_run_id}")
        if run.child_run_ids:
            lines.append(f"Children: {', '.join(run.child_run_ids)}")
        if run.dependency_run_ids:
            lines.append(f"Depends on: {', '.join(run.dependency_run_ids)}")
        if run.dependency_policies:
            rendered = ", ".join(f"{dep}:{policy}" for dep, policy in sorted(run.dependency_policies.items()))
            lines.append(f"Dependency policies: {rendered}")
        if run.aggregate_status:
            lines.append(f"Aggregate status: {run.aggregate_status}")
        lines.append(f"Priority: {run.priority}")
        lines.append(f"Retry policy: {run.retry_policy} ({run.retry_count}/{run.max_retries})")
        if run.workflow_id:
            lines.append(f"Workflow: {run.workflow_id}")
        if run.workflow_node_id:
            lines.append(f"Workflow node: {run.workflow_node_id}")
        if run.parent_run_id:
            lines.append(f"Resumed from: {run.parent_run_id}")
        if run.resume_count:
            lines.append(f"Resume count: {run.resume_count}")
        if run.error:
            lines.append(f"Error: {run.error}")
        if run.progress:
            lines.append("Recent progress:")
            for item in run.progress[-5:]:
                lines.append(f"  - {item}")
        return "\n".join(lines)

    def subagent_result(run_id: str) -> str:
        run = _get_manager().get(run_id)
        if not run:
            return f"Sub-agent '{run_id}' not found."
        if run.status in {"pending", "running"}:
            return f"Sub-agent '{run_id}' is still {run.status}."
        if run.status == "interrupted":
            return f"Sub-agent '{run_id}' was interrupted.\n{run.error or 'Process restarted before it finished.'}"
        if run.status == "cancelled":
            return f"Sub-agent '{run_id}' was cancelled.\n{run.error or 'Cancelled by request.'}"
        if run.error:
            return f"Sub-agent '{run_id}' failed.\n{run.error}"
        return run.result or f"Sub-agent '{run_id}' completed with no result."

    def subagent_list() -> str:
        manager = _get_manager()
        runs = manager.list()
        if not runs:
            return "No sub-agent runs."
        summary = manager.scheduler_summary()
        lines = [
            f"Sub-agent runs ({len(runs)}):",
            f"Scheduler: pending={summary['pending']} running={summary['running']} claimed={summary['claimed']} max_concurrency={summary['max_concurrency']}",
        ]
        for run in runs[:20]:
            detail = f" :: {run.details}" if run.details else ""
            lines.append(f"  {run.run_id} [{run.status}] p={run.priority} retry={run.retry_count}/{run.max_retries} {run.prompt[:80]}{detail}")
        return "\n".join(lines)

    def subagent_progress(run_id: str) -> str:
        run = _get_manager().get(run_id)
        if not run:
            return f"Sub-agent '{run_id}' not found."
        if not run.progress:
            return f"No progress recorded yet for '{run_id}'."
        lines = [f"Progress for {run.run_id} ({run.status}):"]
        for item in run.progress:
            lines.append(f"  - {item}")
        return "\n".join(lines)

    def subagent_graph(run_id: str = "") -> str:
        manager = _get_manager()
        if run_id:
            runs = [manager.get(run_id)]
            runs = [run for run in runs if run is not None]
        else:
            runs = manager.list()[:20]
        if not runs:
            return "No sub-agent graph data."
        summary = manager.scheduler_summary()
        lines = [
            "Sub-agent graph:",
            f"Scheduler: pending={summary['pending']} running={summary['running']} claimed={summary['claimed']} max_concurrency={summary['max_concurrency']}",
        ]
        for run in runs:
            child_suffix = f" children={', '.join(run.child_run_ids)}" if run.child_run_ids else ""
            dep_suffix = f" depends_on={', '.join(run.dependency_run_ids)}" if run.dependency_run_ids else ""
            policy_suffix = ""
            if run.dependency_policies:
                policy_suffix = " dep_policy=" + ",".join(
                    f"{dep}:{policy}" for dep, policy in sorted(run.dependency_policies.items())
                )
            aggregate_suffix = f" aggregate={run.aggregate_status}" if run.aggregate_status else ""
            parent_suffix = f" spawned_by={run.spawned_by_run_id}" if run.spawned_by_run_id else ""
            resume_suffix = f" resumed_from={run.parent_run_id}" if run.parent_run_id else ""
            retry_suffix = f" retry={run.retry_count}/{run.max_retries}:{run.retry_policy}"
            workflow_suffix = f" workflow={run.workflow_id}:{run.workflow_node_id}" if run.workflow_id or run.workflow_node_id else ""
            lines.append(f"  {run.run_id} [{run.status}] p={run.priority}{aggregate_suffix}{parent_suffix}{resume_suffix}{child_suffix}{dep_suffix}{policy_suffix}{retry_suffix}{workflow_suffix}")
        return "\n".join(lines)

    def workflow_list() -> str:
        manager = _get_manager()
        workflows = manager.list_workflows()
        if not workflows:
            return "No workflows."
        lines = [f"Workflows ({len(workflows)}):"]
        for workflow in workflows[:20]:
            summary = manager.workflow_status_summary(workflow.workflow_id) or {}
            name = workflow.name or workflow.workflow_id
            lines.append(
                f"  {workflow.workflow_id} [{summary.get('aggregate_status', 'unknown')}] {name} nodes={len(workflow.node_run_ids)}"
            )
        return "\n".join(lines)

    def workflow_status(workflow_id: str) -> str:
        manager = _get_manager()
        summary = manager.workflow_status_summary(workflow_id)
        if not summary:
            return f"Workflow '{workflow_id}' not found."
        lines = [
            f"{summary['workflow_id']} [{summary['aggregate_status']}] {summary.get('name') or '(unnamed)'}",
            f"Revision: {summary.get('revision', 0)}",
            f"Created: {summary['created_at']}",
            f"Updated: {summary['updated_at']}",
            f"Counts: {json.dumps(summary['counts'], ensure_ascii=False, sort_keys=True)}",
            f"Snapshots: {summary.get('snapshot_count', 0)}",
            "Nodes:",
        ]
        if summary.get("disabled_node_ids"):
            lines.insert(4, f"Disabled nodes: {', '.join(summary['disabled_node_ids'])}")
        if summary.get("removed_node_ids"):
            lines.insert(5 if summary.get("disabled_node_ids") else 4, f"Removed nodes: {', '.join(summary['removed_node_ids'])}")
        for node_id, run_id in sorted(summary["node_run_ids"].items()):
            run = manager.get(run_id)
            status = run.status if run else "missing"
            lines.append(f"  - {node_id}: {run_id} [{status}]")
        return "\n".join(lines)

    def workflow_cancel(workflow_id: str) -> str:
        manager = _get_manager()
        if not manager.cancel_workflow(workflow_id):
            return f"Workflow '{workflow_id}' not found."
        return f"Cancellation requested for workflow '{workflow_id}'."

    def workflow_resume(workflow_id: str) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        resumed: List[str] = []
        skipped: List[str] = []
        for node_id, run_id in workflow.node_run_ids.items():
            run = manager.get(run_id)
            if not run:
                skipped.append(node_id)
                continue
            if run.status not in {"interrupted", "failed", "cancelled"}:
                skipped.append(node_id)
                continue
            response = resume_subagent(run_id, True, "")
            if "Run ID: " in response:
                resumed_run_id = response.split("Run ID: ", 1)[1].splitlines()[0].strip()
                workflow.node_run_ids[node_id] = resumed_run_id
                resumed.append(f"{node_id}->{resumed_run_id}")
            else:
                skipped.append(node_id)
        with manager._lock:
            workflow.updated_at = datetime.now(timezone.utc).isoformat()
            manager._record_workflow_revision_locked(workflow, "workflow_resumed", resumed=resumed, skipped=skipped)
            manager._save_locked()
        manager.append_workflow_event(workflow_id, "workflow_resumed", f"Workflow resumed: {workflow_id}", resumed=resumed, skipped=skipped)
        if not resumed:
            return f"No resumable workflow runs in '{workflow_id}'."
        suffix = f"\nSkipped: {', '.join(skipped)}" if skipped else ""
        return f"Workflow '{workflow_id}' resumed.\n" + "\n".join(f"  {item}" for item in resumed) + suffix

    def workflow_add_node(
        workflow_id: str,
        node_id: str,
        prompt: str,
        depends_on_node_ids: Optional[List[str]] = None,
        dependency_policies_json: str = "",
        tools: Optional[List[str]] = None,
        extra_instructions: str = "",
        include_parent_history: bool = False,
        async_mode: bool = True,
        allowed_command_prefixes: Optional[List[str]] = None,
        denied_command_prefixes: Optional[List[str]] = None,
        workspace_root: Optional[str] = None,
        workspace_required: Optional[bool] = None,
        model_override: str = "",
        max_tool_iterations: Optional[int] = None,
        task_subject: str = "",
        priority: int = 0,
        retry_policy: str = "never",
        max_retries: int = 0,
    ) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        normalized_node_id = (node_id or "").strip()
        if not normalized_node_id:
            return "Error: node_id is required."
        if normalized_node_id in workflow.node_run_ids:
            return f"Error: workflow node '{normalized_node_id}' already exists."
        dependency_policies: Dict[str, str] = {}
        if dependency_policies_json:
            try:
                loaded = json.loads(dependency_policies_json)
                if isinstance(loaded, dict):
                    dependency_policies = {str(k): str(v) for k, v in loaded.items()}
            except json.JSONDecodeError as exc:
                return f"Error: dependency_policies_json must be valid JSON ({exc})"
        depends_on_run_ids: List[str] = []
        for dep_node_id in depends_on_node_ids or []:
            dep_name = str(dep_node_id).strip()
            run_id = workflow.node_run_ids.get(dep_name)
            if not run_id:
                return f"Error: dependency node '{dep_name}' not found in workflow '{workflow_id}'."
            depends_on_run_ids.append(run_id)
        translated_policies = {
            workflow.node_run_ids[str(dep_node_id).strip()]: str(policy)
            for dep_node_id, policy in dependency_policies.items()
            if workflow.node_run_ids.get(str(dep_node_id).strip())
        }
        response = run_subagent(
            prompt=prompt,
            tools=tools,
            extra_instructions=extra_instructions,
            include_parent_history=include_parent_history,
            async_mode=async_mode,
            allowed_command_prefixes=allowed_command_prefixes,
            denied_command_prefixes=denied_command_prefixes,
            workspace_root=workspace_root,
            workspace_required=workspace_required,
            model_override=model_override,
            max_tool_iterations=max_tool_iterations,
            task_subject=task_subject or workflow.name or normalized_node_id,
            depends_on_run_ids=depends_on_run_ids,
            dependency_policies_json=json.dumps(translated_policies),
            priority=priority,
            retry_policy=retry_policy,
            max_retries=max_retries,
            workflow_id=workflow_id,
            workflow_node_id=normalized_node_id,
        )
        if "Run ID: " not in response:
            return response
        run_id = response.split("Run ID: ", 1)[1].splitlines()[0].strip()
        with manager._lock:
            workflow.removed_node_ids = [item for item in workflow.removed_node_ids if item != normalized_node_id]
            manager._record_workflow_revision_locked(workflow, "node_added", workflow_node_id=normalized_node_id, run_id=run_id)
            manager._save_locked()
        manager.append_workflow_event(
            workflow_id,
            "node_added",
            f"Added node {normalized_node_id}",
            workflow_node_id=normalized_node_id,
            run_id=run_id,
        )
        return f"Workflow node added.\nWorkflow: {workflow_id}\nNode: {normalized_node_id}\nRun ID: {run_id}"

    def workflow_retry_node(workflow_id: str, node_id: str) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        run_id = workflow.node_run_ids.get((node_id or "").strip())
        if not run_id:
            return f"Workflow node '{node_id}' not found in '{workflow_id}'."
        response = resume_subagent(run_id, True, "")
        if "Run ID: " not in response:
            return response
        resumed_run_id = response.split("Run ID: ", 1)[1].splitlines()[0].strip()
        with manager._lock:
            workflow.node_run_ids[(node_id or "").strip()] = resumed_run_id
            manager._record_workflow_revision_locked(workflow, "node_retried", workflow_node_id=(node_id or "").strip(), run_id=resumed_run_id)
            manager._save_locked()
        manager.append_workflow_event(
            workflow_id,
            "node_retried",
            f"Retried node {node_id}",
            workflow_node_id=(node_id or "").strip(),
            run_id=resumed_run_id,
        )
        return f"Workflow node retried.\nWorkflow: {workflow_id}\nNode: {node_id}\nRun ID: {resumed_run_id}"

    def workflow_update_edge_policy(
        workflow_id: str,
        node_id: str,
        dependency_node_id: str,
        policy: str,
    ) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        node_run_id = workflow.node_run_ids.get((node_id or "").strip())
        dependency_run_id = workflow.node_run_ids.get((dependency_node_id or "").strip())
        if not node_run_id or not dependency_run_id:
            return f"Workflow edge '{dependency_node_id} -> {node_id}' not found in '{workflow_id}'."
        normalized_policy = (policy or "").strip()
        if normalized_policy not in SubagentManager.DEPENDENCY_POLICIES:
            return "Error: policy must be one of block or ignore_failure."
        with manager._lock:
            run = manager._runs.get(node_run_id)
            if not run:
                return f"Workflow node '{node_id}' run is missing."
            if dependency_run_id not in run.dependency_run_ids:
                return f"Workflow edge '{dependency_node_id} -> {node_id}' not found in '{workflow_id}'."
            run.dependency_policies[dependency_run_id] = normalized_policy
            run.execution_config["dependency_policies"] = dict(run.dependency_policies)
            manager._record_workflow_revision_locked(
                workflow,
                "edge_policy_updated",
                workflow_node_id=(node_id or "").strip(),
                dependency_node_id=(dependency_node_id or "").strip(),
                policy=normalized_policy,
            )
            manager._save_locked()
        manager.append_workflow_event(
            workflow_id,
            "edge_policy_updated",
            f"Updated edge policy {dependency_node_id} -> {node_id} to {normalized_policy}",
            workflow_node_id=(node_id or "").strip(),
            dependency_node_id=(dependency_node_id or "").strip(),
            policy=normalized_policy,
        )
        return f"Updated edge policy for {dependency_node_id} -> {node_id} to {normalized_policy}."

    def workflow_set_priority(workflow_id: str, node_id: str, priority: int) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        run_id = workflow.node_run_ids.get((node_id or "").strip())
        if not run_id:
            return f"Workflow node '{node_id}' not found in '{workflow_id}'."
        with manager._lock:
            run = manager._runs.get(run_id)
            if not run:
                return f"Workflow node '{node_id}' run is missing."
            run.priority = int(priority)
            run.execution_config["priority"] = int(priority)
            manager._record_workflow_revision_locked(
                workflow,
                "node_priority_updated",
                workflow_node_id=(node_id or "").strip(),
                priority=int(priority),
            )
            manager._save_locked()
        manager.append_workflow_event(
            workflow_id,
            "node_priority_updated",
            f"Updated node {node_id} priority to {int(priority)}",
            workflow_node_id=(node_id or "").strip(),
            priority=int(priority),
        )
        return f"Workflow node '{node_id}' priority set to {int(priority)}."

    def workflow_disable_node(workflow_id: str, node_id: str) -> str:
        manager = _get_manager()
        _, message = manager.workflow_disable_node(workflow_id, node_id)
        return message

    def workflow_remove_node(workflow_id: str, node_id: str) -> str:
        manager = _get_manager()
        _, message = manager.workflow_remove_node(workflow_id, node_id)
        return message

    def workflow_retry_branch(workflow_id: str, node_id: str) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        normalized_node_id = (node_id or "").strip()
        root_run_id = workflow.node_run_ids.get(normalized_node_id)
        if not root_run_id:
            return f"Workflow node '{node_id}' not found in '{workflow_id}'."
        branch_node_ids: List[str] = []
        with manager._lock:
            pending = [normalized_node_id]
            seen: set[str] = set()
            while pending:
                current_node_id = pending.pop()
                if current_node_id in seen:
                    continue
                seen.add(current_node_id)
                branch_node_ids.append(current_node_id)
                current_run_id = workflow.node_run_ids.get(current_node_id)
                for other_node_id, other_run_id in workflow.node_run_ids.items():
                    if other_node_id in seen:
                        continue
                    other_run = manager._runs.get(other_run_id)
                    if other_run and current_run_id and current_run_id in other_run.dependency_run_ids:
                        pending.append(other_node_id)
        retried: List[str] = []
        skipped: List[str] = []
        for current_node_id in branch_node_ids:
            current_run_id = workflow.node_run_ids.get(current_node_id)
            current_run = manager.get(current_run_id) if current_run_id else None
            if not current_run or current_run.status not in {"failed", "interrupted", "cancelled"}:
                skipped.append(current_node_id)
                continue
            response = resume_subagent(current_run_id, True, "")
            if "Run ID: " not in response:
                skipped.append(current_node_id)
                continue
            resumed_run_id = response.split("Run ID: ", 1)[1].splitlines()[0].strip()
            with manager._lock:
                workflow.node_run_ids[current_node_id] = resumed_run_id
                for other_node_id, other_run_id in workflow.node_run_ids.items():
                    if other_node_id == current_node_id:
                        continue
                    other_run = manager._runs.get(other_run_id)
                    if not other_run or current_run_id not in other_run.dependency_run_ids:
                        continue
                    other_run.dependency_run_ids = [
                        resumed_run_id if dep_id == current_run_id else dep_id
                        for dep_id in other_run.dependency_run_ids
                    ]
                    if current_run_id in other_run.dependency_policies:
                        other_run.dependency_policies[resumed_run_id] = other_run.dependency_policies.pop(current_run_id)
                        other_run.execution_config["dependency_policies"] = dict(other_run.dependency_policies)
                    other_run.execution_config["depends_on_run_ids"] = list(other_run.dependency_run_ids)
                manager._record_workflow_revision_locked(
                    workflow,
                    "branch_retried_node",
                    workflow_node_id=current_node_id,
                    prior_run_id=current_run_id,
                    run_id=resumed_run_id,
                )
                manager._save_locked()
            retried.append(f"{current_node_id}->{resumed_run_id}")
        manager.append_workflow_event(
            workflow_id,
            "branch_retried",
            f"Retried branch rooted at {normalized_node_id}",
            workflow_node_id=normalized_node_id,
            retried=retried,
            skipped=skipped,
        )
        if not retried:
            return f"No resumable workflow runs in branch '{normalized_node_id}' for '{workflow_id}'."
        suffix = f"\nSkipped: {', '.join(skipped)}" if skipped else ""
        return (
            f"Workflow branch retried.\nWorkflow: {workflow_id}\nRoot node: {normalized_node_id}\n"
            + "\n".join(f"  {item}" for item in retried)
            + suffix
        )

    def workflow_events(workflow_id: str) -> str:
        manager = _get_manager()
        workflow = manager.get_workflow(workflow_id)
        if not workflow:
            return f"Workflow '{workflow_id}' not found."
        events = manager.workflow_events(workflow_id)
        if not events:
            return f"No events for workflow '{workflow_id}'."
        lines = [f"{workflow_id} events ({len(events)}):"]
        for event in events[-25:]:
            suffix = ""
            if event.get("workflow_node_id"):
                suffix += f" node={event['workflow_node_id']}"
            if event.get("run_id"):
                suffix += f" run={event['run_id']}"
            lines.append(f"  [{event['timestamp']}] {event['type']}{suffix}: {event['message']}")
        return "\n".join(lines)

    def workflow_enable_node(workflow_id: str, node_id: str) -> str:
        manager = _get_manager()
        _, message = manager.workflow_enable_node(workflow_id, node_id)
        return message

    def workflow_rewire_dependency(
        workflow_id: str,
        node_id: str,
        dependency_node_id: str,
        action: str,
        policy: str = "block",
    ) -> str:
        manager = _get_manager()
        _, message = manager.workflow_rewire_dependency(workflow_id, node_id, dependency_node_id, action, policy)
        return message

    def workflow_snapshot(workflow_id: str, label: str = "") -> str:
        manager = _get_manager()
        snapshot = manager.workflow_snapshot(workflow_id, label)
        if not snapshot:
            return f"Workflow '{workflow_id}' not found."
        manager.append_workflow_event(
            workflow_id,
            "workflow_snapshot",
            f"Created workflow snapshot {snapshot['snapshot_id']}",
            snapshot_id=snapshot["snapshot_id"],
            label=snapshot.get("label", ""),
        )
        return (
            "Workflow snapshot created.\n"
            f"Workflow: {workflow_id}\n"
            f"Snapshot ID: {snapshot['snapshot_id']}\n"
            f"Revision: {snapshot['spec'].get('revision', 0)}"
        )

    def workflow_export(workflow_id: str, snapshot_id: str = "") -> str:
        manager = _get_manager()
        exported = manager.workflow_export(workflow_id, snapshot_id)
        if not exported:
            return f"Workflow '{workflow_id}' not found."
        if exported.get("error"):
            return exported["error"]
        return json.dumps(exported, indent=2, ensure_ascii=True)

    _get_manager().set_launcher(_start_run_thread)

    agent.register_tool(
        "run_subagent",
        run_subagent,
        {
            "name": "run_subagent",
            "description": (
                "Run a focused child agent with a filtered toolset. "
                "Can run synchronously or in the background."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Task for the child agent"},
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tool names to expose to the child agent",
                    },
                    "extra_instructions": {
                        "type": "string",
                        "description": "Extra system guidance for the child agent",
                    },
                    "include_parent_history": {
                        "type": "boolean",
                        "description": "Whether to copy the current conversation history into the child agent",
                    },
                    "async_mode": {
                        "type": "boolean",
                        "description": "Run in the background and return a run ID (default true)",
                    },
                    "allowed_command_prefixes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional terminal prefixes the child agent is allowed to run",
                    },
                    "denied_command_prefixes": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional terminal prefixes the child agent is denied from running",
                    },
                    "workspace_root": {
                        "type": "string",
                        "description": "Optional workspace root override for child file tools",
                    },
                    "workspace_required": {
                        "type": "boolean",
                        "description": "Whether child file access should fail closed without a workspace root",
                    },
                    "model_override": {
                        "type": "string",
                        "description": "Optional provider model override for the child agent",
                    },
                    "max_tool_iterations": {
                        "type": "integer",
                        "description": "Optional max tool iterations for the child agent",
                    },
                    "task_subject": {
                        "type": "string",
                        "description": "Optional task title to update while the child agent runs",
                    },
                    "spawned_by_run_id": {
                        "type": "string",
                        "description": "Optional parent run ID for graph tracking",
                    },
                    "depends_on_run_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional prerequisite sub-agent runs that must complete first",
                    },
                    "dependency_policies_json": {
                        "type": "string",
                        "description": "Optional JSON object mapping dependency run IDs to edge policies: block or ignore_failure",
                    },
                    "priority": {
                        "type": "integer",
                        "description": "Optional scheduling priority. Higher runs launch first.",
                    },
                    "retry_policy": {
                        "type": "string",
                        "enum": ["never", "on_failure"],
                        "description": "Optional retry behavior for failed runs.",
                    },
                    "max_retries": {
                        "type": "integer",
                        "description": "Optional retry limit when retry_policy is on_failure.",
                    },
                    "workflow_id": {
                        "type": "string",
                        "description": "Optional workflow identifier for grouped DAG runs.",
                    },
                    "workflow_node_id": {
                        "type": "string",
                        "description": "Optional node identifier within a workflow.",
                    },
                },
                "required": ["prompt"],
            },
        },
    )
    agent.register_tool(
        "submit_workflow",
        submit_workflow,
        {
            "name": "submit_workflow",
            "description": "Submit a workflow DAG as JSON and create all queued sub-agent runs with dependency policies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_json": {
                        "type": "string",
                        "description": "JSON object with a nodes array. Each node needs id and prompt, and may include depends_on, dependency_policies, tools, priority, retry_policy, and max_retries.",
                    },
                    "workflow_name": {
                        "type": "string",
                        "description": "Optional human-friendly workflow name.",
                    },
                },
                "required": ["workflow_json"],
            },
        },
    )
    agent.register_tool(
        "resume_subagent",
        resume_subagent,
        {
            "name": "resume_subagent",
            "description": "Resume an interrupted, failed, or cancelled child agent run from its saved execution config.",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string", "description": "Sub-agent run ID"},
                    "async_mode": {"type": "boolean", "description": "Resume in the background (default true)"},
                    "task_subject": {"type": "string", "description": "Optional replacement task title for the resumed run"},
                },
                "required": ["run_id"],
            },
        },
    )
    agent.register_tool(
        "cancel_subagent",
        cancel_subagent,
        {
            "name": "cancel_subagent",
            "description": "Request cancellation for a running child agent run.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Sub-agent run ID"}},
                "required": ["run_id"],
            },
        },
    )
    agent.register_tool(
        "subagent_status",
        subagent_status,
        {
            "name": "subagent_status",
            "description": "Check the status of a child agent run.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Sub-agent run ID"}},
                "required": ["run_id"],
            },
        },
    )
    agent.register_tool(
        "subagent_result",
        subagent_result,
        {
            "name": "subagent_result",
            "description": "Fetch the final result of a completed child agent run.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Sub-agent run ID"}},
                "required": ["run_id"],
            },
        },
    )
    agent.register_tool(
        "subagent_list",
        subagent_list,
        {
            "name": "subagent_list",
            "description": "List recent child agent runs.",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    agent.register_tool(
        "subagent_progress",
        subagent_progress,
        {
            "name": "subagent_progress",
            "description": "Get progress updates for a child agent run.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Sub-agent run ID"}},
                "required": ["run_id"],
            },
        },
    )
    agent.register_tool(
        "subagent_graph",
        subagent_graph,
        {
            "name": "subagent_graph",
            "description": "Show parent-child and dependency relationships for sub-agent runs.",
            "parameters": {
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "Optional root run ID"}},
            },
        },
    )
    agent.register_tool(
        "workflow_list",
        workflow_list,
        {
            "name": "workflow_list",
            "description": "List registered workflows and their aggregate status.",
            "parameters": {"type": "object", "properties": {}},
        },
    )
    agent.register_tool(
        "workflow_status",
        workflow_status,
        {
            "name": "workflow_status",
            "description": "Show workflow-level status and node/run mapping.",
            "parameters": {
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "description": "Workflow ID"}},
                "required": ["workflow_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_cancel",
        workflow_cancel,
        {
            "name": "workflow_cancel",
            "description": "Cancel all runnable or pending nodes in a workflow.",
            "parameters": {
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "description": "Workflow ID"}},
                "required": ["workflow_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_resume",
        workflow_resume,
        {
            "name": "workflow_resume",
            "description": "Resume resumable nodes in a workflow and refresh the node mapping.",
            "parameters": {
                "type": "object",
                "properties": {"workflow_id": {"type": "string", "description": "Workflow ID"}},
                "required": ["workflow_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_add_node",
        workflow_add_node,
        {
            "name": "workflow_add_node",
            "description": "Append a new node to an existing workflow DAG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "New workflow node ID"},
                    "prompt": {"type": "string", "description": "Task for the new node"},
                    "depends_on_node_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional workflow node IDs that this node depends on",
                    },
                    "dependency_policies_json": {
                        "type": "string",
                        "description": "Optional JSON object mapping dependency node IDs to edge policies",
                    },
                    "tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of tool names to expose to the node",
                    },
                    "extra_instructions": {"type": "string"},
                    "include_parent_history": {"type": "boolean"},
                    "async_mode": {"type": "boolean"},
                    "allowed_command_prefixes": {"type": "array", "items": {"type": "string"}},
                    "denied_command_prefixes": {"type": "array", "items": {"type": "string"}},
                    "workspace_root": {"type": "string"},
                    "workspace_required": {"type": "boolean"},
                    "model_override": {"type": "string"},
                    "max_tool_iterations": {"type": "integer"},
                    "task_subject": {"type": "string"},
                    "priority": {"type": "integer"},
                    "retry_policy": {"type": "string", "enum": ["never", "on_failure"]},
                    "max_retries": {"type": "integer"},
                },
                "required": ["workflow_id", "node_id", "prompt"],
            },
        },
    )
    agent.register_tool(
        "workflow_retry_node",
        workflow_retry_node,
        {
            "name": "workflow_retry_node",
            "description": "Retry one workflow node by resuming its current run and remapping the workflow node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Workflow node ID"},
                },
                "required": ["workflow_id", "node_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_update_edge_policy",
        workflow_update_edge_policy,
        {
            "name": "workflow_update_edge_policy",
            "description": "Update the dependency policy for one workflow edge.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Downstream workflow node ID"},
                    "dependency_node_id": {"type": "string", "description": "Upstream dependency workflow node ID"},
                    "policy": {"type": "string", "enum": ["block", "ignore_failure"]},
                },
                "required": ["workflow_id", "node_id", "dependency_node_id", "policy"],
            },
        },
    )
    agent.register_tool(
        "workflow_set_priority",
        workflow_set_priority,
        {
            "name": "workflow_set_priority",
            "description": "Set the scheduling priority for one workflow node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Workflow node ID"},
                    "priority": {"type": "integer", "description": "New scheduling priority"},
                },
                "required": ["workflow_id", "node_id", "priority"],
            },
        },
    )
    agent.register_tool(
        "workflow_disable_node",
        workflow_disable_node,
        {
            "name": "workflow_disable_node",
            "description": "Disable a pending workflow node so the scheduler will not launch it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Workflow node ID"},
                },
                "required": ["workflow_id", "node_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_enable_node",
        workflow_enable_node,
        {
            "name": "workflow_enable_node",
            "description": "Re-enable a previously disabled pending workflow node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Workflow node ID"},
                },
                "required": ["workflow_id", "node_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_remove_node",
        workflow_remove_node,
        {
            "name": "workflow_remove_node",
            "description": "Remove a pending workflow node that has no downstream dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Workflow node ID"},
                },
                "required": ["workflow_id", "node_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_rewire_dependency",
        workflow_rewire_dependency,
        {
            "name": "workflow_rewire_dependency",
            "description": "Add or remove a dependency edge between workflow nodes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Downstream workflow node ID"},
                    "dependency_node_id": {"type": "string", "description": "Upstream workflow node ID"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                    "policy": {"type": "string", "enum": ["block", "ignore_failure"]},
                },
                "required": ["workflow_id", "node_id", "dependency_node_id", "action"],
            },
        },
    )
    agent.register_tool(
        "workflow_retry_branch",
        workflow_retry_branch,
        {
            "name": "workflow_retry_branch",
            "description": "Retry a failed branch rooted at one workflow node and update downstream dependencies.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "node_id": {"type": "string", "description": "Root workflow node ID"},
                },
                "required": ["workflow_id", "node_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_snapshot",
        workflow_snapshot,
        {
            "name": "workflow_snapshot",
            "description": "Persist a named snapshot of the current workflow spec and state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "label": {"type": "string", "description": "Optional snapshot label"},
                },
                "required": ["workflow_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_export",
        workflow_export,
        {
            "name": "workflow_export",
            "description": "Export the current workflow spec or a saved snapshot as JSON.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                    "snapshot_id": {"type": "string", "description": "Optional snapshot ID"},
                },
                "required": ["workflow_id"],
            },
        },
    )
    agent.register_tool(
        "workflow_events",
        workflow_events,
        {
            "name": "workflow_events",
            "description": "Show recent workflow-level events and node transitions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "workflow_id": {"type": "string", "description": "Workflow ID"},
                },
                "required": ["workflow_id"],
            },
        },
    )
