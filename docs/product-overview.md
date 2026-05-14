# Universal Collector 产品概览

> Agent-Native 的知识收录与转化系统

## 产品定位

**一句话定义**：Universal Collector 是一条「你丢链接 → AI 自动分类摘要 → Agent 可对话查询」的知识转化流水线。

**Elevator Pitch**：现有的收藏工具（荣耀收藏、Readwise、印象笔记）都在解决「怎么把东西存好」。但收藏的真正目的不是「存」，而是「用」。UC 不做一个更好的盒子，它做一个**知识路由器**——收录端低摩擦、加工端全自动、输出端 Agent-Ready。区别于一众 Human-Oriented 的收藏产品，UC 从第一天就为 Agent 消费设计。

## 核心差异化：Agent-Oriented vs Human-Oriented

| 维度 | Human-Oriented（传统） | Agent-Oriented（UC） |
|------|----------------------|---------------------|
| **设计假设** | 用户会打开收藏夹浏览 | 用户会和 Agent 对话 |
| **分类目的** | 帮人眼快速定位 | 帮 Agent 精准检索 |
| **摘要目的** | 帮人快速判断是否读原文 | 帮 Agent 理解内容+回答用户问题 |
| **存储格式** | 富文本/PDF（为人阅读优化） | Markdown/JSON/Embedding（为 Agent 消费优化） |
| **输出形式** | 收藏夹列表 / 阅读流 | Agent 对话 / 结构化报告 / Skill 源码 |
| **交互方式** | 打开 App → 翻分类 → 翻列表 | 直接问："最近关于 RAG 的收藏？" |

## 三层架构

**Layer 1 — 收录层（Ingestion）**
- P0（MVP）：用户手动粘贴微信文章链接
- P1：浏览器插件一键收藏
- P2：微信自动化（RPA/企业微信接口）

**Layer 2 — 加工层（Processing），用户只管丢，AI 负责理**
- 文章抓取：requests → playwright → 用户粘贴正文（三级 fallback）
- LLM 理解（DeepSeek-V3.2，~¥0.3/月）
  - 主题分类：科研 / 市场投资 / AI 产品 / AI 技术
  - 子主题：LLM 自动提取（不预设分类树）
  - 标签：自动提取，支持跨主题关联
  - 摘要：一句话 takeaway + 结构化要点
- 存储：Markdown 原文 + JSON 元数据 + index.jsonl 全局索引

**Layer 3 — 消费层（Consumption），Agent 是交互接口**
- P0：WorkBuddy Agent 对话式检索
- P1：定时报告（自动化）、Embedding 语义检索
- P2：Skill 一键转化、论文联动（nova-reader 插件）

## 交互范式：私人图书馆管理员

```
你：最近我收了哪些关于 RAG 的文章？
Agent：过去 7 天 3 篇...
        需要生成对比摘要吗？检测到 6.15 deadline，要提醒吗？
```

## 非功能约束

| 维度 | 要求 |
|------|------|
| **开放** | Markdown/JSON 格式，数据用户掌控，随时可导出 |
| **本地优先** | 数据存在本地文件系统，无 SaaS 锁定 |
| **成本敏感** | DeepSeek-V3.2 主力，~¥0.3/月 |
| **增量建设** | 从微信文章开始，逐步扩展源和功能 |
| **Agent-Oriented** | Agent 是用户与知识库交互的主要接口 |

---

*版本：v1.0 | 创建：2026-05-13*
