# BP v0.6 修改清单

> **版本**: v0.5 → v0.6 · **日期**: 2026-05-25 · **Issue**: #24

---

## 修改原则

- 保持所有内容板块完整（市场分析、产品定位、商业模式、团队、融资计划等）
- 不改变事实和数据，只改表达方式
- 目标风格：创业者写给投资人看的 BP，不是 AI 生成的报告

---

## 1. 全局修改

### 1.1 标题和元信息

| 改前 | 改后 | 原因 |
|------|------|------|
| `# Sheaf — Investment Brief` | `# Sheaf — 投资简报` | 中文 BP，标题中文化 |
| `**Product**: Sheaf — Agent-Native Personal Knowledge Layer` | `**产品**: Sheaf — 面向 AI Agent 的个人知识层` | 中文化 |
| `**Status**: Draft` 不变 | 不变 | — |

### 1.2 词汇层替换

以下是全局性替换的高频 AI 词：

| AI 高频词（改前） | 替换为（改后） | 出现次数 |
|------------------|--------------|---------|
| infrastructure layer | 基础设施层 | 5 → 2 |
| paradigm shift | 范式转换 | 1 |
| fundamental question | 核心问题/核心洞察 | 3 |
| critical | 关键/结构性 | 4 → 2 |
| pivotal | —（删除） | 2 → 0 |
| key innovation | 核心创新 | 1 |
| order of magnitude | 大一个数量级 | 1 |
| composable | 可组合 | 1 |
| compound learning | 复合学习 | 1 |
| serves as / stands as | 是/变成 | 3 → 0 |
| showcases | 展示/覆盖 | 1 |
| underscores / highlights | —（删除或简化） | 2 → 0 |
| represents | 变成/是 | 3 |
| testament | —（删除） | 1 → 0 |
| vibrant / rich (figurative) | —（删除或简化） | 2 → 0 |
| profound | —（删除） | 1 → 0 |
| groundbreaking | —（删除） | 1 → 0 |
| Additionally | 此外（删除连接词） | 2 → 0 |
| Moreover | —（删除） | 1 → 0 |
| Crucially | —（删除） | 1 → 0 |
| seamless | —（删除） | 1 → 0 |

### 1.3 语气调整

| 模式 | 改前 | 改后 | 原因 |
|------|------|------|------|
| Negative parallelism | "This is not about building a better bookmark tool. This is about answering a fundamental question..." | "Sheaf 要回答的问题是：..." | 太像 TED 演讲开场 |
| Negative parallelism | "Sheaf is not a better bookmark tool. It's a knowledge infrastructure layer..." | "Sheaf 不是又一个稍后阅读工具。它是一个知识基础设施层..." | 减少 dramatization |
| Self-appointed insight | "**The fundamental insight**: Current knowledge tools solve the wrong problem." | "**核心洞察**：现有工具在优化..." | 降低自大感 |
| Promotional opening | "张一鸣重新定义了信息的传播与获取方式。Jobs 定义了人与科技产品的交互。Sheaf 重新定义..." | "张一鸣重新定义了信息的分发方式。Jobs 重新定义了人机交互。" + 去掉重复句式 | 去掉三连 parallelism |
| Generic positive | "This is the infrastructure layer that makes this possible" | "Sheaf 做的就是这件事" | 去掉空洞膨胀 |

### 1.4 标题格式

| 改前 | 改后 | 原因 |
|------|------|------|
| Title Case 标题（如 "The Problem: Knowledge Is Broken at Every Layer"） | 混合或中文（如 "问题：知识的三个断裂"） | 更自然的中文 BP 风格 |
| 英文标题 | 中文标题（核心部分） | 中文 BP |

---

## 2. 逐段修改详情

### Section 0: Core Thesis

