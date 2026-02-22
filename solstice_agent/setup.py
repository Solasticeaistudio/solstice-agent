"""
Interactive Setup — Conversational Onboarding
==============================================
Not a form. A conversation. Walks anyone through setup,
even if they've never touched an API key in their life.

Run: solstice-agent --setup
"""

import os
import sys
import time
import random
from pathlib import Path

# Colors
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
WHITE = "\033[97m"


def _type(text: str, pause: float = 0.01):
    """Print with a subtle typing effect. Feels alive without being slow."""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        if char in '.!?\n':
            time.sleep(pause * 8)
        elif char == ',':
            time.sleep(pause * 4)
        else:
            time.sleep(pause)
    print()


def _say(text: str):
    """Agent speaks. Cyan, with a subtle pause before."""
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


def run_setup():
    """The main onboarding experience."""

    config_lines = []

    # ─── Introduction ────────────────────────────────────────
    print()
    _say("Hey! I'm Sol.")
    _wait()
    _say("I'm an AI agent — which basically means I can actually do things")
    _say("on your computer, not just talk about doing them.")
    _wait()
    print()
    _say("I can read and edit your files, run commands in your terminal,")
    _say("search the web, and you can even talk to me through Telegram,")
    _say("Discord, Slack... whatever you use.")
    _wait()
    print()
    _say("Let's get you set up. I'll walk you through everything.")
    _say("Should take about 2 minutes.")
    print()

    input(f"  {DIM}Press Enter to start...{RESET}")
    print()

    # ─── Brain: Which AI to use ──────────────────────────────
    _say("First things first — I need a brain.")
    _wait()
    _say("I can use different AI models to think. You pick which one")
    _say("you want me to run on. Here are your options:")
    print()
    print(f"  {GREEN}1{RESET}  {BOLD}OpenAI{RESET}       — GPT-4o, o1, o3. The most popular one.")
    print(f"  {GREEN}2{RESET}  {BOLD}Anthropic{RESET}    — Claude. Known for being really thoughtful.")
    print(f"  {GREEN}3{RESET}  {BOLD}Google{RESET}       — Gemini. Fast, can search the web natively.")
    print(f"  {GREEN}4{RESET}  {BOLD}Ollama{RESET}       — Run AI {BOLD}locally{RESET} on your own machine. {GREEN}Free.{RESET}")
    print(f"  {GREEN}5{RESET}  {BOLD}Other{RESET}        — Got your own AI server? I can connect to it.")
    print()

    _say_dim("If you're not sure, 1 (OpenAI) is the most common choice.")
    _say_dim("If you want free and private, 4 (Ollama) runs everything on your machine.")
    print()

    choice = _ask("Which one sounds good? [1-5]", default="1")
    provider_map = {"1": "openai", "2": "anthropic", "3": "gemini", "4": "ollama", "5": "openai"}
    provider = provider_map.get(choice, "openai")
    config_lines.append(f"provider: {provider}")

    provider_names = {"openai": "OpenAI", "anthropic": "Anthropic", "gemini": "Gemini", "ollama": "Ollama"}
    provider_name = provider_names.get(provider, "OpenAI")
    print()
    _say(f"Nice, {provider_name} it is.")

    # ─── Model ───────────────────────────────────────────────
    defaults = {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-5-20250929",
        "gemini": "gemini-2.5-flash",
        "ollama": "llama3.1",
    }

    if choice == "5":
        _wait()
        print()
        _say("Cool, you've got your own setup. I just need two things:")
        print()
        base_url = _ask("What's the API URL? (e.g. http://localhost:1234/v1)")
        model = _ask("And the model name?")
        config_lines.append(f"base_url: \"{base_url}\"")
        config_lines.append(f"model: {model}")
    else:
        default_model = defaults.get(provider, "gpt-4o")
        _wait()
        print()
        _say("Each provider has different models. I'll default to their best")
        _say("all-around option, but you can change it if you want.")
        print()
        model = _ask("Model", default=default_model)
        config_lines.append(f"model: {model}")

    # ─── API Key ─────────────────────────────────────────────
    print()
    if provider == "ollama":
        _say("Here's the cool part — Ollama is completely free.")
        _say("It runs the AI model right on your computer. No account needed.")
        _wait()
        print()
        _say("You just need Ollama installed and running. Quick checklist:")
        print()
        _say_dim("  1. Download Ollama from https://ollama.ai (it's a small app)")
        _say_dim(f"  2. Open a terminal and run: ollama pull {model}")
        _say_dim("     (this downloads the model — might take a few minutes)")
        _say_dim("  3. Start it with: ollama serve")
        print()

        if _ask_yn("Already have Ollama running?"):
            _say("Perfect, we're good to go.")
        else:
            _say("No rush. Install it whenever you're ready, then come back")
            _say(f"and just run {BOLD}solstice-agent{RESET}{CYAN} — I'll be here.{RESET}")

        print()
        ollama_url = _ask("Where is Ollama running?", default="http://localhost:11434")
        config_lines.append(f"ollama_base_url: \"{ollama_url}\"")
    else:
        # Need an API key — explain what it is for non-technical users
        _say("Okay, now I need an API key.")
        _wait()
        print()

        _say("If you're thinking \"what's an API key?\" — totally fair.")
        _say("Think of it like a password that lets me talk to the AI service.")
        _say(f"You get one from {provider_name}'s website. It's free to sign up,")
        _say("and they usually give you some free credits to start with.")
        print()

        key_env_var = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
        }.get(provider, "SOLSTICE_API_KEY")

        existing_key = os.getenv(key_env_var, "")

        if existing_key:
            _say("Oh wait — I actually found one already!")
            _say(f"You have {BOLD}{key_env_var}{RESET}{CYAN} set in your environment ({existing_key[:8]}...){RESET}")
            print()
            use_existing = _ask_yn("Want me to use that one?")
            if use_existing:
                api_key = ""
                _say("Done. Using your existing key.")
            else:
                api_key = _ask("Paste your API key here")
        else:
            where_to_get = {
                "openai": ("https://platform.openai.com/api-keys", [
                    "Go to platform.openai.com and sign in (or create an account)",
                    "Click your profile icon (top right) -> 'API keys'",
                    "Click 'Create new secret key'",
                    "Give it a name (anything — like 'solstice') and click 'Create'",
                    "Copy the key (starts with 'sk-'). You won't be able to see it again!",
                ]),
                "anthropic": ("https://console.anthropic.com/settings/keys", [
                    "Go to console.anthropic.com and sign in (or create an account)",
                    "Click 'Settings' in the sidebar, then 'API keys'",
                    "Click 'Create Key'",
                    "Give it a name and click 'Create'",
                    "Copy the key (starts with 'sk-ant-')",
                ]),
                "gemini": ("https://aistudio.google.com/apikey", [
                    "Go to aistudio.google.com/apikey",
                    "Sign in with your Google account",
                    "Click 'Create API key'",
                    "Pick any Google Cloud project (or create one — it's free)",
                    "Copy the key (starts with 'AI')",
                ]),
            }

            url, steps = where_to_get.get(provider, ("", []))

            _say("Here's how to get one. It takes about 60 seconds:")
            print()
            for i, step in enumerate(steps, 1):
                _say_dim(f"  {i}. {step}")
            print()
            _say_dim(f"  Direct link: {CYAN}{url}{RESET}")
            print()

            _say("Take your time — I'll wait right here.")
            print()
            api_key = _ask("Paste your API key")

            if api_key:
                _say("Got it. I'll keep that safe.")

        if api_key:
            config_lines.append(f"api_key: \"{api_key}\"")
        else:
            config_lines.append(f"# api_key set via {key_env_var} environment variable")

    # ─── Capabilities ────────────────────────────────────────
    print()
    _say("Alright, let's talk about what I can do.")
    _wait()
    print()
    _say("By default, I come with a few built-in abilities:")
    print()
    _say_dim("  Files    — I can read, write, and edit files on your computer")
    _say_dim("  Terminal — I can run commands (git, python, npm, etc.)")
    _say_dim("  Web      — I can search the internet and pull info from websites")
    print()
    _say("You're in control of what I have access to.")
    print()

    enable_terminal = _ask_yn("Can I use your terminal? (for running code, builds, etc.)")
    if enable_terminal:
        _say("Awesome, that makes me way more useful.")
    else:
        _say("No problem. I'll stick to file operations and conversation.")

    enable_web = _ask_yn("Can I search the web?")
    if enable_web:
        _say("Great — I'll use DuckDuckGo so there's no extra API key needed.")
    else:
        _say("Got it, staying offline.")

    config_lines.append(f"enable_terminal: {str(enable_terminal).lower()}")
    config_lines.append(f"enable_web: {str(enable_web).lower()}")

    # ─── Messaging Gateway ───────────────────────────────────
    print()
    _say("One more thing — and this part's optional but pretty cool.")
    _wait()
    print()
    _say("I can live inside your messaging apps. Like, you could message me")
    _say("on Telegram or Discord and I'd respond right there, with full")
    _say("access to all my tools. Kind of like having me in your pocket.")
    print()

    setup_gateway = _ask_yn("Want to connect me to any messaging apps?", default=False)

    if setup_gateway:
        config_lines.append("")
        config_lines.append("gateway_enabled: true")
        config_lines.append("gateway_channels:")
        _setup_gateway_channels(config_lines)
    else:
        _say("No worries — you can always set this up later with --setup.")

    # ─── Write config & goodbye ──────────────────────────────
    print()
    _say("That's everything! Let me save your settings.")
    print()

    config_path = Path.cwd() / "solstice-agent.yaml"
    config_content = "\n".join(config_lines) + "\n"

    print(f"  {DIM}{'─' * 45}{RESET}")
    for line in config_content.strip().split("\n"):
        print(f"  {DIM}{line}{RESET}")
    print(f"  {DIM}{'─' * 45}{RESET}")
    print()

    if _ask_yn(f"Save this to {config_path.name}?"):
        with open(config_path, 'w') as f:
            f.write(config_content)
        print()
        _say("Saved! You're all set.")
        _wait()
        print()
        _say("Here's how to talk to me:")
        print()
        print(f"    {GREEN}solstice-agent{RESET}              {DIM}# Start a conversation{RESET}")
        print(f"    {GREEN}solstice-agent \"hello\"{RESET}      {DIM}# Quick one-liner{RESET}")
        if setup_gateway:
            print(f"    {GREEN}solstice-gateway{RESET}            {DIM}# Start the messaging server{RESET}")
        print()
        _say("See you in there.")
    else:
        print()
        _say("No problem. Run --setup again whenever you're ready.")

    print()


