"""
Universal Collector — Article Fetcher

Supports three strategies (fallback chain):
1. requests + common headers (lightweight)
2. playwright (browser rendering, heavier but bypasses basic anti-scrape)
3. manual paste (user provides text)

Usage:
  from fetch_article import fetch_article
  result = fetch_article(url)  # returns dict with title, text, success, method
"""
import re
import sys
import json
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup


def fetch_article(url: str, timeout: int = 15) -> dict:
    """
    Fetch article content from URL. Returns dict with:
      - success: bool
      - title: str or ""
      - text: str or ""
      - method: str (which strategy succeeded)
      - error: str or None
    """
    # Strategy 1: requests
    result = _fetch_requests(url, timeout)
    if result["success"]:
        result["method"] = "requests"
        return result

    # Strategy 2: playwright (if available)
    result2 = _fetch_playwright(url, timeout)
    if result2["success"]:
        result2["method"] = "playwright"
        return result2

    # Both failed
    return {
        "success": False,
        "title": "",
        "text": "",
        "method": "failed",
        "error": f"requests: {result.get('error','')}; playwright: {result2.get('error','')}"
    }


def _extract_title(soup) -> str:
    """Extract article title with priority: og:title → twitter:title → #activity-name → <title> → h1 → first heading"""
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

    # 4. Regular <title> tag
    title_tag = soup.find("title")
    if title_tag:
        title = title_tag.get_text(strip=True)
        # Clean common suffixes
        for suffix in [" - 微信公众平台", "_微信公众平台", "_腾讯新闻", " - 知乎"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
                break
        title = title.strip()
        if title:
            return title

    # 5. First <h1> tag
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if text:
            return text

    # 6. Any heading tag (h2, h3) as last resort
    for tag_name in ["h2", "h3"]:
        heading = soup.find(tag_name)
        if heading:
            text = heading.get_text(strip=True)
            if text and len(text) < 200:  # Sanity check
                return text

    return ""


def _fetch_requests(url: str, timeout: int) -> dict:
    """Lightweight fetch with common headers.
    
    For WeChat articles (mp.weixin.qq.com), the initial HTML often contains
    the full article text inside #js_content, but some articles load content
    dynamically. If we detect a WeChat URL and the content is suspiciously
    short (< 500 chars), we return failure to trigger Playwright fallback.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
        html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Remove script/style elements
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()

        title = _extract_title(soup)

        # Extract text from common article containers
        text = ""
        for selector in ["article", ".article", ".rich_media_content", "#js_content", ".content", ".post-content", "main"]:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator="\n", strip=True)
                break

        # Fallback: get all body text
        if not text or len(text) < 100:
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)

        # Clean up: collapse multiple newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) < 50:
            return {"success": False, "title": title, "text": "", "error": "Too short"}

        # WeChat articles: if content is suspiciously short, trigger Playwright fallback
        is_wechat = "mp.weixin.qq.com" in url
        if is_wechat and len(text) < 500:
            return {"success": False, "title": title, "text": "", 
                    "error": f"WeChat article too short ({len(text)} chars), need browser rendering"}

        return {"success": True, "title": title, "text": text, "error": None}

    except Exception as e:
        return {"success": False, "title": "", "text": "", "error": str(e)}


def _fetch_playwright(url: str, timeout: int) -> dict:
    """Browser-rendered fetch via Playwright. 
    
    Handles JS-heavy pages (especially WeChat) that requests can't fully capture.
    Waits for article content to appear before extracting.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {"success": False, "title": "", "text": "", "error": "playwright not installed"}

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            
            # Wait for article content to render
            is_wechat = "mp.weixin.qq.com" in url
            if is_wechat:
                # WeChat: wait specifically for #js_content to populate
                try:
                    page.wait_for_selector("#js_content", timeout=8000)
                    # Extra wait for lazy-loaded images/content
                    page.wait_for_timeout(1500)
                except Exception:
                    page.wait_for_timeout(3000)
            else:
                page.wait_for_timeout(2000)
            
            # Scroll down to trigger any lazy content
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(500)
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            page.wait_for_timeout(500)
            
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "iframe"]):
            tag.decompose()

        title = _extract_title(soup)

        text = ""
        for selector in ["article", ".article", ".rich_media_content", "#js_content", ".content", "main"]:
            container = soup.select_one(selector)
            if container:
                text = container.get_text(separator="\n", strip=True)
                break

        if not text or len(text) < 100:
            body = soup.find("body")
            if body:
                text = body.get_text(separator="\n", strip=True)

        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

        if len(text) < 50:
            return {"success": False, "title": title, "text": "", "error": "Too short"}

        return {"success": True, "title": title, "text": text, "error": None}

    except Exception as e:
        return {"success": False, "title": "", "text": "", "error": str(e)}


# ============================================================
# CLI entry point
# ============================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python fetch_article.py <url>')
        sys.exit(1)

    url = sys.argv[1]
    result = fetch_article(url)
    result["url"] = url
    print(json.dumps(result, ensure_ascii=False, indent=2))
