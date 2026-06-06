"""
Sheaf Universal Collector — content type detection and handler routing.

The UC pipeline detects the type of a URL/content and routes it to the
appropriate handler (GitHub repo, arXiv paper, YouTube video, PDF, generic web, etc.).

Usage:
    from sheaf_ai.collectors import detect_content_type, route_fetch

    content_type = detect_content_type(url)
    result = route_fetch(url, content_type=content_type)
"""
from sheaf_ai.collectors.router import (
    ContentType,
    detect_content_type,
    detect_from_url,
    detect_from_headers,
    route_fetch,
    register_handler,
    get_handler,
)
from sheaf_ai.collectors.github import fetch_github_repo
from sheaf_ai.collectors.pdf import fetch_pdf, fetch_pdf_from_bytes
from sheaf_ai.collectors.arxiv import fetch_arxiv_paper
from sheaf_ai.collectors.spa_fetcher import fetch_spa_content, is_playwright_available
from sheaf_ai.collectors.semantic_scholar import fetch_semantic_scholar
from sheaf_ai.collectors.paper_handler import fetch_paper, PAPER_SUMMARIZE_PROMPT

# Register built-in handlers
register_handler(ContentType.GITHUB_REPO, fetch_github_repo)
register_handler(ContentType.PDF_FILE, fetch_pdf)
register_handler(ContentType.ARXIV_PAPER, fetch_arxiv_paper)
register_handler(ContentType.SEMANTIC_SCHOLAR_PAPER, fetch_semantic_scholar)
register_handler(ContentType.DOI_PAPER, fetch_paper)  # Issue #46

__all__ = [
    "ContentType",
    "detect_content_type",
    "detect_from_url",
    "detect_from_headers",
    "route_fetch",
    "register_handler",
    "get_handler",
    "fetch_github_repo",
    "fetch_pdf",
    "fetch_pdf_from_bytes",
    "fetch_arxiv_paper",
    "fetch_spa_content",
    "is_playwright_available",
    "fetch_semantic_scholar",
    "fetch_paper",
    "PAPER_SUMMARIZE_PROMPT",
]
