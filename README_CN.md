<p align="center">
  <a href="README.md">English</a> | <b>中文</b>
</p>

<p align="center">
  <img src="assets/logo.png" alt="Sheaf Logo" width="360">
</p>

<h1 align="center">Sheaf</h1>

<p align="center"><b>让你的 Agent 用上你挑选的资料和形成的判断，并帮助你决定哪些内容值得亲自读。</b></p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache%202.0-blue.svg" alt="License: Apache 2.0"></a>
  <a href="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml"><img src="https://github.com/zhelunSun/sheaf-ai/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/sheaf-ai/"><img src="https://img.shields.io/pypi/v/sheaf-ai.svg" alt="PyPI"></a>
</p>

---

**Sheaf**（/ʃiːf/，麦穗束）希望成为 **Agent 时代的个人知识基础设施**。当前版本把主动保存的来源整理为本地、可检索并可追溯的资料库，供 Agent 查找与引用。收藏表达关注，不等于认可来源结论，也不等于完整的个人判断。本地优先，开源。

> **Sheaf** 是一束收获的谷物。Sheaf 把用户主动选择的来源聚成知识，同时保留知识与证据的联系。

> **产品方向：** 随手收藏，让已有 Agent 在实际任务中用上相关资料，并帮助选择值得亲读的内容。零额外反馈也应该有用，不要求填写问卷、逐条标注或先教系统品味。阅读建议、偏好复用和更顺畅的来源核查仍是[计划中的功能](docs/PRODUCT-FEATURES.md)，完整体验尚未验证。见[当前定位](docs/PRODUCT-DESIGN-INDEX.md)和[推进计划](docs/NEXT-PHASE-PLAN.md)。

## 快速开始

**1 · 安装（全平台通用）：**

```bash
pip install sheaf-ai
sheaf config setup     # 一次性：选一个提供商，粘贴任意 OpenAI 兼容的 API Key
```

**2 · 接入你的 agent：**

```bash
sheaf setup            # 自动识别 Claude Code / Codex / Cursor / Windsurf / WorkBuddy，
                       # 写入 MCP 配置 + 部署内置 skill / 说明书
```

**3 · 用起来：**

```bash
sheaf collect https://arxiv.org/abs/2401.00000   # 收藏链接
sheaf search-index --rebuild                     # 可选：构建 Entry embedding，会调用提供商
sheaf search "transformer architecture"          # 混合搜索；降级时给出诊断
sheaf crystallize AI                             # 可选：结晶知识卡片
```

无需 Sheaf 账号或托管存储。语料本地保存 —— 项目目录内为 `./data/`，否则为 `~/.sheaf/data`，格式 Markdown + JSON；模型推理发送到你配置的提供商。可用 `SHEAF_DATA_DIR` 覆盖数据路径。

> **Claude Code 上更快 —— 完全免安装：**
> ```bash
> claude mcp add sheaf -- uvx --from sheaf-ai sheaf-mcp
> ```
> `uvx` 是 npm 风格的运行器（`brew install uv` / `winget install astral-sh.uv`）。随后用 `uvx --from sheaf-ai sheaf config setup` 配置 Key。

## 为什么需要 Sheaf？

收藏的文章、论文、仓库和教程很难直接进入 Agent 工作流。书签能告诉你网页在哪里，
却不能告诉 Agent 哪个来源支持某个结论，也不能解释这个结论后来为什么改变。

当前 Alpha 已有采集、检索和生成带来源链接的卡片等基础。下一步要验证它们能否帮助完成真实任务、减少重复查找，并保留来源观点与用户判断的区别。开始使用已有来源不需要先攒够收藏或生成卡片。

## 核心功能

| | 它做什么 |
|---|---|
| 🌾 **保存资料** | 粘贴链接或笔记，完成抓取、清洗、分类并保留来源。已有质量与来源判断是启发式线索，不是事实核查。 |
| 🔎 **找回资料** | 关键词和可选语义检索；索引过期或不可用会明确提示。 |
| 🤖 **接入已有 Agent** | 支持 MCP 的客户端可检索资料并读取原文；是否正确使用仍需在具体任务中检查。 |
| ✨ **按需生成卡片** | 把相关条目整理为带来源链接的卡片；原始条目可以直接使用。 |
| 🧭 **实验性版本治理** | 受约束的知识变更与不可变历史，和普通卡片生成分开；证据强度是启发式信号，不是概率。 |
| 🔒 **本地优先** | 知识文件保存在本地，无 Sheaf 账号和遥测；模型处理步骤使用你配置的提供商。 |

