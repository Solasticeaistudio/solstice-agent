"""
Solstice Agent — System Tray Entry Point
==========================================
Always-on background agent with system tray / menu bar icon.
Requires: pip install pystray Pillow plyer
"""

import logging
import sys

log = logging.getLogger("solstice.tray")


def _create_icon_image():
    """Generate a 64x64 tray icon with Pillow (avoids bundling files)."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient circle background
    draw.ellipse([4, 4, 60, 60], fill=(59, 130, 246))  # Blue
    draw.ellipse([6, 6, 58, 58], fill=(37, 99, 235))

    # "S" glyph
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except (OSError, IOError):
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), "S", font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (64 - tw) // 2 - bbox[0]
    ty = (64 - th) // 2 - bbox[1]
    draw.text((tx, ty), "S", fill="white", font=font)

    return img


def _run_agent_loop(agent, voice_enabled=False):
    """Run the agent in a background thread, processing voice or queue commands."""
    from .tools.voice_continuous import set_command_callback, voice_start_listening

    if voice_enabled:
        def on_command(text):
            try:
                response = agent.chat(text)
                # Show notification with response
                try:
                    from plyer import notification
                    notification.notify(
                        title="Solstice Agent",
                        message=response.text[:200] if hasattr(response, "text") else str(response)[:200],
                        app_name="Solstice Agent",
                        timeout=10,
                    )
                except Exception:
                    pass
            except Exception as e:
                log.error(f"Agent error: {e}")

        set_command_callback(on_command)
        voice_start_listening()


def main():
    """Launch Solstice Agent as a system tray application."""
    try:
        import pystray
    except ImportError:
        print("System tray requires: pip install pystray Pillow plyer")
        print("Install with: pip install solstice-agent[tray]")
        sys.exit(1)

    from .config import Config
    from .agent.core import Agent
    from .tools.registry import ToolRegistry

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    config = Config()
    provider = config.build_provider()
    agent = Agent(provider=provider)

    registry = ToolRegistry()
    registry.load_builtins()
    registry.apply(agent)

    voice_enabled = False

    def on_toggle_voice(icon, item):
        nonlocal voice_enabled
        voice_enabled = not voice_enabled
        if voice_enabled:
            from .tools.voice_continuous import voice_start_listening
            voice_start_listening()
            icon.title = "Solstice Agent (listening)"
        else:
            from .tools.voice_continuous import voice_stop_listening
            voice_stop_listening()
            icon.title = "Solstice Agent (idle)"

    def on_quit(icon, item):
        from .tools.voice_continuous import voice_stop_listening
        try:
            voice_stop_listening()
        except Exception:
            pass
        icon.stop()

    icon_image = _create_icon_image()

    menu = pystray.Menu(
        pystray.MenuItem("Solstice Agent", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            lambda item: "Voice: ON" if voice_enabled else "Voice: OFF",
            on_toggle_voice,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", on_quit),
    )

    icon = pystray.Icon(
        name="solstice-agent",
        icon=icon_image,
        title="Solstice Agent (idle)",
        menu=menu,
    )

    log.info("Solstice Agent tray started")
    icon.run()


if __name__ == "__main__":
    main()
