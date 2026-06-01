# Sheaf Agent-Native 设计原则升级建议

> Date: 2026-06-01 | Author: Jarvis | Status: Draft v0.1 — 待 Sir 审阅
> Context: Sir 提出"既然面向Agent，是否需要更激进大胆的设计"

---

## 0. 核心问题

**当前状态**: Sheaf 按 CLI（人类用户）的规则设计——单条操作、交互式提示、视觉反馈（emoji/color/进度条）。

**矛盾**: 主要用户是 Agent，不是人类。Agent 需要：
- 批量操作，不要一条条来
- 结构化 JSON 输出，不要彩色文字
- 幂等接口，不要"你确定吗"的交互提示
- 编程式错误处理，不要 try-catch-and-print

**结论**: 需要从 CLI-first 转向 **Agent-first, CLI-compatible** 的设计原则。

---

## 1. 设计原则对比

| 维度 | CLI-First（当前） | Agent-First（建议） | 优先级 |
|------|-------------------|---------------------|--------|
| **输出格式** | 彩色文本 + emoji | JSON by default, text with `--human` flag | 🔴 P0 |
| **批量操作** | 单条处理 | `sheaf collect --batch urls.txt` 或 MCP 数组参数 | 🔴 P0 |
| **错误处理** | print + exit(1) | 结构化 JSON 错误体 + 退出码语义 | 🔴 P0 |
| **静默模式** | 大量 print | `--quiet` / `SHEAF_QUIET=1` 抑制所有非结果输出 | 🟡 P1 |
| **进度反馈** | 进度条 | 无（或 JSON Lines 流式输出） | 🟡 P1 |
| **幂等性** | 有去重但不保证 | `--idempotent` flag + 确定性ID | 🟡 P1 |
| **配置发现** | 交互式 `config setup` | 环境变量优先 + 自动检测 + 零配置启动 | 🔴 P0 |
| **数据路径** | CWD/data/ | `~/.sheaf/data/` 全局默认 + 项目级覆盖 | 🟡 P1 |
| **MCP Resources** | 无 | MCP protocol resources 支持数据浏览 | 🟡 P1 |
| **Webhook/回调** | 无 | `--on-complete <url>` 异步通知 | 🔵 P2 |

---

## 2. 六项激进升级建议

### 🔴 A. JSON-First 输出（P0）

**现状**: CLI 默认输出彩色文本，需要 `--json` 才输出 JSON。MCP 输出 JSON 但混杂 stderr print。

**建议**:
```python
# 默认行为改为：检测是否在 TTY
import sys
IS_TTY = sys.stdout.isatty()

# 非TTY（Agent/pipe）→ 自动 JSON 输出
# TTY（人类终端）→ 保持彩色文本
```

**影响**: 零破坏性——现有 `--json` 继续工作，新增自动检测。

**优先级**: 🔴 P0 — 这是 Agent 体验的基础。

---

### 🔴 B. 批量操作支持（P0）

**现状**: `sheaf collect` 只接受单个 URL。Agent 想一次收藏 10 篇文章需要调用 10 次。

**建议**:
```bash
# CLI: 从文件批量
sheaf collect --batch urls.txt --output results.jsonl

# MCP: 数组参数
{
  "tool": "sheaf_collect_batch",
  "arguments": {
    "urls": ["https://...", "https://...", "https://..."],
    "concurrency": 3,
    "on_error": "continue"  # or "stop"
  }
}
```

**实现成本**: 中 — 需要批量 pipeline + JSONL 输出 + 错误聚合。

---

### 🔴 C. 结构化错误 + 退出码语义（P0）

**现状**: 错误时 print 文本 + exit(1)，Agent 难以区分错误类型。

