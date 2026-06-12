"""MCP verify tools — sheaf_crosscheck."""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.mcp.data import load_index, load_entry
from sheaf_ai.search import search_fulltext

logger = logging.getLogger(__name__)


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_crosscheck",
        "description": (
            "Cross-verify claims from an entry against other sources in the knowledge base.\n"
            "\n"
            "Given an entry_id, search for related entries and generate a fact comparison "
            "matrix with verification status for each claim.\n"
            "\n"
            "Use when:\n"
            "- User wants to verify a claim: '这个说法有其他来源支持吗？'\n"
            "- User wants to see different perspectives: '其他人怎么看这件事？'\n"
            "- After collecting an article with low source_score (tier C or D)\n"
            "\n"
            "Returns a fact matrix with per-claim status:\n"
            "- ✅ Confirmed: multiple independent sources agree\n"
            "- ⚠️ Divergent: sources describe differently\n"
            "- ❌ Unverified: only appears in the anchor entry\n"
            "- ❓ Not mentioned: related entries don't cover this claim\n"
            "\n"
            "Examples:\n"
            "  sheaf_crosscheck(entry_id='2026-06-11_b7b26bac')\n"
            "  sheaf_crosscheck(entry_id='2026-06-11_b7b26bac', focus='端侧算力')\n"
            "  sheaf_crosscheck(entry_id='2026-06-11_b7b26bac', top_k=10)"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "entry_id": {
                    "type": "string",
                    "description": "Entry ID to cross-check (format: YYYY-MM-DD_xxxxxxxx)",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional specific claim or topic to verify",
                },
                "scope": {
                    "type": "string",
                    "enum": ["internal"],
                    "default": "internal",
                    "description": "Search scope — currently only 'internal' (KB only). External planned for v0.7.0.",
                },
                "top_k": {
                    "type": "integer",
                    "default": 5,
                    "description": "Max related entries to compare (default: 5)",
                },
            },
            "required": ["entry_id"],
        },
    },
]


# ── Helpers ───────────────────────────────────────────────────

def _get_domain(url: str) -> str:
    """Extract domain from a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _extract_claims(entry: dict, focus: str | None = None) -> list[str]:
    """Extract key claims from an entry's summary, tags, and structured data.

    If focus is provided, only returns claims relevant to that focus.
    """
    claims: list[str] = []

    # One-liner summary
    summary = entry.get("summary", "")
    if summary and len(summary) > 10:
        claims.append(summary)

    # Structured summary key points
    structured = entry.get("structured_summary", {})
    for key in ("core_argument", "key_data", "action_items"):
        val = structured.get(key, "")
        if val and isinstance(val, str) and len(val) > 5:
            claims.append(val)
        elif val and isinstance(val, list):
            claims.extend(str(v) for v in val if len(str(v)) > 5)

    # If focus provided, filter claims to those relevant
    if focus and claims:
        focus_lower = focus.lower()
        relevant = [c for c in claims if focus_lower in c.lower()]
        if relevant:
            return relevant
        # If no direct match, keep all claims but prepend focus as a claim
        return [f"[验证焦点] {focus}"] + claims

    return claims[:6]  # Cap at 6 claims for manageable comparison


def _llm_compare_claims(
    anchor: dict,
    related: list[dict],
    claims: list[str],
) -> list[dict]:
    """Use LLM to compare anchor entry claims against related entries.

    Returns a fact_matrix list with per-claim status.
    """
    from sheaf_ai.llm_client import chat

    # Build comparison context
    anchor_title = anchor.get("title", "")
    related_context = []
    for r in related:
        related_context.append({
            "id": r.get("id", ""),
            "title": r.get("title", ""),
            "summary": r.get("summary", ""),
            "source_tier": r.get("source_tier", r.get("source", {}).get("tier", "")),
        })

    prompt = f"""Compare the following claims from an anchor article against related entries.
For each claim, determine:
- Status: "✅" (confirmed by other sources), "⚠️" (divergent descriptions), "❌" (only in anchor), "❓" (not mentioned)
- Which related entries support or conflict with it

Anchor article: {anchor_title}

Claims to verify:
{json.dumps(claims, ensure_ascii=False, indent=2)}

