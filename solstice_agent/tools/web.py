"""
Web Tools
=========
Web search and URL fetching. Uses DuckDuckGo (no API key needed)
and httpx for fetching pages.
"""

import logging

log = logging.getLogger("solstice.tools.web")


def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo (no API key needed).
    Returns top results with titles, URLs, and snippets.
    """
    try:
        from duckduckgo_search import DDGS
    except ImportError:
        return "Error: Web search requires: pip install duckduckgo-search"

    try:
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append(
                    f"**{r.get('title', 'No title')}**\n"
                    f"  {r.get('href', '')}\n"
                    f"  {r.get('body', '')}\n"
                )

        if not results:
            return f"No results found for: {query}"

        return f"Search results for '{query}':\n\n" + "\n".join(results)
    except Exception as e:
        return f"Search error: {e}"


def fetch_url(url: str, max_length: int = 5000) -> str:
    """
    Fetch a URL and return its text content.
    Strips HTML tags for readability.
    """
    from .security import validate_url

    url_err = validate_url(url)
    if url_err:
        return f"Error: {url_err}"

    try:
        import httpx
    except ImportError:
        return "Error: URL fetching requires: pip install httpx"

    try:
        # Don't follow redirects automatically — validate each hop
        # to prevent redirect-based SSRF to private IPs
        _MAX_REDIRECTS = 5
        current_url = url
        resp = None
        for _ in range(_MAX_REDIRECTS):
            resp = httpx.get(current_url, follow_redirects=False, timeout=15.0, headers={
                "User-Agent": "Mozilla/5.0 (compatible; SolsticeAgent/0.1)"
            })
            if resp.status_code in (301, 302, 303, 307, 308):
                redirect_url = resp.headers.get("location", "")
                if not redirect_url:
                    break
                # Resolve relative redirects
                if redirect_url.startswith("/"):
                    from urllib.parse import urlparse as _urlparse
                    p = _urlparse(current_url)
                    redirect_url = f"{p.scheme}://{p.netloc}{redirect_url}"
                # Validate the redirect target (blocks private IPs, metadata, etc.)
                redirect_err = validate_url(redirect_url)
                if redirect_err:
                    return f"Error: Redirect blocked — {redirect_err}"
                current_url = redirect_url
            else:
                break
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/html" in content_type:
            # Strip HTML tags
            import re
            text = resp.text
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
        else:
            text = resp.text

        if len(text) > max_length:
            text = text[:max_length] + "\n... (truncated)"

        return f"Content from {url}:\n\n{text}"
    except Exception as e:
        log.debug(f"Fetch failed for {url}: {e}")
        return f"Error fetching {url}. Check that the URL is valid and reachable."


# --- Schemas ---

_SCHEMAS = {
    "web_search": {
        "name": "web_search",
        "description": "Search the web. Returns top results with titles, URLs, and snippets. No API key needed.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "description": "Number of results (default 5)"},
            },
            "required": ["query"],
        },
    },
    "fetch_url": {
        "name": "fetch_url",
        "description": "Fetch a URL and return its text content. HTML is stripped for readability.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_length": {"type": "integer", "description": "Max content length (default 5000)"},
            },
            "required": ["url"],
        },
    },
}


def register_web_tools(registry):
    """Register web tools with a ToolRegistry."""
    registry.register("web_search", web_search, _SCHEMAS["web_search"])
    registry.register("fetch_url", fetch_url, _SCHEMAS["fetch_url"])
