# Sheaf v0.4.0a0 自动化冒烟测试报告

> Date: 2026-06-01 23:15 | Tester: Jarvis (自动化) | Env: Windows 11, Python 3.12.7

## 1. 测试套件运行结果

### 总体
| 指标 | 值 |
|------|-----|
| Total | 486 tests |
| ✅ Passed | 466 (95.9%) |
| ⏭ Skipped | 13 (2.7%) |
| ❌ Failed | 1 (0.2%) |
| ⚠ Warnings | 1 (cache perm) |
| 耗时 | 4.58s |

### 失败详情
| Test | 原因 | 严重度 |
|------|------|--------|
| `test_pdf_collector.py::TestFetchPdfFromBytes::test_invalid_pdf_bytes` | pypdf 抛出 `PdfStreamError` 而非返回空结果 | P2 — 异常处理不够健壮 |

**修复建议**: 在 `collectors/pdf.py:50` 的 `_extract_with_pypdf2` 中捕获 `PdfStreamError`：
```python
try:
    reader = PdfReader(io.BytesIO(content))
except (PdfStreamError, Exception):
    return "", {"pages": 0, "method": "pypdf2", "error": "invalid PDF"}
```

### Skipped 测试 (13个)
均为需要 API key 或网络的测试（预期行为）。

---

## 2. CLI 命令可达性测试

通过代码分析 + `--help` 验证，所有子命令注册正确：

| 命令 | 状态 | 参数 | 备注 |
|------|------|------|------|
| `sheaf --version` | ✅ | - | 输出 `Sheaf v0.4.0a0` |
| `sheaf --help` | ✅ | - | 完整帮助文本 |
| `sheaf collect <url>` | ✅ | `--force`, `--json` | 裸URL自动路由到此 |
| `sheaf search <query>` | ✅ | nargs="+" | 支持多词搜索 |
| `sheaf crystallize <topic>` | ✅ | `--list/--show/--delete/--stats/--semantic/--rebuild-embeddings/--format/--fields` | 功能最丰富的子命令 |
| `sheaf stats` | ✅ | - | 统计信息 |
| `sheaf weekly` | ✅ | - | 周报 |
| `sheaf insights` | ✅ | - | 跨主题关联 |
| `sheaf tags` | ✅ | - | 标签统计 |
| `sheaf trends` | ✅ | - | 趋势 |
| `sheaf urgent` | ✅ | - | 紧急事项 |
| `sheaf reclassify` | ✅ | `--dry-run` | 旧条目迁移 |
| `sheaf mcp` | ✅ | - | MCP stdio 服务器 |
| `sheaf init` | ✅ | - | 首次引导 |
| `sheaf setup` | ✅ | `--target/--data-dir/--dry-run/--show-config` | 自动配置MCP |
| `sheaf serve` | ✅ | `--host/--port` | HTTP API |
| `sheaf config` | ✅ | `setup/set-key/list/use/remove/--provider/--api-key/--base-url/--model` | 配置管理 |

---

## 3. Pipeline 代码分析（无API key路径）

### 3.1 数据目录初始化
- **路径**: `config.py:55-57` `ensure_data_dirs()`
- **行为**: 自动创建 `data/`, `data/entries/`, `data/summaries/`, `data/raw/`
- **问题**: 默认在 CWD 创建，用户在不同目录运行会创建多套数据
- **影响**: 🟡 中 — 用户可能困惑"数据去哪了"
- **建议**: 支持 `~/.sheaf/data/` 作为全局默认（通过 `SHEAF_DATA_DIR`）

### 3.2 裸URL自动路由
- **路径**: `cli.py:122-127`
- **行为**: `sheaf https://example.com` 自动识别为 `sheaf collect`
- **状态**: ✅ 优雅的 UX

### 3.3 去重检查
- **路径**: `pipeline.py:146-159`
- **行为**: URL + 文本哈希双重去重
- **状态**: ✅ 无需 API key

### 3.4 质量门禁
- **路径**: `pipeline.py:184-209`
- **行为**: 图片密度检测 + 内容质量评估
- **状态**: ✅ 无需 API key

### 3.5 MCP Server (stdio)
- **路径**: `mcp_server.py`
- **工具**: 9个（search/list/get/urgent/correct/collect/crystallize/list_cards/get_card）
- **协议**: JSON-RPC 2.0 over stdio
- **状态**: ✅ 协议正确，测试覆盖 `tests/test_mcp.py` + `tests/test_mcp_e2e.py`

### 3.6 配置管理
- **路径**: `settings.py` + `cli.py:312-376`
- **行为**: 多 provider 支持，交互式设置，`~/.sheaf/config.json` 存储
- **状态**: ✅ 健壮

---

## 4. MCP 工具接口详情

| 工具 | 输入参数 | Agent友好度 | 备注 |
|------|----------|------------|------|
| `sheaf_search` | query, limit, mode, deep, alpha | ✅ 高 | 3种搜索模式，结构化输出 |
| `sheaf_list` | category, limit | ✅ 高 | 简单过滤 |
| `sheaf_get` | entry_id | ✅ 高 | 精确查询 |
| `sheaf_urgent` | (无) | ✅ 高 | 零参数 |
| `sheaf_correct` | entry_id, corrections, user_note | ✅ 高 | 纠错反馈 |
| `sheaf_collect` | url, force | ✅ 高 | 一键收藏 |
| `sheaf_crystallize` | topic | ✅ 高 | 知识结晶 |
| `sheaf_list_cards` | topic | ✅ 高 | 卡片列表 |
| `sheaf_get_card` | card_id | ✅ 高 | 卡片详情 |

---

## 5. 发现的问题清单

| # | 问题 | 严重度 | 路径 | 修复建议 |
|---|------|--------|------|---------|
| P1 | PDF collector 对无效字节未优雅处理 | P2 | `collectors/pdf.py:50` | 捕获 PdfStreamError |
| P2 | 数据目录默认在 CWD | P2 | `config.py:33` | 支持 `~/.sheaf/data/` 全局默认 |
| P3 | `sheaf init` 尝试抓取示例文章需要API key | P1 | `onboarding.py` | 应提供离线模式或跳过选项 |
| P4 | pytest cache 写入权限问题 | P3 | `.pytest_cache/` | 加入 `.gitignore` 或使用 tmp |
| P5 | 13个 skipped 测试无 skip reason 标注 | P3 | `tests/` | 使用 `@pytest.mark.skip(reason="...")` |

---

## 6. Agent-Native 体验评估

### 当前优势
1. **CLI 子命令体系完整** — 16 个子命令覆盖全生命周期
2. **MCP 工具接口规范** — 9 个工具，JSON Schema 完整
3. **结构化 JSON 输出** — `--json` flag 支持机器可读
4. **裸 URL 快捷方式** — 降低操作摩擦

### 当前不足（Agent 视角）
1. **缺少批量操作** — `sheaf collect` 只能单 URL，Agent 想批量收藏
2. **缺少 `--quiet` 模式** — 大量 `print()` 干扰 Agent 解析输出
3. **错误恢复不完整** — 某些失败（如 PDF）抛异常而非返回结构化错误
4. **缺少 `sheaf export`** — Agent 需要导出知识库到外部系统
5. **MCP 缺少 `resources` 支持** — Agent 无法通过 MCP 协议浏览数据目录
6. **无进度回调** — 长 pipeline（collect + crystallize）Agent 无法获取进度

---

*Jarvis · 2026-06-01 23:15 · Automated Smoke Test*
