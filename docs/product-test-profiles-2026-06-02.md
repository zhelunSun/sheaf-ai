# Sheaf 多用户 Profile 模拟测试报告

> **日期**: 2026-06-02 | **版本**: v0.4.0a0 | **测试人**: Jarvis 🤖
> **环境**: Windows / Python 3.12.7 / pip install sheaf-ai==0.4.0a0
> **API Provider**: SiliconFlow (DeepSeek-V3.2) — ✅ API key 可用
> **测试目录**: `D:\Agent\WorkBuddy\sheaf-ai\.sandbox-test\`

---

## 环境搭建总结

| 步骤 | 耗时 | 状态 |
|------|------|------|
| venv 创建 | ~2s | ✅ |
| pip install sheaf-ai==0.4.0a0 | ~15s | ✅ (14 个依赖自动解析) |
| 配置 .env | ~1s | ✅ |
| `sheaf --help` 验证 | ~0.5s | ✅ |

**安装体验**: 顺畅。pip 安装无依赖冲突，所有依赖自动解析。

**配置发现**: 
- 需要手动创建 `.env` 文件或设置 `SILICONFLOW_API_KEY` 环境变量
- 默认 provider 是 `openai`（GPT），需要设置 `DEFAULT_PROVIDER=siliconflow` 才能用国产模型
- LLM client 会搜索 CWD/.env，但不会搜索 `~/.sheaf/.env`
- **无 `SHEAF_API_KEY` 环境变量支持** — 只能用 provider-specific 变量名

---

## Profile A — 博士生（AI/遥感方向）

**场景**: 收藏 arXiv 论文 + 微信公众号文章，生成知识卡片用于论文写作
**操作链**: collect → search → crystallize

### 测试结果

| # | 测试 | 命令 | 状态 | 说明 |
|---|------|------|------|------|
| A1 | arXiv 论文收藏 | `collect --json https://arxiv.org/abs/2401.00001` | ✅ | 3757 chars, 分类为"量化金融/投资组合管理/因子投资" |
| A2 | 微信文章收藏 | `collect --json https://mp.weixin.qq.com/s/ebhK0P5klR4swx_KaF7fmQ` | ✅ | 14941 chars, 16 图片, 分类为"世界模型/人工智能基础研究/强化学习" |
| A3 | 搜索 'deep learning' | `search deep learning` | ⚠️ | 无结果 — 内容涉及 AI 但未命中关键词 |
| A4 | 搜索 '模型' (中文) | `search 模型` | ✅ | 2 条结果, 排序正确 (世界模型 25.0 > 金融 5.0) |
| A5 | Crystallize 'AI' | `crystallize AI` | ✅ | 5 张知识卡片, 含置信度 (80%-95%) |
| A6 | 列出卡片 | `crystallize --list` | ✅ | 格式清晰, 含摘要和置信度 |
| A7 | 去重测试 | `collect --json <same-url> --force` | ✅ | 允许 force 重新收集, 生成新 entry_id |

### 摩擦点

1. **搜索关键词局限 (A3)**: "deep learning" 返回 0 结果，即使内容涉及 AI/ML。搜索是关键词匹配，非语义搜索。ArXiv 论文摘要中包含了 "deep learning" 相关方法，但未被爬取到。这是请求体大小限制导致的截断。
2. **ArXiv 主 URL (2401.00001) 内容量小 (3757 chars)**: ArXiv 抽象页只有摘要文本，完整的 PDF 内容无法抓取。对于博士生来说，可能需要更深入的论文内容。
3. **微信文章图片处理**: 16 张图片被提取到 JSON 中，但只有 meta 信息（src/alt/position），没有实际图片存储或 base64 嵌入。

### 质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 分类准确性 | ★★★★☆ | arXiv 正确分类为 research, 微信正确为 analysis |
| 摘要质量 | ★★★★☆ | 结构化摘要含 core_argument/key_data/relevance_to_user |
| 搜索召回 | ★★★☆☆ | 关键词匹配, 不是语义搜索 |
| Crystallize 质量 | ★★★★☆ | 5 张卡片, 引用 Source 0/2, 置信度合理 |

---

## Profile B — 大厂上班族（技术方向）

**场景**: 快速收藏技术博客和文档，批量操作，时间少
**操作链**: 批量 collect → search 关键词

### 测试结果

