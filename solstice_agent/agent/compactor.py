"""
Context Compactor
=================
Intelligent conversation summarization to replace hard history trimming.

Instead of dropping old messages, summarizes them into a compact digest
that preserves key facts, decisions, paths, and errors.

Token counting is approximate (chars/4) to avoid adding a tokenizer dependency.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

log = logging.getLogger("solstice.compactor")

# Model context windows (tokens)
MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    # OpenAI
    "gpt-4o": 128_000,
    "gpt-4o-mini": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_192,
    "o1": 200_000,
    "o1-mini": 128_000,
    "o3": 200_000,
    "o3-mini": 128_000,
    # Anthropic
    "claude-sonnet-4-5-20250929": 200_000,
    "claude-opus-4-5-20250929": 200_000,
    "claude-3-5-sonnet-20241022": 200_000,
    "claude-3-5-haiku-20241022": 200_000,
    # Gemini
    "gemini-2.5-flash": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "gemini-2.0-flash": 1_048_576,
    # Ollama (conservative defaults)
    "llama3.1": 128_000,
    "llama3.2": 128_000,
    "mistral": 32_000,
    "mixtral": 32_000,
    "codellama": 16_000,
    "phi3": 128_000,
    "qwen2": 32_000,
}

DEFAULT_CONTEXT_WINDOW = 128_000

SUMMARY_PREFIX = "[Summary of earlier conversation]"

SUMMARIZATION_PROMPT = """Summarize the following conversation history into a concise digest.

PRESERVE:
- Key facts and data mentioned
- Decisions made and their reasoning
- File paths, URLs, commands used
- Errors encountered and their resolutions
- User preferences expressed
- Task progress and status

FORMAT:
- Use bullet points
- Group by topic/task
- Be concise but don't lose critical details
- Start with: "{prefix}"

