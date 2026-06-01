# Sheaf Matrix — Product Design Brief

> v0.1 | 2026-06-01 | complementary to Issue #63

---

## 1. Terminology: What Product Design Calls This

| Term | Definition | How It Applies to Sheaf Matrix |
|------|-----------|-------------------------------|
| **Aha Moment** | The instant a user understands *why* they need the product | User collects an article → sees "5 other sources reported this" → realizes Sheaf isn't a bookmark tool, it's an *understanding tool* |
| **Progressive Disclosure** | Reveal advanced features only when the user is ready | Don't promote `/matrix` on install. Show it as a contextual prompt *after* the user has collected 3+ articles on related topics |
| **Golden Path** | The simplest, most common user journey to value | `collect URL` → notice "Related coverage" prompt → enter `/matrix` → see the matrix → realize the power |
| **In-Context Activation** | Trigger a feature from within another feature's workflow | `sheaf collect` output shows: "Found 5 related reports on this event. Run `sheaf matrix` to see all angles." |
| **Feature Discovery** | How users learn a feature exists | Passive: collect footer. Active: `sheaf discover` command. Serendipitous: crystallize side-effect |
| **Job-to-be-Done (JTBD)** | The real job the user is hiring the product for | "When I read one article about an event, I want to know if I'm getting the full picture or just one angle." |
| **Hooked Model** | Trigger → Action → Variable Reward → Investment | Trigger: collect an article. Action: run `/matrix`. Reward: discover angles you missed. Investment: matrix gets crystallized into knowledge card. |

---

## 2. Sheaf's Mental Model Evolution

### Current Model (v0.4)
```
collect → [crystallize ← search]
```
User mental model: "Sheaf saves articles and helps me find them later."

### With Matrix (v0.5)
```
                    ┌─ collect ──┐
                    │            │
URL ─→ event fingerprint        ├─→ matrix (new)
                    │            │
                    └─ search ───┘
                         │
                    crystallize (lower threshold: ≥3 same-event articles)
```
User mental model: **"Sheaf helps me understand events, not just save articles."**

The matrix isn't a standalone feature — it's the **bridge** between collection and crystallization. It answers: "Should I crystallize this? Is there enough material?"

---

## 3. How Matrix Fits Into Sheaf's System

### The Sheaf Pipeline (expanded)

| Stage | What Happens | Matrix's Role |
|-------|-------------|---------------|
| `collect URL` | Article ingested, tagged, scored | **Passive discovery**: footer shows "Found N related reports" if event fingerprint matches existing articles |
| `matrix URL` (new) | Cross-source search → cluster → output table | **Active discovery**: user explicitly asks "what else is out there?" |
| `crystallize` (enhanced) | ≥3 same-event articles → auto-trigger | **Lower threshold**: event-based crystallization, not just topic-based |
| `search` | Query returns articles + matrices + crystals | **New result type**: matrix cards alongside articles |

### Integration Points

```
sheaf collect → auto-detect event proximity → prompt: "5 related reports found. Try `sheaf matrix`"
sheaf matrix → cross-search → output → auto-collect → event_id linkage
sheaf crystallize → event_id threshold (3+) → event knowledge card
sheaf search → returns event cards with source count badge
```

### Zero New Concepts
Matrix reuses all existing primitives:
- `event_id` = same as existing `card_id`, just partitioned differently
- Cross-search = existing `sheaf search` with external engines
- Matrix output = formatted `sheaf search` result
- Event crystallization = same `crystallize` pipeline with lower trigger

User doesn't need to learn anything new. They already `collect` and `search`. Matrix is just a smarter `search` that tells them: "Here's what everyone else is saying about this."

---

## 4. Discovery & Low-Friction Path

### Phase 1: Passive (no new UI)
```
$ sheaf collect https://mp.weixin.qq.com/s/xxx
✓ Collected: NVIDIA GTC Taipei 2026
  card_id: 2026-06-01_58fb4a92
  tags: NVIDIA, GTC, RTX Spark, PC芯片
  ─────────────────────────────────────
  📡 This event has 8 other reports in your library.
     Run `sheaf matrix 2026-06-01_58fb4a92` to see all angles.
```
**Why this works**: The user was already going to read the result. The matrix prompt is one extra line, not a new screen.

### Phase 2: Contextual (in crystallize)
```
$ sheaf crystallize
Found 3 articles about NVIDIA GTC Taipei 2026 from Chinese tech media, US tech press, and investor analysis.
Crystallizing into event knowledge card...

✓ Card: NVIDIA GTC Taipei 2026 — 3 sources, 3 angles
```
**Why this works**: The user expects crystallization to aggregate. They discover the matrix *through* crystallization.

### Phase 3: Active (user discovers command)
```
$ sheaf matrix --help
$ sheaf matrix https://mp.weixin.qq.com/s/xxx
$ sheaf matrix 2026-06-01_58fb4a92   # from existing card
```
**Why this works**: By the time the user actively types `matrix`, they already know what it does from Phase 1+2 hints.

