# Sheaf 产品设计文档总索引

> **最后更新**: 2026-06-16 | **维护者**: Jarvis
> **目的**: 让产品设计思路可追溯、有逻辑、能沉淀为经验

---

## 1. 心智模型演化 = 产品定位的思路演化

**是的，"心智模型扩展"就是"思路演化"。** 准确地说：

| 术语 | 含义 | 通俗理解 |
|------|------|---------|
| **Mental Model**（心智模型） | 用户脑子里"这个产品是干什么的"认知 | 用户觉得 Sheaf 是什么 |
| **Mental Model Evolution**（心智模型演化） | 产品价值主张的阶段性升级 | Sheaf 从"保存工具"→"理解工具"→"知识基础设施" |
| **Positioning Pivot**（定位转折） | 重新定义产品解决什么问题 | 从"AI知识助手"→"低摩擦收藏+Agent上下文" |

**每一次心智模型扩展，都是一次产品定位的重新校准。** 不是推翻旧定位，而是在旧定位基础上叠加新价值层。

---

## 2. 产品定位演化时间线

### Phase 0: Universal Collector（05-10 ~ 05-13）
- **心智模型**: "更好的收藏工具"
- **核心叙事**: 丢链接 → AI 分类摘要 → 本地知识库
- **文档**: `internal/archive/docs/product-overview.md`

### Phase 1: Agent-Native 定位精炼（05-14 ~ 05-20）
- **心智模型**: "不只是给人看的，是给 Agent 用的"
- **核心叙事**: Agent-Oriented vs Human-Oriented 的五维设计决策
- **转折触发**: 竞品深度调研后发现 Karakeep/Mem0 都在做 Human-First
- **关键文档**:
  - `internal/archive/positioning-v1.md` — Agent-Native 五维定义
  - `internal/archive/research/whitespace-analysis.md` — 2×2 定位图（收藏摩擦 × Agent 集成度）
  - `internal/archive/research/competitor-deep-dive.md` — 8 款竞品交叉分析
  - `internal/archive/ecosystem-vision.md` — 工具→基础设施→生态平台的三阶段路径
  - `internal/archive/research/business-model-v1.md` — Open-Core 商业模式评估

### Phase 2: BP 定位重新校准（05-25）
- **心智模型**: "低摩擦收藏工具 + Agent 上下文基础设施"
- **核心叙事**: 三层价值梯度 — 收藏(入口) → Agent Context(护城河) → 去中心化市场(终局)
- **转折触发**: Sir 准备 BP 展示，调研国内竞品（ima.copilot 最接近）
- **关键决策**: Sheaf 不是知识库、不是笔记软件，收藏是入口、Agent Context 是护城河
- **关键文档**:
  - `internal/commercialization/PRODUCT-EVOLUTION.md` — 产品演化日志（含竞品 ABC 分类框架）
  - `internal/commercialization/bp-presentation-prep.md` — BP 准备
  - `internal/archive/research/agent-trend-alignment.md` — Agent 趋势对齐分析

### Phase 3: 安装体验升级（06-01 上午）
- **心智模型**: "像装 Chrome 插件一样装 Sheaf"
- **核心叙事**: 一行命令，装完就能用。所有成功工具 ≤2 步
- **转折触发**: 意识到 pip install 后还有 3 步摩擦（setup → API key → MCP 注册）
- **关键文档**:
  - `internal/research/one-click-install-research.md` — 竞品安装体验拆解 + 三条路径（Chrome/skill/CLI）
  - `docs/smoke-test-2026-06-01.md` — 空白环境 10/11 冒烟测试
  - GitHub Issue #62 — `sheaf init --auto`

### Phase 4: Matrix — 从收藏到理解（06-01 下午）
- **心智模型**: "帮我看清事件全貌，不只是收藏"
- **核心叙事**: **"Read one source, understand the whole story."**
- **转折触发**: 收藏一篇 NVIDIA 新闻 → 意识到同一事件有 9 个来源 5 种视角 → Sheaf 应该自动发现这些
- **核心差异**: 所有竞品都是"新闻阅读器"（读完就走），Sheaf 是"知识管道"（读完进 KB）
- **关键文档**:
  - `docs/MATRIX-PRODUCT-DESIGN.md` — 完整产品设计 Brief
  - GitHub Issue #63 — sheaf matrix 技术路线（4 Phase）

