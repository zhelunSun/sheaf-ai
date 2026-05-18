# Agent-Native Positioning Refinement v1

> Universal Collector 产品定位精炼文档：定义「Agent-Native」的实践维度、精炼定位声明、明确产品边界。
> 日期：2026-05-14
> 依赖：`research/competitor-deep-dive.md`、`research/whitespace-analysis.md`、`needs/pm-analysis.md`

---

## 1. 「Agent-Native」五维实践定义

Agent-Native 不是营销标签，而是一组可验证的设计决策。以下是五个实践维度，以及 UC 在每个维度的当前状态与未来实现。

---

### 维度 1：数据格式（Data Format for Agent Consumption）

**定义**：存储格式必须对 Agent「可解析、可理解、可操作」，而非仅对人类「可读、可浏览」。

| 要求 | 反模式（Human-Oriented） | UC 当前实现 | UC 未来实现 |
|------|------------------------|------------|------------|
| 纯文本优先 | 富文本/HTML/PDF（需渲染才能理解） | ✅ Markdown + 原始文本双存储 | — |
| 结构化元数据 | 无标准字段，只有文件夹/标签 | ✅ JSON schema：title/category/tags/summary/source/timestamp/importance | 扩展 schema：evidence_type, confidence_level, review_status（借鉴 ai-native-research 卡片设计） |
| 无锁定格式 | 专有格式（Notion/印象笔记） | ✅ 全部开放格式（Markdown/JSON/txt） | 增加标准化导出（OPML, RSS, RDF） |
| Embedding 就绪 | 仅存储原始内容 | ❌ 无 embedding | Phase 1：ChromaDB 向量存储，每条记录带 vector + source_id |

**验证标准**：一个外部 Agent 能否在零人工干预的情况下，读取 UC 的数据并理解「这是什么、属于哪类、何时收藏、为什么重要」？

---

### 维度 2：元数据结构化（Structured Metadata）

**定义**：每条知识必须有机器可解析的「上下文骨架」，Agent 不需要阅读全文就能判断相关性和用途。

| 元数据字段 | 用途（对 Agent） | UC 当前 | UC 未来 |
|-----------|----------------|--------|--------|
| `title` | 快速识别主题 | ✅ 自动提取 | — |
| `category` / `subcategory` | 领域路由（Agent 知道该问哪个专家） | ✅ LLM 自动 4 类分类 | 扩展为可配置 taxonomy |
| `tags` | 细粒度关联检索 | ✅ LLM 自动提取 | 增加共现标签图谱 |
| `one_liner` | 30 秒判断相关性 | ✅ LLM 生成 | — |
| `core_argument` | 无需读全文即可获知核心观点 | ✅ LLM 结构化摘要 | — |
| `relevance_to_user` | 个性化优先级排序 | ✅ LLM 评估 | 结合用户行为反馈校准 |
| `action_items` / `deadlines` | Agent 可直接转化为任务 | ✅ LLM 提取 | 与日历/待办系统联动 |
| `source_url` / `fetched_at` | 溯源与时效性判断 | ✅ 自动记录 | 增加内容更新检测 |
| `importance` | Agent 检索时的排序权重 | ✅ LLM 评估 1-5 | 结合用户反馈动态调整 |

**关键洞察**：ai-native-research 的知识卡片实验证明，**结构化元数据比原始文本更能提升 Agent 的规划质量**（G3 Asset-RAG vs G2 Text-RAG）。UC 的元数据层就是面向终端用户的「轻量级知识卡片」。

---

### 维度 3：检索接口（Retrieval Interface）

**定义**：Agent 必须能通过多种方式查询知识库，从精确匹配到语义关联到对话式探索。

| 接口层级 | 查询范式 | UC 当前 | UC 未来 |
|---------|---------|--------|--------|
| L1: 关键词 | `query_collection("RAG")` | ✅ 字符串匹配 title/category/tags/summary | 增加布尔逻辑、模糊匹配 |
| L2: 语义向量 | 向量相似度检索 | ❌ 未实现 | Phase 1：ChromaDB + embedding，支持「找类似这篇文章的内容」 |
| L3: 结构化过滤 | `category=="市场投资" AND importance>=4` | ❌ 未实现 | Phase 1：JSONL 上的结构化查询 |
| L4: Agent 对话式 | 「我上周收藏的关于 Agent 记忆的文章有哪些？」 | ❌ 未实现 | Phase 2：自然语言 → 查询计划 → 执行 |
| L5: MCP Server | 外部 Agent 通过 MCP 协议消费 UC 知识库 | ❌ 未实现 | Phase 2：UC 作为 MCP Server 暴露检索接口 |

