"""Bounded, append-only v3 transport; no credential discovery or gold access.

The caller owns source/protocol freezes and must reuse the same complete campaign
evidence across revisions. Its frozen identity and relative run paths permit
relocation; independently active copies do not share a filesystem lock. This
module checks manifest integrity, exact request bodies, receipts, and the campaign
ceiling. Hashes detect corruption, not a writer who can replace all evidence.
A missing receipt is never automatically retried.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import time
import uuid

import httpx

from sheaf_ai.provenance_registry import provenance_registry_lock

ENDPOINT = "https://llmapi.paratera.com/v1/chat/completions"
MAX_REQUESTS = 170
MAX_TOKENS = 600_000
MAX_OUTPUT_TOKENS = 6_000


class RunStopped(RuntimeError):
    """Inspection is required; no implicit retry or new revision clears this stop."""


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


payload_digest = digest


def _clone(value):
    try:
        return json.loads(_encoded(value))
    except (TypeError, ValueError, UnicodeError):
        raise RunStopped("Invalid JSON value") from None


def _text(value):
    return isinstance(value, str) and bool(value.strip()) and "\x00" not in value


def _validate_manifest(manifest):
    if not isinstance(manifest, dict) or not _text(manifest.get("model")):
        raise RunStopped("Invalid manifest model")
    if manifest.get("manifest_hash") != digest({k: v for k, v in manifest.items()
                                               if k != "manifest_hash"}):
        raise RunStopped("Manifest checksum mismatch")
    if manifest.get("endpoint") != ENDPOINT:
        raise RunStopped("Unexpected credential destination")
    if "campaign_id" in manifest and not _text(manifest["campaign_id"]):
        raise RunStopped("Invalid explicit campaign identity")
    for name, ceiling in (("max_requests", MAX_REQUESTS), ("max_tokens", MAX_TOKENS)):
        if type(manifest.get(name)) is not int or not 1 <= manifest[name] <= ceiling:
            raise RunStopped("Manifest exceeds campaign ceiling or has invalid limits")


def _validate_payload(payload, model):
    fields = {"model", "messages", "temperature", "max_tokens", "stream", "reasoning_effort"}
    if not isinstance(payload, dict) or set(payload) != fields:
        raise RunStopped("Invalid payload schema")
    if payload["model"] != model or not _text(model):
        raise RunStopped("Payload model differs from manifest")
    if payload["stream"] is not False or payload["reasoning_effort"] != "none":
        raise RunStopped("Payload requires non-streaming and reasoning_effort=none")
    cap = payload["max_tokens"]
    if type(cap) is not int or not 1 <= cap <= MAX_OUTPUT_TOKENS:
        raise RunStopped("Output cap outside 1..6000")
    temp = payload["temperature"]
    if type(temp) not in (int, float) or not math.isfinite(temp) or not 0 <= temp <= 2:
        raise RunStopped("Invalid temperature")
    messages = payload["messages"]
    if not isinstance(messages, list) or len(messages) != 2:
        raise RunStopped("Expected system and user messages")
    for message, role in zip(messages, ("system", "user")):
        if (not isinstance(message, dict) or set(message) != {"role", "content"}
                or message["role"] != role or not _text(message["content"])):
            raise RunStopped("Invalid message schema")


def make_payload(model, system, prompt, max_output_tokens, temperature=0.2):
    """Return the complete body that is hashed, frozen, and sent without additions."""
    payload = {"model": model, "messages": [{"role": "system", "content": system},
               {"role": "user", "content": prompt}], "temperature": temperature,
               "max_tokens": max_output_tokens, "stream": False, "reasoning_effort": "none"}
    _validate_payload(payload, model)
    return _clone(payload)


def reservation(payload):
    """Operational upper reservation, not a tokenizer or billing estimate."""
    return sum(len(m["content"].encode("utf-8")) for m in payload["messages"]) + 512 + payload["max_tokens"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _signed(value):
    return {**value, "receipt_hash": digest(value)}


def _save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except (OSError, ValueError, TypeError):
        raise RunStopped("Artifact could not be persisted; inspect before further dispatch") from None


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_object)
    except (OSError, UnicodeError, ValueError):
        raise RunStopped("Unreadable or malformed artifact") from None


def _preserve(path, value):
    if path.exists():
        if _read(path) != value:
            raise RunStopped("Frozen artifact differs")
    else:
        _save(path, value)


def _checked(path):
    value = _read(path)
    if (not isinstance(value, dict) or value.get("receipt_hash") != digest(
            {k: v for k, v in value.items() if k != "receipt_hash"})):
        raise RunStopped("Receipt checksum mismatch")
    return value


def _campaign_record(campaign_dir):
    campaign = _checked(campaign_dir / "campaign.json")
    if (set(campaign) != {"version", "campaign_id", "max_requests", "max_tokens", "receipt_hash"}
            or campaign["version"] != "method-selection-v3-campaign-v1"
            or not _text(campaign["campaign_id"])
            or type(campaign["max_requests"]) is not int
            or type(campaign["max_tokens"]) is not int
            or campaign["max_requests"] != MAX_REQUESTS or campaign["max_tokens"] != MAX_TOKENS):
        raise RunStopped("Invalid frozen campaign identity or ceiling")
    return campaign


def _registration(campaign_dir, run_dir, manifest, campaign):
    if (campaign is None or manifest.get("campaign_id", campaign["campaign_id"])
            != campaign["campaign_id"]):
        raise RunStopped("Manifest differs from frozen campaign identity")
    return _signed({"campaign_id": campaign["campaign_id"],
                    "run": run_dir.relative_to(campaign_dir).as_posix(),
                    "manifest_hash": manifest["manifest_hash"]})


def _parse_response(request_id, payload, status, body, elapsed):
    record = {"request_id": request_id, "payload_hash": payload_digest(payload),
              "model": "unreported", "text": "", "finish_reason": "error",
              "usage": {"input_tokens": None, "output_tokens": None}, "latency_ms": elapsed}
    issues, provider_model, provider_usage = [], None, None
    if status != 200:
        issues.append("http_error")
    try:
        data = json.loads(body, object_pairs_hook=_object)
        if not isinstance(data, dict):
            raise ValueError("object required")
        provider_model, provider_usage = data.get("model"), data.get("usage")
        if isinstance(provider_model, str):
            record["model"] = provider_model
        if isinstance(provider_usage, dict):
            for target, source in (("input_tokens", "prompt_tokens"),
                                   ("output_tokens", "completion_tokens")):
                value = provider_usage.get(source)
                if type(value) is int and value >= 0:
                    record["usage"][target] = value
        choices = data.get("choices")
        if not isinstance(choices, list) or len(choices) != 1:
            raise ValueError("one choice required")
        choice = choices[0]
        content = choice["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("text required")
        record["text"] = content
        finish = choice.get("finish_reason")
        if finish not in ("stop", "length", "content_filter"):
            issues.append("unknown_finish_reason")
        else:
            record["finish_reason"] = finish
    except (ValueError, TypeError, KeyError):
        issues.append("invalid_provider_envelope")
    if provider_model != payload["model"]:
        issues.append("provider_model_mismatch")
    if any(value is None for value in record["usage"].values()):
        issues.append("unknown_usage")
    if isinstance(provider_usage, dict) and "total_tokens" in provider_usage:
        total = provider_usage["total_tokens"]
        if (type(total) is not int or any(v is None for v in record["usage"].values())
                or total != sum(record["usage"].values())):
            issues.append("inconsistent_usage")
    inp, out = record["usage"].values()
    if ((inp is not None and inp > reservation(payload) - payload["max_tokens"])
            or (out is not None and out > payload["max_tokens"])):
        issues.append("usage_exceeded_reservation")
    return {"response": record, "provider_model": provider_model,
            "provider_usage": provider_usage, "issues": issues}


def _redact(body, key):
    """Also catch JSON-escaped reflections; such evidence is explicitly transformed."""
    reflected = key in body

    def scrub(value):
        nonlocal reflected
        if isinstance(value, str):
            if key in value:
                reflected = True
            return value.replace(key, "[REDACTED_CREDENTIAL]")
        if isinstance(value, list):
            return [scrub(item) for item in value]
        if isinstance(value, dict):
            return {scrub(k): scrub(v) for k, v in value.items()}
        return value

    try:
        decoded = scrub(json.loads(body))
        if reflected:
            # Re-encoding is restricted to credential-reflecting, failed responses.
            body = json.dumps(decoded, ensure_ascii=False)
    except (ValueError, TypeError):
        pass
    return body.replace(key, "[REDACTED_CREDENTIAL]"), reflected


def _scan(campaign_dir):
    """Recompute from all run evidence; never trust a mutable cumulative counter."""
    rows, issues, uncertain, input_tokens, output_tokens = [], [], 0, 0, 0
    intents = sorted(campaign_dir.rglob("*.intent.json"))
    results = set(campaign_dir.rglob("*.result.json"))
    admissions = list((campaign_dir / "admissions").glob("*.json"))
    registrations = list((campaign_dir / "registrations").glob("*.json"))
    campaign = None
    if (campaign_dir / "campaign.json").exists() or intents or results or admissions or registrations:
        try:
            campaign = _campaign_record(campaign_dir)
        except (RunStopped, KeyError, TypeError, ValueError):
            issues.append("invalid_campaign_identity")
            uncertain += 1
    sequences, identities, seen_intents = set(), set(), {}
    for path in intents:
        result_path = path.with_name(path.name.replace(".intent.json", ".result.json"))
        results.discard(result_path)
        try:
            intent = _checked(path)
            run_dir = path.parent.parent
            manifest = _read(run_dir / "manifest.json")
            _validate_manifest(manifest)
            registration = _registration(campaign_dir, run_dir, manifest, campaign)
            registration_path = campaign_dir / "registrations" / (digest(registration["run"]) + ".json")
            if (_checked(registration_path) != registration
                    or _checked(run_dir / "transport-binding.json") != registration):
                raise RunStopped("Missing or mismatched run registration")
            payload = intent["payload"]
            _validate_payload(payload, manifest["model"])
            rid, seq = intent["request_id"], intent["sequence"]
            identity = (run_dir, rid)
            if (not _text(rid) or type(seq) is not int or seq < 1 or seq in sequences
                    or identity in identities or intent["payload_hash"] != payload_digest(payload)
                    or intent["manifest_hash"] != manifest["manifest_hash"]
                    or intent["reserved_tokens_estimate"] != reservation(payload)
                    or intent["run"] != run_dir.relative_to(campaign_dir).as_posix()
                    or path.name != digest(rid) + ".intent.json"):
                raise RunStopped("Intent identity or reservation mismatch")
            sequences.add(seq)
            identities.add(identity)
            seen_intents[seq] = {"run": intent["run"], "sequence": seq,
                                 "intent_hash": intent["receipt_hash"]}
            if not result_path.exists():
                uncertain += 1
                issues.append("pending_intent")
                continue
            result = _checked(result_path)
            if (result["intent_hash"] != intent["receipt_hash"]
                    or result["manifest_hash"] != manifest["manifest_hash"]
                    or result["payload_hash"] != intent["payload_hash"]):
                raise RunStopped("Result identity mismatch")
            parsed = _parse_response(rid, payload, result["http_status"], result["raw_body"],
                                     result["response"]["latency_ms"])
            expected_issues = list(parsed["issues"])
            if result["transport_error"]:
                expected_issues.append("transport_error")
            if result["raw_body_credential_redacted"]:
                expected_issues.append("credential_reflected_and_redacted")
            if (any(result[k] != parsed[k] for k in ("response", "provider_model", "provider_usage"))
                    or result["issues"] != expected_issues):
                raise RunStopped("Result does not match raw provider evidence")
            inp, out = result["response"]["usage"].values()
            input_tokens += inp if inp is not None else 0
            output_tokens += out if out is not None else 0
            if inp is None or out is None or "inconsistent_usage" in result["issues"]:
                uncertain += 1
            issues.extend(result["issues"])
            rows.append((run_dir, intent, result))
        except (RunStopped, KeyError, TypeError, ValueError, UnicodeError):
            uncertain += 1
            issues.append("invalid_campaign_evidence")
    if results:
        uncertain += len(results)
        issues.append("orphan_result")
    if sequences != set(range(1, len(intents) + 1)):
        issues.append("campaign_sequence_gap")
    # Independent admissions detect lost terminal calls as well as lost revisions.
    registered_intents = {}
    for path in admissions:
        try:
            admission = _checked(path)
            seq = admission["sequence"]
            if type(seq) is not int or seq < 1 or seq in registered_intents:
                raise RunStopped("Invalid campaign admission")
            registered_intents[seq] = {k: v for k, v in admission.items() if k != "receipt_hash"}
            if path.name != str(seq) + ".json":
                raise RunStopped("Admission filename mismatch")
        except (RunStopped, KeyError, TypeError, ValueError):
            issues.append("invalid_campaign_admission")
            uncertain += 1
    if seen_intents != registered_intents:
        issues.append("campaign_admission_mismatch")
        uncertain += 1
    # Registrations persist even if someone removes an entire run directory.
    for path in registrations:
        try:
            registration = _checked(path)
            run_dir = (campaign_dir / registration["run"]).resolve()
            if (not run_dir.is_relative_to(campaign_dir) or run_dir == campaign_dir
                    or campaign is None or registration["campaign_id"] != campaign["campaign_id"]
                    or _read(run_dir / "transport-binding.json") != registration
                    or _read(run_dir / "manifest.json")["manifest_hash"] != registration["manifest_hash"]):
                raise RunStopped("Missing or mismatched registered run")
        except (RunStopped, KeyError, TypeError, ValueError):
            issues.append("missing_registered_run")
            uncertain += 1
    requests = max(len(intents) + len(results), len(admissions))
    return rows, {"actual_requests": requests,
                  "input_tokens": input_tokens, "output_tokens": output_tokens,
                  "total_tokens": input_tokens + output_tokens, "uncertain": bool(uncertain),
                  "uncertain_requests": min(requests, uncertain), "issues": sorted(set(issues)),
                  "max_requests": MAX_REQUESTS, "max_tokens": MAX_TOKENS}


def report_usage(campaign_dir):
    """Report known usage, including failed calls, without credentials or network."""
    campaign_dir = Path(campaign_dir).resolve()
    with provenance_registry_lock(campaign_dir / "execution", timeout=1):
        return _scan(campaign_dir)[1]


class ExperimentClient:
    def __init__(self, run_dir: Path, manifest: dict, client: httpx.Client,
                 key: str, campaign_dir: Path):
        self.run_dir = Path(run_dir).resolve()
        self.campaign_dir = Path(campaign_dir).resolve()
        if self.run_dir == self.campaign_dir or not self.run_dir.is_relative_to(self.campaign_dir):
            raise RunStopped("Run directory must be inside the fixed campaign directory")
        self.manifest = _clone(manifest)
        _validate_manifest(self.manifest)
        self.client, self.key = client, key

    def call(self, request_id: str, payload: dict):
        """Cache first; otherwise admit and dispatch once while holding campaign lock."""
        payload = _clone(payload)
        _validate_manifest(self.manifest)
        _validate_payload(payload, self.manifest["model"])
        if not _text(request_id):
            raise RunStopped("Invalid request ID")
        with provenance_registry_lock(self.campaign_dir / "execution", timeout=1):
            return self._call_locked(request_id, payload)

    def _call_locked(self, request_id, payload):
        if (self.run_dir / "manifest.json").exists():
            if _read(self.run_dir / "manifest.json") != self.manifest:
                raise RunStopped("Frozen manifest differs")
        rows, usage = _scan(self.campaign_dir)
        for run_dir, intent, result in rows:
            if run_dir == self.run_dir and intent["request_id"] == request_id:
                if intent["payload"] != payload or intent["manifest_hash"] != self.manifest["manifest_hash"]:
                    raise RunStopped("Request ID reused with different payload or manifest")
                if result["issues"]:
                    raise RunStopped("Prior provider failure persisted; no automatic retry")
                return _clone(result["response"])
        if usage["issues"] or usage["uncertain"]:
            raise RunStopped("Campaign has failed or uncertain evidence; inspect before new calls")
        campaign = (_campaign_record(self.campaign_dir)
                    if (self.campaign_dir / "campaign.json").exists() else None)
        if (campaign is not None and self.manifest.get("campaign_id", campaign["campaign_id"])
                != campaign["campaign_id"]):
            raise RunStopped("Manifest differs from frozen campaign identity")
        ordered = sorted(rows, key=lambda row: row[1]["sequence"])
        if len(ordered) >= 2 and all(
                not row[2]["response"]["text"].strip()
                or row[2]["response"]["finish_reason"] == "length" for row in ordered[-2:]):
            raise RunStopped("Two consecutive empty or length responses; no new request sent")
        if (usage["actual_requests"] >= self.manifest["max_requests"]
                or usage["total_tokens"] + reservation(payload) > self.manifest["max_tokens"]):
            raise RunStopped("Campaign budget exhausted before dispatch; no request sent")
        # No key inspection is necessary for verified cached responses.
        key = self.key
        if not isinstance(key, str) or not key.strip() or key == "offline" or any(c in key for c in "\r\n"):
            raise RunStopped("A valid explicit credential is required for a new request")
        if key in _encoded({"payload": payload, "manifest": self.manifest,
                            "request_id": request_id}).decode("utf-8"):
            raise RunStopped("Credential detected in request artifacts; no artifacts or request written")
        if campaign is None:
            campaign = _signed({"version": "method-selection-v3-campaign-v1",
                                "campaign_id": self.manifest.get("campaign_id", str(uuid.uuid4())),
                                "max_requests": MAX_REQUESTS, "max_tokens": MAX_TOKENS})
        registration = _registration(self.campaign_dir, self.run_dir, self.manifest, campaign)
        _preserve(self.campaign_dir / "campaign.json", campaign)
        _preserve(self.run_dir / "manifest.json", self.manifest)
        _preserve(self.run_dir / "transport-binding.json", registration)
        _preserve(self.campaign_dir / "registrations" / (digest(registration["run"]) + ".json"),
                  registration)
        intent = _signed({"request_id": request_id, "payload": payload,
                          "payload_hash": payload_digest(payload),
                          "manifest_hash": self.manifest["manifest_hash"],
                          "run": registration["run"], "sequence": usage["actual_requests"] + 1,
                          "reserved_tokens_estimate": reservation(payload), "started_at": _now()})
        stem = self.run_dir / "calls" / digest(request_id)
        _save(stem.with_suffix(".intent.json"), intent)
        _save(self.campaign_dir / "admissions" / (str(intent["sequence"]) + ".json"),
              _signed({"run": registration["run"], "sequence": intent["sequence"],
                       "intent_hash": intent["receipt_hash"]}))
        started, status, body, transport_error = time.monotonic(), None, "", False
        try:
            response = self.client.post(ENDPOINT, content=_encoded(payload),
                                        headers={"Authorization": "Bearer " + key,
                                                 "Content-Type": "application/json"},
                                        follow_redirects=False)
            status, body = response.status_code, response.text
        except Exception:
            # Neither exception strings, types, request objects nor headers are persisted.
            transport_error = True
        elapsed = round((time.monotonic() - started) * 1000, 3)
        body, redacted = _redact(body, key)
        parsed = _parse_response(request_id, payload, status, body, elapsed)
        if transport_error:
            parsed["issues"].append("transport_error")
        if redacted:
            parsed["issues"].append("credential_reflected_and_redacted")
        result = _signed({**parsed, "intent_hash": intent["receipt_hash"],
                          "manifest_hash": self.manifest["manifest_hash"],
                          "payload_hash": intent["payload_hash"], "finished_at": _now(),
                          "http_status": status, "transport_error": transport_error,
                          "raw_body": body, "raw_body_credential_redacted": redacted})
        _save(stem.with_suffix(".result.json"), result)
        if parsed["issues"]:
            raise RunStopped("Provider or usage failure persisted; no automatic retry")
        return _clone(parsed["response"])
