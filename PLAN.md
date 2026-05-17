# Universal Collector — 项目计划

> 产品孵化空间：从零散收藏到 Agent 可用知识资产的转化基础设施

## 仓库双系列结构

本仓库维护两个核心内容系列：

```
universal-collector/
├── 📦 产品文档系列（输入）
│   ├── needs/           — 用户调研、需求分析
│   ├── docs/            — 产品架构、定位、生态愿景
│   ├── research/        — 竞品分析、Whitespace、商业模式、战略简报
│   ├── scripts/         — 旧原型代码（Phase 1 遗留，保留不删）
│   └── data/            — 运行时数据（.gitignore 排除）
│
├── 🐍 uc/ 包（当前代码）
│   ├── __init__.py      — 版本号唯一来源（__version__）
│   ├── config.py        — 共享常量、路径、编码修复
│   ├── utils.py         — URL标准化、内容hash、平台检测
│   ├── storage.py       — 存储与索引管理
│   ├── search.py        — 全文检索（摘要 + raw 原文）
│   ├── query.py         — 查询、统计、趋势分析
│   ├── pipeline.py      — 主流程编排
│   ├── llm_client.py    — 双Provider LLM客户端
│   ├── fetch_article.py — 智能抓取（requests + playwright）
│   ├── feedback.py      — 纠偏反馈
│   ├── gamification.py  — 游戏化引擎（streak + baskets + milestones）
│   ├── onboarding.py    — 首次使用引导
│   ├── mcp_server.py    — MCP stdio server（6 工具）
│   └── cli.py           — CLI 入口（uc <url>, --search, --weekly, --init, --tags, --trends, --urgent）
│
├── 📋 BP 系列（输出出口）
│   ├── BP.md            — 文档版 BP（当前版本）
│   └── (未来) BP.pptx   — PPT 版 BP（Phase 2+ 产出）
│
├── pyproject.toml       — 包配置 + CLI 入口 + ruff 规则
├── PLAN.md              — 本文件：项目计划 + 仓库维护方式
├── CHANGELOG.md         — 变更日志
├── BACKLOG.md           — 待办/Idea/Bug 追踪
└── AGENTS.md            — Agent 协作指南
```

**核心关系**：
- **产品文档系列**是 BP 的素材源（调研、分析、定位、原型验证）
- **BP 系列**是所有产品文档的**输出出口**，面向投资人/合作伙伴/早期用户
- BP 随产品文档更新而迭代，版本同步

## 当前阶段

```
Phase 0:    需求梳理              ✅ 已完成
Phase 0.5:  MVP 验证              ✅ 4/4 文章端到端跑通
Phase 0.75: 战略研究              ✅ 竞品调研+定位+商业模式+OPC运营框架
Phase 0.76: 用户画像+产品审计      ✅ 3 Persona + 审计报告 + 优化建议
Phase 1:    核心逻辑夯实          ✅ P0+P1+BLG 全部完成
Phase 1.5:  工程加固+债务清理      ← 当前（v0.3.1a → v0.4.0）
Phase 2:    生态联动
Phase 3:    产品化/Skill 化
```

**当前版本**：`v0.3.1a`（2026-05-17）
**下一里程碑**：`v0.4.0`（Phase 1.5 完成后发布）

## 技术现状快照

| 指标 | 值 |
|------|-----|
| 包结构 | uc/ 包（13 模块）+ pyproject.toml |
| uc/pipeline.py | ~335 行（编排逻辑） |
| uc/fetch_article.py | ~375 行 |
| uc/storage.py | ~295 行 |
| uc/mcp_server.py | ~290 行 |
| uc/search.py | ~155 行（全文检索 + 相关性评分） |
| uc/query.py | ~200 行 |
| uc/feedback.py | ~175 行 |
| uc/gamification.py | ~230 行（游戏化引擎） |
| uc/onboarding.py | ~145 行（首次引导） |
| uc/llm_client.py | ~112 行 |
| uc/cli.py | ~200 行 |
| uc/config.py | ~57 行 |
| uc/utils.py | ~100 行 |
| 总代码量 | ~2570 行（uc/ 包，不含旧 scripts/） |
| Schema 版本 | v1.1.0 |
| MCP 工具数 | 6（search/list/get/urgent/correct/collect） |
| 依赖 | openai / requests / beautifulsoup4 / playwright |
| CLI 入口 | `uc` (pip install -e .), supports --search/--weekly/--init/--tags/--trends/--urgent/--reclassify |
| Git remote | ❌ 未配置 |
| Python | 3.12.7 |

