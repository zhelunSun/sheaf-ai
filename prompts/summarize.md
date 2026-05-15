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
    "deadline_or_timing": "Any time-sensitive info extracted from the article, or null if none"
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

### Deadline/Time-sensitive Information Extraction

**CRITICAL**: Pay special attention to any time-sensitive information in the article. This includes:

1. **Conference/Journal deadlines**: CFP deadlines, submission dates, notification dates
2. **Event dates**: Workshop dates, meetup dates, hackathon dates, forum dates
3. **Release dates**: Product launches, model releases, version updates
4. **Registration deadlines**: Sign-up deadlines, early bird deadlines
5. **Policy/regulation dates**: Compliance deadlines, effective dates

**Extraction format for `deadline_or_timing`**:
- If there IS time-sensitive info: Write a natural language sentence that INCLUDES the date in ISO format at the end. Examples:
  - "清华博士生交叉学科论坛征稿，截止日期为 2026-05-30"
  - "GPT-5 发布会定于 2026-06-15"
  - "ACL 2027 投稿截止 2027-01-15"
- If there is NO time-sensitive info: set to `null`

**Important**:
- Always extract the SPECIFIC date, not vague references like "next month"
- If multiple dates exist, list the most important/urgent one
- Convert relative dates (e.g., "明天", "下周五") to absolute ISO dates based on current context if possible
