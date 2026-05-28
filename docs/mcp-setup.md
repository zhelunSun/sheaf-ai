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
# Option A: Sheaf auto-setup
sheaf setup --target claude

# Option B: Claude CLI (if uvx is available)
claude mcp add sheaf -- python -m sheaf_ai.mcp_server
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

| Tool | Description |
|------|-------------|
| `sheaf_search` | Full-text search across all collected entries |
| `sheaf_list` | List entries with optional category filter |
| `sheaf_get` | Get full details of a specific entry by ID |
| `sheaf_urgent` | Get entries with upcoming deadlines |
| `sheaf_correct` | Submit corrections/feedback for an entry |
| `sheaf_collect` | Collect a URL into the knowledge base |
| `sheaf_crystallize` | Crystallize knowledge cards from a topic |
| `sheaf_list_cards` | List crystallized knowledge cards |
| `sheaf_get_card` | Get full details of a knowledge card |

---

## Manual Configuration

If you prefer to configure manually, add this to your MCP config file:

```json
{
  "mcpServers": {
    "sheaf": {
      "command": "/path/to/python",
      "args": ["-m", "sheaf_ai.mcp_server"],
      "env": {
        "OPENAI_API_KEY": "your-api-key-here",
        "SHEAF_DATA_DIR": "/path/to/sheaf/data"
      }
    }
  }
}
```

**Notes:**
- `command`: Use the full path to the Python interpreter where `sheaf-ai` is installed
- `args`: The MCP server module path (`sheaf_ai.mcp_server`)
- `env.OPENAI_API_KEY`: Required for LLM-powered features (classify, summarize, crystallize)
- `env.SHEAF_DATA_DIR`: Optional — defaults to `./data` relative to CWD

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
