"""
Sheaf HTTP API — FastAPI-based local server for Chrome Extension + Agent access.

This is the HTTP interface layer that wraps Sheaf's core functionality,
enabling browser extensions and remote agents to interact with the knowledge base.

Includes MCP Streamable HTTP transport endpoint (/mcp) for agent integration.

Usage:
    sheaf serve                    # Start server on http://localhost:8321
    sheaf serve --port 9000        # Custom port
    SHEAF_API_TOKEN=<token> sheaf serve --host 0.0.0.0  # Authenticated external access
"""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime
from ipaddress import ip_address
from typing import Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from sheaf_ai.config import VERSION, DATA_DIR, ENTRIES_DIR, fix_windows_encoding
from sheaf_ai.entry_paths import InvalidEntryId, resolve_entry_json_path, validate_entry_id
from sheaf_ai.search import search_hybrid
from sheaf_ai.pipeline import process_url
from sheaf_ai.feedback import submit_feedback
from sheaf_ai.mcp_server import MCP_PROTOCOL_VERSION
from sheaf_ai import card_service

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
    corrections: Optional[dict] = Field(None, description="Fields to correct")
    user_note: str = Field("", description="Optional note explaining the correction")
    feedback_type: Optional[str] = Field(None, description="Legacy field name")
    content: Optional[str] = Field(None, description="Legacy field value")


class SearchResponse(BaseModel):
    """Response model for search results."""
    query: str
    total: int
    results: list[dict]
    semantic_backend: str = "unknown"
    degraded: bool = False
    reason: str = ""


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