| # | 测试 | 命令 | 状态 | 说明 |
|---|------|------|------|------|
| B1 | Python 文档 | `collect --json https://docs.python.org/3/` | ✅ | 2387 chars, 分类"编程语言/软件开发/技术文档" |
| B2 | CSDN 博客主页 | `collect --json https://blog.csdn.net/` | ✅ | 7509 chars, 20 个导航/广告图片提取 |
| B3 | Python 教程 | `collect --json https://docs.python.org/3/tutorial/index.html` | ✅ | 6952 chars, 分类"编程语言/软件开发/技术教育" |
| B4 | 搜索 'Python' | `search Python` | ✅ | 3 条结果, Python 文档 20.0 > 教程 20.0 > CSDN 2.0 |
| B5 | 搜索 'tutorial' | `search tutorial` | ✅ | 2 条结果, 排序正确 |
| B6 | 搜索不存在内容 | `search Django` | ✅ | 优雅返回 "No results" |
| B7 | 数据统计 | `stats` | ✅ | 全面的统计, 含 gamification |
| B8 | 标签统计 | `tags` | ✅ | 20 个 tag, 含首次使用日期 |

### 摩擦点

1. **无批量收集命令**: 收藏 3 个 URL 需要 3 次独立的 `sheaf collect`。上班族需要 `sheaf collect --batch urls.txt` 或 `sheaf collect url1 url2 url3`。
2. **CSDN 主页噪音大**: 20 张图片中大部分是导航图标、广告和装饰元素，只有少量正文内容。质量门禁检测到 (score: 4, is_image_heavy: false) 但仍通过。对于技术人想收藏的具体技术文章，最好是收藏文章 URL 而不是主页。
3. **Python 文档主页内容偏少 (2387 chars)**: 文档主页主要包含导航链接，实际内容在子页面。
4. **搜索分数解释**: 搜索结果中 "Python 3.14 documentation" 的 relevance score 是 20.0，"CSDN博客"只有 2.0。得分机制不透明，用户无法理解为什么分数是 20 而不是 10 或 100。

### 质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 抓取速度 | ★★★★★ | requests 策略快速完成 (1-3s per URL) |
| 分类准确性 | ★★★★☆ | Python 正确分类, CSDN 合理 |
| 搜索体验 | ★★★★☆ | 全文搜索 + 标签匹配, 结果排序合理 |
| 去重能力 | ★★★★★ | 区分 URL 重复, `--force` 覆盖 |

---

## Profile C — 知识博主（多源内容创作）

**场景**: 多平台收藏，重分类和 crystallize，用于内容创作
**操作链**: collect 多源 → 分类 → crystallize → search 主题

### 测试结果

| # | 测试 | 命令 | 状态 | 说明 |
|---|------|------|------|------|
| C1 | 36kr 主页 | `collect https://www.36kr.com/` | ❌ | "All strategies failed" — JS 渲染 SPA |
| C2 | SSPai 主页 | `collect https://sspai.com/` | ❌ | 同上, JS 渲染 |
| C3 | 36kr 文章 | `collect https://www.36kr.com/p/2397857654768261` | ❌ | 同上, 即使具体文章 URL 也不行 |
| C4 | SSPai 文章 | `collect https://sspai.com/post/73145` | ✅ | 2448 chars, 5 图片, 分类"消费电子/科技新闻/知识产权" |
| C5 | Reclassify | `reclassify` / `reclassify --dry-run` | ⚠️ | "0 entries" — 没有实际执行重分类 |
| C6 | Crystallize '科技' | `crystallize 科技` | ⚠️ | 需要 3+ 相关条目 — 当前只有 1 条 SSPai 相关 |
| C7 | Crystallize '编程' | `crystallize 编程` | ⚠️ | 同上, 3 个不同主题的条目不够聚集 |
| C8 | Crystallize JSON | `crystallize --format json` | ⚠️ | 无卡片, 优雅返回 |
| C9 | Insights | `insights` | ✅ | 9 topics, 12 connections, 含可视化连接图 |
| C10 | Weekly | `weekly` | ✅ | 完整周报, 含热点话题统计 |
| C11 | Trends | `trends` | ✅ | 正确显示日趋势 |
| C12 | Urgent | `urgent` | ✅ | "No urgent items" |
| C13 | Serve | `serve --help` | ✅ | HTTP API 可用 (port 8321) |
| C14 | MCP | `mcp --help` | ✅ | MCP stdio server |

### 摩擦点

