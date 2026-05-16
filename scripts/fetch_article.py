"""
Universal Collector — Article Fetcher v2

Platform-aware fetching with smart fallback chain:
  1. Platform detection → choose optimal strategy
  2. requests (lightweight, works for most SSR pages)
  3. Playwright (JS rendering, for dynamic pages)

Key improvements over v1:
  - Single extraction logic (DRY)
  - Platform-aware: skip requests for known JS-heavy domains
  - Better content quality detection (paragraph ratio, not just length)
  - Lazy Playwright init with persistent browser context

Usage:
  from fetch_article import fetch_article
  result = fetch_article(url)  # returns dict with title, text, success, method
"""
import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import Optional
from functools import lru_cache

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ============================================================
# Platform detection — knows which domains need special treatment
# ============================================================

# Domains that almost always need Playwright (JS-heavy rendering)
_PLAYWRIGHT_PREFERRED = {
    "view.inews.qq.com",     # Tencent News
    "news.qq.com",           # Tencent News (alt)
    "x.com",                 # Twitter/X
    "twitter.com",           # Twitter
    "www.zhihu.com",         # Zhihu (JS-heavy)
    "zhuanlan.zhihu.com",    # Zhihu Column
    "bilibili.com",          # Bilibili
    "www.bilibili.com",      # Bilibili
}

# Domains where requests usually works (SSR / static content)
_REQUESTS_OK = {
    "mp.weixin.qq.com",      # WeChat articles (SSR, but sometimes short)
    "arxiv.org",             # arXiv papers
    "medium.com",            # Medium (partial SSR)
}

# Selectors for article content extraction, ordered by priority
_CONTENT_SELECTORS = [
    "#js_content",           # WeChat
    ".rich_media_content",   # WeChat (alt)
    "article",               # HTML5 semantic
    ".article-content",      # Generic
    ".post-content",         # Blog posts
    ".content",              # Generic fallback
    "main",                  # HTML5 semantic
]


def _detect_platform(url: str) -> str:
    """Detect platform from URL, returns domain key."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip www. prefix for matching
        domain_clean = domain.replace("www.", "") if domain.startswith("www.") else domain
        return domain_clean
    except Exception:
        return ""


def _needs_playwright(url: str) -> bool:
    """Check if URL is from a known JS-heavy domain."""
    domain = _detect_platform(url)
    return domain in _PLAYWRIGHT_PREFERRED


def _is_wechat(url: str) -> bool:
    """Check if URL is a WeChat article."""
    return "mp.weixin.qq.com" in url.lower()


# ============================================================
# Content extraction — single source of truth (DRY)
# ============================================================

def _extract_title(soup) -> str:
    """Extract article title with priority chain:
    og:title → twitter:title → #activity-name → <title> → h1 → heading"""
    # 1. Open Graph title
    og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
    if og and og.get("content"):
        content = og["content"].strip()
        if content:
            return content

    # 2. Twitter card title
    tw = soup.find("meta", attrs={"name": "twitter:title"})
    if tw and tw.get("content"):
        content = tw["content"].strip()
        if content:
            return content

    # 3. WeChat specific: #activity-name
    wc = soup.select_one("#activity-name")
    if wc:
        text = wc.get_text(strip=True)
        if text:
            return text

    # 4. Regular <title> tag (cleaned)
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        for suffix in [
            " - 微信公众平台", "_微信公众平台", "_腾讯新闻", " - 知乎",
            " - 知乎专栏", " | Medium", " | bilibili"
        ]:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
                break
        title = title.strip()
        if title:
            return title

    # 5. First <h1>
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return text

    # 6. Any heading (h2, h3) as last resort
    for tag_name in ["h2", "h3"]:
        heading = soup.find(tag_name)
        if heading:
            text = heading.get_text(strip=True)
            if text and len(text) < 200:
                return text

    return ""


def _extract_text(soup) -> str:
    """Extract article body text using selector chain."""
    # Remove noise elements first
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
        tag.decompose()

    # Try specific content containers
    for selector in _CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator="\n", strip=True)
            if len(text) >= 50:
                return _clean_text(text)

    # Fallback: body text
    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        if len(text) >= 50:
            return _clean_text(text)

    return ""


def _clean_text(text: str) -> str:
    """Clean extracted text: collapse newlines, remove noise."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    return text


def _content_quality(text: str) -> dict:
    """Assess content quality. Returns dict with score and reason."""
    if not text:
        return {"ok": False, "reason": "empty", "score": 0}

    length = len(text)
    lines = text.split("\n")
    avg_line_len = sum(len(l) for l in lines) / max(len(lines), 1)
    # Paragraph ratio: lines with >20 chars / total lines
    para_lines = sum(1 for l in lines if len(l.strip()) > 20)
    para_ratio = para_lines / max(len(lines), 1)

    score = 0
    if length >= 200:
        score += 1
    if length >= 1000:
        score += 1
    if avg_line_len > 15:
        score += 1
    if para_ratio > 0.3:
        score += 1

    return {
        "ok": score >= 2,
        "score": score,
        "length": length,
        "reason": "quality_pass" if score >= 2 else "low_quality"
    }


# ============================================================
# Fetch strategies
# ============================================================

_COMMON_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


def _fetch_requests(url: str, timeout: int = 15) -> dict:
    """Lightweight fetch. Returns raw HTML result dict."""
    try:
        resp = requests.get(url, headers=_COMMON_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return {"success": True, "html": resp.text, "error": None}
    except Exception as e:
        return {"success": False, "html": "", "error": str(e)}


def _fetch_playwright(url: str, timeout: int = 15) -> dict:
    """Browser-rendered fetch via Playwright with platform-aware wait strategies."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "html": "", "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

            # Platform-specific wait strategies
            domain = _detect_platform(url)

            if domain == "mp.weixin.qq.com":
                # WeChat: wait for #js_content specifically
                try:
                    page.wait_for_selector("#js_content", timeout=8000)
                    page.wait_for_timeout(1500)
                except Exception:
                    page.wait_for_timeout(3000)
            elif domain in ("view.inews.qq.com", "news.qq.com"):
                # Tencent News: wait for content area
                try:
                    page.wait_for_selector(".content-article, .article", timeout=8000)
                    page.wait_for_timeout(2000)
                except Exception:
                    page.wait_for_timeout(3000)
            else:
                # Generic: give JS time to render
                page.wait_for_timeout(2000)

            # Scroll to trigger lazy content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)

            html = page.content()
            browser.close()

        return {"success": True, "html": html, "error": None}

    except Exception as e:
        return {"success": False, "html": "", "error": str(e)}


