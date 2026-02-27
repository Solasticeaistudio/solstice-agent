"""
CLI Agent
=========
Interactive terminal agent. Type messages, get responses with tool use.

Usage:
    solstice-agent                    # Interactive mode
    solstice-agent "What's in my cwd?"  # One-shot mode
    solstice-agent --provider ollama  # Use local model
    solstice-agent --setup            # Interactive setup wizard
"""

import json
import sys
import time
import argparse
import logging

from .config import Config
from .agent.core import Agent
from .agent.personality import DEFAULT, CODER
from .tools.registry import ToolRegistry

# Colors
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
BLUE = "\033[34m"


def main():
    parser = argparse.ArgumentParser(
        prog="solstice-agent",
        description="AI agent with real tool use. Not a chatbot wrapper.",
    )
    parser.add_argument("message", nargs="?", help="One-shot message (skip interactive mode)")
    parser.add_argument("--provider", "-p", help="LLM provider (openai, anthropic, gemini, ollama)")
    parser.add_argument("--model", "-m", help="Model name")
    parser.add_argument("--api-key", "-k", help="API key")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--personality", choices=["default", "coder"], default="default")
    parser.add_argument("--no-tools", action="store_true", help="Disable all tools")
    parser.add_argument("--no-terminal", action="store_true", help="Disable terminal tool")
    parser.add_argument("--no-web", action="store_true", help="Disable web tools")
    parser.add_argument("--no-browser", action="store_true", help="Disable browser tools")
    parser.add_argument("--no-voice", action="store_true", help="Disable voice tools")
    parser.add_argument("--no-memory", action="store_true", help="Disable persistent memory")
    parser.add_argument("--no-skills", action="store_true", help="Disable skill system")
    parser.add_argument("--no-cron", action="store_true", help="Disable scheduling system")
    parser.add_argument("--no-registry", action="store_true", help="Disable API registry tools")
    parser.add_argument("--no-screen", action="store_true", help="Disable screen capture tools")
    parser.add_argument("--no-docker", action="store_true", help="Disable Docker sandbox tools")
    parser.add_argument("--no-recording", action="store_true", help="Disable recording tools")
    parser.add_argument("--no-presence", action="store_true", help="Disable presence tools")
    parser.add_argument("--cron", nargs=2, metavar=("SCHEDULE", "QUERY"),
                        help='Quick-schedule a job: --cron "every 6h" "check my email"')
    parser.add_argument("--agent", "-a", help="Select agent by name (requires multi-agent config)")
    parser.add_argument("--list-agents", action="store_true", help="List available agents and exit")
    parser.add_argument("--image", "-i", action="append", help="Image path for multimodal (can repeat)")
    parser.add_argument("--continue", dest="continue_session", action="store_true", help="Resume last conversation")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming (wait for full response)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug logs")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")

    args = parser.parse_args()

    # Setup wizard
    if args.setup:
        from .setup import run_setup
        run_setup()
        return

    # Logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s: %(message)s")

    # Set workspace root for path sandboxing (defaults to CWD)
    import os
    from .tools.security import set_workspace_root
    set_workspace_root(os.getcwd())

    # Load config
    config = Config.load(args.config)

    # CLI args override config
    if args.provider:
        config.provider = args.provider
    if args.model:
        config.model = args.model
    if args.api_key:
        config.api_key = args.api_key

    # Wire up command safety confirmation
    from .tools.terminal import set_confirm_callback

    def _cli_confirm(command: str, reason: str) -> bool:
        """Interactive confirmation for dangerous commands."""
        print(f"\n{YELLOW}  {reason}{RESET}")
        print(f"{DIM}  Command: {command}{RESET}")
        try:
            answer = input(f"{YELLOW}  Allow this command? [y/N]{RESET} ").strip().lower()
            return answer in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    set_confirm_callback(_cli_confirm)

    # Validate — offer setup wizard if no API key configured
    if config.provider != "ollama" and not config.api_key:
        print(f"\n{YELLOW}No API key configured.{RESET}")
        print(f"{DIM}Sol needs an LLM provider to think. Let's fix that.{RESET}\n")
        try:
            answer = input("  Run the setup wizard? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"
        if answer in ("", "y", "yes"):
            from .setup import run_setup
            run_setup()
            # Reload config after setup
            config = Config.load(args.config)
            if config.provider != "ollama" and not config.api_key:
                print(f"\n{YELLOW}Setup didn't configure an API key. Exiting.{RESET}")
                sys.exit(1)
        else:
            print(f"\n{DIM}You can run setup later with: solstice-agent --setup{RESET}")
            print(f"{DIM}Or set OPENAI_API_KEY, ANTHROPIC_API_KEY, or GEMINI_API_KEY{RESET}")
            sys.exit(1)

    # List agents (if multi-agent configured)
    if args.list_agents:
        if config.has_multi_agent():
            agent_configs = config.get_agent_configs()
            print(f"{BOLD}Available agents:{RESET}")
            for name, cfg in agent_configs.items():
                provider_str = cfg.provider or config.provider
                personality_str = cfg.personality_spec if isinstance(cfg.personality_spec, str) else "custom"
                disabled = [k.replace("enable_", "") for k, v in cfg.resolved_tool_flags().items() if not v]
                disabled_str = f" (disabled: {', '.join(disabled)})" if disabled else ""
                print(f"  {GREEN}{name}{RESET}: {provider_str} / {personality_str}{disabled_str}")
            routing = config.get_routing_config()
            if routing:
                print(f"\n{BOLD}Routing:{RESET} strategy={routing.get('strategy', 'channel')}, "
                      f"default={routing.get('default', 'default')}")
        else:
            print(f"{DIM}No multi-agent config. Using single default agent.{RESET}")
        return

    # Skills system
    if not args.no_skills:
        from .agent.skills import init_skills, _get_loader
        init_skills()

    # Multi-agent mode
    if config.has_multi_agent() and not args.no_tools:
        from .agent.router import AgentPool
        agent_configs = config.get_agent_configs()
        pool = AgentPool(agent_configs, global_config=config)
        agent_name = args.agent or "default"
        if agent_name not in agent_configs:
            print(f"{YELLOW}Agent '{agent_name}' not found. Available: {', '.join(agent_configs.keys())}{RESET}")
            sys.exit(1)
        agent = pool.get_agent(agent_name)
    else:
        # Single-agent mode (original behavior)
        try:
            provider = config.create_provider()
        except Exception as e:
            print(f"{YELLOW}Failed to create provider: {e}{RESET}")
            sys.exit(1)

        personality = CODER if args.personality == "coder" else DEFAULT

        skill_loader = None
        if not args.no_skills:
            from .agent.skills import _get_loader
            skill_loader = _get_loader()

        # Context compactor
        from .agent.compactor import ContextCompactor, CompactorConfig
        compactor = ContextCompactor(
            provider=provider,
            config=CompactorConfig(model_name=config.model),
        )

        agent = Agent(
            provider=provider, personality=personality,
            temperature=config.temperature,
            skill_loader=skill_loader, compactor=compactor,
        )

        # Register tools
        if not args.no_tools:
            registry = ToolRegistry()
            registry.load_builtins(
                enable_terminal=not args.no_terminal,
                enable_web=not args.no_web,
                enable_browser=not args.no_browser,
                enable_voice=not args.no_voice,
                enable_memory=not args.no_memory,
                enable_skills=not args.no_skills,
                enable_cron=not args.no_cron,
                enable_registry=not args.no_registry,
                enable_screen=not args.no_screen,
                enable_docker=not args.no_docker,
                enable_presence=not args.no_presence,
                enable_recording=not args.no_recording,
            )
            registry.apply(agent)

    # Scheduler
    if not args.no_cron:
        from .agent.scheduler import init_scheduler, cron_add

        def _agent_factory():
            p = config.create_provider()
            a = Agent(provider=p, personality=personality,
                      temperature=config.temperature, skill_loader=skill_loader)
            r = ToolRegistry()
            r.load_builtins(
                enable_terminal=not args.no_terminal,
                enable_web=not args.no_web,
                enable_cron=False,  # Prevent recursive scheduling
                enable_registry=not args.no_registry,
            )
            r.apply(a)
            return a

        init_scheduler(_agent_factory)

        if args.cron:
            schedule_str, query_str = args.cron
            print(cron_add(schedule_str, query_str))
            if not args.message:
                print(f"{DIM}Scheduler running. Press Ctrl+C to stop.{RESET}")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    print(f"\n{DIM}Scheduler stopped.{RESET}")
                return

    # Persistent memory
    memory = None
    if not args.no_memory:
        from .agent.memory import Memory
        memory = Memory()
        if args.continue_session:
            prev = memory.load_conversation()
            if prev:
                agent.history = prev
                print(f"{DIM}Resumed previous conversation ({len(prev)} messages){RESET}")

    # One-shot mode
    if args.message:
        if args.no_stream:
            response = agent.chat(args.message, images=args.image)
            print(response)
        else:
            _stream_response(agent, args.message, images=args.image)
        if memory:
            memory.save_conversation(agent.get_history())
        return

    # Interactive mode
    agent_label = args.agent if args.agent and config.has_multi_agent() else None
    _interactive(agent, config, memory, agent_label=agent_label, stream=not args.no_stream)


def _stream_response(agent: Agent, message: str, images=None):
    """Stream a response to stdout with tool call indicators."""
    import sys
    started = False
    for event in agent.chat_stream(message, images=images):
        if event.type == "text":
            if not started:
                sys.stdout.write(f"\n{CYAN}")
                started = True
            sys.stdout.write(event.text)
            sys.stdout.flush()
        elif event.type == "tool_calls":
            for tc in event.tool_calls:
                args_str = json.dumps(tc.get("arguments", {}), default=str)
                if len(args_str) > 80:
                    args_str = args_str[:77] + "..."
                print(f"  {DIM}{BLUE}[{tc['name']}]{RESET} {DIM}{args_str}{RESET}")
        elif event.type == "done":
            if started:
                sys.stdout.write(f"{RESET}\n\n")
                sys.stdout.flush()
            elif not started:
                # No text was streamed (edge case)
                print()


BANNER = f"""{CYAN}
                   -j:
              <c)  {{z-  I`      ?z]
              ^/X> ,c] "rI ^f}} ~ct" `1|
            i{{ ,c{{  !; .,. ^_ ^/(' >cnl
         .  .j}}      .'```'.      in|'
    lI   \\r;     !)vL00OZOO0Qz|<     "\\x"
    -cz)' ";  :rQ00000mmmqb#&&hZLv>  ^^
      +jx^  "u0000000000000000w#%hZUI   1n1
 lnu\\>     -C0000000000000000000Oh8kQ).   "]tuc-
   ,\\zz~  <L0000000000000000000000m&#0\\  +/|_'
   ^;`   ;Y000000000000000000000000O&h0[    ^;!!;
   ,])_  rJ000000c|jQ0000000Lt\\X0000qh0C, "jcXu/>
        ;uU00000t_mw?L00000U_)#|c0000kqL+
  `fn\\^ ivYQ0000U|-~x000000Qfji[L000000Q[  1xx;
        ;vXC000000000000000000000000000Q+
I|uXzu>  rXYQ00000000000000000000000000C" >)}};
,iil"    IzXYL000000000000000000000000Q?   .;:
   .<(/)}}  >XXXJQ000000000000000000000L}}  :vcf!
 iuvj1:    ~cXXXJQ0000000000000000QCX[.    l|xv+
      _x/^  ^tXXXXYJL0000000000QCYXn:  .\\r].
          .^  "|zXXXXXXXXYYXXXXXzjI  ,,  ?zz1.
        ./rI     I}}jcXXXXXXXzr1>  .  ^\\n`  :!.
         .  [u?      .`^^^`'      +x,  .
          "jz[  ?r; <;  "' ^<  +z> _?
          ]|: ')X{{ >nI "xl <z< :cxI
              >v\\   .  .l' ivr  <X[          [L>
                           `\\\\{RESET}"""


def _interactive(agent: Agent, config: Config, memory=None, agent_label=None, stream=True):
    """Interactive REPL."""
    label = f" [{agent_label}]" if agent_label else ""
    print(BANNER)
    print(f"  {BOLD}{CYAN}Solstice Agent{RESET}{label} {DIM}v0.2.0{RESET}")
    print(f"  {DIM}{agent.provider.name()} / {agent.personality.name}{RESET}")
    tool_names = [s['name'] for s in agent._tool_schemas] if agent._tool_schemas else ['none']
    streaming_label = "on" if stream else "off"
    print(f"  {DIM}Tools: {len(tool_names)} loaded | Streaming: {streaming_label}{RESET}")
    print(f"  {DIM}Type 'exit' to quit, 'clear' to reset, 'tools' to list{RESET}\n")

    while True:
        try:
            user_input = input(f"{GREEN}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{DIM}Saving...{RESET}")
            if memory:
                memory.save_conversation(agent.get_history())
            print(f"{DIM}Goodbye.{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("exit", "quit", "q"):
            if memory:
                memory.save_conversation(agent.get_history())
            print(f"{DIM}Goodbye.{RESET}")
            break

        if user_input.lower() == "clear":
            agent.clear_history()
            print(f"{DIM}History cleared.{RESET}")
            continue

        if user_input.lower() == "tools":
            for name in tool_names:
                print(f"  {DIM}{name}{RESET}")
            continue

        if user_input.lower() == "history":
            for msg in agent.get_history():
                role = msg["role"]
                content = msg["content"]
                if isinstance(content, str):
                    print(f"{DIM}[{role}]{RESET} {content[:100]}")
            continue

        try:
            if stream:
                _stream_response(agent, user_input)
            else:
                response = agent.chat(user_input)
                print(f"\n{CYAN}{response}{RESET}\n")
        except KeyboardInterrupt:
            print(f"\n{DIM}(interrupted){RESET}")
        except Exception as e:
            print(f"\n{YELLOW}Error: {e}{RESET}\n")


if __name__ == "__main__":
    main()
