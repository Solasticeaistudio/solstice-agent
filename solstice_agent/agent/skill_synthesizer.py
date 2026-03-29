"""
Skill Synthesizer
=================
Hermes-style self-improving skill system for Sol.

After completing complex tasks Sol can automatically extract reusable
technique guides and save them as markdown skill files. Skills improve
over time as Sol encounters similar tasks.

Three mechanisms:
  1. Auto-synthesis  — triggered post-task when enough tool calls were used
  2. Explicit save   — agent calls skill_save during a task
  3. Skill evolution — agent calls skill_improve to update an existing skill

Storage:
  ~/.solstice-agent/skills/synthesized/   (auto + explicit saves)
  ~/.solstice-agent/skills/               (user-authored, never overwritten here)
"""

import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.synthesizer")

_SYNTHESIZED_DIR = Path.home() / ".solstice-agent" / "skills" / "synthesized"

# Minimum tool invocations before auto-synthesis is attempted
_DEFAULT_THRESHOLD = 4


@dataclass
class SynthesisResult:
    saved: bool
    skill_name: str
    path: str
    action: str   # "created" | "updated" | "skipped"
    reason: str


class SkillSynthesizer:
    """
    Watches completed agent tasks and synthesizes reusable skill guides.

    Attach to an Agent by passing synthesizer=SkillSynthesizer(...) when
    constructing the Agent. After each chat() call the Agent will pass the
    conversation history and tool call count to maybe_synthesize().
    """

    def __init__(
        self,
        provider,
        skill_loader=None,
        threshold: int = _DEFAULT_THRESHOLD,
    ):
        self.provider = provider
        self.skill_loader = skill_loader
        self.threshold = threshold
        _SYNTHESIZED_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API — called by Agent after each completed task
    # ------------------------------------------------------------------

    def maybe_synthesize(
        self,
        history: List[Dict[str, Any]],
        tool_call_count: int,
    ) -> Optional[SynthesisResult]:
        """
        If the task used enough tool calls, prompt the LLM to decide whether
        a reusable skill should be saved or an existing one updated.
        Returns a SynthesisResult, or None if synthesis was not attempted.
        """
        if tool_call_count < self.threshold:
            log.debug(
                f"Synthesis skipped: {tool_call_count} tool calls < threshold {self.threshold}"
            )
            return None

        log.info(f"Auto-synthesis triggered ({tool_call_count} tool calls)")

        existing = self._list_existing_names()
        prompt = self._build_prompt(history, existing)

        try:
            response = self.provider.chat(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a skill extraction assistant. "
                            "Analyze agent conversations and extract reusable workflows. "
                            "Be concise, specific, and actionable."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                tools=None,
                temperature=0.3,
                max_tokens=1500,
            )
            return self._parse_and_save(response.text)
        except Exception as exc:
            log.warning(f"Auto-synthesis failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_prompt(self, history: List[Dict], existing: List[str]) -> str:
        lines: List[str] = []
        tool_calls: List[str] = []

        for msg in history[-30:]:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user" and isinstance(content, str):
                lines.append(f"USER: {content[:300]}")
            elif role == "assistant":
                if isinstance(content, str):
                    lines.append(f"SOL: {content[:400]}")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                lines.append(f"SOL: {block['text'][:400]}")
                            elif block.get("type") == "tool_use":
                                args_preview = str(block.get("input", ""))[:100]
                                tool_calls.append(
                                    f"  called: {block.get('name', '?')}({args_preview})"
                                )

        conversation = "\n".join(lines)
        tools_used = "\n".join(tool_calls) if tool_calls else "(not recorded in history)"
        existing_str = ", ".join(existing) if existing else "none"

        return f"""Analyze this completed agent task and decide if a reusable skill guide should be saved.

CONVERSATION:
{conversation}

TOOLS USED:
{tools_used}

EXISTING SYNTHESIZED SKILLS: {existing_str}

DECISION RULES:
- Save a NEW skill if: the task involved a non-obvious repeatable workflow (3+ steps, specific tool sequences, error patterns, or domain knowledge).
- UPDATE an existing skill if: the task revealed a better approach, edge case, or correction for one of the existing skills.
- SKIP if: the task was trivial, one-off, or already well-covered by an existing skill.

OUTPUT FORMAT — new skill:
---
SKILL_NAME: <kebab-case>
DESCRIPTION: <one sentence>
TOOLS: <comma-separated tool names>
TRIGGER: <regex to auto-trigger, or leave blank>
---
<Full markdown guide. Be specific: exact commands, flags, sequences, gotchas.>

OUTPUT FORMAT — update:
UPDATE:<existing-skill-name>
---
<Revised full guide content>

OUTPUT FORMAT — skip:
SKIP: <one-line reason>
"""

    def _parse_and_save(self, text: str) -> SynthesisResult:
        text = text.strip()

        if text.upper().startswith("SKIP"):
            reason = text.split(":", 1)[1].strip() if ":" in text else "not worth saving"
            log.info(f"Synthesis skipped by LLM: {reason}")
            return SynthesisResult(
                saved=False, skill_name="", path="", action="skipped", reason=reason
            )

        if text.upper().startswith("UPDATE:"):
            first_line, _, rest = text.partition("\n")
            skill_name = first_line.split(":", 1)[1].strip()
            return self._update_skill(skill_name, rest)

        return self._save_new_from_response(text)

    def _save_new_from_response(self, text: str) -> SynthesisResult:
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
        if not match:
            log.warning("Synthesis output did not match expected format — skipping")
            return SynthesisResult(
                saved=False, skill_name="", path="", action="skipped",
                reason="output format mismatch"
            )

        fm_text = match.group(1)
        body = match.group(2).strip()

        fm: Dict[str, str] = {}
        for line in fm_text.strip().splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                fm[k.strip().upper()] = v.strip()

        raw_name = fm.get("SKILL_NAME", "").lower().replace(" ", "-")
        description = fm.get("DESCRIPTION", "Auto-synthesized skill")
        tools_str = fm.get("TOOLS", "")
        trigger = fm.get("TRIGGER", "")

        if not raw_name or not body:
            return SynthesisResult(
                saved=False, skill_name="", path="", action="skipped",
                reason="empty name or body in LLM output"
            )

        return self._write_file(raw_name, description, tools_str, trigger, body, action="created")

    def _update_skill(self, skill_name: str, new_content: str) -> SynthesisResult:
        path = _SYNTHESIZED_DIR / f"{skill_name}.md"
        if not path.exists():
            # Skill doesn't exist yet — save as new
            return self._write_file(skill_name, f"Updated: {skill_name}", "", "", new_content, "created")

        existing = path.read_text(encoding="utf-8")
        fm_match = re.match(r"^(---\s*\n.*?\n---\s*\n)", existing, re.DOTALL)
        if fm_match:
            updated = fm_match.group(1) + "\n" + new_content.strip() + "\n"
        else:
            updated = existing + f"\n\n<!-- updated {time.strftime('%Y-%m-%dT%H:%M:%S')} -->\n" + new_content.strip() + "\n"

        path.write_text(updated, encoding="utf-8")
        log.info(f"Skill updated: {skill_name}")
        self._reload()
        return SynthesisResult(
            saved=True, skill_name=skill_name, path=str(path), action="updated", reason=""
        )

    def _write_file(
        self,
        skill_name: str,
        description: str,
        tools_str: str,
        trigger: str,
        body: str,
        action: str,
    ) -> SynthesisResult:
        # Never overwrite user-authored skills
        user_path = Path.home() / ".solstice-agent" / "skills" / f"{skill_name}.md"
        if user_path.exists():
            skill_name = f"{skill_name}-synthesized"

        path = _SYNTHESIZED_DIR / f"{skill_name}.md"

        lines = [
            "---",
            f'name: "{skill_name}"',
            f'description: "{description}"',
        ]
        if tools_str:
            lines.append(f"tools: [{tools_str}]")
        if trigger:
            lines.append(f'trigger: "{trigger}"')
        lines += [
            "synthesized: true",
            f"synthesized_at: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
            "---",
            "",
            body,
        ]

        path.write_text("\n".join(lines), encoding="utf-8")
        log.info(f"Skill {action}: {skill_name} → {path}")
        self._reload()
        return SynthesisResult(
            saved=True, skill_name=skill_name, path=str(path), action=action, reason=""
        )

    def _list_existing_names(self) -> List[str]:
        if not _SYNTHESIZED_DIR.exists():
            return []
        return [p.stem for p in _SYNTHESIZED_DIR.glob("*.md")]

    def _reload(self):
        """Hot-reload the skill loader so new skills are immediately available."""
        if self.skill_loader:
            try:
                from .skills import init_skills
                init_skills()
            except Exception as exc:
                log.debug(f"Skill reload skipped: {exc}")


# ---------------------------------------------------------------------------
# Explicit tools the LLM can call during a task
# ---------------------------------------------------------------------------

def skill_save(
    name: str,
    description: str,
    content: str,
    tools: str = "",
    trigger: str = "",
) -> str:
    """
    Persist a reusable skill guide discovered during the current task.
    Call this when you've successfully worked out a non-obvious technique
    you want to remember for future sessions.
    """
    _SYNTHESIZED_DIR.mkdir(parents=True, exist_ok=True)
    skill_name = name.lower().replace(" ", "-")
    path = _SYNTHESIZED_DIR / f"{skill_name}.md"

    lines = [
        "---",
        f'name: "{skill_name}"',
        f'description: "{description}"',
    ]
    if tools:
        lines.append(f"tools: [{tools}]")
    if trigger:
        lines.append(f'trigger: "{trigger}"')
    lines += [
        "synthesized: true",
        f"synthesized_at: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        "---",
        "",
        content,
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Skill saved (explicit): {skill_name}")
    return f"Skill '{skill_name}' saved to {path}"


def skill_improve(name: str, additional_notes: str) -> str:
    """
    Append new findings to an existing skill guide.
    Call this when you discover a better approach, edge case, or correction
    for a skill that's already been saved.
    """
    _SYNTHESIZED_DIR.mkdir(parents=True, exist_ok=True)
    skill_name = name.lower().replace(" ", "-")

    for search_dir in (
        _SYNTHESIZED_DIR,
        Path.home() / ".solstice-agent" / "skills",
    ):
        path = search_dir / f"{skill_name}.md"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            updated = existing.rstrip() + f"\n\n<!-- improved {timestamp} -->\n{additional_notes}\n"
            path.write_text(updated, encoding="utf-8")
            log.info(f"Skill improved: {skill_name}")
            return f"Skill '{skill_name}' updated with new notes."

    return (
        f"Skill '{skill_name}' not found. "
        "Use skill_save to create it first, then skill_improve to refine it."
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "skill_save": {
        "name": "skill_save",
        "description": (
            "Save a reusable skill guide from the current task for future sessions. "
            "Call this when you've worked out a non-trivial workflow you want to remember. "
            "The skill will be auto-loaded in future conversations when relevant."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Kebab-case skill name (e.g. 'deploy-docker-app')",
                },
                "description": {
                    "type": "string",
                    "description": "One-sentence description of what the skill covers",
                },
                "content": {
                    "type": "string",
                    "description": "Full markdown guide — include exact steps, commands, and gotchas",
                },
                "tools": {
                    "type": "string",
                    "description": "Comma-separated tool names used in this skill",
                },
                "trigger": {
                    "type": "string",
                    "description": "Regex pattern that should auto-load this skill",
                },
            },
            "required": ["name", "description", "content"],
        },
    },
    "skill_improve": {
        "name": "skill_improve",
        "description": (
            "Append new learnings to an existing skill guide. "
            "Use this when you find a better approach, edge case, or correction "
            "for a skill that was previously saved."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the skill to update",
                },
                "additional_notes": {
                    "type": "string",
                    "description": "New findings, corrections, or edge cases to append",
                },
            },
            "required": ["name", "additional_notes"],
        },
    },
}


def register_synthesis_tools(registry):
    """Register skill synthesis tools with a ToolRegistry."""
    registry.register("skill_save", skill_save, _SCHEMAS["skill_save"])
    registry.register("skill_improve", skill_improve, _SCHEMAS["skill_improve"])
