# Universal Collector — Backlog

> 项目待办、Idea、Bug、改进的统一追踪。取代散落对话的零碎记录。
>
> 状态：💡=idea / 🔄=进行中 / ✅=完成 / ❌=放弃 / 🏗️=技术债务
> 优先级：P0=必须 / P1=重要 / P2=nice-to-have

---

## 🔥 P0 — 当前迭代（Phase 1.5 工程加固）

- 🏗️ **TD-01** 配置 Git remote — 当前仓库无远程，阻塞推送/备份/协作
- 🏗️ **TD-02** 依赖版本锁定 — requirements.txt 改 `==` 精确版本 或 引入 pyproject.toml + uv

## 📋 P1 — 近期待做

- 🏗️ **TD-03** pipeline.py 拆分 — 1114 行 → 5 模块（orchestrator/query/storage/cli/compat）
- 🏗️ **TD-04** MCP Server 版本同步 — 从单一来源读取版本号，不再硬编码
- 🏗️ **TD-05** __pycache__ 清理 — 残留目录清理 + 确认 .gitignore 覆盖
- 🏗️ **TD-06** CLI 统一入口 — pyproject.toml + `[project.scripts]`，支持 `uc collect/query`

## 💭 P2 — 远期 Idea

- 💡 **BLG-008** 浏览器插件一键收录
- 💡 **BLG-009** Embedding 语义检索（50+ 收藏后）
- 💡 **BLG-010** nova-reader 论文精读联动
- 💡 **BLG-011** 定时报告（WorkBuddy automation 集成）
- 💡 **BLG-012** 多项目/上下文隔离
- 🏗️ **TD-07** 错误处理统一 — 定义统一异常体系 + 日志策略
- 🏗️ **TD-08** 测试覆盖 — 至少核心路径 smoke test
- 🏗️ **TD-09** 类型注解 — 渐进添加，优先覆盖公开 API

## 🐛 Known Issues

- 🐛 **BLG-K01** Windows GBK stdout 静默崩溃 — 已修复（`sys.stdout.reconfigure`），但所有新 CLI 脚本都需加
- 🐛 **BLG-K02** WeChat 短文误判为抓取失败 — 已确认是文章本身短，不是 bug，但需要更好的日志区分

## ✅ 已完成（Phase 1 及之前）

- ✅ **BLG-001** 爬取代码优化 — 平台感知策略 + 提取函数去重 + Playwright 复用
- ✅ **BLG-002** 动态标签机制 — 去掉硬分类，改为 topics + tags 双层动态体系
- ✅ **BLG-003** 建立变更追踪 — BACKLOG.md + git commit 引用
- ✅ **BLG-004** Tencent News 视频播放器 debug text 清洗 — 20+ 噪音模式
- ✅ **BLG-005** 标签注册表自动归并 — difflib 模糊匹配，阈值 0.85
- ✅ **BLG-006** 标签统计分析 — tag_stats() + topic_trends() + CLI
- ✅ **BLG-007** Legacy entry 迁移 + 全量重分类 — schema v1.1.0
- ✅ MVP 端到端跑通（requests + LLM + 存储）
- ✅ Schema v1 定义 + pipeline 升级
- ✅ MCP Server 原型
- ✅ 去重机制（URL + content hash）
- ✅ 人机纠偏反馈回路
- ✅ Windows UTF-8 修复
- ✅ Playwright WeChat fallback
- ✅ 中文输出强制（prompt + system 双层）
