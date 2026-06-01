# Sheaf 产品设计文档总索引

> **最后更新**: 2026-06-01 | **维护者**: Jarvis
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
  - `docs/ONE-CLICK-INSTALL-RESEARCH.md` — 竞品安装体验拆解 + 三条路径（Chrome/skill/CLI）
  - `docs/smoke-test-2026-06-01.md` — 空白环境 10/11 冒烟测试
  - GitHub Issue #62 — `sheaf init --auto`

### Phase 4: Matrix — 从收藏到理解（06-01 下午）⭐ 当前
- **心智模型**: "帮我看清事件全貌，不只是收藏"
- **核心叙事**: **"Read one source, understand the whole story."**
- **转折触发**: 收藏一篇 NVIDIA 新闻 → 意识到同一事件有 9 个来源 5 种视角 → Sheaf 应该自动发现这些
- **核心差异**: 所有竞品都是"新闻阅读器"（读完就走），Sheaf 是"知识管道"（读完进 KB）
- **关键文档**:
  - `docs/MATRIX-PRODUCT-DESIGN.md` — 完整产品设计 Brief
  - GitHub Issue #63 — sheaf matrix 技术路线（4 Phase）

---

## 3. 心智模型扩展图

```
Phase 0          Phase 1             Phase 2              Phase 3           Phase 4
收藏工具    →   Agent-Native     →  低摩擦+Agent Context → 一键安装     →  事件理解
"保存文章"     "给Agent用的"        "收藏是入口"          "装完就能用"      "看清全貌"

  collect     →  collect + MCP   →   collect +         →  sheaf init    →  sheaf matrix
                   + crystallize      crystallize +       --auto             (同事件
                                      Agent Context                          多源聚合)
```

**每一次扩展都不是推翻，而是叠加新价值层：**
- Phase 0→1: 从 Human-First 到 Agent-First（数据格式 + 元数据结构化）
- Phase 1→2: 从技术定位到产品叙事（三层价值梯度）
- Phase 2→3: 从功能完整到体验流畅（降低安装摩擦）
- Phase 3→4: 从"保存"到"理解"（同事件跨源聚合 + 知识矩阵）

---

## 4. 文档分类索引

### 📍 活跃文档（正在使用，需维护）

| 文档 | 路径 | 用途 |
|------|------|------|
| 产品演化日志 | `internal/commercialization/PRODUCT-EVOLUTION.md` | 记录每次定位转折的触发事件、决策、理由 |
| 项目计划 | `internal/PLAN.md` | 当前版本、Wave 进度、仓库结构 |
| Matrix 产品设计 | `docs/MATRIX-PRODUCT-DESIGN.md` | Phase 4 的完整产品设计 Brief |
| 一键安装调研 | `docs/ONE-CLICK-INSTALL-RESEARCH.md` | Phase 3 的竞品安装体验分析 |
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
| Obsidian 集成调研 | `docs/OBSIDIAN-INTEGRATION-RESEARCH.md` | 未来集成方向 |

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

*本文档是 Sheaf 产品设计的"北极星索引"——每次产品定位演化后更新此文件。*