### The One-Sentence Discovery
> "Every time you collect an article, Sheaf shows you who else is talking about the same event — without you having to search."

---

## 5. The Story: How to Pitch It

### For Developers (PyPI/GitHub README)

> **Sheaf doesn't just save articles. It tells you what you're missing.**
>
> Collect one report → Sheaf finds every other source covering the same event → See the full picture, not one angle.

### For Researchers (Academic use case)

> When building a literature review, you need to know: "Is this the only paper saying X, or are there 10 others?" Sheaf Matrix answers that question in one command.

### For Investors (Web3/Finance use case)

> A project announces funding on one outlet. Is it covered differently on CoinDesk vs The Block vs 36Kr? Sheaf Matrix shows you the spin — not just the news.

### For Product Managers

> You read a competitor launch on TechCrunch. Sheaf Matrix shows you the same launch through the eyes of their investors' blog, their customers' complaints on Twitter, and their competitors' responses.

### The Elevator Pitch (15 seconds)

> "You read one article. Sheaf Matrix shows you the same event through 5 different lenses — official, financial, technical, competitive, international. All auto-collected into your knowledge base."

### The One-Liner (3 seconds)

> **"Sheaf Matrix: read one source, understand the whole story."**

---

## 6. Competitive Positioning

### Matrix vs News Aggregators

| | Ground News / NewsCord | Sheaf Matrix |
|---|---|---|
| Primary axis | Political bias (L→R) | **Source type** (official/financial/technical/competitive) |
| Output | Browse → leave | **Collect → crystallize → search forever** |
| User | "I want balanced news" | "I want to understand this event deeply and keep it" |
| URL input | ❌ (except NewsCord) | ✅ Core flow |
| Tech/research focus | ❌ | ✅ |

### The Positioning Statement

> While Ground News tells you "this story is covered by 50% left-leaning and 50% right-leaning sources," Sheaf Matrix tells you "this AI model launch was covered as a technical breakthrough by arXiv, a market threat by Bloomberg, and a regulatory concern by Politico — here are all three, saved to your library."

---

## 7. MVP Scope (What to Build First)

| Priority | Feature | Rationale |
|----------|---------|-----------|
| **P0** | `sheaf matrix <url>` — basic cross-search + table output | Core value. Prove it works. |
| **P0** | Collect footer: "N related reports" prompt | Discovery mechanism. Without this, nobody finds it. |
| **P1** | Auto-collect matrix results with `event_id` | Persistence. Without this, it's just a search tool. |
| **P1** | Event-based crystallize (≥3 same-event articles) | Closes the loop. Matrix → Crystallize → Knowledge. |
| **P2** | Angle classification (official/tech/finance/competitive) | Differentiation. This is why users choose Sheaf over Ground News. |
| **P3** | `sheaf discover` — proactive "events you might want to matrix" | Growth. Users come back to check what they're missing. |

### One-Week Sprint Plan

| Day | Deliverable |
|-----|------------|
| 1 | Event fingerprint extraction (LLM prompt + search query generation) |
| 2 | Multi-engine cross-search + dedup |
| 3 | Matrix table output + collect footer integration |
| 4 | event_id linkage + auto-collect |
| 5 | Event-based crystallize + test with 3 real-world events |

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Cross-search returns noise (unrelated articles) | Require ≥2 common entities + date proximity for event match |
| Users ignore the footer prompt | Make it contextual: only show when ≥3 related articles detected |
| Matrix output overwhelming (50+ sources) | Default: top 10 by relevance. Expandable: "Show all N sources" |
| Event fingerprint extraction unreliable | Fallback: keyword-based search. LLM is nice-to-have, not required |
| Users don't understand "event_id" concept | Hide from UI. Use "Related coverage" language, not "event_id: evt_xxx" |

---

## Appendix: Real-World Test Case

**Input**: `https://mp.weixin.qq.com/s/jE-Vt-BHDKpfc-oXiAFNjA` (NVIDIA GTC Taipei 2026)

**Manual result** (proof of concept, 2026-06-01):

| # | Source | Angle | Key Narrative |
|---|--------|-------|---------------|
| 1 | NVIDIA Blog | Product | RTX Spark, Vera Rubin, DGX Station |
| 2 | 财联社 | Live coverage | 黄仁勋 full transcript |
| 3 | 新浪财经 | Competition | "Chip giants invade each other's turf" |
| 4 | 国际电子商情 | Industry | Strategic pivot to AI factory |
| 5 | 东方财富 | Investor | Vera production, OpenAI/Anthropic first customers |
| 6 | 新浪科技 | Ecosystem | Lenovo first to ship RTX Spark |
| 7 | 知乎专栏 | Technical | Vera Rubin trillion-parameter architecture |
| 8 | Grenade.tw | Product | Taiwan tech media full list |
| 9 | 微信公众号 | Synthesis | Chinese-language comprehensive |

**9 sources. 5 angles. All reporting on the same event. None of them complete alone.**
