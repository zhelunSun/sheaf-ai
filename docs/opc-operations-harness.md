# AI-Native OPC Operations Harness

> Universal Collector 的 AI-Native 运营框架：一人公司（OPC）+ AI Agent  amplification 的完整操作手册。
> 日期：2026-05-14
> 方法论来源：复用 `ai-native-research` 的 harness 模式（phase gate、multi-agent roles、claim-safe、five-day handoff）

---

## 1. AI-Native OPC 定义

**AI-Native One-Person Company（AI-Native OPC）** 不是「一个人用 AI 工具提高效率」，而是：

> **Solo founder 设定方向、规则和验收标准；AI Agents 在明确边界内自主执行具体工作；人类只在决策节点、异常处理和创意判断时介入。**

### 与传统 OPC 的区别

| 维度 | 传统 OPC（Indie Hacker） | AI-Native OPC |
|------|------------------------|---------------|
| 团队规模 | 1 人 | 1 人 + N 个 Agent |
| 工作执行 | 人类手动完成 | Agent 自主完成，人类审核 |
| 内容产出 | 创始人自己写 | Agent 生成，创始人审核调音 |
| 支持响应 | 创始人自己回 | Agent 处理 80%，创始人处理 20% |
| 增长速度 | 线性（受限于创始人时间） | 超线性（Agent 可并行、可 24/7） |
| 瓶颈 |  founder 的时间 |  founder 的决策质量和方向判断 |

### UC 的 AI-Native OPC 特殊性

UC 自身就是 AI-Native 工具，因此它的运营具有**自举性（bootstrapping）**：
- UC 的开发和改进可以由 AI Agent 完成（因为 UC 是代码）
- UC 的内容营销可以由 UC 本身产出的知识资产支撑（dogfooding）
- UC 的用户支持可以由 AI Agent + UC 知识库自动回复

---

## 2. 可自动化的角色分工

基于 `ai-native-research` 的多 Agent 设计，将传统创业公司的 5 个角色映射到 UC 的 OPC 运营中。

### 角色 1：Product / PM（产品经理）

| 职责 | 人类负责 | Agent 负责 | 工具 / Harness |
|------|---------|-----------|---------------|
| 方向设定 | 产品愿景、目标用户、核心价值 | — | `docs/positioning-v1.md` |
| 竞品调研 | 审核 Agent 产出的竞品分析 | 收集信息、结构化分析、输出报告 | Deep Research + Web Search |
| 用户反馈分析 | 判断优先级、决定路线 | 收集 Issue/Discord/社交媒体反馈、分类、汇总情感 | GitHub API + NLP 分析 |
| PRD / 需求文档 | 审核关键决策、签字 | 起草 PRD、用户故事、验收标准 | WorkBuddy + UC 本身 |
| Roadmap 维护 | 战略调整、重大方向变更 | 维护 backlog、更新 milestone、追踪进度 | GitHub Projects + AI 辅助 |

**Agent Prompt 模板**：
```
你是 UC 的产品研究 Agent。本周任务：
1. 扫描 GitHub Issues（open + closed），分类为 bug/feature/question
2. 分析本周 Hacker News/Reddit/V2EX 上关于「bookmark AI」「personal knowledge management」的讨论
3. 输出：用户痛点 TOP 5 + 竞品动态摘要 + 建议的下周优先级
约束：所有结论标注 [SUPPORTED] / [POSITIVE-SIGNAL] / [NOT-VERIFIED]
```

---

### 角色 2：Engineering（工程）

| 职责 | 人类负责 | Agent 负责 | 工具 / Harness |
|------|---------|-----------|---------------|
| 架构决策 | 技术选型、重大重构判断 | — | `docs/architecture.md` |
| Code Review | 审核核心 PR、安全关键代码 | 自动 lint、格式检查、简单 bug 检测 | GitHub Actions + AI review bot |
| 功能实现 | 复杂算法、创新功能原型 | 标准功能开发、模板代码生成、测试编写 | WorkBuddy + Claude/Cursor |
| Bugfix | 判断根因、验证修复 | 定位问题、生成修复、验证回归测试 | GitHub Issues + AI debugger |
| Refactor | 判断重构价值 | 执行标准化重构、更新文档 | AI code editor |
| 测试 | 审核测试覆盖率 | 生成单元测试、集成测试、端到端测试 | Pytest + AI test generator |

