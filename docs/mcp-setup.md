# MCP Setup Guide

Sheaf exposes its full knowledge layer via the **MCP (Model Context Protocol)**, enabling any MCP-compatible Agent to search, collect, and crystallize knowledge.

## Quick Start

### One-command setup (recommended)

```bash
# Auto-detect your platform and write config
sheaf setup

# Or specify a target
sheaf setup --target cursor
sheaf setup --target claude
sheaf setup --target workbuddy
sheaf setup --target windsurf
```

### Preview without writing

```bash
sheaf setup --target cursor --dry-run
```

### Print config for manual setup

```bash
sheaf setup --show-config
```

---

## Platform-Specific Guides

### Claude Code

```bash
# Option A: zero-install via uvx (recommended — no pip install needed)
claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp

# Option B: Sheaf auto-setup (writes config + deploys the skill)
sheaf setup --target claude
```

**Config location**: `~/.claude.json`

After setup:
1. Restart Claude Code
2. Run `claude mcp list` — should show `sheaf`

### Cursor

```bash
sheaf setup --target cursor
```

**Config location**: `.cursor/mcp.json` (in your project root)

After setup:
1. Restart Cursor or reload the window (`Ctrl+Shift+P` → "Reload Window")
2. Open any chat — the Sheaf MCP tools should auto-appear

### WorkBuddy (CodeBuddy)

```bash
sheaf setup --target workbuddy
```

**Config location**: `~/.workbuddy/mcp.json`

After setup:
1. Open WorkBuddy → Settings → Custom Connectors
2. Click **Trust** on the new `sheaf` MCP server
3. Start a new conversation — Sheaf tools will be available

### Windsurf

```bash
sheaf setup --target windsurf
```

**Config location**: `.windsurf/mcp.json` (in your project root)

After setup:
1. Restart Windsurf
2. The Sheaf MCP tools should appear in the agent panel

---

## Available MCP Tools

Sheaf's MCP surface is intentionally lean — **4 core tools** cover ~90% of agent workflows and keep the schema small (~1.5k tokens). See [Issue #91](https://github.com/zhelunSun/sheaf-ai/issues/91) for the rationale.

| Core tool | Description |
|-----------|-------------|
| `sheaf_collect` | Collect a URL **or a pasted note** (`url` or `text`) |
| `sheaf_search` | Full-text + semantic search (keyword / hybrid / quick) |
| `sheaf_crystallize` | Crystallize knowledge cards from a topic |
| `sheaf_get_card` | Get full details of a knowledge card |

7 more tools (`sheaf_list`, `sheaf_get`, `sheaf_correct`, `sheaf_insights`, `sheaf_crosscheck`, `sheaf_list_cards`, `sheaf_collect_batch`) stay reachable via the `sheaf` CLI (`--json`) or MCP `tools/call` — their handlers are kept for backward compatibility. Re-expose the full set with `SHEAF_MCP_TOOLS=all`. For Claude Code & Codex, `sheaf setup` also deploys a bundled skill / AGENTS note that tells the agent when to use the CLI for these.

---

## Manual Configuration

Prefer `sheaf setup` (above) — it writes the right format for each platform. If you configure manually, prefer the path-independent `sheaf-mcp` command (or `uvx` for zero-install) over a hard-coded Python path, which breaks when the venv moves:

```json
{
  "mcpServers": {
    "sheaf": {
      "command": "sheaf-mcp",
      "env": {
        "SHEAF_API_KEY": "your-openai-compatible-key",
        "SHEAF_DATA_DIR": "/path/to/sheaf/data"
      }
    }
  }
}
```

**Notes:**
- `command`: `sheaf-mcp` (installed by `pip install sheaf-ai`) or `uvx --from sheaf-ai sheaf-mcp` (zero-install). Fallback: `python -m sheaf_ai.mcp_server`.
- API key: any OpenAI-compatible key. `SHEAF_API_KEY` is generic; or use a provider-specific var (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, …) and set `DEFAULT_PROVIDER` + `OPENAI_BASE_URL` for non-OpenAI endpoints. `sheaf config setup` stores keys in `~/.sheaf/config.json` so you can omit them here.
- `SHEAF_DATA_DIR`: optional. Without it, Sheaf resolves data three-tier: `SHEAF_DATA_DIR` → `./data` (if CWD has project markers) → `~/.sheaf/data`.

## Troubleshooting

### "Sheaf command not found"

Make sure `sheaf-ai` is installed in the Python environment:
```bash
pip install sheaf-ai
sheaf --version
```

### MCP server not appearing

1. Check the config file exists at the correct path
2. Verify the Python path in the config matches your environment
3. Test manually: `python -m sheaf_ai.mcp_server` (then send `{"jsonrpc":"2.0","method":"initialize","id":1}`)

### "API Key not found"

Set your API key either:
- In `.env` file in your project root: `OPENAI_API_KEY=sk-...`
- In the MCP config `env` block
- As a system environment variable
