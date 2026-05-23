# Obsidian 生态融合路径调研

> Created: 2026-05-23 | Issue: https://github.com/zhelunSun/sheaf-ai/issues/19
> Status: Research v1.0

---

## 1. 定位分析：Sheaf vs Obsidian

### 1.1 核心差异

| 维度 | Sheaf | Obsidian |
|------|-------|----------|
| **核心功能** | AI 自动采集 + 结构化提取 | 本地笔记 + 知识关联 |
| **输入方式** | URL → AI 自动处理 | 手动撰写 / 粘贴 |
| **输出格式** | 结构化知识卡片（JSON/YAML） | 自由格式 Markdown 笔记 |
| **知识加工** | 自动分类、打标签、摘要 | 人工组织（标签、链接、文件夹） |
| **存储方式** | 本地文件 + 可选云端同步 | 纯本地 Markdown 文件 |
| **可视化** | CLI（未来 App） | Graph View、Backlinks、Canvas |
| **价格** | 开源免费（知识市场收费） | 个人免费，Sync/Publish 付费 |

### 1.2 互补关系（不是竞争）

```
用户工作流：

  浏览器 ──→ [Sheaf 采集] ──→ 知识卡片 ──→ [Obsidian 管理] ──→ 深度知识库
                                   ↓                              ↓
                              自动分类/标签                    手动关联/洞察
                                   ↓                              ↓
                              [知识市场] ←───────────── 创作者变现
```

**Sheaf = 上游采集引擎**（自动化、AI 处理）
**Obsidian = 下游管理工具**（可视化、关联、长期维护）

两者在「知识工作者的完整工作流」中是上下游关系，不冲突。

---

## 2. Obsidian 集成技术方案

### 2.1 三大集成路径

#### 路径 A：Local REST API（推荐 MVP 方案）

