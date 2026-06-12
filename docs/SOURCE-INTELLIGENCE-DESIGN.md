# Sheaf Source Intelligence — v0.6.1 Beta 功能设计

> **版本**: v0.1 Draft | **日期**: 2026-06-12
> **作者**: Jarvis (参谋长) | **审阅**: Sir
> **分支**: `feat/mcp-v2` (从 main v0.6.0 切出)
> **定位**: Phase 4 Matrix 的前置能力，Phase 5 记忆层的信任基础设施

---

## 0. 一句话

> **给每条收藏打上"谁说的"和"还有谁也说了"两个标签。**

消息源评分回答「这个来源靠谱吗」，交叉验证回答「这件事还有谁在说」。

---

## 1. 产品定位：为什么是这两个功能

### 1.1 在 Sheaf 心智模型演化中的位置

```
Phase 3: 一键安装     → Phase 4: 事件理解     → Phase 5: Agent 记忆层
                          ↑ 我们在这里
                     Matrix 的核心问题：
                     "我看到的这个故事是真的吗？"
                     "还有谁在报道同一件事？"

Source Intelligence = Matrix 的信任基础设施
  - 消息源评分 = 每个"谁在说"的可信度量化
  - 交叉验证 = "还有谁在说"的自动发现
```

**关键洞察**: Matrix 的 `sheaf matrix` 已经设计了跨源事件聚合，但缺少两个底层能力：
1. **来源可信度** — 目前不管量子位还是个人博客，quality_tier 一视同仁
2. **事实交叉** — 目前只搜库内，不自动对比事实差异

这两个不是独立功能，而是 **Matrix 的信任层**。

### 1.2 用户场景

```
场景 1: Sir 收藏了一篇微信公众号文章
  → Sheaf 自动评估: 来源=津津乐道播客(非一手), 可信度=B
  → 提示: "此消息源为二手报道。发现 3 篇一手来源，运行 sheaf crosscheck 查看"

场景 2: Sir 想验证某个论点
  → sheaf crosscheck "端侧算力可分担20% Token" --entry 2026-06-11_b7b26bac
  → 搜索库内 + 外部(arXiv/Scholar)同主题文章
  → 输出: 5 篇相关报道的事实对比矩阵
  → 标注: 该数据仅见于本消息源，未见其他报道 (confidence: 低)

场景 3: 批量收藏后的来源概览
  → sheaf list --sort source_score
  → 看到哪些收藏来自高可信来源，哪些来自低可信来源
```

---

## 2. 功能 A: 消息源评分 (Source Credibility Score)

### 2.1 设计原则

**混合打分，不用纯 Prompt**。原因：
- Prompt 打分不可复现（同一文章两次打分可能不同）
- 纯规则太死板（新来源无法自动评估）
- 混合方案 = 规则基础分 + LLM 增量分 + 用户修正

### 2.2 评分模型

```
source_score = rule_base(0-40) + llm_bonus(0-30) + user_bonus(-20~+20) + freshness(0-10)

总分 0-100，映射到 tiers:
  A (≥75): 高可信 — 官方信源、学术论文、权威媒体
  B (50-74): 中可信 — 行业媒体、知名博主、专业社区
  C (25-49): 低可信 — 个人博客、未认证账号、转载无出处
  D (<25): 不可信 — 内容农场、AI 批量生成、已知虚假信源
```

### 2.3 规则基础分 (rule_base, 0-40)

| 维度 | 规则 | 分值 |
|------|------|------|
| **域名权威度** | URL 匹配预定义权威域名表 | 0-15 |
| | `*.edu.cn`, `arxiv.org`, `nature.com` → 15 | |
| | `mp.weixin.qq.com` (公众号) → 8 | |
| | `zhihu.com`, `medium.com` → 5 | |
| | 未知域名 → 0 | |
| **一手/二手判断** | 文本中含"据 XX 报道"/"转自" → 二手 | -5 |
| | 文本中含原始数据/实验结果 → 一手 | +5 |
| **作者识别** | 有明确署名 → +3 | |
| | 有机构背景 → +5 | |
| | 匿名/无署名 → 0 | |
| **引用质量** | 文中包含 DOI/arXiv/可验证链接 → +5 | |
| | 无任何引用 → 0 | |

