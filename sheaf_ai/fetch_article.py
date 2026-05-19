"""
Sheaf Article Fetcher v2 — platform-aware fetching with smart fallback.

Strategy:
  1. Platform detection -> choose optimal strategy
  2. requests (lightweight, SSR pages)
  3. Playwright (JS rendering, dynamic pages)

Usage:
    from sheaf_ai.fetch_article import fetch_article
    result = fetch_article(url)
"""
import re
import sys
import json
import time
import logging
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ============================================================
# Platform detection
# ============================================================

_PLAYWRIGHT_PREFERRED = {
    "view.inews.qq.com",
    "news.qq.com",
    "x.com",
    "twitter.com",
    "www.zhihu.com",
    "zhuanlan.zhihu.com",
    "bilibili.com",
    "www.bilibili.com",
}

# ChatGPT share links get dedicated extraction (not generic Playwright)
_CHATGPT_DOMAINS = {
    "chatgpt.com",
    "chat.openai.com",
}

_REQUESTS_OK = {
    "mp.weixin.qq.com",
    "arxiv.org",
    "medium.com",
}

_CONTENT_SELECTORS = [
    "#js_content",
    ".rich_media_content",
    "article",
    ".article-content",
    ".post-content",
    ".content",
    "main",
]


def _detect_platform(url: str) -> str:
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        domain_clean = domain.replace("www.", "") if domain.startswith("www.") else domain
        return domain_clean
    except Exception:
        return ""


def _needs_playwright(url: str) -> bool:
    domain = _detect_platform(url)
    return domain in _PLAYWRIGHT_PREFERRED


# ============================================================
# Content extraction (DRY)
# ============================================================

def _extract_title(soup) -> str:
    og = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "og:title"})
    if og and og.get("content"):
        content = og["content"].strip()
        if content:
            return content

    tw = soup.find("meta", attrs={"name": "twitter:title"})
    if tw and tw.get("content"):
        content = tw["content"].strip()
        if content:
            return content

    wc = soup.select_one("#activity-name")
    if wc:
        text = wc.get_text(strip=True)
        if text:
            return text

    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        for suffix in [
            " - 微信公众平台", "_微信公众平台", "_腾讯新闻", " - 知乎",
            " - 知乎专栏", " | Medium", " | bilibili",
        ]:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
                break
        title = title.strip()
        if title:
            return title

    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return text

    for tag_name in ["h2", "h3"]:
        heading = soup.find(tag_name)
        if heading:
            text = heading.get_text(strip=True)
            if text and len(text) < 200:
                return text

    return ""


def _extract_text(soup) -> str:
    for tag in soup(["script", "style", "noscript", "iframe", "nav", "footer", "header"]):
        tag.decompose()

    for sel in [
        ".video-player", ".player-wrap", ".txp_player", ".bilibili-player",
        "[class*='player']", "[class*='video-wrap']", "[class*='debug']",
        ".video-info", ".play-info", ".upload-log",
    ]:
        for el in soup.select(sel):
            el.decompose()

    for selector in _CONTENT_SELECTORS:
        container = soup.select_one(selector)
        if container:
            text = container.get_text(separator="\n", strip=True)
            if len(text) >= 50:
                return _clean_text(text)

    body = soup.find("body")
    if body:
        text = body.get_text(separator="\n", strip=True)
        if len(text) >= 50:
            return _clean_text(text)

    return ""


_VIDEO_UI_PATTERNS = [
    re.compile(r'^\d{1,2}:\d{2}(?:\s*/\s*\d{1,2}:\d{2})?$'),
    re.compile(r'^\d\.?\d*X$'),
    re.compile(r'^\d{3,4}P'),
    re.compile(r'^(播放|下一个|打开循环播放|静音播放中.*|恢复音量|画中画|网页全屏|全屏|倍速|AirPlay|刷新|试试)$'),
    re.compile(r'^(视频信息|播放信息|上传日志|调试信息|\[X\]|视频ID|VID|播放流水|Flowid|播放内核|Kernel|显示器信息|Res|帧数|缓冲健康度|网络活动|net|视频分辨率|编码|Codec|mystery)$'),
    re.compile(r'^[a-f0-9]{16,}$'),
    re.compile(r'^[a-z]\d[a-z0-9]{6,}$'),
    re.compile(r'^m3u8/'),
    re.compile(r'^avc1\.'),
    re.compile(r'^\(O\d+\)$'),
    re.compile(r'^\d+\*\d+$'),
    re.compile(r'^br:'),
    re.compile(r'^\d+\s*KB/s'),
    re.compile(r'^\d+\.\d+s$'),
    re.compile(r'^\d+\.\d+\.\d+(-p2p.*)?$'),
    re.compile(r'^(登录|内容更精彩|安装电脑版|你可以)$'),
    re.compile(r'^\d+/\d+;\s*\d+\.\d+%'),
    re.compile(r'^[-/]$'),
    re.compile(r'^\d$'),
]


