"""
Platform Presence Tools
========================
System notifications, clipboard access, and tray status management.
Requires: pip install plyer pyperclip
"""

import logging

log = logging.getLogger("solstice.tools.presence")

_current_status = "idle"


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def presence_notify(title: str, message: str) -> str:
    """Show a cross-platform system notification."""
    try:
        from plyer import notification
    except ImportError:
        return "Error: Notifications require: pip install plyer"

    try:
        notification.notify(
            title=title,
            message=message,
            app_name="Solstice Agent",
            timeout=10,
        )
        return f"Notification sent: {title}"
    except Exception as e:
        return f"Error sending notification: {e}"


def presence_set_status(status: str) -> str:
    """Update the agent status indicator."""
    global _current_status
    valid = ("active", "idle", "busy", "listening")
    if status not in valid:
        return f"Error: Status must be one of: {', '.join(valid)}"
    _current_status = status
    log.info(f"Status updated: {status}")
    return f"Status set to: {status}"


def presence_get_clipboard() -> str:
    """Read the system clipboard text content."""
    try:
        import pyperclip
    except ImportError:
        return "Error: Clipboard access requires: pip install pyperclip"

    try:
        content = pyperclip.paste()
        if not content:
            return "(clipboard is empty)"
        return content
    except Exception as e:
        return f"Error reading clipboard: {e}"


def presence_set_clipboard(text: str) -> str:
    """Write text to the system clipboard."""
    try:
        import pyperclip
    except ImportError:
        return "Error: Clipboard access requires: pip install pyperclip"

    try:
        pyperclip.copy(text)
        preview = text[:100] + "..." if len(text) > 100 else text
        return f"Copied to clipboard ({len(text)} chars): {preview}"
    except Exception as e:
        return f"Error writing clipboard: {e}"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "presence_notify": {
        "name": "presence_notify",
        "description": (
            "Show a system notification popup. Cross-platform: "
            "Windows toast, macOS notification center, Linux notify-send."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Notification title"},
                "message": {"type": "string", "description": "Notification body text"},
            },
            "required": ["title", "message"],
        },
    },
    "presence_set_status": {
        "name": "presence_set_status",
        "description": "Update the agent status indicator (active, idle, busy, listening).",
        "parameters": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "description": "Status: 'active', 'idle', 'busy', 'listening'",
                },
            },
            "required": ["status"],
        },
    },
    "presence_get_clipboard": {
        "name": "presence_get_clipboard",
        "description": "Read the current system clipboard text content.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
    "presence_set_clipboard": {
        "name": "presence_set_clipboard",
        "description": "Write text to the system clipboard.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to copy to clipboard"},
            },
            "required": ["text"],
        },
    },
}


def register_presence_tools(registry):
    """Register platform presence tools."""
    registry.register("presence_notify", presence_notify, _SCHEMAS["presence_notify"])
    registry.register("presence_set_status", presence_set_status, _SCHEMAS["presence_set_status"])
    registry.register("presence_get_clipboard", presence_get_clipboard, _SCHEMAS["presence_get_clipboard"])
    registry.register("presence_set_clipboard", presence_set_clipboard, _SCHEMAS["presence_set_clipboard"])