**改前**（代表性段落）：
> This is not about building a better bookmark tool. This is about answering a fundamental question that the AI revolution has created:
> **When AI agents become the primary consumers of knowledge, what does "knowledge" even mean?**
> In the pre-AI era, knowledge was articles, papers, books — designed for human eyes, stored in human formats. In the AI-native era, knowledge must be:
> - **Defined** as structured, machine-readable units with provenance (not blobs of text)
> - **Organized** by semantic relationships and composability (not folder hierarchies)
> - **Traded** as verifiable, ownable, transactable assets (not locked in platform silos)
> Sheaf is the infrastructure layer that makes this possible — from individual knowledge collection to a global knowledge marketplace.

**改后**：
> 张一鸣重新定义了信息的分发方式。Jobs 重新定义了人机交互。
> Sheaf 要回答的问题是：**当 AI agent 成为知识的主要消费者，"知识"本身该是什么形态？**
> 前 AI 时代，知识是文章、论文、书籍——给人看的，存在人的格式里。AI-native 时代，知识需要变成机器可读的结构化单元，带溯源、可组合、可交易。Sheaf 做的就是这件事：从个人知识采集到全球知识市场的基础设施。

**修改原因**：
1. 去掉 "This is not about X. This is about Y." negative parallelism
2. 去掉 "fundamental question that the AI revolution has created"——过度膨胀
3. 去掉 Rule of Three bolded list（Defined/Organized/Traded）——太工整
4. "infrastructure layer that makes this possible"→"Sheaf 做的就是这件事"——简洁直接

### Section 1: The Problem

**改前**（代表性段落）：
> This isn't a discipline problem. It's an **infrastructure problem**. The tools we use to save knowledge were designed for filing, not for thinking. They store links and text, but they don't understand, connect, or activate what you save.
> **The real pain is not "I can't find things."** It's deeper:

**改后**：
> 这不是自律问题，是工具问题。现有的知识存储工具是为归档设计的，不是为思考设计的。它们存链接和文本，但不理解、不连接、不激活你存的东西。

**修改原因**：
1. 去掉 "This isn't X. It's Y." 强调句式
2. 去掉 "**The real pain is not X.** It's deeper:"——过度 dramatization
3. 简化为直接陈述

**表格标题简化**：

| 改前 | 改后 |
|------|------|
| What hurts / Why it hurts / What it costs | 痛点 / 原因 / 代价 |

**末尾段落**：

改前："**The fundamental insight**: Current knowledge tools solve the wrong problem. They optimize for *storage and retrieval* — how to file things so you can find them later. But in an AI-native world, the problem isn't finding information. It's **making your accumulated knowledge computable — so that AI agents can reason over it, connect it, and act on it without you.**"

改后："**核心洞察**：现有工具在优化"存储和检索"——怎么归档、怎么找到。但在 AI 时代，问题不是找到信息，是 **让你积累的知识变得可计算**——让 agent 能推理、连接、自主行动。"

修改：去掉 excessive bold + em dash，简化为创业者语气。

### Section 2: The Solution

**改前**：
> Sheaf is not a better bookmark tool. It's a **knowledge infrastructure layer** that sits between the information you consume and the AI agents you work with.
> **The paradigm shift**: From "save and search" to "save and activate."

**改后**：
> Sheaf 不是又一个稍后阅读工具。它是一个知识基础设施层，放在你消费的信息和你使用的 AI agent 之间。
> **范式转换**：从"存了再找"到"存了就用"。

**修改原因**：
1. "not X, Y"→"不是 X，是 Y"但去掉重复的 "not a better bookmark tool" 句式（Section 0 已用过）
2. "**paradigm shift**"→"范式转换"——中文化

**Competitive comparison table**：

表头全部中文化：Dimension→维度，Designed for→设计目标，Input friction→输入摩擦 等。

**Why Structure Matters 段落**：

改前："The key innovation is not better search. It's **structured knowledge assets**."
改后："核心创新不是更好的搜索，是 **结构化知识资产**。"

改前："Why this matters: When an agent reasons over Knowledge Cards, it can cite sources, detect contradictions across saves, identify patterns you'd miss, and build domain expertise that compounds over time. Raw text and vectors can't do this."
改后："当 agent 基于知识卡片推理时，它可以引用来源、检测矛盾、发现你忽略的模式、积累领域专长。原始文本和向量做不到这些。"

