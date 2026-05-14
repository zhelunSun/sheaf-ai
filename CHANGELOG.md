# Universal Collector CHANGELOG

## v0.2.0 (2026-05-14) — 战略研究完成

### 新增：竞品调研
- `research/competitor-deep-dive.md` — 8 个竞品深度分析（Readwise、Karakeep、Cubox、NotebookLM、Otio、Mem0、Supermemory、Quivr）
- `research/whitespace-analysis.md` — 2x2 定位图 + Gap 陈述 + 差异化主张 v1 + 风险扫描
- 竞品覆盖 A（传统书签+AI）/ B（AI 原生知识工具）/ C（Agent 记忆+开源社区）三类

### 新增：产品定位精炼
- `docs/positioning-v1.md` — Agent-Native 五维实践定义（数据格式/元数据/检索接口/知识复用/人机分工）
- Agent-Native vs Human-Oriented 的清晰边界声明
- vs nova-reader、skill-factory、通用 RAG 的边界划分

### 新增：行业趋势对齐
- `research/agent-trend-alignment.md` — 五大趋势（Agentic AI / MCP / Memory Layer / AI-Native Ops / Open Format）
- UC Trend Fit 评分（全部为 tailwind）
- Phase 1-3 路线图的趋势对齐建议

### 新增：商业模式与 OPC 运营
- `research/business-model-v1.md` — Open-Core + Skill 市场 + SaaS 对比
- Open-Core vs SaaS Freemium 深度四维对比
- Rough Unit Economics（保守：10-12 月盈亏平衡，60 付费用户）
- `docs/opc-operations-harness.md` — AI-Native OPC 完整运营框架
- 五角色分工（Product/Engineering/Content/Support/Research）
- Weekly Agent Sprint + Phase Gate + Claim-Safe 协议

### 新增：整合与愿景
- `research/strategy-brief-v1.md` — 一页 Executive Summary + 全量引用
- `research/checkpoint-strategy-research.md` — 自审四门报告
- `docs/ecosystem-vision.md` — 三阶段演进生态蓝图（工具→基础设施→平台）

### 更新
- `PLAN.md` — 添加 Phase 0.75，Phase 1 重新排序（Embedding + MCP 优先），Phase 2 扩展为完整生态愿景
- `needs/pm-analysis.md` — 扩展竞品矩阵至 8 个，增加 Agent-Native 五维定义，更新风险

### 核心结论
- Whitespace：「低摩擦收藏 + 高 Agent 集成 + 开放格式」的左上象限完全空白
- 商业模式：Open-Core 三步走（开源社区 → Skill 分发 → 云服务增值）
- 运营方式：AI-Native OPC，1人 + N Agent，Weekly Sprint，10-17h/周等效 3-5 人产出

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
