"""
Sheaf Paper Handler — unified academic paper metadata extraction.

Issue #46: A dedicated handler for academic papers that unifies
arXiv, Semantic Scholar, DOI, and PDF metadata extraction.

Architecture:
  fetch_paper(url)
    ├── arxiv.org → delegate to arxiv handler
    ├── semanticscholar.org → delegate to S2 handler
    ├── doi.org → resolve DOI → Crossref metadata
    ├── *.pdf → delegate to PDF handler
    └── other academic URLs → best-effort web fetch

All paper handlers return a unified metadata format with:
  - title, authors, abstract, year
  - arxiv_id, doi, citation_count
  - paper_summarize prompt hint for crystallize
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================
# Paper Summary Prompt (for crystallize)
# ============================================================

PAPER_SUMMARIZE_PROMPT = """You are a research assistant analyzing an academic paper. Provide:

1. **Core Argument**: What is the main contribution of this paper?
2. **Methodology**: What approach/algorithm/architecture is used?
3. **Key Results**: What are the most important findings or benchmarks?
4. **Limitations**: What are the stated or apparent limitations?
5. **Relevance**: How does this relate to the user's research interests?
6. **Action Items**: What follow-up actions should the user take?
   (read more, cite, reproduce experiment, compare with method X, etc.)

Respond in structured format with clear headings."""


# ============================================================
# DOI Resolution
# ============================================================

def _resolve_doi(doi: str, timeout: int = 15) -> dict[str, Any]:
    """Resolve a DOI to paper metadata via Crossref API.

    Best-effort: returns empty dict on failure.
    """
    try:
        import requests
        # Crossref content negotiation
        url = f"https://api.crossref.org/works/{doi}"
        headers = {"Accept": "application/json"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code != 200:
            return {}

        data = resp.json().get("message", {})

        # Extract authors
        authors = []
        for author in data.get("author", []):
            given = author.get("given", "")
            family = author.get("family", "")
            authors.append(f"{given} {family}".strip())

        # Extract year
        date_parts = (
            data.get("published-print") or data.get("published-online") or {}
        ).get("date-parts", [[]])
        year = date_parts[0][0] if date_parts and date_parts[0] else None

        # Extract abstract (Crossref may not have it)
        abstract = data.get("abstract", "")
        # Strip HTML tags from abstract
        if abstract:
            abstract = re.sub(r"<[^>]+>", "", abstract)

        return {
            "title": data.get("title", [""])[0] if data.get("title") else "",
            "authors": authors,
            "abstract": abstract,
            "year": year,
            "doi": doi,
            "journal": data.get("container-title", [""])[0] if data.get("container-title") else "",
            "publisher": data.get("publisher", ""),
            "citation_count": data.get("is-referenced-by-count", 0),
            "reference_count": data.get("references-count", 0),
            "url": data.get("URL", ""),
            "type": data.get("type", ""),
        }
    except Exception as e:
        logger.debug(f"DOI resolution failed for {doi}: {e}")
        return {}


# ============================================================
# Unified Paper Fetcher
# ============================================================

def fetch_paper(url: str, timeout: int = 30, **kwargs) -> dict[str, Any]:
    """Unified academic paper fetcher.

    Routes to the appropriate sub-handler based on URL pattern:
      - arXiv → existing arxiv handler
      - Semantic Scholar → existing S2 handler
      - DOI → Crossref resolution
      - PDF → existing PDF handler
      - Other → generic web fetch with paper metadata hints

    Args:
        url: Paper URL (arXiv, S2, DOI, PDF, or generic).
        timeout: Request timeout in seconds.

    Returns:
        Standard handler result dict with paper-specific metadata.
    """
    url_lower = url.lower()

    # Route to existing handlers
    if "arxiv.org" in url_lower or "ar5iv" in url_lower:
        try:
            from sheaf_ai.collectors.arxiv import fetch_arxiv_paper
            result = fetch_arxiv_paper(url, timeout=timeout)
            if result.get("success"):
                result["meta"] = result.get("meta", {})
                result["meta"]["paper_handler"] = "arxiv"
                result["meta"]["summarize_prompt"] = PAPER_SUMMARIZE_PROMPT
            return result
        except Exception as e:
            logger.warning(f"arXiv handler failed: {e}")

    if "semanticscholar.org" in url_lower:
        try:
            from sheaf_ai.collectors.semantic_scholar import fetch_semantic_scholar
            result = fetch_semantic_scholar(url, timeout=timeout)
            if result.get("success"):
                result["meta"] = result.get("meta", {})
                result["meta"]["paper_handler"] = "semantic_scholar"
                result["meta"]["summarize_prompt"] = PAPER_SUMMARIZE_PROMPT
            return result
        except Exception as e:
            logger.warning(f"Semantic Scholar handler failed: {e}")

    if url_lower.endswith(".pdf") or ".pdf?" in url_lower:
        try:
            from sheaf_ai.collectors.pdf import fetch_pdf
            result = fetch_pdf(url, timeout=timeout)
            if result.get("success"):
                result["meta"] = result.get("meta", {})
                result["meta"]["paper_handler"] = "pdf"
                result["meta"]["summarize_prompt"] = PAPER_SUMMARIZE_PROMPT
            return result
        except Exception as e:
            logger.warning(f"PDF handler failed: {e}")

    # DOI resolution
    if "doi.org" in url_lower:
        return _fetch_doi_paper(url, timeout)

    # Fallback: generic web fetch with paper hints
    return _fetch_generic_paper(url, timeout)


def _fetch_doi_paper(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fetch paper metadata from a DOI URL."""
    # Extract DOI from URL
    doi_match = re.search(r'doi\.org/(10\.\d{4,}/[^\s]+)', url)
    if not doi_match:
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "doi-resolve",
            "error": f"Could not extract DOI from URL: {url}",
        }

    doi = doi_match.group(1).rstrip(".")

    metadata = _resolve_doi(doi, timeout=timeout)
    if not metadata or not metadata.get("title"):
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "doi-resolve",
            "error": f"DOI resolution returned no metadata: {doi}",
        }

    # Build result
    authors_str = ", ".join(metadata.get("authors", []))
    abstract = metadata.get("abstract", "")
    year = metadata.get("year", "")
    journal = metadata.get("journal", "")
    citation_count = metadata.get("citation_count", 0)

    text_parts = []
    if metadata.get("title"):
        text_parts.append(f"# {metadata['title']}")
    if authors_str:
        text_parts.append(f"\nAuthors: {authors_str}")
    if year:
        text_parts.append(f"Year: {year}")
    if journal:
        text_parts.append(f"Journal: {journal}")
    if abstract:
        text_parts.append(f"\n## Abstract\n{abstract}")
    if citation_count:
        text_parts.append(f"\nCitations: {citation_count}")

    return {
        "success": True,
        "title": metadata["title"],
        "text": "\n".join(text_parts),
        "method": "doi-crossref",
        "error": None,
        "meta": {
            "paper_handler": "doi",
            "doi": doi,
            "authors": metadata.get("authors", []),
            "year": year,
            "journal": journal,
            "citation_count": citation_count,
            "reference_count": metadata.get("reference_count", 0),
            "publisher": metadata.get("publisher", ""),
            "summarize_prompt": PAPER_SUMMARIZE_PROMPT,
        },
    }


