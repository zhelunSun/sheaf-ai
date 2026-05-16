# Universal Collector — Backlog

> 项目待办、Idea、Bug、改进的统一追踪。取代散落对话的零碎记录。
>
> 状态：💡=idea / 🔄=进行中 / ✅=完成 / ❌=放弃
> 优先级：P0=必须 / P1=重要 / P2=nice-to-have

---

## 🔥 P0 — 当前迭代

- ✅ **BLG-001** 爬取代码优化 — 平台感知策略 + 提取函数去重 + Playwright 复用
- ✅ **BLG-002** 动态标签机制 — 去掉硬分类，改为 topics + tags 双层动态体系
- ✅ **BLG-003** 建立变更追踪 — 本项目文件 BACKLOG.md + git commit 引用

## 📋 P1 — 近期待做

- ✅ **BLG-004** Tencent News 视频播放器 debug text 清洗 — 20+ 噪音模式，HTML+text 双层清理
- ✅ **BLG-005** 标签注册表自动归并 — difflib 模糊匹配，阈值 0.85
- ✅ **BLG-006** 标签统计分析 — tag_stats() + topic_trends() + CLI --tags/--trends
- 💡 **BLG-007** 已有 7 条 entry 重新分类 — 用新 topics 机制重新跑一遍 LLM

## 💭 P2 — 远期 Idea

- 💡 **BLG-008** 浏览器插件一键收录
- 💡 **BLG-009** Embedding 语义检索（50+ 收藏后）
- 💡 **BLG-010** nova-reader 论文精读联动
- 💡 **BLG-011** 定时报告（WorkBuddy automation 集成）
- 💡 **BLG-012** 多项目/上下文隔离

## 🐛 Known Issues

- 🐛 **BLG-K01** Windows GBK stdout 静默崩溃 — 已修复（`sys.stdout.reconfigure`），但所有新 CLI 脚本都需加
- 🐛 **BLG-K02** WeChat 短文误判为抓取失败 — 已确认是文章本身短，不是 bug，但需要更好的日志区分

## 已完成（v0.2.0 之前）

- ✅ MVP 端到端跑通（requests + LLM + 存储）
- ✅ Schema v1 定义 + pipeline 升级
- ✅ MCP Server 原型
- ✅ 去重机制（URL + content hash）
- ✅ 人机纠偏反馈回路
- ✅ Windows UTF-8 修复
- ✅ Playwright WeChat fallback
- ✅ 中文输出强制（prompt + system 双层）