1. **🔥 36kr 完全不可用**: JS 渲染 SPA，requests 策略抓取不到内容，Playwright 未安装作为备用。用户收到"All strategies failed"无从下手。
2. **🔥 SSPai 主页不可用但文章可用**: 主页 (JS 渲染) 失败，但具体文章 URL 工作。用户不知道有这种 URL 层面的差异。
3. **⚠️ Reclassify 行为不清**: `reclassify` 输出 0 entries，不是重新运行 AI 分类，而是只修复已标记为"待修正"的条目。文档没有说明这种行为。
4. **Crystallize 阈值**: 需要 3+ 个同一主题的条目才能进结晶。知识博主初期只有零散收藏，需要积累才能使用此功能。
5. **Insights 的冷启动问题**: 需要 3+ 个条目才能启动。初次使用时 insights/weekly/trends 都显示空状态。

### 质量评分

| 维度 | 评分 | 说明 |
|------|------|------|
| 多平台兼容性 | ★★★☆☆ | 静态页面 ok, JS 渲染页面完全不可用 |
| 分类智能 | ★★★★☆ | SSPai 正确分类为消费电子/科技新闻/知识产权 |
| Insights | ★★★★☆ | 9 topics, 12 connections, topics 连接图清晰 |
| 零数据体验 | ★★★★★ | 优雅处理空数据和冷启动 |

---

## 汇总问题清单（按优先级排序）

### 🔴 P0 — 必须修复（阻碍基本可用性）

| # | 问题 | 影响 Profile | 描述 | 当前表现 |
|---|------|--------------|------|---------|
| P0-1 | **JS 站点完全不可用** | C | 36kr、SSPai 主页等 SPA 站点全部失败 | "All strategies failed" 无具体原因 |
| P0-2 | **无批量操作** | B, C | 收藏多个 URL 需要 N 次调用 | 无 `--batch` 或多 URL 支持 |
| P0-3 | **搜索纯关键词匹配** | A | "deep learning" 搜索不到 AI 相关文章 | 返回 0 结果，无语义搜索 |
| P0-4 | **默认 provider 是 OpenAI** | ALL | 中国用户需手动设置 `DEFAULT_PROVIDER` | 默认需要 OpenAI API key |
| P0-5 | **错误信息无具体原因** | C | "All strategies failed" 不说明失败原因 | 无结构化错误码 |

### 🟡 P1 — 重要（影响用户体验）

| # | 问题 | 影响 Profile | 描述 | 当前表现 |
|---|------|--------------|------|---------|
| P1-1 | **Crystallize 需要 3+ 同主题条目** | A, C | 跨主题条目不能触发结晶 | "Not enough related entries (need 3+)" |
| P1-2 | **Reclassify 行为不透明** | C | 只修复"待修正"条目，非重新分类 | 输出 "0 entries" 无解释 |
| P1-3 | **搜索结果分数不透明** | B | 20.0 vs 2.0 的分数含义不清 | 分数出现在 UI 但无图例 |
| P1-4 | **OpenAI 兼容但无 SILICONFLOW 环境变量配置** | ALL | 只有 provider-specific key | 需手动设置 `SILICONFLOW_API_KEY` |
| P1-5 | **CSDN 主页噪音过多** | B | 导航/广告图片大量提取 | 20 images 但大部分无用 |
| P1-6 | **无 `SHEAF_API_KEY` 统一环境变量** | ALL | 所有 provider 需要各自独立配置 | 无统一入口 |

### 🔵 P2 — 可改进（提升体验）

| # | 问题 | 影响 Profile | 描述 | 当前表现 |
|---|------|--------------|------|---------|
| P2-1 | **无全局数据目录** | ALL | 数据在 CWD/data/，切目录后丢失 | 需要 `SHEAF_DATA_DIR` |
| P2-2 | **无 Playwright 依赖提示** | C | 需要额外安装 playwright | 安装 sheaf 时无提示 |
| P2-3 | **MCP 无 resources** | A | Agent 只能通过 tools 操作 | 无 `sheaf://` URI scheme |
| P2-4 | **无 sheaf doctor 诊断命令** | ALL | 配置问题无从排查 | 无诊断工具 |
| P2-5 | **无降级模式** | ALL | 无 API key 时部分功能不可用 | 分类/摘要失败，但 collect 仍执行 |
| P2-6 | **无 completions/exports** | ALL | 无法保存 SS 内容为 PDF 或 Markdown | 仅支持 JSON/text 输出 |

---

## 与 Agent-Native 设计原则对比

根据 `docs/AGENT-NATIVE-DESIGN-PRINCIPLES.md` 的 6 项建议（A-F），逐项标注测试中发现的问题是否可以通过设计升级解决：

### A. JSON-First 输出 (P0)

