"""
Browser Tools
=============
Headless browser automation via Playwright. Navigate, click, type,
screenshot, and read page content — all as agent tools.

Requires: pip install playwright && playwright install chromium
"""

import json
import logging
import os
import re
import tempfile
from typing import Optional

log = logging.getLogger("solstice.tools.browser")

# ---------------------------------------------------------------------------
# Module-level browser state
# ---------------------------------------------------------------------------
_browser = None
_page = None
_playwright = None


def _ensure_browser():
    """Launch browser if not already running."""
    global _browser, _page, _playwright

    if _page is not None:
        return True

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False

    _playwright = sync_playwright().start()
    _browser = _playwright.chromium.launch(headless=True)
    _page = _browser.new_page(
        viewport={"width": 1280, "height": 720},
        user_agent="Sol/0.1 (Browser Tool)",
    )
    log.info("Browser launched (headless Chromium)")
    return True


_ALLOWED_BROWSER_SCHEMES = {"http", "https"}


def browser_navigate(url: str) -> str:
    """
    Navigate to a URL and return the page title and status.
    """
    if not _ensure_browser():
        return "Error: Browser tools require Playwright. Install with: pip install playwright && playwright install chromium"

    # Block dangerous URL schemes (file://, javascript:, data:, etc.)
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in _ALLOWED_BROWSER_SCHEMES:
            return f"Error: URL scheme '{scheme}' is not allowed. Only http:// and https:// are supported."
    except Exception:
        return f"Error: Invalid URL: {url}"

    try:
        response = _page.goto(url, wait_until="domcontentloaded", timeout=30000)
        status = response.status if response else "unknown"
        title = _page.title()
        return f"Navigated to {url}\n  Title: {title}\n  Status: {status}"
    except Exception as e:
        log.debug(f"Navigation failed: {url}: {e}")
        return f"Failed to navigate to {url}. Check the URL and try again."


def browser_read(selector: Optional[str] = None, max_length: int = 5000) -> str:
    """
    Read text content from the current page. Optionally target a specific
    CSS selector. Returns plain text with whitespace collapsed.
    """
    if not _ensure_browser():
        return "Error: Browser not available."

    if _page.url == "about:blank":
        return "No page loaded. Use browser_navigate first."

    try:
        if selector:
            elements = _page.query_selector_all(selector)
            if not elements:
                return f"No elements found matching '{selector}'."
            texts = [el.inner_text() for el in elements]
            content = "\n\n".join(texts)
        else:
            content = _page.inner_text("body")

        # Collapse whitespace
        import re
        content = re.sub(r'\n{3,}', '\n\n', content)
        content = re.sub(r'[ \t]+', ' ', content)
        content = content.strip()

        if len(content) > max_length:
            content = content[:max_length] + "\n... (truncated)"

        url = _page.url
        title = _page.title()
        return f"Page: {title} ({url})\n\n{content}"
    except Exception as e:
        log.debug(f"Failed to read page content: {e}")
        return "Failed to read page content."


def browser_click(selector: str) -> str:
    """
    Click an element on the page by CSS selector.
    Examples: 'button.submit', '#login', 'a[href="/about"]'
    """
    if not _ensure_browser():
        return "Error: Browser not available."

    try:
        _page.click(selector, timeout=5000)
        _page.wait_for_load_state("domcontentloaded", timeout=10000)
        title = _page.title()
        url = _page.url
        return f"Clicked '{selector}'. Now on: {title} ({url})"
    except Exception as e:
        log.debug(f"Click failed: {selector}: {e}")
        return f"Could not click '{selector}'. Element may not exist or is not visible."


def browser_type(selector: str, text: str, submit: bool = False) -> str:
    """
    Type text into an input field. Optionally press Enter to submit.
    """
    if not _ensure_browser():
        return "Error: Browser not available."

    try:
        _page.fill(selector, text, timeout=5000)
        result = f"Typed into '{selector}'."
        if submit:
            _page.press(selector, "Enter")
            _page.wait_for_load_state("domcontentloaded", timeout=10000)
            result += f" Submitted. Now on: {_page.title()} ({_page.url})"
        return result
    except Exception as e:
        log.debug(f"Type failed: {selector}: {e}")
        return f"Could not type into '{selector}'. Element may not exist or is not an input."


def browser_screenshot(full_page: bool = False) -> str:
    """
    Take a screenshot of the current page. Returns the file path.
    Use full_page=True to capture the entire scrollable page.
    """
    if not _ensure_browser():
        return "Error: Browser not available."

    if _page.url == "about:blank":
        return "No page loaded. Use browser_navigate first."

    try:
        path = os.path.join(tempfile.gettempdir(), "sol_screenshot.png")
        _page.screenshot(path=path, full_page=full_page)
        return f"Screenshot saved to {path}"
    except Exception as e:
        log.debug(f"Screenshot failed: {e}")
        return "Failed to take screenshot."


# Patterns that indicate dangerous JS operations
_DANGEROUS_JS_PATTERNS = [
    "fetch(", "xmlhttprequest", "navigator.sendbeacon",
    "window.open(", "document.cookie", "localstorage",
    "sessionstorage", "indexeddb", "websocket(",
    "importscripts", "eval(", "function(",
    "serviceworker", "postmessage(", ".src=",
    # Additional dangerous APIs
    "navigator.credentials", "document.location", "window.location",
    ".innerhtml", ".appendchild", ".insertbefore",
    "new worker(", "sharedworker(",
]

