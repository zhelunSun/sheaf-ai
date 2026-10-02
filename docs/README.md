# Sheaf — 公开文档索引

> 产品定位以 [PRODUCT-DESIGN-INDEX.md](PRODUCT-DESIGN-INDEX.md) 为准，功能状态见
> [PRODUCT-FEATURES.md](PRODUCT-FEATURES.md)，推进顺序见
> [NEXT-PHASE-PLAN.md](NEXT-PHASE-PLAN.md)。架构与技术证据边界见
> [ARCHITECTURE-AND-EVALUATION.md](ARCHITECTURE-AND-EVALUATION.md)。
> 其他产品文档可能记录历史探索，不等同于当前路线或已实现承诺。

---

## 文档地图

### 🚀 新用户入门

| 文档 | 内容 | 阅读时间 |
|------|------|----------|
| [mcp-setup.md](mcp-setup.md) | 一键将 Sheaf 接入 AI 编程助手（Cursor/Claude/WorkBuddy/Windsurf） | 2 min |

### 🏗️ 产品设计

| 文档 | 内容 | 目标读者 |
|------|------|----------|
| [PRODUCT-DESIGN-INDEX.md](PRODUCT-DESIGN-INDEX.md) | 个人知识基础设施定位、零额外教学的使用方式、研发取舍与技术证据 | 用户、产品、工程 |
| [PRODUCT-FEATURES.md](PRODUCT-FEATURES.md) | 收藏、筛选、核查与 Agent 复用的功能状态、缺口和验收边界 | 用户、产品、贡献者 |
| [ARCHITECTURE-AND-EVALUATION.md](ARCHITECTURE-AND-EVALUATION.md) | 系统分层、测试阶梯、实验和声明边界 | 工程、研究、贡献者 |
| [ENGINEERING-WORK-MODE.md](ENGINEERING-WORK-MODE.md) | 核心路径的审查、并行、交叉攻击和证据收口方式 | 研发执行、代码审核 |
| [HARDENING-2026-09-22.md](HARDENING-2026-09-22.md) | 生产结晶、跨接口结果、批保存和模拟用户执行安全加固 | 工程、产品、贡献者 |
| [LONG-SOURCE-EXPERIMENT-2026-09-05.md](LONG-SOURCE-EXPERIMENT-2026-09-05.md) | 长来源真实模型诊断、测量修订、失败分母与结论边界 | 工程、研究、贡献者 |
| [MATRIX-PRODUCT-DESIGN.md](MATRIX-PRODUCT-DESIGN.md) | 历史探索：多来源事件理解，不是当前路线 | 历史参考 |

### 🌐 保留的远景探索（未启动交付）

| 文档 | 内容 | 目标读者 |
|------|------|----------|
| [KNOWLEDGE-MARKETPLACE-VISION.md](KNOWLEDGE-MARKETPLACE-VISION.md) | 历史探索：知识授权交易与链上主权，不是近期功能承诺 | 历史参考 |

### 🔧 技术文档

| 文档 | 内容 | 目标读者 |
|------|------|----------|
| [agent-query-spec.md](agent-query-spec.md) | Agent 查询规范 — MCP 工具接口、KnowledgeCard JSON schema | 开发者、Agent 集成方 |

### 📋 项目治理

| 文档 | 内容 | 目标读者 |
|------|------|----------|
| [NEXT-PHASE-PLAN.md](NEXT-PHASE-PLAN.md) | 产品推进：零反馈复用循环、必要质量修复与真实使用验证 | 产品、工程、贡献者 |
| [RELEASE-LIFECYCLE.md](RELEASE-LIFECYCLE.md) | 发布生命周期 — 版本策略、合并门槛、公共契约 | 贡献者、用户 |

### 🎨 其他

| 文件 | 说明 |
|------|------|
| `architecture.svg` | 当前系统边界图（接口、能力、领域、基础设施、质量治理） |

---

## 文档分类速查

```
我要...                              → 看这里
──────────────────────────────────────────────────
了解 Sheaf 是什么 / 为什么存在        → PRODUCT-DESIGN-INDEX.md
看哪些功能已实现 / 还缺什么            → PRODUCT-FEATURES.md
看技术架构 / 评测边界                 → ARCHITECTURE-AND-EVALUATION.md
看下一阶段产品推进                    → NEXT-PHASE-PLAN.md
看过去的 Matrix / 知识市场探索         → 对应历史文档
把 Sheaf 接入我的 AI 助手             → mcp-setup.md
开发 Agent 集成 / MCP 调用           → agent-query-spec.md
了解版本策略 / 发布流程               → RELEASE-LIFECYCLE.md
```

---

## 文档维护规则

1. **前台文档只放面向外部的** — 内部工作档案在 `internal/`
2. **面向投资人的** — 高质量叙事，去 AI 味，人类审阅
3. **面向用户/开发者的** — 清晰准确，可复现
4. **新增 docs/ 文件** — 必须更新本文档索引

---

> 📦 **GitHub** → [zhelunSun/sheaf-ai](https://github.com/zhelunSun/sheaf-ai)