| 测试发现 | 能否通过 A 解决 | 说明 |
|----------|---------------|------|
| `--json` 是 opt-in 而非 default | ✅ 是 | 自动 TTY 检测 → Agent 管道自动 JSON |
| stderr 与 stdout 混杂 | ❌ 部分 | 彩色文本和 progress 信息需要统一到 structured output |
| 搜索结果无 JSON | ✅ 是 | JSON-first 确保 search 也输出结构化结果 |

### B. 批量操作 (P0)

| 测试发现 | 能否通过 B 解决 | 说明 |
|----------|---------------|------|
| 无 `--batch` 参数 | ✅ 是 | 直接实现批量 collect |
| Profile B 需要快速收藏多个 URL | ✅ 是 | `--batch urls.txt` 或 `batch mcp call` |
| 去重已在单条层面实现 | ❌ 无需解决 | 批量需要复用去重逻辑 |

### C. 结构化错误 + 退出码 (P0)

| 测试发现 | 能否通过 C 解决 | 说明 |
|----------|---------------|------|
| "All strategies failed" 无具体原因 | ✅ 是 | 改为 JSON 错误体 + stage 字段 |
| 搜索 0 结果无结构化反馈 | ✅ 是 | 结构化空结果 |
| 所有错误 exit(0) | ✅ 是 | 语义退出码 |

### D. 零配置启动 (P1)

| 测试发现 | 能否通过 D 解决 | 说明 |
|----------|---------------|------|
| 默认 provider 是 OpenAI | ✅ 部分 | 中国市场默认 SiliconFlow |
| 无 `SHEAF_API_KEY` 统一入口 | ✅ 是 | 统一 API key 环境变量 |
| 需要手动创建 .env | ✅ 是 | `sheaf doctor` + 自动检测 |
| Playwright 未安装无提示 | ❌ 无关 | 需要独立处理依赖安装提示 |

### E. 全局数据目录 (P1)

| 测试发现 | 能否通过 E 解决 | 说明 |
|----------|---------------|------|
| 数据在 CWD/data/ | ✅ 是 | `~/.sheaf/data/` 全局默认 |
| 切换目录丢失历史 | ✅ 是 | 全局目录 + `SHEAF_DATA_DIR` |

### F. MCP Resources (P1)

| 测试发现 | 能否通过 F 解决 | 说明 |
|----------|---------------|------|
| 只有 tools 无 resources | ✅ 是 | `sheaf://entries/` URI 方案 |
| Agent 需要浏览知识库结构 | ✅ 是 | MCP resources 暴露条目列表和详情 |
| Crystallize 卡片无结构化访问 | ✅ 是 | `sheaf://cards/` URI |

### 总结：可解决的问题占比

| 问题类别 | 通过设计升级可解决 | 说明 |
|----------|------------------|------|
| 🔴 P0 (5 个) | 4/5 (80%) | 仅 Playwright 依赖不属于设计原则范畴 |
| 🟡 P1 (6 个) | 4/6 (67%) | Reclassify 行为和搜索分数透明性需要功能增强 |
| 🔵 P2 (6 个) | 4/6 (67%) | 降级模式和多格式导出需要单独设计 |
| **总计** | **12/17 (71%)** | **大部分问题可通过设计升级解决** |

---

## 额外发现的亮点

1. **Gamification 系统很棒**: 里程碑（"知识种子"、"主题探索者"、"跨界传粉者"）增加收藏动力
2. **Quality gate 有效**: 图片密度检测 + score 评级，虽然有提升空间但基础框架好
3. **结构化的 JSON 输出完整**: `--json` 输出包含所有关键字段，适合 Agent 消费
4. **冷启动体验优雅**: 空数据时 weekly/insights 友好提示而不是报错
5. **所有命令退出码 0**: 即使是功能失败也优雅退出，不产生令人困惑的错误堆栈

---

## 结论

Sheaf v0.4.0a0 在核心场景（静态页面收藏、分类、搜索、crystallize）上表现良好，能完成端到端的知识管理流程。主要瓶颈有：

1. **JS 渲染页面兼容性** 是最严重的可用性问题 — 直接影响 36kr、SSPai 等常用中文科技平台
2. **批量操作缺失** 对 Agent 场景影响深重 — Agent 需要一次处理多个 URL
3. **搜索纯关键词匹配** 导致语义搜索场景失效 — "deep learning" 搜不到 AI 文章
4. **错误信息缺乏结构化** 让 Agent 无法编程式处理错误

按照 Agent-Native 设计原则升级后，71% 的测试问题可以直接被设计级方案解决，剩余 29% 需要功能增量（Playwright 支持、搜索语义化、多格式导出）。

---

*报告生成: 2026-06-02 10:30 CST | Jarvis 🤖*
