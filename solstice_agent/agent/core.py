"""
Agent Core
==========
The tool-calling loop. This is what makes it an agent, not a chatbot.

Flow:
    User message → LLM (with tools) → tool calls? → execute → feed results back → repeat
    ↓ no tool calls
    Return response to user

The loop continues until the LLM responds with text (no tool calls) or hits max iterations.
"""

import json
import logging
import copy
from typing import Generator, List, Dict, Any, Callable, Optional

from .providers.base import BaseLLMProvider, LLMResponse, StreamEvent
from .personality import Personality, DEFAULT

log = logging.getLogger("solstice.agent")


class AgentExecutionCancelled(Exception):
    """Raised when an agent run is cancelled cooperatively."""


class Agent:
    """
    Core agent with tool-calling loop and conversation memory.

    Usage:
        from solstice_agent.agent import Agent
        from solstice_agent.agent.providers import OpenAIProvider

        provider = OpenAIProvider(api_key="sk-...")
        agent = Agent(provider=provider)

        # Register tools
        agent.register_tool("read_file", read_file_fn, {
            "name": "read_file",
            "description": "Read a file from disk",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            }
        })

        # Chat
        response = agent.chat("What's in README.md?")
        print(response)
    """

    MAX_TOOL_ITERATIONS = 10

    def __init__(
        self,
        provider: BaseLLMProvider,
        personality: Personality = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        max_tool_iterations: Optional[int] = None,
        skill_loader=None,
        compactor=None,
        synthesizer=None,
    ):
        self.provider = provider
        self.personality = personality or DEFAULT
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_iterations = max_tool_iterations or self.MAX_TOOL_ITERATIONS
        self.skill_loader = skill_loader
        self.compactor = compactor
        self.synthesizer = synthesizer

        # Conversation history
        self.history: List[Dict[str, Any]] = []

        # Tool registry
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: List[Dict[str, Any]] = []
        self.command_policy: Dict[str, List[str]] = {"allowed_prefixes": [], "denied_prefixes": []}
        self.workspace_root_override: Optional[str] = None
        self.workspace_required_override: Optional[bool] = None
        self.auto_track_tasks: bool = False
        self.progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self.should_continue_callback: Optional[Callable[[], bool]] = None

        log.info(f"Agent initialized: {self.personality.name} via {provider.name()}")

    def list_tool_names(self) -> List[str]:
        """List currently registered tool names."""
        return list(self._tools.keys())

    def register_tool(self, name: str, handler: Callable, schema: Dict[str, Any]):
        """
        Register a tool the agent can use.

        Args:
            name: Tool name (must match schema name)
            handler: Function to call. Receives **kwargs from LLM arguments.
                     Must return a string (the result).
            schema: Tool schema dict with name, description, parameters.
        """
        self._tools[name] = handler
        # Avoid duplicates
        self._tool_schemas = [s for s in self._tool_schemas if s["name"] != name]
        self._tool_schemas.append(schema)
        log.debug(f"Registered tool: {name}")

    def register_tools(self, tools: Dict[str, tuple]):
        """
        Bulk register tools.

        Args:
            tools: Dict of {name: (handler_fn, schema_dict)}
        """
        for name, (handler, schema) in tools.items():
            self.register_tool(name, handler, schema)

    def clone_with_tools(
        self,
        tool_names: Optional[List[str]] = None,
        extra_instructions: str = "",
        include_history: bool = False,
        allowed_command_prefixes: Optional[List[str]] = None,
        denied_command_prefixes: Optional[List[str]] = None,
        workspace_root: Optional[str] = None,
        workspace_required: Optional[bool] = None,
        model_override: str = "",
        max_tool_iterations: Optional[int] = None,
    ) -> "Agent":
        """
        Create a child agent with a filtered tool surface.
        This is the core primitive used by the sub-agent tool.
        """
        child_personality = self.personality
        if extra_instructions:
            context = self.personality.context or ""
            extra = f"Sub-agent instructions:\n{extra_instructions}"
            child_personality = Personality(
                name=self.personality.name,
                role=self.personality.role,
                tone=self.personality.tone,
                rules=list(self.personality.rules),
                context=(context + "\n\n" + extra).strip(),
            )

        child_provider = self.provider
        if model_override:
            try:
                child_provider = copy.copy(self.provider)
                child_provider.model = model_override
            except Exception:
                child_provider = self.provider

        child = Agent(
            provider=child_provider,
            personality=child_personality,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            max_tool_iterations=max_tool_iterations or self.max_tool_iterations,
            skill_loader=self.skill_loader,
            compactor=self.compactor,
            synthesizer=self.synthesizer,
        )
        allowed = set(tool_names or self._tools.keys())
        for schema in self._tool_schemas:
            name = schema["name"]
            if name in allowed and name != "run_subagent":
                child.register_tool(name, self._tools[name], schema)

        if include_history:
            child.history = list(self.history)
        child.command_policy = {
            "allowed_prefixes": list(allowed_command_prefixes or self.command_policy.get("allowed_prefixes", [])),
            "denied_prefixes": list(denied_command_prefixes or self.command_policy.get("denied_prefixes", [])),
        }
        child.workspace_root_override = workspace_root if workspace_root is not None else self.workspace_root_override
        child.workspace_required_override = (
            workspace_required if workspace_required is not None else self.workspace_required_override
        )
        child.auto_track_tasks = self.auto_track_tasks
        return child

    def chat(self, message: str, images: list = None) -> str:
        """
        Send a message and get a response. Tools are called automatically.

        Args:
            message: The user's text message.
            images: Optional list of image file paths to include (multimodal).

        This is the main entry point. The agent will:
        1. Add the message to conversation history
        2. Call the LLM with available tools
        3. If the LLM wants to use tools, execute them and feed results back
        4. Repeat until the LLM responds with text
        5. Return the final text response
        """
        auto_task_id = self._maybe_start_auto_task(message if isinstance(message, str) else "")
        self._emit_progress("request_started", message=(message if isinstance(message, str) else ""))

        # Build user message content (text or multimodal)
        if images and self.provider.supports_vision():
            from .providers.base import encode_image
            content = [{"type": "text", "text": message}]
            for img_path in images:
                try:
                    b64_data, media_type = encode_image(img_path)
                    content.append({
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                        "path": img_path,  # Kept for provider-specific formatting
                    })
                except Exception as e:
                    log.warning(f"Failed to load image {img_path}: {e}")
            self.history.append({"role": "user", "content": content})
        else:
            # Add user message to history
            self.history.append({"role": "user", "content": message})

        # Build messages with system prompt
        messages = self._build_messages(user_message=message if isinstance(message, str) else "")

        # Tool-calling loop
        tool_call_count = 0
        for iteration in range(self.max_tool_iterations):
            self._ensure_can_continue()
            tools = self._tool_schemas if self._tools and self.provider.supports_tools() else None

            response = self.provider.chat(
                messages=messages,
                tools=tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            self._emit_progress(
                "model_iteration",
                iteration=iteration + 1,
                tool_calls=[tc.get("name") for tc in response.tool_calls],
            )

            if not response.tool_calls:
                # No tool calls — we have our final response
                final_text = response.text.strip()
                self.history.append({"role": "assistant", "content": final_text})
                self._compact_or_trim()
                self._maybe_synthesize(tool_call_count)
                self._finish_auto_task(auto_task_id, "completed", final_text)
                self._emit_progress("request_completed", response=final_text)
                return final_text

            # Execute tool calls
            log.info(f"Tool calls (iteration {iteration + 1}): "
                     f"{[tc['name'] for tc in response.tool_calls]}")

            # Add assistant message with tool calls to messages
            messages.append(self._format_assistant_tool_message(response))

            # Execute each tool and add results
            for tool_call in response.tool_calls:
                tool_call_count += 1
                result = self._execute_tool(tool_call)
                messages.append(self._format_tool_result(tool_call, result))

        # Hit max iterations — return whatever we have
        fallback = response.text if response.text else "I got stuck in a tool loop. Try rephrasing?"
        self.history.append({"role": "assistant", "content": fallback})
        self._compact_or_trim()
        self._maybe_synthesize(tool_call_count)
        self._finish_auto_task(auto_task_id, "completed", fallback)
        self._emit_progress("request_completed", response=fallback)
        return fallback

    def chat_stream(self, message: str, images: list = None) -> Generator[StreamEvent, None, None]:
        """
        Stream a response token-by-token. Yields StreamEvents.

        Tool calls are executed internally (blocking) and their results are
        fed back to the LLM. Only the final text response is streamed.
        Intermediate tool iterations use non-streaming chat() for speed.
        """
        # Build user message (same as chat())
        if images and self.provider.supports_vision():
            from .providers.base import encode_image
            content = [{"type": "text", "text": message}]
            for img_path in images:
                try:
                    b64_data, media_type = encode_image(img_path)
                    content.append({
                        "type": "image",
                        "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                        "path": img_path,
                    })
                except Exception as e:
                    log.warning(f"Failed to load image {img_path}: {e}")
            self.history.append({"role": "user", "content": content})
        else:
            self.history.append({"role": "user", "content": message})

        messages = self._build_messages(user_message=message if isinstance(message, str) else "")
        tools = self._tool_schemas if self._tools and self.provider.supports_tools() else None

        # Tool loop: use non-streaming chat() for tool iterations
        tool_iterations = 0
        auto_task_id = self._maybe_start_auto_task(message if isinstance(message, str) else "")
        self._emit_progress("request_started", message=(message if isinstance(message, str) else ""))
        for iteration in range(self.max_tool_iterations):
            self._ensure_can_continue()
            # On the last possible iteration, or if no tools, stream directly
            # Otherwise, try non-streaming first to check for tool calls
            if not tools or iteration == self.max_tool_iterations - 1:
                break

            response = self.provider.chat(
                messages=messages,
                tools=tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            self._emit_progress(
                "model_iteration",
                iteration=iteration + 1,
                tool_calls=[tc.get("name") for tc in response.tool_calls],
            )

            if not response.tool_calls:
                # No tool calls — we should stream the final response instead
                # But we already got it non-streaming. Yield it as a single chunk.
                final_text = response.text.strip()
                self.history.append({"role": "assistant", "content": final_text})
                self._compact_or_trim()
                self._finish_auto_task(auto_task_id, "completed", final_text)
                self._emit_progress("request_completed", response=final_text)
                yield StreamEvent(type="text", text=final_text)
                yield StreamEvent(type="done", usage=response.usage)
                return

            # Execute tool calls (same as chat())
            log.info(f"Tool calls (iteration {iteration + 1}): "
                     f"{[tc['name'] for tc in response.tool_calls]}")

            messages.append(self._format_assistant_tool_message(response))

            for tool_call in response.tool_calls:
                tool_iterations += 1
                if tool_iterations > self.max_tool_iterations:
                    final_text = "I got stuck in a tool loop. Try rephrasing?"
                    self.history.append({"role": "assistant", "content": final_text})
                    self._compact_or_trim()
                    self._finish_auto_task(auto_task_id, "completed", final_text)
                    self._emit_progress("request_completed", response=final_text)
                    yield StreamEvent(type="text", text=final_text)
                    yield StreamEvent(type="done", usage=response.usage)
                    return
                yield StreamEvent(type="tool_calls", tool_calls=[tool_call])
                result = self._execute_tool(tool_call)
                messages.append(self._format_tool_result(tool_call, result))

        # Final response: stream it
        full_text = ""
        self._ensure_can_continue()
        for event in self.provider.stream(
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            self._ensure_can_continue()
            if event.type == "text":
                full_text += event.text
                yield event
            elif event.type == "tool_calls":
                # Unexpected tool calls in the streaming pass — handle them
                log.info(f"Late tool calls in stream: {[tc['name'] for tc in event.tool_calls]}")
                messages.append(self._format_assistant_tool_message(
                    LLMResponse(text=full_text, tool_calls=event.tool_calls)))
                for tool_call in event.tool_calls:
                    tool_iterations += 1
                    if tool_iterations > self.max_tool_iterations:
                        final_text = "I got stuck in a tool loop. Try rephrasing?"
                        self.history.append({"role": "assistant", "content": final_text})
                        self._compact_or_trim()
                        self._finish_auto_task(auto_task_id, "completed", final_text)
                        self._emit_progress("request_completed", response=final_text)
                        yield StreamEvent(type="text", text=final_text)
                        yield StreamEvent(type="done", usage=None)
                        return
                    yield StreamEvent(type="tool_calls", tool_calls=[tool_call])
                    result = self._execute_tool(tool_call)
                    messages.append(self._format_tool_result(tool_call, result))
                # After handling late tools, get the final response non-streaming
                fallback = self.provider.chat(
                    messages=messages, tools=tools,
                    temperature=self.temperature, max_tokens=self.max_tokens)
                final = fallback.text.strip()
                self.history.append({"role": "assistant", "content": final})
                self._compact_or_trim()
                self._finish_auto_task(auto_task_id, "completed", final)
                self._emit_progress("request_completed", response=final)
                yield StreamEvent(type="text", text=final)
                yield StreamEvent(type="done", usage=fallback.usage)
                return
            elif event.type == "done":
                pass  # Handled below

        final_text = full_text.strip()
        self.history.append({"role": "assistant", "content": final_text})
        self._compact_or_trim()
        self._finish_auto_task(auto_task_id, "completed", final_text)
        self._emit_progress("request_completed", response=final_text)
        yield StreamEvent(type="done")

    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """Execute a single tool call and return the result as a string."""
        self._ensure_can_continue()
        name = tool_call["name"]
        args = tool_call.get("arguments", {})

        handler = self._tools.get(name)
        if not handler:
            self._emit_progress("tool_failed", tool=name, error=f"Unknown tool '{name}'")
            return self._format_tool_payload(
                tool=name,
                status="error",
                error=f"Unknown tool '{name}'",
            )

        try:
            log.info(f"Executing tool: {name}({self._safe_args_preview(args)})")
            self._emit_progress("tool_started", tool=name, args=args)
            from ..tools.terminal import command_policy_context
            from ..tools.security import workspace_root_context

            with workspace_root_context(
                self.workspace_root_override,
                required=self.workspace_required_override,
            ), command_policy_context(
                denied_prefixes=self.command_policy.get("denied_prefixes"),
                allowed_prefixes=self.command_policy.get("allowed_prefixes"),
            ):
                result = handler(**args)
            result_str = str(result) if result is not None else "Done."
            log.debug(f"Tool result: {result_str[:200]}")
            self._emit_progress("tool_completed", tool=name, result_preview=result_str[:200])
            return self._format_tool_payload(
                tool=name,
                status="ok",
                data=result_str,
            )
        except Exception as e:
            error_msg = f"{type(e).__name__}: {e}"
            log.error(f"Tool '{name}' failed: {error_msg}")
            self._emit_progress("tool_failed", tool=name, error=error_msg)
            return self._format_tool_payload(
                tool=name,
                status="error",
                error=error_msg,
            )

    def _format_tool_payload(self, tool: str, status: str, data: str | None = None, error: str | None = None) -> str:
        """Return a structured tool result string for the LLM to consume."""
        payload = {
            "tool": tool,
            "status": status,
            "data": data if data is not None else "",
            "error": error if error is not None else "",
        }
        if len(payload["data"]) > 10000:
            payload["data"] = payload["data"][:5000] + "\n... (truncated) ...\n" + payload["data"][-3000:]
        return json.dumps(payload, ensure_ascii=False)

    def _safe_args_preview(self, args: Dict[str, Any]) -> str:
        """Redact likely secrets from tool args before logging."""
        def _redact(obj):
            if isinstance(obj, dict):
                cleaned = {}
                for k, v in obj.items():
                    key_lower = str(k).lower()
                    if any(token in key_lower for token in ("key", "token", "secret", "password", "auth", "cookie")):
                        cleaned[k] = "***"
                    else:
                        cleaned[k] = _redact(v)
                return cleaned
            if isinstance(obj, list):
                return [_redact(v) for v in obj]
            return obj

        try:
            redacted = _redact(args)
            return json.dumps(redacted, default=str)[:200]
        except Exception:
            return "<redacted>"

    def _build_messages(self, user_message: str = "") -> List[Dict[str, Any]]:
        """Build the message list with system prompt + conversation history."""
        system_prompt = self.personality.to_system_prompt()

        task_prompt = self._task_prompt_block()
        if task_prompt:
            system_prompt += "\n" + task_prompt

        # Inject skill Tier 1 summaries into system prompt
        if self.skill_loader:
            tier1 = self.skill_loader.tier1_block()
            if tier1:
                system_prompt += "\n" + tier1

        policy_prompt = self._command_policy_prompt_block()
        if policy_prompt:
            system_prompt += "\n" + policy_prompt

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(self.history)

        # Auto-inject triggered skills as system messages
        if self.skill_loader and user_message:
            triggered = self.skill_loader.match_triggers(user_message)
            for skill_name in triggered:
                skill = self.skill_loader.get_skill(skill_name)
                if skill:
                    messages.append({
                        "role": "system",
                        "content": f"[Auto-loaded skill: {skill.name}]\n{skill.tier2_full()}",
                    })

        return messages

    def _task_prompt_block(self) -> str:
        try:
            from .tasks import _get_board

            items = _get_board().list()
        except Exception:
            return ""

        lines = [
            "\n## Task Tracking",
            "For multi-step work, use task_upsert to track progress instead of keeping the plan only in prose.",
        ]
        if not items:
            lines.append("No tracked tasks yet.")
            return "\n".join(lines)

        lines.append("Current tracked tasks:")
        for item in items[:8]:
            suffix = f" :: {item.details}" if item.details else ""
            lines.append(f"- {item.id} [{item.status}] {item.subject}{suffix}")
        if len(items) > 8:
            lines.append(f"- ... and {len(items) - 8} more")
        return "\n".join(lines)

    def _command_policy_prompt_block(self) -> str:
        allowed = self.command_policy.get("allowed_prefixes") or []
        denied = self.command_policy.get("denied_prefixes") or []
        if not allowed and not denied:
            return ""
        lines = ["\n## Command Policy", "Terminal tools are subject to these command constraints:"]
        if allowed:
            lines.append(f"- Allowed prefixes: {', '.join(allowed)}")
        if denied:
            lines.append(f"- Denied prefixes: {', '.join(denied)}")
        return "\n".join(lines)

    def _format_assistant_tool_message(self, response: LLMResponse) -> Dict[str, Any]:
        """Format an assistant message that contains tool calls."""
        # OpenAI format — other providers are normalized to this in their adapters
        msg: Dict[str, Any] = {"role": "assistant", "content": response.text or ""}

        if self.provider.__class__.__name__ == "OpenAIProvider":
            msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["arguments"]),
                    },
                }
                for tc in response.tool_calls
            ]
        elif self.provider.__class__.__name__ == "AnthropicProvider":
            # For Anthropic, we reconstruct content blocks
            content = []
            if response.text:
                content.append({"type": "text", "text": response.text})
            for tc in response.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["name"],
                    "input": tc["arguments"],
                })
            msg = {"role": "assistant", "content": content}
        else:
            # Generic: embed tool calls in content for providers that need text
            if response.tool_calls:
                calls_text = "\n".join(
                    f"[Calling {tc['name']}({json.dumps(tc['arguments'], default=str)})]"
                    for tc in response.tool_calls
                )
                msg["content"] = (response.text + "\n" + calls_text).strip()

        return msg

    def _format_tool_result(self, tool_call: Dict[str, Any], result: str) -> Dict[str, Any]:
        """Format a tool result message for the conversation."""
        if self.provider.__class__.__name__ == "OpenAIProvider":
            return {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            }
        elif self.provider.__class__.__name__ == "AnthropicProvider":
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_call["id"],
                    "content": result,
                }],
            }
        else:
            # Generic: tool results as user messages
            return {
                "role": "user",
                "content": f"[Tool result for {tool_call['name']}]: {result}",
            }

    def _trim_history(self, max_messages: int = 40):
        """Keep conversation history bounded (hard fallback)."""
        if len(self.history) > max_messages:
            self.history = self.history[-max_messages:]

    def _compact_or_trim(self):
        """Use compactor if available, otherwise hard trim."""
        if self.compactor:
            self.history = self.compactor.compact(self.history)
        else:
            self._trim_history()

    def _maybe_synthesize(self, tool_call_count: int):
        """Fire-and-forget: ask the synthesizer to consider saving a skill."""
        if not self.synthesizer:
            return
        try:
            result = self.synthesizer.maybe_synthesize(self.history, tool_call_count)
            if result and result.saved:
                log.info(
                    f"Skill {result.action}: '{result.skill_name}' → {result.path}"
                )
        except Exception as exc:
            log.debug(f"Synthesis error (non-fatal): {exc}")

    def _maybe_start_auto_task(self, message: str) -> str:
        if not self.auto_track_tasks:
            return ""
        text = (message or "").strip()
        if len(text.split()) < 4:
            return ""
        try:
            from .tasks import task_upsert

            result = task_upsert(
                subject=text[:120],
                status="in_progress",
                details="Auto-tracked from agent request",
            )
            return result.split()[1] if result.startswith("Task ") else ""
        except Exception:
            return ""

    def _finish_auto_task(self, task_id: str, status: str, result: str):
        if not self.auto_track_tasks or not task_id:
            return
        try:
            from .tasks import task_upsert

            task_upsert(
                subject="",
                task_id=task_id,
                status=status,
                details=(result or "")[:240],
            )
        except Exception:
            pass

    def _emit_progress(self, event_type: str, **payload):
        if not self.progress_callback:
            return
        try:
            event = {"type": event_type, **payload}
            self.progress_callback(event)
        except Exception:
            pass

    def _ensure_can_continue(self):
        if not self.should_continue_callback:
            return
        try:
            allowed = self.should_continue_callback()
        except Exception:
            allowed = True
        if not allowed:
            self._emit_progress("request_cancelled")
            raise AgentExecutionCancelled("Agent execution was cancelled.")

    def clear_history(self):
        """Reset conversation history."""
        self.history.clear()

    def get_history(self) -> List[Dict[str, Any]]:
        """Get current conversation history."""
        return list(self.history)
