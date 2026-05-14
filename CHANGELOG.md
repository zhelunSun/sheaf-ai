# Universal Collector CHANGELOG

## v0.1.0 (2026-05-13) — MVP 跑通

### 新增
- 三层架构设计（收录→加工→消费），Agent-Oriented 产品理念
- 用户需求文档 `needs/user-needs.md` v0.2
- PM 视角分析 `needs/pm-analysis.md` v0.1
- 产品概览 `docs/product-overview.md`
- 三层架构图 `docs/architecture.svg`

### MVP 脚本
- `scripts/fetch_article.py` — 文章抓取（requests → playwright → 手动粘贴三级 fallback）
- `scripts/pipeline.py` — 端到端流水线（抓取→分类→摘要→存储+查询）
- `scripts/llm_client.py` — LLM 客户端（SiliconFlow + XTY 双 Provider）
- `prompts/classify.md` — LLM 分类 Prompt（四大主题 + AI 子分类）
- `prompts/summarize.md` — LLM 摘要 Prompt（一句 + 结构化要点）

### 技术验证
- 微信文章 requests 可直接抓取 ✅（4/4 成功）
- DeepSeek-V3.2 分类+摘要质量达可用水平
- 成本~¥0.012/4篇，可忽略
- `data/index.jsonl` + 关键词查询可用

### 数据分离
- `data/` 运行时数据不与源码混放
- `.gitignore` 排除 data/、.env、__pycache__

### 已知不足
- 微信文章标题提取为空（需从 meta og:title 解析）
- 分类暂无用户纠偏机制
- 仅支持关键词搜索（无语义检索）
- 无去重机制