**建议**:
```python
# 退出码语义
EXIT_SUCCESS = 0
EXIT_PARTIAL = 1    # 部分成功（批量操作）
EXIT_DUPLICATE = 2  # 去重跳过
EXIT_QUALITY = 3    # 质量门禁
EXIT_NETWORK = 4    # 网络错误
EXIT_CONFIG = 5     # 配置缺失
EXIT_LLM = 6        # LLM API 失败
EXIT_STORAGE = 7    # 存储错误

# JSON 错误体（始终输出到 stdout）
{
  "ok": false,
  "error": {
    "code": "QUALITY_GATE",
    "message": "Image-heavy article (87% images)",
    "hint": "Use --force to override",
    "stage": "quality",
    "url": "https://..."
  },
  "exit_code": 3
}
```

---

### 🟡 D. 零配置启动（P1）

**现状**: 安装后需要 `sheaf config setup` 配置 API key，否则核心功能不可用。

**Agent 场景**: Agent 安装 Sheaf 后应该**立刻能用**，API key 通过环境变量传入。

**建议**:
1. **环境变量优先**: `SHEAF_API_KEY` / `SHEAF_PROVIDER` 直接生效
2. **免费 tier 自动配置**: 内置 SiliconFlow 免费 token（限流），装完即用
3. **降级模式**: 无 API key 时也能 collect（存储原文） + search（关键词），只是不分类不摘要
4. **sheaf doctor 命令**: 一键诊断配置完整性

```python
# config.py 新增
FREE_TIER_KEY = os.environ.get("SHEAF_FREE_TIER", "builtin-limited-token")
EFFECTIVE_KEY = os.environ.get("SHEAF_API_KEY") or FREE_TIER_KEY
```

---

### 🟡 E. 全局数据目录 + 项目级覆盖（P1）

**现状**: `data/` 默认在 CWD，不同目录运行 = 不同知识库。

**建议**:
```python
# 查找顺序
1. SHEAF_DATA_DIR 环境变量
2. .sheaf-data/ in CWD（项目级）
3. ~/.sheaf/data/（全局默认）
```

**好处**: Agent 只需配置一次，所有项目共享知识库；特殊项目可独立。

---

### 🟡 F. MCP Resources + Sampling（P1）

**现状**: MCP 只有 tools，没有 resources 和 sampling。

**建议**:
```json
// resources: 让 Agent 浏览知识库结构
{
  "uri": "sheaf://entries/recent",
  "name": "Recent entries",
  "mimeType": "application/json"
}

// resources: 条目详情
{
  "uri": "sheaf://entries/2026-06-01_58fb4a92",
  "name": "Entry detail",
  "mimeType": "application/json"
}

// sampling: 让 MCP server 向 Agent 请求 LLM 能力
// （减少自身 API key 依赖，借用宿主 Agent 的 LLM）
```

---

## 3. 实施路线

### Phase 1: Quick Wins（1-2 天）
- [ ] A. JSON-First: 自动 TTY 检测
- [ ] C. 结构化错误: 退出码语义 + JSON 错误体
- [ ] D. 零配置: 环境变量优先 + 降级模式

### Phase 2: 批量 + 全局（3-5 天）
- [ ] B. 批量操作: `--batch` + `sheaf_collect_batch` MCP tool
- [ ] E. 全局数据目录: 三层查找 + `~/.sheaf/`

### Phase 3: MCP 增强（1 周）
- [ ] F. MCP Resources: `sheaf://` URI scheme
- [ ] MCP Sampling: 借用宿主 Agent LLM
- [ ] `sheaf doctor`: 配置诊断命令

---

## 4. Agent-Native 设计哲学总结

> **"CLI 是 Sheaf 的调试界面，MCP 才是主界面。"**

| 原则 | 含义 |
|------|------|
| **JSON by default** | 除非检测到人类终端，否则输出 JSON |
| **Batch over single** | 每个操作都应支持批量 |
| **Zero-config for Agents** | 环境变量 > 配置文件 > 交互式设置 |
| **Structured errors** | 错误是数据，不是文本 |
| **Idempotent** | 同一输入，同一输出，可安全重试 |
| **Graceful degradation** | 缺 LLM key 就降级，不要拒绝服务 |
| **Stateless MCP** | 每个 MCP 调用自包含，不依赖 session state |

---

*Jarvis · 2026-06-01 · Draft for Sir review*
