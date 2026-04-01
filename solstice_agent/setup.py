"""
Interactive setup and first-run onboarding.

Run: sol --setup
"""

import importlib.util
import os
import random
import sys
import time
from pathlib import Path

import httpx

from .config import default_config_path

# Colors
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
WHITE = "\033[97m"


PROFILE_CHOICES = {
    "1": "local_safe",
    "2": "developer",
    "3": "gateway",
    "4": "power_user",
}

PROFILE_LABELS = {
    "1": ("Everyday", "Safe default for most people. Files, memory, web, and scheduled reminders."),
    "2": ("Builder", "Best for coding and power use. Adds browser automation, terminal, and containers."),
    "3": ("Messages", "Best for running Sol behind chat apps or a gateway server."),
    "4": ("Full Access", "Broad local access for advanced users who know they want it."),
}


def _type(text: str, pause: float = 0.01):
    """Print with a subtle typing effect."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        if char in ".!?\n":
            time.sleep(pause * 8)
        elif char == ",":
            time.sleep(pause * 4)
        else:
            time.sleep(pause)
    print()


def _say(text: str):
    """Agent speaks."""
    time.sleep(0.15)
    print(f"  {CYAN}{text}{RESET}")


def _say_dim(text: str):
    """Quieter context/instructions."""
    print(f"  {DIM}{text}{RESET}")


def _ask(prompt: str, default: str = None) -> str:
    """Ask for input conversationally."""
    if default:
        display = f"  {WHITE}{prompt}{RESET} {DIM}[{default}]{RESET}: "
    else:
        display = f"  {WHITE}{prompt}{RESET}: "
    try:
        value = input(display).strip()
        return value if value else (default or "")
    except (EOFError, KeyboardInterrupt):
        print(f"\n\n  {CYAN}No worries. Come back whenever you're ready.{RESET}\n")
        sys.exit(0)


def _ask_yn(prompt: str, default: bool = True) -> bool:
    """Yes/no with friendly tone."""
    hint = "Y/n" if default else "y/N"
    try:
        value = input(f"  {WHITE}{prompt}{RESET} {DIM}[{hint}]{RESET}: ").strip().lower()
        if not value:
            return default
        return value in ("y", "yes", "yep", "yeah", "sure", "yea", "ya")
    except (EOFError, KeyboardInterrupt):
        print(f"\n\n  {CYAN}No worries. Come back whenever you're ready.{RESET}\n")
        sys.exit(0)


def _wait():
    """Small breathing room between sections."""
    time.sleep(0.4)


def _yaml_quote(value: str) -> str:
    """Quote free-form strings so YAML keeps them literal."""
    return "'" + value.replace("'", "''") + "'"


def _provider_extra_installed(provider: str) -> bool:
    """Best-effort check for optional provider SDKs."""
    module_name = {
        "openai": "openai",
        "anthropic": "anthropic",
        "gemini": "google.genai",
        "ollama": "",
    }.get(provider, "")
    return not module_name or importlib.util.find_spec(module_name) is not None


def _provider_install_hint(provider: str) -> str:
    if provider == "openai":
        return "pip install \"solstice-agent[openai]\""
    if provider == "anthropic":
        return "pip install \"solstice-agent[anthropic]\""
    if provider == "gemini":
        return "pip install \"solstice-agent[gemini]\""
    return ""


def _detected_provider_keys() -> list[tuple[str, str]]:
    detections: list[tuple[str, str]] = []
    for provider, env_names in (
        ("openai", ("OPENAI_API_KEY",)),
        ("anthropic", ("ANTHROPIC_API_KEY",)),
        ("gemini", ("GEMINI_API_KEY", "GOOGLE_API_KEY")),
    ):
        for env_name in env_names:
            value = os.getenv(env_name, "")
            if value:
                detections.append((provider, env_name))
                break
    return detections


def _choose_provider() -> tuple[str, str]:
    """Ask for a provider using plain language labels."""
    detections = _detected_provider_keys()
    detected_provider = detections[0][0] if len(detections) == 1 else ""

    _say("First, let's pick the model company or app you want me to use.")
    if detected_provider:
        detected_name = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "gemini": "Google Gemini",
        }.get(detected_provider, detected_provider)
        _say_dim(f"I found an existing API key for {detected_name}, so I'll recommend that option.")
    elif len(detections) > 1:
        _say_dim("I found keys for more than one provider, so it's best to choose explicitly.")
    print()
    print(f"  {GREEN}1{RESET}  {BOLD}OpenAI{RESET}        - Easiest cloud setup for most people.")
    print(f"  {GREEN}2{RESET}  {BOLD}Anthropic{RESET}     - Claude models.")
    print(f"  {GREEN}3{RESET}  {BOLD}Google Gemini{RESET} - Gemini models.")
    print(f"  {GREEN}4{RESET}  {BOLD}Ollama{RESET}        - Fully local models on your own machine.")
    print(f"  {GREEN}5{RESET}  {BOLD}Something else{RESET} - Your own OpenAI-compatible endpoint.")
    print()

    default_choice = {"openai": "1", "anthropic": "2", "gemini": "3"}.get(detected_provider, "1")
    choice = _ask("Which one sounds right? [1-5]", default=default_choice)
    provider_map = {"1": "openai", "2": "anthropic", "3": "gemini", "4": "ollama", "5": "openai"}
    return provider_map.get(choice, "openai"), choice


def _choose_runtime_profile() -> str:
    """Ask how the user wants Sol to run."""
    _say("Next: pick how hands-on you want me to be on this computer.")
    _say("If you're not sure, choose Everyday. That's the safest default for most people.")
    print()
    for key in ("1", "2", "3", "4"):
        label, description = PROFILE_LABELS[key]
        print(f"  {GREEN}{key}{RESET}  {BOLD}{label}{RESET} - {description}")
    print()
    choice = _ask("Which profile should I start with? [1-4]", default="1")
    return PROFILE_CHOICES.get(choice, "local_safe")


def _next_steps(provider: str, profile: str, workspace_root: str, setup_gateway: bool) -> list[str]:
    """Return the most relevant next commands for the chosen path."""
    steps = []
    if provider == "ollama":
        steps.append("ollama serve               # Start the local model server if it is not already running")
    if profile == "gateway":
        steps.append(f"sol-gateway --profile gateway --workspace-root \"{workspace_root}\"")
        steps.append("sol                         # Open a local chat against the same config")
    elif setup_gateway:
        steps.append("sol                         # Start a local conversation first")
        steps.append(f"sol-gateway --workspace-root \"{workspace_root}\"")
    else:
        steps.append("sol                         # Start a conversation")
        steps.append("sol \"hello\"                 # Quick one-liner")
    return steps


def _starter_prompts(profile: str) -> list[str]:
    prompts = [
        "What can you help me with on this computer?",
        "Look through my workspace and explain what is here.",
    ]
    if profile == "developer":
        prompts.append("Open this repo and tell me what looks risky.")
    elif profile == "gateway":
        prompts.append("Help me connect this to my messaging apps.")
    else:
        prompts.append("Set a daily reminder or recurring check for me.")
    return prompts


def _validate_workspace_root(workspace_root: str) -> tuple[str, str]:
    path = Path(workspace_root).expanduser()
    if path.exists() and path.is_dir():
        return ("ok", f"Workspace root exists: {path}")
    if path.exists():
        return ("warn", f"Workspace root is not a directory: {path}")
    return ("warn", f"Workspace root does not exist yet: {path}")


def _validate_provider_path(provider: str, has_api_key: bool) -> tuple[str, str]:
    if provider == "ollama":
        return ("ok", "Ollama selected. No cloud API key required.")
    if not _provider_extra_installed(provider):
        return ("warn", f"Provider package missing. Install with: {_provider_install_hint(provider)}")
    if has_api_key:
        return ("ok", f"{provider} provider package and API key look configured.")
    return ("warn", f"{provider} provider package is installed, but no API key was saved in config.")


def _validate_ollama_connection(ollama_url: str) -> tuple[str, str]:
    try:
        response = httpx.get(f"{ollama_url.rstrip('/')}/api/tags", timeout=2.0)
        if response.status_code < 400:
            return ("ok", f"Ollama is reachable at {ollama_url}.")
        return ("warn", f"Ollama responded with HTTP {response.status_code} at {ollama_url}.")
    except Exception as exc:
        return ("warn", f"Could not reach Ollama at {ollama_url}: {exc}")


def _post_setup_checks(
    provider: str,
    workspace_root: str,
    has_api_key: bool,
    ollama_url: str = "",
) -> list[tuple[str, str]]:
    checks = [
        _validate_workspace_root(workspace_root),
        _validate_provider_path(provider, has_api_key),
    ]
    if provider == "ollama":
        checks.append(_validate_ollama_connection(ollama_url))
    return checks


def run_setup(config_path: str | None = None):
    """The main onboarding experience."""
    config_lines = []
    api_key_saved = False
    ollama_url = ""

    print()
    _say("Hey! I'm Sol.")
    _wait()
    _say("I'm an AI agent, which means I can actually do things on your computer.")
    _say("Not just talk about them.")
    _wait()
    print()
    _say("Let's get you into a usable state quickly.")
    _say("I'll keep this simple and explain things in plain English.")
    print()

    input(f"  {DIM}Press Enter to start...{RESET}")
    print()

    _say("First, I need a brain.")
    _wait()
    print()
    provider, choice = _choose_provider()
    config_lines.append(f"provider: {provider}")

    provider_names = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini", "ollama": "Ollama"}
    provider_name = provider_names.get(provider, "OpenAI")
    print()
    _say(f"Nice, {provider_name} it is.")
    if provider in {"openai", "anthropic", "gemini"}:
        print()
        if _provider_extra_installed(provider):
            _say_dim(f"Provider package detected for {provider_name}.")
        else:
            _say("One quick heads-up: this environment does not look like it has that provider package installed yet.")
            _say_dim(f"Install it before first use with: {_provider_install_hint(provider)}")

    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-5-20250929",
        "gemini": "gemini-2.5-flash",
        "ollama": "llama3.1",
    }

    if choice == "5":
        _wait()
        print()
        _say("Cool, you've got your own setup. I just need two things.")
        print()
        base_url = _ask("What's the API URL? (e.g. http://localhost:1234/v1)")
        model = _ask("And the model name?")
        config_lines.append(f"base_url: {_yaml_quote(base_url)}")
        config_lines.append(f"model: {model}")
    else:
        default_model = defaults.get(provider, "gpt-4o")
        _wait()
        print()
        _say("I'll default to a solid all-around model, but you can change it now if you want.")
        print()
        model = _ask("Model", default=default_model)
        config_lines.append(f"model: {model}")

    print()
    if provider == "ollama":
        _say("Ollama runs locally, so no cloud account is required.")
        _wait()
        print()
        _say("Quick checklist:")
        _say_dim("  1. Install Ollama from https://ollama.ai")
        _say_dim(f"  2. Run: ollama pull {model}")
        _say_dim("  3. Run: ollama serve")
        print()

        if _ask_yn("Already have Ollama running?"):
            _say("Perfect, we're good to go.")
        else:
            _say("No problem. You can finish the install and come back.")

        print()
        ollama_url = _ask("Where is Ollama running?", default="http://localhost:11434")
        config_lines.append(f"ollama_base_url: {_yaml_quote(ollama_url)}")
    else:
        _say("Now I need an API key.")
        _wait()
        print()
        _say("Think of it like the credential that lets me talk to the model provider.")
        print()

        key_env_var = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(provider, "SOLSTICE_API_KEY")

        existing_key = os.getenv(key_env_var, "")
        if existing_key:
            _say("I found one in your environment already.")
            _say(f"{key_env_var} is set ({existing_key[:8]}...).")
            print()
            use_existing = _ask_yn("Want me to use that one?")
            if use_existing:
                api_key = ""
                _say("Done. I'll use the environment variable.")
            else:
                api_key = _ask("Paste your API key here")
        else:
            where_to_get = {
                "openai": "https://platform.openai.com/api-keys",
                "anthropic": "https://console.anthropic.com/settings/keys",
                "gemini": "https://aistudio.google.com/apikey",
            }
            _say_dim(f"Get one here: {where_to_get.get(provider, '')}")
            print()
            api_key = _ask("Paste your API key")
            if api_key:
                _say("Got it.")

        if api_key:
            api_key_saved = True
            config_lines.append(f"api_key: {_yaml_quote(api_key)}")
        else:
            config_lines.append(f"# api_key set via {key_env_var} environment variable")

    print()
    profile = _choose_runtime_profile()
    config_lines.append(f"runtime_profile: {profile}")

    print()
    _say("I also need to know what folder or area of your computer I should treat as my workspace.")
    _say("This is the place where my file tools are allowed to read and make changes.")
    print()
    default_workspace = os.getcwd()
    if profile == "gateway":
        _say_dim("Gateway mode should always use an explicit workspace root.")
        workspace_prompt = "Workspace root for gateway file access"
    else:
        _say_dim("Press Enter to use your current folder, or point me somewhere narrower.")
        workspace_prompt = "Workspace root"
    workspace_root = _ask(workspace_prompt, default=default_workspace)
    config_lines.append(f"workspace_root: {_yaml_quote(workspace_root)}")

    print()
    _say("Profiles already set sane defaults, so you usually don't need to micromanage tools here.")
    _say("If you want, I can apply a couple of simple overrides now.")
    print()
    if _ask_yn("Customize terminal/web defaults now?", default=False):
        enable_terminal = _ask_yn("Can I use your terminal? (for running code, builds, etc.)")
        enable_web = _ask_yn("Can I search the web?")
        config_lines.append(f"enable_terminal: {str(enable_terminal).lower()}")
        config_lines.append(f"enable_web: {str(enable_web).lower()}")
    else:
        _say("Perfect. I'll stick with the profile defaults.")

    print()
    if profile == "gateway":
        _say("Since you picked gateway mode, channel setup is available now but still optional.")
        _say("You can also skip this and wire channels later after the local server is up.")
    else:
        _say("Messaging channels are an advanced add-on. Most people set this up later.")
    _wait()
    print()

    setup_gateway = _ask_yn("Configure messaging channels now?", default=False)
    if setup_gateway:
        config_lines.append("")
        config_lines.append("gateway_enabled: true")
        config_lines.append("gateway_channels:")
        _setup_gateway_channels(config_lines)
    else:
        _say("No worries. You can always do this later with --setup.")

    print()
    _say("That's everything. Let me save your settings.")
    print()

    config_path = default_config_path(config_path)
    config_content = "\n".join(config_lines) + "\n"

    print(f"  {DIM}{'-' * 45}{RESET}")
    for line in config_content.strip().split("\n"):
        print(f"  {DIM}{line}{RESET}")
    print(f"  {DIM}{'-' * 45}{RESET}")
    print()

    if _ask_yn(f"Save this to {config_path.name}?"):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(config_content)
        print()
        _say("Saved. You're all set.")
        _wait()
        print()
        _say_dim(f"Config saved to {config_path}")
        print()
        _say("Quick validation:")
        for status, message in _post_setup_checks(provider, workspace_root, api_key_saved or bool(existing_key if provider != "ollama" else ""), ollama_url):
            color = GREEN if status == "ok" else YELLOW
            print(f"    {color}{status.upper():4}{RESET} {message}")
        print()
        _say("Here's what to run next:")
        print()
        for step in _next_steps(provider, profile, workspace_root, setup_gateway):
            if "#" in step:
                command, comment = step.split("#", 1)
                print(f"    {GREEN}{command.rstrip()}{RESET}  {DIM}# {comment.strip()}{RESET}")
            else:
                print(f"    {GREEN}{step}{RESET}")
        print()
        _say("A few easy starter things you can ask me:")
        for prompt in _starter_prompts(profile):
            print(f"    {GREEN}> {prompt}{RESET}")
        print()
        _say("If you need a deep enterprise integration, install an Artemis connector into the same environment.")
        _say_dim("  Example (Camunda): pipx inject solstice-agent artemis-camunda")
        print()
        _say("See you in there.")
    else:
        print()
        _say("No problem. Run --setup again whenever you're ready.")

    print()


def _setup_gateway_channels(config_lines: list):
    """Walk through each messaging channel conversationally."""
    print()
    _say("Let's pick which apps you want to connect. I'll walk you through each one.")
    print()

    if _ask_yn("Telegram?", default=False):
        print()
        _say("Telegram is the quickest one to set up.")
        _wait()
        print()
        _say_dim("  1. Open Telegram and search for @BotFather")
        _say_dim("  2. Send /newbot")
        _say_dim("  3. Pick a display name and username")
        _say_dim("  4. Copy the bot token")
        print()
        token = _ask("Bot token")
        config_lines.append("  telegram:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: {_yaml_quote(token)}")
        config_lines.append(f"    webhook_secret: {_yaml_quote(f'sol-{random.randint(100000, 999999)}')}")

    print()

    if _ask_yn("Discord?", default=False):
        print()
        _say("Discord takes a few extra steps in the developer portal.")
        _wait()
        print()
        _say_dim("  1. Create a Discord application and bot")
        _say_dim("  2. Enable Message Content Intent")
        _say_dim("  3. Invite the bot to your server")
        _say_dim("  4. Copy the bot token and channel IDs")
        print()
        token = _ask("Bot token")
        channel_ids = _ask("Channel ID(s) (comma-separate if multiple)")
        config_lines.append("  discord:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: {_yaml_quote(token)}")
        config_lines.append(f"    channel_ids: {_yaml_quote(channel_ids)}")

    print()

    if _ask_yn("Slack?", default=False):
        print()
        _say("Slack needs an app, a bot token, and a signing secret.")
        _wait()
        print()
        _say_dim("  1. Create a Slack app")
        _say_dim("  2. Add bot scopes and install it")
        _say_dim("  3. Copy the bot token and signing secret")
        _say_dim("  4. Enable event subscriptions after starting the gateway")
        print()
        token = _ask("Bot token (starts with xoxb-)")
        secret = _ask("Signing secret")
        config_lines.append("  slack:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: {_yaml_quote(token)}")
        config_lines.append(f"    signing_secret: {_yaml_quote(secret)}")


if __name__ == "__main__":
    run_setup()
