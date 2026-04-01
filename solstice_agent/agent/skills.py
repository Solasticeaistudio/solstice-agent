"""
Skill System
=============
Lazy-loaded markdown skill files that teach the LLM domain-specific workflows.

Three-tier loading:
  Tier 1: Name + description (always in system prompt, ~30 tokens per skill)
  Tier 2: Full guide body (loaded on-demand via skill_get tool)
  Tier 3: Reference docs below <!-- tier3 --> marker (loaded on further demand)

Storage:
  ~/.solstice-agent/skills/    (user skills)
  ./skills/                    (project-local skills)
"""

import logging
import re
from fnmatch import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("solstice.skills")

_DEFAULT_SKILLS_DIR = Path.home() / ".solstice-agent" / "skills"


@dataclass
class Skill:
    """Parsed skill from a markdown file."""
    name: str
    description: str
    tools: List[str] = field(default_factory=list)
    allowed_tools: List[str] = field(default_factory=list)
    trigger: str = ""
    when_to_use: str = ""
    model: str = ""
    effort: str = ""
    paths: List[str] = field(default_factory=list)
    argument_hint: str = ""
    argument_names: List[str] = field(default_factory=list)
    execution_context: str = ""
    tier2_content: str = ""
    tier3_content: str = ""
    source_path: str = ""

    def tier1_summary(self) -> str:
        """~30 token summary for system prompt injection."""
        return f"- **{self.name}**: {self.description}"

    def tier2_full(self) -> str:
        return self.tier2_content.strip()

    def tier3_reference(self) -> str:
        return self.tier3_content.strip()