### 2.4 LLM 增量分 (llm_bonus, 0-30)

在现有 `classify.md` prompt 中**新增一个字段**：

```json
{
  "source_assessment": {
    "is_primary_source": true/false,
    "has_verifiable_claims": true/false,
    "domain_expertise": "high/medium/low",
    "reasoning": "一句话判断理由"
  }
}
```

映射到分数：
- `is_primary_source=true` → +10
- `has_verifiable_claims=true` → +10
- `domain_expertise=high` → +10

**关键**: LLM 评分和分类在同一次调用中完成，不增加 API 成本。

### 2.5 用户修正 (user_bonus)

```python
# 通过 sheaf_correct 机制
sheaf_correct(entry_id, corrections={
    "source_score_override": 85,  # 用户手动调整
    "source_note": "这是某教授的官方博客"
})
```

用户修正会写入 `source_registry.json`（域名级缓存），下次同域名自动应用。

### 2.6 新鲜度 (freshness, 0-10)

```python
# 发布时间越近，新鲜度越高（仅用于新闻类内容）
if content_type == "news":
    freshness = max(0, 10 - days_since_publish / 3)
else:
    freshness = 5  # 非新闻默认中等
```

### 2.7 存储变更

```python
# Entry 新增字段
entry = {
    ...existing_fields...,
    "source": {
        "domain": "mp.weixin.qq.com",
        "author": "津津乐道播客",
        "score": 58,           # 总分 0-100
        "tier": "B",           # A/B/C/D
        "is_primary": false,   # 是否一手信源
        "rule_score": 28,      # 规则基础分
        "llm_score": 20,       # LLM 增量分
        "user_override": null, # 用户修正
        "freshness": 8,        # 新鲜度
    }
}
```

---

## 3. 功能 B: 交叉验证 (Cross-Check)

### 3.1 定位

**`sheaf_crosscheck` 是 `sheaf_matrix` 的轻量版**。

| | matrix | crosscheck |
|---|--------|-----------|
| 触发 | 用户主动 `sheaf matrix` | 自动提示 + 手动触发 |
| 范围 | 外部搜索 + 库内聚合 | 库内优先 + 可选外部 |
| 输出 | 完整事件矩阵 | 事实对比摘要 |
| 成本 | 高（多轮外部搜索） | 低（库内搜索 + 1 次 LLM） |

### 3.2 MCP 工具定义

```python
{
    "name": "sheaf_crosscheck",
    "description": (
        "Cross-verify claims from an entry against other sources in the knowledge base.\n"
        "\n"
        "Given an entry_id and optional focus topic, search for related entries "
        "and generate a fact comparison matrix.\n"
        "\n"
        "Use when:\n"
        "- User wants to verify a claim: '这个说法有其他来源支持吗？'\n"
        "- User wants to see different perspectives: '其他人怎么看这件事？'\n"
        "- After collecting an article with low source_score\n"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "string",
                "description": "Entry ID to cross-check"
            },
            "focus": {
                "type": "string",
                "description": "Optional specific claim/topic to verify"
            },
            "scope": {
                "type": "string",
                "enum": ["internal", "external", "both"],
                "default": "internal",
                "description": "Search scope: internal (KB only), external (web), or both"
            },
            "top_k": {
                "type": "integer",
                "default": 5,
                "description": "Max related entries to compare"
            }
        },
        "required": ["entry_id"]
    }
}
```

### 3.3 交叉验证流水线

