# Universal Collector — AGENTS.md

> 面向智能体的项目导航。首次阅读本项目代码前，请先读此文件。

## 一句话

用户粘贴链接 → AI 动态提取主题/标签 → 自动摘要 → 存入本地知识库 → Agent 可查询。

## 关键文件地图

| 文件 | 内容 |
|------|------|
| `uc/__init__.py` | 版本号唯一来源（`__version__`） |
| `uc/config.py` | 共享常量、路径、编码修复 |
| `uc/pipeline.py` | 端到端处理流水线（编排层） |
| `uc/fetch_article.py` | 文章抓取（requests + playwright fallback） |
| `uc/llm_client.py` | LLM 客户端（SiliconFlow + XTY） |
| `uc/storage.py` | 存储与索引管理 |
| `uc/query.py` | 查询、统计、趋势分析 |
| `uc/feedback.py` | 纠偏反馈回路 |
| `uc/mcp_server.py` | MCP stdio server（6 工具） |
| `uc/cli.py` | CLI 入口（`uc` 命令） |
| `uc/utils.py` | URL标准化、内容hash、平台检测 |
| `pyproject.toml` | 包配置 + CLI 入口 + ruff 规则 |
| `docs/schema-v1.md` | 知识卡片 Schema v1.1（动态 topics） |
| `docs/architecture.svg` | 三层架构图 |
| `prompts/classify.md` | LLM 动态主题+标签提取 Prompt |
| `prompts/summarize.md` | LLM 摘要 Prompt |
| `data/tags_registry.json` | 全局标签注册表 |
| `data/index.jsonl` | 轻量索引 |
| `scripts/` | 旧原型代码（Phase 1 遗留，保留不删） |
| `BACKLOG.md` | 待办/Idea/Bug 追踪 |
| `CHANGELOG.md` | 版本历史 |

## 核心约束

1. **运行时数据分离**：`data/` 目录不提交 git，由 pipeline.py 运行时自动创建
2. **API Key 不提交**：`.env` 文件已加入 `.gitignore`
3. **动态主题体系**：不做硬分类，LLM 自由提取 topics + tags（Schema v1.1）
4. **优先本地文件系统**：Markdown + JSON，依赖零外部数据库
5. **LLM 默认模型**：DeepSeek-V3.2 via SiliconFlow（成本~¥0.3/月）
6. **Windows 兼容**：所有 CLI 脚本入口加 `sys.stdout.reconfigure(encoding="utf-8")`

## 收藏入口

```bash
# 新 CLI（推荐）
uc <url>                 # 收藏一篇
uc                       # 查看统计（主题分布+标签频率）
uc --tags                # 标签统计
uc --trends              # 话题趋势
uc --urgent              # 紧急/即将到期
uc --reclassify          # 重新分类所有条目
uc --version             # 版本号

# 旧方式（仍可用，指向 scripts/）
python scripts/pipeline.py <url>

# Python API
python -c "from uc.query import query_collection; print(query_collection('rag'))"

# MCP Server（stdio transport）
python -m uc.mcp_server
```

## 版本管理约定

- **Backlog 条目**：`BLG-XXX` 格式，在 `BACKLOG.md` 维护
- **Git commit**：引用 Backlog ID，如 `BLG-001: optimize fetch strategy`
- **CHANGELOG**：发版时从 Backlog 汇总