def _clean_text(text: str) -> str:
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            cleaned.append("")
            continue
        skip = False
        for pattern in _VIDEO_UI_PATTERNS:
            if pattern.match(stripped):
                skip = True
                break
        if not skip:
            cleaned.append(stripped)

    text = "\n".join(cleaned)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _content_quality(text: str) -> dict:
    if not text:
        return {"ok": False, "reason": "empty", "score": 0}

    length = len(text)
    lines = text.split("\n")
    avg_line_len = sum(len(l) for l in lines) / max(len(lines), 1)
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
        "reason": "quality_pass" if score >= 2 else "low_quality",
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
    try:
        resp = requests.get(url, headers=_COMMON_HEADERS, timeout=timeout)
        resp.raise_for_status()
        return {"success": True, "html": resp.text, "error": None}
    except Exception as e:
        return {"success": False, "html": "", "error": str(e)}


def _fetch_playwright(url: str, timeout: int = 15) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "html": "", "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")

            domain = _detect_platform(url)

            if domain == "mp.weixin.qq.com":
                try:
                    page.wait_for_selector("#js_content", timeout=8000)
                    page.wait_for_timeout(1500)
                except Exception:
                    page.wait_for_timeout(3000)
            elif domain in ("view.inews.qq.com", "news.qq.com"):
                try:
                    page.wait_for_selector(".content-article, .article", timeout=8000)
                    page.wait_for_timeout(2000)
                except Exception:
                    page.wait_for_timeout(3000)
            else:
                page.wait_for_timeout(2000)

            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)

            html = page.content()
            browser.close()

        return {"success": True, "html": html, "error": None}

    except Exception as e:
        return {"success": False, "html": "", "error": str(e)}


# ============================================================
# ChatGPT share link extraction (dedicated)
# ============================================================

def _fetch_chatgpt_share(url: str, timeout: int = 20) -> dict:
    """
    Extract structured conversation from ChatGPT share links.

    ChatGPT share pages (/share/xxx) are fully JS-rendered SPA.
    Messages use [data-message-author-role] attribute for role detection.

    Returns dict with:
      success, title, text (formatted conversation), method, error,
      meta: { turns, user_msgs, assistant_msgs, source }
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "success": False, "title": "", "text": "",
            "method": "chatgpt", "error": "playwright not installed",
        }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # Navigate with networkidle for SPA
            page.goto(url, timeout=timeout * 1000, wait_until="networkidle")

            # Wait for conversation messages to render
            try:
                page.wait_for_selector(
                    '[data-message-author-role]',
                    timeout=15000,
                )
                # Extra wait for late-loading messages
                page.wait_for_timeout(3000)
            except Exception:
                browser.close()
                return {
                    "success": False, "title": "", "text": "",
                    "method": "chatgpt", "error": "No messages found on page",
                }

            # Extract title from page
            title = page.title()
            # Clean up ChatGPT default title patterns
            for suffix in [" - ChatGPT", " | ChatGPT", "ChatGPT"]:
                if title.endswith(suffix):
                    title = title[:-len(suffix)].strip()
                    break
            if not title or len(title) < 2:
                title = "ChatGPT Conversation"

            # Extract all messages
            messages = page.evaluate("""() => {
                const turns = [];
                const elements = document.querySelectorAll('[data-message-author-role]');
                elements.forEach(el => {
                    const role = el.getAttribute('data-message-author-role');
                    const text = el.innerText || el.textContent || '';
                    if (text.trim()) {
                        turns.push({ role: role, text: text.trim() });
                    }
                });
                return turns;
            }""")

            browser.close()

        if not messages:
            return {
                "success": False, "title": title, "text": "",
                "method": "chatgpt", "error": "No messages extracted",
            }

        # Separate user / assistant messages
        user_msgs = [m for m in messages if m["role"] == "user"]
        assistant_msgs = [m for m in messages if m["role"] == "assistant"]
        total_turns = len(messages)

        # Format conversation as readable text
        formatted_lines = [f"# {title}", ""]
        for i, msg in enumerate(messages, 1):
            role_label = "👤 User" if msg["role"] == "user" else "🤖 Assistant"
            formatted_lines.append(f"## [{role_label}] (Turn {i})")
            formatted_lines.append("")
            formatted_lines.append(msg["text"])
            formatted_lines.append("")

        formatted_text = "\n".join(formatted_lines)

        return {
            "success": True,
            "title": title,
            "text": formatted_text,
            "method": "chatgpt-share",
            "error": None,
            "quality": {
                "ok": True,
                "score": 4,
                "length": len(formatted_text),
                "reason": "chatgpt_conversation",
            },
            "meta": {
                "content_type": "ai_conversation",
                "turns": total_turns,
                "user_msgs": len(user_msgs),
                "assistant_msgs": len(assistant_msgs),
                "source": "chatgpt",
            },
        }

    except Exception as e:
        return {
            "success": False, "title": "", "text": "",
            "method": "chatgpt", "error": str(e),
        }


def _is_chatgpt_share(url: str) -> bool:
    """Check if URL is a ChatGPT share link."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        return domain in _CHATGPT_DOMAINS and "/share/" in parsed.path
    except Exception:
        return False