## 路线图

### Phase 0.5 ✅ MVP 验证
- [x] 微信文章 requests 抓取测试（4/4 成功）
- [x] 四大主题 LLM 自动分类
- [x] 一句摘要 + 结构化要点生成
- [x] Markdown + JSON 本地存储
- [x] index.jsonl 全局索引
- [x] 关键词查询接口
- [x] 文档与 git 版本管理

### Phase 0.76 ✅ 用户画像 + 产品审计（2026-05-16）
- [x] 3 个典型 Persona：博士生 / AI开发者-创始人 / B站-小红书创作者
- [x] 每个 Persona 配具体的一天使用时间线 + 核心痛点 + UC 价值
- [x] 产品设计审计报告（10 个问题，3 个 P0 + 4 个 P1 + 3 个 P2）
- [x] 功能优先级重排：浏览器插件升 P0、新增 Schema 定义 + Onboarding
- [x] 产出：`docs/personas-and-scenarios.md` + `docs/product-audit.md`

**审计关键发现**：
- 收录摩擦过高（3-4 步 vs 竞品 1-click）是冷启动最大障碍 → 浏览器插件升 P0
- Agent-Native 定位未落地（MCP/Embedding/Schema 均未实现）→ MCP Server 是验证锚点
- 缺少知识卡片 Schema 标准定义 → Agent 可消费的前提条件
- 商业模式可行但天花板低，适合 solo lifestyle business，VC 路线需更高叙事

### Phase 0.75 ✅ 战略研究完成（2026-05-14）
- [x] 竞品深度调研：8 个竞品交叉分析（A/B/C 三类）
- [x] Whitespace 分析：2x2 定位图 + Gap 陈述 + 差异化主张 v1
- [x] Agent-Native 定位精炼：五维实践定义 + Elevator Pitch + 边界声明
- [x] 行业趋势对齐：五大趋势（Agentic AI / MCP / Memory Layer / AI-Native Operations / Open Format）
- [x] 商业模式探索：Open-Core 为主 + Skill 市场为辅 + SaaS 后备
- [x] OPC 运营框架：五角色分工 + Weekly Agent Sprint + Phase Gate + Claim-Safe
- [x] 战略简报整合：`research/strategy-brief-v1.md`

**战略结论**：
- 产品定位：左上象限（低摩擦 + 高 Agent 集成）的空白机会
- 商业模式：Open-Core 三步走（开源社区 → Skill 分发 → 云服务增值）
- 运营方式：AI-Native OPC，1 人 + N Agent，Weekly Sprint

### Phase 1 ✅ 核心逻辑夯实（2026-05-16 ~ 2026-05-17）

> Sir 反馈：产品形态不急（浏览器插件/悬浮球是远期），先把核心逻辑搞扎实。Embedding 不是护城河，引入时机是收藏量 50+ 之后。大愿景是 AI 时代个人知识秘书。

**P0 — 核心管线逻辑（先跑通再优化）** ✅ 已完成（2026-05-16）
- [x] **P0-0** 标题提取修复（微信文章 og:title） — 增加 h1/heading fallback + 回填空标题 entry
- [x] **P0-1** 知识卡片 Schema v1 定义 — `docs/schema-v1.md` + pipeline.py 全面升级至 v1 格式
- [x] **P0-2** 时效性识别 — summarize prompt 增强 + `_extract_timeliness()` 自动解析日期 + urgency 判定
- [x] **P0-3** MCP Server 原型 — `scripts/mcp_server.py` stdio transport，6 个工具

