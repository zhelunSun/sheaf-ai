"""MCP card and evidence-governed memory tools."""
from __future__ import annotations

import copy
import json

from sheaf_ai import card_service
from sheaf_ai.evidence_memory import EvidenceMemoryError, TransitionValidationError
from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error


# ── Tool definitions ─────────────────────────────────────────

TOOLS = [
    {
        "name": "sheaf_crystallize",
        "description": (
            "Crystallize knowledge cards from collected entries about a topic.\n"
            "\n"
            "Analyzes 3+ related entries and synthesizes them into structured "
            "knowledge cards — each with a falsifiable claim, evidence citing "
            "specific sources, confidence score, and tags.\n"
            "\n"
            "This is the core value of Sheaf: turning scattered bookmarks into "
            "Agent-consumable knowledge assets with full provenance tracing.\n"
            "\n"
            "Requires at least 3 entries on the topic to generate cards.\n"
            "\n"
            "Examples:\n"
            "  sheaf_crystallize(topic='AI Agent')     — crystallize AI Agent knowledge\n"
            "  sheaf_crystallize(topic='遥感')          — crystallize remote sensing knowledge\n"
            "  sheaf_crystallize(topic='open source')"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Topic to crystallize (e.g. 'AI Agent', '遥感', 'open source'). Must have 3+ collected entries on this topic."},
            },
            "required": ["topic"],
        },
    },
    {
        "name": "sheaf_list_cards",
        "description": (
            "List crystallized knowledge cards. Optionally filter by topic.\n"
            "\n"
            "Each card includes: title, claim, evidence, tags, confidence, "
            "source entry IDs, and related card associations.\n"
            "\n"
            "Examples:\n"
            "  sheaf_list_cards()                 — all cards\n"
            "  sheaf_list_cards(topic='AI Agent')  — cards about AI Agent"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Filter by topic (optional)"},
            },
        },
    },
    {
        "name": "sheaf_get_card",
        "description": (
            "Get full details of a specific knowledge card by ID.\n"
            "\n"
            "Returns the card with its complete claim, evidence, source references, "
            "confidence score, tags, and links to related cards.\n"
            "\n"
            "Use this to deep-dive into a card found via sheaf_list_cards."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "card_id": {"type": "string", "description": "Card ID (format: card_xxxxxxxxxxxx)"},
            },
            "required": ["card_id"],
        },
    },
    {
        "name": "sheaf_memory_apply",
        "description": (
            "Apply one explicit evidence-governed memory transition. "
            "Source IDs are resolved only from stored Sheaf Entries; the request "
            "is executed by the governed transition engine, not by an LLM."
        ),
        "inputSchema": copy.deepcopy(card_service.MEMORY_TRANSITION_REQUEST_SCHEMA),
    },
    {
        "name": "sheaf_memory_snapshot",
        "description": (
            "Read the latest public KnowledgeCard projections grouped as active, "
            "contested, retired, or superseded."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "topic": {"type": "string", "description": "Exact topic filter"},
            },
        },
    },
    {
        "name": "sheaf_memory_history",
        "description": (
            "Read transition history and the replayable audit graph, including "
            "conflict proposals and explicit resolution basis."
        ),
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "topic": {"type": "string", "description": "Exact topic filter"},
                "card_id": {"type": "string", "description": "Card ID filter"},
            },
        },
    },
]


# ── Handlers ─────────────────────────────────────────────────

def _handle_crystallize(req_id: int | str, arguments: dict) -> str:
    topic = arguments.get("topic", "")
    if not topic:
        return jsonrpc_error(req_id, -32602, "Missing required parameter: topic")
    try:
        cards = card_service.crystallize_cards(topic)
        card_data = [card_service.card_to_public_dict(c) for c in cards]
        return jsonrpc_response(req_id, {
            "content": [{"type": "text", "text": json.dumps({
                "topic": topic,
                "cards_generated": len(cards),
                "cards": card_data,
            }, ensure_ascii=False, indent=2)}]
        })
    except Exception as e:
        return jsonrpc_error(req_id, -32603, f"Crystallization failed: {e}")


def _handle_list_cards(req_id: int | str, arguments: dict) -> str:
    topic = arguments.get("topic")
    cards = card_service.list_cards(topic=topic)
    card_data = [card_service.card_to_public_dict(c) for c in cards]
    return jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps({
            "total": len(card_data),
            "cards": card_data,
        }, ensure_ascii=False, indent=2)}]
    })


def _handle_get_card(req_id: int | str, arguments: dict) -> str:
    card_id = arguments.get("card_id", "")
    card = card_service.get_card_detail(card_id)
    if not card:
        return jsonrpc_error(req_id, -32602, f"Card not found: {card_id}")
    return jsonrpc_response(req_id, {
        "content": [{
            "type": "text",
            "text": json.dumps(
                card_service.card_to_public_dict(card),
                ensure_ascii=False,
                indent=2,
            ),
        }]
    })


def _memory_response(req_id: int | str, payload: dict) -> str:
    return jsonrpc_response(req_id, {
        "content": [{
            "type": "text",
            "text": json.dumps(payload, ensure_ascii=False, indent=2),
        }]
    })


def _handle_memory_apply(req_id: int | str, arguments: dict) -> str:
    try:
        return _memory_response(req_id, card_service.apply_evidence_transition(arguments))
    except (ValueError, TransitionValidationError) as exc:
        return jsonrpc_error(req_id, -32602, str(exc))
    except EvidenceMemoryError as exc:
        return jsonrpc_error(req_id, -32603, f"Evidence memory failed: {exc}")


def _handle_memory_snapshot(req_id: int | str, arguments: dict) -> str:
    try:
        return _memory_response(
            req_id,
            card_service.get_memory_snapshot(topic=arguments.get("topic", "")),
        )
    except ValueError as exc:
        return jsonrpc_error(req_id, -32602, str(exc))
    except EvidenceMemoryError as exc:
        return jsonrpc_error(req_id, -32603, f"Evidence memory failed: {exc}")


def _handle_memory_history(req_id: int | str, arguments: dict) -> str:
    try:
        return _memory_response(
            req_id,
            card_service.get_memory_history(
                topic=arguments.get("topic", ""),
                card_id=arguments.get("card_id", ""),
            ),
        )
    except ValueError as exc:
        return jsonrpc_error(req_id, -32602, str(exc))
    except EvidenceMemoryError as exc:
        return jsonrpc_error(req_id, -32603, f"Evidence memory failed: {exc}")


HANDLERS = {
    "sheaf_crystallize": _handle_crystallize,
    "sheaf_list_cards": _handle_list_cards,
    "sheaf_get_card": _handle_get_card,
    "sheaf_memory_apply": _handle_memory_apply,
    "sheaf_memory_snapshot": _handle_memory_snapshot,
    "sheaf_memory_history": _handle_memory_history,
}
