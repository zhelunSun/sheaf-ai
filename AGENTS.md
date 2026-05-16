# Universal Collector — AGENTS.md

> 面向智能体的项目导航。首次阅读本项目代码前，请先读此文件。

## 一句话

用户粘贴链接 → AI 动态提取主题/标签 → 自动摘要 → 存入本地知识库 → Agent 可查询。

## 关键文件地图

| 文件 | 内容 |
|------|------|
| `docs/product-overview.md` | 产品定位、架构、差异化 |
| `docs/schema-v1.md` | 知识卡片 Schema v1.1（动态 topics） |
| `docs/architecture.svg` | 三层架构图 |
| `needs/user-needs.md` | 用户需求文档 |
| `prompts/classify.md` | LLM 动态主题+标签提取 Prompt |
| `prompts/summarize.md` | LLM 摘要 Prompt |
| `scripts/pipeline.py` | 端到端处理流水线 v2（入口） |
| `scripts/fetch_article.py` | 文章抓取模块 v2（平台感知） |
| `scripts/llm_client.py` | LLM 客户端（SiliconFlow + XTY） |
| `data/tags_registry.json` | 全局标签注册表 |
| `data/index.jsonl` | 轻量索引 |
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
python scripts/pipeline.py <url>          # 单篇
python scripts/pipeline.py                # 查看统计（主题分布+标签频率）
python scripts/pipeline.py <url> --force  # 跳过去重
python -c "from scripts.pipeline import query_collection; print(query_collection('rag'))"  # 查询
```

## 版本管理约定

- **Backlog 条目**：`BLG-XXX` 格式，在 `BACKLOG.md` 维护
- **Git commit**：引用 Backlog ID，如 `BLG-001: optimize fetch strategy`
- **CHANGELOG**：发版时从 Backlog 汇总
