"""
Sheaf arXiv Paper Collector — fetch paper metadata + abstract from arXiv API.

Uses the arXiv API (Atom XML feed) for paper metadata extraction.
Optionally enriches with Semantic Scholar citation counts when available.

Supported URL formats:
  - https://arxiv.org/abs/2401.12345
  - https://arxiv.org/pdf/2401.12345
  - https://arxiv.org/html/2401.12345
  - https://ar5iv.labs.arxiv.org/html/2401.12345
  - Bare ID: 2401.12345, 2401.12345v2

Design:
  - Pure Python, uses only requests + xml.etree (stdlib)
  - Best-effort Semantic Scholar enrichment (optional, graceful failure)
  - Rich metadata: title, authors, abstract, categories, published date, citation count
  - paper_summarize prompt for crystallization

Usage:
    from sheaf_ai.collectors.arxiv import fetch_arxiv_paper
    result = fetch_arxiv_paper("https://arxiv.org/abs/2401.12345")
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any, Optional
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# arXiv API endpoint
_ARXIV_API = "http://export.arxiv.org/api/query"

# Semantic Scholar API endpoint
_S2_API = "https://api.semanticscholar.org/graph/v1/paper"

# Namespace for arXiv Atom feed
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_ARXIV_NS = "{http://arxiv.org/schemas/atom}"

# arXiv ID pattern (e.g., 2401.12345, 2401.12345v2, cs/0701001)
_ARXIV_ID_RE = re.compile(
    r"(?:^|/)(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+/\d{7}(?:v\d+)?)$"
)


# ============================================================
# URL parsing
# ============================================================

def parse_arxiv_url(url: str) -> Optional[str]:
    """Parse an arXiv URL or bare ID into a normalized arXiv ID.

    Supports:
      - https://arxiv.org/abs/2401.12345
      - https://arxiv.org/pdf/2401.12345
      - https://arxiv.org/html/2401.12345
      - https://ar5iv.labs.arxiv.org/html/2401.12345
      - 2401.12345
      - 2401.12345v2

    Args:
        url: arXiv URL or bare paper ID.

    Returns:
        Normalized arXiv ID string (e.g., "2401.12345"), or None if not valid.
    """
    if not url:
        return None

    # Bare ID (e.g., "2401.12345" or "2401.12345v2")
    if re.match(r"^\d{4}\.\d{4,5}(?:v\d+)?$", url.strip()):
        return url.strip()

    # Old-style ID (e.g., "cs/0701001")
    if re.match(r"^[a-z-]+/\d{7}(?:v\d+)?$", url.strip()):
        return url.strip()

    # URL format
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()

        # Standard arxiv.org URLs
        if host in ("arxiv.org", "www.arxiv.org"):
            path = parsed.path.strip("/")
            # /abs/2401.12345, /pdf/2401.12345, /html/2401.12345
            for prefix in ("abs", "pdf", "html", "format"):
                if path.startswith(prefix + "/"):
                    paper_id = path[len(prefix) + 1:]
                    # Remove .pdf suffix if present
                    if paper_id.endswith(".pdf"):
                        paper_id = paper_id[:-4]
                    return paper_id if paper_id else None
            # /list/cs.AI (listing page, not a specific paper)
            return None

        # ar5iv mirrors
        if "ar5iv" in host:
            path = parsed.path.strip("/")
            if path.startswith("html/"):
                return path[5:] or None
            if path.startswith("abs/"):
                return path[4:] or None
            return None

    except Exception:
        pass

    return None


# ============================================================
# arXiv API fetcher
# ============================================================

def _fetch_arxiv_metadata(paper_id: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch paper metadata from the arXiv API (Atom feed).

    Args:
        paper_id: arXiv paper ID (e.g., "2401.12345").
        timeout: Request timeout in seconds.

    Returns:
        dict with paper metadata, or empty dict on failure.
    """
    params = {"id_list": paper_id, "max_results": "1"}
    headers = {
        "User-Agent": "Sheaf-Bot/0.4.0 (https://github.com/zhelunSun/sheaf-ai)",
    }

    try:
        resp = requests.get(_ARXIV_API, params=params, headers=headers, timeout=timeout)
        resp.raise_for_status()

        root = ET.fromstring(resp.text)

        # Find the first entry
        entries = root.findall(f"{_ATOM_NS}entry")
        if not entries:
            logger.warning(f"No arXiv entry found for ID: {paper_id}")
            return {}

        entry = entries[0]

        # Check if this is an error entry (arXiv returns an entry with <title>Error</title>)
        title_el = entry.find(f"{_ATOM_NS}title")
        if title_el is not None and "Error" in (title_el.text or ""):
            logger.warning(f"arXiv API returned error for ID: {paper_id}")
            return {}

        # Extract fields
        title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""

        # Authors
        authors = []
        for author_el in entry.findall(f"{_ATOM_NS}author"):
            name_el = author_el.find(f"{_ATOM_NS}name")
            if name_el is not None and name_el.text:
                authors.append(name_el.text.strip())

        # Abstract
        abstract_el = entry.find(f"{_ATOM_NS}summary")
        abstract = ""
        if abstract_el is not None and abstract_el.text:
            abstract = abstract_el.text.strip().replace("\n", " ")

        # Published / Updated dates
        published_el = entry.find(f"{_ATOM_NS}published")
        published = published_el.text.strip() if published_el is not None and published_el.text else ""

        updated_el = entry.find(f"{_ATOM_NS}updated")
        updated = updated_el.text.strip() if updated_el is not None and updated_el.text else ""

        # Categories (primary + secondary)
        categories = []
        primary_cat_el = entry.find(f"{_ARXIV_NS}primary_category")
        if primary_cat_el is not None:
            primary = primary_cat_el.get("term", "")
            if primary:
                categories.append(primary)

        for cat_el in entry.findall(f"{_ATOM_NS}category"):
            cat = cat_el.get("term", "")
            if cat and cat not in categories:
                categories.append(cat)

        # DOI
        doi_el = entry.find(f"{_ARXIV_NS}doi")
        doi = doi_el.text.strip() if doi_el is not None and doi_el.text else ""

        # PDF link
        pdf_url = ""
        for link_el in entry.findall(f"{_ATOM_NS}link"):
            if link_el.get("title") == "pdf":
                pdf_url = link_el.get("href", "")
                break

        # Abs page URL (canonical)
        abs_url = f"https://arxiv.org/abs/{paper_id}"

        # Comment (often contains publication info)
        comment_el = entry.find(f"{_ARXIV_NS}comment")
        comment = comment_el.text.strip() if comment_el is not None and comment_el.text else ""

        # Journal reference
        journal_el = entry.find(f"{_ARXIV_NS}journal_ref")
        journal_ref = journal_el.text.strip() if journal_el is not None and journal_el.text else ""

        return {
            "arxiv_id": paper_id,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "categories": categories,
            "published": published,
            "updated": updated,
            "doi": doi,
            "pdf_url": pdf_url or f"https://arxiv.org/pdf/{paper_id}",
            "abs_url": abs_url,
            "comment": comment,
            "journal_ref": journal_ref,
            "_raw_entry": True,
        }

    except ET.ParseError as e:
        logger.warning(f"arXiv API XML parse error for {paper_id}: {e}")
        return {}
    except Exception as e:
        logger.warning(f"arXiv API fetch failed for {paper_id}: {e}")
        return {}


