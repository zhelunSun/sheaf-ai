# Universal Collector / 全局收藏系统

> 从「零散收藏」到「Agent 可用知识资产」的转化基础设施

## 项目定位

这是一个**产品 Idea 的孵化空间**，目标是把「看到好东西 → 收藏 → 吃灰」的断裂流程，变成「收藏 → 自动结构化 → 注入 Agent / 生成 Skill / 输出洞察」的闭环。

## 📋 BP（商业计划书）

- **[BP.md](BP.md)** — 文档版 BP，所有产品文档的输出出口

## 仓库结构

```
universal-collector/
├── BP.md              # 📋 商业计划书（输出出口）
├── PLAN.md            # 项目计划 + 仓库维护方式
├── CHANGELOG.md       # 变更日志
├── AGENTS.md          # Agent 协作指南
│
├── needs/             # 用户调研
│   ├── user-needs.md
│   └── pm-analysis.md
│
├── docs/              # 产品文档
│   ├── positioning-v1.md
│   ├── product-overview.md
│   ├── ecosystem-vision.md
│   ├── opc-operations-harness.md
│   ├── personas-and-scenarios.md   # 用户画像 + 使用场景
│   ├── product-audit.md            # 产品设计审计报告
│   ├── schema-v1.md                # 知识卡片 Schema v1 定义
│   └── agent-query-spec.md         # Agent 查询交互规范
│
├── research/          # 战略研究
│   ├── competitor-deep-dive.md
│   ├── whitespace-analysis.md
│   ├── business-model-v1.md
│   ├── strategy-brief-v1.md
│   └── agent-trend-alignment.md
│
├── scripts/           # 原型代码
│   ├── pipeline.py     # 主管线：fetch → classify → summarize → store
│   ├── fetch_article.py # 文章抓取（3-strategy fallback）
│   ├── llm_client.py   # LLM 客户端（SiliconFlow/XTY 双 provider）
│   ├── mcp_server.py    # MCP Server（6 工具，stdio transport）
│   ├── feedback.py      # 人机纠偏模块
│   └── onboarding.py    # 5 分钟快速体验
│
├── prompts/           # LLM 提示词
│   ├── classify.md      # 分类提示词
│   └── summarize.md     # 摘要提示词（含时效性提取）
│
├── data/              # 运行时数据（gitignored）
└── proposals/         # 早期概念（归档）
```

## 当前阶段

| 阶段 | 状态 | 产出 |
|------|------|------|
| Phase 0: 需求梳理 | ✅ 完成 | `needs/user-needs.md` + `needs/pm-analysis.md` |
| Phase 0.5: MVP 验证 | ✅ 完成 | 4/4 文章端到端跑通 |
| Phase 0.75: 战略研究 | ✅ 完成 | 8 竞品分析 + 定位 + 商业模式 |
| Phase 0.76: 用户画像+审计 | ✅ 完成 | 3 Persona + 审计报告 + 优先级重排 |
| Phase 1: 核心逻辑夯实 | ✅ P0+P1 完成 | Schema v1 + MCP Server + 去重 + 纠偏 + Onboarding |
| Phase 2: 生态联动 | 🔲 | 多源收录 + Skill 联动 |
| Phase 3: 产品化 | 🔲 | Skill 发布 + 多用户 |

## 与现有项目的关系

| 现有项目 | 关系 |
|---------|------|
| `nova-reader/` | **场景互补**。论文精读走 nova-reader，碎片化网络内容走 UC |
| `skill-factory/` | **下游输出**。UC 的结构化知识可打包成可发布 Skill |
| `thesis-exec/` | **用户场景**。博士论文写作是 UC 的核心用户场景之一 |
| `distillation-research/` | **上游技术参考**。内容→知识资产转化策略可复用 |

---

*创建日期：2026-05-13 · 最近更新：2026-05-17*
