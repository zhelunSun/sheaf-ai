"""
Sheaf PDF Collector — extract text content from PDF files/URLs.

Supports two input modes:
  1. URL pointing to a PDF file (detected by ContentType.PDF_FILE)
  2. Local file path (for Extension file upload pipeline, Issue #51)

Uses PyPDF2 (pure Python, no system deps) with optional pdfminer fallback.
If neither is available, falls back to basic text extraction.

Design:
  - Zero external dependencies beyond what's already installed
  - Graceful degradation: partial text extraction is better than failure
  - Metadata extraction: page count, file size, PDF title/author
  - Text truncation at configurable max_chars

Usage:
    from sheaf_ai.collectors.pdf import fetch_pdf
    result = fetch_pdf("https://example.com/paper.pdf")
"""
from __future__ import annotations

import io
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Max chars to extract (PDFs can be very large)
_DEFAULT_MAX_CHARS = 12000
# Max pages to process (avoid memory issues with huge PDFs)
_DEFAULT_MAX_PAGES = 100


def _extract_with_pypdf2(content: bytes, max_pages: int = _DEFAULT_MAX_PAGES) -> tuple[str, dict[str, Any]]:
    """Extract text using PyPDF2 (pure Python).

    Returns (text, metadata_dict).
    """
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        try:
            from pypdf import PdfReader
        except ImportError:
            return "", {"_unsupported": True}

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as e:
        logger.debug(f"PyPDF reader initialization failed: {e}")
        return "", {"_engine": "pypdf2", "page_count": 0, "_invalid": True}

    meta: dict[str, Any] = {
        "page_count": len(reader.pages),
        "_engine": "pypdf2",
    }

    # Extract document-level metadata
    doc_meta = reader.metadata
    if doc_meta:
        meta["pdf_title"] = doc_meta.title or ""
        meta["pdf_author"] = doc_meta.author or ""
        meta["pdf_subject"] = doc_meta.subject or ""
        meta["pdf_creator"] = doc_meta.creator or ""

    # Extract text page by page
    pages_to_read = min(len(reader.pages), max_pages)
    text_parts = []
    for i in range(pages_to_read):
        try:
            page_text = reader.pages[i].extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
        except Exception as e:
            logger.debug(f"Page {i+1} extraction failed: {e}")
            continue

    text = "\n\n".join(text_parts)
    return text, meta


def _extract_with_pdfminer(content: bytes, max_pages: int = _DEFAULT_MAX_PAGES) -> tuple[str, dict[str, Any]]:
    """Extract text using pdfminer (fallback, better for complex layouts).

    Returns (text, metadata_dict).
    """
    try:
        from pdfminer.high_level import extract_text_to_fp
        from pdfminer.pdfparser import PDFParser
        from pdfminer.pdfdocument import PDFDocument
    except ImportError:
        return "", {"_unsupported": True}

    # Extract metadata
    meta: dict[str, Any] = {"_engine": "pdfminer"}
    try:
        parser = PDFParser(io.BytesIO(content))
        doc = PDFDocument(parser)
        if doc.info:
            info = doc.info[0] if isinstance(doc.info, list) else doc.info
            meta["pdf_title"] = info.get("Title", b"").decode("utf-8", errors="replace") if isinstance(info.get("Title"), bytes) else str(info.get("Title", ""))
            meta["pdf_author"] = info.get("Author", b"").decode("utf-8", errors="replace") if isinstance(info.get("Author"), bytes) else str(info.get("Author", ""))
            meta["page_count"] = len(list(doc.get_pages())) if hasattr(doc, "get_pages") else 0
    except Exception as e:
        logger.debug(f"PDF metadata extraction failed: {e}")

    # Extract text
    try:
        output = io.StringIO()
        extract_text_to_fp(io.BytesIO(content), output, maxpages=max_pages)
        text = output.getvalue()
        return text, meta
    except Exception as e:
        logger.debug(f"pdfminer text extraction failed: {e}")
        return "", meta


def _extract_text(content: bytes, max_pages: int = _DEFAULT_MAX_PAGES) -> tuple[str, dict[str, Any]]:
    """Try extraction engines in order: PyPDF2 → pdfminer → empty.

    Returns (text, metadata_dict).
    """
    # Try PyPDF2 first (fastest, pure Python)
    text, meta = _extract_with_pypdf2(content, max_pages=max_pages)
    if not meta.get("_unsupported") and text.strip():
        return text, meta

    # Fall back to pdfminer (slower but more accurate)
    text, meta = _extract_with_pdfminer(content, max_pages=max_pages)
    if not meta.get("_unsupported") and text.strip():
        return text, meta

    # No extraction available
    if meta.get("_unsupported"):
        return "", {"_engine": "none", "page_count": 0, "_reason": "No PDF library installed (pip install PyPDF2 or pdfminer.six)"}

    return text, meta