**Agent Prompt 模板**：
```
你是 UC 的工程 Agent。本周任务：
1. 从 GitHub Issues 中选取 3 个标记 "good-first-issue" 的 bug
2. 为每个 bug：定位根因 → 生成修复 → 编写回归测试 → 提交 PR（draft）
3. 人类审核后标记为 ready-for-review
约束：不改变公共 API；所有 PR 必须通过现有测试；未确定方案先问人类
```

---

### 角色 3：Content / Marketing（内容与市场）

| 职责 | 人类负责 | Agent 负责 | 工具 / Harness |
|------|---------|-----------|---------------|
| 品牌声音 | 定义调性、关键信息 | — | `docs/brand-voice.md`（待创建） |
| 内容策略 | 主题选择、发布节奏 | 生成内容日历、追踪热点 | UC 收藏 + Trend 分析 |
| 技术博客 | 审核、润色关键文章 | 起草教程、发布说明、案例研究 | UC → Markdown 输出 |
| 社媒运营 | 审核重要发布 | 日常推文/线程生成、回复互动 | Twitter/X API + AI writer |
| Newsletter | 审核每期主旨 | 汇总本周收藏/更新/社区动态，生成 Newsletter | UC 聚合 + AI 编辑 |
| 视频/演示 | 审核脚本 | 生成演示脚本、截图说明 | AI 辅助 |

**Agent Prompt 模板**：
```
你是 UC 的内容营销 Agent。本周任务：
1. 读取 UC 本周的代码变更（git diff）和收藏条目
2. 生成 1 篇技术博客（中文 + 英文版）：主题聚焦本周最有价值的改进
3. 生成 5 条 Twitter/X 线程（技术洞见 + 产品更新 + 社区互动）
4. 生成 1 期 Weekly Newsletter（UC 更新 + 行业趋势 + 精选收藏）
约束：不夸大产品能力；所有技术声明必须有代码或文档支撑；未验证信息标 [CANDIDATE]
```

---

### 角色 4：Support（支持）

| 职责 | 人类负责 | Agent 负责 | 工具 / Harness |
|------|---------|-----------|---------------|
| 复杂问题 | 架构问题、数据恢复、安全报告 | — | 人工介入 |
| FAQ / 文档 | 审核文档准确性 | 自动生成 FAQ、更新文档、回复常见问题 | UC 知识库 + AI 客服 |
| Issue 初筛 | 判断优先级和分类 | 自动回复模板、请求补充信息、标记重复 | GitHub Actions + AI classifier |
| 社区管理 | 处理冲突、维护规则 | 欢迎新成员、引导讨论、汇总周报 | Discord/论坛 bot |

**Agent Prompt 模板**：
```
你是 UC 的支持 Agent。任务：
1. 监控 GitHub Issues 和 Discord，对新增问题在 1 小时内自动回复
2. 如果问题在 FAQ/文档中有答案，直接回复并引用链接
3. 如果是 bug，请求补充信息（复现步骤、环境、日志）并标记 "needs-info"
4. 如果是功能请求，标记 "feature-request" 并汇总到本周反馈报告
5. 如果涉及数据安全/隐私，立即升级给人类
约束：语气友好但专业；不猜测答案；不确定时说「我需要确认一下」
```

---

### 角色 5：Research（研究）

| 职责 | 人类负责 | Agent 负责 | 工具 / Harness |
|------|---------|-----------|---------------|
| 研究方向 | 假设设定、研究问题定义 | — | `ai-native-research` harness |
| Claim 审核 | 判断结论是否过度推断 | 收集证据、结构化分析、标注可信度 | ai-native-research 协议 |
| 文献调研 | 审核关键引用 | 扫描 arXiv/博客/论文、生成综述 | nova-reader + Deep Research |
| 数据分析 | 判断统计方法、解释结果 | 数据清洗、可视化、统计检验 | Python + AI analyst |
| 实验设计 | 假设-验证框架 | 生成实验方案、控制变量设计 | ai-native-research briefs |

**Agent Prompt 模板**：
```
你是 UC 的研究 Agent。本周任务：
1. 扫描 2025-2026 年关于「AI agent memory」「MCP protocol」「personal knowledge management」的最新论文和博客
2. 对每条信息：提取核心 claim → 评估证据强度 → 标注 [SUPPORTED] / [POSITIVE-SIGNAL] / [NOT-VERIFIED]
3. 输出：研究周报（5 条最有价值发现 + 对 UC 的启示）
约束：严格遵循 claim-safe 协议；不将相关当作因果；不将单一样本推广为普遍规律
```