### Phase 5: Agent 终端记忆层 — Sheaf 不是 Agent，是 Agent 的记忆（06-08）⭐ 当前
- **心智模型**: "Sheaf 不是 Agent，是 Agent 的记忆层"
- **核心叙事**: **三层架构 — 内容层(收藏) → 记忆层(Sheaf) → 终端层(Claude Code/Kimi Work/WorkBuddy)**
- **转折触发**: Kimi Work + WorkBuddy 企业版发布 → Agent 终端大爆发 → 每个终端都缺持久化个人记忆
- **关键洞察**:
  - Claude Code/Kimi Work/WorkBuddy 都在做"帮用户做事"，但都缺"记住用户读过什么"
  - 8 大 Agent 记忆系统 (Mem0/Hindsight/Letta 等) 全部面向开发者，无个人知识产品
  - 国内市场空白：GPT 插件生态已死，大陆无同类竞品
- **核心定位**: Sheaf = `~/.sheaf/` 作为个人知识 home directory，任何 Agent 终端通过 MCP 接入
- **投资人叙事**: "Agent 终端层正在爆发(Kimi Work/WorkBuddy/Claude Code)，但所有终端都缺一个共同的记忆层。Sheaf 就是那个层——本地优先、跨平台、开源。"
- **关键文档**:
  - 本文档 §7 三层架构详述
  - 本对话 (2026-06-08) 完整讨论

### Phase 5.5: Source Intelligence — 消息源信任基础设施（06-12）✅ 已实现 (feat/mcp-v2)
- **心智模型**: "不只是收藏，还要知道谁说的、靠不靠谱"
- **核心叙事**: **给每条收藏打上"谁说的"和"还有谁也说了"两个标签**
- **转折触发**: Sir 收藏两篇文章后追问消息源评分机制 → 发现现有 quality gate 只评内容质量不评来源可信度
- **两大功能**:
  - **消息源评分 (source_score)**: 规则(0-40) + LLM(0-30) + 用户修正 + 新鲜度 → 总分 0-100, tier A/B/C/D
  - **交叉验证 (sheaf_crosscheck)**: 库内多源事实对比，✅确认/⚠️有差异/❌仅本源/❓未提及
- **与 Matrix 的关系**: crosscheck = matrix 的 MVP, source_score = matrix 的信任层
- **技术特点**: LLM 评分在现有 classify 调用中一并完成，不增加 API 成本
- **实现状态**: ✅ 已合并入 main（feat/mcp-v2 全量吸收）;source scoring 在 pipeline Step 3.5 生效,`sheaf_crosscheck` 经 CLI / `tools/call` 可用。#67 联网验证为独立项,不阻塞已发布版本。
- **关键文档**:
  - `docs/SOURCE-INTELLIGENCE-DESIGN.md` — 完整设计文档(Beta 草案)
  - `internal/design/MCP-V2-PLAN.md` — MCP v2 架构计划

### Phase 5.6: MemTensor 调研后的定位再确认（06-16）
- **调研结论**: MemOS 给 AI 装记忆，Sheaf 给人装外脑 — **互补而非竞争**
- **3 条建议**: 🔴 Extension 升级为知识注入助手 / 🟡 Card schema 对齐 MemOS / 🟢 agent-legion 借鉴 MemScheduler
- **不影响 Phase 5 三层架构叙事**

---

## 3. 心智模型扩展图

```
Phase 0          Phase 1             Phase 2              Phase 3           Phase 4           Phase 5           Phase 5.5
收藏工具    →   Agent-Native     →  低摩擦+Agent Context → 一键安装     →  事件理解      →  Agent 记忆层   →  消息源信任
"保存文章"     "给Agent用的"        "收藏是入口"          "装完就能用"      "看清全貌"        "所有Agent的记忆"  "谁说的+还有谁说了"

  collect     →  collect + MCP   →   collect +         →  sheaf init    →  sheaf matrix  →  ~/.sheaf/      →  source_score
                   + crystallize      crystallize +       --auto             (同事件          三层架构：          + crosscheck
                                      Agent Context                          多源聚合)         内容→记忆→终端
```

**每一次扩展都不是推翻，而是叠加新价值层：**
- Phase 0→1: 从 Human-First 到 Agent-First（数据格式 + 元数据结构化）
- Phase 1→2: 从技术定位到产品叙事（三层价值梯度）
- Phase 2→3: 从功能完整到体验流畅（降低安装摩擦）
- Phase 3→4: 从"保存"到"理解"（同事件跨源聚合 + 知识矩阵）
- Phase 4→5: 从独立产品到生态基础设施（Agent 终端的记忆层）
- Phase 5→5.5: 从"记住什么"到"判断谁靠谱"（消息源信任基础设施）