### 结晶 —— 把精选来源变成可复用主张

`sheaf crystallize` 把相关来源整理为可复用、可返回原文检查的卡片。
生成结果仍需按具体用途核查。以下是输出示例：

```
$ sheaf crystallize AI
✨ 5 张知识卡片已结晶:
  📌 RAG 面临检索相关性挑战
     RAG 系统高度依赖检索质量；错误会降低输出可靠性。
  📌 CRAG 框架提升 RAG 鲁棒性
     CRAG 引入检索评估器、网页搜索增强和文档分解。
```

每张 batch 卡片含 **证据溯源**（哪些来源贡献了它）、**主题归属**、**标签**。用 `sheaf crystallize --semantic "查询"` 跨所有卡片做向量语义搜索。

<details>
<summary>技术保证与实验依据</summary>

实验性的证据治理路径更严格。ledger schema 3 会验证 `quote` 或字符区间证据身份，
并可重放旧 ledger。`evidence-rule-v3` 只按相同 `source_key`、可信的完整 SHA-256
evidence digest、或已持久化的 `exact` / `near_duplicate` 关系形成 non-duplicate
group；普通自声明 provenance 绝不能覆盖去重。这些 group 还不等于可信的独立确认：
`independent_source_count` 仍保守记为 `1`，corroboration bonus 关闭。已有本地追加式
provenance registry，将管理员声明绑定到具体 Entry、来源与完整 evidence digest；
缺失、冲突、损坏或撤销记录时降到 tier `U`。有效记录可授予来源等级、primary/authority
范围和纠正关系；SHA-256 链提供完整性线索，不构成身份认证。v1/v2 历史评分按原算法重放。
它不宣称 LLM 决策策略或置信概率已经校准：

```bash
sheaf memory apply --request transition.json
sheaf memory snapshot --topic "Agent memory"
sheaf memory history --topic "Agent memory"
```

已实现能力与拟议能力的边界见[产品与评测提案](docs/EVIDENCE-GOVERNED-MEMORY-PROPOSAL.md)及冻结的 [G0-G3 协议](evals/evidence-governed-memory/PROTOCOL.md)。
可用 `python evals/evidence-governed-memory/run_executor_acceptance.py` 独立复现
确定性执行器验收；它验证来源约束、幂等、冲突保留、官方更正与审计历史，但不冒充
LLM 策略质量 benchmark。

SPLIT 和 NOOP 已有 preview-first 的可审计 decision trace。生产 evidence-ledger
adapter 通过一次文件替换提交 SPLIT 的 UPDATE + CREATE、receipt 和 head 检查；
执行 manifest 绑定具体操作、证据、目标 head、策略版本与幂等身份，防止重试换计划。
decision 与 evidence ledger 仍是独立文件，可通过 receipt-first 对账恢复，不是跨文件事务。

[架构与评测约定](docs/ARCHITECTURE-AND-EVALUATION.md)说明支撑算法、成熟度和比较性
结论仍需完成的实验。产品开发顺序以[当前计划](docs/NEXT-PHASE-PLAN.md)为准。

### 检索证据快照

首份冻结检索实验包含 22 条 Entry 和 36 个 query。manifest 锁定 corpus、query 与
evaluator-only qrels 的 hash，并在加载 qrels 前产生 ranking。已入库的 local-LSA 是
经典 TF-IDF/SVD 基线，不是神经 embedding 结果。dev 选中
`linear-0.25 @ 0.4`；held-out Recall@5 为 `0.9375`、MRR `1.0`、nDCG@5 `0.9498`、
no-answer FPR `1.0`。它没有优于 keyword，也没有解决 abstention。真实 embedding 因
缺少凭据尚未运行。详见[冻结检索报告](evals/retrieval-frozen/README.md)。

当前 relevance gate 是 backend/version-specific 实验信号，不是概率或通用阈值；
语义检索降级时，生产路径回到 keyword coverage 标尺。

</details>

## 接入你的 Agent

`sheaf setup` 为每个工具写入正确格式的 MCP 配置，并部署内置 skill / 说明书，让 agent 知道如何使用 Sheaf：