```
输入: entry_id + focus(可选) + scope(internal/external/both)

Step 1: 提取锚点
  → 从 entry 提取 key_claims (通过现有 tags + summary)
  → 如有 focus 参数，仅提取 focus 相关 claims

Step 2: 检索相关条目
  → [internal] sheaf_search(key_claims) → top_k 相关条目
  → [external] 如果 scope=external/both:
     → arxiv API 搜索 (如果是学术内容)
     → 或 web search (通用内容)
  → 过滤: 排除同源条目 (不同 domain)

Step 3: 事实对比 (LLM)
  → 输入: 锚点条目 + 相关条目摘要
  → Prompt: 逐条 claim 对比，标注:
    ✅ 确认: 多个独立来源支持
    ⚠️ 有差异: 不同来源描述不一致
    ❌ 仅本源: 仅在锚点条目中出现
    ❓ 未提及: 相关条目未覆盖

Step 4: 输出
  → fact_matrix: [
      {claim: "...", status: "✅", supporting: [entry_ids], conflicting: []},
      {claim: "...", status: "⚠️", supporting: [...], conflicting: [...]},
    ]
  → overall_confidence: high/medium/low
  → related_by_topic: 布尔 (是否通过主题关联)
```

### 3.4 自动触发

在 `sheaf_collect` 的输出中，当满足条件时自动提示：

```python
# collect 输出追加
if source_score < 50:  # C/D 级来源
    footer += "\n⚠️ 消息源可信度较低。运行 sheaf_crosscheck 查看交叉验证。"
elif related_count >= 3:  # 有 3+ 相关条目
    footer += f"\n💡 发现 {related_count} 篇相关报道。运行 sheaf_crosscheck 查看对比。"
```

---

## 4. 产品融入：与现有体系的关系

### 4.1 与 Matrix 的关系

```
Source Intelligence (v0.6.1 beta)
  ├── source_score     → 每个 entry 的来源可信度标签
  └── sheaf_crosscheck → 轻量级事实对比

Matrix (v0.7.0, Issue #63)
  ├── 事件聚类         → 跨来源的事件聚合 (已有设计)
  ├── 矩阵视图         → 多维对比表格 (已有设计)
  └── source_score     → 作为 Matrix 排序/着色的维度 ← v0.6.1 前置提供

关系:
  crosscheck = matrix 的 MVP
  source_score = matrix 的信任层
  v0.6.1 先做信任基础设施 → v0.7.0 Matrix 直接复用
```

### 4.2 与 MCP v2 的关系

```
MCP v2 (v0.6.x, MCP-V2-PLAN.md)
  Layer 0: 现有工具不变
  Layer 1: 元工具拆分
  Layer 2: 角色专属工具

Source Intelligence 纳入:
  - source_score → Layer 0 扩展 (现有 collect pipeline 增加一个步骤)
  - sheaf_crosscheck → Layer 2 Scientist 角色专属工具

不冲突: v0.6.1 beta 在 feat/mcp-v2 分支上开发
```

### 4.3 数据流变更

```
现有: fetch → quality_gate → classify(LLM) → summarize(LLM) → store
新增: fetch → quality_gate → classify(LLM+source) → summarize(LLM) → store
                                                           ↑ source_assessment 在 classify 中一并完成
```

**改动最小**: 只修改 `classify.md` prompt + `pipeline.py` 的 classify 结果解析。

---

## 5. 技术方案（Claude Code 可执行）

### 5.1 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `sheaf_ai/source_registry.py` | **新建** | 域名权威度表 + source_registry.json 管理 |
| `sheaf_ai/source_scoring.py` | **新建** | source_score 计算逻辑 |
| `sheaf_ai/mcp/verify.py` | **新建** | sheaf_crosscheck MCP 工具 |
| `prompts/classify.md` | **修改** | 新增 source_assessment 输出字段 |
| `sheaf_ai/pipeline.py` | **修改** | classify 结果解析增加 source 字段 |
| `sheaf_ai/mcp/entries.py` | **修改** | sheaf_get 返回 source 字段 |
| `sheaf_ai/mcp/server.py` | **修改** | 注册 sheaf_crosscheck 工具 |
| `sheaf_ai/display.py` | **修改** | CLI 输出显示 source_tier |
| `tests/test_source_scoring.py` | **新建** | 消息源评分单元测试 |
| `tests/test_crosscheck.py` | **新建** | 交叉验证集成测试 |

### 5.2 核心代码骨架

#### source_registry.py

