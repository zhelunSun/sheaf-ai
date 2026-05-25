"""
Sheaf HTTP API — FastAPI-based local server for Chrome Extension + Agent access.

This is the HTTP interface layer that wraps Sheaf's core functionality,
enabling browser extensions and remote agents to interact with the knowledge base.

Includes MCP Streamable HTTP transport endpoint (/mcp) for agent integration.

Usage:
    sheaf serve                    # Start server on http://localhost:8321
    sheaf serve --port 9000        # Custom port
    sheaf serve --host 0.0.0.0     # Allow external access
"""
from __future__ import annotations

import json
import secrets
import sys
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sheaf_ai.config import VERSION, DATA_DIR, ENTRIES_DIR, fix_windows_encoding
from sheaf_ai.config import INDEX_FILE as _INDEX_FILE
from sheaf_ai.search import search_fulltext, search_quick
from sheaf_ai.pipeline import process_url
from sheaf_ai.feedback import submit_feedback
from sheaf_ai.crystallize import (
    crystallize_and_save,
    list_crystallized,
    get_card,
    delete_card,
    semantic_search,
)

# Ensure Windows UTF-8 output
fix_windows_encoding()

# ============================================================
# Pydantic Models (Request/Response schemas)
# ============================================================

class CollectRequest(BaseModel):
    """Request body for collecting a URL."""
    url: str = Field(..., description="URL to collect")
    force: bool = Field(False, description="Skip dedup check")
    manual_text: Optional[str] = Field(None, description="Override fetch with manual text")


class CrystallizeRequest(BaseModel):
    """Request body for crystallizing a topic."""
    topic: str = Field(..., description="Topic to crystallize")


class FeedbackRequest(BaseModel):
    """Request body for submitting feedback."""
    entry_id: str = Field(..., description="Entry ID")
    feedback_type: str = Field(..., description="Type: correction | rating")
    content: str = Field(..., description="Feedback content")


class SearchResponse(BaseModel):
    """Response model for search results."""
    query: str
    total: int
    results: list[dict]


class CollectResponse(BaseModel):
    """Response model for collect results."""
    success: bool
    entry_id: Optional[str] = None
    url: Optional[str] = None
    topics: Optional[list[str]] = None
    one_liner: Optional[str] = None
    error: Optional[str] = None


class CardResponse(BaseModel):
    """Response model for knowledge cards."""
    title: str
    confidence: float
    evidence_count: int
    card_id: Optional[str] = None


class StatsResponse(BaseModel):
    """Response model for collection statistics."""
    total_entries: int
    total_cards: int
    topics: dict[str, int]
    version: str


class HealthResponse(BaseModel):
    """Response model for health check."""
    status: str
    version: str
    uptime: Optional[str] = None


# ============================================================
# FastAPI App
# ============================================================