```bash
sheaf setup --target claude          # ~/.claude.json + ~/.claude/skills/sheaf-guide.md
sheaf setup --target codex           # ~/.codex/config.toml + ~/.codex/AGENTS.sheaf.md
sheaf setup --target cursor          # .cursor/mcp.json（另有 windsurf、workbuddy）
sheaf setup                          # 自动检测当前环境 + 已安装的 agent
sheaf setup --target codex --dry-run # 预览但不写入
```

> **MCP 与 skill 一体安装。** `sheaf setup` 一次部署 MCP 服务器 **和** skill —— skill 告诉 agent *何时* 主动捕获笔记、何时从知识库召回,所以它不是可有可无的装饰。优先用它,而非裸 `uvx` 一行(那只接 MCP、不带 skill)。要一次全搞定(key + MCP + skill + 健康检查)用 `sheaf init --auto`。

MCP 服务器默认暴露 **4 个核心工具** —— `sheaf_collect`、`sheaf_search`、`sheaf_crystallize`、`sheaf_get_card` —— 刻意保持默认上下文精简。其余 10 个（含 3 个 evidence-memory 工具）仍可通过 CLI 或显式 MCP `tools/call` 调用；设 `SHEAF_MCP_TOOLS=all` 可暴露全部 14 个。完整工具矩阵与设计理由见 [Issue #91](https://github.com/zhelunSun/sheaf-ai/issues/91)，接入细节见 [docs/mcp-setup.md](docs/mcp-setup.md)。

Agent 还可经 **MCP Resources** 只读**浏览**知识库 —— `sheaf://entries/recent`、`sheaf://entries/{id}`、`sheaf://stats`、`sheaf://tags`（`resources/list` / `resources/read`）。规范见 [docs/agent-query-spec.md](docs/agent-query-spec.md)。

## 命令一览

```bash
sheaf help                       # 分组命令总览
sheaf collect <url> | --text "…" # 收藏链接，或保存笔记（标记为 note）
sheaf search <query>             # Entry 混合搜索（显示 id 与降级诊断）
sheaf search-index --rebuild     # 显式构建或重建 Entry 向量索引
sheaf list [--page N]            # 浏览条目，分页
sheaf get <id>                   # 查看一条条目完整详情
sheaf crystallize <topic>        # 从主题结晶知识卡片
sheaf memory apply --request FILE # 应用经过校验的证据转移
sheaf memory snapshot            # 查看 active / contested 状态
sheaf memory history             # 审计不可变转移历史
sheaf stats | tags | weekly | insights | urgent
sheaf mcp                        # 启动 MCP 服务器（stdio）
```

每个命令的参数见 `sheaf <命令> --help`。

<details>
<summary><b>Agent 友好：语义化退出码</b></summary>

Sheaf 返回带类型的退出码，让 Agent 可按错误类型编程式分支处理，无需解析 stderr：

| 码 | 名称 | 含义 |
|----|------|------|
| 0 | `SUCCESS` | 操作成功完成 |
| 1 | `PARTIAL` | 部分成功（如批量操作有跳过） |
| 2 | `DUPLICATE` | 条目已存在（去重跳过） |
| 3 | `QUALITY` | 内容质量门禁未通过 |
| 4 | `NETWORK` | 网络连接或 API 调用失败 |
| 5 | `CONFIG` | API key 缺失、URL 无效或配置错误 |
| 6 | `LLM` | LLM API 失败（限流、响应异常） |
| 7 | `STORAGE` | 文件 I/O 或存储故障 |

`--json` 模式下，错误负载含 `exit_code`、`exit_code_name`、`error_type`、`hint` 字段，便于程序化内省。
</details>

## 隐私 & 本地优先

**你的持久化语料留在本机；推理去向由你选择的模型提供商决定。**

- 所有内容本地存储 —— 项目目录内为 `./data/`，否则为 `~/.sheaf/data`（可用 `SHEAF_DATA_DIR` 覆盖）
- LLM 调用发送到**你选择的** API 提供商 —— 不经 Sheaf 中转
- 无遥测、无分析、无账号
- 开放的本地 Markdown 和 JSON/JSONL 文件，可直接读取；受支持的导出与恢复范围见[功能计划](docs/PRODUCT-FEATURES.md#pf-06--export-and-restore-a-minimal-local-library)。

## 配置

推荐用 `sheaf config setup` —— 交互式、OS 无关，Key 安全存入 `~/.sheaf/config.json`。支持任何 OpenAI 兼容端点：

| 提供商 | Key 环境变量 | 默认模型 |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `gpt-4o` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-chat` |
| SiliconFlow | `SILICONFLOW_API_KEY` | `deepseek-ai/DeepSeek-V3.2` |
| Together AI | `TOGETHER_API_KEY` | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` |

```bash
sheaf config use deepseek        # 切换默认提供商
sheaf config list                # 查看已配置的提供商
```

<details>
<summary><b>高级：环境变量 / <code>.env</code>（CI 或临时使用）</b></summary>

Sheaf 会自动读取工作目录下的 `.env` 文件（见 [.env.example](.env.example)）。也可在 shell 中设置 —— 唯一的 OS 差异只是语法：

```bash
# macOS / Linux
export OPENAI_API_KEY=sk-...
# Windows PowerShell:   $env:OPENAI_API_KEY="sk-..."
# Windows CMD:          set OPENAI_API_KEY=sk-...
export OPENAI_BASE_URL=https://api.openai.com/v1   # 可选 —— 非 OpenAI 端点用
```
</details>

## 架构

```
来源 → 收藏与规范化 → Entry → 检索 → Agent
                         ↓
                  来源集合 → 结晶 → KnowledgeCard
                         ↓
新证据 → 受约束状态转移 → 事件账本 → 当前卡片版本
```

| 模块 | 职责 |
|---|---|
| `sheaf_ai/` | 核心 — 管道、存储、搜索、CLI、MCP 服务器、结晶引擎 |
| `sheaf_cards/` | 知识卡片引擎 — 基础类型、向量嵌入、生成 |
| `prompts/` | LLM 提示模板（分类、摘要、结晶） |
| `data/` | 本地知识库（JSONL + Markdown，已 gitignore） |

应用层、领域层、基础设施边界和分阶段开发计划见
[架构与评测约定](docs/ARCHITECTURE-AND-EVALUATION.md)。

## 系统要求

- **Python 3.10+**
- 一个 OpenAI 兼容的 API Key
- Playwright Chromium *（可选，用于 JS 重度网站）*：`pip install -e ".[browser]" && playwright install chromium`

## 开发

```bash
git clone https://github.com/zhelunSun/sheaf-ai.git && cd sheaf-ai
python -m pip install -e ".[dev]"
python -m pytest tests/ -q
python evals/core-algorithms/run_offline_eval.py --compact
python -m ruff check sheaf_ai/ tests/ sheaf_cards/
```

依赖通过 extras 管理：`.[dev]` 本地开发、`.[server]` HTTP API、`.[browser]` Playwright 抓取。

## 当前状态 & 浏览器扩展

Sheaf 处于早期 Alpha，已实现采集、检索和 Agent 接口；工程检查不能证明持续采纳。
当前重点是[低负担、来源可查的产品流程](docs/NEXT-PHASE-PLAN.md)：保存资料、在
真实任务中复用，并试验轻量阅读建议。比较性效果、用户价值和付费意愿仍待验证。

Chrome 扩展（`extension/`）提供任意网页的一键收藏与搜索：用 `sheaf serve` 启动本地 API，在 Chrome → 管理扩展 → 开发者模式中加载 `extension/`，然后 `Alt+Shift+S` 或右键任意页面 → "🌾 Collect with Sheaf"。

**试试看**：选一个正在处理的问题，保存几份相关来源，让 Agent 据此做一次比较或解释，检查返回的出处和结论是否有用。欢迎通过 Issue 或 Discussion 告诉我们阻碍和实际收益。

> ⭐ 如果 Sheaf 帮到了你，在 [GitHub](https://github.com/zhelunSun/sheaf-ai) 点个 Star 能帮更多人发现它。

## 许可证

[Apache 2.0](LICENSE)

---

<p align="center">
  <b>Sheaf</b> — 一束收获的麦穗，农人带到集市的基本单位。<br>
  数学中，<a href="https://en.wikipedia.org/wiki/Sheaf_(mathematics)">Sheaf</a> 将局部数据粘合为全局图景。<br>
  Sheaf 这个工具做的是同样的事：把精选来源聚拢成束，让你的 Agent 能够找回、核验和复用。
</p>
