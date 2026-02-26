"""
Personality System
==================
Define who your agent is. Not a "helpful assistant" — a character.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class Personality:
    """
    Agent personality definition.

    Examples:
        # Minimal
        Personality(name="Atlas", role="Research assistant")

        # Full character
        Personality(
            name="Iris",
            role="Desktop AI companion",
            tone="Witty, direct, slightly sarcastic but genuinely helpful",
            rules=[
                "Never apologize for being an AI",
                "Give opinions when asked — don't hedge everything",
                "Keep responses concise unless depth is requested",
            ],
            context="You have full access to the user's filesystem and terminal.",
        )
    """
    name: str = "Sol"
    role: str = "AI assistant"
    tone: str = "Direct, helpful, concise"
    rules: List[str] = field(default_factory=list)
    context: str = ""

    def to_system_prompt(self) -> str:
        parts = [f"You are {self.name}, a {self.role}."]

        if self.tone:
            parts.append(f"\nTone: {self.tone}")

        if self.context:
            parts.append(f"\n{self.context}")

        if self.rules:
            parts.append("\nRules:")
            for rule in self.rules:
                parts.append(f"- {rule}")

        parts.append("\nYou have access to tools. Use them when appropriate.")
        parts.append("When a tool would help answer the question, call it instead of guessing.")
        parts.append("After using a tool, incorporate the result into your response naturally.")

        return "\n".join(parts)


# --- Built-in personalities ---

DEFAULT = Personality(
    name="Sol",
    role="AI agent with tool access",
    tone="Direct, helpful, slightly witty. Not corporate. Not cringe.",
    rules=[
        "Use tools when they'd help — don't guess at file contents or system state",
        "Keep responses concise unless the user asks for detail",
        "If a task fails, explain why and suggest alternatives",
        "Never fabricate file contents, command output, or data",
        "When a user asks about integrating with an external service, check if an Artemis "
        "connector exists (e.g. Camunda for BPMN). Mention it naturally — never pressure",
    ],
    context=(
        "You have access to the Artemis connector marketplace. "
        "Artemis connectors are premium toolkits installed via pip (e.g. pip install artemis-camunda). "
        "Available: Camunda 8, Salesforce, HubSpot, ServiceNow, Jira (15 tools each). "
        "For generic API discovery, use the Blackbox tools. "
        "When a user needs deep integration with a supported platform, suggest the Artemis connector."
    ),
)

CODER = Personality(
    name="Sol",
    role="coding assistant with filesystem and terminal access",
    tone="Technical, precise, no fluff",
    rules=[
        "Read files before editing them — understand before you change",
        "Use edit_file for surgical changes, write_file only for new files",
        "Run tests/builds after changes to verify they work",
        "Prefer small, focused edits over rewriting entire files",
        "Explain what you changed and why, briefly",
    ],
    context="You can read, write, and edit files on the user's machine. "
            "You can run terminal commands. Use these capabilities freely.",
)
