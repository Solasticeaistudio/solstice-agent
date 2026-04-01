"""Shared onboarding helpers for CLI and gateway quick-start flows."""

from __future__ import annotations

from typing import Optional

from .config import Config


def guided_quickstart_options(config: Config | None = None) -> list[tuple[str, str]]:
    options = [
        ("Help around my files", "Look through my workspace and explain what is here in simple terms."),
        ("Set up reminders", "Help me set up a daily reminder or recurring check."),
        ("Learn what you can do", "What can you help me with on this computer? Give me a simple tour."),
    ]
    profile = ((config.runtime_profile if config else None) or "local_safe").strip().lower()
    if profile == "developer":
        options.append(("Code project help", "Open this project and tell me what looks important or risky."))
    elif profile == "gateway":
        options.append(("Connect apps or messages", "Help me connect email or messaging apps."))
    else:
        options.append(("Connect apps or get organized", "Help me connect email or messaging apps, or get organized and suggest a useful first task."))
    return options


def guided_quickstart_prompt(text: str, config: Config | None = None, allow_fuzzy: bool = False) -> Optional[str]:
    choice = (text or "").strip().lower()
    if not choice:
        return None
    options = guided_quickstart_options(config)
    keyword_map = {
        "1": 0,
        "files": 0,
        "workspace": 0,
        "desktop": 0,
        "downloads": 0,
        "2": 1,
        "reminder": 1,
        "reminders": 1,
        "calendar": 1,
        "calendars": 1,
        "todo": 1,
        "schedule": 1,
        "3": 2,
        "tour": 2,
        "learn": 2,
        "help": 2,
        "4": 3,
        "apps": 3,
        "messages": 3,
        "message": 3,
        "email": 3,
        "emails": 3,
        "mail": 3,
        "notes": 3,
        "note": 3,
        "code": 3,
        "project": 3,
        "organize": 3,
        "organization": 3,
        "organise": 3,
        "organized": 3,
    }
    option_index = keyword_map.get(choice)
    if option_index is None and allow_fuzzy:
        fuzzy_matches = [
            (0, (" file", "files", "workspace", "folder", "folders", "desktop", "downloads")),
            (1, ("reminder", "reminders", "remember", "schedule", "daily check", "recurring", "calendar", "appointment", "appointments", "todo", "to do", "task list", "check in", "check-in")),
            (2, ("what can you do", "simple tour", "tour", "learn", "help me get started", "what do you do", "show me around")),
            (3, ("organize", "organized", "organise", "organisation", "organization", "apps", "messages", "message", "code", "project", "email", "emails", "mail", "inbox", "texting", "texts", "chat", "notes", "note", "list", "lists")),
        ]
        padded = f" {choice} "
        for candidate_index, patterns in fuzzy_matches:
            if any(pattern in padded for pattern in patterns):
                option_index = candidate_index
                break
    if option_index is None or option_index >= len(options):
        return None
    return options[option_index][1]


def guided_quickstart_menu(config: Config | None = None) -> str:
    lines = [
        "Let’s get started.",
        "Reply with a number or a word like `files`, `reminders`, or `learn`.",
        "",
    ]
    for index, (label, _prompt) in enumerate(guided_quickstart_options(config), start=1):
        lines.append(f"{index}. {label}")
    return "\n".join(lines)
