# Sheaf Project Long-term Memory

_Updated: 2026-05-23_

## Project Identity

- **Package**: `sheaf-ai` / CLI: `sheaf` / import: `sheaf_ai`
- **Repo**: D:\Agent\WorkBuddy\sheaf-ai
- **Version**: v0.4.0-alpha
- **Brand**: Sheaf（数学层论隐喻）

## Architecture

- `sheaf_ai/` — 主包（16+ 模块，新增 renderer.py），`sheaf_cards/` — 独立卡片子包
- MCP server: 9 tools (JSON-RPC over stdio)
- Embedding: SiliconFlow API + numpy 余弦相似度（无 FAISS）
- LLM: DeepSeek-V3.2 via openai-compatible API
- Renderer: CardOutputConfig + CardRenderer (text/json/detailed) + Jinja2 可选

## Development Workflow

- Nightly dev pipeline: automation 触发 01:30 CST
- Branch: `nightly/YYYY-MM-DD`, never push to main
- `.venv` 隔离环境，所有 pip install 在 .venv 中
- 经验记录三层：`internal/dev-log/`（Sheaf 可收集）+ `.workbuddy/agents/`（Agent 操作手册）+ `.learnings/`（错误和学习）

## Key Patterns

- Monkeypatch 模块级常量：同时 patch 所有派生变量（用 `_patch_cards_dir` helper）
- Mock lazy import：patch 源模块不是使用模块（`patch("source_module.Y")`）
- best-effort embedding：`_embed_cards` 用 try/except，不阻塞核心功能
- KnowledgeCard.id 属性：便捷 alias for card_id（MCP/CLI 消费者）

## Current State (2026-05-23)

- Wave 2 W2-01~07: ✅ 全部完成（140 tests）
- 新增模块: `sheaf_ai/renderer.py` — CardOutputConfig + CardRenderer
- 新增测试: `tests/test_renderer.py` — 30 tests
- Jinja2: 已安装到 .venv（可选依赖，未写入 pyproject.toml）
- Nightly branch: `nightly/2026-05-23`, commit 0c3b9b9
- Wave 2 出口条件: ✅ 全部达成（含 W2-07 输出模板）
- 下一步: Wave 2.5 游戏化 Lite（W2.5-01: sheaf stats）
- ⚠️ 待处理: .venv/ 未在 .gitignore 中