---

## 4. 文档分类索引

### 📍 活跃文档（正在使用，需维护）

| 文档 | 路径 | 用途 |
|------|------|------|
| 产品演化日志 | `internal/commercialization/PRODUCT-EVOLUTION.md` | 记录每次定位转折的触发事件、决策、理由 |
| 项目计划 | `internal/PLAN.md` | 当前版本、Wave 进度、仓库结构 |
| Matrix 产品设计 | `docs/MATRIX-PRODUCT-DESIGN.md` | Phase 4 的完整产品设计 Brief |
| 一键安装调研 | `internal/research/one-click-install-research.md` | Phase 3 的竞品安装体验分析 |
| 冒烟测试报告 | `docs/smoke-test-2026-06-01.md` | v0.4.0a0 空白环境验证 |
| 商业化路线 | `internal/commercialization/commercialization-roadmap.md` | 变现路径 |
| 资金机会 | `internal/commercialization/funding-opportunities.md` | 孵化器/基金申请追踪 |

### 📍 归档文档（历史参考，不再更新）

| 文档 | 路径 | 历史价值 |
|------|------|---------|
| 产品概览 v1 | `internal/archive/docs/product-overview.md` | Phase 0 的原始定位 |
| Agent-Native 定义 | `internal/archive/positioning-v1.md` | Phase 1 五维度定义（仍适用） |
| 竞品深度分析 | `internal/archive/research/competitor-deep-dive.md` | 8 款竞品（Karakeep/Mem0 等） |
| 空白地带分析 | `internal/archive/research/whitespace-analysis.md` | 2×2 定位图（仍适用） |
| 商业模式 v1 | `internal/archive/research/business-model-v1.md` | Open-Core 评估（仍适用） |
| 生态愿景 | `internal/archive/ecosystem-vision.md` | 三阶段路径（工具→基础设施→生态） |
| 知识市场愿景 | `docs/KNOWLEDGE-MARKETPLACE-VISION.md` | 中远期 Web3 知识交易（Phase 5+） |
| Obsidian 集成调研 | `internal/research/obsidian-integration-research.md` | 未来集成方向 |

### 📍 GitHub Issues（产品功能追踪）

| Issue | 标题 | Milestone | 状态 |
|-------|------|-----------|------|
| #40 | uvx 一键部署 | v0.5.0 | ✅ Closed |
| #62 | sheaf init --auto (一键安装) | v0.5.0 | Open (P1) |
| #63 | sheaf matrix (跨源事件验证) | v0.5.0 | Open (P1) |
| #22 | Knowledge Marketplace | Backlog | Open |

---

## 5. 产品设计经验沉淀

> 以下是从 4 次 Phase 演化中提炼的可复用经验

### EXP-001: 定位转折的触发信号
- **信号 1**: 竞品调研发现"别人已经在做了" → 需要重新差异化
- **信号 2**: 用户（自己）真实使用中发现"缺了什么" → 需要扩展功能
- **信号 3**: 安装/使用时出现摩擦 → 需要降低门槛
- **信号 4**: 某次使用中突然发现新价值场景 → 需要产品化

### EXP-002: 心智模型扩展三原则
1. **叠加不推翻**: 每次扩展在旧定位上叠加，不是重新来过
2. **用户行为驱动**: 新价值层必须从真实用户行为中发现，不能凭空想象
3. **故事一句话**: 每个新心智模型必须能在一句话内说清楚

### EXP-003: 产品设计文档分层
```
顶层: PRODUCT-EVOLUTION.md（演化日志，append-only）
  ↑ 更新
中层: 各 Phase 的详细设计文档（MATRIX-PRODUCT-DESIGN, ONE-CLICK-INSTALL 等）
  ↑ 引用
底层: 竞品调研、技术调研（archive/research/）
```

### EXP-004: 竞品分析框架
- **2×2 定位图**: 找到"无人占据的空白地带"（参见 whitespace-analysis.md）
- **ABC 分类**: A(大厂/强竞品) / B(中等/部分重叠) / C(弱/可借鉴)
- **安装体验计数**: 每个竞品从 0 到可用需要几步

---

## 6. 下一步: Phase 4 (Matrix) 的产品设计待办