---

## 3. 运营 Workflow 设计

### 3.1 Weekly Agent Sprint（周 Sprint 制）

```
周一 09:00    ├─ Agent 读取 GitHub backlog + 上周未完成任务 + 人类输入的优先级
              ├─ Agent 生成本周任务列表（按角色分组，标注预估工时）
              └─ 人类审核 → 确认/调整/删除 → 锁定本周计划

周一-周五     ├─ Agent 并行执行各自角色的任务
              ├─ 每日 18:00 Agent 提交进度更新（markdown 日志）
              └─ 人类每天花 30-60min 审核进度、回答阻塞问题

周五 18:00    ├─ Agent 汇总本周产出（代码/文档/内容/研究）
              ├─ Agent 生成本周复盘报告（完成度、阻塞项、下周建议）
              └─ 人类审核 → 通过/要求补充 → 标记任务完成

周末         ├─ 人类做战略思考（方向、优先级、重大决策）
              └─ Agent 休息（或执行低优先级背景任务，如数据清理）
```

**关键原则**：
- **人类是瓶颈，不是执行者**：人类每天只花 1-2 小时在 UC 上，其余时间由 Agent 自主推进
- **每日产出必须写入文件**：所有 Agent 的产出必须是 repo 中的 markdown/json/code，不是聊天记录
- **阻塞立即升级**：Agent 遇到不确定的问题（如架构决策、敏感变更），必须在 1 小时内升级给人类，不能猜测

---

### 3.2 Phase Gate 适配（产品开发阶段门）

将 `ai-native-research` 的 Phase Gate 系统适配到 UC 产品开发：

| Phase | 名称 | 人类职责 | Agent 职责 | 验收标准 | 预计周期 |
|-------|------|---------|-----------|---------|---------|
| **P0** | Idea（需求） | 提出需求或审核 Agent 收集的用户反馈 | 汇总反馈、输出 PRD 草稿、竞品对标 | PRD 通过审核，有明确用户价值和验收标准 | 1-3 天 |
| **P0.5** | Design（设计） | 审核技术方案、确认架构影响 | 输出技术设计文档、API 草案、测试策略 | 设计文档通过审核，无重大技术风险 | 1-3 天 |
| **P1** | Implement（实现） | Code review 核心代码 | 开发、测试、文档、自动化检查 | 所有测试通过，代码覆盖率不下降，文档更新 | 3-7 天 |
| **P2** | Release（发布） | 审核发布说明、确认发布时机 | 生成 release note、更新 changelog、打包发布 | GitHub Release 完成，社区通知发送 | 1 天 |
| **P3** | Review（复盘） | 判断用户反馈、决定后续行动 | 收集发布后的用户反馈、bug 报告、使用数据 | 复盘报告完成， lessons learned 记录 | 3-7 天 |

**Gate 规则**：
- 每个 Phase 结束后必须提交 Checkpoint Report（markdown 文件）
- 人类未审核通过，Agent 不得进入下一 Phase
- Agent 可以并行准备下一 Phase 的材料（如 P1 实现时，Agent 可起草 P2 的 release note）

---

### 3.3 Claim-Safe 适配（产品宣称的证据纪律）

`ai-native-research` 的核心教训：**AI Agent 的 instinct 是 over-claim**。UC 的产品运营必须建立证据纪律：

| 场景 | Claim 类型 | 要求 |
|------|-----------|------|
| 技术博客 | 「UC 的摘要质量优于 Readwise」 | 必须有 A/B 测试数据或第三方评测支撑，否则标 [NOT-VERIFIED] |
| 产品页面 | 「Agent-Native 设计让效率提升 50%」 | 必须有用户调研或实验数据，否则改为「我们设计目标是…」 |
| 社媒内容 | 「UC 是市面上唯一的 Agent-Ready 知识工具」 | 必须有竞品矩阵证明，否则改为「在我们调研的 X 个工具中…」 |
| 社区回复 | 「这个功能下周上线」 | 必须有明确的 milestone 支撑，否则改为「我们在规划中，预计…」 |