**关键洞察**：检索接口的演进路径是从「人类查询」到「Agent 查询」到「Agent 自主查询」。UC 的终点是 L5：任何支持 MCP 的 Agent 都能把 UC 当作其长期记忆层。

---

### 维度 4：知识复用（Knowledge Reuse）

**定义**：收藏的知识必须能流动 —— 从 UC 注入到任何 Agent、Workflow、Skill 或报告，而非锁死在 UC 内部。

| 复用场景 | 描述 | UC 当前 | UC 未来 |
|---------|------|--------|--------|
| 注入 Agent Context | 把相关收藏作为上下文发给 LLM | ⚠️ 需手动复制 | Phase 1：`uc.get_context(query, top_k=5)` API |
| 生成 Skill | 把某类收藏一键转化为可发布 Skill | ❌ 未实现 | Phase 2：与 skill-factory 联动，taxonomy → Skill template |
| 生成报告 | 按主题自动汇总收藏并生成 Markdown 报告 | ❌ 未实现 | Phase 2：Scheduled report（WorkBuddy automation） |
| 导出知识卡片 | 单条或批量导出为 ai-native-research 兼容的卡片格式 | ❌ 未实现 | Phase 2：schema.json 兼容导出 |
| 同步到外部系统 | 同步到 Obsidian/Notion/Logseq | ❌ 未实现 | Phase 1：Markdown 文件夹同步 |

**关键洞察**：知识复用是 UC 从「工具」升级为「基础设施」的关键。当用户的收藏能成为其所有 Agent 的共享上下文时，UC 就变成了个人知识操作系统（Personal Knowledge OS）。

---

### 维度 5：人机分工（Human-Agent Division of Labor）

**定义**：Agent 做所有能自动化的事，人类只做判断、纠偏和创意 —— 且人类的介入点必须明确、低频、高价值。

| 环节 | Agent 负责 | 人类负责 | UC 当前 | UC 未来 |
|------|-----------|---------|--------|--------|
| 收录 | 自动抓取、去重、存储 | 提供 URL / 一键收藏 | ✅ 全自动 | Browser plugin 进一步降低摩擦 |
| 分类 | LLM 自动分类、打标签 | 纠偏错误分类 | ✅ 全自动 | Phase 1：反馈循环（人类说「错了」→ 记住偏好） |
| 摘要 | LLM 生成结构化摘要 | 审核关键摘要 | ✅ 全自动 | — |
| 检索 | 执行查询、排序、去重 | 提出查询意图 | ⚠️ 需手动写代码 | Phase 2：自然语言接口 |
| 复用 | 格式化输出、注入上下文 | 决策「用在哪里」 | ❌ 未实现 | Phase 2：Workflow 模板 |
| 归档/清理 | 自动检测过期内容、低质量内容 | 最终确认删除 | ❌ 未实现 | Phase 2：自动归档策略 |

**关键洞察**：ai-native-research 的五日 Agent Handoff 模式证明，**明确的人机分工边界是 AI-Native 运营的前提**。UC 的加工层应做到「零人工」，消费层应做到「人类只决策、不执行」。

---

## 2. 精炼定位声明（Refined Positioning Statement）

### 英文版（完整版）

> For **knowledge workers who already use AI agents daily**, who **collect scattered content across WeChat, web, newsletters, and papers but never revisit 95% of it**, Universal Collector is a **personal knowledge ingestion and activation pipeline** that **turns any link into structured, queryable, agent-ready knowledge assets in under 10 seconds**. Unlike **Readwise or Cubox**, our product is **designed for agent consumption from day one — open formats, structured metadata, and native agent interfaces, not just a better reading list**. Unlike **Mem0 or Supermemory**, we **start from the user's friction (one paste) rather than the developer's API**.

### 中文版（完整版）

> 对于**每天使用 AI Agent 的知识工作者**，那些**在微信、网页、Newsletter、论文中收藏了大量内容却从不回看的人**，Universal Collector 是一个**个人知识摄取与激活管道**，能在 **10 秒内把任意链接转化为结构化、可查询、Agent 就绪的知识资产**。与 **Readwise 或 Cubox** 不同，我们的产品**从第一天就为 Agent 消费而设计 —— 开放格式、结构化元数据、原生 Agent 接口，而不仅是更好的阅读列表**。与 **Mem0 或 Supermemory** 不同，我们**从用户的摩擦出发（粘贴一下）而非开发者的 API**。

### 一句话版本（Slogan）