def _parse_html(html: str, url: str = "") -> dict:
    """Parse HTML into structured result with title + text."""
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)
    text = _extract_text(soup)
    quality = _content_quality(text)

    return {
        "title": title,
        "text": text if quality["ok"] else "",
        "quality": quality,
        "success": quality["ok"],
    }


# ============================================================
# Main entry point — smart strategy selection
# ============================================================

def fetch_article(url: str, timeout: int = 15) -> dict:
    """
    Fetch article content from URL.

    Strategy selection:
      - Known JS-heavy domains → Playwright first (skip requests)
      - WeChat → requests first (SSR usually works), fallback to Playwright
      - Everything else → requests first, Playwright fallback if content is poor

    Returns dict with:
      - success: bool
      - title: str or ""
      - text: str or ""
      - method: str (requests / playwright / failed)
      - error: str or None
      - quality: dict (content quality assessment)
    """
    domain = _detect_platform(url)

    # Strategy 1: Known JS-heavy → go straight to Playwright
    if domain in _PLAYWRIGHT_PREFERRED:
        logger.info(f"Platform {domain} → Playwright (known JS-heavy)")
        result = _fetch_playwright(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True,
                    "title": parsed["title"],
                    "text": parsed["text"],
                    "method": "playwright",
                    "error": None,
                    "quality": parsed["quality"],
                }
        # Playwright failed — try requests as fallback (rare but worth trying)
        result = _fetch_requests(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True,
                    "title": parsed["title"],
                    "text": parsed["text"],
                    "method": "requests",
                    "error": None,
                    "quality": parsed["quality"],
                }
        return {
            "success": False, "title": "", "text": "",
            "method": "failed", "error": "Both playwright and requests failed"
        }

    # Strategy 2: WeChat → requests first (SSR), Playwright fallback
    if domain == "mp.weixin.qq.com":
        logger.info("WeChat → requests first (SSR)")
        result = _fetch_requests(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                # Additional WeChat check: if content looks too short for a real article
                if len(parsed["text"]) < 500:
                    logger.info(f"WeChat content too short ({len(parsed['text'])} chars), trying Playwright")
                else:
                    return {
                        "success": True,
                        "title": parsed["title"],
                        "text": parsed["text"],
                        "method": "requests",
                        "error": None,
                        "quality": parsed["quality"],
                    }

        # Fallback to Playwright
        logger.info("WeChat → Playwright fallback")
        result = _fetch_playwright(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True,
                    "title": parsed["title"],
                    "text": parsed["text"],
                    "method": "playwright",
                    "error": None,
                    "quality": parsed["quality"],
                }

        # If requests got something but it was short, return it anyway (might be a real short article)
        if result_r := _fetch_requests(url, timeout):
            if result_r["success"]:
                parsed = _parse_html(result_r["html"], url)
                if parsed["text"]:  # Has some content at least
                    return {
                        "success": True,
                        "title": parsed["title"],
                        "text": parsed["text"],
                        "method": "requests-short",
                        "error": None,
                        "quality": parsed["quality"],
                    }

        return {
            "success": False, "title": "", "text": "",
            "method": "failed", "error": "WeChat: both strategies failed"
        }

    # Strategy 3: Default → requests first, Playwright fallback if content poor
    logger.info(f"Default → requests first for {domain}")
    result = _fetch_requests(url, timeout)
    if result["success"]:
        parsed = _parse_html(result["html"], url)
        if parsed["success"]:
            return {
                "success": True,
                "title": parsed["title"],
                "text": parsed["text"],
                "method": "requests",
                "error": None,
                "quality": parsed["quality"],
            }

    # Requests failed or content poor → try Playwright
    logger.info(f"Requests insufficient → Playwright fallback")
    result = _fetch_playwright(url, timeout)
    if result["success"]:
        parsed = _parse_html(result["html"], url)
        if parsed["success"]:
            return {
                "success": True,
                "title": parsed["title"],
                "text": parsed["text"],
                "method": "playwright",
                "error": None,
                "quality": parsed["quality"],
            }

    return {
        "success": False, "title": "", "text": "",
        "method": "failed", "error": "All strategies failed"
    }


# ============================================================
# CLI entry point
# ============================================================
if __name__ == "__main__":
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        print('Usage: python fetch_article.py <url>')
        sys.exit(1)

    # Setup basic logging for CLI mode
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    url = sys.argv[1]
    print(f"Fetching: {url}")
    start = time.time()
    result = fetch_article(url)
    elapsed = time.time() - start

    result["url"] = url
    result["elapsed_sec"] = round(elapsed, 2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