**P1 — 体验优化（核心逻辑跑通后）** ✅ 已完成（2026-05-17）
- [x] **P1-0** 人机纠偏反馈回路 — `scripts/feedback.py` + MCP `uc_correct` 工具 + feedback.jsonl 日志
- [x] **P1-1** URL 去重 + 内容相似度去重 — URL 标准化 + content hash + 微信 s= 参数精确匹配
- [x] **P1-2** 首次使用引导（Onboarding） — `scripts/onboarding.py` 3 篇示例 + 查询演示 + 操作指南
- [x] **P1-3** Agent 查询交互规范 — `docs/agent-query-spec.md` 返回格式 + 错误码 + 去重 + 纠偏机制

**BLG 修复** ✅ 全部完成
- [x] **BLG-001** 爬取代码优化 — 平台感知策略 + 提取函数去重 + Playwright 复用
- [x] **BLG-002** 动态标签机制 — 去掉硬分类，改为 topics + tags 双层动态体系
- [x] **BLG-003** 建立变更追踪 — BACKLOG.md + git commit 引用
- [x] **BLG-004** Tencent News 视频播放器噪音清洗 — 20+ 正则模式，HTML+text 双层清理
- [x] **BLG-005** 标签注册表自动归并 — difflib 模糊匹配，阈值 0.85
- [x] **BLG-006** 标签统计分析 — tag_stats() + topic_trends() + CLI --tags/--trends
- [x] **BLG-007** Legacy entry 迁移 + 全量重分类 — schema 统一至 v1.1.0

### Phase 1.5 🔄 工程加固 + 债务清理（v0.3.1a → v0.4.0）

> Phase 1 快速迭代积累了技术债务。进入 Phase 2 之前，先清理干净，确保工程基座扎实。

**TD-P0 — 必须修复（阻塞后续开发）**

- [ ] **TD-01** 配置 Git remote — 当前仓库无远程，无法推送/备份/协作
  - 行动：Sir 在 GitHub 创建 `universal-collector` 仓库后，执行 `git remote add origin`
  - 阻塞：开源/分发/CI 的前提条件

- [ ] **TD-02** 依赖版本锁定 — `requirements.txt` 使用 `>=` 宽约束，存在供应链风险
  - 行动：`pip freeze > requirements-lock.txt`，requirements.txt 改为 `==` 精确版本
  - 或：引入 `pyproject.toml` + `uv` 现代化包管理

**TD-P1 — 应该修复（影响可维护性和可扩展性）**

- [x] **TD-03** pipeline.py 拆分 — 1114 行单文件 → 9 模块 uc/ 包
  - 已完成（2026-05-16）：config / utils / storage / query / pipeline / llm_client / fetch_article / feedback / mcp_server / cli
  - pip install -e . 成功，`uc` CLI 入口可用，所有命令（--version/--tags/--trends/--urgent/无参stats）回归通过
  - 旧 scripts/ 目录保留（harness principle）

- [x] **TD-04** MCP Server 版本同步 — 从 uc.__init__.__version__ 读取，单一来源
  - config.py → `from uc import __version__; VERSION = __version__`
  - mcp_server.py → `from uc.config import VERSION`

- [x] **TD-05** __pycache__ 清理 — 已清理 + .gitignore 已覆盖 build artifacts

- [x] **TD-06** CLI 脚本统一入口 — pyproject.toml `[project.scripts]` uc = uc.cli:main
  - 支持 `uc <url>` / `uc --tags` / `uc --trends` / `uc --urgent` / `uc --reclassify` / `uc --version`

**TD-P2 — 可以改善（不影响功能）**

- [ ] **TD-07** 错误处理统一 — 当前各函数错误处理风格不一致（有的 raise，有的 return None，有的 print+exit）
  - 行动：定义统一异常体系 + 日志策略

