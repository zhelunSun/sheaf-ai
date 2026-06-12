## Sheaf — 动态分类 Prompt

给定一篇网页文章（标题 + 正文），提取文章的主题和标签。

**核心原则：不做硬分类，让内容自然归类。**

### 输出格式 (JSON)

```json
{
  "topics": [
    {"name": "主题名称", "confidence": 0.9},
    {"name": "次要主题", "confidence": 0.4}
  ],
  "tags": ["标签1", "标签2", "标签3"],
  "importance": "high | medium | low",
  "content_type": "news | analysis | research | tutorial | opinion | event | product | reference",
  "relevance_note": "一句话解释为什么提取这些主题和标签",
  "source_assessment": {
    "is_primary_source": false,
    "has_verifiable_claims": true,
    "domain_expertise": "medium",
    "reasoning": "一句话判断理由"
  }
}
```

### 主题提取规则

1. **topics 是领域维度的归类**，不是固定分类表。LLM 自由提取，例如：
   - "AI Agent", "Remote Sensing", "Web3", "Climate", "Investing", "International Relations", "Open Source", "LLM", "Computer Vision"...
   - 一篇文章可以有 1-3 个主题，每个带 confidence（0-1）
   - confidence > 0.7 的视为主要主题

2. **tags 是更细粒度的关键词**，用于交叉检索。例如：
   - 文章讨论 GPT-5 发布 → tags: ["GPT-5", "OpenAI", "大模型", "产品发布"]
   - 文章讨论 RAG 在遥感中的应用 → tags: ["RAG", "remote sensing", "knowledge retrieval", "geospatial"]

3. **content_type 描述文章体裁**：
   - `news` — 新闻快讯、动态报道
   - `analysis` — 深度分析、行业洞察
   - `research` — 学术论文、研究方法
   - `tutorial` — 教程、实操指南
   - `opinion` — 观点评论、博客
   - `event` — 活动预告、会议征稿
   - `product` — 产品发布、评测
   - `reference` — 参考资料、工具清单
   - `ai_conversation` — AI 对话记录（ChatGPT、Claude 等多轮对话归档）

4. **importance 判断**：
   - `high` — 突破性信息、与用户研究领域直接相关、重大行业变化
   - `medium` — 值得了解、有参考价值
   - `low` — 边缘兴趣、信息增量较小

5. **标签提取原则**：
   - 具体 > 抽象（"RAG" > "AI技术"）
   - 保留专有名词原文（DeepSeek、OpenAI、Transformer）
   - 每篇文章 3-8 个标签
   - 尽量复用已有常见标签（如 "大模型"、"Agent"、"LLM"、"投资"）
   - 英文标签必须拼写正确（如 "artificial" 而非 "artifical"），不确定时用中文标签

6. **source_assessment 评估**：
   判断这篇文章的消息源可信度，输出以下字段：
   - `is_primary_source`: true/false — 是否一手信源（原始数据/实验/官方发布）
   - `has_verifiable_claims`: true/false — 文中是否包含可验证的引用/数据/链接
   - `domain_expertise`: "high"/"medium"/"low" — 作者/来源在文章主题领域的专业度
   - `reasoning`: 一句话解释判断理由
