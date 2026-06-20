<p align="center">
  <a href="README.md">English</a> | <b>中文</b>
</p>

<p align="center">
  <img src="assets/logo.png" alt="Sheaf Logo" width="360">
</p>

<h1 align="center">Sheaf</h1>

<p align="center"><b>拾穗成束，聚沙成塔 — 面向 Agent 时代的知识基础设施</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="tests/"><img src="https://img.shields.io/badge/tests-1003%20pass-brightgreen" alt="Tests"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/pyversions/sheaf-ai.svg" alt="Python Version"></a>
</p>

---

**Sheaf**（/ʃiːf/，麦穗束）是一束收获的谷物 — 农人带到集市的基本单位。Sheaf 对知识做同样的事：收集你读过的内容，结晶为结构化的知识卡片，让 AI Agent 可以搜索、引用和推理。

**一句话定位**：全局书签 + Agent 记忆，本地优先，开源免费。

## 为什么需要 Sheaf？

你每天都在收藏 — 文章、论文、仓库、教程。**90% 的收藏再也不会被打开。**

不是因为你懒。而是因为书签服务于**人类阅读**，不服务于 **Agent 工作流**。当你问你的编程助手「上周我读过的 MCP 相关内容是什么？」，它完全不知道。

Sheaf 解决这个问题。你保存的每一条链接都变成一个**结构化条目** — 一根麦穗。积累足够多后，结晶为**知识卡片** — 一束可携带、可搜索的知识包，任何 Agent 都能消费。

## 快速开始

**一行接入 Claude Code —— 无需安装 Python：**

```bash
claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
```

然后让 agent *收藏一个链接*、*搜索知识库*、或 *结晶某个主题* —— 就这些。`uvx` 是 npm 风格的运行器（`brew install uv` / `winget install astral-sh.uv`）；需要一个 OpenAI 兼容的 API Key —— 设置 `SHEAF_API_KEY`，或运行一次 `uvx --from sheaf-ai sheaf config setup`。

<details>
<summary><b>OpenAI Codex CLI</b> —— 加到 <code>~/.codex/config.toml</code></summary>

```toml
[mcp_servers.sheaf]
command = "uvx"
args = ["--from", "sheaf-ai", "sheaf-mcp"]
```

</details>

**偏好 CLI 或 Python 库？**

```bash
pip install sheaf-ai
sheaf config setup          # 交互式 API Key 向导（推荐）

# 然后开始使用
sheaf collect https://arxiv.org/abs/2401.00000   # 收藏
sheaf search "transformer architecture"          # 搜索
sheaf crystallize AI                             # 结晶知识卡片
```

无需注册，无需云端。数据本地存储 —— 在项目目录内为 `./data/`，否则为 `~/.sheaf/data`，格式为 Markdown + JSON。可用 `SHEAF_DATA_DIR` 覆盖。

## 核心功能

### 1. 收藏（Harvest）

粘贴链接，Sheaf 自动抓取、分类、摘要：

```bash
sheaf collect https://arxiv.org/abs/2401.00000    # 论文
sheaf collect https://mp.weixin.qq.com/s/xxx       # 微信文章
sheaf collect https://chatgpt.com/share/xxx        # AI 对话分享
sheaf collect --text "关键洞察..."                   # 自由文本
```

| 输入类型 | 说明 |
|----------|------|
| **网页 / 论文** | 抓取全文，提取标题、作者、摘要，自动分类 |
| **AI 对话分享** | 提取问答内容，结构化为可复用知识 |
| **微信 / 知乎** | 通过 Playwright 处理动态渲染和付费墙 |
| **自由文本** | 包装为结构化条目，自动分类 |

### 2. 结晶（Crystallize）— 核心特性

不是把书签存着吃灰。`sheaf crystallize` 跨多条收藏合成洞察：

```bash
$ sheaf crystallize AI
正在结晶 'AI'...
✨ 5 张知识卡片已结晶:
  📌 RAG 面临检索相关性挑战 (90%)
     RAG 系统高度依赖检索质量；错误会降低 LLM 输出可靠性。
  📌 CRAG 框架提升 RAG 鲁棒性 (95%)
     CRAG 引入检索评估器、网页搜索增强和文档分解。
```

