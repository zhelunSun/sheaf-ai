# Sheaf — Technical Architecture Audit & Roadmap

> **Status**: v0.1.0 技术现状诊断 + 未来架构规划
> **Created**: 2026-05-17

---

## 1. 当前技术流程现状

### 实际 Pipeline（v0.1.0）

```
URL → Fetch全文 → LLM Classify → LLM Summarize → Store → Keyword Search
```

### 存储层详解

每条知识产出 **4 个文件**：

| 文件 | 位置 | 内容 | 格式 |
|------|------|------|------|
| Entry JSON | `data/entries/YYYY-MM/{id}.json` | 完整结构化元数据 | JSON |
| Raw Text | `data/raw/{id}.txt` | **原始全文** | Plain Text |
| Summary MD | `data/summaries/{id}.md` | 人类可读摘要 | Markdown |
| Index | `data/index.jsonl` | 轻量索引（追加行） | JSONL |

**关键发现**：

1. **原始全文是保存的** — `raw/{id}.txt` 存储了 fetch 到的完整原文
2. **摘要 ≠ 全文替代** — Entry 中的 `summary` 和 `structured_summary` 是 LLM 生成的摘要，但 raw 全文也在
3. **没有 Embedding / 向量检索** — 目前搜索是纯关键词匹配（`search.py` 的 `_compute_relevance`）
4. **没有中间层知识卡片** — 直接是 raw text → LLM 摘要 → 存储，缺少结构化知识资产层

### 当前搜索能力

| 能力 | 实现 | 局限 |
|------|------|------|
| 关键词搜索 | ✅ 标题/标签/摘要/全文逐行扫描 | 无语义理解，精确匹配 |
| 标签/主题浏览 | ✅ `--tags`, `--trends` | 标签由 LLM 生成，质量取决于 prompt |
| 紧急事项 | ✅ `--urgent` | 依赖 LLM 提取时效性 |
| 语义搜索 | ❌ 未实现 | 需要 Embedding |
| 向量相似度 | ❌ 未实现 | 需要 Vector DB |
| 跨条目关联 | ❌ 未实现 | `associations` 字段为空 |

---

## 2. 技术差距 vs 理想架构

### 理想的三层架构

```
┌─────────────────────────────────────────────────┐
│            Layer 3: Agent Interface              │
│    MCP Server / CLI / API / Knowledge Packs      │
├─────────────────────────────────────────────────┤
│            Layer 2: Knowledge Card Layer          │
│  结构化知识卡片 ← 论文研究映射                      │
│  可追溯 / 可组合 / 可分享 / 可管理                   │
├─────────────────────────────────────────────────┤
│            Layer 1: Raw Data + Index              │
│  全文 + Embedding 向量 + 关键词索引                │
│  本地存储，用户完全控制                              │
└─────────────────────────────────────────────────┘
```

### 当前 vs 理想差距

| 层 | 当前 | 理想 | 差距 |
|----|------|------|------|
| **Layer 1** | ✅ 全文存储 + 关键词索引 | 全文 + **Embedding 向量** | 缺向量层 |
| **Layer 2** | ❌ 不存在 | **知识卡片中间层** | 核心差距 |
| **Layer 3** | ✅ MCP Server (6 工具) | MCP + **Knowledge Pack 分享** | 缺生态 |

---

## 3. 知识卡片中间层（Knowledge Card Layer）

### 设计灵感：博士论文研究映射

Sheaf 的知识卡片层直接映射 Sir 的博士论文研究——**在原始向量知识和前端 Agent 调用之间建立中间层**：

```
论文中的架构:
  Raw Vectors → [Knowledge Cards (结构化资产)] → Agent Planning

Sheaf 中的架构:
  Raw Text + Embeddings → [Knowledge Cards (可追溯资产)] → Agent Query / Knowledge Packs
```

### 知识卡片定义

每张卡片是 **一条知识的结构化封装**，不是摘要的替代，而是知识的「可流通单元」：

```json
{
  "card_id": "card_2026-05-17_a1b2c3",
  "source_entry_ids": ["2026-05-17_de7d08eb"],
  "title": "Glean 的产品定位与差异化",
  "claim": "Glean 是一家估值 $4.6B 的企业 AI 搜索公司，与个人知识管理赛道不直接竞争",
  "evidence": "基于 2026-05-17 收录的 glean.com 分析",
  "tags": ["竞品分析", "AI搜索", "企业服务"],
  "card_type": "fact|insight|opinion|method|tool",
  "confidence": 0.9,
  "provenance": {
    "source_url": "https://glean.com",
    "collected_at": "2026-05-17T...",
    "raw_text_snippet": "..."
  },
  "associations": ["card_xxx", "card_yyy"],
  "created_at": "2026-05-17T...",
  "updated_at": "2026-05-17T..."
}
```

