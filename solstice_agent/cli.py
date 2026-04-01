"""
CLI Agent
=========
Interactive terminal agent. Type messages, get responses with tool use.

Usage:
    sol                              # Interactive mode
    sol "What's in my cwd?"          # One-shot mode
    sol --provider ollama            # Use local model
    sol --setup                      # Interactive setup wizard
"""

import json
import os
import sys
import time
import argparse
import logging

from .config import (
    Config,
    RUNTIME_PROFILE_NAMES,
    default_config_path,
    find_config_path,
    provider_env_snapshot,
)
from .agent.core import Agent
from .agent.personalities import list_personalities, resolve_personality
from .onboarding import guided_quickstart_options, guided_quickstart_prompt
from .tools.registry import ToolRegistry

# Colors
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
BLUE = "\033[34m"
WHITE = "\033[97m"


def _has_any_provider_credentials() -> bool:
    env = provider_env_snapshot()
    return any(
        env.get(name)
        for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "SOLSTICE_API_KEY")
    )


def _first_run_needs_onboarding(config_path: str | None) -> bool:
    return sys.stdin.isatty() and find_config_path(config_path) is None


def _print_provider_warnings(config: Config):
    env = provider_env_snapshot()
    if config.provider == "gemini" and env.get("GOOGLE_API_KEY") and env.get("GEMINI_API_KEY"):
        print(f"{YELLOW}Both GOOGLE_API_KEY and GEMINI_API_KEY are set.{RESET}")
        print(f"{DIM}Sol will normalize Gemini auth in-process, but keeping only one is cleaner.{RESET}")
        print(f"{DIM}Recommended: remove the stale key and keep the one you actually want to use.{RESET}\n")


def _friendly_runtime_error(error: Exception, config: Config) -> str:
    text = str(error)
    upper = text.upper()
    if config.provider == "gemini" and (
        "API KEY EXPIRED" in upper or "API_KEY_INVALID" in upper or "INVALID_ARGUMENT" in upper
    ):
        return (
            "Your Gemini API key looks invalid or expired.\n"
            "Fix it with `sol --setup`, or refresh GOOGLE_API_KEY / GEMINI_API_KEY and relaunch Sol."
        )
    return f"Error: {error}"


def _run_setup_and_reload(config_path: str | None) -> Config:
    from .setup import run_setup

    run_setup(config_path or str(default_config_path()))
    return Config.load(config_path)


def _guided_quickstart_options(config: Config) -> list[tuple[str, str]]:
    return guided_quickstart_options(config)


