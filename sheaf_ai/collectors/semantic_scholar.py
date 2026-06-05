"""
Sheaf Semantic Scholar Handler — fetch paper metadata from Semantic Scholar URLs.

Handles URLs like:
  https://www.semanticscholar.org/paper/Attention-is-All-you-Need-Vaswani-Shazeer/204e3073870fae3d05bcbc2f6a8e263d9b72e776

Strategy:
  1. Extract paper ID from URL
  2. Query Semantic Scholar API for metadata
  3. Build text from title + abstract + metadata
  4. Fallback to generic web fetch if API fails

Reference: Issue #75
"""
from __future__ import annotations

import logging
import re
from typing import Any

import requests

logger = logging.getLogger(__name__)

_S2_API = "https://api.semanticscholar.org/graph/v1/paper"


def _parse_s2_url(url: str) -> str | None:
    """Extract Semantic Scholar paper ID from URL.

    Supports formats:
      - /paper/<title-slug>/<paper-id>
      - /paper/<paper-id>

    Args:
        url: The Semantic Scholar URL.

    Returns:
        The paper ID (40-char hex), or None if not parseable.
    """
    m = re.match(
        r'https?://(?:www\.)?semanticscholar\.org/paper/(?:[^/]+/)?([a-f0-9]{40})',
        url,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    return None


def fetch_semantic_scholar(url: str, **kwargs) -> dict[str, Any]:
    """Fetch a Semantic Scholar paper page.

    Args:
        url: The Semantic Scholar paper URL.
        **kwargs: Additional arguments (unused).

    Returns:
        Standard handler result dict with keys: success, title, text, method, error, meta.
    """
    paper_id = _parse_s2_url(url)
    if not paper_id:
        logger.warning(f"Could not parse Semantic Scholar URL: {url}")
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "semantic_scholar",
            "error": f"Could not extract paper ID from URL: {url}",
            "meta": {},
        }

    # Query Semantic Scholar API
    fields = "title,abstract,authors,year,citationCount,referenceCount,externalIds,url"
    headers = {
        "User-Agent": "Sheaf-Bot/0.4.0 (https://github.com/zhelunSun/sheaf-ai)",
    }

    try:
        resp = requests.get(
            f"{_S2_API}/{paper_id}",
            params={"fields": fields},
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return {
                "success": False,
                "title": "",
                "text": "",
                "method": "semantic_scholar",
                "error": f"Paper not found on Semantic Scholar: {paper_id}",
                "meta": {},
            }
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        logger.warning(f"Semantic Scholar API failed for {paper_id}: {e}")
        # Fallback to generic web fetch
        return _fallback_web_fetch(url, error=str(e))

    # Build text
    title = data.get("title", "")
    abstract = data.get("abstract", "")
    authors = data.get("authors", [])
    year = data.get("year")
    citation_count = data.get("citationCount", 0)
    reference_count = data.get("referenceCount", 0)
    ext_ids = data.get("externalIds", {})

    parts = []
    if title:
        parts.append(f"# {title}")
        parts.append("")

    # Authors
    if authors:
        author_names = [a.get("name", "") for a in authors[:20]]
        parts.append(f"Authors: {', '.join(author_names)}")
        parts.append("")

    # Year
    if year:
        parts.append(f"Year: {year}")

    # Citations
    parts.append(f"Citations: {citation_count}")
    parts.append(f"References: {reference_count}")
    parts.append("")

    # External IDs
    if ext_ids:
        if ext_ids.get("ArXiv"):
            parts.append(f"arXiv: {ext_ids['ArXiv']}")
        if ext_ids.get("DOI"):
            parts.append(f"DOI: {ext_ids['DOI']}")
        parts.append("")

    # Abstract
    if abstract:
        parts.append("## Abstract")
        parts.append("")
        parts.append(abstract[:4000])

    text = "\n".join(parts)

    return {
        "success": True,
        "title": title,
        "text": text,
        "method": "semantic_scholar_api",
        "error": None,
        "meta": {
            "paper_id": paper_id,
            "citation_count": citation_count,
            "reference_count": reference_count,
            "year": year,
            "arxiv_id": ext_ids.get("ArXiv"),
            "doi": ext_ids.get("DOI"),
        },
    }


def _fallback_web_fetch(url: str, error: str = "") -> dict[str, Any]:
    """Fallback to generic web fetcher when Semantic Scholar API fails.

    Args:
        url: The original URL.
        error: The error that triggered the fallback.

    Returns:
        Standard handler result dict.
    """
    try:
        from sheaf_ai.fetch_article import fetch_article
        result = fetch_article(url)
        if result["success"]:
            result["method"] = "semantic_scholar_web_fallback"
        return result
    except Exception as fallback_err:
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "semantic_scholar",
            "error": f"API failed ({error}), web fallback also failed ({fallback_err})",
            "meta": {},
        }