> **Universal Collector — 让你的收藏，Agent 能用。**

> *Readwise helps you remember what you read. UC helps your Agents use what you saved.*

### 三句话电梯 pitch

1. 你每天都在收藏文章，但 95% 再也没看过 —— 这是「收藏即坟墓」。
2. Universal Collector 不改变你的习惯（还是粘贴链接），但 AI 自动把它变成 Agent 能读懂的知识资产。
3. 你的 Agent 从此能回答：「我上周收藏的关于 MCP 的文章有哪些？」「总结一下我收藏的所有 Agent 记忆相关的文章。」「把这些收藏变成一个 Skill。」

---

## 3. 边界声明（Product Boundary）

明确 UC **是什么**、**不是什么**，避免功能蔓延和战略模糊。

### 3.1 UC vs nova-reader

| 维度 | UC | nova-reader |
|------|-----|-------------|
| **处理对象** | 碎片化网络内容：微信文章、博客、Newsletter、Twitter 线程 | 学术论文：arXiv PDF、期刊论文 |
| **加工深度** | 轻量级：自动分类 + 结构化摘要（30 秒内完成） | 重量级：精读笔记、方法提取、实验分析、引用网络 |
| **输出格式** | 知识卡片（JSON + Markdown） | 精读报告（结构化分析 + 批判性评价） |
| **使用场景** | 日常信息摄取、快速检索、Agent 上下文注入 | 文献综述、研究前沿跟踪、论文写作素材 |
| **关系** | UC 可识别「这是论文」并路由到 nova-reader 进行深度处理；nova-reader 的产出可回流到 UC 作为结构化知识资产 |

**边界原则**：UC 不取代 nova-reader 的学术精读能力；UC 负责「广度」，nova-reader 负责「深度」。

### 3.2 UC vs skill-factory

| 维度 | UC | skill-factory |
|------|-----|---------------|
| **定位** | 上游：知识摄取与存储层 | 下游：知识产品化与分发层 |
| **输入** | 任意链接/内容 | 主题 + 结构化知识（可来自 UC） |
| **输出** | 结构化知识资产（卡片） | 可发布的 Skill（SKILL.md + scripts + references） |
| **用户** | 终端知识工作者 | Skill Builder / 开发者 |
| **关系** | UC 的收藏可按 taxonomy 一键导出为 skill-factory 的输入；skill-factory 产出的 Skill 可作为 UC 的「消费端」之一 |

**边界原则**：UC 不做 Skill 打包和发布，只提供「收藏 → 结构化知识」；skill-factory 负责「结构化知识 → 可分发 Skill」。

### 3.3 UC vs 通用 RAG

| 维度 | UC | 通用 RAG（如 Quivr / LangChain RAG） |
|------|-----|-------------------------------------|
| **范围** | 个人知识层：用户主动收藏的内容 | 企业知识库：任意文档集合 |
| **摄取方式** | 主动收藏（低摩擦、高意图） | 批量上传/同步（高摩擦、低筛选） |
| **加工策略** | 结构化元数据 + 分类 + 摘要（理解内容） | 分块 + Embedding（仅检索，不理解） |
| **消费方式** | Agent 注入 / Skill 生成 / 报告输出 / 对话查询 | 问答式检索（Q&A over documents） |
| **数据主权** | 本地优先、开源、开放格式 | 通常云服务、格式封闭 |
| **关系** | UC 可以在底层使用 RAG 技术（向量检索），但 UC 的价值在 RAG 之上 —— 结构化知识资产层 |

**边界原则**：UC 不是「更好的 RAG 工具」，而是「RAG 之上的个人知识操作系统」。RAG 是 UC 的实现细节之一，不是产品定义。

---

## 4. 定位检验清单

以下问题用于检验任何产品决策是否符合 Agent-Native 定位：

| 检验问题 | 如果回答「否」，说明偏离定位 |
|---------|------------------------|
| 这个功能是否让 Agent 更容易消费用户的收藏？ | 可能是 Human-Only 功能 |
| 这个数据格式是否对 Agent 可解析，无需渲染？ | 可能是 Human-Oriented 格式 |
| 这个接口是否支持 Agent 自主查询，而非仅人类点击？ | 可能是传统 UI 思维 |
| 这个流程是否减少了人类的重复劳动，而非增加？ | 可能是伪自动化 |
| 这个决策是否与开放格式/数据主权冲突？ | 可能是封闭花园诱惑 |

---

*Positioning version: v1.0*
*Date: 2026-05-14*
*Next review: after Phase 3 business model validation*