**插件**: [obsidian-local-rest-api](https://github.com/coddingtonbear/obsidian-local-rest-api)
**原理**: 在 Obsidian 内运行 HTTPS 服务器，暴露 RESTful API
**能力**:
- `POST /vault/{path}` — 创建/更新笔记
- `GET /vault/{path}` — 读取笔记
- `PATCH /vault/{path}` — 追加内容
- `DELETE /vault/{path}` — 删除笔记
- 支持 Markdown 和 JSON 格式

**集成方式**:
```bash
# Sheaf collect → 自动推送到 Obsidian
sheaf collect https://example.com/article --obsidian

# 底层调用
# POST https://localhost:27124/vault/Sheaf%20Cards/2026-05-23_article-title.md
# Body: Markdown 格式的知识卡片内容
```

**优势**: 零开发成本、用户只需安装插件、Sheaf 侧只需 HTTP 调用
**劣势**: 需要用户安装插件 + 配置 API Key、Obsidian 必须运行

#### 路径 B：直接文件系统写入（最简方案）

**原理**: Sheaf 直接将知识卡片写入 Obsidian Vault 目录
**要求**: 用户指定 Vault 路径

**集成方式**:
```bash
sheaf config set obsidian.vault_path ~/Documents/MyVault
sheaf collect https://example.com/article --to-obsidian
# → 写入 ~/Documents/MyVault/Sheaf/2026-05-23_article-title.md
```

**优势**: 零依赖、最快实现
**劣势**: 无 API 校验、可能和 Obsidian 的文件监控冲突

#### 路径 C：Obsidian 插件（深度集成方案）

**原理**: 开发 Obsidian 社区插件，在 Obsidian 内直接调用 Sheaf
**功能**:
- 侧边栏面板：输入 URL → 一键采集
- 命令面板：`Sheaf: Collect URL`
- 采集历史浏览
- 知识卡片预览 + 编辑

**技术栈**: TypeScript + Obsidian API + 调用 Sheaf CLI/HTTP
**开发周期**: 2-4 周（MVP）

**优势**: 最佳用户体验、双向同步
**劣势**: 需要独立开发和维护插件

#### 路径 D：URI Scheme（轻量交互方案）

**原理**: Obsidian 支持 `obsidian://` URI scheme
**Advanced URI 插件**: 支持更丰富的操作（创建笔记、打开文件、搜索）

```bash
# Sheaf 完成采集后，打开 Obsidian 显示结果
obsidian://advanced-uri?vault=MyVault&filepath=Sheaf%2Fcard.md
```

**优势**: 零开发、轻量
**劣势**: 功能有限，只能打开/创建，不能复杂交互

### 2.2 推荐融合路线图

```
Phase 1 (v0.5 Alpha)          Phase 2 (v1.0 Beta)         Phase 3 (v2.0)
┌──────────────────┐    ┌──────────────────────┐    ┌────────────────────┐
│ 文件系统写入      │    │ Local REST API 集成   │    │ Obsidian 社区插件   │
│ sheaf collect     │    │ sheaf --obsidian      │    │ 侧边栏面板         │
│   --to-obsidian   │   │ 自动推送到 Vault      │   │ 一键采集+预览       │
│                   │    │                       │    │ 双向同步            │
│ 实现: 1 天        │    │ 实现: 3-5 天          │    │ 实现: 2-4 周        │
│ 依赖: 用户指定路径 │    │ 依赖: REST API 插件   │    │ 依赖: 插件审核流程   │
└──────────────────┘    └──────────────────────┘    └────────────────────┘
```

---

## 3. 商业价值评估

### 3.1 为什么做 Obsidian 集成？

| 理由 | 分析 |
|------|------|
| **用户重叠** | Obsidian 用户 = 知识密集型 = Sheaf 目标用户 |
| **引流渠道** | Obsidian 社区插件市场 = 30M+ 用户 |
| **信任背书** | 在 Obsidian 插件市场上线 = 产品可信度 |
| **互补定位** | 不与 Obsidian 竞争，而是增强其价值 |
| **数据飞轮** | 更多用户 → 更多知识包 → 更好的知识市场 |

### 3.2 竞品在 Obsidian 生态的布局

| 工具 | Obsidian 集成方式 | 状态 |
|------|-----------------|------|
| Readwise | 官方插件 + 自动同步 | ✅ 成熟 |
| Omnivore | 官方插件（已关闭） | ❌ 已关 |
| Matter | 插件 | ✅ 运营中 |
| Notion | 无官方集成 | — |
| Cubox | 社区插件 | ✅ 小众 |

**Sheaf 的差异化**：AI 自动分类/摘要 + 结构化知识卡片 + 未来知识市场。Readwise 只做高亮同步，不做 AI 处理。

---

## 4. 技术实现建议

### Phase 1: 文件系统写入（Alpha 阶段可做）

1. 新增 CLI 参数 `--to-obsidian [vault_path]`
2. 知识卡片转为 Obsidian-friendly Markdown：
   - Frontmatter: `tags`, `source`, `date`, `sheaf_id`
   - 正文: 标题 + 摘要 + 分类 + 原始标签
   - 底部: 来源 URL + 采集时间
3. 写入 `{vault}/Sheaf Inbox/{date}_{title}.md`
4. 保留原始 JSON/YAML 卡片

### Phase 2: Local REST API 集成（Beta 阶段）

1. `sheaf config set obsidian.api_url https://localhost:27124`
2. `sheaf config set obsidian.api_key <key>`
3. `sheaf collect URL --obsidian` → 自动 POST 到 Vault
4. 支持 append 模式：同主题卡片追加到同一笔记

### Phase 3: Obsidian 社区插件（v1.0+）

1. TypeScript 插件项目初始化
2. Settings Tab: 配置 Sheaf CLI 路径 / API 连接
3. 侧边栏: 采集历史 + 知识卡片浏览
4. Command: `Sheaf: Collect URL from clipboard`
5. 提交 Obsidian 社区插件审核

---

## 5. 结论

| 建议 | 详情 |
|------|------|
| **做不做？** | ✅ 做，是 Sheaf 用户增长的关键渠道 |
| **何时做？** | Phase 1 跟随 Alpha，Phase 2 跟随 Beta，Phase 3 跟随 v1.0 |
| **先做什么？** | Phase 1（文件系统写入）成本最低、价值最大 |
| **风险** | 低 — Obsidian 生态开放、API 稳定、社区活跃 |

---

*Next action: Phase 1 实现时，创建对应 dev Issue*
