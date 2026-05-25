# Sheaf — Backlog

> ⚠️ **P0 任务已迁移至 GitHub Issues**：https://github.com/zhelunSun/sheaf-ai/issues
> 本文件仅保留 P1/P2 远期 ideas 和 Known Issues，不再管理可执行任务。
>
> 状态：💡=idea / 🔄=进行中 / ✅=完成 / ❌=放弃 / 🏗️=技术债务
> 优先级：P0=必须 / P1=重要 / P2=nice-to-have
> 迁移日期：2026-05-22

---

## 🔥 P0 — 当前迭代（Wave 2 Crystallize）

- ✅ **W2-01** `sheaf_ai/crystallize.py` — 核心：search entries → LLM 提炼 → KnowledgeCard（commit d425da8）
- ✅ **W2-02** `prompts/crystallize.md` — 提炼 prompt（commit d425da8）
- ✅ **W2-03** CLI `sheaf crystallize "topic"` / `--list` / `--show`（commit 07324c6, 97 tests）
- ✅ **W2-04** MCP `sheaf_crystallize` + `sheaf_list_cards`（commit 07324c6）
- ✅ **W2-05** KnowledgeCard → EmbeddingEngine 索引集成（commit cbd0d63, 104 tests）
- ✅ **W2-06** 端到端测试 + 隔离环境搭建
- ✅ **W2-07** `sheaf_ai/renderer.py` — CardOutputConfig + CardRenderer（commit 0c3b9b9, 140 tests）

**Wave 2 出口条件**：
1. ✅ `sheaf crystallize "topic"` 能从 3+ 篇收藏生成知识卡片
2. ✅ 每张卡片有 evidence 追溯
3. ✅ Agent 通过 MCP 可消费卡片内容

> Wave 2 + Wave 2.5 全部完成。当前处于 **Wave 3: Agent Context Server** 阶段。

### Wave 2.5: 游戏化 Lite（✅ 全部完成）
- ✅ **W2.5-01** `sheaf stats` 双维度进度条 + 阈值 10/30/50/100
- ✅ **W2.5-02** Streak 连续签到展示
- ✅ **W2.5-03** 里程碑 Badge + 通知
- ✅ **W2.5-A** 知识卡片引擎核心（sheaf_cards/ 4 文件 ~1000 行，202 tests pass）

### Wave 3: Agent Context Server（🔄 进行中，见 #25）
- ✅ **MVP-EXT-01**: 本地 HTTP API 层（FastAPI 12 端点 + sheaf serve 命令）
- ✅ **MVP-EXT-02**: Chrome Extension 骨架（Manifest V3 + popup + background）
- 🔄 **MVP-EXT-03**: 一键收藏打通（Extension → HTTP API → process_url）— popup 改进 + 快捷键 + API 验证通过
- 🔲 **MVP-EXT-04**: MCP HTTP transport（SSE）
- 🔲 **MVP-EXT-05**: 打包发布

### 排期计划（2026-05-25 更新）

| 优先级 | Issue | 内容 | 计划时间 | 执行方式 |
|--------|-------|------|----------|----------|
| 🔴 P1 | #24 | BP 去 AI 味优化 | 05-25 | ✅ 已完成（commit b889cb5, issue closed） |
| 🔴 P1 | #25 | Wave 3 继续推进 | nightly | 🌙 Nightly Dev Pipeline |
| 🔴 P1 | #18 | Agent 基础设施调研 | 05-26~27 | 🌙 Nightly Dev |
| 🔴 P1 | #19 | Obsidian 融合（调研已完成，闭环） | 05-26 | 🤖 自主闭环 |
| 🔴 P1 | #14 | BP 定稿 | #24 后 | 🤖 自动跟进 |
| 🔴 P1 | #17 | Ch3 样本迁移 | 等 VPN/GEE | 👤 需 Sir 解锁环境 |
| 🔴 P1 | #11 | Ch1 实验设计 | 等 Sir 审查 | 👤 需 Sir 审查 pilot memo |
| 🟡 P2 | #23 | 图片识别 Phase 2 | Alpha 后 | 🌙 Nightly Dev |
| 🟡 P2 | #15 | HSW skill 开源 | 空闲时 | 🤖 批量处理 |
| 🟡 P2 | #13 | LaTeX 学术简历 | 空闲时 | 🤖 批量处理 |
| 🟢 P2 | #22 | 知识市场 | 远期 | 💡 idea 阶段 |
| 🟢 P2 | #20 | App/客户端 | 远期 | 💡 idea 阶段 |

---

## 🔴 P0-UX — 用户不友好风险（✅ P0 全部已修复，P1 待处理）

> 2026-05-22 UX 审计：7 个 P0 已全部修复（#6~#10 closed），剩余 P1 待排期

> 2026-05-22 UX 审计发现，7 个 P0 + 15 个 P1 问题

- ✅ **UX-01** [P0] 首次安装无 API key 引导（#6 closed）
- ✅ **UX-02** [P0] `sheaf collect` 输出原始 JSON（#7 closed）
- ✅ **UX-03** [P0] onboarding 混合中英文（#8 closed）
- ✅ **UX-04** [P0] onboarding 示例全是 arXiv（#9 closed）
- ✅ **UX-12** [P0] `--help` epilog 换行被压缩（#10 closed）
- 🔲 **UX-05** [P1] collect 无进度反馈
- 🔲 **UX-06** [P1] DATA_DIR 基于 cwd
- 🔲 **UX-07** [P1] `--help` 不展示 URL 快捷方式
- ✅ **UX-08** [P1] version 定义两处（已改为 importlib.metadata 单源）
- 🔲 **UX-09** [P1] numpy 在核心依赖
- ✅ **UX-10** [P1] MCP ping 方法（已添加）
- 🔲 **UX-11** [P1] MCP 错误暴露内部细节
- 🔲 **UX-13** [P1] `sheaf init` 结尾命令用旧语法
- 🔲 **UX-14** [P1] MCP tools 列表未包含 crystallize 新工具
- 🐛 **BLG-K04** `ensure_data_dirs()` 定义了但从未调用 → `sheaf init` 存储阶段崩溃
  → ✅ 已修复：`pipeline.py` `process_url()` 开头调用