- [ ] **TD-08** 测试覆盖 — 当前零测试，纯手动验证
  - 行动：至少覆盖核心路径（collect → classify → store → query）的 smoke test

- [ ] **TD-09** 类型注解 — 函数签名缺少 type hints，不利于 IDE 辅助和静态检查
  - 行动：渐进添加，优先覆盖公开 API

**Phase 1.75 — Glean 游戏化 MVP** ✅ 已完成（2026-05-17）

- [x] **GAME-01** Gamification 引擎核心 — `uc/gamification.py`（streak + baskets + milestones）
- [x] **GAME-02** Pipeline 集成 — 收藏成功后自动更新游戏状态
- [x] **GAME-03** CLI 集成 — stats 底部展示进度

**Phase 1.5 出口条件**（全部满足 → 发版 v0.4.0）：
1. 🔲 Git remote 已配置（需 Sir 创建 GitHub 仓库）
2. ✅ 依赖版本锁定
3. ✅ pipeline.py 拆分完成
4. ✅ 所有现有功能回归通过（collect/query/correct/stats）
5. ✅ 游戏化引擎已集成
6. 🔲 CHANGELOG 更新至 v0.4.0

### Phase 2 — 核心功能补强（v0.4.0 → v0.5.0）

> 敏捷原则：**先补短板，再加长板**。游戏化是长板（差异化），但核心管线还有几个缺口需要先堵上。

**CORE — 核心管线补强（P0，先于一切）**

- [x] **CORE-01** 全文检索增强 — `uc/search.py`（相关性评分 + 原文片段）
  - search_fulltext(): 同时搜摘要 + raw/ 全文，加权评分（title 10x, topic 5x, tag 3x, summary 2x, full-text 1x/count）
  - search_quick(): 快速仅搜 metadata
  - MCP uc_search 升级：支持 deep 参数
  - CLI `uc --search <query>` 新命令
  - 2026-05-17 完成

- [x] **CORE-02** `uc --weekly` 周报命令 — 每周自动总结收集趋势 + 游戏进度
  - 输出：本周收藏数 / 热门主题 / 内容类型分布 / 连续天数 / 篮子进度 / 下一里程碑
  - 技术实现：query.py + gamification.py 组合
  - 2026-05-17 完成

- [x] **CORE-03** Onboarding 适配新包结构 — `uc/onboarding.py`
  - 从 scripts/onboarding.py 迁移至 uc/onboarding.py
  - 使用 `from uc.xxx` 导入
  - CLI `uc --init` 入口
  - 品牌更新为 Glean
  - 2026-05-17 完成

**GROW — 增长引擎（P1，CORE 完成后）**

- [ ] **GROW-01** 游戏化 v2 — 篮子可视化 + 知识洞察推送
  - 跨主题关联发现："你收藏的 AI Agent 和区块链有交叉"
  - 知识回流："3个月前收藏的 X 话题有新进展"（需定期扫描，可选）
- [ ] **GROW-02** 定时报告（WorkBuddy automation 集成）— 每周自动推送周报
- [ ] **GROW-03** 中英文品牌名落地 — pyproject.toml + CLI + README + GitHub repo name

**SCALE — 规模化准备（P2，视数据量触发）**

- [ ] **SCALE-01** 浏览器插件 / 桌面悬浮球 — 降低收录摩擦
- [ ] **SCALE-02** Embedding 语义检索（ChromaDB）— 收藏量 50+ 后引入
- [ ] **SCALE-03** 多上下文/项目隔离
- [ ] **SCALE-04** 下游任务集成 — 编辑器/写作工具的 Agent 知识注入
- [ ] **SCALE-05** nova-reader 论文精读联动

### Phase 2 🔲 生态联动（产品形态完善 + 融资叙事）

**核心目标**：从「个人工具」进化为「个人知识基础设施」，形成可传播、可扩展、可融资的完整产品叙事。

> Phase 2 的启动条件：Phase 1.5 工程加固完成 + Sir 确认战略方向。以下为远景规划，执行时再细化。

