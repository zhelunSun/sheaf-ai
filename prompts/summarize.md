## Sheaf — 摘要 Prompt

给定一篇网页文章（标题 + 正文），生成两个层级的摘要。

**重要：所有文本输出必须使用中文。** 保留专有名词的英文原文（如模型名、公司名、框架名），但解释和描述用中文。

### 输出格式 (JSON)

```json
{
  "one_liner": "一句话概括核心要点（≤50字）",
  "structured": {
    "core_argument": "主要论点或关键洞察（1-3句话）",
    "key_data": "文章中提到的重要数字、统计数据或具体证据",
    "relevance_to_user": "为什么这对一位关注 AI 技术趋势的科研或工程人员很重要",
    "action_items": "可以采取的行动（例如'试用这个框架'、'关注这个趋势'、'在论文中引用'）",
    "deadline_or_timing": "从文章中提取的时间敏感信息，如果没有则为 null"
  },
  "original_title": "文章标题",
  "source_author": "作者 / 发布方名称（如果能识别的话）"
}
```

### 指导原则
- 简洁。结构化摘要总计控制在 ~200 字以内。
- 对于 "relevance_to_user"，假设读者是关注 AI 技术趋势的科研或工程人员。
- 如果文章与用户已知兴趣明显无关，请诚实说明。
- 保留所有专有名词（人名、公司名、模型名、框架名、论文名）。
- **标题处理**：若输入提供了标题，`original_title` 原样回显；若**未提供标题**（如用户粘贴的笔记/观点），则根据正文**生成一个简洁的描述性标题**（≤30 字，点明主题，不要加引号或"笔记"等前缀），写入 `original_title`。

### Deadline/Time-sensitive Information Extraction

**CRITICAL**: Pay special attention to any time-sensitive information in the article. This includes:

1. **Conference/Journal deadlines**: CFP deadlines, submission dates, notification dates
2. **Event dates**: Workshop dates, meetup dates, hackathon dates, forum dates
3. **Release dates**: Product launches, model releases, version updates
4. **Registration deadlines**: Sign-up deadlines, early bird deadlines
5. **Policy/regulation dates**: Compliance deadlines, effective dates

**Extraction format for `deadline_or_timing`**:
- If there IS time-sensitive info: Write a natural language sentence that INCLUDES the date in ISO format at the end. Examples:
  - "交叉学科论坛征稿，截止日期为 2026-05-30"
  - "GPT-5 发布会定于 2026-06-15"
  - "ACL 2027 投稿截止 2027-01-15"
- If there is NO time-sensitive info: set to `null`

**Important**:
- Always extract the SPECIFIC date, not vague references like "next month"
- If multiple dates exist, list the most important/urgent one
- Convert relative dates (e.g., "明天", "下周五") to absolute ISO dates based on current context if possible