修改：去掉 "Why this matters:" explanatory framing，直接说结论。去掉 "compounds over time" AI 高频词。

**Pipeline 示例**：

改前 Flywheel 段用英文长句，改为短句中文：
"飞轮：创作者用 Sheaf → 产出有价值的 bundle → 买家发现 → 他们也开始用 Sheaf → 变成创作者 → 更多 bundle → 网络效应累积。"

### Section 3: Market Opportunity

**改前**：
> Three converging forces create a window that didn't exist 18 months ago:
> **Force 1: AI Agents are becoming primary knowledge workers.** In 2026, millions of professionals use AI agents (Claude, GPT, Cursor, Copilot) daily. These agents are powerful but **stateless** — every conversation starts from zero. The agent that remembers what you know is an order of magnitude more valuable.

**改后**：
> 三个趋势正在汇合，创造了 18 个月前不存在的窗口：
> 1. **AI agent 正在成为主要的知识工作者。** 2026 年，数百万专业人士每天使用 AI agent。这些 agent 很强，但无状态——每次对话从零开始。记住你知道什么的 agent，价值大一个数量级。

**修改原因**：
1. 去掉 "converging forces"——AI 词汇
2. "Force 1/2/3"→简洁编号
3. 保留 "**stateless**" 因为核心概念需要强调
4. 去掉 "order of magnitude" 的冗余解释

**Competitive Landscape**：

定位图标签全部中文化。空白位置从 "— EMPTY —" 改为 "— 空白 —"。

**Three Structural Gaps**：

表头简化：Gap→缺口，What's missing→现状，Why it matters→影响。

改前："This is the critical missing infrastructure layer for personal AI."
改后："个人 AI 的基础设施缺失"——去掉 promotional tone。

### Section 4: Product Status

**改前**：
> Sheaf has progressed through systematic validation, not just coding:

**改后**：
> Sheaf 通过系统性验证推进，不是闭门造车：

**修改原因**："not just coding" 过于防御性解释，"闭门造车" 更简洁有力。

表头：Stage→阶段，What happened→做了什么，Evidence→产出。

**Wave Roadmap**：

Focus→重点，Key Deliverable→核心交付，Timeline→时间线。

Obsidian 段落：简化说明，去掉 "详见" 前的冗余引用。

### Section 5: Business Model

**改前**：
> Sheaf's value proposition is **"your knowledge, owned by you, usable by any agent."** This philosophy is the product. A SaaS that uploads your knowledge to a cloud server contradicts the core promise.
> Open-Core is not just a pricing strategy — it's an architectural and philosophical alignment:

**改后**：
> Sheaf 的价值主张是"你的知识，你拥有，任何 agent 可用"。这个理念就是产品本身。一个把你的知识上传到云端服务器的 SaaS，和核心承诺矛盾。
> Open-Core 不只是定价策略——是架构和理念的统一：

**修改原因**：
1. 去掉 "philosophical alignment"——过度学术化
2. 去掉 "not just X — it's Y" 句式
3. 保留核心对比但更直接

**China factor**：

改前："**Betting on open-source is betting on asymmetric upside** — minimal downside (the tool is useful even if commercialization fails), massive upside if the ecosystem takes off."

改后："**押注开源就是押注非对称上行**——下行有限（工具本身就有用），上行巨大（生态爆发）。"

修改：去掉括号内过度解释，更简洁。

**Governance section**：

Hugging Face 分析段落：

改前："**Key insight from Hugging Face**: They are a **pure for-profit company** ($20B valuation, ~300 employees, no separate foundation) that has successfully maintained community trust because:"

改后："Hugging Face 是纯营利公司（$20B 估值，约 300 人，没有独立基金会），成功维持了社区信任，因为："

修改：去掉 "Key insight from" 的 self-important framing，去掉 bold 过度使用。

**Unit Economics**：

表头全部中文化。去掉 "Conservative" 括号说明，直接放在标题中。

**Dogfood Bundle**：

改前："The founder's own research domain becomes the first commercial knowledge bundle:"
改后："创始人的研究领域变成第一个商业化知识 bundle："