def _fetch_generic_paper(url: str, timeout: int = 30) -> dict[str, Any]:
    """Fallback: try generic web fetch for a paper URL.

    Used for OpenReview, PubMed, ACM, IEEE, etc. where we don't
    have dedicated API handlers.
    """
    try:
        from sheaf_ai.fetch_article import fetch_article
        result = fetch_article(url, timeout=timeout)

        if result.get("success"):
            result["meta"] = result.get("meta", {})
            result["meta"]["paper_handler"] = "generic"
            result["meta"]["summarize_prompt"] = PAPER_SUMMARIZE_PROMPT

            # Try to detect paper metadata from the HTML
            text = result.get("text", "")
            title = result.get("title", "")

            # Look for DOI in text
            doi_match = re.search(r'(?:DOI|doi)[:\s]*(10\.\d{4,}/[^\s]+)', text)
            if doi_match:
                result["meta"]["doi"] = doi_match.group(1).rstrip(".")

            # Look for arXiv ID in text
            arxiv_match = re.search(r'arXiv[:\s]*(\d{4}\.\d{4,5})', text)
            if arxiv_match:
                result["meta"]["arxiv_id"] = arxiv_match.group(1)

        return result
    except Exception as e:
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "paper-generic",
            "error": str(e),
        }


# ============================================================
# Paper Metadata Enrichment
# ============================================================

def enrich_with_citations(result: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    """Enrich a paper result with citation counts from Semantic Scholar.

    Best-effort: adds citation_count if available, doesn't modify on failure.
    """
    meta = result.get("meta", {})

    # Try to get citations via arXiv ID
    arxiv_id = meta.get("arxiv_id")
    doi = meta.get("doi")
    title = result.get("title", "")

    if not arxiv_id and not doi and not title:
        return result

    try:
        import requests

        # Build S2 API URL
        if arxiv_id:
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}?fields=citationCount,referenceCount,year,tldr"
        elif doi:
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=citationCount,referenceCount,year,tldr"
        elif title:
            import urllib.parse
            encoded = urllib.parse.quote(title)
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={encoded}&limit=1&fields=citationCount,referenceCount,year,tldr"
        else:
            return result

        resp = requests.get(s2_url, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if "data" in data:
                data = data["data"][0] if data["data"] else {}
            meta["citation_count"] = data.get("citationCount", 0)
            meta["reference_count"] = data.get("referenceCount", 0)
            if data.get("year"):
                meta["year"] = data["year"]
            if data.get("tldr"):
                meta["tldr"] = data["tldr"].get("text", "")
            result["meta"] = meta

    except Exception as e:
        logger.debug(f"Citation enrichment failed: {e}")

    return result
