# Universal Collector — AGENTS.md

> 面向智能体的项目导航。首次阅读本项目代码前，请先读此文件。

## 一句话

用户粘贴微信文章链接 → AI 自动分类摘要 → 存入本地知识库 → Agent 可对话查询。

## 关键文件地图

| 文件 | 内容 |
|------|------|
| `docs/product-overview.md` | 产品定位、架构、差异化 |
| `docs/architecture.svg` | 三层架构图 |
| `needs/user-needs.md` | 用户需求文档 |
| `needs/pm-analysis.md` | PM 视角分析 |
| `proposals/mvp-readiness-checklist.md` | MVP 支撑体系梳理 |
| `prompts/classify.md` | LLM 分类 Prompt |
| `prompts/summarize.md` | LLM 摘要 Prompt |
| `scripts/pipeline.py` | 端到端处理流水线（入口） |
| `scripts/fetch_article.py` | 文章抓取模块 |
| `scripts/llm_client.py` | LLM 客户端（复用） |
| `data/` | 运行时数据（不提交 git） |
| `CHANGELOG.md` | 版本历史 |

## 核心约束

1. **运行时数据分离**：`data/` 目录不提交 git，由 pipeline.py 运行时自动创建
2. **API Key 不提交**：`.env` 文件已加入 `.gitignore`
3. **四大主题**：科研 / 市场投资 / AI 产品 / AI 技术（分类以 LLM 自动提取为主）
4. **优先本地文件系统**：Markdown + JSON，依赖零外部数据库
5. **LLM 默认模型**：DeepSeek-V3.2 via SiliconFlow（国产加速，成本~¥0.3/月）

## 新增收藏入口

```bash
python scripts/pipeline.py <url>          # 单篇
python scripts/pipeline.py                # 查看统计
python -c "from scripts.pipeline import query_collection; print(query_collection('rag'))"  # 查询
```
