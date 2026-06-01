# Sheaf One-Click Install Research

> 2026-06-01 | Competing products analyzed: Kimi WebBridge, agent-browser, Codex Plugins, MCP (npx/uvx)

## Competitive Landscape

| Product | Install Method | Steps | Post-Install Friction |
|---------|---------------|-------|-----------------------|
| **Kimi WebBridge** | Chrome Store + 1 curl | 1-2 | Desktop version: zero config |
| **agent-browser** | `npm i -g` → `agent-browser install` | 2 | Auto-downloads Chrome; `doctor` for diagnostics |
| **Codex Plugins** | marketplace → click | 1 | App-store model; cached and versioned |
| **MCP (npx)** | paste 1 line in mcp.json | 1 | `npx` auto-downloads and runs |
| **MCP (uvx)** | paste 1 line in mcp.json | 1 | `uvx` auto-downloads and runs |
| **Sheaf (current)** | `pip install` → `sheaf setup` → API keys → mcp.json | **4** | ⚠️ Steps 2-4 are friction |

## Key Insight

**Every successful tool has ≤2 user-facing steps.** The post-install work (dependency download, config, registration) is automated, not manual.

## Sheaf's Advantage

`uvx sheaf-ai` (Issue #40, already works) puts Sheaf at parity with npx/uvx MCP servers. The gap is the **3-step tail**: setup → API keys → MCP registration.

## Proposed One-Click Paths

### Path A: Browser Extension First (1 click)
```
User installs Chrome Extension → opens popup → "Connect" button
→ Extension auto-configures everything (API key prompt or free tier)
→ MCP server auto-registered in the user's AI agent
```
- **Target**: 0 terminal commands for end users
- **Reach**: Largest potential user base (non-developers)

### Path B: One-Line Terminal Install (1 copy-paste)
```
curl -sSL https://get.sheaf.ai | bash
# Or: npx sheaf-ai init
# Or: uvx sheaf-ai init --auto
```
- **What it does**: pip install → sheaf setup with guided API key input → auto-detect AI agents → register MCP server
- **Target**: Developer users
- **Reference**: Oh-My-Zsh, Homebrew, agent-browser

### Path C: WorkBuddy Skill as Install Gateway (load a skill)
```
User loads `sheaf-installer` skill → says "install sheaf"
→ Agent handles pip install, config, MCP registration, test
```
- **Target**: WorkBuddy users
- **Reference**: Kimi WebBridge's "one curl" pattern
- **Note**: This is the user's original idea — "paste one line, Agent does the rest"

## Competitive Pattern: What They All Do

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│  Discovery    │ → │  Install     │ → │  Immediate    │
│  (1 action)   │    │  (automated) │    │  Value        │
└──────────────┘    └──────────────┘    └──────────────┘
Click/Type/Paste    Dependencies,      First run
                    config, register   produces result
```

Sheaf is missing only the **automated config layer** between install and value.

## Immediate Action (13:30 smoke test will validate)

1. Verify `pip install sheaf-ai` works in blank venv (the first step)
2. Measure the gap: what exactly fails/shows friction after install?
3. Propose minimal fix for v0.4.0a1: `sheaf init --auto` command that:
   - Prompts for API key interactively (or reads from env var)
   - Creates default config
   - Outputs the MCP server registration line for copy-paste into mcp.json
   - Shows a "you're ready" message with first command to try

## Next: `sheaf init --auto` Spec (draft)

```bash
$ sheaf init --auto

Sheaf v0.4.0 — One-Click Setup
───────────────────────────────
✓ Python 3.13 detected
✓ Sheaf installed at /path/to/sheaf
? API Key (leave empty to skip): ********
✓ Config saved to ~/.sheaf/config.toml
✓ Data directory: ~/.sheaf/data/
✓ Test embedding: connected

🎉 Sheaf is ready!
Try your first collection:
  sheaf collect "https://example.com/article"

For AI agent integration, add to your MCP config:
  sheaf serve --mcp

Or one-line in Claude Code:
  codex mcp add sheaf -- uvx sheaf-ai serve
```

## References

- Kimi WebBridge: https://kimi.com/features/webbridge
- agent-browser: https://github.com/vercel-labs/agent-browser
- Codex Plugins: https://knightli.com/2026/05/06/codex-app-complete-guide-skills-mcp/
- Sheaf Issue #40 (uvx deploy): closed 2026-06-01
