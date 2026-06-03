# Sheaf 收藏功能强化调研报告

> **目标**：为 Issue #68（Router 补全）和 #69（SPA 降级）提供竞品背景 + 方案设计
> **日期**：2026-06-03

---

## 1. Sheaf 当前提架能力全景

| 能力 | 状态 | 覆盖范围 | 瓶颈 |
|------|------|----------|------|
| **URL 模式检测** | ✅ 30+ 正则 | GitHub/arXiv/YouTube/Bilibili/Twitter/WeChat/PDF/Image | 部分 GitHub 子页面漏匹配；缺少 Medium/Substack/知乎/Reddit 等 |
| **HTTP Header 检测** | ✅ HEAD fallback | PDF/Image/HTML | 依赖网络请求，无法识别 SPA |
| **内容路由** | ✅ Handler 注册表 | GitHub API / arXiv API / PDF 提取 | YouTube/Bilibili/Twitter/WeChat 只有 type 检测无专属 handler |
| **通用 Web 抓取** | ✅ requests + Playwright | SSR 页面（默认）/ JS 重度页面（Playwright fallback） | Playwright 为可选依赖，未安装时 SPA 全部失败 |
| **ChatGPT 分享页** | ✅ 专属 extractor | chatgpt.com/share/* | 需 Playwright |
| **微信公众号** | ✅ 双抓取策略 | mp.weixin.qq.com | 图片/图为主文章质量差 |
| **PDF 提取** | ✅ PyPDF2 + pdfminer | URL PDF / 本地文件 | 扫描版 PDF 无 OCR |
| **批量操作** | ✅ ThreadPoolExecutor | CLI `--batch` + MCP `sheaf_collect_batch` | 单机并发受网络限制 |
| **SPA 检测** | ✅ 启发式 `_is_js_heavy_page` | 判断 body 文本 < 100 字符 | 仅在失败后诊断，不参与路由决策 |
| **浏览器扩展** | 🔄 WIP | Chrome Extension（`extension/`） | 未集成到 UC Pipeline |

### 架构小结

```
URL → detect_content_type() → route_fetch()
                                    │
                   ┌────────────────┼─────────────────┐
                   │                │                  │
              有 Handler?       无 Handler         ChatGPT?
              github/pdf/     fetch_article()     _fetch_chatgpt
              arxiv            │  ├ requests       (Playwright)
                               │  ├ Playwright
                               │  └ 质量检测 + 降级
```

---

## 2. 竞品调研：书签/万能收藏工具

### 2.1 Karakeep（原 Hoarder）— ⭐ 主要对标

| 维度 | 详情 |
|------|------|
| **抓取方式** | **Playwright + Headless Chrome**（Workers 容器内运行） |
| **SPA 支持** | ✅ 完整支持（Playwright 渲染所有 JS） |
| **浏览器扩展** | ✅ Chrome/Firefox，tRPC 直连后端 |
| **是否开源** | ✅ MIT，monorepo |
| **核心技术栈** | Next.js + tRPC + Drizzle ORM + SQLite + Meilisearch |
| **AI 标签** | OpenAI / Ollama 可选，工厂模式切换 |
| **内容类型** | 网页 / PDF / 图片 / RSS Feed |
| **架构亮点** | 双进程（Web + Workers），SQLite 队列（liteque），Playwright 可配置外部浏览器 `BROWSER_WEB_URL` |

**关键学习**：
- 爬取是独立 Worker，与 Web 服务解耦，通过队列通信
- Playwright 为**唯一爬取引擎**（没有 requests 降级），但可配置外部 Chrome 实例
- AI 处理也是独立 Worker（inference），Post-crawl 触发

### 2.2 Readwise Reader

| 维度 | 详情 |
|------|------|
| **抓取方式** | 服务端 Mercury parser（类 Readability）+ 浏览器扩展辅助 |
| **SPA 支持** | ⚠️ 部分支持（依赖 Mercury，对 SPA 效果不稳定） |
| **浏览器扩展** | ✅ Chrome/Safari/Firefox/Edge |
| **是否开源** | ❌ 闭源 SaaS |
| **核心技术栈** | Ruby on Rails 后端（推测），React 前端 |
| **特色** | 全平台同步、Highlight 复用 Readwise 核心能力、支持 EPUB/Newsletter/PDF |

### 2.3 Cubox

| 维度 | 详情 |
|------|------|
| **抓取方式** | 服务端渲染 + 智能解析 + 浏览器扩展 |
| **SPA 支持** | ✅ 智能解析引擎，声称支持多媒体 OCR |
| **浏览器扩展** | ✅ Chrome/Safari/Firefox + 微信收藏助手 |
| **是否开源** | ❌ 闭源 SaaS |
| **核心技术栈** | 未公开（NLP + CV 技术栈） |
| **特色** | AI 摘要/问答、智能文本解析（多媒体→文本）、全平台覆盖 |

### 2.4 Omnivore（已停云服务，可自托管）

| 维度 | 详情 |
|------|------|
| **抓取方式** | **Puppeteer + Chromium**（`puppeteer-parse` 服务） |
| **SPA 支持** | ✅ 完整支持（真实浏览器渲染） |
| **浏览器扩展** | ✅ Chrome/Safari/Firefox/Edge |
| **是否开源** | ✅ AGPL-3.0 |
| **核心技术栈** | Node.js + TypeScript + Next.js + PostgreSQL + GraphQL |
| **内容解析** | **Mozilla Readability**（扩展版）提取正文 + PDF.js |
| **架构亮点** | 微服务：`api`(4000) + `puppeteer-parse`(9090) + `content-fetch` + `imageproxy` |

**关键学习**：
- Puppeteer 作为独立微服务，端口 9090，API 层调度
- 使用 Readability 做正文提取，比 BeautifulSoup 的 CSS selector 方案更通用
- 2024.11 云服务关闭，转为自托管，社区仍在维护

### 2.5 Raindrop.io

| 维度 | 详情 |
|------|------|
| **抓取方式** | 浏览器扩展 **DOM 注入**（客户端解析）+ 服务端 |
| **SPA 支持** | ⚠️ 有 SPA 检测（`isSPA.js`），但仅影响元数据提取路径 |
| **浏览器扩展** | ✅ 全平台 |
| **是否开源** | ❌ 闭源 SaaS |
| **核心技术栈** | React + 自研解析引擎 |
| **内容提取** | 级联策略：JSON-LD → Meta Tags → DOM 抓取，最多 9 张图 |
| **特色** | 轻量元数据提取为主，全文可能由服务端处理 |

### 2.6 Pocket（Mozilla，已宣布关停）

| 维度 | 详情 |
|------|------|
| **抓取方式** | 服务端解析（推测 Mercury parser） |
| **SPA 支持** | ⚠️ 部分支持 |
| **浏览器扩展** | ✅ 全平台（已内置于 Firefox） |
| **是否开源** | ❌ 闭源 |
| **状态** | Mozilla 宣布关停，用户迁移至 Raindrop 等 |

### 2.7 ArchiveBox / WebCite / Archive.org

| 维度 | 详情 |
|------|------|
| **抓取方式** | 多引擎：`wget` + `chromium` + `readability` + `screenshot` |
| **SPA 支持** | ✅ ArchiveBox 用 headless Chrome |
| **是否开源** | ✅ ArchiveBox MIT / Wayback Machine 闭源 |
| **核心技术栈** | Python + Django（ArchiveBox） |
| **定位** | 网页存档而非知识提取，但抓取策略可借鉴 |

### 竞品对比总结

| 产品 | 抓取引擎 | SPA | 开源 | 核心技术 |
|------|----------|-----|------|----------|
| **Karakeep** | Playwright | ✅ | ✅ | Next.js + SQLite queue |
| **Omnivore** | Puppeteer + Readability | ✅ | ✅ | Node.js + GraphQL |
| **Readwise Reader** | Mercury/Readability | ⚠️ | ❌ | Rails |
| **Cubox** | 自研 + Extension | ✅ | ❌ | NLP+CV |
| **Raindrop.io** | DOM 注入 + 服务端 | ⚠️ | ❌ | React 级联解析 |
| **Pocket** | Mercury | ⚠️ | ❌ | 已关停 |
| **ArchiveBox** | wget + Chromium | ✅ | ✅ | Python + Django |

**模式总结**：行业分两派——
1. **纯无头浏览器派**（Karakeep/Omnivore/ArchiveBox）：用 Playwright/Puppeteer 统一处理所有页面，SPA 天然支持
2. **轻量解析派**（Raindrop/Pocket）：HTTP 抓取 + Readability/Mercury，浏览器扩展辅助元数据提取

---

## 3. AI 客户端的 LLM 搜索实现

| 客户端 | 抓取策略 | SPA 处理 | 通用降级 |
|--------|----------|----------|----------|
| **Perplexity** | 自建搜索索引（千亿网页）+ 实时爬取 + 自研 Search API | 推测有 headless 渲染层 | 搜索摘要为主，不直接抓原文 |
| **ChatGPT browsing** | Bing Search API → 爬取 top N 结果 → content extraction | 有 JS 执行能力（推测 Playwright） | 降级为搜索摘要 |
| **Claude web search** | 类似 ChatGPT，多搜索引擎 + 内容提取 | 未确认 | 返回搜索结果 + 引用 |
| **Cursor/Windsurf** | `@web` 命令触发 WebFetch，服务端 fetch + HTML→Markdown | 无专用 SPA 处理 | 降级为纯文本提取 |
| **WorkBuddy WebFetch** | 服务端 HTTP GET → HTML→Markdown → AI 摘要 | 无 SPA 处理 | 直接返回能拿到的内容 |

**关键洞察**：AI 客户端几乎不做"完整正文提取"，而是做**搜索摘要**——它们的目标是回答问题，不是收藏内容。Sheaf 的定位不同：需要完整正文 + 元数据，所以必须解决 SPA 问题。

---

## 4. 轻量化方案设计

### 4.1 三层架构

```
┌──────────────────────────────────────────────────┐
│  Layer 3: Extension 兜底（未来）                    │
│  浏览器扩展注入 DOM → 拿到完整渲染后 HTML            │
│  适用: 需登录页面 / 反爬站点 / 复杂 SPA              │
├──────────────────────────────────────────────────┤
│  Layer 2: Playwright 降级                          │
│  requests 抓取失败或质量不足 → Playwright 渲染      │
│  适用: JS 重度页面 (知乎/B站/Twitter/ChatGPT 等)    │
│  检测: _is_js_heavy_page() / _PLAYWRIGHT_PREFERRED │
├──────────────────────────────────────────────────┤
│  Layer 1: HTTP + Readability（基础层）               │
│  requests GET → HTML → Readability/BS4 提取正文     │
│  适用: SSR 页面 / API 站点 (GitHub/arXiv/PDF)       │
└──────────────────────────────────────────────────┘
```

### 4.2 各层职责

| 层 | 触发条件 | 输出 | 依赖 |
|----|----------|------|------|
| **L1: HTTP** | 默认 | title + text + images + quality | requests + BS4 |
| **L2: Playwright** | L1 质量不足 / `_PLAYWRIGHT_PREFERRED` / `_is_js_heavy_page` | 完整渲染后 HTML → 同 L1 提取 | playwright（可选） |
| **L3: Extension** | L2 失败 / 需登录 | DOM snapshot + 元数据 | Chrome Extension（未来） |

### 4.3 和现有代码的集成点

| 改动 | 文件 | 说明 |
|------|------|------|
| **Router 补全**（#68） | `router.py` `_URL_PATTERNS` | 新增 Medium/Substack/Reddit/知乎/小红书/Notion 等 pattern |
| **Readability 集成** | `fetch_article.py` `_extract_text()` | 引入 `readability-lxml` 作为 L1 正文提取器，替代手工 CSS selector |
| **SPA 预判路由** | `fetch_article.py` `fetch_article()` | 将 `_is_js_heavy_page` 从"失败后诊断"升级为"路由前决策" |
| **Handler 补全** | `collectors/` 新文件 | YouTube/Bilibili/Twitter 各加轻量 handler（用 API 或 oEmbed） |
| **质量检测增强** | `fetch_article.py` `_content_quality()` | 短文本 + 高图片密度 → 触发 L2 降级 |
| **Extension 管道** | `extension/` + `collectors/` | Extension 将渲染后 HTML POST 到 MCP → 走 L1 提取 |

### 4.4 推荐依赖策略

```
必选:  requests, beautifulsoup4
推荐:  readability-lxml       (L1 正文提取升级)
可选:  playwright             (L2 JS 渲染)
未来:  chrome extension       (L3 兜底)
```

---

## 5. Action Items（按优先级排序）

| # | Issue | 优先级 | 说明 |
|---|-------|--------|------|
| 1 | **#68 Router 补全** | P0 | 补全 Medium/Substack/Reddit/知乎/小红书/Notion/Discord/Telegram 等 URL pattern |
| 2 | **Readability 集成** | P0 | 引入 `readability-lxml` 替代手工 CSS selector，提升 L1 正文提取覆盖率 |
| 3 | **#69 SPA 降级策略** | P0 | 将 `_is_js_heavy_page` 从诊断工具升级为路由决策，低质量自动触发 Playwright |
| 4 | **YouTube/Bilibili Handler** | P1 | 用 oEmbed API 提取视频元数据，不依赖页面渲染 |
| 5 | **Twitter/X Handler** | P1 | 用 Nitter 代理或 syndication API 提取推文内容 |
| 6 | **质量→降级闭环** | P1 | 图片密度高 + 文本少 → 自动标记为"需 JS 渲染" |
| 7 | **Extension 管道** | P2 | Chrome Extension 抓取渲染后 DOM → POST 到 MCP `sheaf_collect` |
| 8 | **RSS Feed Handler** | P2 | 参考 Karakeep 的 feed Worker，定时抓取 RSS/Atom |
| 9 | **截图 + PDF 存档** | P3 | Playwright 截图 + PDF 生成，参考 Karakeep crawler Worker |
| 10 | **Meilisearch/向量搜索集成** | P3 | 参考 Karakeep 的 search Worker，独立索引服务 |

---

> **报告总结**：Sheaf 当前架构（requests → Playwright fallback）方向正确，核心差距在两点：(1) 正文提取依赖手工 CSS selector 而非 Readability，(2) SPA 检测在路由决策之后而非之前。对标 Karakeep 的 Playwright-first 策略，Sheaf 应坚持"HTTP + Readability 优先，Playwright 按需降级"的轻量路线，避免引入重量级 headless-only 依赖。
