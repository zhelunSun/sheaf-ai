"""
Sheaf Content Type Router — detect content type from URL/headers and route to handlers.

Strategies (in priority order):
  1. URL pattern matching — fast, no network required
  2. HTTP Content-Type header — requires HEAD request
  3. HTML meta tag inspection — requires GET request (lazy)

Design principles:
  - Pure Python, no external dependencies beyond requests (already used)
  - Extensible: register_handler() for adding new handlers
  - Graceful degradation: unknown types fall back to generic web fetcher
"""
from __future__ import annotations

import logging
import re
from enum import Enum
from typing import Any, Callable, Optional

import requests

logger = logging.getLogger(__name__)


# ============================================================
# Content type enum
# ============================================================

class ContentType(str, Enum):
    """Supported content types for the UC pipeline."""
    GITHUB_REPO = "github_repo"
    ARXIV_PAPER = "arxiv_paper"
    YOUTUBE_VIDEO = "youtube_video"
    BILIBILI_VIDEO = "bilibili_video"
    TWITTER_POST = "twitter_post"
    PDF_FILE = "pdf_file"
    IMAGE_FILE = "image_file"
    WEBPAGE = "webpage"
    WECHAT_ARTICLE = "wechat_article"
    # Chinese content platforms (Issue #68)
    DOUBAO_POST = "doubao_post"           # 豆包/扣子
    ZHIHU_ARTICLE = "zhihu_article"       # 知乎专栏/回答
    XIAOHONGSHU_NOTE = "xiaohongshu_note" # 小红书
    JIKE_POST = "jike_post"               # 即刻
    SSPAI_ARTICLE = "sspai_article"       # 少数派
    KR36_ARTICLE = "kr36_article"         # 36氪
    HUXIU_ARTICLE = "huxiu_article"       # 虎嗅
    IFANR_ARTICLE = "ifanr_article"       # 爱范儿
    FEISHU_DOC = "feishu_doc"             # 飞书文档
    NOTION_PAGE = "notion_page"           # Notion 公开页面
    SEMANTIC_SCHOLAR_PAPER = "semantic_scholar_paper"  # Semantic Scholar (Issue #75)
    UNKNOWN = "unknown"

    @property
    def label(self) -> str:
        """Human-readable label for CLI display."""
        labels = {
            "github_repo": "GitHub Repo",
            "arxiv_paper": "arXiv Paper",
            "youtube_video": "YouTube Video",
            "bilibili_video": "Bilibili Video",
            "twitter_post": "X/Twitter Post",
            "pdf_file": "PDF Document",
            "image_file": "Image",
            "webpage": "Web Page",
            "wechat_article": "WeChat Article",
            # Chinese content platforms (Issue #68)
            "doubao_post": "Doubao/Coze Post",
            "zhihu_article": "Zhihu Article",
            "xiaohongshu_note": "Xiaohongshu Note",
            "jike_post": "Jike Post",
            "sspai_article": "SSPai Article",
            "kr36_article": "36Kr Article",
            "huxiu_article": "Huxiu Article",
            "ifanr_article": "ifanr Article",
            "feishu_doc": "Feishu Doc",
            "notion_page": "Notion Page",
            "semantic_scholar_paper": "Semantic Scholar Paper",
            "unknown": "Unknown",
        }
        return labels.get(self.value, self.value)


# ============================================================
# URL pattern registry (30+ patterns)
# ============================================================

