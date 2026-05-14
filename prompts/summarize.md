## Universal Collector — Summary Prompt

Given a web article (title + text content), generate two levels of summary.

### Output format (JSON)

```json
{
  "one_liner": "A single sentence capturing the core takeaway (≤50 words)",
  "structured": {
    "core_argument": "The main thesis or key insight (1-3 sentences)",
    "key_data": "Any important numbers, statistics, or concrete evidence mentioned",
    "relevance_to_user": "Why this matters to a AI/remote sensing researcher and AI agent builder",
    "action_items": "What could be done with this info (e.g. 'try this framework', 'monitor this trend', 'cite in paper')",
    "deadline_or_timing": "Any time-sensitive info (conference deadlines, release dates, etc.) or null"
  },
  "original_title": "The article's title",
  "source_author": "Author / publication name if identifiable"
}
```

### Guidelines
- Be concise. The structured summary should fit within ~200 words total.
- For "relevance_to_user", assume the reader works at the intersection of AI agents and remote sensing, and also follows AI/Web3 investment.
- If the article is clearly irrelevant to the user's known interests, note that honestly.
- Preserve all specific names (people, companies, models, frameworks, papers).
