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
from typing import Generator, List, Dict, Any, Callable

from .providers.base import BaseLLMProvider, LLMResponse, StreamEvent
from .personality import Personality, DEFAULT

log = logging.getLogger("solstice.agent")


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
        skill_loader=None,
        compactor=None,
    ):
        self.provider = provider
        self.personality = personality or DEFAULT
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.skill_loader = skill_loader
        self.compactor = compactor

        # Conversation history
        self.history: List[Dict[str, Any]] = []

        # Tool registry
        self._tools: Dict[str, Callable] = {}
        self._tool_schemas: List[Dict[str, Any]] = []

        log.info(f"Agent initialized: {self.personality.name} via {provider.name()}")

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
        for iteration in range(self.MAX_TOOL_ITERATIONS):
            tools = self._tool_schemas if self._tools and self.provider.supports_tools() else None

            response = self.provider.chat(
                messages=messages,
                tools=tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if not response.tool_calls:
                # No tool calls — we have our final response
                final_text = response.text.strip()
                self.history.append({"role": "assistant", "content": final_text})
                self._compact_or_trim()
                return final_text

            # Execute tool calls
            log.info(f"Tool calls (iteration {iteration + 1}): "
                     f"{[tc['name'] for tc in response.tool_calls]}")

            # Add assistant message with tool calls to messages
            messages.append(self._format_assistant_tool_message(response))

            # Execute each tool and add results
            for tool_call in response.tool_calls:
                result = self._execute_tool(tool_call)
                messages.append(self._format_tool_result(tool_call, result))

        # Hit max iterations — return whatever we have
        fallback = response.text if response.text else "I got stuck in a tool loop. Try rephrasing?"
        self.history.append({"role": "assistant", "content": fallback})
        self._compact_or_trim()
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
        for iteration in range(self.MAX_TOOL_ITERATIONS):
            # On the last possible iteration, or if no tools, stream directly
            # Otherwise, try non-streaming first to check for tool calls
            if not tools or iteration == self.MAX_TOOL_ITERATIONS - 1:
                break

            response = self.provider.chat(
                messages=messages,
                tools=tools,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            if not response.tool_calls:
                # No tool calls — we should stream the final response instead
                # But we already got it non-streaming. Yield it as a single chunk.
                final_text = response.text.strip()
                self.history.append({"role": "assistant", "content": final_text})
                self._compact_or_trim()
                yield StreamEvent(type="text", text=final_text)
                yield StreamEvent(type="done", usage=response.usage)
                return

            # Execute tool calls (same as chat())
            log.info(f"Tool calls (iteration {iteration + 1}): "
                     f"{[tc['name'] for tc in response.tool_calls]}")

            messages.append(self._format_assistant_tool_message(response))

            for tool_call in response.tool_calls:
                yield StreamEvent(type="tool_calls", tool_calls=[tool_call])
                result = self._execute_tool(tool_call)
                messages.append(self._format_tool_result(tool_call, result))

        # Final response: stream it
        full_text = ""
        for event in self.provider.stream(
            messages=messages,
            tools=tools,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        ):
            if event.type == "text":
                full_text += event.text
                yield event
            elif event.type == "tool_calls":
                # Unexpected tool calls in the streaming pass — handle them
                log.info(f"Late tool calls in stream: {[tc['name'] for tc in event.tool_calls]}")
                messages.append(self._format_assistant_tool_message(
                    LLMResponse(text=full_text, tool_calls=event.tool_calls)))
                for tool_call in event.tool_calls:
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
                yield StreamEvent(type="text", text=final)
                yield StreamEvent(type="done", usage=fallback.usage)
                return
            elif event.type == "done":
                pass  # Handled below

        final_text = full_text.strip()
        self.history.append({"role": "assistant", "content": final_text})
        self._compact_or_trim()
        yield StreamEvent(type="done")

    def _execute_tool(self, tool_call: Dict[str, Any]) -> str:
        """Execute a single tool call and return the result as a string."""
        name = tool_call["name"]
        args = tool_call.get("arguments", {})

        handler = self._tools.get(name)
        if not handler:
            return f"Error: Unknown tool '{name}'"

        try:
            log.info(f"Executing tool: {name}({json.dumps(args, default=str)[:200]})")
            result = handler(**args)
            result_str = str(result) if result is not None else "Done."
            log.debug(f"Tool result: {result_str[:200]}")
            return result_str
        except Exception as e:
            error_msg = f"Tool '{name}' failed: {type(e).__name__}: {e}"
            log.error(error_msg)
            return error_msg

    def _build_messages(self, user_message: str = "") -> List[Dict[str, Any]]:
        """Build the message list with system prompt + conversation history."""
        system_prompt = self.personality.to_system_prompt()

        # Inject skill Tier 1 summaries into system prompt
        if self.skill_loader:
            tier1 = self.skill_loader.tier1_block()
            if tier1:
                system_prompt += "\n" + tier1

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

    def clear_history(self):
        """Reset conversation history."""
        self.history.clear()

    def get_history(self) -> List[Dict[str, Any]]:
        """Get current conversation history."""
        return list(self.history)