CONVERSATION TO SUMMARIZE:
{conversation}"""


@dataclass
class CompactorConfig:
    """Configuration for the context compactor."""
    threshold: float = 0.75        # Compact at 75% of context window
    keep_recent: int = 10          # Always keep last N messages uncompacted
    model_name: str = ""           # For context window lookup
    context_window: int = 0        # Override (0 = auto-detect from model_name)


class ContextCompactor:
    """
    Manages conversation history compaction via LLM summarization.

    Instead of hard-trimming at 40 messages, estimates token usage and
    summarizes older messages when approaching the context window limit.
    """

    def __init__(self, provider, config: CompactorConfig = None):
        self.provider = provider
        self.config = config or CompactorConfig()
        self._context_window = self._resolve_context_window()

    def _resolve_context_window(self) -> int:
        if self.config.context_window > 0:
            return self.config.context_window

        model = self.config.model_name or getattr(self.provider, "model", "")

        # Exact match
        if model in MODEL_CONTEXT_WINDOWS:
            return MODEL_CONTEXT_WINDOWS[model]

        # Prefix match (e.g., "gpt-4o-2024-..." matches "gpt-4o")
        for key, window in MODEL_CONTEXT_WINDOWS.items():
            if model.startswith(key):
                return window

        log.info(f"Unknown model '{model}', using default context window: {DEFAULT_CONTEXT_WINDOW}")
        return DEFAULT_CONTEXT_WINDOW

    @staticmethod
    def estimate_tokens(messages: List[Dict]) -> int:
        """Approximate token count. Heuristic: 1 token ~ 4 characters."""
        total_chars = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total_chars += len(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            total_chars += len(block.get("text", ""))
                        elif block.get("type") == "tool_result":
                            total_chars += len(str(block.get("content", "")))
                        elif block.get("type") in ("image", "image_url"):
                            total_chars += 4000  # ~1000 tokens
            total_chars += len(msg.get("role", "")) + 4  # framing overhead
        return total_chars // 4

    def needs_compaction(self, history: List[Dict]) -> bool:
        if len(history) <= self.config.keep_recent:
            return False
        estimated = self.estimate_tokens(history)
        threshold = int(self._context_window * self.config.threshold)
        log.debug(f"Token estimate: {estimated}/{self._context_window} "
                  f"(threshold: {threshold}, {len(history)} messages)")
        return estimated > threshold

    def compact(self, history: List[Dict]) -> List[Dict]:
        """
        Compact conversation history by summarizing older messages.
        Returns new history with summary replacing old messages.
        Recent messages (last keep_recent) are preserved verbatim.
        """
        if not self.needs_compaction(history):
            return history

        keep_recent = self.config.keep_recent

        # Split — keep last N intact, don't break tool call/result pairs
        split_idx = len(history) - keep_recent
        split_idx = self._safe_split_point(history, split_idx)

        if split_idx <= 0:
            return history

        old_messages = history[:split_idx]
        recent_messages = history[split_idx:]

        log.info(f"Compacting {len(old_messages)} messages into summary, "
                 f"keeping {len(recent_messages)} recent")

        conversation_text = self._format_for_summary(old_messages)
        summary = self._summarize(conversation_text)

        if not summary:
            log.warning("Summarization failed, keeping recent messages only")
            return recent_messages

        summary_message = {"role": "user", "content": summary}
        return [summary_message] + recent_messages

    def _safe_split_point(self, history: List[Dict], target_idx: int) -> int:
        """Adjust split point to avoid breaking tool call/result pairs."""
        idx = target_idx
        while idx > 0:
            msg = history[idx]

            # Don't split right after an assistant message with tool calls
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if isinstance(content, list):
                    has_tool_use = any(
                        b.get("type") == "tool_use" for b in content if isinstance(b, dict)
                    )
                    if has_tool_use:
                        idx -= 1
                        continue
                if msg.get("tool_calls"):
                    idx -= 1
                    continue

            # Don't split on a tool result (orphaned without its call)
            if msg.get("role") == "tool":
                idx -= 1
                continue
            if msg.get("role") == "user" and isinstance(msg.get("content"), list):
                has_tool_result = any(
                    b.get("type") == "tool_result" for b in msg["content"]
                    if isinstance(b, dict)
                )
                if has_tool_result:
                    idx -= 1
                    continue

            break

        return max(idx, 0)

    def _format_for_summary(self, messages: List[Dict]) -> str:
        """Format messages into readable text for the summarization LLM."""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")

            if isinstance(content, str):
                if content.startswith(SUMMARY_PREFIX):
                    lines.append(f"[PREVIOUS SUMMARY]\n{content}\n")
                else:
                    display = content[:2000] + "..." if len(content) > 2000 else content
                    lines.append(f"{role}: {display}")
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(block["text"])
                        elif block.get("type") == "tool_use":
                            parts.append(f"[called {block.get('name', '?')}]")
                        elif block.get("type") == "tool_result":
                            result = str(block.get("content", ""))[:500]
                            parts.append(f"[result: {result}]")
                if parts:
                    lines.append(f"{role}: {' '.join(parts)}")

            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    if isinstance(tc, dict):
                        name = tc.get("function", {}).get("name", "") or tc.get("name", "")
                        lines.append(f"  [called tool: {name}]")

        return "\n".join(lines)

    def _summarize(self, conversation_text: str) -> Optional[str]:
        """Call the LLM to generate a summary."""
        prompt = SUMMARIZATION_PROMPT.format(
            prefix=SUMMARY_PREFIX,
            conversation=conversation_text,
        )

        messages = [
            {"role": "system", "content": "You are a conversation summarizer. Be concise and accurate."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.provider.chat(
                messages=messages,
                tools=None,
                temperature=0.3,
                max_tokens=2048,
            )
            summary = response.text.strip()

            if not summary.startswith(SUMMARY_PREFIX):
                summary = f"{SUMMARY_PREFIX}\n{summary}"

            log.info(f"Generated summary: {len(summary)} chars")
            return summary

        except Exception as e:
            log.error(f"Summarization failed: {e}")
            return None