_START_TIME: Optional[datetime] = None


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    global _START_TIME
    _START_TIME = datetime.now()

    app = FastAPI(
        title="Sheaf API",
        description="Agent-native personal knowledge layer — HTTP interface",
        version=VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow browser extensions and local tools
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Local server, all origins OK
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ============================================================
    # Routes
    # ============================================================

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    async def health_check():
        """Health check endpoint."""
        uptime = None
        if _START_TIME:
            delta = datetime.now() - _START_TIME
            uptime = f"{delta.total_seconds():.0f}s"
        return HealthResponse(status="ok", version=VERSION, uptime=uptime)

    @app.get("/stats", response_model=StatsResponse, tags=["collection"])
    async def get_stats():
        """Get collection statistics."""
        from sheaf_ai.config import INDEX_FILE as idx
        # Count entries from index
        total_entries = 0
        topic_counts: dict[str, int] = {}
        if idx.exists():
            with open(idx, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                        total_entries += 1
                        for t in entry.get("topics", []):
                            name = t if isinstance(t, str) else t.get("name", "")
                            if name:
                                topic_counts[name] = topic_counts.get(name, 0) + 1
                    except json.JSONDecodeError:
                        continue

        # Count cards
        total_cards = len(list_crystallized())

        return StatsResponse(
            total_entries=total_entries,
            total_cards=total_cards,
            topics=dict(sorted(topic_counts.items(), key=lambda x: -x[1])[:20]),
            version=VERSION,
        )

    @app.post("/collect", response_model=CollectResponse, tags=["collection"])
    async def collect_url(req: CollectRequest):
        """Collect a URL — fetch, classify, summarize, store."""
        try:
            result = process_url(
                url=req.url,
                manual_text=req.manual_text,
                force=req.force,
            )
            if result.get("success"):
                return CollectResponse(
                    success=True,
                    entry_id=result.get("entry_id"),
                    url=result.get("url"),
                    topics=result.get("topics", []),
                    one_liner=result.get("one_liner", ""),
                )
            else:
                return CollectResponse(
                    success=False,
                    error=result.get("error", "Unknown error"),
                )
        except Exception as e:
            return CollectResponse(success=False, error=str(e))

    @app.get("/search", response_model=SearchResponse, tags=["search"])
    async def search(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, ge=1, le=100, description="Max results"),
    ):
        """Full-text search across collection."""
        results = search_fulltext(q)
        # Trim to limit and serialize
        trimmed = results[:limit]
        return SearchResponse(query=q, total=len(results), results=trimmed)

    @app.get("/entries", tags=["collection"])
    async def list_entries(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        """List collected entries (paginated)."""
        from sheaf_ai.config import INDEX_FILE as idx
        entries = []
        if idx.exists():
            with open(idx, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        # Reverse to show newest first
        entries = list(reversed(entries))
        page = entries[offset : offset + limit]
        return {"total": len(entries), "offset": offset, "limit": limit, "entries": page}

    @app.get("/entries/{entry_id}", tags=["collection"])
    async def get_entry(entry_id: str):
        """Get a specific entry by ID."""
        date_prefix = entry_id[:7]
        entry_path = ENTRIES_DIR / date_prefix / f"{entry_id}.json"
        if not entry_path.exists():
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
        data = json.loads(entry_path.read_text(encoding="utf-8"))
        return data

    @app.post("/crystallize", tags=["knowledge"])
    async def crystallize(req: CrystallizeRequest):
        """Crystallize knowledge cards from a topic."""
        try:
            result = crystallize_and_save(req.topic)
            return {"success": True, "topic": req.topic, "result": str(result)}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/cards", tags=["knowledge"])
    async def list_cards():
        """List all crystallized knowledge cards."""
        cards = list_crystallized()
        return {
            "total": len(cards),
            "cards": [
                {
                    "card_id": c.card_id if hasattr(c, "card_id") else None,
                    "title": c.title,
                    "confidence": c.confidence,
                    "evidence_count": len(c.evidence) if hasattr(c, "evidence") else 0,
                }
                for c in cards
            ],
        }

    @app.get("/cards/{card_id}", tags=["knowledge"])
    async def get_card_detail(card_id: str):
        """Get a specific knowledge card."""
        card = get_card(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
        return {
            "card_id": card.card_id if hasattr(card, "card_id") else card_id,
            "title": card.title,
            "confidence": card.confidence,
            "evidence": [
                {"entry_id": e.entry_id if hasattr(e, "entry_id") else str(e),
                 "relevance": e.relevance if hasattr(e, "relevance") else None}
                for e in (card.evidence if hasattr(card, "evidence") else [])
            ],
        }

    @app.delete("/cards/{card_id}", tags=["knowledge"])
    async def remove_card(card_id: str):
        """Delete a knowledge card."""
        try:
            delete_card(card_id)
            return {"success": True, "deleted": card_id}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/cards/search/semantic", tags=["search"])
    async def semantic_search_cards(
        q: str = Query(..., description="Semantic search query"),
        limit: int = Query(5, ge=1, le=20),
    ):
        """Semantic vector search across knowledge cards."""
        try:
            results = semantic_search(q)
            return {"query": q, "total": len(results), "results": results[:limit]}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/feedback", tags=["feedback"])
    async def submit_feedback_api(req: FeedbackRequest):
        """Submit feedback on an entry."""
        try:
            submit_feedback(req.entry_id, req.feedback_type, req.content)
            return {"success": True}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # ============================================================
    # MCP Streamable HTTP Transport (EXT-04)
    # ============================================================

    _sessions: dict[str, datetime] = {}

    def _make_sse_event(data: dict, event_id: str | None = None) -> str:
        """Format a dict as an SSE event string."""
        parts = []
        if event_id:
            parts.append(f"id: {event_id}")
        payload = json.dumps(data, ensure_ascii=False)
        for line in payload.split("\n"):
            parts.append(f"data: {line}")
        parts.append("")
        parts.append("")
        return "\n".join(parts)

    @app.post("/mcp", tags=["mcp"])
    async def mcp_post(request: Request):
        """MCP Streamable HTTP transport — POST endpoint.

        Handles JSON-RPC requests from MCP clients. Supports both
        single JSON response and SSE streaming response modes.
        """
        # Validate Origin for security (DNS rebinding prevention)
        origin = request.headers.get("origin", "")
        if origin and not _is_safe_origin(origin):
            return Response(status_code=403, content="Forbidden origin")

        session_id = request.headers.get("mcp-session-id")
        if session_id and session_id not in _sessions:
            return Response(status_code=404, content="Session not found")

        try:
            body = await request.json()
        except Exception:
            return Response(status_code=400, content="Invalid JSON")

        # Delegate to existing MCP handler
        from sheaf_ai.mcp_server import handle_request
        response_str = handle_request(body)

        # No response for notifications
        if response_str is None:
            return Response(status_code=202)

        try:
            response_data = json.loads(response_str)
        except Exception:
            return Response(status_code=500, content="Internal MCP error")

        # Check if this is an initialize request → create session
        method = body.get("method", "")
        if method == "initialize":
            new_session = secrets.token_hex(16)
            _sessions[new_session] = datetime.now()

            resp = Response(
                content=response_str,
                media_type="application/json",
                headers={
                    "mcp-session-id": new_session,
                    "mcp-protocol-version": "2025-06-18",
                },
            )
            return resp

        # For regular requests, return JSON response
        # (SSE streaming mode can be added later for tool calls that need it)
        accept = request.headers.get("accept", "")
        if "text/event-stream" in accept and "result" in response_data:
            # Stream the response via SSE
            event_id = secrets.token_hex(8)
            async def _stream():
                yield _make_sse_event(response_data, event_id)
            return StreamingResponse(
                _stream(),
                media_type="text/event-stream",
                headers={
                    "mcp-session-id": session_id or "",
                    "mcp-protocol-version": "2025-06-18",
                },
            )

        return Response(
            content=response_str,
            media_type="application/json",
            headers={"mcp-protocol-version": "2025-06-18"},
        )

    @app.get("/mcp", tags=["mcp"])
    async def mcp_get(request: Request):
        """MCP Streamable HTTP transport — GET endpoint for server-initiated messages.

        Opens an SSE stream for server-to-client communication.
        """
        session_id = request.headers.get("mcp-session-id")
        if not session_id or session_id not in _sessions:
            return Response(status_code=400, content="Session required")

        async def _heartbeat():
            """Keep-alive SSE stream. Server notifications can be pushed here."""
            yield _make_sse_event({"jsonrpc": "2.0", "method": "ping"})

        return StreamingResponse(
            _heartbeat(),
            media_type="text/event-stream",
        )

    @app.delete("/mcp", tags=["mcp"])
    async def mcp_delete(request: Request):
        """MCP Streamable HTTP transport — DELETE endpoint to terminate session."""
        session_id = request.headers.get("mcp-session-id")
        if session_id and session_id in _sessions:
            del _sessions[session_id]
        return Response(status_code=204)

    return app


def _is_safe_origin(origin: str) -> bool:
    """Check if origin is safe (localhost or same-host)."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ""
        return host in ("localhost", "127.0.0.1", "::1") or host.endswith(".localhost")
    except Exception:
        return False


# Module-level app instance (for uvicorn import)
app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 8321):
    """Run the HTTP API server."""
    import uvicorn

    print(f"🚀 Sheaf API v{VERSION}")
    print(f"   http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    print(f"   Data: {DATA_DIR}")
    print()

    uvicorn.run(
        "sheaf_ai.api:app",
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    run_server()
