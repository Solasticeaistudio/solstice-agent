"""
Screen Capture + Annotation Tools
==================================
Screenshots, display enumeration, and image annotation (A2UI).
Requires: pip install mss Pillow
"""

import json
import logging
import os
import platform
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger("solstice.tools.screen")

# Allowed characters for window title searches (prevent command injection)
_SAFE_TITLE_RE = re.compile(r'^[\w\s\-\.\,\:\;\!\?\(\)\[\]\+\=\@\#\%\&]+$', re.UNICODE)


def _sanitize_title(title: str) -> str:
    """Sanitize a window title for safe use in shell commands.

    Raises ValueError if the title contains suspicious characters.
    """
    title = title.strip()
    if not title:
        raise ValueError("Window title cannot be empty")
    if len(title) > 200:
        raise ValueError("Window title too long (max 200 chars)")
    if not _SAFE_TITLE_RE.match(title):
        raise ValueError(
            f"Window title contains disallowed characters: {title!r}. "
            "Only letters, numbers, spaces, and basic punctuation are allowed."
        )
    return title


# ---------------------------------------------------------------------------
# Screen capture
# ---------------------------------------------------------------------------

def screen_capture(
    monitor: int = -1,
    region: Optional[str] = None,
    output_path: Optional[str] = None,
    quality: int = 80,
) -> str:
    """Capture a screenshot. monitor=-1 stitches all displays."""
    try:
        import mss
        from PIL import Image
    except ImportError:
        return "Error: Screen capture requires: pip install mss Pillow"

    out = output_path or os.path.join(
        tempfile.gettempdir(), f"sol_screenshot_{int(time.time())}.png"
    )

    with mss.mss() as sct:
        if region:
            try:
                parts = [int(x.strip()) for x in region.split(",")]
                if len(parts) != 4:
                    raise ValueError
                x, y, w, h = parts
                bbox = {"left": x, "top": y, "width": w, "height": h}
            except (ValueError, TypeError):
                return "Error: region must be 'x,y,width,height' (integers)"
            raw = sct.grab(bbox)
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        elif monitor == -1:
            # Stitch all monitors horizontally (Iris pattern)
            monitors = sct.monitors[1:]  # skip virtual "all" monitor
            if not monitors:
                return "Error: No monitors detected"

            images = []
            for mon in monitors:
                raw = sct.grab(mon)
                images.append(Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX"))

            total_w = sum(im.width for im in images)
            max_h = max(im.height for im in images)
            img = Image.new("RGB", (total_w, max_h))
            x_offset = 0
            for im in images:
                img.paste(im, (x_offset, 0))
                x_offset += im.width
        else:
            # Specific monitor (1-indexed in mss, but we expose 0-indexed)
            monitors = sct.monitors[1:]
            if monitor < 0 or monitor >= len(monitors):
                return f"Error: Monitor {monitor} not found. Available: 0-{len(monitors) - 1}"
            raw = sct.grab(monitors[monitor])
            img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    # Save
    ext = Path(out).suffix.lower()
    if ext in (".jpg", ".jpeg"):
        img.save(out, "JPEG", quality=quality)
    else:
        img.save(out, "PNG")

    return f"Screenshot saved: {out} ({img.width}x{img.height})"


# ---------------------------------------------------------------------------
# Window capture
# ---------------------------------------------------------------------------

def _get_window_rect_windows(title: str):
    """Get window rectangle on Windows via PowerShell."""
    ps_cmd = (
        f'Add-Type -AssemblyName System.Windows.Forms; '
        f'$procs = Get-Process | Where-Object {{$_.MainWindowTitle -like "*{title}*"}}; '
        f'if ($procs) {{ '
        f'Add-Type @" \n'
        f'using System; using System.Runtime.InteropServices; \n'
        f'public class Win32 {{ \n'
        f'  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect); \n'
        f'  [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left, Top, Right, Bottom; }} \n'
        f'}} \n'
        f'"@; '
        f'$r = New-Object Win32+RECT; '
        f'[Win32]::GetWindowRect($procs[0].MainWindowHandle, [ref]$r) | Out-Null; '
        f'"{0},$($r.Left),$($r.Top),$($r.Right - $r.Left),$($r.Bottom - $r.Top)" '
        f'}} else {{ "NOT_FOUND" }}'
    )
    try:
        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            capture_output=True, text=True, timeout=10
        )
        out = result.stdout.strip().split("\n")[-1]
        if "NOT_FOUND" in out or not out:
            return None
        # Parse "0,left,top,width,height"
        parts = out.split(",")
        if len(parts) >= 5:
            return int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
    except Exception as e:
        log.debug(f"Window rect failed: {e}")
    return None