- 🐛 **BLG-K05** `sheaf init` Category 显示为 `?` — `process_url` 返回的 `category` 字段未设置
  → 待排查

---

## 📋 P1 — 近期待做

- ✅ **W0-03** PyPI 发布（v0.4.0a0 已上线，2026-05-25）
- ✅ **BLG-015** 游戏化 Lite — `sheaf stats` 展示收藏进度条（W2.5-01 已完成，双维度 sheaves+cards 进度条 + 阈值 10/30/50/100）
  - 进度条：收藏总量 / 卡片数量双维度，阈值节点 10/30/50/100
  - Streak：每日有新收藏/新卡片即算，CLI 启动一行展示
  - 里程碑：预设 5-6 个触发条件（首张卡片、覆盖 5 topic、连续 7 天…），触发时 print 通知
  - 零额外存储，纯从现有数据计算
- 🏗️ **TD-07** 错误处理统一 — 统一异常体系 + 日志策略
- 🏗️ **TD-09** 类型注解 — 渐进添加，优先覆盖公开 API

---

## 💭 P2 — 远期 Idea

- 💡 **BLG-014** Sheaf Bundle — `sheaf bundle "topic"` 打包卡片为可交易的 `.sheaf.zip`（→ #22 知识市场）
- 💡 **BLG-011** 定时报告（WorkBuddy automation 集成）
- ✅ **BLG-009** Embedding 语义检索（W2-05 已实现，SiliconFlow embed + numpy cosine）
- ✅ **BLG-008** 浏览器插件一键收录（→ #25 已开 Issue，Wave 3 核心目标）
- 💡 **BLG-012** 多项目/上下文隔离（Wave 4）
- 💡 **BLG-010** nova-reader 论文精读联动（Wave 5）

---

## 📐 软件分层（Architecture Layers）

### Layer 1: Raw Data + Index（✅ 成熟）
- `sheaf_ai/fetch_article.py` — 多策略抓取（requests + Playwright + manual）
- `sheaf_ai/pipeline.py` — process_url 完整流程
- `sheaf_ai/storage.py` — JSON + JSONL 存储
- `sheaf_ai/search.py` — 全文关键词搜索

### Layer 2: Knowledge Card Engine（✅ Wave 2.5 完成）
- `sheaf_cards/base.py` — KnowledgeCard dataclass + CRUD
- `sheaf_cards/generator.py` — LLM 卡片生成（结构化 prompt）
- `sheaf_cards/embeddings.py` — SiliconFlow embed + numpy 余弦相似度
- `sheaf_ai/crystallize.py` — 盘点引擎（find_entries → generate_cards → persist）
- `sheaf_ai/renderer.py` — CardOutputConfig + CardRenderer + Jinja2 模板

### Layer 3: Service Layer（🔄 部分完成）
- `sheaf_ai/cli.py` — CLI argparse（collect/search/crystallize/stats/tags/weekly/insights/urgent/mcp）
- `sheaf_ai/mcp_server.py` — MCP stdio transport（9 tools）
- `sheaf_ai/insights.py` — 跨 topic 关联发现
- `sheaf_ai/feedback.py` — 反馈收集
- `sheaf_ai/gamification.py` — 游戏化（进度条/streak/badge）
- 🔲 **缺失**: HTTP API 层（Wave 3 新增，服务 Extension + Agent）

### Layer 4: Agent Interface（🔄 MCP done, Extension 待开发）
- ✅ MCP Server（9 tools, stdio transport）— Agent 可直接消费
- ✅ CLI（完整命令集）— 人类用户
- 🔲 Chrome/Edge Extension（#25）— 一键收藏
- 🔲 MCP HTTP transport（SSE）— 远程 Agent 接入

---

## 🐛 Known Issues

- 🐛 **BLG-K01** Windows GBK stdout 静默崩溃 — 已修复，但新 CLI 脚本需加 `sys.stdout.reconfigure`
- 🐛 **BLG-K02** WeChat 短文误判为抓取失败 — 确认非 bug，需更好的日志区分
- 🐛 **BLG-K03** Topic 粒度过散 — 8 篇散出 23 个 topic，缺归一化约束（触发条件：收藏 20+ 或 topic/收藏 > 4:1）

---

## ✅ 已完成摘要

Wave 0/1 + Wave 2 + Wave 2.5 全部完成。
核心里程碑：MVP 跑通 → 模块化重构（sheaf_ai/ 15模块）→ 测试套件（202 tests pass）→ Alpha 发布（v0.4.0-alpha, repo public）→ CLI argparse 重构 → 知识卡片引擎（sheaf_cards/ 4 模块 ~1000 行）→ Embedding 语义检索 → Crystallize 盘点引擎 → 游戏化 Lite → P0 UX 修复（6 issues closed）→ 微信双策略抓取 → 图片元数据提取 Phase 1。

**当前版本**: v0.4.0a0 (PyPI published) | **测试**: 257/257 pass | **Git**: main + nightly synced