# Each pattern maps to (regex_pattern, content_type, priority)
# Lower priority number = higher priority (matched first)
_URL_PATTERNS: list[tuple[re.Pattern, ContentType, int]] = [
    # GitHub repos
    (re.compile(
        r'https?://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:/(?:tree|blob|issues|pull|releases|wiki|actions))?/?',
        re.IGNORECASE,
    ), ContentType.GITHUB_REPO, 10),

    # GitHub Gist
    (re.compile(
        r'https?://gist\.github\.com/[\w-]+/[a-f0-9]+',
        re.IGNORECASE,
    ), ContentType.GITHUB_REPO, 11),

    # arXiv papers (multiple URL formats)
    (re.compile(
        r'https?://arxiv\.org/(?:abs|pdf|html|list|search|format)/',
        re.IGNORECASE,
    ), ContentType.ARXIV_PAPER, 20),

    (re.compile(
        r'https?://ar5iv\.(?:labs\.)?arxiv\.org/html/',
        re.IGNORECASE,
    ), ContentType.ARXIV_PAPER, 21),

    (re.compile(
        r'https?://arxiv\.org/pdf/\d+\.\d+',
        re.IGNORECASE,
    ), ContentType.ARXIV_PAPER, 22),

    # Semantic Scholar (Issue #75)
    (re.compile(
        r'https?://(?:www\.)?semanticscholar\.org/paper/',
        re.IGNORECASE,
    ), ContentType.SEMANTIC_SCHOLAR_PAPER, 25),

    # YouTube
    (re.compile(
        r'https?://(?:www\.)?(?:youtube\.com/(?:watch|shorts|embed|live|playlist)|youtu\.be/)',
        re.IGNORECASE,
    ), ContentType.YOUTUBE_VIDEO, 30),

    # Bilibili
    (re.compile(
        r'https?://(?:www\.)?bilibili\.com/(?:video|bangumi)/',
        re.IGNORECASE,
    ), ContentType.BILIBILI_VIDEO, 31),

    (re.compile(
        r'https?://b23\.tv/',
        re.IGNORECASE,
    ), ContentType.BILIBILI_VIDEO, 32),

    # X/Twitter
    (re.compile(
        r'https?://(?:www\.)?(?:x\.com|twitter\.com)/[\w]+/status/',
        re.IGNORECASE,
    ), ContentType.TWITTER_POST, 40),

    # WeChat articles
    (re.compile(
        r'https?://mp\.weixin\.qq\.com/s/',
        re.IGNORECASE,
    ), ContentType.WECHAT_ARTICLE, 50),

    # ── Chinese content platforms (Issue #68) ──────────────────

    # 豆包/扣子
    (re.compile(
        r'https?://www\.doubao\.com/thread/',
        re.IGNORECASE,
    ), ContentType.DOUBAO_POST, 70),
    (re.compile(
        r'https?://www\.coze\.com/s/',
        re.IGNORECASE,
    ), ContentType.DOUBAO_POST, 71),
    (re.compile(
        r'https?://www\.coze\.cn/s/',
        re.IGNORECASE,
    ), ContentType.DOUBAO_POST, 72),

    # 知乎
    (re.compile(
        r'https?://zhuanlan\.zhihu\.com/p/',
        re.IGNORECASE,
    ), ContentType.ZHIHU_ARTICLE, 80),
    (re.compile(
        r'https?://www\.zhihu\.com/question/\d+/answer/',
        re.IGNORECASE,
    ), ContentType.ZHIHU_ARTICLE, 81),
    (re.compile(
        r'https?://www\.zhihu\.com/pin/',
        re.IGNORECASE,
    ), ContentType.ZHIHU_ARTICLE, 82),

    # 小红书
    (re.compile(
        r'https?://www\.xiaohongshu\.com/(?:explore|discovery)/',
        re.IGNORECASE,
    ), ContentType.XIAOHONGSHU_NOTE, 90),
    (re.compile(
        r'https?://www\.xiaohongshu\.com/user/profile/',
        re.IGNORECASE,
    ), ContentType.XIAOHONGSHU_NOTE, 91),
    (re.compile(
        r'https?://xhslink\.com/',
        re.IGNORECASE,
    ), ContentType.XIAOHONGSHU_NOTE, 92),

    # 即刻
    (re.compile(
        r'https?://m\.okjike\.com/',
        re.IGNORECASE,
    ), ContentType.JIKE_POST, 100),
    (re.compile(
        r'https?://web\.okjike\.com/',
        re.IGNORECASE,
    ), ContentType.JIKE_POST, 101),

    # 少数派
    (re.compile(
        r'https?://sspai\.com/post/',
        re.IGNORECASE,
    ), ContentType.SSPAI_ARTICLE, 110),

    # 36氪
    (re.compile(
        r'https?://36kr\.com/p/',
        re.IGNORECASE,
    ), ContentType.KR36_ARTICLE, 120),

    # 虎嗅
    (re.compile(
        r'https?://www\.huxiu\.com/article/',
        re.IGNORECASE,
    ), ContentType.HUXIU_ARTICLE, 130),
    (re.compile(
        r'https?://www\.huxiu\.com/moment/',
        re.IGNORECASE,
    ), ContentType.HUXIU_ARTICLE, 131),

    # 爱范儿
    (re.compile(
        r'https?://www\.ifanr\.com/\d+',
        re.IGNORECASE,
    ), ContentType.IFANR_ARTICLE, 140),

    # 飞书文档
    (re.compile(
        r'https?://[a-z0-9-]+\.feishu\.cn/(?:doc|docx|wiki|sheets)/',
        re.IGNORECASE,
    ), ContentType.FEISHU_DOC, 150),

    # Notion 公开页面
    (re.compile(
        r'https?://[a-z0-9-]+\.notion\.site/',
        re.IGNORECASE,
    ), ContentType.NOTION_PAGE, 160),
    (re.compile(
        r'https?://www\.notion\.so/[a-z0-9-]+/',
        re.IGNORECASE,
    ), ContentType.NOTION_PAGE, 161),

    # ── End Chinese platforms ───────────────────────────────────

    # PDF files (URL ending or Content-Type)
    (re.compile(
        r'.*\.pdf(?:\?.*)?$',
        re.IGNORECASE,
    ), ContentType.PDF_FILE, 60),

    # Image files
    (re.compile(
        r'.*\.(?:jpg|jpeg|png|gif|webp|svg|bmp|ico)(?:\?.*)?$',
        re.IGNORECASE,
    ), ContentType.IMAGE_FILE, 61),
]