```python
"""Source credibility registry — domain-level authority mapping."""

from pathlib import Path
import json

# Tier 1: 学术/官方 (15分)
TIER1_DOMAINS = {
    "arxiv.org", "nature.com", "science.org", "ieee.org",
    "*.edu.cn", "scholar.google.com", "dl.acm.org",
    "gov.cn", "stats.gov.cn",
}

# Tier 2: 权威媒体 (10分)
TIER2_DOMAINS = {
    "mp.weixin.qq.com",  # 公众号，需进一步判断
    "36kr.com", "jiemian.com", "caixin.com",
    "techcrunch.com", "theverge.com", "arstechnica.com",
}

# Tier 3: 社区/博客 (5分)
TIER3_DOMAINS = {
    "zhihu.com", "medium.com", "substack.com",
    "github.com", "reddit.com",
    "juejin.cn", "csdn.net",
}

# Tier D: 已知低质 (0分，额外扣分)
TIER_D_DOMAINS = {
    # 内容农场、AI 批量站、已知虚假信源
    # 初始为空，用户修正时自动积累
}


def get_domain_tier(domain: str) -> tuple[int, str]:
    """Get rule base score for a domain. Returns (score, tier_name)."""
    # ... matching logic with wildcard support ...


class SourceRegistry:
    """Persistent domain-level source score adjustments."""

    def __init__(self, path: Path):
        self.path = path
        self._data = self._load()

    def get_override(self, domain: str) -> int | None:
        """Get user-corrected score override for a domain."""

    def set_override(self, domain: str, score: int, note: str = ""):
        """Save a user correction for future auto-apply."""

    def _load(self) -> dict: ...
    def save(self): ...
```

#### source_scoring.py

```python
"""Source credibility scoring — hybrid rule + LLM approach."""

from sheaf_ai.source_registry import get_domain_tier, SourceRegistry


def compute_source_score(
    url: str,
    title: str,
    text: str,
    llm_assessment: dict | None = None,
    user_override: int | None = None,
    content_type: str = "reference",
    published_date: str | None = None,
) -> dict:
    """Compute source credibility score (0-100).

    Returns:
        {
            "score": 58,
            "tier": "B",
            "domain": "mp.weixin.qq.com",
            "author": "...",
            "is_primary": false,
            "rule_score": 28,
            "llm_score": 20,
            "user_override": null,
            "freshness": 8,
        }
    """
    # Step 1: Extract domain
    from urllib.parse import urlparse
    parsed = urlparse(url)
    domain = parsed.netloc

    # Step 2: Rule base (0-40)
    domain_score, _ = get_domain_tier(domain)
    primary_bonus = _detect_primary_source(text)      # 0 or 5
    author_bonus = _detect_author(title, text)          # 0-5
    citation_bonus = _detect_citations(text)            # 0-5
    rule_score = min(40, domain_score + primary_bonus + author_bonus + citation_bonus)

    # Step 3: LLM bonus (0-30) — from classify prompt
    llm_score = 0
    is_primary = False
    if llm_assessment:
        is_primary = llm_assessment.get("is_primary_source", False)
        if is_primary:
            llm_score += 10
        if llm_assessment.get("has_verifiable_claims"):
            llm_score += 10
        expertise = llm_assessment.get("domain_expertise", "low")
        llm_score += {"high": 10, "medium": 5, "low": 0}.get(expertise, 0)

    # Step 4: User override
    user_score = user_override or 0

    # Step 5: Freshness (0-10)
    freshness = _compute_freshness(content_type, published_date)

    # Total
    total = min(100, rule_score + llm_score + user_score + freshness)

    # Tier mapping
    if total >= 75:
        tier = "A"
    elif total >= 50:
        tier = "B"
    elif total >= 25:
        tier = "C"
    else:
        tier = "D"

    return {
        "score": total,
        "tier": tier,
        "domain": domain,
        "is_primary": is_primary,
        "rule_score": rule_score,
        "llm_score": llm_score,
        "user_override": user_override,
        "freshness": freshness,
    }


def _detect_primary_source(text: str) -> int:
    """Check if article is a primary source (original data/experiment)."""
    secondary_markers = ["据", "转自", "援引", "reported by", "according to", "cited by"]
    text_lower = text[:2000].lower()
    for marker in secondary_markers:
        if marker in text_lower:
            return 0  # secondary source
    return 5  # likely primary


def _detect_author(title: str, text: str) -> int:
    """Detect author attribution."""
    # Simple heuristic: check for byline patterns
    # Returns 0-5
    ...


def _detect_citations(text: str) -> int:
    """Detect verifiable citations (DOI, arXiv, URLs)."""
    import re
    citation_patterns = [
        r'10\.\d{4,}/[^\s]+',  # DOI
        r'arxiv\.org/abs/\d+\.\d+',
        r'https?://[^\s]+(?:doi|paper|research)',
    ]
    for pat in citation_patterns:
        if re.search(pat, text[:5000]):
            return 5
    return 0


def _compute_freshness(content_type: str, published_date: str | None) -> int:
    """Compute freshness bonus for news content."""
    if content_type != "news" or not published_date:
        return 5
    from datetime import datetime
    try:
        pub = datetime.fromisoformat(published_date)
        days = (datetime.now() - pub).days
        return max(0, min(10, 10 - days // 3))
    except:
        return 5
```