每张卡片包含：
- **置信度评分**（0-100%）
- **证据溯源** — 哪些源条目贡献了这张卡片
- **主题归属** — 属于哪个主题
- **标签** — 用于过滤和交叉引用

### 3. Agent 就绪（MCP Server）

内置 [Model Context Protocol](https://modelcontextprotocol.io/) 服务器，任何兼容 MCP 的 Agent 都能查询你的知识库：

```bash
sheaf mcp
```

**默认暴露 4 个核心工具**（覆盖 ~90% 自动化 agent 工作流），其余走 `sheaf` CLI + `--json`：

| 工具 | 类型 | 说明 |
|------|------|------|
| `sheaf_collect` | 核心 MCP | 收藏一个 **URL 或一段笔记**（`url` 或 `text`） |
| `sheaf_search` | 核心 MCP | 全文 + 语义搜索（keyword/hybrid/quick） |
| `sheaf_crystallize` | 核心 MCP | 从主题结晶知识卡片 |
| `sheaf_get_card` | 核心 MCP | 按 ID 获取卡片详情 |
| `sheaf_collect_batch` | CLI | `sheaf collect URL1 URL2 ...` |
| `sheaf_list` | CLI | `sheaf list [--topic T] [--json]` |
| `sheaf_get` | CLI | `sheaf get <id> --json` |
| `sheaf_correct` | CLI | MCP `tools/call` 兜底 |
| `sheaf_insights` | CLI | `sheaf insights` |
| `sheaf_crosscheck` | CLI | MCP `tools/call`；另见 `sheaf matrix` |
| `sheaf_list_cards` | CLI | `sheaf crystallize --list` |

> 4 个核心工具让 MCP schema 更精简（~1.5k vs ~5k tokens）。其余 7 个工具的
> handler 全部保留，可经 `tools/call` 调用；设 `SHEAF_MCP_TOOLS=all` 恢复全部
> 11 个。Claude Code / Codex 的 `sheaf setup` 还会一并部署 skill / 说明书
> （`sheaf-guide.md` / `AGENTS.sheaf.md`），引导 agent 何时用 CLI。

### 一键接入 Agent

一条命令将 Sheaf 接入你的 AI 编程助手：

```bash
# Cursor / Windsurf / WorkBuddy
sheaf setup --target cursor      # 写入 .cursor/mcp.json
sheaf setup --target windsurf    # 写入 .windsurf/mcp.json
sheaf setup --target workbuddy   # 写入 ~/.workbuddy/mcp.json

# Claude Code — 写入 ~/.claude.json，并部署 ~/.claude/skills/sheaf-guide.md
sheaf setup --target claude

# OpenAI Codex — 写入 ~/.codex/config.toml，并部署 ~/.codex/AGENTS.sheaf.md
sheaf setup --target codex

# 自动检测当前环境
sheaf setup                      # 自动识别 claude/codex/cursor/windsurf/workbuddy
```

> MCP 默认只暴露 4 个核心工具，`sheaf setup` 会一并部署 skill / 说明书。
> 详见上方「Agent 就绪」节的工具矩阵。

**预览但不写入：**
```bash
sheaf setup --target cursor --dry-run
```

详见 [docs/mcp-setup.md](docs/mcp-setup.md)。

## 命令一览

```bash
sheaf help                       # 命令总览（分组）—— 或 `sheaf <命令> --help`
sheaf collect <url>              # 收藏文章、论文或网页
sheaf collect --text "..."       # 保存一条笔记/洞察（不抓取，标记为 note）
sheaf search <query>             # 全文搜索（结果显示 entry id）
sheaf list [--page N]            # 浏览条目，分页
sheaf get <id>                   # 查看一条条目的完整详情
sheaf stats                      # 收藏统计与主题趋势
sheaf crystallize <topic>        # 结晶知识卡片
sheaf crystallize --list         # 列出所有已结晶卡片
sheaf crystallize --semantic <q> # 向量语义搜索
sheaf tags                       # 标签统计
sheaf weekly                     # 周报摘要
sheaf insights                   # 跨主题关联发现
sheaf urgent                     # 显示有截止日期的条目
sheaf mcp                        # 启动 MCP 服务器
sheaf setup --target <platform>  # 一键配置 MCP（cursor/claude/workbuddy/windsurf）
sheaf init                       # 首次初始化
```

## 退出码（Agent 友好）

Sheaf 返回**语义化退出码**，让 Agent 可以按错误类型编程式分支处理，无需解析 stderr：

| 码 | 名称        | 含义                                          |
|----|-------------|-----------------------------------------------|
| 0  | `SUCCESS`   | 操作成功完成                                  |
| 1  | `PARTIAL`   | 部分成功（如批量操作有跳过）                  |
| 2  | `DUPLICATE` | 条目已存在（去重跳过）                        |
| 3  | `QUALITY`   | 内容质量门禁未通过                            |
| 4  | `NETWORK`   | 网络连接或 API 调用失败                       |
| 5  | `CONFIG`    | API key 缺失、URL 无效或配置错误              |
| 6  | `LLM`       | LLM API 失败（限流、响应异常）                |
| 7  | `STORAGE`   | 文件 I/O 或存储故障                           |

`--json` 模式下，错误负载包含 `exit_code`、`exit_code_name` 和 `error_type` 字段，便于程序化内省。

## 架构

```
URL → 抓取 → 分类 → 摘要 → 存储 → 查询
       ↓       ↓       ↓       ↓
   3策略    LLM标签  摘要+    JSONL + MD
   降级     +主题    截止期   索引

              ↓
         crystallize → KnowledgeCard → EmbeddingEngine
              ↓              ↓
          CLI/MCP       语义搜索
```

| 模块 | 职责 |
|------|------|
| `sheaf_ai/` | 核心 — 管道、存储、搜索、CLI、MCP 服务器、结晶引擎 |
| `sheaf_cards/` | 知识卡片引擎 — 基础类型、向量嵌入、生成 |
| `prompts/` | LLM 提示模板（分类、摘要、结晶） |
| `data/` | 本地知识库（JSONL + Markdown，已 gitignore） |

## 隐私 & 本地优先

**你的数据不会离开你的机器，除非你主动选择。**

- 所有内容本地存储 —— 项目目录内为 `./data/`，否则为 `~/.sheaf/data`（可用 `SHEAF_DATA_DIR` 覆盖）
- LLM 调用发送到**你选择的** API 提供商
- 无遥测、无分析、无账号
- Markdown + JSONL 格式 — 完全可迁移，零锁定

## 配置

Sheaf 支持任何 OpenAI 兼容 API：

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# 或任何兼容端点（Together、Groq、DeepSeek 等）
export OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.together.xyz/v1
```

可选：在工作目录创建 `.env` 文件。参见 [.env.example](.env.example)。

## 系统要求

- **Python 3.10+**
- **LLM API Key** — 任何 OpenAI 兼容端点
- **Playwright Chromium**（可选，用于 JS 重度网站）：`pip install -e ".[browser]" && playwright install chromium`

## 开发

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git
cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q     # 1003 passed, 19 skipped
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

依赖通过 `pyproject.toml` extras 管理。本地开发用 `.[dev]`，HTTP API 用 `.[server]`，Playwright 抓取用 `.[browser]`。

## 当前状态

Sheaf 处于早期 Alpha 阶段。核心 收藏 → 搜索 → 结晶 → MCP 管道已可工作，1003 个测试通过、19 个跳过。我们正在用真实用户验证，准备进入 Beta。

浏览器扩展（`extension/`）是 HTTP API 的实验性本地伴侣，其 manifest 版本独立于 Python 包版本，直到扩展拥有自己的发布渠道。

**试试看**：收藏 20+ 条链接，运行 `sheaf crystallize <topic>`，然后让你的 Agent 来查询。如果对你有用，欢迎开 Issue 或 Discussion 告诉我们你的想法。

## 许可证

[Apache 2.0](LICENSE)

---

<p align="center">
  <b>Sheaf</b> — 一束收获的麦穗，农人带到集市的基本单位。<br>
  数学中，<a href="https://en.wikipedia.org/wiki/Sheaf_(mathematics)">Sheaf</a> 将局部数据粘合为全局图景。<br>
  Sheaf 这个工具做的是同样的事：<br>
  把散落的知识聚拢成束，让你的 Agent 随时取用，也让你与他人分享。
</p>
