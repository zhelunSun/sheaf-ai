"""
Sheaf Universal Collector — content type detection and handler routing.

The UC pipeline detects the type of a URL/content and routes it to the
appropriate handler (GitHub repo, arXiv paper, YouTube video, generic web, etc.).

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

__all__ = [
    "ContentType",
    "detect_content_type",
    "detect_from_url",
    "detect_from_headers",
    "route_fetch",
    "register_handler",
    "get_handler",
]