去掉 "becomes" 的 ceremonial tone。

### Section 6: Team

**改前**：
> **1 founder + N AI agents. Human invests 10-17 hours/week, producing output equivalent to 3-5 FTE.**
> This isn't a theoretical model — it's how Sheaf was built. Every line of code, every product document, every strategic analysis was produced through human-AI collaboration with rigorous phase gates.

**改后**：
> **1 个创始人 + N 个 AI agent。人投入 10-17 小时/周，产出等价于 3-5 个全职。**
> 这不是理论模型——Sheaf 就是这样建出来的。每行代码、每份产品文档、每次战略分析，都通过人机协作完成，配有严格的阶段门控。

**修改原因**：
1. "This isn't X — it's Y" 再次出现，改为更自然的 "这不是 X——X 就是这样做出来的"
2. 保留 Rule of Three 但改为中文短句，节奏不同

**Academic-Product Synergy**：

改前："Sheaf's knowledge card engine shares its theoretical foundation with the founder's PhD research at Tsinghua University — specifically, **evidence-governed knowledge assets for autonomous agents**."

改后："Sheaf 的知识卡片引擎和创始人在清华大学的博士研究共享理论基础——具体说，是 **受证据治理的自主 agent 知识资产**。"

修改：去掉 em dash 的 ceremonial 感觉，改为中文破折号。

"This means:" → "这意味着："——直接。

### Section 7: Vision

**Long-term bet**：

改前："As AI agents become the primary interface for knowledge work, the competitive advantage shifts from "who has the best agent" to "whose agent has the richest domain-specific knowledge." Sheaf is building the infrastructure layer that makes personal knowledge the moat."

改后："随着 AI agent 成为知识工作的主要界面，竞争优势从"谁的 agent 最好"转向"谁的 agent 拥有最丰富的领域知识"。Sheaf 在建的基础设施层，让个人知识成为护城河。"

修改："infrastructure layer that makes X the moat"→"在建的基础设施层，让 X 成为护城河"——更直接。

**Web3 section**：

改前："The knowledge industry's biggest unsolved problem is **intellectual property**."
改后："知识行业最大的未解问题是 **知识产权**。"

改前："Web3 provides natural answers:" → "Web3 提供了天然答案："

去掉所有 "Why Web3 fits Sheaf specifically" 的 excessive sub-header，直接用简短说明句。

**Web3 竞品**：

表头全部中文化。去掉 emoji star（⭐）。

结尾：

改前："This is a **long-term vision**, not an immediate priority."
改后："这是长期愿景，不是当前优先级。"

去掉 bold + 去掉 "immediate priority" 的 AI 措辞。

### Section 8: Risks

表头中文化。内容保持英文但简化 promotional 添加词。

### Section 9: Ask & Next Steps

标题改为 "需求与下一步"。

"Key Decisions" → "已决策"。

去掉所有 "~~" 删除线的冗长回顾，保留决策结果。

**Appendix**：

表格全部中文化。去掉 emoji（✅/⚠️）改为纯文字说明。

---

## 3. 统计

| 指标 | v0.5 | v0.6 | 变化 |
|------|------|------|------|
| 总行数 | 527 | ~460 | -12.5% |
| 英文段落 | ~85% | ~65% | 中文化主要段落 |
| AI 高频词 | ~40 处 | ~5 处 | -87.5% |
| Bold 过度使用 | ~60 处 | ~25 处 | -58% |
| Em dash (—) | ~35 处 | ~15 处 | -57% |
| "This is not X, it's Y" 句式 | 4 处 | 1 处 | -75% |
| Rule of Three | 6 处 | 2 处 | -67% |
| 表格数量 | 18 | 18 | 不变 |
| 代码块数量 | 8 | 8 | 不变 |

---

## 4. 保留不变的部分

- 所有事实、数据、定价、时间线
- 竞品定位图（ASCII art）
- 三层架构图
- 端到端管线代码块
- 产品路线图表格结构
- 所有 Appendix 的内容（只做表头中文化）

---

*BP-CHANGES v0.6 · 2026-05-25 · Issue #24*
