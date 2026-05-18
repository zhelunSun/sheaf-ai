# Sheaf × PhD Thesis — Knowledge Card Dual-Use Synergy Plan

> **Created**: 2026-06-14
> **Author**: Jarvis (for Sir's review)
> **Status**: Draft — awaiting Sir's approval before execution

---

## 1. 核心洞察

> **一句话**：Sheaf 的知识卡片和博士论文的 evidence card 共享同一个理论骨架——**结构化知识资产作为 raw data 和 agent query 之间的可追溯中间层**——但面向不同受众，用不同术语包装。

**共享的是什么**：
- 知识卡片 = 知识的「可流通单元」这个核心抽象
- 每张卡片可追溯到原始来源（provenance）
- 卡片可组合、可管理、可审计
- 卡片是 canonical source，向量/文本片段/图谱都是其 projection

**不同的是什么**：
- 博士论文：面向学术审稿人，强调 evidence governance、claim-level audit、confidence scoring
- Sheaf 产品：面向开发者/创作者，强调低摩擦、自动生成、Knowledge Pack 分享

**花一份时间完成两件事**：底层引擎写一次，两个出口各自包装。

---

## 2. 架构映射

### 2.1 三层架构的对应关系

```
┌──────────────────────────────────────────────────────────────┐
│                    学术论文 (Chapter 1)                        │                    Sheaf 产品                                 │
├──────────────────────────────────────────────────────────────┤
│  Layer 1: Raw RS Data + Vectors                              │  Layer 1: Raw Articles + Embeddings                          │
│  - 遥感影像、光谱数据、LiDAR                                   │  - 全文原文 (data/raw/)                                       │
│  - 文献原文 PDF                                               │  - Embedding vectors (待实现)                                  │
├──────────────────────────────────────────────────────────────┤
│  Layer 2: Knowledge Cards (Evidence-Governed)                │  Layer 2: Knowledge Cards (Shareable)                        │
│  - concept / indicator / data_source / method                │  - fact / insight / opinion / method / tool                  │
│  - 24-field template + claim-level audit                     │  - 轻量 template + auto-generation                            │
│  - card_claims.csv + evidence_registry.csv                   │  - provenance → source_entry_ids                              │
│  - 严格的 confidence + review_status                          │  - confidence (简化版)                                         │
├──────────────────────────────────────────────────────────────┤
│  Layer 3: Agent Planning                                     │  Layer 3: Agent Query + Knowledge Packs                       │
│  - URSA 多智能体规划系统                                       │  - MCP Server + CLI                                           │
│  - 评测：G1-G4 对比实验                                        │  - Knowledge Pack 导出/分享                                    │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心抽象对照表

| 抽象 | 学术论文 (PhD) | Sheaf 产品 | 共享引擎？ |
|------|---------------|-----------|----------|
| **知识单元** | Knowledge Card (asset) | Knowledge Card | ✅ 同一概念 |
| **唯一标识** | `asset_id` (KC-CON-001) | `card_id` (card_2026-05_xxx) | ✅ 同一模式，前缀不同 |
| **来源追溯** | `literature_source` + `evidence_notes` | `provenance.source_url` + `source_entry_ids` | ✅ 同一机制 |
| **证据治理** | `card_claims.csv` + claim-level audit | 简化：`confidence` + `evidence` 字段 | ⚠️ 共享底层，Sheaf 简化暴露面 |
| **类型系统** | concept / indicator / data_source / method | fact / insight / opinion / method / tool | ❌ 不同分类法（领域 vs 通用） |
| **卡片关联** | `related_assets` + `relations.csv` | `associations` (card_id list) | ✅ 同一模式 |
| **质量门控** | 6维 0-8 scoring + strict validator | confidence + auto-generation | ⚠️ 共享验证器框架，Sheaf 用宽松模式 |
| **投影规则** | card → text snippet / vector / graph | card → embedding / summary / pack | ✅ 同一规则 |

---

## 3. 字段级映射

### 3.1 可以直接复用的字段

| 博士论文字段 | Sheaf 字段 | 映射规则 |
|-------------|-----------|---------|
| `asset_id` | `card_id` | 格式不同但语义相同 |
| `name_zh` + `name_en` | `title` | Sheaf 只用单语 title |
| `scientific_meaning` | `claim` | 核心知识声明 |
| `tags` (taxonomy) | `tags` (free-form) | Sheaf 更自由 |
| `evidence_notes` | `evidence` | 来源说明 |
| `related_assets` | `associations` | 卡片间关联 |
| `confidence_level` | `confidence` | Sheaf 用 0-1 浮点数 |
| `review_status` | _(内部，不暴露)_ | Sheaf 简化为 confidence |
| `last_updated` | `updated_at` | 时间戳 |

### 3.2 博士论文独有（Sheaf 不暴露）

| 字段 | 原因 |
|------|------|
| `belonging_task` | RS 领域专属 |
| `spatial_composition` | RS 领域专属 |
| `functional_attribute` | RS 领域专属 |
| `remote_sensing_proxy` | RS 领域专属 |
| `computation_method` | RS 领域专属（Sheaf 的 method 更通用） |
| `spatial_scale` / `temporal_scale` | RS 专属度量 |
| `callable_tools` | RS 工作流专属 |
| `trigger_condition` / `constraint_scope` | Agent planning 专属（Sheaf 的 trigger 机制不同） |
| `verification_basis` | 学术证据治理专属 |
| `evidence_type` | 学术审核链专属 |

### 3.3 Sheaf 独有（博士论文不需要）

| 字段 | 原因 |
|------|------|
| `card_type` (fact/insight/opinion/method/tool) | 通用知识分类 |
| `source_entry_ids` | 关联到 Sheaf entry |
| `provenance.raw_text_snippet` | 产品用户体验 |
| `pack_membership` | Knowledge Pack 生态 |

---

## 4. 代码复用策略

### 4.1 共享引擎层 (`sheaf_cards/`)

抽取一个**纯逻辑层**，不含领域特化：

```python
# sheaf_cards/base.py — 两个出口共享的核心引擎

class KnowledgeCard:
    """Core card abstraction — shared by Sheaf product and PhD thesis."""
    card_id: str
    title: str
    claim: str           # 核心知识声明
    evidence: str        # 来源说明
    tags: list[str]
    confidence: float    # 0.0 - 1.0
    associations: list[str]
    source_ids: list[str]  # 指向原始资料
    provenance: dict
    created_at: str
    updated_at: str

    def validate(self, strict: bool = False) -> list[str]:
        """Validate card. Returns list of issues."""
        ...

    def to_dict(self) -> dict:
        ...

    @classmethod
    def from_dict(cls, data: dict) -> "KnowledgeCard":
        ...


class CardStore:
    """Card storage + retrieval engine — format-agnostic."""
    
    def save(self, card: KnowledgeCard) -> str: ...
    def load(self, card_id: str) -> KnowledgeCard: ...
    def search(self, query: str, limit: int = 10) -> list[KnowledgeCard]: ...
    def delete(self, card_id: str) -> bool: ...
    def link(self, card_a: str, card_b: str, relation: str) -> None: ...


class CardGenerator:
    """LLM-powered card generation from raw text."""
    
    def generate(self, text: str, source_ids: list[str], 
                 card_type: str = "auto") -> list[KnowledgeCard]:
        """Extract knowledge cards from raw text."""
        ...


class CardValidator:
    """Schema + semantic validation for cards."""
    
    def validate_schema(self, card: KnowledgeCard) -> list[str]: ...
    def validate_evidence(self, card: KnowledgeCard, strict: bool = False) -> list[str]: ...
    def validate_links(self, card: KnowledgeCard, store: CardStore) -> list[str]: ...
```

### 4.2 两个出口（各自包装）

```
sheaf_cards/                 # 共享引擎
├── base.py                  # KnowledgeCard, CardStore, CardValidator
├── generator.py             # CardGenerator (LLM card extraction)
├── embeddings.py            # Embedding index (FAISS/ChromaDB)
└── projection.py            # Card → vector / text / graph projections

uc/                          # Sheaf 产品出口
├── card_adapter.py          # KnowledgeCard → Sheaf card_type 映射
├── card_cli.py              # CLI commands for card management
└── pack.py                  # Knowledge Pack export/import

ai-native-research/          # 博士论文出口
├── assets/cards/            # 领域特化 JSON (concept/indicator/data_source/method)
├── config/card_claims.csv   # Claim-level evidence governance
└── scripts/validate_cards.py # Strict academic validator
```

### 4.3 关键复用点

| 模块 | Sheaf 用法 | PhD 用法 | 共享比例 |
|------|-----------|---------|---------|
| `KnowledgeCard` base | 简化 schema（~10 字段） | 扩展 schema（~24 字段） | 核心 100% |
| `CardStore` | JSONL + FAISS | JSON + CSV + JSONL | 80% |
| `CardGenerator` | 自动从文章生成 | 半自动（人审 + AI seed） | 70% |
| `CardValidator` | 宽松模式 | strict 模式 | 90% |
| `projection.py` | → embedding / pack | → vector / graph / ontology | 60% |

---

## 5. 实施计划

### Phase 2A: 共享引擎 + Sheaf Embedding（预计 2-3 天）

**目标**：先为 Sheaf 实现 embedding 层和卡片基础引擎

1. **`sheaf_cards/base.py`** — KnowledgeCard 核心类
   - 定义通用 card schema（10 个核心字段）
   - validate() / to_dict() / from_dict()
   - 支持扩展字段（`extra: dict`），PhD 论文可注入领域字段

2. **`sheaf_cards/embeddings.py`** — Embedding 引擎
   - 支持 SiliconFlow / OpenAI embedding API
   - 本地 FAISS 索引（零依赖安装，纯 numpy fallback）
   - `build_index()` / `search_similar()` / `update_index()`

3. **`uc/embedding_bridge.py`** — Sheaf 接入层
   - 连接 `uc/storage.py` → `sheaf_cards/embeddings.py`
   - 新 entry 自动生成 embedding
   - `sheaf --search-semantic` CLI 命令

4. **`sheaf_cards/generator.py`** — 卡片生成器
   - LLM 从 raw text 提取 knowledge cards
   - 支持自定义 card_type taxonomy
   - Sheaf 用 `fact/insight/opinion/method/tool`
   - PhD 可注入 `concept/indicator/data_source/method`

### Phase 2B: Sheaf 卡片管理（预计 1-2 天）

5. **`uc/card_adapter.py`** — 产品层适配
   - KnowledgeCard → Sheaf 展示格式
   - 卡片 CRUD 命令

6. **`uc/card_cli.py`** — CLI 集成
   - `sheaf --cards` — 查看所有卡片
   - `sheaf --generate-cards` — 为已有 entries 生成卡片
   - `sheaf --card <id>` — 查看单张卡片

### Phase 2C: PhD 论文对接（预计 1 天）

7. **PhD adapter** — 在 `ai-native-research/` 中引用 `sheaf_cards`
   - `knowledge_cards/base.py` → `from sheaf_cards import KnowledgeCard`
   - 扩展字段：`belonging_task`, `spatial_composition`, `remote_sensing_proxy`, etc.
   - 复用 `CardValidator` 在 strict 模式
   - 复用 `CardGenerator` 配合 PhD 特化 prompt

### Phase 2D: 投影规则统一（预计 1 天）

8. **`sheaf_cards/projection.py`** — 投影引擎
   - Card → embedding vector
   - Card → text snippet (for RAG context)
   - Card → graph edge (for relation traversal)
   - 投影元数据记录（source_card_id, projection_rule, version）

---

## 6. 术语映射表（关键！）

Sir 强调"学术研究和产品的口径不一样"。以下是**同一概念在不同场景的说法**：

| 概念 | 学术论文用词 | Sheaf 产品用词 | 备注 |
|------|------------|--------------|------|
| 知识单元 | Knowledge Asset | Knowledge Card | 学术用 "asset" 强调资产属性 |
| 知识声明 | Claim | Claim | 一致 |
| 来源追溯 | Provenance | Provenance | 一致 |
| 证据级别 | Evidence Governance | Confidence | 学术细分类型，产品用数字 |
| 审核状态 | Review Status | _(隐藏)_ | 学术必须显式，产品自动 |
| 类型系统 | asset_type (RS-specific) | card_type (general) | **最大差异** |
| 质量门控 | Audit Protocol | Auto-validation | 学术严格，产品宽松 |
| 投影 | Projection Rule | _(隐式)_ | 学术需显式记录 |
| 卡片集合 | Card Set | Knowledge Pack | 不同包装 |
| 卡片关联 | Relations Graph | Associations | 同义 |
| 去重 | — | Content Hash + URL | 产品特有 |

**写作时的注意**：
- 论文写 "knowledge assets with evidence governance"
- 产品写 "knowledge cards with provenance"
- 不要在论文里用产品术语，也不要在产品里暴露学术审核链

---

## 7. 风险与约束

| 风险 | 缓解 |
|------|------|
| 共享引擎过于抽象导致两个出口都不好用 | 保持核心 <200 行，适配层各 <100 行 |
| PhD 论文需要 strict 模式但 Sheaf 用宽松模式 | `validate(strict=False/True)` 参数控制 |
| Embedding API 成本 | 批量处理 + 缓存 + 仅对 raw text 做 embedding |
| 两个仓库的依赖管理 | `sheaf_cards` 作为 Sheaf 的子包（同一 repo），PhD 引用时 `pip install -e` |
| 学术 vs 产品的术语混用 | 严格遵循第 6 节术语映射表 |

---

## 8. 执行顺序总结

```
Phase 2A (Day 1-3)
  ├── [1] sheaf_cards/base.py — KnowledgeCard 核心类
  ├── [2] sheaf_cards/embeddings.py — Embedding 引擎 + FAISS
  ├── [3] uc/embedding_bridge.py — Sheaf 接入
  └── [4] sheaf_cards/generator.py — LLM 卡片生成器

Phase 2B (Day 3-4)
  ├── [5] uc/card_adapter.py — 产品层适配
  └── [6] uc/card_cli.py — CLI 集成

Phase 2C (Day 5)
  └── [7] ai-native-research adapter — PhD 论文对接

Phase 2D (Day 6)
  └── [8] sheaf_cards/projection.py — 投影规则统一
```

**总预估**：6 天完成共享引擎 + Sheaf 完整卡片层 + PhD 对接

---

## 9. 验收标准

- [ ] `sheaf --search-semantic "xxx"` 返回语义相关结果
- [ ] `sheaf --generate-cards` 从已有 entries 自动生成卡片
- [ ] `sheaf --cards` 列出所有卡片
- [ ] 每张卡片可追溯到原始 entry
- [ ] `sheaf_cards/base.py` < 200 行
- [ ] PhD 仓库可 `from sheaf_cards import KnowledgeCard` 并扩展领域字段
- [ ] 两个出口的术语完全隔离（产品不暴露 audit 链，论文不用产品术语）
- [ ] embedding 构建后搜索质量明显优于 keyword-only

---

*"花一份时间完成两件事" — 底层引擎写一次，学术和产品各自包装出口。*
