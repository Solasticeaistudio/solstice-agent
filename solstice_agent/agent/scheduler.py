"""
Cron / Scheduler
================
Persistent scheduled tasks that survive restarts.

Storage: ~/.solstice-agent/cron/jobs.json

Supports:
  - Natural language: "every 6h", "every day at 9am", "every monday"
  - Standard cron: "cron 0 */6 * * *"
  - One-shot: "at 09:00" (runs once, then disables)
"""

import json
import logging
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional

log = logging.getLogger("solstice.scheduler")

_DEFAULT_CRON_DIR = Path.home() / ".solstice-agent" / "cron"
_JOBS_FILE = "jobs.json"


class ScheduleParser:
    """
    Parse natural language and cron schedules into next-run datetimes.

    Supported:
      "every 6h" / "every 30m" / "every 2d"
      "every day at 9am" / "every day at 09:00"
      "every monday" / "every friday at 5pm"
      "at 09:00" / "at 3pm" (one-shot)
      "cron 0 */6 * * *" (standard 5-field)
    """

    @staticmethod
    def next_run(schedule: str, from_time: datetime = None) -> Optional[datetime]:
        now = from_time or datetime.now(timezone.utc)
        schedule = schedule.strip().lower()

        # "every Xh/Xm/Xd"
        interval_match = re.match(
            r'every\s+(\d+)\s*(h|hr|hours?|m|min|minutes?|d|days?)\s*$', schedule
        )
        if interval_match:
            amount = int(interval_match.group(1))
            unit = interval_match.group(2)[0]
            delta = {"h": timedelta(hours=amount), "m": timedelta(minutes=amount),
                     "d": timedelta(days=amount)}[unit]
            return now + delta

        # "every day at HH:MM"
        daily_match = re.match(r'every\s+day\s+at\s+(.+)$', schedule)
        if daily_match:
            target_time = ScheduleParser._parse_time(daily_match.group(1))
            if target_time:
                candidate = now.replace(
                    hour=target_time[0], minute=target_time[1], second=0, microsecond=0
                )
                if candidate <= now:
                    candidate += timedelta(days=1)
                return candidate

        # "every <weekday>" with optional "at HH:MM"
        weekday_match = re.match(
            r'every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
            r'(?:\s+at\s+(.+))?$', schedule
        )
        if weekday_match:
            day_names = {
                "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
                "friday": 4, "saturday": 5, "sunday": 6,
            }
            target_day = day_names[weekday_match.group(1)]
            time_part = weekday_match.group(2)
            target_time = ScheduleParser._parse_time(time_part) if time_part else (9, 0)

            days_ahead = target_day - now.weekday()
            if days_ahead <= 0:
                days_ahead += 7

            candidate = now.replace(
                hour=target_time[0], minute=target_time[1], second=0, microsecond=0
            ) + timedelta(days=days_ahead)
            return candidate

        # "at HH:MM" (one-shot)
        at_match = re.match(r'at\s+(.+)$', schedule)
        if at_match:
            target_time = ScheduleParser._parse_time(at_match.group(1))
            if target_time:
                candidate = now.replace(
                    hour=target_time[0], minute=target_time[1], second=0, microsecond=0
                )
                if candidate <= now:
                    candidate += timedelta(days=1)
                return candidate

        # "cron <5 fields>"
        cron_match = re.match(r'cron\s+(.+)$', schedule)
        if cron_match:
            return ScheduleParser._next_cron(cron_match.group(1), now)

        log.warning(f"Unrecognized schedule format: {schedule}")
        return None

    @staticmethod
    def _parse_time(time_str: str) -> Optional[tuple]:
        """Parse time: '9am', '3:30pm', '09:00', '17:30'."""
        time_str = time_str.strip()

        # "3pm", "9am"
        ampm_match = re.match(r'^(\d{1,2})\s*(am|pm)$', time_str, re.IGNORECASE)
        if ampm_match:
            h = int(ampm_match.group(1))
            is_pm = ampm_match.group(2).lower() == "pm"
            if is_pm and h != 12:
                h += 12
            elif not is_pm and h == 12:
                h = 0
            return (h, 0)

        # "3:30pm"
        ampm_full = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', time_str, re.IGNORECASE)
        if ampm_full:
            h = int(ampm_full.group(1))
            m = int(ampm_full.group(2))
            is_pm = ampm_full.group(3).lower() == "pm"
            if is_pm and h != 12:
                h += 12
            elif not is_pm and h == 12:
                h = 0
            return (h, m)

        # "09:00", "17:30"
        mil = re.match(r'^(\d{1,2}):(\d{2})$', time_str)
        if mil:
            return (int(mil.group(1)), int(mil.group(2)))

        return None

    @staticmethod
    def _next_cron(cron_expr: str, now: datetime) -> Optional[datetime]:
        """Simple 5-field cron: minute hour day month weekday."""
        fields = cron_expr.strip().split()
        if len(fields) != 5:
            return None

        def expand(field_str: str, lo: int, hi: int) -> List[int]:
            if field_str == "*":
                return list(range(lo, hi + 1))
            if "/" in field_str:
                base, step = field_str.split("/", 1)
                start = lo if base == "*" else int(base)
                return list(range(start, hi + 1, int(step)))
            if "-" in field_str:
                a, b = field_str.split("-", 1)
                return list(range(int(a), int(b) + 1))
            if "," in field_str:
                return [int(x) for x in field_str.split(",")]
            return [int(field_str)]

        try:
            valid_min = expand(fields[0], 0, 59)
            valid_hr = expand(fields[1], 0, 23)
            valid_day = expand(fields[2], 1, 31)
            valid_mon = expand(fields[3], 1, 12)
            valid_dow = expand(fields[4], 0, 6)
        except (ValueError, IndexError):
            return None

        candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
        for _ in range(525960):  # ~1 year in minutes
            if (candidate.minute in valid_min and candidate.hour in valid_hr
                    and candidate.day in valid_day and candidate.month in valid_mon
                    and candidate.weekday() in valid_dow):
                return candidate
            candidate += timedelta(minutes=1)

        return None


