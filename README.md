# Universal Collector / 全局收藏系统

> 从「零散收藏」到「Agent 可用知识资产」的转化基础设施

## 项目定位

这是一个**产品 Idea 的孵化空间**，目标是把「看到好东西 → 收藏 → 吃灰」的断裂流程，变成「收藏 → 自动结构化 → 注入 Agent / 生成 Skill / 输出洞察」的闭环。

## 当前阶段

| 阶段 | 状态 | 产出 |
|------|------|------|
| Phase 0: 需求梳理 | **进行中** | `needs/user-needs.md` + `needs/pm-analysis.md` |
| Phase 1: 竞品与方案调研 | 待开始 | 荣耀/Readwise/Omnivore/印象笔记等分析 |
| Phase 2: 最小概念验证 | 待开始 | 选一个场景跑通端到端 |
| Phase 3: 产品化/Skill 化 | 待开始 | 可发布的 Skill 或独立工具 |

## 文件结构

```
universal-collector/
├── README.md                     # 本文件：项目导航
├── needs/
│   ├── user-needs.md             # 用户需求视角（Phase 0-1）
│   └── pm-analysis.md            # 产品经理视角（Phase 0-2）
├── research/
│   └── competitive-analysis.md   # 竞品与现有方案分析
└── proposals/
    └── concept-v0.md             # 产品概念雏形（待共识后撰写）
```

## 与现有项目的关系

| 现有项目 | 关系 |
|---------|------|
| `distillation-research/` | **上游技术参考**。已调研长文本蒸馏策略（Map-Reduce/GraphRAG/分层摘要）， collector 的「内容→知识资产」转化可直接复用 |
| `0inbox/` | **临时收件箱**。目前只存放单次 skill 更新，未来可作为 collector 的原始输入端之一 |
| `nova-reader/` | **场景重叠**。论文精读已有独立工作流，collector 聚焦「非论文类」或「轻量论文」的快速收录 |
| `skill-factory/` | **下游输出**。Collector 产出的结构化知识，可通过 skill-factory 打包成可发布 Skill |
| `thesis-exec/` | **用户场景**。博士论文写作是 collector 的核心用户场景之一 |

## 核心问题（待回答）

1. **边界问题**：collector 和 nova-reader 的边界在哪？论文走 nova-reader，其他走 collector？
2. **开放性问题**：什么叫「比荣耀更 open」？是指数据格式开放、API 开放、还是生态可扩展？
3. **闭环问题**：收藏的终点是什么？是生成一个 Skill？是更新一个知识库？还是产出一份周报？
4. **人机分工**：哪些步骤必须人做（打标签？确认质量？），哪些可以全自动？

---

*创建日期：2026-05-13*
