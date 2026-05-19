# Sheaf — Agent Query Specification

> **Version**: 1.0.0
> **Purpose**: 定义 Agent 通过 MCP 消费知识库时的交互规范

## 概述

Agent 通过 MCP Server（`sheaf_ai/mcp_server.py`）访问知识库。所有交互遵循 MCP 协议 (JSON-RPC 2.0 over stdio)。

## 工具清单

| 工具 | 用途 | 输入 | 输出 |
|------|------|------|------|
| `sheaf_search` | 关键词搜索 | query, limit | 匹配条目列表 |
| `sheaf_list` | 浏览列表 | category?, limit | 最近条目列表 |
| `sheaf_get` | 详情获取 | entry_id | 完整条目 + summary markdown |
| `sheaf_urgent` | 时效查询 | — | 有 deadline 的条目 |
| `sheaf_correct` | 纠正分类 | entry_id, corrections, note? | 纠正结果 |
| `sheaf_collect` | 新收录 | url, force? | 处理结果 |

## 返回格式规范

### 成功响应

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "<JSON string of results>"
      }
    ]
  }
}
```

### 错误响应

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Entry not found: 2026-05-13_invalid"
  }
}
```

### 错误码

| Code | 含义 | 场景 |
|------|------|------|
| -32700 | Parse error | JSON 解析失败 |
| -32601 | Method not found | 未知工具名 |
| -32602 | Invalid params | 缺少必填参数 / entry 不存在 |
| -32603 | Internal error | 代码异常 |

## 检索精度策略

### 关键词搜索 (sheaf_search)

1. **搜索范围**: title + primary_category + sub_category + tags + summary
2. **匹配方式**: case-insensitive substring match
3. **排序**: 按 collected_at 降序（最新优先）
4. **限制**: 默认 10 条，最大 50 条

### Fallback 策略

当关键词搜索无结果时，Agent 应：
1. 尝试同义词或更宽泛的关键词
2. 使用 `sheaf_list` 浏览最近的收藏
3. 用 `sheaf_collect` 直接收录新内容

### 搜索优化建议

- 使用英文关键词命中率更高（summary 中英文混杂）
- 用中文搜索分类名（科研、市场投资、AI产品、AI技术）
- tags 中英混合，搜索时用核心词

## 条目数据格式

### 轻量条目 (sheaf_search / sheaf_list / sheaf_urgent)

```json
{
  "id": "2026-05-13_de7d08eb",
  "url": "https://...",
  "title": "文章标题",
  "primary_category": "科研",
  "sub_category": "子分类",
  "tags": ["tag1", "tag2"],
  "importance": "high",
  "summary": "一句话摘要",
  "has_deadline": true,
  "deadline_date": "2026-05-30",
  "urgency": "upcoming",
  "collected_at": "2026-05-13T17:52:58+08:00"
}
```

### 完整条目 (sheaf_get)

```json
{
  "id": "...",
  "url": "...",
  "title": "...",
  "category": {"primary": "...", "sub": "..."},
  "tags": [...],
  "importance": "...",
  "summary": "...",
  "structured_summary": {
    "core_argument": "...",
    "key_data": "...",
    "relevance_to_user": "...",
    "action_items": "..."
  },
  "timeliness": {
    "has_deadline": true,
    "deadline_date": "2026-05-30",
    "deadline_label": null,
    "urgency": "upcoming"
  },
  "source": {
    "author": "公众号名",
    "platform": "wechat",
    "publish_date": null
  },
  "metadata": {
    "collected_at": "...",
    "fetch_method": "requests",
    "schema_version": "1.0.0",
    "content_hash": "a1b2c3d4e5f6"
  },
  "status": "active",
  "summary_markdown": "# Title\n...(markdown)"
}
```

## 去重行为

### 收录时 (sheaf_collect / process_url)

1. URL 标准化后匹配（去 tracking params、fragment、trailing slash）
2. 微信文章：提取 `s=` 参数做精确匹配
3. 内容 hash：前 2000 字符的 MD5 前 12 位
4. 发现重复时返回 `stage: "dedup"` + 已有条目信息
5. `force: true` 可跳过去重

### Agent 处理建议

- 收到 dedup 响应时，告知用户已收录过
- 如果用户确认要重新收录，使用 `force: true`

## 纠偏机制

### sheaf_correct 使用流程

1. Agent 展示分类结果给用户
2. 用户说"分类不对"或"应该归到科研"
3. Agent 调用 `sheaf_correct` 提交纠正
4. 纠正自动应用到 entry + index，并记录到 feedback log
5. `feedback.jsonl` 积累后可用于 prompt 优化或 few-shot 示例

### 支持纠正的字段

| 字段 | key | 值域 |
|------|-----|------|
| 主分类 | `category_primary` | 科研 / 市场投资 / AI产品 / AI技术 |
| 子分类 | `category_sub` | 自由文本 |
| 标签 | `tags` | 字符串数组 |
| 重要性 | `importance` | high / medium / low |
| 摘要 | `summary` | 自由文本 |

## 版本兼容

- Schema v1.0.0 entry 和 legacy entry (无 schema_version) 共存
- Agent 应检查 `metadata.schema_version` 判断格式
- Legacy entry 中 title 可能为空，Agent 需做 fallback
