# Universal Collector MVP 前支撑体系梳理

> 在正式开始「手动粘贴链接 → 处理」MVP 之前，系统检查当前有哪些基础设施可复用，哪些需要新建。

---

## 一、MVP 最小流程定义

```
用户复制微信文章链接 ──▶ 粘贴给 Agent ──▶ Agent 抓取正文 ──▶ 
LLM 分类+摘要 ──▶ 存储为 Markdown+JSON ──▶ 用户可随时对话查询
```

**MVP 不做**：自动化收录、Embedding 向量检索、定时报告、Skill 转化、浏览器插件。

---

## 二、现有基础设施盘点

### ✅ 已就绪（可直接复用）

| 组件 | 现状 | 复用方式 |
|------|------|---------|
| **LLM Client** | `ai-native-research/scripts/llm_client.py` 已验证可用（SiliconFlow + XTY 双 Provider） | 复制/软链接到 `universal-collector/scripts/` |
| **API Keys** | `.env` 已配置（SiliconFlow + XTY） | 复用同一套环境变量 |
| **WorkBuddy 聊天界面** | 当前就是 Agent 对话环境 | 直接作为消费端接口 |
| **本地文件存储** | WorkBuddy 有完整文件系统权限 | Markdown + JSON 存本地 |
| **nova-reader 经验** | 已有 ChromaDB 向量库经验 | Phase 1 再复用 |
| **skill-factory** | 已有 Skill 打包和发布流程 | Phase 2 再对接 |

### ⚠️ 需要新建（MVP 必需）

| 组件 | 必要性 | 工作量 | 说明 |
|------|--------|--------|------|
| **文章抓取模块** | P0 | 中 | 微信文章反爬，需要测试稳定方案 |
| **数据 Schema** | P0 | 低 | 定义收藏条目的 JSON 结构 |
| **存储目录结构** | P0 | 低 | 按主题/日期组织文件 |
| **分类 Prompt** | P0 | 低 | 四大主题 + 子主题自动分类的 LLM Prompt |
| **摘要 Prompt** | P0 | 低 | 结构化摘要提取的 LLM Prompt |
| **去重机制** | P1 | 低 | URL 去重 + 内容相似度去重 |
| **Agent 查询接口** | P0 | 中 | 让 Agent 能读取收藏库并回答用户问题 |

### ❌ 暂不需要（MVP 之后）

| 组件 | 阶段 |
|------|------|
| Embedding 向量库 | Phase 1 |
| 微信自动化接入 | Phase 1 |
| 浏览器插件 | Phase 1 |
| 定时报告 | Phase 1 |
| Skill 一键转化 | Phase 2 |
| 知识图谱 | Phase 3 |

---

## 三、缺失点详细分析

### 3.1 文章抓取：最大技术不确定性

**问题**：微信文章有反爬机制，直接 requests 可能拿不到正文。

**待测试方案**（按优先级）：

| 方案 | 原理 | 优点 | 风险 |
|------|------|------|------|
| A. `requests + 微信文章特殊 headers` | 模拟微信内置浏览器 | 轻量、快 | 可能被封 |
| B. `playwright` | 真实浏览器渲染 | 绕过大部分反爬 | 重、慢、需安装浏览器 |
| C. `wechat-spider` 等开源库 | 社区已有方案 | 可能稳定 | 维护状态未知 |
| D. **用户手动复制正文** | MVP fallback | 100% 可用 | 摩擦高 |

**MVP 策略**：先测试方案 A（5 分钟），不行就方案 B（15 分钟），再不行就用方案 D（fallback）。

### 3.2 数据 Schema：需要定义

每条收藏需要存什么？

```json
{
  "id": "uuid",
  "url": "https://mp.weixin.qq.com/s/...",
  "title": "文章标题",
  "source": "微信公众号",
  "author": "公众号名称",
  "publish_date": "2026-05-10",
  "collected_at": "2026-05-13T15:00:00+08:00",
  "content_text": "正文纯文本（用于 LLM 处理）",
  "content_html": "原始 HTML（可选）",
  "summary": "AI 生成的结构化摘要",
  "category": {
    "primary": "科研",
    "sub": "多智能体系统"
  },
  "tags": ["AutoGen", "Multi-Agent", "规划"],
  "importance": "high",
  "status": "active",
  "language": "zh"
}
```

### 3.3 分类策略：需要设计 Prompt

**第一层（硬编码四大主题）**：
- 科研（Research）
- 市场投资（Market & Investment）
- AI 产品（AI Products）
- AI 技术（AI Technology）

