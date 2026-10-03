"""Additive collection diagnostics shared by public adapters.

Legacy records have unknown processing status. A saved source is distinct from
successful model enrichment; neither heuristic quality nor source scores are proof.
"""
from __future__ import annotations

QUALITY_FIELDS = {
    "decision", "reason", "text_length", "image_count", "score", "quality_tier",
    "is_image_heavy", "alt_text_available", "hint",
}
SOURCE_FIELDS = {
    "score", "tier", "domain", "domain_tier", "is_primary", "is_primary_claim",
    "rule_score", "llm_score", "user_override", "freshness", "prestige_override",
    "academic_bonus",
}


def _scalars(value: object, fields: set[str]) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        key: item[:1000] if isinstance(item, str) else item
        for key, item in value.items()
        if key in fields and (item is None or isinstance(item, (str, bool, int, float)))
    }


def collection_diagnostics(result: dict, *, persisted: bool = False) -> dict:
    """Project known fields, never invent successful processing for old entries."""
    meta = result.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    saved = meta.get("collection")
    saved = saved if isinstance(saved, dict) else {}
    data = saved if persisted else result
    status = data.get("status", "unknown")
    if not isinstance(status, str) or status not in {"success", "partial", "error", "unknown"}:
        status = "unknown"
    stages = data.get("processing")
    stages = stages if isinstance(stages, dict) else {}
    processing = {}
    for name in ("classify", "summarize"):
        stage = stages.get(name)
        stage = stage if isinstance(stage, dict) else {}
        stage_status = stage.get("status", "unknown")
        method = stage.get("method", "none")
        processing[name] = {
            "status": stage_status if isinstance(stage_status, str) and stage_status in {
                "success", "fallback", "error", "not_run", "unknown",
            } else "unknown",
            "method": method if isinstance(method, str) and method in {"llm", "rules", "none"} else "none",
        }
        if processing[name]["status"] == "success" and processing[name]["method"] == "none":
            processing[name]["status"] = "unknown"
    if status == "success":
        stage_states = {stage["status"] for stage in processing.values()}
        if stage_states & {"fallback", "error", "not_run"}:
            status = "partial"
        elif "unknown" in stage_states:
            status = "unknown"
    warnings = data.get("warnings", [])
    warnings = [w[:1000] for w in warnings[:10] if isinstance(w, str)] if isinstance(warnings, list) else []
    stored = True if persisted else result.get("stored", bool(result.get("success")))
    if stored is not None and not isinstance(stored, bool):
        stored = None
    quality = data.get("quality", meta.get("quality", {}))
    source = data.get("source", result.get("source", result.get("source_info", {})))
    return {
        "status": status, "stored": stored, "processing": processing,
        "warnings": warnings, "quality": _scalars(quality, QUALITY_FIELDS),
        "source": _scalars(source, SOURCE_FIELDS),
    }


def unexpected_collection_error() -> dict:
    """Persistence may have completed before an unexpected adapter exception."""
    return {
        "success": False, "status": "error", "stored": None,
        "stage": "unknown", "error": "Collection interrupted; check existing entries before retrying.",
        "warnings": [],
    }