class SkillLoader:
    """Scans skill directories and provides lazy-loaded access."""

    def __init__(self, extra_dirs: Optional[List[str]] = None):
        self._skills: Dict[str, Skill] = {}
        self._dirs: List[Path] = [_DEFAULT_SKILLS_DIR]

        local_skills = Path.cwd() / "skills"
        if local_skills.exists():
            self._dirs.append(local_skills)

        if extra_dirs:
            for d in extra_dirs:
                self._dirs.append(Path(d))

        self._scan()

    def _scan(self):
        for skills_dir in self._dirs:
            if not skills_dir.exists():
                continue
            candidates = sorted(skills_dir.glob("*.md")) + sorted(skills_dir.glob("**/SKILL.md"))
            seen = set()
            for md_file in candidates:
                resolved = str(md_file.resolve())
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    skill = self._parse_skill(md_file)
                    if skill:
                        self._skills[skill.name] = skill
                        log.debug(f"Loaded skill: {skill.name} from {md_file}")
                except Exception as e:
                    log.warning(f"Failed to parse skill {md_file}: {e}")

        log.info(f"Loaded {len(self._skills)} skills from {len(self._dirs)} directories")

    def _parse_skill(self, path: Path) -> Optional[Skill]:
        text = path.read_text(encoding="utf-8")

        # Extract YAML frontmatter
        fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', text, re.DOTALL)
        if not fm_match:
            return None

        frontmatter_text = fm_match.group(1)
        body = text[fm_match.end():]

        fm = self._parse_frontmatter(frontmatter_text)

        name = fm.get("name", "")
        description = fm.get("description", "")
        if not name or not description:
            return None

        tools = self._parse_list_field(fm.get("tools"))
        allowed_tools = self._parse_list_field(fm.get("allowed_tools") or fm.get("allowed-tools"))
        trigger = str(fm.get("trigger", ""))

        # Split at tier3 marker
        tier3_marker = "<!-- tier3 -->"
        if tier3_marker in body:
            parts = body.split(tier3_marker, 1)
            tier2_content = parts[0]
            tier3_content = parts[1]
        else:
            tier2_content = body
            tier3_content = ""

        return Skill(
            name=name,
            description=description,
            tools=tools,
            allowed_tools=allowed_tools,
            trigger=trigger,
            when_to_use=str(fm.get("when_to_use") or fm.get("when-to-use") or ""),
            model=str(fm.get("model", "")),
            effort=str(fm.get("effort", "")),
            paths=self._parse_list_field(fm.get("paths")),
            argument_hint=str(fm.get("argument_hint") or fm.get("argument-hint") or ""),
            argument_names=self._parse_list_field(fm.get("arguments")),
            execution_context=str(fm.get("context", "")),
            tier2_content=tier2_content,
            tier3_content=tier3_content,
            source_path=str(path),
        )

    def _parse_frontmatter(self, text: str) -> Dict[str, Any]:
        """Simple YAML-like frontmatter parser (no PyYAML needed)."""
        result = {}
        for line in text.strip().split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                parsed = value.strip().strip('"').strip("'")
                if parsed.startswith("[") and parsed.endswith("]"):
                    parsed = [
                        item.strip().strip('"').strip("'")
                        for item in parsed[1:-1].split(",")
                        if item.strip()
                    ]
                result[key.strip()] = parsed
        return result

    def _parse_list_field(self, value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [item.strip() for item in str(value).split(",") if item.strip()]

    def get_skill(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        return list(self._skills.values())

    def tier1_block(self) -> str:
        """Build Tier 1 block for system prompt. Empty if no skills."""
        if not self._skills:
            return ""
        lines = [
            "\n## Available Skills",
            "You have access to specialized skill guides. "
            "Use `skill_get` to load the full guide for any skill before attempting the task.",
        ]
        for skill in self._skills.values():
            lines.append(skill.tier1_summary())
        return "\n".join(lines)

    def skills_for_path(self, target_path: str) -> List[Skill]:
        """Return path-scoped skills plus global skills."""
        normalized = str(target_path).replace("\\", "/")
        matched: List[Skill] = []
        for skill in self._skills.values():
            if not skill.paths:
                matched.append(skill)
                continue
            for pattern in skill.paths:
                normalized_pattern = pattern.replace("\\", "/").rstrip("/")
                if not normalized_pattern:
                    continue
                glob_pattern = normalized_pattern
                if "*" not in glob_pattern and "?" not in glob_pattern:
                    glob_pattern = f"{glob_pattern}/**"
                if fnmatch(normalized, glob_pattern) or fnmatch(normalized, normalized_pattern):
                    matched.append(skill)
                    break
        return matched

    def match_triggers(self, user_message: str) -> List[str]:
        """Check user message against skill trigger patterns."""
        matches = []
        for skill in self._skills.values():
            if skill.trigger:
                try:
                    if re.search(skill.trigger, user_message, re.IGNORECASE):
                        matches.append(skill.name)
                except re.error:
                    pass
        return matches

    def ensure_dirs(self):
        _DEFAULT_SKILLS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_loader: Optional[SkillLoader] = None


def _get_loader() -> SkillLoader:
    global _loader
    if _loader is None:
        _loader = SkillLoader()
    return _loader


def init_skills(extra_dirs: Optional[List[str]] = None):
    """Initialize the skill loader (call once at startup)."""
    global _loader
    _loader = SkillLoader(extra_dirs=extra_dirs)
    _loader.ensure_dirs()


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

def skill_get(name: str, tier: int = 2) -> str:
    """Load skill content. Tier 2 = full guide, Tier 3 = guide + reference."""
    loader = _get_loader()
    skill = loader.get_skill(name)
    if not skill:
        available = ", ".join(s.name for s in loader.list_skills())
        return f"Skill '{name}' not found. Available: {available or 'none'}"

    if tier >= 3 and skill.tier3_content:
        return f"# {skill.name} (Full Guide + Reference)\n\n{skill.tier2_full()}\n\n---\n\n{skill.tier3_reference()}"
    return f"# {skill.name}\n\n{skill.tier2_full()}"


def skill_list() -> str:
    """List all available skills with descriptions."""
    loader = _get_loader()
    skills = loader.list_skills()
    if not skills:
        return "No skills loaded. Add .md files to ~/.solstice-agent/skills/"

    lines = [f"Available skills ({len(skills)}):"]
    for s in skills:
        tools_str = f" (tools: {', '.join(s.tools)})" if s.tools else ""
        extras = []
        if s.allowed_tools:
            extras.append(f"allowed={', '.join(s.allowed_tools)}")
        if s.paths:
            extras.append(f"paths={', '.join(s.paths)}")
        if s.when_to_use:
            extras.append(f"when={s.when_to_use}")
        suffix = f" [{' | '.join(extras)}]" if extras else ""
        lines.append(f"  {s.name}: {s.description}{tools_str}{suffix}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "skill_get": {
        "name": "skill_get",
        "description": (
            "Load a skill guide that teaches you how to handle a specific task. "
            "Call this BEFORE attempting a task that matches an available skill. "
            "Tier 2 = full guide (default), Tier 3 = includes reference docs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name to load"},
                "tier": {
                    "type": "integer",
                    "description": "2 for full guide, 3 for guide + reference docs",
                    "enum": [2, 3],
                },
            },
            "required": ["name"],
        },
    },
    "skill_list": {
        "name": "skill_list",
        "description": "List all available skill guides with their descriptions.",
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

def register_skill_tools(registry):
    """Register skill tools with a ToolRegistry."""
    registry.register("skill_get", skill_get, _SCHEMAS["skill_get"])
    registry.register("skill_list", skill_list, _SCHEMAS["skill_list"])