# SPA platforms — require JavaScript rendering (Playwright)
_SPA_PLATFORMS: set[ContentType] = {
    ContentType.DOUBAO_POST,
    ContentType.XIAOHONGSHU_NOTE,
    ContentType.JIKE_POST,
    ContentType.FEISHU_DOC,
    ContentType.NOTION_PAGE,
}


# ============================================================
# Detection functions
# ============================================================

def detect_from_url(url: str) -> Optional[ContentType]:
    """Detect content type from URL pattern alone (no network request).

    Args:
        url: The URL to classify.

    Returns:
        ContentType or None if no pattern matches.
    """
    if not url or not url.startswith("http"):
        return None

    for pattern, content_type, _priority in sorted(
        _URL_PATTERNS, key=lambda x: x[2]
    ):
        if pattern.match(url):
            return content_type

    return None


def detect_from_headers(url: str, timeout: int = 5) -> Optional[ContentType]:
    """Detect content type from HTTP HEAD response headers.

    Uses Content-Type and Content-Disposition headers.

    Args:
        url: The URL to HEAD-request.
        timeout: Request timeout in seconds.

    Returns:
        ContentType or None if no header-based detection succeeds.
    """
    try:
        resp = requests.head(
            url,
            allow_redirects=True,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        content_type = resp.headers.get("Content-Type", "").lower()
        content_disp = resp.headers.get("Content-Disposition", "").lower()

        # PDF from Content-Type
        if "application/pdf" in content_type:
            return ContentType.PDF_FILE

        # PDF from Content-Disposition
        if ".pdf" in content_disp:
            return ContentType.PDF_FILE

        # Image from Content-Type
        if content_type.startswith("image/"):
            return ContentType.IMAGE_FILE

        # HTML from Content-Type (generic webpage)
        if "text/html" in content_type:
            return ContentType.WEBPAGE

    except Exception as e:
        logger.debug(f"HEAD request failed for {url}: {e}")

    return None


def detect_content_type(
    url: str,
    use_headers: bool = True,
    timeout: int = 5,
) -> ContentType:
    """Detect content type using all available strategies.

    Strategy priority:
      1. URL pattern matching (instant, no network)
      2. HTTP headers (if use_headers=True, requires HEAD request)
      3. Fallback to ContentType.UNKNOWN

    Args:
        url: The URL to classify.
        use_headers: Whether to use HTTP HEAD for fallback detection.
        timeout: Timeout for HTTP HEAD request.

    Returns:
        The detected ContentType.
    """
    # Strategy 1: URL pattern (fastest)
    url_result = detect_from_url(url)
    if url_result is not None:
        return url_result

    # Strategy 2: HTTP headers
    if use_headers:
        header_result = detect_from_headers(url, timeout=timeout)
        if header_result is not None:
            return header_result

    # Strategy 3: Fallback
    return ContentType.UNKNOWN


# ============================================================
# Handler registry and routing
# ============================================================

# Handler type: a callable that takes (url, **kwargs) and returns a dict
Handler = Callable[[str], dict[str, Any]]

# Global handler registry
_HANDLERS: dict[ContentType, Handler] = {}


def register_handler(content_type: ContentType, handler: Handler) -> None:
    """Register a handler function for a content type.

    Args:
        content_type: The ContentType this handler handles.
        handler: A callable(url: str) -> dict with keys:
            success, title, text, method, error, meta.
    """
    _HANDLERS[content_type] = handler
    logger.debug(f"Registered handler for {content_type.value}: {handler.__name__}")


def get_handler(content_type: ContentType) -> Optional[Handler]:
    """Get the registered handler for a content type.

    Args:
        content_type: The ContentType to look up.

    Returns:
        The handler callable, or None if not registered.
    """
    return _HANDLERS.get(content_type)


def _try_spa_fetch(url: str, content_type: ContentType, **kwargs) -> dict[str, Any]:
    """Try fetching an SPA page via Playwright.

    Delegates to spa_fetcher module for the actual browser rendering.
    Returns a standard handler result dict. If Playwright is not installed,
    returns a friendly error with install instructions.

    Args:
        url: The SPA URL to fetch.
        content_type: The detected ContentType (for metadata).
        **kwargs: Additional arguments (e.g. timeout).

    Returns:
        dict with keys: success, title, text, method, error, content_type, meta.
    """
    from sheaf_ai.collectors.spa_fetcher import fetch_spa_content

    timeout = kwargs.pop("timeout", 15)
    logger.info(f"SPA platform {content_type.value} -> Playwright fetch for {url}")

    result = fetch_spa_content(
        url,
        timeout=timeout,
        content_type_label=content_type.label,
    )
    result["content_type"] = content_type.value
    return result


def route_fetch(url: str, content_type: Optional[ContentType] = None, **kwargs) -> dict[str, Any]:
    """Route a URL to the appropriate handler based on content type.

    If no content_type is provided, auto-detect it.
    For SPA platforms (_SPA_PLATFORMS), automatically uses Playwright.
    Falls back to generic web fetcher if no handler is registered.

    Args:
        url: The URL to fetch.
        content_type: Override content type detection (None = auto-detect).
        **kwargs: Additional arguments passed to the handler.

    Returns:
        dict with keys: success, title, text, method, error, meta, content_type
    """
    if content_type is None:
        content_type = detect_content_type(url)

    # SPA auto-degradation: route to Playwright for JS-rendered platforms
    if content_type in _SPA_PLATFORMS:
        return _try_spa_fetch(url, content_type, **kwargs)

    handler = get_handler(content_type)

    if handler is not None:
        logger.info(f"Routing {url} -> {content_type.value} handler ({handler.__name__})")
        try:
            result = handler(url, **kwargs)
            result["content_type"] = content_type.value
            return result
        except Exception as e:
            logger.error(f"Handler {handler.__name__} failed: {e}")
            return {
                "success": False,
                "title": "",
                "text": "",
                "method": content_type.value,
                "error": str(e),
                "content_type": content_type.value,
                "meta": {},
            }

    # No handler registered — fall back to generic web fetch
    logger.info(f"No handler for {content_type.value}, falling back to generic web fetch")
    from sheaf_ai.fetch_article import fetch_article

    result = fetch_article(url, **kwargs)
    result["content_type"] = content_type.value
    return result