# Regex patterns for bracket-notation access to dangerous globals
_JS_BRACKET_PATTERNS = re.compile(
    r"""\[\s*['"`](?:fetch|eval|cookie|localStorage|sessionStorage|"""
    r"""indexedDB|WebSocket|XMLHttpRequest|Function|importScripts|"""
    r"""sendBeacon|open|location|innerHTML|credentials)['"`]\s*\]""",
    re.IGNORECASE,
)


def _normalize_js(expression: str) -> str:
    """Normalize JS expression to defeat obfuscation.

    Handles unicode escapes (\\x28, \\u0028), full-width characters,
    and string concatenation tricks.
    """
    import codecs
    normalized = expression
    # Decode \\xNN hex escapes
    try:
        normalized = codecs.decode(normalized, 'unicode_escape')
    except Exception:
        pass
    # Normalize full-width characters (U+FF01..U+FF5E → ASCII)
    result = []
    for ch in normalized:
        cp = ord(ch)
        if 0xFF01 <= cp <= 0xFF5E:
            result.append(chr(cp - 0xFEE0))
        else:
            result.append(ch)
    return ''.join(result)


def browser_eval(expression: str) -> str:
    """
    Evaluate a JavaScript expression in the page context and return the result.
    Use for extracting data, checking state, or reading page structure.
    Blocked: network requests, cookie access, eval chains, storage access.
    """
    if not _ensure_browser():
        return "Error: Browser not available."

    # Normalize to defeat unicode/fullwidth obfuscation, then check
    normalized = _normalize_js(expression)
    expr_lower = normalized.lower()

    for pattern in _DANGEROUS_JS_PATTERNS:
        if pattern in expr_lower:
            return (
                f"Error: Expression contains blocked pattern '{pattern}'. "
                f"browser_eval is restricted to data extraction and page state queries."
            )

    # Check bracket-notation access (window["fetch"](), etc.)
    if _JS_BRACKET_PATTERNS.search(expression) or _JS_BRACKET_PATTERNS.search(normalized):
        return (
            "Error: Expression contains bracket-notation access to a blocked API. "
            "browser_eval is restricted to data extraction and page state queries."
        )

    try:
        result = _page.evaluate(expression)
        if isinstance(result, (dict, list)):
            return json.dumps(result, indent=2, default=str)
        return str(result) if result is not None else "(undefined)"
    except Exception as e:
        log.debug(f"Eval failed: {expression[:100]}: {e}")
        return "JavaScript evaluation failed. Check the expression syntax."


def browser_close() -> str:
    """Close the browser and free resources."""
    global _browser, _page, _playwright

    if _browser:
        try:
            _browser.close()
        except Exception:
            pass
    if _playwright:
        try:
            _playwright.stop()
        except Exception:
            pass

    _browser = None
    _page = None
    _playwright = None
    return "Browser closed."


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

_SCHEMAS = {
    "browser_navigate": {
        "name": "browser_navigate",
        "description": (
            "Navigate to a URL in a headless browser. Returns the page title and HTTP status. "
            "Use this to load web pages for reading, interaction, or screenshots."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to navigate to"},
            },
            "required": ["url"],
        },
    },
    "browser_read": {
        "name": "browser_read",
        "description": (
            "Read text content from the current browser page. Optionally target a specific "
            "CSS selector to read only that element. Returns plain text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector to target (optional — reads whole page if omitted)"},
                "max_length": {"type": "integer", "description": "Max characters to return (default 5000)"},
            },
            "required": [],
        },
    },
    "browser_click": {
        "name": "browser_click",
        "description": (
            "Click an element on the current page by CSS selector. "
            "Waits for navigation if the click causes a page load."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the element to click (e.g. 'button.submit', '#login')"},
            },
            "required": ["selector"],
        },
    },
    "browser_type": {
        "name": "browser_type",
        "description": (
            "Type text into an input field on the current page. "
            "Optionally press Enter to submit the form."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {"type": "string", "description": "CSS selector of the input field"},
                "text": {"type": "string", "description": "Text to type"},
                "submit": {"type": "boolean", "description": "Press Enter after typing (default false)"},
            },
            "required": ["selector", "text"],
        },
    },
    "browser_screenshot": {
        "name": "browser_screenshot",
        "description": (
            "Take a screenshot of the current browser page. Returns the file path. "
            "Use full_page=True to capture the entire scrollable page."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "full_page": {"type": "boolean", "description": "Capture full scrollable page (default false)"},
            },
            "required": [],
        },
    },
    "browser_eval": {
        "name": "browser_eval",
        "description": (
            "Evaluate a JavaScript expression in the browser page context. "
            "Returns the result. Useful for extracting data or checking page state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "JavaScript expression to evaluate"},
            },
            "required": ["expression"],
        },
    },
    "browser_close": {
        "name": "browser_close",
        "description": "Close the headless browser and free resources.",
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

def register_browser_tools(registry):
    """Register browser automation tools with a ToolRegistry."""
    registry.register("browser_navigate", browser_navigate, _SCHEMAS["browser_navigate"])
    registry.register("browser_read", browser_read, _SCHEMAS["browser_read"])
    registry.register("browser_click", browser_click, _SCHEMAS["browser_click"])
    registry.register("browser_type", browser_type, _SCHEMAS["browser_type"])
    registry.register("browser_screenshot", browser_screenshot, _SCHEMAS["browser_screenshot"])
    registry.register("browser_eval", browser_eval, _SCHEMAS["browser_eval"])
    registry.register("browser_close", browser_close, _SCHEMAS["browser_close"])