#### mcp/verify.py (crosscheck)

```python
"""MCP verify tools — sheaf_crosscheck."""

import json
from sheaf_ai.mcp.protocol import jsonrpc_response, jsonrpc_error
from sheaf_ai.mcp.data import load_index, load_entry
from sheaf_ai.search import full_text_search


def _crosscheck_entry(
    entry_id: str,
    focus: str | None = None,
    scope: str = "internal",
    top_k: int = 5,
) -> dict:
    """Cross-check an entry's claims against other sources."""

    # Load anchor entry
    anchor = load_entry(entry_id)
    if not anchor:
        return {"error": f"Entry not found: {entry_id}"}

    # Extract key claims from summary + tags
    claims = _extract_claims(anchor, focus)

    # Search related entries (internal)
    query = focus or " ".join(anchor.get("tags", [])[:5])
    related = full_text_search(query, limit=top_k * 2)

    # Filter: exclude self and same-domain entries
    anchor_domain = anchor.get("url", "")
    related = [
        r for r in related
        if r.get("id") != entry_id
        and _get_domain(r.get("url", "")) != _get_domain(anchor_domain)
    ][:top_k]

    # LLM compare (if related found)
    if related:
        fact_matrix = _llm_compare_claims(anchor, related, claims)
    else:
        fact_matrix = [
            {"claim": c, "status": "❓", "supporting": [], "conflicting": [], "note": "无相关条目"}
            for c in claims
        ]

    # Determine overall confidence
    confirmed = sum(1 for f in fact_matrix if f["status"] == "✅")
    total = len(fact_matrix)
    if total == 0:
        confidence = "unknown"
    elif confirmed / total >= 0.7:
        confidence = "high"
    elif confirmed / total >= 0.4:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "anchor_id": entry_id,
        "anchor_title": anchor.get("title", ""),
        "anchor_source": anchor.get("source", {}),
        "focus": focus,
        "claims_checked": total,
        "fact_matrix": fact_matrix,
        "overall_confidence": confidence,
        "related_count": len(related),
        "scope": scope,
    }


TOOLS = [{
    "name": "sheaf_crosscheck",
    "description": (
        "Cross-verify claims from an entry against other sources.\n"
        "\n"
        "Given an entry_id, search for related entries and compare facts.\n"
        "Returns a fact comparison matrix with verification status.\n"
        "\n"
        "Use when:\n"
        "- Verifying a claim: '这个说法有其他来源支持吗？'\n"
        "- Seeing different perspectives: '其他人怎么看？'\n"
        "- Checking low-credibility sources\n"
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entry_id": {"type": "string", "description": "Entry to cross-check"},
            "focus": {"type": "string", "description": "Specific claim to verify"},
            "scope": {
                "type": "string",
                "enum": ["internal", "external", "both"],
                "default": "internal"
            },
            "top_k": {"type": "integer", "default": 5}
        },
        "required": ["entry_id"]
    }
}]

HANDLERS = {
    "sheaf_crosscheck": lambda req_id, args: jsonrpc_response(req_id, {
        "content": [{"type": "text", "text": json.dumps(
            _crosscheck_entry(
                entry_id=args.get("entry_id", ""),
                focus=args.get("focus"),
                scope=args.get("scope", "internal"),
                top_k=args.get("top_k", 5),
            ), ensure_ascii=False, indent=2
        )}]
    })
}
```