def _get_window_rect_macos(title: str):
    """Get window rectangle on macOS via osascript."""
    script = (
        f'tell application "System Events" to tell (first process whose '
        f'name contains "{title}") to get {{position, size}} of front window'
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        # Output like: 100, 200, 800, 600
        parts = [int(x.strip()) for x in result.stdout.strip().split(",")]
        if len(parts) == 4:
            return parts[0], parts[1], parts[2], parts[3]
    except Exception as e:
        log.debug(f"Window rect failed: {e}")
    return None


def _get_window_rect_linux(title: str):
    """Get window rectangle on Linux via xdotool + xwininfo."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            capture_output=True, text=True, timeout=10
        )
        wid = result.stdout.strip().split("\n")[0]
        if not wid:
            return None
        result = subprocess.run(
            ["xdotool", "getwindowgeometry", "--shell", wid],
            capture_output=True, text=True, timeout=10
        )
        info = {}
        for line in result.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = int(v.strip())
        # Also get size
        result2 = subprocess.run(
            ["xdotool", "getwindowfocus", "getwindowgeometry", "--shell", wid],
            capture_output=True, text=True, timeout=10
        )
        for line in result2.stdout.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                info[k.strip()] = int(v.strip())
        if "X" in info and "Y" in info and "WIDTH" in info and "HEIGHT" in info:
            return info["X"], info["Y"], info["WIDTH"], info["HEIGHT"]
    except Exception as e:
        log.debug(f"Window rect failed: {e}")
    return None


def screen_capture_window(title: str, output_path: Optional[str] = None) -> str:
    """Capture a specific window by title substring."""
    try:
        import mss
        from PIL import Image
    except ImportError:
        return "Error: Screen capture requires: pip install mss Pillow"

    # Sanitize title to prevent command injection
    try:
        title = _sanitize_title(title)
    except ValueError as e:
        return f"Error: {e}"

    system = platform.system()
    if system == "Windows":
        rect = _get_window_rect_windows(title)
    elif system == "Darwin":
        rect = _get_window_rect_macos(title)
    else:
        rect = _get_window_rect_linux(title)

    if rect is None:
        return f"Error: Window '{title}' not found"

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return f"Error: Window '{title}' has invalid dimensions ({w}x{h})"

    out = output_path or os.path.join(
        tempfile.gettempdir(), f"sol_window_{int(time.time())}.png"
    )

    with mss.mss() as sct:
        bbox = {"left": x, "top": y, "width": w, "height": h}
        raw = sct.grab(bbox)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    img.save(out, "PNG")
    return f"Window '{title}' captured: {out} ({w}x{h})"


# ---------------------------------------------------------------------------
# Display enumeration
# ---------------------------------------------------------------------------

def screen_list_displays() -> str:
    """List all connected displays."""
    try:
        import mss
    except ImportError:
        return "Error: Screen capture requires: pip install mss"

    with mss.mss() as sct:
        monitors = sct.monitors[1:]  # skip virtual
        if not monitors:
            return "No monitors detected"

        lines = [f"Displays ({len(monitors)}):"]
        for i, mon in enumerate(monitors):
            primary = " (primary)" if i == 0 else ""
            lines.append(
                f"  [{i}] {mon['width']}x{mon['height']} "
                f"at ({mon['left']},{mon['top']}){primary}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Image annotation (A2UI)
# ---------------------------------------------------------------------------

def screen_annotate(
    image_path: str,
    annotations: str,
    output_path: Optional[str] = None,
) -> str:
    """Annotate an image with shapes (circle, arrow, rectangle, text, highlight)."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return "Error: Annotation requires: pip install Pillow"

    if not os.path.isfile(image_path):
        return f"Error: File not found: {image_path}"

    try:
        items = json.loads(annotations)
        if not isinstance(items, list):
            return "Error: annotations must be a JSON array"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON: {e}"

    img = Image.open(image_path).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw_main = ImageDraw.Draw(img)
    draw_overlay = ImageDraw.Draw(overlay)

    for ann in items:
        atype = ann.get("type", "")
        color = ann.get("color", "red")
        width = ann.get("width", 3)

        if atype == "circle":
            x, y = ann.get("x", 0), ann.get("y", 0)
            r = ann.get("radius", 20)
            draw_main.ellipse(
                [x - r, y - r, x + r, y + r],
                outline=color, width=width
            )

        elif atype == "arrow":
            x1, y1 = ann.get("x1", 0), ann.get("y1", 0)
            x2, y2 = ann.get("x2", 0), ann.get("y2", 0)
            draw_main.line([(x1, y1), (x2, y2)], fill=color, width=width)
            # Arrowhead
            import math
            angle = math.atan2(y2 - y1, x2 - x1)
            head_len = max(10, width * 4)
            for offset in [2.5, -2.5]:
                hx = x2 - head_len * math.cos(angle + offset * 0.174533)
                hy = y2 - head_len * math.sin(angle + offset * 0.174533)
                draw_main.line([(x2, y2), (int(hx), int(hy))], fill=color, width=width)

        elif atype == "rectangle":
            x, y = ann.get("x", 0), ann.get("y", 0)
            w, h = ann.get("width", 100), ann.get("height", 50)
            draw_main.rectangle([x, y, x + w, y + h], outline=color, width=width)

        elif atype == "text":
            x, y = ann.get("x", 0), ann.get("y", 0)
            text = ann.get("text", "")
            size = ann.get("size", 24)
            try:
                font = ImageFont.truetype("arial.ttf", size)
            except (OSError, IOError):
                font = ImageFont.load_default()
            draw_main.text((x, y), text, fill=color, font=font)

        elif atype == "highlight":
            x, y = ann.get("x", 0), ann.get("y", 0)
            w, h = ann.get("width", 100), ann.get("height", 40)
            opacity = int(ann.get("opacity", 0.3) * 255)
            # Parse color for RGBA
            try:
                from PIL import ImageColor
                rgb = ImageColor.getrgb(color)
            except (ValueError, AttributeError):
                rgb = (255, 255, 0)
            draw_overlay.rectangle(
                [x, y, x + w, y + h],
                fill=(*rgb, opacity)
            )

    # Composite overlay onto main image
    img = Image.alpha_composite(img, overlay).convert("RGB")

    out = output_path or image_path
    img.save(out, "PNG")
    return f"Annotated image saved: {out} ({len(items)} annotations)"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "screen_capture": {
        "name": "screen_capture",
        "description": (
            "Capture a screenshot. Captures all monitors stitched horizontally by default. "
            "Use monitor=0,1,2 for a specific display. Use region='x,y,w,h' for a crop."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "monitor": {
                    "type": "integer",
                    "description": "Monitor index (-1 for all, 0 for primary, etc.)",
                },
                "region": {
                    "type": "string",
                    "description": "Crop region as 'x,y,width,height'",
                },
                "output_path": {
                    "type": "string",
                    "description": "Where to save (default: temp dir)",
                },
                "quality": {
                    "type": "integer",
                    "description": "JPEG quality 1-100 (default 80)",
                },
            },
            "required": [],
        },
    },
    "screen_capture_window": {
        "name": "screen_capture_window",
        "description": "Capture a specific window by its title text (case-insensitive substring match).",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Window title to match",
                },
                "output_path": {
                    "type": "string",
                    "description": "Where to save (default: temp dir)",
                },
            },
            "required": ["title"],
        },
    },
    "screen_list_displays": {
        "name": "screen_list_displays",
        "description": "List all connected displays with index, resolution, position, and primary status.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    "screen_annotate": {
        "name": "screen_annotate",
        "description": (
            "Annotate an image with shapes. Pass annotations as a JSON array. "
            "Types: circle (x,y,radius), arrow (x1,y1,x2,y2), rectangle (x,y,width,height), "
            "text (x,y,text,size), highlight (x,y,width,height,opacity)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the image to annotate",
                },
                "annotations": {
                    "type": "string",
                    "description": "JSON array of annotation objects",
                },
                "output_path": {
                    "type": "string",
                    "description": "Where to save (default: overwrites original)",
                },
            },
            "required": ["image_path", "annotations"],
        },
    },
}


def register_screen_tools(registry):
    """Register screen capture and annotation tools."""
    registry.register("screen_capture", screen_capture, _SCHEMAS["screen_capture"])
    registry.register("screen_capture_window", screen_capture_window, _SCHEMAS["screen_capture_window"])
    registry.register("screen_list_displays", screen_list_displays, _SCHEMAS["screen_list_displays"])
    registry.register("screen_annotate", screen_annotate, _SCHEMAS["screen_annotate"])