def _build_pdf_text(text: str, metadata: dict[str, Any], url: str, max_chars: int = _DEFAULT_MAX_CHARS) -> str:
    """Build formatted text output from PDF extraction results.

    Args:
        text: Extracted text content.
        metadata: PDF metadata.
        url: Source URL.
        max_chars: Maximum characters to include.

    Returns:
        Formatted text string.
    """
    parts = []

    # Title
    title = metadata.get("pdf_title") or ""
    if title:
        parts.append(f"# {title}")

    # Meta line
    meta_items = []
    if metadata.get("pdf_author"):
        meta_items.append(f"Author: {metadata['pdf_author']}")
    if metadata.get("page_count"):
        meta_items.append(f"Pages: {metadata['page_count']}")
    if url:
        meta_items.append(f"Source: {url}")
    if meta_items:
        parts.append("\n" + " | ".join(meta_items))

    # Subject
    subject = metadata.get("pdf_subject")
    if subject:
        parts.append(f"\n> {subject}")

    # Content
    if text:
        truncated = text[:max_chars]
        if len(text) > max_chars:
            truncated += f"\n\n... (truncated at {max_chars} chars, total {len(text)} chars)"
        parts.append("\n## Content\n")
        parts.append(truncated)

    return "\n".join(parts)


# ============================================================
# Main entry point
# ============================================================

def fetch_pdf(
    url: str,
    timeout: int = 30,
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_chars: int = _DEFAULT_MAX_CHARS,
    **kwargs,
) -> dict[str, Any]:
    """Fetch and extract text from a PDF file at a URL.

    This is the main entry point for the PDF collector, compatible with
    the UC handler interface: callable(url) -> dict.

    Args:
        url: URL pointing to a PDF file.
        timeout: HTTP request timeout in seconds.
        max_pages: Maximum pages to extract text from.
        max_chars: Maximum characters of text to return.
        **kwargs: Additional arguments (ignored).

    Returns:
        dict with keys:
            success: bool
            title: str
            text: str (extracted text content)
            method: str ("pdf-extract")
            error: str or None
            meta: dict with PDF metadata
    """
    logger.info(f"Fetching PDF: {url}")

    # Download the PDF
    try:
        resp = requests.get(
            url,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        )
        resp.raise_for_status()
        content = resp.content
    except Exception as e:
        logger.error(f"PDF download failed: {e}")
        return {
            "success": False,
            "title": "",
            "text": "",
            "method": "pdf-extract",
            "error": f"Download failed: {e}",
            "meta": {"source": "pdf", "url": url},
        }

    # Check size (warn but don't fail for large files)
    size_mb = len(content) / (1024 * 1024)
    if size_mb > 50:
        logger.warning(f"Large PDF: {size_mb:.1f} MB, extraction may be slow")

    # Extract text
    text, meta = _extract_text(content, max_pages=max_pages)
    meta["source"] = "pdf"
    meta["url"] = url
    meta["size_bytes"] = len(content)
    meta["size_mb"] = round(size_mb, 2)

    # Build output
    title = meta.get("pdf_title") or _title_from_url(url)
    output_text = _build_pdf_text(text, meta, url, max_chars=max_chars)

    has_text = bool(text.strip())
    no_lib = meta.get("_reason")

    return {
        "success": has_text,
        "title": title,
        "text": output_text,
        "method": "pdf-extract",
        "error": no_lib if not has_text else None,
        "meta": meta,
        "quality": {
            "ok": has_text,
            "score": 3 if has_text and meta.get("page_count", 0) > 1 else (1 if has_text else 0),
            "length": len(output_text),
            "reason": "pdf_text" if has_text else ("no_pdf_library" if no_lib else "empty_pdf"),
        },
    }


def fetch_pdf_from_bytes(
    content: bytes,
    filename: str = "",
    max_pages: int = _DEFAULT_MAX_PAGES,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """Extract text from PDF bytes (for Extension file upload pipeline, Issue #51).

    Args:
        content: Raw PDF file bytes.
        filename: Original filename (for metadata).
        max_pages: Maximum pages to extract text from.
        max_chars: Maximum characters of text to return.

    Returns:
        Same dict format as fetch_pdf.
    """
    logger.info(f"Extracting PDF from bytes: {filename or 'unknown'} ({len(content)} bytes)")

    size_mb = len(content) / (1024 * 1024)

    text, meta = _extract_text(content, max_pages=max_pages)
    meta["source"] = "pdf_upload"
    meta["filename"] = filename
    meta["size_bytes"] = len(content)
    meta["size_mb"] = round(size_mb, 2)

    title = meta.get("pdf_title") or filename or "PDF Document"
    output_text = _build_pdf_text(text, meta, url="", max_chars=max_chars)

    has_text = bool(text.strip())
    no_lib = meta.get("_reason")

    return {
        "success": has_text,
        "title": title,
        "text": output_text,
        "method": "pdf-extract",
        "error": no_lib if not has_text else None,
        "meta": meta,
        "quality": {
            "ok": has_text,
            "score": 3 if has_text and meta.get("page_count", 0) > 1 else (1 if has_text else 0),
            "length": len(output_text),
            "reason": "pdf_text" if has_text else ("no_pdf_library" if no_lib else "empty_pdf"),
        },
    }


def _title_from_url(url: str) -> str:
    """Extract a reasonable title from a PDF URL."""
    try:
        from urllib.parse import urlparse, unquote
        path = unquote(urlparse(url).path)
        filename = path.rsplit("/", 1)[-1]
        # Remove .pdf extension
        if filename.lower().endswith(".pdf"):
            filename = filename[:-4]
        # Replace hyphens/underscores with spaces
        title = filename.replace("-", " ").replace("_", " ")
        return title or "PDF Document"
    except Exception:
        return "PDF Document"