def _setup_gateway_channels(config_lines: list):
    """Walk through each messaging channel conversationally."""

    print()
    _say("Let's pick which apps you want to connect. I'll walk you")
    _say("through each one step by step.")
    print()

    # ─── Telegram ────────────────────────────────────────────
    if _ask_yn("Telegram?", default=False):
        print()
        _say("Telegram's the easiest one to set up. Takes about 30 seconds.")
        _wait()
        print()
        _say("You need to create a bot on Telegram — don't worry, it's")
        _say("just a quick chat with their bot-making bot (yes, really).")
        print()
        _say_dim("  1. Open Telegram and search for @BotFather")
        _say_dim("  2. Send it the message: /newbot")
        _say_dim("  3. Pick a display name (like 'My Sol Agent')")
        _say_dim("  4. Pick a username (like 'my_sol_bot' — must end in 'bot')")
        _say_dim("  5. BotFather gives you a token — it looks like this:")
        _say_dim(f"     {CYAN}123456789:AAF-some-long-random-string{RESET}")
        print()
        _say("Got it? Paste the token here:")
        print()
        token = _ask("Bot token")
        config_lines.append("  telegram:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: \"{token}\"")
        config_lines.append(f"    webhook_secret: \"sol-{random.randint(100000, 999999)}\"")
        print()
        _say("Nice! After you start the gateway server, you'll need to tell")
        _say("Telegram where to send messages. I'll remind you how when")
        _say("you run solstice-gateway.")

    print()

    # ─── Discord ─────────────────────────────────────────────
    if _ask_yn("Discord?", default=False):
        print()
        _say("Discord takes a couple more steps, but I'll walk you through it.")
        _wait()
        print()
        _say("You need to create a bot application on Discord's developer portal.")
        print()
        _say_dim("  1. Go to: discord.com/developers/applications")
        _say_dim("  2. Click 'New Application' and give it a name")
        _say_dim("  3. Go to the 'Bot' tab on the left")
        _say_dim("  4. Click 'Reset Token' and copy the token it shows you")
        print()
        _say_dim(f"  {YELLOW}Important:{RESET} {DIM}Scroll down and turn ON 'Message Content Intent'{RESET}")
        _say_dim(f"  {DIM}(under Privileged Gateway Intents). Without this, I can't read messages.{RESET}")
        print()
        _say_dim("  5. Go to 'OAuth2' -> 'URL Generator'")
        _say_dim("     Check 'bot' under scopes")
        _say_dim("     Check 'Send Messages' and 'Read Message History' under permissions")
        _say_dim("  6. Copy the URL at the bottom and open it — this invites me to your server")
        print()
        _say_dim("  7. To get a channel ID: right-click any channel -> 'Copy Channel ID'")
        _say_dim("     (If you don't see that option, enable Developer Mode in Discord settings)")
        print()
        token = _ask("Bot token")
        channel_ids = _ask("Channel ID(s) (comma-separate if multiple)")
        config_lines.append("  discord:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: \"{token}\"")
        config_lines.append(f"    channel_ids: \"{channel_ids}\"")
        print()
        _say("Discord's ready. I'll connect automatically when you start the gateway.")

    print()

    # ─── Slack ───────────────────────────────────────────────
    if _ask_yn("Slack?", default=False):
        print()
        _say("Slack's got a few more steps because... well, it's Slack.")
        _wait()
        print()
        _say_dim("  1. Go to: api.slack.com/apps -> 'Create New App' -> 'From scratch'")
        _say_dim("  2. Name it whatever you want, pick your workspace")
        _say_dim("  3. Go to 'OAuth & Permissions' in the sidebar")
        _say_dim("     Scroll to 'Bot Token Scopes' and add:")
        _say_dim(f"     {CYAN}chat:write, channels:history, im:history, channels:read{RESET}")
        _say_dim("  4. Click 'Install to Workspace' at the top and authorize")
        _say_dim("  5. Copy the 'Bot User OAuth Token' (starts with xoxb-)")
        print()
        _say_dim("  6. Go to 'Basic Information' in the sidebar")
        _say_dim("     Under 'App Credentials', copy the 'Signing Secret'")
        print()
        _say_dim("  7. Go to 'Event Subscriptions' -> toggle ON")
        _say_dim("     You'll set the webhook URL after starting the gateway")
        _say_dim("  8. Under 'Subscribe to bot events', add: message.channels, message.im")
        print()
        token = _ask("Bot token (starts with xoxb-)")
        secret = _ask("Signing secret")
        config_lines.append("  slack:")
        config_lines.append("    enabled: true")
        config_lines.append(f"    bot_token: \"{token}\"")
        config_lines.append(f"    signing_secret: \"{secret}\"")
        print()
        _say("Slack's configured. Don't forget to set the Events URL after")
        _say("starting the gateway — Slack needs to verify the connection.")


if __name__ == "__main__":
    run_setup()
