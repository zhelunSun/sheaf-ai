"""
End-to-end MCP server test — spawns `sheaf mcp` as a real subprocess,
sends JSON-RPC via stdin, reads responses from stdout.

Tests the full MCP lifecycle: initialize → tools/list → tools/call (all 9 tools).
This simulates what WorkBuddy would do when registered as a connector.
"""
import json
import os
import subprocess
import sys
import time

import pytest


if os.environ.get("SHEAF_RUN_E2E") != "1":
    pytest.skip("set SHEAF_RUN_E2E=1 to run subprocess MCP E2E", allow_module_level=True)


SHEAF_EXE = sys.executable.replace("python.exe", "Scripts/sheaf.exe")

def send(req: dict, timeout: float = 15.0) -> dict:
    """Send a JSON-RPC request and return the parsed response."""
    p.stdin.write((json.dumps(req) + "\n").encode("utf-8"))
    p.stdin.flush()
    line = p.stdout.readline()
    if not line:
        # Check if process died
        rc = p.poll()
        if rc is not None:
            stderr = p.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP server died (exit={rc}). stderr: {stderr[:500]}")
        raise RuntimeError(f"Empty response from MCP server for: {req}")
    return json.loads(line)


def check_ok(resp: dict, step: str) -> None:
    """Fail fast if response has an error."""
    if "error" in resp:
        raise AssertionError(f"[{step}] ERROR: {resp['error']}")
    if "result" not in resp:
        raise AssertionError(f"[{step}] No result: {resp}")


# --- Start MCP server ---
print("=== 1. Start MCP server ===")
p = subprocess.Popen(
    [SHEAF_EXE, "mcp"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
print(f"  PID: {p.pid}")
time.sleep(0.5)
assert p.poll() is None, f"Server died immediately: {p.stderr.read()}"

# --- 2. Initialize ---
print("\n=== 2. Initialize ===")
resp = send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
check_ok(resp, "init")
result = resp["result"]
print(f"  Server: {result['serverInfo']['name']} v{result['serverInfo']['version']}")
print(f"  Protocol: {result['protocolVersion']}")
assert result["capabilities"]["tools"] == {}, "Expected tools capability"
assert result["protocolVersion"] == "2025-06-18"

# --- 3. Send initialized notification ---
print("\n=== 3. Initialized notification ===")
p.stdin.write((json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode("utf-8"))
p.stdin.flush()
print("  Sent (no response expected)")

# --- 4. Tools list ---
print("\n=== 4. tools/list ===")
resp = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
check_ok(resp, "tools/list")
tools = resp["result"]["tools"]
print(f"  Tools: {len(tools)}")
tool_names = [t["name"] for t in tools]
print(f"  Names: {tool_names}")
expected = [
    "sheaf_collect", "sheaf_search",
    "sheaf_crystallize", "sheaf_get_card",
]
for name in expected:
    assert name in tool_names, f"Missing tool: {name}"
# Default surface is 4 core tools; the other 7 are CLI-only (Issue #91).
assert len(tools) == 4, f"Expected 4 core tools, got {len(tools)}: {tool_names}"
print("  All 4 core tools present ✅")

# --- 5. sheaf_search ---
print("\n=== 5. sheaf_search ===")
resp = send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "sheaf_search", "arguments": {"query": "遥感", "deep": False}}})
check_ok(resp, "search")
results = json.loads(resp["result"]["content"][0]["text"])
print(f"  Results: {len(results)}")
for r in results[:3]:
    print(f"    - [{r.get('importance','')}] {r['title'][:50]}")
assert len(results) >= 1, "Should find at least 1 result for '遥感'"

# --- 6. sheaf_list ---
print("\n=== 6. sheaf_list ===")
resp = send({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "sheaf_list", "arguments": {"limit": 5}}})
check_ok(resp, "list")
entries = json.loads(resp["result"]["content"][0]["text"])
print(f"  Entries: {len(entries)}")
for e in entries[:3]:
    print(f"    - [{e.get('collected_at','')[:10]}] {e['title'][:40]}")
assert len(entries) >= 1