class Scheduler:
    """
    Background scheduler that checks jobs every 60 seconds.
    Persists to disk. Delivers results to gateway channels or saves to file.
    """

    CHECK_INTERVAL = 60

    def __init__(
        self,
        agent_factory: Callable,
        gateway_manager=None,
        storage_dir: Optional[str] = None,
    ):
        self._agent_factory = agent_factory
        self._gateway = gateway_manager
        self._dir = Path(storage_dir) if storage_dir else _DEFAULT_CRON_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._jobs_path = self._dir / _JOBS_FILE
        self._jobs: Dict[str, Dict] = self._load_jobs()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._results_dir = self._dir / "results"
        self._results_dir.mkdir(parents=True, exist_ok=True)

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="solstice-scheduler"
        )
        self._thread.start()
        log.info(f"Scheduler started with {len(self._jobs)} jobs")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Scheduler stopped")

    def add_job(self, schedule: str, query: str, channel: str = "",
                recipient: str = "") -> Dict:
        next_run = ScheduleParser.next_run(schedule)
        if not next_run:
            raise ValueError(f"Could not parse schedule: '{schedule}'")

        job = {
            "id": f"j-{uuid.uuid4().hex[:8]}",
            "schedule": schedule,
            "query": query,
            "channel": channel,
            "recipient": recipient,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_run": "",
            "next_run": next_run.isoformat(),
            "failures": 0,
            "max_failures": 3,
            "enabled": True,
        }
        self._jobs[job["id"]] = job
        self._save_jobs()
        log.info(f"Added job {job['id']}: '{query}' ({schedule}), next: {next_run}")
        return job

    def remove_job(self, job_id: str) -> bool:
        if job_id in self._jobs:
            del self._jobs[job_id]
            self._save_jobs()
            return True
        return False

    def list_jobs(self) -> List[Dict]:
        return list(self._jobs.values())

    def _loop(self):
        while self._running:
            try:
                self._check_jobs()
            except Exception as e:
                log.error(f"Scheduler loop error: {e}", exc_info=True)
            time.sleep(self.CHECK_INTERVAL)

    def _check_jobs(self):
        now = datetime.now(timezone.utc)
        for job_id, job in list(self._jobs.items()):
            if not job.get("enabled", True):
                continue
            next_run_str = job.get("next_run", "")
            if not next_run_str:
                continue
            try:
                next_run = datetime.fromisoformat(next_run_str)
                if next_run.tzinfo is None:
                    next_run = next_run.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if now >= next_run:
                self._execute_job(job)

    def _execute_job(self, job: Dict):
        job_id = job["id"]
        log.info(f"Executing job {job_id}: {job['query']}")

        try:
            agent = self._agent_factory()
            result = agent.chat(job["query"])
            self._deliver_result(job, result)

            job["last_run"] = datetime.now(timezone.utc).isoformat()
            job["failures"] = 0

            # One-shot jobs disable after execution
            if job["schedule"].strip().lower().startswith("at "):
                job["enabled"] = False
                log.info(f"One-shot job {job_id} completed, now disabled")
            else:
                next_run = ScheduleParser.next_run(job["schedule"])
                job["next_run"] = next_run.isoformat() if next_run else ""

        except Exception as e:
            log.error(f"Job {job_id} failed: {e}")
            job["failures"] = job.get("failures", 0) + 1
            job["last_run"] = datetime.now(timezone.utc).isoformat()

            backoff_minutes = min(2 ** job["failures"], 60)
            job["next_run"] = (
                datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)
            ).isoformat()

            if job["failures"] >= job.get("max_failures", 3):
                job["enabled"] = False
                log.warning(f"Job {job_id} disabled after {job['failures']} failures")

        self._save_jobs()

    def _deliver_result(self, job: Dict, result: str):
        channel = job.get("channel", "")
        recipient = job.get("recipient", "")

        if channel and recipient and self._gateway:
            try:
                from ..gateway.models import ChannelType
                ct = ChannelType(channel)
                self._gateway.send_proactive(ct, recipient, result)
                log.info(f"Delivered job {job['id']} result to {channel}:{recipient}")
            except Exception as e:
                log.error(f"Failed to deliver via {channel}: {e}")
                self._save_result_to_file(job, result)
        else:
            self._save_result_to_file(job, result)

    def _save_result_to_file(self, job: Dict, result: str):
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self._results_dir / f"{job['id']}_{timestamp}.txt"
        content = (
            f"Job: {job['id']}\n"
            f"Query: {job['query']}\n"
            f"Schedule: {job['schedule']}\n"
            f"Executed: {datetime.now(timezone.utc).isoformat()}\n"
            f"{'=' * 40}\n\n"
            f"{result}"
        )
        path.write_text(content, encoding="utf-8")
        log.info(f"Job result saved to {path}")

    def _load_jobs(self) -> Dict[str, Dict]:
        if self._jobs_path.exists():
            try:
                data = json.loads(self._jobs_path.read_text(encoding="utf-8"))
                return {j["id"]: j for j in data}
            except Exception as e:
                log.warning(f"Failed to load jobs: {e}")
        return {}

    def _save_jobs(self):
        self._jobs_path.write_text(
            json.dumps(list(self._jobs.values()), indent=2, default=str),
            encoding="utf-8",
        )


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler: Optional[Scheduler] = None