def create_app(api_token: str | None = None) -> FastAPI:
    """Create and configure the FastAPI application.

    Without a token the app is intentionally localhost-only at the HTTP
    boundary.  Supplying a token enables remote hosts and requires a Bearer
    token on every request.  The default local CLI and extension workflow stays
    unauthenticated.
    """
    global _START_TIME
    _START_TIME = datetime.now()

    app = FastAPI(
        title="Sheaf API",
        description="Agent-native personal knowledge layer — HTTP interface",
        version=VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # CORS — allow local tools and unpacked browser extensions by default.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[],
        allow_origin_regex=(
            r"^(https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?"
            r"|chrome-extension://[a-z]{32})$"
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def enforce_http_boundary(request: Request, call_next):
        """Block DNS-rebinding origins/hosts locally or require remote auth."""
        if api_token:
            provided = request.headers.get("authorization", "")
            expected = f"Bearer {api_token}"
            if not secrets.compare_digest(
                provided.encode("utf-8", errors="surrogatepass"),
                expected.encode("utf-8", errors="surrogatepass"),
            ):
                return Response(
                    status_code=401,
                    content="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
        else:
            client_host = request.client.host if request.client else ""
            if client_host != "testclient" and not _is_loopback_host(client_host):
                return Response(status_code=403, content="Loopback client required")
            if not _is_safe_host_header(request.headers.get("host", "")):
                return Response(status_code=403, content="Forbidden host")
            origin = request.headers.get("origin", "")
            if origin and not _is_safe_origin(origin):
                return Response(status_code=403, content="Forbidden origin")
        return await call_next(request)

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
    def get_stats():
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
        total_cards = card_service.count_cards()

        return StatsResponse(
            total_entries=total_entries,
            total_cards=total_cards,
            topics=dict(sorted(topic_counts.items(), key=lambda x: -x[1])[:20]),
            version=VERSION,
        )

    @app.post("/collect", response_model=CollectResponse, tags=["collection"])
    def collect_url(req: CollectRequest):
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
    def search(
        q: str = Query(..., description="Search query"),
        limit: int = Query(10, ge=1, le=100, description="Max results"),
        min_evidence_score: float = Query(
            0.0,
            ge=0.0,
            le=1.0,
            description=(
                "Optional experimental relevance gate; zero disables abstention. "
                "Thresholds are backend/version specific."
            ),
        ),
    ):
        """Hybrid keyword + semantic search across the Entry collection."""
        raw_diagnostics: dict[str, object] = {}
        results = search_hybrid(
            q,
            limit=limit,
            include_raw=True,
            diagnostics=raw_diagnostics,
            min_evidence_score=min_evidence_score,
        )
        if raw_diagnostics:
            diagnostics = {
                "semantic_backend": str(
                    raw_diagnostics.get(
                        "semantic_backend",
                        raw_diagnostics.get("backend", "unknown"),
                    )
                ),
                "degraded": bool(raw_diagnostics.get("degraded", False)),
                "reason": str(raw_diagnostics.get("reason", "")),
            }
        elif results:
            first = results[0]
            diagnostics = {
                "semantic_backend": str(first.get("semantic_backend", "unknown")),
                "degraded": bool(first.get("semantic_degraded", False)),
                "reason": str(first.get("semantic_reason", "")),
            }
        else:
            diagnostics = {
                "semantic_backend": "unknown",
                "degraded": True,
                "reason": "No result-level semantic diagnostics are available",
            }
        return SearchResponse(
            query=q,
            total=len(results),
            results=results,
            **diagnostics,
        )

    @app.get("/entries", tags=["collection"])
    def list_entries(
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
    def get_entry(entry_id: str):
        """Get a specific entry by ID."""
        try:
            entry_path = resolve_entry_json_path(ENTRIES_DIR, entry_id)
        except InvalidEntryId:
            raise HTTPException(status_code=400, detail="Invalid entry ID")
        if not entry_path.exists():
            raise HTTPException(status_code=404, detail=f"Entry {entry_id} not found")
        data = json.loads(entry_path.read_text(encoding="utf-8"))
        return data

    @app.post("/crystallize", tags=["knowledge"])
    def crystallize(req: CrystallizeRequest):
        """Crystallize knowledge cards from a topic."""
        try:
            cards = card_service.crystallize_cards(req.topic)
            card_data = [card_service.card_to_public_dict(c) for c in cards]
            return {
                "success": True,
                "topic": req.topic,
                "count": len(card_data),
                "cards": card_data,
                "result": str(cards),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/cards", tags=["knowledge"])
    def list_cards(
        limit: int = Query(20, ge=1, le=100),
        offset: int = Query(0, ge=0),
    ):
        """List crystallized knowledge cards with explicit pagination."""
        cards = card_service.list_cards(limit=offset + limit)
        page = cards[offset : offset + limit]
        return {
            "total": card_service.count_cards(),
            "offset": offset,
            "limit": limit,
            "cards": [card_service.card_to_public_dict(c) for c in page],
        }

    @app.get("/cards/search/semantic", tags=["search"])
    def semantic_search_cards(
        q: str = Query(..., description="Semantic search query"),
        limit: int = Query(5, ge=1, le=20),
    ):
        """Semantic vector search across knowledge cards."""
        try:
            results = card_service.search_cards_semantic(q, top_k=limit)
            return {"query": q, "total": len(results), "results": results}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/cards/{card_id}", tags=["knowledge"])
    def get_card_detail(card_id: str):
        """Get a specific knowledge card."""
        card = card_service.get_card_detail(card_id)
        if card is None:
            raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
        return card_service.card_to_public_dict(card)

    @app.delete("/cards/{card_id}", tags=["knowledge"])
    def remove_card(card_id: str):
        """Delete a knowledge card."""
        try:
            deleted = card_service.delete_card_by_id(card_id)
            if not deleted:
                raise HTTPException(status_code=404, detail=f"Card {card_id} not found")
            return {"success": True, "deleted": card_id}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.post("/feedback", tags=["feedback"])
    def submit_feedback_api(req: FeedbackRequest):
        """Submit feedback on an entry."""
        try:
            corrections = req.corrections or {}
            if not corrections and req.feedback_type and req.content is not None:
                corrections = {req.feedback_type: req.content}
            if not corrections:
                raise HTTPException(status_code=422, detail="corrections is required")
            try:
                validate_entry_id(req.entry_id)
            except InvalidEntryId:
                raise HTTPException(status_code=400, detail="Invalid entry ID")
            result = submit_feedback(req.entry_id, corrections, req.user_note)
            if not result.get("success"):
                raise HTTPException(status_code=404, detail="Entry not found")
            return {"success": True}
        except HTTPException:
            raise
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
        if not api_token and origin and not _is_safe_origin(origin):
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
                    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
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
                    "mcp-protocol-version": MCP_PROTOCOL_VERSION,
                },
            )

        return Response(
            content=response_str,
            media_type="application/json",
            headers={"mcp-protocol-version": MCP_PROTOCOL_VERSION},
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
    """Check if an Origin is a loopback web app or Chrome extension."""
    from urllib.parse import urlparse
    try:
        parsed = urlparse(origin)
        host = parsed.hostname or ""
        if parsed.scheme in ("http", "https"):
            return _is_loopback_host(host)
        return (
            parsed.scheme == "chrome-extension"
            and re.fullmatch(r"[a-z]{32}", host) is not None
        )
    except (TypeError, ValueError):
        return False


def _is_loopback_host(host: str) -> bool:
    """Return whether a bind/origin host is unambiguously loopback."""
    normalized = host.strip().lower().rstrip(".").strip("[]")
    if normalized == "localhost" or normalized.endswith(".localhost"):
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _is_safe_host_header(host_header: str) -> bool:
    """Validate a Host header without trusting DNS resolution."""
    from urllib.parse import urlsplit
    try:
        host = urlsplit(f"//{host_header}").hostname or ""
    except ValueError:
        return False
    return _is_loopback_host(host)


# Module-level app instance (for ASGI imports).  Explicit environment opt-in is
# required to expose an authenticated API through a separate ASGI runner.
app = create_app(api_token=os.environ.get("SHEAF_API_TOKEN") or None)


def run_server(host: str = "127.0.0.1", port: int = 8321, api_token: str | None = None):
    """Run the HTTP API server."""
    import uvicorn

    resolved_token = api_token if api_token is not None else os.environ.get("SHEAF_API_TOKEN")
    resolved_token = resolved_token or None
    if not _is_loopback_host(host) and not resolved_token:
        raise RuntimeError(
            "Refusing non-loopback bind without SHEAF_API_TOKEN or an explicit api_token"
        )

    print(f"🚀 Sheaf API v{VERSION}")
    print(f"   http://{host}:{port}")
    print(f"   Docs: http://{host}:{port}/docs")
    print(f"   Data: {DATA_DIR}")
    if resolved_token:
        print("   Authentication: Bearer token required")
    print()

    uvicorn.run(
        create_app(api_token=resolved_token),
        host=host,
        port=port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    run_server()