**第二层（LLM 自动子分类）**：
- 不预设子分类列表，让 LLM 根据内容自动提取
- 但可给示例引导（如 AI 技术下常见：模型发布、框架工具、infra、评测基准）

**第三层（标签）**：
- 自动提取关键词标签
- 支持跨主题标签（如一篇讲「Agent 投资」的文章同时属于「AI 技术」和「市场投资」）

### 3.4 存储结构：建议按主题+日期组织

```
universal-collector/
├── data/                           # 运行时数据（不打包）
│   ├── raw/                        # 原始抓取内容
│   ├── entries/                    # 结构化条目（JSON）
│   │   ├── 2026-05/
│   │   │   ├── 2026-05-13_001_research_multi-agent.json
│   │   │   └── 2026-05-13_002_ai-tech_llm.json
│   │   └── 2026-04/
│   ├── summaries/                  # AI 摘要（Markdown）
│   └── index.jsonl                 # 全局索引（方便检索）
├── scripts/
│   ├── fetch_article.py            # 文章抓取
│   ├── classify.py                 # 分类+摘要
│   └── query_collection.py         # 查询接口
└── prompts/
    ├── classify_v1.txt             # 分类 Prompt
    └── summarize_v1.txt            # 摘要 Prompt
```

### 3.5 Agent 查询接口：需要设计

用户问："最近我收了哪些关于 RAG 的文章？"

Agent 需要：
1. 读取 `index.jsonl` 找到相关条目
2. 用 LLM 理解用户意图（"最近" = 最近 7 天？30 天？）
3. 检索匹配条目（先关键词，Phase 1 再上向量）
4. 生成回答

**MVP 简化**：Agent 直接读 `index.jsonl`，用 LLM 做理解和总结。

### 3.6 去重机制：MVP 可简化

- **URL 去重**：简单哈希，同一链接不重复收录
- **内容去重**：MVP 不做，Phase 1 用 Embedding 相似度

### 3.7 成本估算（SiliconFlow DeepSeek-V3.2）

| 操作 | 单次 Token | 成本（约） |
|------|-----------|-----------|
| 分类+摘要（一篇 3000 字文章） | ~4K input + 1K output | ~¥0.003 |
| 查询回答（检索 5 条 + 生成） | ~3K input + 500 output | ~¥0.002 |
| 假设周收 20 篇 + 10 次查询 | - | ~¥0.08/周 = ~¥0.3/月 |

**结论**：成本极低，可忽略。

---

## 四、MVP 前待办清单

| # | 任务 | 状态 | 阻塞 |
|---|------|------|------|
| 1 | 测试微信文章抓取（requests / playwright） | ⏳ 待做 | 需用户提供 1-2 个微信文章链接 |
| 2 | 定义数据 Schema（JSON 结构） | ⏳ 待做 | 需用户确认字段 |
| 3 | 设计分类 Prompt（四大主题 + 子分类） | ⏳ 待做 | 需用户确认主题列表 |
| 4 | 设计摘要 Prompt（结构化输出） | ⏳ 待做 | 无阻塞 |
| 5 | 创建存储目录结构 + 初始化脚本 | ⏳ 待做 | 依赖 Schema 确定 |
| 6 | 实现单篇文章处理流水线（抓取→分类→摘要→存储） | ⏳ 待做 | 依赖 1-5 |
| 7 | 实现 Agent 查询接口（读取 index + LLM 回答） | ⏳ 待做 | 依赖 6 |
| 8 | 端到端测试（3-5 篇真实文章） | ⏳ 待做 | 依赖 6-7 + 用户提供链接 |

---

## 五、需要用户确认的问题

1. **Schema 字段**：上面的 JSON 结构有没有漏掉什么字段？比如「是否已读」「用户备注」「关联论文」？

2. **主题列表**：四大主题（科研/市场投资/AI产品/AI技术）是否准确？有没有遗漏或合并？

3. **摘要格式**：你希望摘要是什么样的？
   - 选项 A：一句话核心 takeaway
   - 选项 B：结构化（核心观点 / 关键数据 / 与我相关 / 行动建议）
   - 选项 C：两者都要

4. **第一篇测试文章**：现在能给我 1-2 个你最近收藏的微信文章链接吗？我立刻开始测试抓取。

---

*文档版本：v0.1*
*日期：2026-05-13*
*下一步：用户确认后，开始实现单篇文章处理流水线*