| # | 待办 | 优先级 |
|---|------|--------|
| 1 | Matrix 的 Golden Path 用户旅程图（3 步即可） | P1 |
| 2 | 矩阵视角分类标准（官方/技术/金融/竞争/国际）的精确定义 | P1 |
| 3 | "Read one source, understand the whole story" 的英文 Landing Page 文案 | P2 |
| 4 | matrix → crystallize 的自动触发门槛（同事件≥3 篇？） | P1 |
| 5 | Matrix 的 Ground News 对位宣传素材 | P2 |

---

## 7. 三层架构：投资人叙事（Phase 5 核心）

### 一句话 pitch

> **Agent 终端层正在爆发，但所有终端都缺一个共同的记忆层。Sheaf 就是那个层——本地优先、跨平台、开源。**

### 三层模型

```
┌──────────────────────────────────────────────────────┐
│  终端层：帮用户"做事"的 Agent                          │
│  Claude Code │ Kimi Work │ WorkBuddy │ Codex │ 更多   │
│  "写代码"     "办公"      "企业协作"   "编程"          │
│                                                      │
│  ⚠️ 共同短板：没有跨会话持久化记忆                     │
│  Claude Code /clear = 清空对话 → 之前的推理全丢        │
│  Kimi Work 技能包 = 任务模板，不是个人知识              │
│  WorkBuddy 团队上下文 = 组织级，非个人级                 │
├──────────────────────────────────────────────────────┤
│  记忆层：Sheaf — 个人知识基础设施                       │
│  收藏 ▸ 索引 ▸ 结晶 ▸ 检索 ▸ 关联                      │
│  ~/.sheaf/ = 个人知识 home directory                  │
│                                                      │
│  ✅ 任何 Agent 终端通过 MCP 接入                        │
│  ✅ 本地优先，隐私可控                                  │
│  ✅ 跨平台（Linux/Mac/Windows）                         │
│  ✅ 知识卡片自动结晶                                    │
├──────────────────────────────────────────────────────┤
│  内容层：用户阅读的一切                                 │
│  网页 │ 微信 │ arXiv │ PDF │ 笔记 │ GitHub │ 更多      │
│  Chrome 插件一键收藏                                    │
└──────────────────────────────────────────────────────┘
```

### 为什么安全：竞品空白

| 层次 | 竞品 | 为何不冲突 |
|------|------|-----------|
| **Agent 记忆系统** | Mem0, Hindsight, Letta, Zep 等 8 个 | 全部面向**开发者**（SDK/API），非个人终端用户 |
| **个人知识产品** | Cubox, Readwise, MyMemo 等 | 停留在**内容存储**阶段，无知识结晶/Agent 集成 |
| **GPT 生态** | ChatGPT Memory (Dreaming V3) | **对话记忆**，非阅读收藏的知识图谱；GPT Plugins 已死 |
| **大厂 Agent 终端** | Kimi Work, WorkBuddy | 做 Agent 终端，不做 Agent 的记忆层 |

**关键数据点**：
- 8 大 Agent 记忆系统全部是面向开发者 SDK，无一面向个人用户
- ChatGPT Plugins 已于 2024 年停止运营，GPTs 替代品无个人知识管理品类
- 国内市场：大陆尚无同类本地优先 + 跨平台 + Agent 可接入的个人知识层产品

### 投资人三板斧

1. **市场时机**: Agent 终端大爆发（Kimi Work/WorkBuddy/Claude Code），每个用户需要一个跨终端的记忆 → Sheaf 正好填这个缺
2. **护城河**: 本地优先 + 跨平台 + 开源 → 大厂不会做（太小太底层），小厂做不了（需要 Agent 生态理解）
3. **增长飞轮**: 每多一个 Agent 终端接入 MCP → Sheaf 的价值翻倍 → 更多终端接入

### 竞争者可能出现的信号
- 有公司做"ChatGPT 个人记忆插件"（但国内没人做）
- Mem0 推出面向终端用户的产品（目前仅 SDK）
- 某个 Agent 终端内置了自己的记忆系统（但用户会被锁定在一个终端）

Sheaf 的先发窗口：在这些信号出现前，完成**三层架构的产品化 + 社区认知建立**。

---

*本文档是 Sheaf 产品设计的"北极星索引"——每次产品定位演化后更新此文件。*
*Phase 5 新增 (2026-06-08): 三层架构 + 投资人叙事*
