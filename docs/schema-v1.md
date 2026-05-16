# Universal Collector — Knowledge Card Schema v1.1

> **Status**: Active
> **Version**: 1.1.0 (dynamic topics)
> **Purpose**: 标准化知识资产格式，使 Agent 可消费、可检索、可关联

## 设计原则

1. **Agent-First**: Schema 的首要消费者是 Agent（MCP/LLM），不是人类浏览器
2. **Backward Compatible**: 现有 entry 无需迁移，新字段有合理默认值
3. **Progressive Enrichment**: 录入时填核心字段，后续 Agent 可补充关联/时效状态
4. **Dynamic Topics**: 不做硬分类，主题由 LLM 自由提取，自然生长

## v1.1 变更（vs v1.0）

| 字段 | v1.0 | v1.1 |
|------|------|------|
| `topics` | 不存在 | **NEW** — 动态主题列表 `[{name, confidence}]` |
| `content_type` | 不存在 | **NEW** — 文章体裁 `news/analysis/research/...` |
| `category.primary` | 枚举四选一 | 由 topics[0].name 自动填充（兼容） |
| `tags_registry.json` | 不存在 | **NEW** — 全局标签注册表 |

## Schema Definition

```json
{
  "$schema": "https://universal-collector.dev/schema/v1.1",
  "type": "object",
  "required": ["id", "url", "title", "collected_at", "category", "status"],
  "properties": {

    "id": {
      "type": "string",
      "description": "唯一标识: {date}_{uuid8}",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}_[a-f0-9]{8}$",
      "example": "2026-05-13_de7d08eb"
    },

    "url": {
      "type": "string",
      "format": "uri",
      "description": "原始收录链接"
    },

    "title": {
      "type": "string",
      "description": "文章标题（fetch 提取，或 LLM 推断）",
      "minLength": 1
    },

    "category": {
      "type": "object",
      "description": "Legacy 兼容 — primary 从 topics[0] 自动填充",
      "properties": {
        "primary": {
          "type": "string",
          "description": "主主题（自动从 topics 最高置信度项填充）"
        },
        "sub": {
          "type": "string",
          "description": "子主题（保留为空，用 topics 代替）"
        }
      }
    },

    "topics": {
      "type": "array",
      "description": "动态主题列表（LLM 自由提取，非固定枚举）",
      "items": {
        "type": "object",
        "properties": {
          "name": { "type": "string", "description": "主题名称" },
          "confidence": { "type": "number", "minimum": 0, "maximum": 1 }
        }
      }
    },

    "content_type": {
      "type": "string",
      "enum": ["news", "analysis", "research", "tutorial", "opinion", "event", "product", "reference"],
      "description": "文章体裁"
    },

    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "description": "自由标签（LLM 提取，支持跨分类）"
    },

    "importance": {
      "type": "string",
      "enum": ["high", "medium", "low"],
      "default": "medium",
      "description": "重要性评估"
    },

    "summary": {
      "type": "string",
      "description": "一句话摘要（≤50词）"
    },

    "structured_summary": {
      "type": "object",
      "description": "结构化摘要（Phase 1 P0-2 扩展）",
      "properties": {
        "core_argument": { "type": "string" },
        "key_data": { "type": "string" },
        "relevance_to_user": { "type": "string" },
        "action_items": { "type": "string" }
      }
    },

    "timeliness": {
      "type": "object",
      "description": "时效性信息（Phase 1 P0-2 扩展）",
      "properties": {
        "has_deadline": {
          "type": "boolean",
          "default": false,
          "description": "是否包含时间敏感信息"
        },
        "deadline_date": {
          "type": ["string", "null"],
          "format": "date",
          "description": "ISO 8601 日期，如 2026-05-30"
        },
        "deadline_label": {
          "type": ["string", "null"],
          "description": "人类可读标签，如 'CFP 截止', '发布会', '截止报名'"
        },
        "urgency": {
          "type": "string",
          "enum": ["expired", "urgent", "upcoming", "evergreen"],
          "default": "evergreen",
          "description": "时效状态: expired=已过, urgent=7天内, upcoming=30天内, evergreen=无时效"
        }
      }
    },

    "source": {
      "type": "object",
      "description": "来源元数据",
      "properties": {
        "author": {
          "type": "string",
          "description": "作者/公众号名称"
        },
        "platform": {
          "type": "string",
          "enum": ["wechat", "web", "twitter", "paper", "rss", "manual", "unknown"],
          "default": "unknown",
          "description": "收录平台"
        },
        "publish_date": {
          "type": ["string", "null"],
          "format": "date",
          "description": "原文发布日期"
        }
      }
    },

    "associations": {
      "type": "array",
      "description": "知识关联（Phase 1+ 渐进填充）",
      "items": {
        "type": "object",
        "properties": {
          "related_id": { "type": "string", "description": "关联的 entry_id" },
          "relation": {
            "type": "string",
            "enum": ["same_topic", "contradicts", "extends", "cited_by", "supersedes"],
            "description": "关联类型"
          }
        }
      }
    },

    "metadata": {
      "type": "object",
      "description": "系统元数据",
      "properties": {
        "collected_at": {
          "type": "string",
          "format": "date-time",
          "description": "收录时间 (ISO 8601)"
        },
        "fetch_method": {
          "type": "string",
          "enum": ["requests", "playwright", "manual", "unknown"],
          "description": "抓取方式"
        },
        "language": {
          "type": "string",
          "default": "zh",
          "description": "内容语言"
        },
        "schema_version": {
          "type": "string",
          "default": "1.0.0",
          "description": "Schema 版本"
        }
      }
    },

    "status": {
      "type": "string",
      "enum": ["active", "archived", "deleted"],
      "default": "active"
    }
  }
}
```

## Index Entry Schema（轻量索引）

`index.jsonl` 中每行是一条轻量索引，用于快速检索：

```json
{
  "id": "string",
  "url": "string",
  "title": "string",
  "primary_category": "string",
  "sub_category": "string",
  "tags": ["string"],
  "importance": "string",
  "summary": "string",
  "has_deadline": false,
  "deadline_date": "date|null",
  "urgency": "string",
  "collected_at": "datetime"
}
```

## 字段扩展路线

| Phase | 新增字段 | 说明 |
|-------|---------|------|
| P0-2 | timeliness.* | 时效性自动识别 |
| P1-0 | associations | 知识关联 |
| P1-1 | content_hash | 去重标识 |
| P2-1 | embedding_vector | 语义检索向量 |
| P2-3 | project_id | 多项目隔离 |

## 迁移策略

- 现有 entry 无 `schema_version` 字段 → 视为 `0.x`（legacy）
- Phase 1 代码需兼容 `0.x` 和 `1.0.0` 两种格式
- 新写入一律使用 `1.0.0`
- 不做一次性批量迁移，渐进式升级（读取时补默认值）
