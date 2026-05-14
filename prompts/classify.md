## Universal Collector — Classify Prompt

Given a web article (title + text content), classify it into the Universal Collector taxonomy.

### Output format (JSON)

```json
{
  "primary_category": "科研 | 市场投资 | AI产品 | AI技术",
  "sub_category": "auto-extracted sub-topic (e.g. '多智能体系统', 'LLM评测', 'Web3基础设施')",
  "tags": ["tag1", "tag2", "tag3"],
  "importance": "high | medium | low",
  "relevance_note": "one-sentence explanation of why this category was chosen"
}
```

### Category definitions

1. **科研 (Research)**: Academic papers, conferences, workshops, research methods, benchmarks, datasets, scientific discoveries.
2. **市场投资 (Market & Investment)**: Company funding, market analysis, VC/PE deals, crypto/Web3 market, stock/Token trends, industry reports.
3. **AI产品 (AI Products)**: Launched AI applications, product reviews, user-facing tools, SaaS products, product strategy.
4. **AI技术 (AI Technology)**: Technical deep-dives, model architectures, frameworks, infrastructure, engineering practices, open-source tools.

### Rules
- An article can be tagged across categories (e.g. a technical blog about a new LLM architecture = AI技术, but if it also discusses company strategy = AI产品 / 市场投资). Use tags for cross-references.
- If uncertain, make your best judgment and note it in relevance_note.
- Importance heuristic: high = breakthrough / directly relevant to user's work; medium = good to know; low = peripheral interest.