Related entries:
{json.dumps(related_context, ensure_ascii=False, indent=2)}

Respond with ONLY a valid JSON array:
[
  {{
    "claim": "the original claim text",
    "status": "✅|⚠️|❌|❓",
    "supporting": ["entry_id1"],
    "conflicting": ["entry_id2"],
    "note": "brief explanation"
  }}
]"""

    try:
        result = chat(
            prompt=prompt,
            system="You are a precise fact-checker. Output ONLY valid JSON array.",
            temperature=0.2,
            max_tokens=1200,
        )
        # Clean response
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        result = result.strip()

        parsed = json.loads(result)
        if isinstance(parsed, list):
            return parsed
    except Exception as e:
        logger.warning("LLM comparison failed: %s", e)

    # Fallback: mark all claims as ❓
    return [
        {
            "claim": c,
            "status": "❓",
            "supporting": [],
            "conflicting": [],
            "note": "LLM comparison unavailable",
        }
        for c in claims
    ]


def _crosscheck_entry(
    entry_id: str,
    focus: str | None = None,
    scope: str = "internal",
    top_k: int = 5,
) -> dict:
    """Cross-check an entry's claims against other sources in the KB.

    Args:
        entry_id: The entry to cross-check.
        focus: Optional specific claim to verify.
        scope: Search scope (currently only "internal").
        top_k: Max related entries to compare.

    Returns:
        Dict with fact_matrix, overall_confidence, and metadata.
    """
    # Load anchor entry
    anchor = load_entry(entry_id)
    if not anchor:
        return {"error": f"Entry not found: {entry_id}"}

    # Extract key claims
    claims = _extract_claims(anchor, focus)
    if not claims:
        return {
            "anchor_id": entry_id,
            "anchor_title": anchor.get("title", ""),
            "claims_checked": 0,
            "fact_matrix": [],
            "overall_confidence": "unknown",
            "related_count": 0,
            "scope": scope,
            "note": "No claims could be extracted from this entry",
        }

    # Search related entries using tags + summary as query
    tags = anchor.get("tags", [])
    search_query = focus or " ".join(tags[:5])
    if not search_query:
        search_query = anchor.get("summary", "")[:100]

    related_results = search_fulltext(search_query, limit=top_k * 2, include_raw=False)

    # Filter: exclude self and same-domain entries
    anchor_domain = _get_domain(anchor.get("url", ""))
    related = [
        r["entry"] for r in related_results
        if r["entry"].get("id") != entry_id
        and _get_domain(r["entry"].get("url", "")) != anchor_domain
    ][:top_k]

    # LLM compare if related entries found
    if related:
        fact_matrix = _llm_compare_claims(anchor, related, claims)
    else:
        fact_matrix = [
            {
                "claim": c,
                "status": "❓",
                "supporting": [],
                "conflicting": [],
                "note": "No related entries found in knowledge base",
            }
            for c in claims
        ]

    # Determine overall confidence
    confirmed = sum(1 for f in fact_matrix if f.get("status") == "✅")
    total = len(fact_matrix)
    if total == 0:
        confidence = "unknown"
    elif confirmed / total >= 0.7:
        confidence = "high"
    elif confirmed / total >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "anchor_id": entry_id,
        "anchor_title": anchor.get("title", ""),
        "anchor_source": anchor.get("source", {}),
        "focus": focus,
        "claims_checked": total,
        "fact_matrix": fact_matrix,
        "overall_confidence": confidence,
        "related_count": len(related),
        "scope": scope,
    }


# ── Handlers ─────────────────────────────────────────────────

def _handle_crosscheck(req_id: int | str, arguments: dict) -> str:
    entry_id = arguments.get("entry_id", "")
    if not entry_id:
        return jsonrpc_error(req_id, -32602, "Missing required parameter: entry_id")

    result = _crosscheck_entry(
        entry_id=entry_id,
        focus=arguments.get("focus"),
        scope=arguments.get("scope", "internal"),
        top_k=arguments.get("top_k", 5),
    )

    if "error" in result:
        return jsonrpc_error(req_id, -32602, result["error"])

    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
    })


HANDLERS = {
    "sheaf_crosscheck": _handle_crosscheck,
}