def _parse_html(html: str, url: str = "") -> dict:
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
# Main entry point
# ============================================================

def fetch_article(url: str, timeout: int = 15) -> dict:
    """
    Fetch article content from URL with smart strategy selection.

    Returns dict: {success, title, text, method, error, quality}
    Special paths:
      - ChatGPT share links -> dedicated conversation extractor
    """
    domain = _detect_platform(url)

    # Strategy 0: ChatGPT share link -> dedicated extraction
    if _is_chatgpt_share(url):
        logger.info(f"ChatGPT share link detected -> dedicated extractor")
        result = _fetch_chatgpt_share(url, timeout)
        if result["success"]:
            return result
        # Fallback to generic Playwright if dedicated fails
        logger.warning("ChatGPT dedicated extractor failed, trying generic Playwright")
        result = _fetch_playwright(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True, "title": parsed["title"], "text": parsed["text"],
                    "method": "playwright", "error": None, "quality": parsed["quality"],
                }
        return {
            "success": False, "title": "", "text": "",
            "method": "failed", "error": "ChatGPT extraction failed (dedicated + fallback)",
        }

    # Strategy 1: Known JS-heavy -> Playwright first
    if domain in _PLAYWRIGHT_PREFERRED:
        logger.info(f"Platform {domain} -> Playwright (known JS-heavy)")
        result = _fetch_playwright(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True, "title": parsed["title"], "text": parsed["text"],
                    "method": "playwright", "error": None, "quality": parsed["quality"],
                }
        result = _fetch_requests(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True, "title": parsed["title"], "text": parsed["text"],
                    "method": "requests", "error": None, "quality": parsed["quality"],
                }
        return {
            "success": False, "title": "", "text": "",
            "method": "failed", "error": "Both playwright and requests failed",
        }

    # Strategy 2: WeChat -> requests first (SSR), Playwright fallback
    if domain == "mp.weixin.qq.com":
        logger.info("WeChat -> requests first (SSR)")
        result = _fetch_requests(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                if len(parsed["text"]) < 500:
                    logger.info(f"WeChat content too short ({len(parsed['text'])} chars), trying Playwright")
                else:
                    return {
                        "success": True, "title": parsed["title"], "text": parsed["text"],
                        "method": "requests", "error": None, "quality": parsed["quality"],
                    }

        logger.info("WeChat -> Playwright fallback")
        result = _fetch_playwright(url, timeout)
        if result["success"]:
            parsed = _parse_html(result["html"], url)
            if parsed["success"]:
                return {
                    "success": True, "title": parsed["title"], "text": parsed["text"],
                    "method": "playwright", "error": None, "quality": parsed["quality"],
                }

        # Short article might be real
        result_r = _fetch_requests(url, timeout)
        if result_r["success"]:
            parsed = _parse_html(result_r["html"], url)
            if parsed["text"]:
                return {
                    "success": True, "title": parsed["title"], "text": parsed["text"],
                    "method": "requests-short", "error": None, "quality": parsed["quality"],
                }

        return {
            "success": False, "title": "", "text": "",
            "method": "failed", "error": "WeChat: both strategies failed",
        }

    # Strategy 3: Default -> requests first, Playwright fallback
    logger.info(f"Default -> requests first for {domain}")
    result = _fetch_requests(url, timeout)
    if result["success"]:
        parsed = _parse_html(result["html"], url)
        if parsed["success"]:
            return {
                "success": True, "title": parsed["title"], "text": parsed["text"],
                "method": "requests", "error": None, "quality": parsed["quality"],
            }

    logger.info("Requests insufficient -> Playwright fallback")
    result = _fetch_playwright(url, timeout)
    if result["success"]:
        parsed = _parse_html(result["html"], url)
        if parsed["success"]:
            return {
                "success": True, "title": parsed["title"], "text": parsed["text"],
                "method": "playwright", "error": None, "quality": parsed["quality"],
            }

    return {
        "success": False, "title": "", "text": "",
        "method": "failed", "error": "All strategies failed",
    }