#### 2.1 学术知识闭环（nova-reader 对接）— P1

**愿景**：打通「碎片化网络内容 ←→ 深度学术论文」的知识鸿沟。
- UC 识别论文类收藏 → 自动路由到 nova-reader 进行精读
- nova-reader 的精读笔记 → 回流 UC 作为结构化知识资产
- Agent 可以同时检索「快消内容」和「深度论文」，获得「广度 × 深度」的完整知识上下文

**交付物**：
- [ ] nova-reader → UC 数据回流适配器
- [ ] UC 论文自动检测与路由功能
- [ ] 跨知识库统一检索接口

#### 2.2 知识产品化引擎（skill-factory 对接）— P1

**愿景**：用户收藏的知识资产不再「沉睡」，而是转化为可在 ClawHub 生态分发的 Skill。
- 用户收藏的某个主题积累到一定量（如 10+ 条） → 一键生成 Skill 骨架
- Skill 包含：知识卡片集 + Agent 使用说明 + 示例对话
- 用户可在 ClawHub 发布/分享/甚至销售这些 Skill

**交付物**：
- [ ] UC → skill-factory 数据转换协议
- [ ] 一键「收藏主题 → Skill 草案」功能
- [ ] ClawHub 发布集成

#### 2.3 全渠道信息吸收层（多源收录）— P1

**愿景**：用户不需要「粘贴链接」—— UC 主动从用户的信息渠道捕获内容。
- 邮件转发 → 自动收录并分类
- RSS 订阅 → 自动追踪指定博客/期刊
- Twitter / 微博时间线 → 自动抓取含有关键字的推文/链接

**交付物**：
- [ ] 邮件转发收录（Mail → Parse → Classify）
- [ ] RSS 订阅管理（新增/刷新/过滤）
- [ ] Twitter 关键词追踪

#### 2.4 从收藏到洞察（知识图谱与关联推理）— P2

**愿景**：Agent 不仅能检索用户收藏了什么，还能发现「收藏之间的逻辑关系」。
- 自动发现同主题文章的「观点矛盾」
- 自动追踪「趋势演变」
- 自动生成「知识关联图」辅助研究和写作

**交付物**：
- [ ] 轻量知识图谱构建（节点 = 收藏，边 = 共引/共标签/共主题）
- [ ] 观点矛盾检测
- [ ] 趋势演变分析（time-series 标签频率）

#### 2.5 团队协作知识层（可选）— P2

**交付物**：
- [ ] 共享收藏空间 MVP
- [ ] 团队知识图谱
- [ ] 权限管理（私有/团队/公开）

#### 2.6 ClawHub 生态分发 — P2

**交付物**：
- [ ] UC Skill 包装与发布
- [ ] 与其他 Skill 的数据互操作协议

### Phase 3 🔲 产品化
- [ ] 独立 Skill 化发布
- [ ] ClawHub 分发
- [ ] 多用户支持（可选）

## 技术债务追踪

> 来源：Phase 1 快速迭代 + 2026-05-17 全量审计

| ID | 描述 | 优先级 | 状态 | Phase |
|----|------|--------|------|-------|
| TD-01 | 无 Git remote | P0 | 🔲 | 1.5 |
| TD-02 | 依赖版本未锁定 | P0 | ✅ pyproject.toml | 1.5 |
| TD-03 | pipeline.py 拆分 | P1 | ✅ uc/ 9 模块 | 1.5 |
| TD-04 | MCP Server 版本硬编码 | P1 | ✅ 从 __init__ 读取 | 1.5 |
| TD-05 | __pycache__ 残留 | P1 | ✅ 已清理 | 1.5 |
| TD-06 | CLI 缺统一入口 | P1 | ✅ pyproject.toml scripts | 1.5 |
| TD-07 | 错误处理不统一 | P2 | 🔲 | 1.5+ |
| TD-08 | 零测试覆盖 | P2 | 🔲 | 2 |
| TD-09 | 缺少类型注解 | P2 | 🔲 | 2 |