# --- 7. sheaf_get ---
print("\n=== 7. sheaf_get ===")
entry_id = entries[0]["id"]
resp = send({"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "sheaf_get", "arguments": {"entry_id": entry_id}}})
check_ok(resp, "get")
entry = json.loads(resp["result"]["content"][0]["text"])
print(f"  ID: {entry['id']}")
print(f"  Title: {entry['title'][:50]}")
print(f"  Topics: {[t['name'] for t in entry.get('topics',[])]}")
print(f"  Has summary_md: {'summary_markdown' in entry}")
assert entry["id"] == entry_id

# --- 8. sheaf_get (missing) ---
print("\n=== 8. sheaf_get (missing) ===")
resp = send({"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "sheaf_get", "arguments": {"entry_id": "0000-00-00_nonexistent"}}})
assert "error" in resp, "Should return error for missing entry"
assert "not found" in resp["error"]["message"].lower()
print(f"  Correctly returned error: {resp['error']['message']}")

# --- 9. sheaf_urgent ---
print("\n=== 9. sheaf_urgent ===")
resp = send({"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "sheaf_urgent", "arguments": {}}})
check_ok(resp, "urgent")
items = json.loads(resp["result"]["content"][0]["text"])
print(f"  Urgent items: {len(items)}")

# --- 10. sheaf_crystallize ---
print("\n=== 10. sheaf_crystallize ===")
resp = send({"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "sheaf_crystallize", "arguments": {"topic": "遥感"}}})
check_ok(resp, "crystallize")
data = json.loads(resp["result"]["content"][0]["text"])
print(f"  Topic: {data['topic']}")
print(f"  Cards generated: {data['cards_generated']}")

# --- 11. sheaf_list_cards ---
print("\n=== 11. sheaf_list_cards ===")
resp = send({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "sheaf_list_cards", "arguments": {}}})
check_ok(resp, "list_cards")
data = json.loads(resp["result"]["content"][0]["text"])
print(f"  Total cards: {data['total']}")

# --- 12. sheaf_get_card ---
if data["total"] > 0:
    print("\n=== 12. sheaf_get_card ===")
    card_id = data["cards"][0]["id"]
    resp = send({"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "sheaf_get_card", "arguments": {"card_id": card_id}}})
    check_ok(resp, "get_card")
    card_text = resp["result"]["content"][0]["text"]
    card = json.loads(card_text)
    print(f"  Card: {card.get('title', card.get('card_id', '?'))}")
else:
    print("\n=== 12. sheaf_get_card (skipped — no cards) ===")

# --- 13. sheaf_collect (known duplicate — instant dedup, no LLM) ---
print("\n=== 13. sheaf_collect (known duplicate) ===")
resp = send({"jsonrpc": "2.0", "id": 11, "method": "tools/call", "params": {"name": "sheaf_collect", "arguments": {"url": "https://mp.weixin.qq.com/s/8xKqgqT0fUP3scCgWZTc3w"}}})
parsed = json.loads(resp["result"]["content"][0]["text"])
print(f"  Success: {parsed['success']}, Stage: {parsed.get('stage','?')}")
assert not parsed["success"], "Expected duplicate detection"
assert parsed["stage"] == "dedup", f"Expected dedup stage, got {parsed.get('stage')}"
print("  Correctly detected duplicate ✅")

# --- 14. Ping ---
print("\n=== 14. Ping ===")
resp = send({"jsonrpc": "2.0", "id": 12, "method": "ping"})
check_ok(resp, "ping")
print("  Pong ✅")

# --- 15. Unknown tool ---
print("\n=== 15. Unknown tool ===")
resp = send({"jsonrpc": "2.0", "id": 13, "method": "tools/call", "params": {"name": "nonexistent", "arguments": {}}})
assert "error" in resp
assert resp["error"]["code"] == -32601
print(f"  Correctly rejected: {resp['error']['message']}")

# --- Cleanup ---
print("\n=== Cleanup ===")
p.stdin.close()
p.wait(timeout=5)
stderr_output = p.stderr.read().decode("utf-8", errors="replace")
if stderr_output:
    print(f"  stderr: {stderr_output[:200]}")

print("\n" + "=" * 50)
print("ALL 15 CHECKS PASSED ✅")
print("=" * 50)