### 核心特性

| 特性 | 说明 |
|------|------|
| **可追溯** | 每张卡片链接回原始 entry，用户知道「这条知识来自哪里」 |
| **可组合** | 多张卡片可组成 Knowledge Pack |
| **可管理** | 支持纠偏、更新、删除，不会像向量黑洞一样不可见 |
| **可流通** | Knowledge Pack 可以导出、分享、甚至售卖 |

---

## 4. 生态愿景：Knowledge Pack Marketplace

### 核心概念

用户攒的知识按主题组织成 **Sheaf（束）**，每个 Sheaf 是一个 **Knowledge Pack**：

```
用户的收藏
  └── 主题聚类（自动/手动）
        └── Knowledge Pack（一个 Sheaf）
              ├── manifest.json    # 元信息、作者、版本
              ├── cards/           # 知识卡片集合
              └── embeddings/      # 预计算向量（可选）
```

### 生态层级

```
个人层（免费）
  ├── 本地知识库，完全用户控制
  ├── CLI + MCP Server
  └── 本地搜索（关键词 + embedding）

分享层（社区）
  ├── Knowledge Pack 导出/导入
  ├── Sheaf Hub（类似 npm registry）
  ├── 免费分享，open knowledge
  └── README + cards + preview

商业层（未来）
  ├── Token-gated Knowledge Packs
  ├── 付费获取 pack token → 解锁内容
  ├── Web3 集成（NFT / 链上确权）
  └── 创作者经济：知识变现
```

### 与龙虾生态的类比

| 维度 | 龙虾生态 | Sheaf 生态 |
|------|---------|-----------|
| 基本单位 | 技能/工具 | 知识包 |
| 交易物 | 可执行能力 | 可消费知识 |
| 分享机制 | ClawHub marketplace | Sheaf Hub |
| 变现方式 | Skill 售卖 | Knowledge Pack token |
| 协作模式 | 用户贡献 skill | 用户贡献知识束 |

---

## 5. 技术路线图

### Phase 1（当前 v0.1.0）— 基础可用 ✅

- [x] 全文抓取 + 3-strategy fallback
- [x] LLM 分类 + 摘要
- [x] 本地 JSONL + Markdown 存储
- [x] 关键词搜索
- [x] MCP Server（6 工具）
- [x] CLI 工具
- [x] 去重 + 纠偏

### Phase 2 — 向量层 + 知识卡片

- [ ] **Embedding 集成**：每条 entry 自动生成 embedding 向量
- [ ] **向量存储**：本地 FAISS / ChromaDB（用户可选）
- [ ] **语义搜索**：基于向量的相似度检索
- [ ] **知识卡片生成**：从 raw entry → 结构化知识卡片
- [ ] **卡片管理**：查看/编辑/删除/关联卡片
- [ ] **Provenance 追溯**：每张卡片可追溯到原始来源

### Phase 3 — Knowledge Pack + 生态

- [ ] **Knowledge Pack 导出**：选择卡片 → 打包成 .sheaf 文件
- [ ] **Knowledge Pack 导入**：解包 → 合并到本地知识库
- [ ] **Sheaf Hub**：社区分享平台（MVP: GitHub-based）
- [ ] **Pack Manifest**：标准化的 pack 元信息格式
- [ ] **版本管理**：pack 版本更新 + 依赖关系

### Phase 4 — 商业化 + Web3

- [ ] **Token-gated Packs**：付费解锁机制
- [ ] **创作者仪表盘**：下载量、收入、反馈
- [ ] **Web3 集成**：链上确权、NFT 知识包
- [ ] **去中心化存储选项**：IPFS / Arweave 可选

---

## 6. 安全与隐私设计原则

### 核心理念：**Your Knowledge, Your Control**

| 原则 | 实现 |
|------|------|
| **本地优先** | 所有数据默认存储在用户本地 `data/` 目录 |
| **零上传** | 除非用户主动导出/分享，数据不离开本机 |
| **可审计** | 每张知识卡片可追溯到原始 URL + 抓取时间 |
| **可删除** | 用户可随时删除任何 entry / card / pack |
| **可选分享** | Knowledge Pack 的分享是 opt-in，不是默认行为 |
| **加密导出** | 付费 Pack 使用 token 加密，只有持有者可解密 |

---

*This document serves as both a technical audit of v0.1.0 and a strategic roadmap for Sheaf's evolution.*