## 功能特性追踪

> Phase 2+ 按敏捷优先级排列（CORE → GROW → SCALE）

| ID | 描述 | 层级 | 状态 | 备注 |
|----|------|------|------|------|
| CORE-01 | 全文检索增强 | CORE | ✅ uc/search.py | 加权评分 + 原文片段 |
| CORE-02 | `uc --weekly` 周报 | CORE | ✅ | query + gamification 组合 |
| CORE-03 | Onboarding 适配新包 | CORE | ✅ uc/onboarding.py | CLI --init 入口 |
| GAME-01 | Gamification 引擎 | CORE | ✅ | streak + baskets + milestones |
| GAME-02 | Pipeline 游戏集成 | CORE | ✅ | 非阻塞式 try/except |
| GAME-03 | CLI 游戏展示 | CORE | ✅ | stats 底部展示进度 |
| GROW-01 | 游戏化 v2（洞察推送） | GROW | 🔲 | 跨主题关联 |
| GROW-02 | 定时报告集成 | GROW | 🔲 | WorkBuddy automation |
| GROW-03 | 品牌名落地 | GROW | 🔲 | pyproject + CLI + README |
| SCALE-01 | 浏览器插件 | SCALE | 🔲 | 降低收录摩擦 |
| SCALE-02 | Embedding 语义检索 | SCALE | 🔲 | 50+ 收藏后引入 |
| SCALE-03 | 多项目隔离 | SCALE | 🔲 | 多上下文支持 |
| SCALE-04 | 下游任务集成 | SCALE | 🔲 | 编辑器/写作工具 |
| SCALE-05 | nova-reader 联动 | SCALE | 🔲 | 论文精读闭环 |

## 已知问题（Known Issues）

| ID | 描述 | 状态 |
|----|------|------|
| BLG-K01 | Windows GBK stdout 静默崩溃 | ✅ 已修复（sys.stdout.reconfigure），但新 CLI 脚本需加 |
| BLG-K02 | WeChat 短文误判为抓取失败 | ⚠️ 确认非 bug，但需更好的日志区分 |

## 当前待决问题

1. ~~**Schema v1 设计**~~ — ✅ 已解决（v1.1.0 动态 topics + content_type）
2. ~~**Agent 查询体验定义**~~ — ✅ 已解决（MCP 6 工具 + agent-query-spec.md）
3. ~~**Phase 1 工程优先级确认**~~ — ✅ 已解决（P0+P1+BLG 全部完成，P2 远期）
4. **Git remote 配置** — 🔲 需 Sir 在 GitHub 创建仓库后手动配置
5. **开源时间决策** — 🔲 何时将 UC 核心代码开源（GitHub public）？
6. **商业模式路线选择** — 🔲 solo lifestyle business vs VC-backable？决定后续产品节奏
7. **Sir 审阅战略简报** — 🔲 `research/strategy-brief-v1.md` 定位/商业模式/OPC 运营是否符合预期？
8. ~~**pipeline.py 拆分方案确认**~~ — ✅ 已完成（9 模块 uc/ 包）
9. ~~**包管理方案选择**~~ — ✅ 已完成（pyproject.toml + setuptools）

## 里程碑时间线

```
v0.1.0  2026-05-13  MVP 跑通
v0.2.0  2026-05-14  战略研究完成
v0.3.0  2026-05-16  爬取v2 + 动态标签 + BLG-001~003
v0.3.1  2026-05-16  噪音清洗 + 标签归并 + BLG-004~006
v0.3.1a 2026-05-17  Legacy迁移 + 全量重分类 + BLG-007 + 技术债务审计
                    ↑ 当前版本
v0.4.0  ???         Phase 1.5 完成（工程加固 + pipeline拆分 + 依赖锁定）
v0.5.0  ???         Phase 2 里程碑（nova-reader/skill-factory 对接 MVP）
v1.0.0  ???         Phase 3 产品化（ClawHub 发布 + 可选多用户）
```