# ============================================================
# Semantic Scholar enrichment (optional)
# ============================================================

def _fetch_s2_citations(arxiv_id: str, timeout: int = 10) -> dict[str, Any]:
    """Fetch citation count and paper info from Semantic Scholar.

    This is best-effort: if the API is unavailable, returns empty dict.
    Uses the arXiv ID to look up the paper.

    Args:
        arxiv_id: arXiv paper ID.
        timeout: Request timeout in seconds.

    Returns:
        dict with citation_count, reference_count, influential_citation_count,
        or empty dict on failure.
    """
    params = {"fields": "citationCount,referenceCount,influentialCitationCount,title,year"}
    headers = {
        "User-Agent": "Sheaf-Bot/0.4.0 (https://github.com/zhelunSun/sheaf-ai)",
    }

    try:
        resp = requests.get(
            f"{_S2_API}/ArXiv:{arxiv_id}",
            params=params,
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code == 404:
            logger.debug(f"Semantic Scholar: paper not found for arXiv:{arxiv_id}")
            return {}
        resp.raise_for_status()
        data = resp.json()

        return {
            "citation_count": data.get("citationCount", 0),
            "reference_count": data.get("referenceCount", 0),
            "influential_citation_count": data.get("influentialCitationCount", 0),
            "s2_year": data.get("year"),
        }
    except Exception as e:
        logger.debug(f"Semantic Scholar fetch failed for {arxiv_id}: {e}")
        return {}


# ============================================================
# Formatting
# ============================================================

def _build_paper_text(metadata: dict[str, Any], s2_data: dict[str, Any], max_abstract: int = 4000) -> str:
    """Build the combined text representation of an arXiv paper.

    Args:
        metadata: Paper metadata from arXiv API.
        s2_data: Semantic Scholar enrichment data.
        max_abstract: Maximum abstract characters to include.

    Returns:
        Formatted text string.
    """
    parts = []

    title = metadata.get("title", "")
    if title:
        parts.append(f"# {title}")

    # Authors
    authors = metadata.get("authors", [])
    if authors:
        parts.append(f"\nAuthors: {', '.join(authors)}")

    # Meta line
    meta_items = []
    if metadata.get("published"):
        meta_items.append(f"Published: {metadata['published'][:10]}")
    if metadata.get("categories"):
        meta_items.append(f"Categories: {', '.join(metadata['categories'])}")
    if metadata.get("doi"):
        meta_items.append(f"DOI: {metadata['doi']}")
    if metadata.get("journal_ref"):
        meta_items.append(f"Journal: {metadata['journal_ref']}")
    if s2_data.get("citation_count") is not None:
        meta_items.append(f"Citations: {s2_data['citation_count']}")
    if s2_data.get("s2_year"):
        meta_items.append(f"Year: {s2_data['s2_year']}")
    if meta_items:
        parts.append("\n" + " | ".join(meta_items))

    # Comment (often has page count, conference info)
    comment = metadata.get("comment", "")
    if comment:
        parts.append(f"\n> {comment}")

    # Abstract
    abstract = metadata.get("abstract", "")
    if abstract:
        if len(abstract) > max_abstract:
            abstract = abstract[:max_abstract] + "..."
        parts.append("\n## Abstract\n")
        parts.append(abstract)

    # URLs
    abs_url = metadata.get("abs_url", "")
    pdf_url = metadata.get("pdf_url", "")
    if abs_url:
        parts.append(f"\n[arXiv page]({abs_url})")
    if pdf_url:
        parts.append(f"[PDF]({pdf_url})")

    return "\n".join(parts)


# ============================================================
# Paper summarize prompt for crystallization
# ============================================================

PAPER_SUMMARIZE_PROMPT = """You are a research paper analyst. Given the following arXiv paper metadata and abstract, extract:

1. **Core contribution** (1-2 sentences): What is the main novel idea?
2. **Method summary** (2-3 sentences): What approach/technique is used?
3. **Key findings** (bullet points): Main results or claims.
4. **Relevance tags** (3-5 tags): What domains/topics does this relate to?
5. **Quality assessment** (A/B/C): Is this a landmark paper (A), solid work (B), or incremental (C)?

Paper information:
{paper_text}

Respond in JSON format:
{{
    "contribution": "...",
    "method": "...",
    "findings": ["...", "..."],
    "tags": ["...", "..."],
    "quality": "A|B|C"
}}"""


# ============================================================
# Main entry point
# ============================================================

def fetch_arxiv_paper(url: str, timeout: int = 15, enrich_s2: bool = True, **kwargs) -> dict[str, Any]:
    """Fetch an arXiv paper's metadata + abstract + citation data.

    This is the main entry point for the arXiv paper collector,
    compatible with the UC handler interface: callable(url) -> dict.

    Args:
        url: arXiv URL (e.g., https://arxiv.org/abs/2401.12345) or bare paper ID.
        timeout: API request timeout in seconds.
        enrich_s2: Whether to enrich with Semantic Scholar citation data.
        **kwargs: Additional arguments (ignored).

    Returns:
        dict with keys:
            success: bool
            title: str (paper title)
            text: str (formatted: metadata + abstract)
            method: str ("arxiv-api")
            error: str or None
            meta: dict with raw metadata
    """
    # Parse URL to arXiv ID
    paper_id = parse_arxiv_url(url)
    if paper_id is None:
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "arxiv-api",
            "error": "Not a valid arXiv URL or paper ID",
            "meta": {},
        }

    logger.info(f"Fetching arXiv paper: {paper_id}")

    # Fetch metadata from arXiv API
    metadata = _fetch_arxiv_metadata(paper_id, timeout=timeout)

    if not metadata:
        return {
            "success": False,
            "title": f"arXiv:{paper_id}",
            "text": "",
            "method": "arxiv-api",
            "error": f"Paper not found on arXiv: {paper_id}",
            "meta": {"arxiv_id": paper_id, "url": url},
        }

    # Enrich with Semantic Scholar (best-effort)
    s2_data = {}
    if enrich_s2:
        try:
            s2_data = _fetch_s2_citations(paper_id, timeout=timeout)
        except Exception as e:
            logger.debug(f"Semantic Scholar enrichment failed: {e}")

    # Build combined text
    text = _build_paper_text(metadata, s2_data)
    title = metadata.get("title", f"arXiv:{paper_id}")

    # Build meta dict
    meta: dict[str, Any] = {
        "source": "arxiv",
        "arxiv_id": paper_id,
        "url": url,
        "abs_url": metadata.get("abs_url", ""),
        "pdf_url": metadata.get("pdf_url", ""),
        "authors": metadata.get("authors", []),
        "categories": metadata.get("categories", []),
        "published": metadata.get("published", ""),
        "doi": metadata.get("doi", ""),
        "journal_ref": metadata.get("journal_ref", ""),
    }

    # Add S2 data if available
    if s2_data:
        meta["citation_count"] = s2_data.get("citation_count", 0)
        meta["reference_count"] = s2_data.get("reference_count", 0)
        meta["s2_year"] = s2_data.get("s2_year")

    return {
        "success": True,
        "title": title,
        "text": text,
        "method": "arxiv-api",
        "error": None,
        "meta": meta,
        "quality": {
            "ok": True,
            "score": 4 if metadata.get("abstract") else 2,
            "length": len(text),
            "reason": "arxiv_paper",
        },
    }