def _run_guided_quickstart(agent: Agent, config: Config, stream: bool = True):
    options = _guided_quickstart_options(config)
    print(f"{CYAN}  Let's get started.{RESET}")
    print(f"  {DIM}Tell me what you want help with first. You can type a number or a word like 'files' or 'reminders'.{RESET}")
    print()
    for index, (label, _prompt) in enumerate(options, start=1):
        print(f"  {GREEN}{index}{RESET}  {label}")
    print(f"  {GREEN}s{RESET}  Skip for now")
    print()
    try:
        choice = input(f"  {WHITE}What should I help with first?{RESET} {DIM}[1]{RESET}: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if choice in {"", "1"}:
        selected_prompt = options[0][1]
    elif choice in {"s", "skip"}:
        print()
        return
    elif choice.isdigit() and 1 <= int(choice) <= len(options):
        selected_prompt = options[int(choice) - 1][1]
    else:
        selected_prompt = guided_quickstart_prompt(choice, config=config, allow_fuzzy=False)
        if not selected_prompt:
            print(f"  {DIM}Skipping guided start. Just type normally when you're ready.{RESET}\n")
            return

    print()
    if stream:
        _stream_response(agent, selected_prompt)
    else:
        response = agent.chat(selected_prompt)
        print(f"\n{CYAN}{response}{RESET}\n")


def main():
    did_auto_onboarding = False
    # Ensure UTF-8 output on Windows so Unicode banner characters render correctly.
    # Only reconfigure if stdout has a real underlying buffer and non-UTF-8 encoding
    # (skip when running under pytest capsys or other test capture wrappers).
    if sys.platform == "win32":
        import io
        try:
            enc = getattr(sys.stdout, "encoding", "utf-8") or "utf-8"
            if enc.lower().replace("-", "") != "utf8":
                buf = getattr(sys.stdout, "buffer", None)
                if buf is not None:
                    sys.stdout = io.TextIOWrapper(buf, encoding="utf-8", errors="replace")
            enc = getattr(sys.stderr, "encoding", "utf-8") or "utf-8"
            if enc.lower().replace("-", "") != "utf8":
                buf = getattr(sys.stderr, "buffer", None)
                if buf is not None:
                    sys.stderr = io.TextIOWrapper(buf, encoding="utf-8", errors="replace")
        except Exception:
            pass

    prog = "sol" if "sol" in (sys.argv[0] or "").lower() else "solstice-agent"
    parser = argparse.ArgumentParser(
        prog=prog,
        description="AI agent with real tool use. Not a chatbot wrapper.",
    )
    parser.add_argument("message", nargs="?", help="One-shot message (skip interactive mode)")
    parser.add_argument("--provider", "-p", help="LLM provider (openai, anthropic, gemini, ollama)")
    parser.add_argument("--model", "-m", help="Model name")
    parser.add_argument("--api-key", "-k", help="API key")
    parser.add_argument("--config", "-c", help="Path to config file")
    parser.add_argument("--profile", choices=RUNTIME_PROFILE_NAMES,
                        help="Runtime profile for CLI tool defaults")
    parser.add_argument("--personality", choices=list_personalities(), default="default")
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
    parser.add_argument("--tasks", action="store_true", help="Print tracked tasks and exit")
    parser.add_argument("--clear-tasks", action="store_true", help="Clear tracked tasks and exit")
    parser.add_argument("--subagents", action="store_true", help="Print sub-agent runs and exit")
    parser.add_argument("--workflows", action="store_true", help="Print workflows and exit")
    parser.add_argument("--workflow-status", help="Print a workflow status by workflow ID and exit")
    parser.add_argument("--workflow-events", help="Print recent workflow events by workflow ID and exit")
    parser.add_argument("--workflow-export", nargs="+", metavar="WORKFLOW_ARG", help="Export a workflow or snapshot as JSON and exit")
    parser.add_argument("--workflow-snapshot", nargs="+", metavar="WORKFLOW_ARG", help="Create a workflow snapshot and exit")
    parser.add_argument("--resume-workflow", help="Resume a workflow by workflow ID and exit")
    parser.add_argument("--cancel-workflow", help="Cancel a workflow by workflow ID and exit")
    parser.add_argument(
        "--retry-workflow-branch",
        nargs=2,
        metavar=("WORKFLOW_ID", "NODE_ID"),
        help="Retry a failed workflow branch rooted at a node and exit",
    )
    parser.add_argument(
        "--disable-workflow-node",
        nargs=2,
        metavar=("WORKFLOW_ID", "NODE_ID"),
        help="Disable a pending workflow node and exit",
    )
    parser.add_argument(
        "--enable-workflow-node",
        nargs=2,
        metavar=("WORKFLOW_ID", "NODE_ID"),
        help="Enable a disabled workflow node and exit",
    )
    parser.add_argument(
        "--remove-workflow-node",
        nargs=2,
        metavar=("WORKFLOW_ID", "NODE_ID"),
        help="Remove a pending workflow node and exit",
    )
    parser.add_argument(
        "--rewire-workflow",
        nargs="+",
        metavar="WORKFLOW_ARG",
        help="Add or remove a workflow dependency edge and exit",
    )
    parser.add_argument(
        "--retry-workflow-node",
        nargs=2,
        metavar=("WORKFLOW_ID", "NODE_ID"),
        help="Retry a workflow node and exit",
    )
    parser.add_argument(
        "--set-workflow-priority",
        nargs=3,
        metavar=("WORKFLOW_ID", "NODE_ID", "PRIORITY"),
        help="Set a workflow node priority and exit",
    )
    parser.add_argument(
        "--set-workflow-edge",
        nargs=4,
        metavar=("WORKFLOW_ID", "NODE_ID", "DEPENDENCY_NODE_ID", "POLICY"),
        help="Update a workflow edge policy and exit",
    )
    parser.add_argument(
        "--add-workflow-node",
        nargs=3,
        metavar=("WORKFLOW_ID", "NODE_ID", "PROMPT"),
        help="Add a workflow node with the given prompt and exit",
    )
    parser.add_argument("--subagent-graph", nargs="?", const="", help="Print sub-agent graph data and exit")
    parser.add_argument("--subagent-result", help="Print a sub-agent result by run ID and exit")
    parser.add_argument("--subagent-progress", help="Print sub-agent progress by run ID and exit")
    parser.add_argument("--resume-subagent", help="Resume a saved sub-agent run by run ID and exit")
    parser.add_argument("--cancel-subagent", help="Request cancellation for a sub-agent run and exit")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug logs")
    parser.add_argument("--setup", action="store_true", help="Run interactive setup wizard")
    parser.add_argument("--outreach-load-seeds", nargs=2, metavar=("CAMPAIGN_JSON", "LEADS_JSON"),
                        help="Load outreach campaign and lead seeds into the local outreach store")
    parser.add_argument("--outreach-store-root",
                        help="Optional outreach store root to use with --outreach-load-seeds")
    parser.add_argument("--replace-seeds", action="store_true",
                        help="Overwrite an existing seeded campaign and update matching leads by email")
    parser.add_argument("--outreach-prepare-drafts", metavar="CAMPAIGN_ID",
                        help="Prepare compose artifacts for a campaign's leads")
    parser.add_argument("--email-type", default="initial",
                        help="Email type for --outreach-prepare-drafts (default: initial)")
    parser.add_argument("--stage", default="qualified",
                        help="Lead stage filter for --outreach-prepare-drafts (default: qualified)")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max drafts to prepare with --outreach-prepare-drafts")
    parser.add_argument("--custom-angle", default="",
                        help="Optional shared angle to inject into prepared draft contexts")
    parser.add_argument("--outreach-prepare-replies", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Prepare reply compose artifacts for pending inbound replies")
    parser.add_argument("--auto-safe-only", action="store_true",
                        help="With --outreach-prepare-replies, only auto-prepare replies classified as safe")
    parser.add_argument("--outreach-review-replies", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Show pending reply triage for a campaign or all campaigns")
    parser.add_argument("--outreach-pipeline-memory", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Show tagged pipeline memory for a campaign or all campaigns")
    parser.add_argument("--outreach-analytics", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Show outreach analytics for a campaign or all campaigns")
    parser.add_argument("--outreach-next-actions", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Show ranked next best actions for a campaign or all campaigns")
    parser.add_argument("--outreach-export-crm", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Export connector-ready CRM records for a campaign or all campaigns")
    parser.add_argument("--outreach-export-meetings", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Export meeting handoff records for demo or converted leads")
    parser.add_argument("--outreach-push-crm", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Push CRM records to a webhook endpoint")
    parser.add_argument("--outreach-push-meetings", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Push meeting handoff records to a webhook endpoint")
    parser.add_argument("--crm-webhook", help="Webhook URL for CRM push operations")
    parser.add_argument("--meeting-webhook", help="Webhook URL for meeting push operations")
    parser.add_argument("--outreach-autoreply-safe", nargs="?", const="",
                        metavar="CAMPAIGN_ID",
                        help="Use the configured LLM to draft/send safe pending replies for a campaign or all campaigns")
    parser.add_argument("--booking-link",
                        help="Booking link to use for auto-handling demo requests")
    parser.add_argument("--booking-cta",
                        help="Intro line to place before the booking link in demo replies")
    parser.add_argument("--booking-label",
                        help="Human label for the booking link")

    args = parser.parse_args()

    # Setup wizard
    if args.setup:
        _run_setup_and_reload(args.config)
        return

    if not args.setup and not args.message and _first_run_needs_onboarding(args.config):
        print(f"\n{CYAN}First launch detected. Sol needs a quick setup before it can think.{RESET}\n")
        _run_setup_and_reload(args.config)
        did_auto_onboarding = True

    # Load config before branches that rely on config-backed defaults.
    config = Config.load(args.config)

    if args.outreach_load_seeds:
        from .outreach import load_seed_bundle

        campaign_seed_path, leads_seed_path = args.outreach_load_seeds
        print(
            load_seed_bundle(
                campaign_seed_path=campaign_seed_path,
                leads_seed_path=leads_seed_path,
                store_root=args.outreach_store_root,
                replace=args.replace_seeds,
            )
        )
        return

    if args.outreach_prepare_drafts:
        from .outreach.composer import outreach_prepare_draft_batch

        print(
            outreach_prepare_draft_batch(
                campaign_id=args.outreach_prepare_drafts,
                email_type=args.email_type,
                limit=args.limit,
                stage=args.stage,
                custom_angle=args.custom_angle,
            )
        )
        return

    if args.outreach_prepare_replies is not None:
        from .outreach.reply_triage import outreach_prepare_reply_batch

        print(
            outreach_prepare_reply_batch(
                campaign_id=args.outreach_prepare_replies,
                limit=args.limit,
                auto_safe_only=args.auto_safe_only,
            )
        )
        return

    if args.outreach_review_replies is not None:
        from .outreach.reply_triage import outreach_reply_review_queue

        print(
            outreach_reply_review_queue(
                campaign_id=args.outreach_review_replies,
                limit=args.limit,
            )
        )
        return

    if args.outreach_pipeline_memory is not None:
        from .outreach.reply_triage import outreach_pipeline_snapshot

        print(outreach_pipeline_snapshot(campaign_id=args.outreach_pipeline_memory))
        return

    if args.outreach_analytics is not None:
        from .outreach.analytics import outreach_analytics

        print(outreach_analytics(campaign_id=args.outreach_analytics))
        return

    if args.outreach_next_actions is not None:
        from .outreach.analytics import outreach_next_best_actions

        print(outreach_next_best_actions(campaign_id=args.outreach_next_actions, limit=args.limit))
        return

    if args.outreach_export_crm is not None:
        from .outreach.sync_queue import outreach_export_crm

        print(outreach_export_crm(campaign_id=args.outreach_export_crm))
        return

    if args.outreach_export_meetings is not None:
        from .outreach.sync_queue import outreach_export_meeting_queue

        print(outreach_export_meeting_queue(campaign_id=args.outreach_export_meetings))
        return

    if args.outreach_push_crm is not None:
        from .outreach.sync_queue import outreach_push_crm

        print(
            outreach_push_crm(
                campaign_id=args.outreach_push_crm,
                webhook_url=args.crm_webhook or config.outreach_crm_webhook,
            )
        )
        return

    if args.outreach_push_meetings is not None:
        from .outreach.sync_queue import outreach_push_meeting_queue

        print(
            outreach_push_meeting_queue(
                campaign_id=args.outreach_push_meetings,
                webhook_url=args.meeting_webhook or config.outreach_meeting_webhook,
            )
        )
        return

    # CLI args override config
    config.runtime_profile = args.profile or config.runtime_profile or "local_safe"
    if args.provider:
        config.provider = args.provider
    if args.model:
        config.model = args.model
    if args.api_key:
        config.api_key = args.api_key

    # Logging
    level = logging.DEBUG if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(name)s: %(message)s")

    # Set workspace root for path sandboxing (defaults to configured root or CWD)
    from .tools.security import set_workspace_root
    set_workspace_root(config.workspace_root or os.getcwd())

    _print_provider_warnings(config)

    if args.outreach_autoreply_safe is not None:
        try:
            provider = config.create_provider()
        except Exception as e:
            print(f"{YELLOW}Failed to create provider: {e}{RESET}")
            sys.exit(1)

        from .outreach.autoreply import outreach_autoreply_safe

        print(
            outreach_autoreply_safe(
                provider=provider,
                campaign_id=args.outreach_autoreply_safe,
                limit=args.limit,
                booking_link=args.booking_link or config.outreach_booking_link,
                booking_cta=args.booking_cta or config.outreach_booking_cta,
                booking_label=args.booking_label or config.outreach_booking_label,
            )
        )
        return

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
            _run_setup_and_reload(args.config)
            # Reload config after setup
            config = Config.load(args.config)
            if config.provider != "ollama" and not config.api_key:
                print(f"\n{YELLOW}Setup didn't configure an API key. Exiting.{RESET}")
                sys.exit(1)
        else:
            print(f"\n{DIM}You can run setup later with: sol --setup{RESET}")
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
                disabled = [
                    k.replace("enable_", "")
                    for k, v in cfg.resolved_tool_flags(base_flags=config.resolve_tool_flags("developer")).items()
                    if not v
                ]
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

        personality = resolve_personality(args.personality)

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
        agent.auto_track_tasks = True

        # Register tools
        if not args.no_tools:
            registry = ToolRegistry()
            cli_flags = config.resolve_tool_flags(
                "developer",
                overrides={
                    "enable_terminal": False if args.no_terminal else None,
                    "enable_web": False if args.no_web else None,
                    "enable_browser": False if args.no_browser else None,
                    "enable_voice": False if args.no_voice else None,
                    "enable_memory": False if args.no_memory else None,
                    "enable_skills": False if args.no_skills else None,
                    "enable_cron": False if args.no_cron else None,
                    "enable_registry": False if args.no_registry else None,
                    "enable_screen": False if args.no_screen else None,
                    "enable_docker": False if args.no_docker else None,
                    "enable_presence": False if args.no_presence else None,
                    "enable_recording": False if args.no_recording else None,
                },
            )
            registry.load_builtins(**cli_flags)
            registry.apply(agent)
    if hasattr(agent, "auto_track_tasks"):
        agent.auto_track_tasks = True

    if args.tasks:
        from .agent.tasks import task_list
        print(task_list())
        return

    if args.clear_tasks:
        from .agent.tasks import task_clear
        print(task_clear())
        return

    if args.subagents:
        if "subagent_list" in getattr(agent, "_tools", {}):
            print(agent._tools["subagent_list"]())
        else:
            print("Sub-agent tools are not available.")
        return

    if args.workflows:
        if "workflow_list" in getattr(agent, "_tools", {}):
            print(agent._tools["workflow_list"]())
        else:
            print("Workflow tools are not available.")
        return

    if args.workflow_status:
        if "workflow_status" in getattr(agent, "_tools", {}):
            print(agent._tools["workflow_status"](args.workflow_status))
        else:
            print("Workflow tools are not available.")
        return

    if args.workflow_events:
        if "workflow_events" in getattr(agent, "_tools", {}):
            print(agent._tools["workflow_events"](args.workflow_events))
        else:
            print("Workflow tools are not available.")
        return

    if args.workflow_export:
        if "workflow_export" in getattr(agent, "_tools", {}):
            workflow_id = args.workflow_export[0]
            snapshot_id = args.workflow_export[1] if len(args.workflow_export) > 1 else ""
            print(agent._tools["workflow_export"](workflow_id, snapshot_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.workflow_snapshot:
        if "workflow_snapshot" in getattr(agent, "_tools", {}):
            workflow_id = args.workflow_snapshot[0]
            label = " ".join(args.workflow_snapshot[1:]) if len(args.workflow_snapshot) > 1 else ""
            print(agent._tools["workflow_snapshot"](workflow_id, label))
        else:
            print("Workflow tools are not available.")
        return

    if args.resume_workflow:
        if "workflow_resume" in getattr(agent, "_tools", {}):
            print(agent._tools["workflow_resume"](args.resume_workflow))
        else:
            print("Workflow tools are not available.")
        return

    if args.cancel_workflow:
        if "workflow_cancel" in getattr(agent, "_tools", {}):
            print(agent._tools["workflow_cancel"](args.cancel_workflow))
        else:
            print("Workflow tools are not available.")
        return

    if args.retry_workflow_branch:
        if "workflow_retry_branch" in getattr(agent, "_tools", {}):
            workflow_id, node_id = args.retry_workflow_branch
            print(agent._tools["workflow_retry_branch"](workflow_id, node_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.disable_workflow_node:
        if "workflow_disable_node" in getattr(agent, "_tools", {}):
            workflow_id, node_id = args.disable_workflow_node
            print(agent._tools["workflow_disable_node"](workflow_id, node_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.enable_workflow_node:
        if "workflow_enable_node" in getattr(agent, "_tools", {}):
            workflow_id, node_id = args.enable_workflow_node
            print(agent._tools["workflow_enable_node"](workflow_id, node_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.remove_workflow_node:
        if "workflow_remove_node" in getattr(agent, "_tools", {}):
            workflow_id, node_id = args.remove_workflow_node
            print(agent._tools["workflow_remove_node"](workflow_id, node_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.rewire_workflow:
        if "workflow_rewire_dependency" in getattr(agent, "_tools", {}):
            if len(args.rewire_workflow) < 4:
                print("Usage: --rewire-workflow <workflow_id> <node_id> <dependency_node_id> <action> [policy]")
            else:
                workflow_id, node_id, dependency_node_id, action = args.rewire_workflow[:4]
                policy = args.rewire_workflow[4] if len(args.rewire_workflow) > 4 else "block"
                print(agent._tools["workflow_rewire_dependency"](workflow_id, node_id, dependency_node_id, action, policy))
        else:
            print("Workflow tools are not available.")
        return

    if args.retry_workflow_node:
        if "workflow_retry_node" in getattr(agent, "_tools", {}):
            workflow_id, node_id = args.retry_workflow_node
            print(agent._tools["workflow_retry_node"](workflow_id, node_id))
        else:
            print("Workflow tools are not available.")
        return

    if args.set_workflow_priority:
        if "workflow_set_priority" in getattr(agent, "_tools", {}):
            workflow_id, node_id, priority_text = args.set_workflow_priority
            print(agent._tools["workflow_set_priority"](workflow_id, node_id, int(priority_text)))
        else:
            print("Workflow tools are not available.")
        return

    if args.set_workflow_edge:
        if "workflow_update_edge_policy" in getattr(agent, "_tools", {}):
            workflow_id, node_id, dependency_node_id, policy = args.set_workflow_edge
            print(agent._tools["workflow_update_edge_policy"](workflow_id, node_id, dependency_node_id, policy))
        else:
            print("Workflow tools are not available.")
        return

    if args.add_workflow_node:
        if "workflow_add_node" in getattr(agent, "_tools", {}):
            workflow_id, node_id, prompt = args.add_workflow_node
            print(
                agent._tools["workflow_add_node"](
                    workflow_id,
                    node_id,
                    prompt,
                    [],
                    "{}",
                    [],
                    "",
                    False,
                    True,
                    None,
                    None,
                    None,
                    None,
                    "",
                    None,
                    "",
                    0,
                    "never",
                    0,
                )
            )
        else:
            print("Workflow tools are not available.")
        return

    if args.subagent_graph is not None:
        if "subagent_graph" in getattr(agent, "_tools", {}):
            print(agent._tools["subagent_graph"](args.subagent_graph or ""))
        else:
            print("Sub-agent tools are not available.")
        return

    if args.subagent_result:
        if "subagent_result" in getattr(agent, "_tools", {}):
            print(agent._tools["subagent_result"](args.subagent_result))
        else:
            print("Sub-agent tools are not available.")
        return

    if args.subagent_progress:
        if "subagent_progress" in getattr(agent, "_tools", {}):
            print(agent._tools["subagent_progress"](args.subagent_progress))
        else:
            print("Sub-agent tools are not available.")
        return

    if args.resume_subagent:
        if "resume_subagent" in getattr(agent, "_tools", {}):
            print(agent._tools["resume_subagent"](args.resume_subagent))
        else:
            print("Sub-agent tools are not available.")
        return

    if args.cancel_subagent:
        if "cancel_subagent" in getattr(agent, "_tools", {}):
            print(agent._tools["cancel_subagent"](args.cancel_subagent))
        else:
            print("Sub-agent tools are not available.")
        return

    # Scheduler
    if not args.no_cron:
        from .agent.scheduler import init_scheduler, cron_add

        def _agent_factory():
            p = config.create_provider()
            a = Agent(provider=p, personality=personality,
                      temperature=config.temperature, skill_loader=skill_loader)
            r = ToolRegistry()
            cli_flags = config.resolve_tool_flags(
                "developer",
                overrides={
                    "enable_terminal": False if args.no_terminal else None,
                    "enable_web": False if args.no_web else None,
                    "enable_browser": False if args.no_browser else None,
                    "enable_voice": False if args.no_voice else None,
                    "enable_memory": False if args.no_memory else None,
                    "enable_skills": False if args.no_skills else None,
                    "enable_cron": False,
                    "enable_registry": False if args.no_registry else None,
                    "enable_screen": False if args.no_screen else None,
                    "enable_docker": False if args.no_docker else None,
                    "enable_presence": False if args.no_presence else None,
                    "enable_recording": False if args.no_recording else None,
                },
            )
            r.load_builtins(**cli_flags)
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
            prev = memory.resume_conversation()
            if prev:
                agent.history = prev
                print(f"{DIM}Resumed conversation {memory.session_id} ({len(prev)} messages){RESET}")

    # One-shot mode
    if args.message:
        try:
            if args.no_stream:
                response = agent.chat(args.message, images=args.image)
                print(response)
            else:
                _stream_response(agent, args.message, images=args.image)
        except Exception as e:
            print(f"{YELLOW}{_friendly_runtime_error(e, config)}{RESET}")
            sys.exit(1)
        if memory:
            memory.save_conversation(agent.get_history())
        return

    # Interactive mode
    agent_label = args.agent if args.agent and config.has_multi_agent() else None
    _interactive(
        agent,
        config,
        memory,
        agent_label=agent_label,
        stream=not args.no_stream,
        guided_start=did_auto_onboarding and not args.continue_session,
    )


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

                               ▂▄▄▄▄▁                         ▂▄▄▄▄▁
                             ▁▆▅▃▃▇█▇▄                       ▆▇█▄▃▃▆▄
                             ▁█▆▃████▅                       ████▆▃█▆
                             ▁▆▇████▆▃                       ▅▇████▆▄
                               ▂▃▃▃▃▁    ▃▅             ▅▃    ▂▃▃▃▃▁
                                         ▄█             █▄
                                         ▂▅▅▅▁        ▃▄▅▃
                                          ▁▃▃▇▆▆▆▆▆▆▆▆▄▃▁
                                             ▁▁▁▁▁▁▁▁▁▁
{RESET}"""


def _interactive(agent: Agent, config: Config, memory=None, agent_label=None, stream=True, guided_start: bool = False):
    """Interactive REPL."""
    label = f" [{agent_label}]" if agent_label else ""
    print(BANNER)
    from . import __version__
    print(f"  {BOLD}{CYAN}Solstice Agent{RESET}{label} {DIM}v{__version__}{RESET}")
    print(f"  {DIM}{agent.provider.name()} / {agent.personality.name}{RESET}")
    tool_names = [s['name'] for s in agent._tool_schemas] if agent._tool_schemas else ['none']
    streaming_label = "on" if stream else "off"
    print(f"  {DIM}Tools: {len(tool_names)} loaded | Streaming: {streaming_label}{RESET}")
    print(
        f"  {DIM}Type 'exit' to quit, 'clear' to reset, 'tools' to list, '/start', '/tasks', '/subagents', '/workflows', "
        f"'/workflow <id>', '/workflow-events <id>', '/workflow-export <workflow_id> [snapshot_id]', '/workflow-snapshot <workflow_id> [label]', '/add-workflow-node <workflow_id> <node_id> <prompt>', '/retry-workflow-node <workflow_id> <node_id>', '/retry-workflow-branch <workflow_id> <node_id>', "
        f"'/disable-workflow-node <workflow_id> <node_id>', '/enable-workflow-node <workflow_id> <node_id>', '/remove-workflow-node <workflow_id> <node_id>', '/rewire-workflow <workflow_id> <node_id> <dependency_node_id> <action> [policy]', "
        f"'/set-workflow-priority <workflow_id> <node_id> <priority>', '/set-workflow-edge <workflow_id> <node_id> <dependency_node_id> <policy>', "
        f"'/subagent-graph', '/subagent-progress <id>', '/resume-subagent <id>', or '/cancel-subagent <id>'{RESET}\n"
    )

    if guided_start:
        _run_guided_quickstart(agent, config, stream=stream)

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

        if user_input.lower() == "/start":
            _run_guided_quickstart(agent, config, stream=stream)
            continue

        if user_input.lower() == "history":
            for msg in agent.get_history():
                role = msg["role"]
                content = msg["content"]
                if isinstance(content, str):
                    print(f"{DIM}[{role}]{RESET} {content[:100]}")
            continue

        if user_input.lower() == "/tasks":
            from .agent.tasks import task_list
            print(task_list())
            continue

        if user_input.lower() == "/clear-tasks":
            from .agent.tasks import task_clear
            print(task_clear())
            continue

        if user_input.lower() == "/subagents":
            if "subagent_list" in getattr(agent, "_tools", {}):
                print(agent._tools["subagent_list"]())
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower() == "/workflows":
            if "workflow_list" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_list"]())
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/workflow "):
            workflow_id = user_input.split(" ", 1)[1].strip()
            if "workflow_status" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_status"](workflow_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/workflow-events "):
            workflow_id = user_input.split(" ", 1)[1].strip()
            if "workflow_events" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_events"](workflow_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/workflow-export "):
            parts = user_input.split(" ", 2)
            workflow_id = parts[1].strip() if len(parts) > 1 else ""
            snapshot_id = parts[2].strip() if len(parts) > 2 else ""
            if "workflow_export" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_export"](workflow_id, snapshot_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/workflow-snapshot "):
            parts = user_input.split(" ", 2)
            workflow_id = parts[1].strip() if len(parts) > 1 else ""
            label = parts[2].strip() if len(parts) > 2 else ""
            if "workflow_snapshot" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_snapshot"](workflow_id, label))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/resume-workflow "):
            workflow_id = user_input.split(" ", 1)[1].strip()
            if "workflow_resume" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_resume"](workflow_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/cancel-workflow "):
            workflow_id = user_input.split(" ", 1)[1].strip()
            if "workflow_cancel" in getattr(agent, "_tools", {}):
                print(agent._tools["workflow_cancel"](workflow_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/add-workflow-node "):
            parts = user_input.split(" ", 3)
            if len(parts) < 4:
                print("Usage: /add-workflow-node <workflow_id> <node_id> <prompt>")
                continue
            if "workflow_add_node" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id, prompt = parts
                print(
                    agent._tools["workflow_add_node"](
                        workflow_id,
                        node_id,
                        prompt,
                        [],
                        "{}",
                        [],
                        "",
                        False,
                        True,
                        None,
                        None,
                        None,
                        None,
                        "",
                        None,
                        "",
                        0,
                        "never",
                        0,
                    )
                )
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/retry-workflow-node "):
            parts = user_input.split(" ", 2)
            if len(parts) < 3:
                print("Usage: /retry-workflow-node <workflow_id> <node_id>")
                continue
            if "workflow_retry_node" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id = parts
                print(agent._tools["workflow_retry_node"](workflow_id, node_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/retry-workflow-branch "):
            parts = user_input.split(" ", 2)
            if len(parts) < 3:
                print("Usage: /retry-workflow-branch <workflow_id> <node_id>")
                continue
            if "workflow_retry_branch" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id = parts
                print(agent._tools["workflow_retry_branch"](workflow_id, node_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/disable-workflow-node "):
            parts = user_input.split(" ", 2)
            if len(parts) < 3:
                print("Usage: /disable-workflow-node <workflow_id> <node_id>")
                continue
            if "workflow_disable_node" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id = parts
                print(agent._tools["workflow_disable_node"](workflow_id, node_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/enable-workflow-node "):
            parts = user_input.split(" ", 2)
            if len(parts) < 3:
                print("Usage: /enable-workflow-node <workflow_id> <node_id>")
                continue
            if "workflow_enable_node" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id = parts
                print(agent._tools["workflow_enable_node"](workflow_id, node_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/remove-workflow-node "):
            parts = user_input.split(" ", 2)
            if len(parts) < 3:
                print("Usage: /remove-workflow-node <workflow_id> <node_id>")
                continue
            if "workflow_remove_node" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id = parts
                print(agent._tools["workflow_remove_node"](workflow_id, node_id))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/rewire-workflow "):
            parts = user_input.split(" ")
            if len(parts) < 5:
                print("Usage: /rewire-workflow <workflow_id> <node_id> <dependency_node_id> <action> [policy]")
                continue
            if "workflow_rewire_dependency" in getattr(agent, "_tools", {}):
                workflow_id, node_id, dependency_node_id, action = parts[1:5]
                policy = parts[5] if len(parts) > 5 else "block"
                print(agent._tools["workflow_rewire_dependency"](workflow_id, node_id, dependency_node_id, action, policy))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/set-workflow-priority "):
            parts = user_input.split(" ", 3)
            if len(parts) < 4:
                print("Usage: /set-workflow-priority <workflow_id> <node_id> <priority>")
                continue
            if "workflow_set_priority" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id, priority_text = parts
                print(agent._tools["workflow_set_priority"](workflow_id, node_id, int(priority_text)))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower().startswith("/set-workflow-edge "):
            parts = user_input.split(" ", 4)
            if len(parts) < 5:
                print("Usage: /set-workflow-edge <workflow_id> <node_id> <dependency_node_id> <policy>")
                continue
            if "workflow_update_edge_policy" in getattr(agent, "_tools", {}):
                _, workflow_id, node_id, dependency_node_id, policy = parts
                print(agent._tools["workflow_update_edge_policy"](workflow_id, node_id, dependency_node_id, policy))
            else:
                print("Workflow tools are not available.")
            continue

        if user_input.lower() == "/subagent-graph":
            if "subagent_graph" in getattr(agent, "_tools", {}):
                print(agent._tools["subagent_graph"](""))
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower().startswith("/subagent-graph "):
            run_id = user_input.split(" ", 1)[1].strip()
            if "subagent_graph" in getattr(agent, "_tools", {}):
                print(agent._tools["subagent_graph"](run_id))
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower().startswith("/subagent "):
            run_id = user_input.split(" ", 1)[1].strip()
            if "subagent_result" in getattr(agent, "_tools", {}):
                print(agent._tools["subagent_result"](run_id))
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower().startswith("/subagent-progress "):
            run_id = user_input.split(" ", 1)[1].strip()
            if "subagent_progress" in getattr(agent, "_tools", {}):
                print(agent._tools["subagent_progress"](run_id))
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower().startswith("/resume-subagent "):
            run_id = user_input.split(" ", 1)[1].strip()
            if "resume_subagent" in getattr(agent, "_tools", {}):
                print(agent._tools["resume_subagent"](run_id))
            else:
                print("Sub-agent tools are not available.")
            continue

        if user_input.lower().startswith("/cancel-subagent "):
            run_id = user_input.split(" ", 1)[1].strip()
            if "cancel_subagent" in getattr(agent, "_tools", {}):
                print(agent._tools["cancel_subagent"](run_id))
            else:
                print("Sub-agent tools are not available.")
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
            print(f"\n{YELLOW}{_friendly_runtime_error(e, config)}{RESET}\n")


if __name__ == "__main__":
    main()
