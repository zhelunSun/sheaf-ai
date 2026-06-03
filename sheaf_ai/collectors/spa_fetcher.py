"""
Sheaf SPA Fetcher — JavaScript-rendered page content extraction via Playwright.

This module provides a dedicated fetcher for SPA (Single Page Application) platforms
that require browser rendering to extract meaningful content. It is designed to be
called from the router when a URL is detected as belonging to an SPA platform.

Strategies (3-layer degradation):
  Layer 1: URL pattern -> SPA platform identification (instant, done by router)
  Layer 2: Playwright available -> headless browser fetch (15s timeout)
  Layer 3: Playwright unavailable -> friendly error + install instructions

Design principles:
  - Playwright is an optional dependency; module works gracefully without it
  - Timeout protection: browser fetch capped at configurable timeout
  - Non-blocking: SPA fetch only triggers for URLs in _SPA_PLATFORMS
  - Reuses fetch_article's HTML parsing pipeline for consistent output quality
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default timeout for Playwright browser fetch (seconds)
DEFAULT_SPA_TIMEOUT = 15

# Install instructions shown when Playwright is not available
_INSTALL_INSTRUCTIONS = (
    "pip install sheaf-ai[browser] && playwright install chromium"
)


def is_playwright_available() -> bool:
    """Check if Playwright is installed and importable.

    Returns:
        True if playwright.sync_api can be imported, False otherwise.
    """
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_spa_content(
    url: str,
    timeout: int = DEFAULT_SPA_TIMEOUT,
    content_type_label: str = "SPA",
) -> dict[str, Any]:
    """Fetch content from an SPA page using Playwright headless browser.

    This is the main entry point for SPA content extraction. It attempts to:
    1. Import Playwright (returns friendly error if missing)
    2. Launch headless Chromium, navigate to URL
    3. Wait for JS rendering and extract HTML
    4. Parse HTML through fetch_article's pipeline for consistent quality

    Args:
        url: The SPA URL to fetch.
        timeout: Browser timeout in seconds (default: 15).
        content_type_label: Human-readable label for error messages.

    Returns:
        Standard handler result dict with keys:
        success, title, text, method, error, content_type, meta.
        If Playwright is not installed, method is "spa_unavailable".
        If Playwright succeeds, method is "playwright".
        If Playwright fails, method is "spa_failed".
    """
    # Layer 3: Playwright not installed
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning(f"Playwright not installed - cannot fetch SPA: {url}")
        return _unavailable_result(content_type_label)

    # Attempt browser fetch
    try:
        pw_result = _playwright_fetch(url, timeout)
    except Exception as e:
        logger.error(f"Playwright fetch exception for {url}: {e}")
        return _failed_result(content_type_label, str(e))

    if not pw_result["success"]:
        return _failed_result(content_type_label, pw_result.get("error", "unknown"))

    # Parse HTML through fetch_article's pipeline
    return _parse_and_build(pw_result["html"], url, content_type_label)


def _playwright_fetch(url: str, timeout: int) -> dict[str, Any]:
    """Execute a Playwright browser fetch.

    Launches headless Chromium, navigates to the URL, waits for JS rendering,
    and extracts the rendered HTML.

    Args:
        url: The URL to fetch.
        timeout: Browser timeout in seconds.

    Returns:
        dict with keys: success, html (str), error (str|None).
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

        # Give JS frameworks time to hydrate
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            # networkidle may timeout on pages with persistent connections
            pass

        title = page.title()
        html = page.content()
        browser.close()

    return {"success": True, "html": html, "title": title, "error": None}


def _parse_and_build(
    html: str,
    url: str,
    content_type_label: str,
) -> dict[str, Any]:
    """Parse raw HTML through fetch_article's pipeline and build result.

    Args:
        html: Raw HTML string from Playwright.
        url: Original URL (for context).
        content_type_label: Label for metadata.

    Returns:
        Standard handler result dict.
    """
    try:
        from sheaf_ai.fetch_article import _parse_html, _build_result
    except ImportError:
        # Fallback: basic HTML-to-text extraction
        logger.warning("fetch_article._parse_html not available, using basic extraction")
        return _basic_html_result(html, content_type_label)

    parsed = _parse_html(html, url)
    if parsed["success"] and parsed["text"]:
        result = _build_result(parsed, "playwright")
        result["meta"] = {
            "rendered_with": "playwright_chromium",
            "spa": True,
        }
        return result

    # Parsing got HTML but text extraction failed - return raw text
    if parsed.get("text"):
        return {
            "success": True,
            "title": parsed["title"],
            "text": parsed["text"],
            "method": "playwright",
            "error": None,
            "quality": parsed.get("quality", {}),
            "meta": {
                "rendered_with": "playwright_chromium",
                "spa": True,
            },
        }

    # Got HTML but no text at all
    return _failed_result(
        content_type_label,
        "Page rendered but no extractable text content found",
    )


def _basic_html_result(html: str, content_type_label: str) -> dict[str, Any]:
    """Fallback extraction when fetch_article pipeline is unavailable.

    Uses basic HTML tag stripping to extract text.

    Args:
        html: Raw HTML string.
        content_type_label: Label for error messages.

    Returns:
        Handler result dict.
    """
    import re
    # Remove script/style tags
    clean = re.sub(r'<(script|style|noscript)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Remove all HTML tags
    text = re.sub(r'<[^>]+>', ' ', clean)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    # Extract title from <title> tag
    title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else ""

    if len(text) >= 50:
        return {
            "success": True,
            "title": title,
            "text": text,
            "method": "playwright",
            "error": None,
            "meta": {
                "rendered_with": "playwright_chromium",
                "spa": True,
                "extraction": "basic_fallback",
            },
        }

    return _failed_result(content_type_label, "No extractable text content found")


def _unavailable_result(content_type_label: str) -> dict[str, Any]:
    """Build a result dict for when Playwright is not installed.

    Args:
        content_type_label: Human-readable content type label.

    Returns:
        Handler result dict with method="spa_unavailable".
    """
    return {
        "success": False,
        "title": "",
        "text": "",
        "method": "spa_unavailable",
        "error": (
            f"Content from {content_type_label} requires JavaScript rendering. "
            f"Install: {_INSTALL_INSTRUCTIONS}"
        ),
        "meta": {"requires_js": True},
    }


def _failed_result(content_type_label: str, error_detail: str) -> dict[str, Any]:
    """Build a result dict for when Playwright fetch fails.

    Args:
        content_type_label: Human-readable content type label.
        error_detail: Specific error message from the failure.

    Returns:
        Handler result dict with method="spa_failed".
    """
    return {
        "success": False,
        "title": "",
        "text": "",
        "method": "spa_failed",
        "error": f"Browser rendering failed for {content_type_label}: {error_detail}",
        "meta": {"requires_js": True},
    }
