# Sheaf Project Long-term Memory

_Updated: 2026-05-22_

## Project Identity

- **Package**: `sheaf-ai` / CLI: `sheaf` / import: `sheaf_ai`
- **Repo**: D:\Agent\WorkBuddy\sheaf-ai
- **Version**: v0.4.0-alpha
- **Brand**: Sheaf（数学层论隐喻）

## Architecture

- `sheaf_ai/` — 主包（15+ 模块），`sheaf_cards/` — 独立卡片子包
- MCP server: 9 tools (JSON-RPC over stdio)
- Embedding: SiliconFlow API + numpy 余弦相似度（无 FAISS）
- LLM: DeepSeek-V3.2 via openai-compatible API

## Development Workflow

- Nightly dev pipeline: automation 触发 01:30 CST
- Branch: `nightly/YYYY-MM-DD`, never push to main
- `.venv` 隔离环境，所有 pip install 在 .venv 中
- 经验记录三层：`internal/dev-log/`（Sheaf 可收集）+ `.workbuddy/agents/`（Agent 操作手册）+ `.learnings/`（错误和学习）

## Key Patterns

- Monkeypatch 模块级常量：同时 patch 所有派生变量（用 `_patch_cards_dir` helper）
- Mock lazy import：patch 源模块不是使用模块（`patch("source_module.Y")`）
- best-effort embedding：`_embed_cards` 用 try/except，不阻塞核心功能

## Current State (2026-05-22)

- Wave 2 W2-01~06: ✅ 全部完成（104 tests + E2E）
- E2E 环境: `D:/Agent/WorkBuddy/sheaf-e2e-test/`（run-e2e.sh）
- Bug fix: `ensure_data_dirs()` 在 `process_url()` 中调用（BLG-K04）
- UX: 6 new issues from E2E (UX-12~14, total 10 P0/P1)
- Nightly branch: `nightly/2026-05-22`, 5 commits
- Wave 2 出口条件: ✅ 全部达成
- Quality: ruff linting clean (per-file-ignores for CLI compact syntax)
- Docs: README rewritten, CHANGELOG created