def get_scheduler() -> Optional[Scheduler]:
    return _scheduler


def init_scheduler(
    agent_factory: Callable,
    gateway_manager=None,
    storage_dir: str = None,
) -> Scheduler:
    """Initialize and start the scheduler."""
    global _scheduler
    _scheduler = Scheduler(agent_factory, gateway_manager, storage_dir)
    _scheduler.start()
    return _scheduler


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

_MAX_CRON_JOBS = 20


def cron_add(schedule: str, query: str, channel: str = "",
             recipient: str = "") -> str:
    """Schedule a recurring task."""
    scheduler = get_scheduler()
    if not scheduler:
        return "Error: Scheduler not initialized. Start with --cron or in server mode."

    # Limit total cron jobs
    if len(scheduler.list_jobs()) >= _MAX_CRON_JOBS:
        return f"Error: Maximum of {_MAX_CRON_JOBS} scheduled jobs reached. Remove existing jobs first."

    try:
        job = scheduler.add_job(schedule, query, channel, recipient)
        return (
            f"Scheduled job {job['id']}:\n"
            f"  Query: {query}\n"
            f"  Schedule: {schedule}\n"
            f"  Next run: {job['next_run'][:19]}\n"
            f"  Delivery: {channel + ':' + recipient if channel else 'saved to file'}"
        )
    except ValueError as e:
        return f"Error: {e}"


def cron_list() -> str:
    """List all scheduled jobs."""
    scheduler = get_scheduler()
    if not scheduler:
        return "Error: Scheduler not initialized."
    jobs = scheduler.list_jobs()
    if not jobs:
        return "No scheduled jobs."

    lines = [f"Scheduled jobs ({len(jobs)}):"]
    for j in jobs:
        status = "ENABLED" if j.get("enabled") else "DISABLED"
        next_run = j.get("next_run", "?")[:19]
        lines.append(
            f"  {j['id']} [{status}] {j['schedule']}\n"
            f"    Query: {j['query'][:60]}\n"
            f"    Next: {next_run} | Failures: {j.get('failures', 0)}"
        )
    return "\n".join(lines)


def cron_remove(job_id: str) -> str:
    """Remove a scheduled job by ID."""
    scheduler = get_scheduler()
    if not scheduler:
        return "Error: Scheduler not initialized."
    if scheduler.remove_job(job_id):
        return f"Removed job {job_id}."
    return f"Job '{job_id}' not found."


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "cron_add": {
        "name": "cron_add",
        "description": (
            "Schedule a recurring task. The agent will run the query on the given schedule "
            "and deliver results to a channel or save them. "
            "Formats: 'every 6h', 'every day at 9am', 'every monday', 'cron 0 */6 * * *'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": "Schedule expression (e.g. 'every 6h', 'every day at 9am', 'cron 0 */6 * * *')",
                },
                "query": {
                    "type": "string",
                    "description": "The question/task to run on each execution",
                },
                "channel": {
                    "type": "string",
                    "description": "Optional delivery channel (telegram, discord, slack, email, etc.)",
                },
                "recipient": {
                    "type": "string",
                    "description": "Optional recipient ID on the channel",
                },
            },
            "required": ["schedule", "query"],
        },
    },
    "cron_list": {
        "name": "cron_list",
        "description": "List all scheduled jobs with their status, next run time, and failure count.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "cron_remove": {
        "name": "cron_remove",
        "description": "Remove a scheduled job by its ID (e.g. 'j-abc123').",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job ID to remove"},
            },
            "required": ["job_id"],
        },
    },
}


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_cron_tools(registry):
    """Register scheduling tools with a ToolRegistry."""
    registry.register("cron_add", cron_add, _SCHEMAS["cron_add"])
    registry.register("cron_list", cron_list, _SCHEMAS["cron_list"])
    registry.register("cron_remove", cron_remove, _SCHEMAS["cron_remove"])