### 5.3 classify.md 修改

在现有 prompt 末尾追加：

```markdown
6. **source_assessment 评估** (新增):
   判断这篇文章的消息源可信度，输出以下字段：
   - `is_primary_source`: true/false — 是否一手信源（原始数据/实验/官方发布）
   - `has_verifiable_claims`: true/false — 文中是否包含可验证的引用/数据/链接
   - `domain_expertise`: "high"/"medium"/"low" — 作者/来源在文章主题领域的专业度
   - `reasoning`: 一句话解释判断理由
```

对应 JSON 输出新增：
```json
{
  "source_assessment": {
    "is_primary_source": false,
    "has_verifiable_claims": true,
    "domain_expertise": "medium",
    "reasoning": "播客对话形式，非一手研究，但引用了具体产品数据和融资信息"
  }
}
```

---

## 6. Claude Code 执行计划

### Phase 1: 基础设施 (30 min)

```
1. 创建 source_registry.py
   - TIER1/2/3/D 域名表
   - SourceRegistry 类 (JSON 持久化)
   - get_domain_tier() 函数

2. 创建 source_scoring.py
   - compute_source_score() 混合评分
   - _detect_primary_source/author/citations 规则函数

3. 编写 test_source_scoring.py
   - 各 tier 域名的评分测试
   - 一手/二手检测测试
   - 引用检测测试
```

### Phase 2: Pipeline 集成 (20 min)

```
4. 修改 prompts/classify.md
   - 新增 source_assessment 字段

5. 修改 pipeline.py
   - classify_article() 结果解析增加 source_assessment
   - process_url() 中调用 compute_source_score()
   - entry 增加 source 字段

6. 修改 display.py
   - collect 输出显示 source_tier
   - 低可信度来源自动提示 crosscheck
```

### Phase 3: Crosscheck 工具 (30 min)

```
7. 创建 mcp/verify.py
   - sheaf_crosscheck MCP 工具
   - _crosscheck_entry() 核心逻辑
   - _llm_compare_claims() 事实对比

8. 修改 mcp/server.py
   - 注册 verify TOOLS + HANDLERS

9. 编写 test_crosscheck.py
   - 基础交叉验证测试
```

### Phase 4: 端到端验证 (15 min)

```
10. 运行全量测试 pytest tests/ -q
11. 手动测试: sheaf collect + sheaf crosscheck
12. 确认论文 notebook 不受影响
```

**预计总时长**: ~1.5 小时 Claude Code 工作

---

## 7. 版本号与发布

```
当前: v0.6.0 (main)
开发: v0.6.1-beta.1 (feat/mcp-v2)
发布: v0.6.1 (合并到 main 后)

CHANGELOG 新增:
## [0.6.1-beta.1] — 2026-06-12
### Added (Beta)
- **消息源可信度评分** — 混合规则+LLM打分，每个 entry 新增 source.score/tier
- **交叉验证工具** — sheaf_crosscheck MCP tool，库内多源事实对比
- **来源权威度表** — source_registry.py，域名级权威度映射
```

---

## 8. 开放问题

| # | 问题 | 默认假设 |
|---|------|---------|
| Q1 | source_assessment 是否计入 classify API 调用？ | 是，同一次调用，不增加成本 |
| Q2 | crosscheck 是否需要外部搜索？ | v0.6.1 仅 internal，外部留给 v0.7.0 matrix |
| Q3 | source_registry.json 是否纳入 git？ | 否，列入 .gitignore（用户私有） |
| Q4 | 低可信度来源是否自动降权搜索结果？ | v0.6.1 不做，v0.7.0 考虑 |
| Q5 | 域名表是否支持用户自定义？ | 是，通过 source_registry.json |

---

> **设计文档状态**: Draft v0.1，待 Sir 审阅后进入 Claude Code 执行。
> **审阅重点**: §2.2 评分模型是否合理？§3.3 crosscheck 流水线是否满足需求？