**Claim-Safe 审核清单**（每次发布前 Agent 自检）：
1. 这篇博客/推文/文档中是否有任何数据没有来源？
2. 是否有将「我们计划做」说成「我们已经做到」？
3. 是否有将「个别用户反馈」推广为「普遍用户需求」？
4. 是否有将「相关」说成「因果」？
5. 未验证信息是否全部标注了 `[CANDIDATE]` / `[NOT-VERIFIED]`？

---

## 4. 工具栈

### 4.1 核心工具栈

| 用途 | 工具 | 角色 | 备注 |
|------|------|------|------|
| **代码托管** | GitHub | Engineering | 代码、Issue、PR、Actions、Release |
| **产品管理** | GitHub Projects + markdown | Product | 轻量级，无需复杂项目管理工具 |
| **AI 执行环境** | WorkBuddy | All | Agent 执行主平台，支持多角色并发 |
| **内容生成** | UC 本身 + Claude/DeepSeek | Content | UC 收藏的素材直接用于内容生产 |
| **研究调研** | ai-native-research harness | Research | 复用论文调研、实验设计、claim-safe 协议 |
| **社区** | Discord / GitHub Discussions | Support | 免费，开发者友好 |

### 4.2 可选扩展工具

| 用途 | 工具 | 触发条件 |
|------|------|---------|
| **文档站点** | VitePress / Docusaurus | 当文档超过 20 页时启用 |
| **分析监控** | Plausible（隐私友好）或自建 | 需要追踪网站流量时启用 |
| **邮件列表** | Buttondown / Revue | Newsletter 订阅 >100 人时启用 |
| **支付** | Stripe / Lemon Squeezy | 启动云服务付费时启用 |
| **云服务** | Vercel + Supabase + Cloudflare R2 | 启动云同步功能时启用 |

### 4.3 与现有项目的协同

| 项目 | 协同方式 |
|------|---------|
| **ai-native-research** | 复用 harness 模式（phase gate、claim-safe、multi-agent）；UC 的研究 Agent 直接调用 ai-native-research 的文献库和实验协议 |
| **skill-factory** | UC 的收藏可一键导出为 skill-factory 输入；skill-factory 产出的 Skill 可作为 UC 的内容营销素材 |
| **nova-reader** | UC 识别论文类收藏 → 路由到 nova-reader 精读；nova-reader 产出回流 UC 作为结构化知识 |
| **ClawHub / WorkBuddy** | UC 作为 Skill 分发；WorkBuddy 作为 Agent 执行平台 |

---

## 5. 人力时间预算

作为 OPC，solo founder 每周在 UC 上的时间分配：

| 活动 | 每周时间 | 说明 |
|------|---------|------|
| **方向与决策** | 3-5h | 审核 Agent 产出、做战略判断、处理异常 |
| **社区互动** | 2-3h | 回复重要 Issue/Discord、参与关键讨论 |
| **代码审核** | 2-4h | Review 核心 PR、做架构决策 |
| **内容润色** | 1-2h | 审核重要博客/发布的品牌调性 |
| **学习与思考** | 2-3h | 阅读行业动态、思考产品方向 |
| **总计** | **10-17h/周** | 约 1.5-2.5 个工作日 |

**Agent 并行能力**：
- 在 human 的 10-17h 之外，Agent 可 24/7 执行：内容生成、文档维护、初级支持、研究调研、测试运行
- 等效人力：约 **3-5 个全职员工**（按传统分工）

---

## 6. 启动 checklist

要在 1 周内建立完整的 AI-Native OPC 运营 harness：

- [ ] 为 5 个角色各创建 1 个 Agent memory 文件（角色定义 + prompt 模板 + 工具权限）
- [ ] 在 GitHub 上设置自动化：Issue 标签、PR template、Release checklist
- [ ] 创建 Weekly Sprint 模板（markdown，每周一 Agent 填充）
- [ ] 创建 Checkpoint Report 模板（markdown，每个 Phase Gate 使用）
- [ ] 设置 Discord 或 GitHub Discussions 作为社区入口
- [ ] 配置 Claim-Safe 自检 prompt（每次发布前 Agent 自动运行）
- [ ] 测试一轮完整 Sprint：从 backlog → 任务分配 → Agent 执行 → 人类审核 → Checkpoint

---

*OPC Operations Harness version: v1.0*
*Date: 2026-05-14*
*Source methodology: ai-native-research harness (phase gate, multi-agent, claim-safe, five-day handoff)*
*Next review: 启动后 1 个月（根据首次 Sprint 经验优化 workflow）*
