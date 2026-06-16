# Sheaf 上线前人工测试 — 2026-06-15 晚

> **目的**: 模拟一个全新用户,从零安装到跑通核心功能,验证上线体验。
>
> **预计耗时**: 20-30 分钟
>
> **原则**: 不搞复杂 Profile,线性走一遍,功能正常 + 输出合理就过。

---

## Step 0: 模拟全新环境(2 分钟)

```bash
# 建一个干净的测试目录(别在 sheaf-ai 仓库里跑,模拟真实用户)
mkdir D:\sheaf-fresh-test
cd D:\sheaf-fresh-test

# 建虚拟环境
python -m venv .venv
.venv\Scripts\activate

# 从 PyPI 安装(跟真实用户一模一样)
pip install sheaf-ai

# 验证装上了
sheaf --version
sheaf --help
```

**过线标准**:
- [ ] `sheaf --version` 输出 `Sheaf v0.6.0`(或更高)
- [ ] `sheaf --help` 列出 collect/search/crystallize/matrix 等命令
- [ ] 全过程 < 2 分钟,无报错

---

## Step 1: 初始化 + 健康检查(1 分钟)

```bash
sheaf init
sheaf doctor
```

**过线标准**:
- [ ] `sheaf init` 成功,生成配置
- [ ] `sheaf doctor` 输出 `All checks passed! 🎉` 或清晰提示缺什么

---

## Step 2: 配 API Key(如果你要测结晶功能)

crystallize 需要 LLM,**Sheaf 不绑定任何特定 Provider**——支持 OpenAI / DeepSeek / SiliconFlow / Together / Groq 等 OpenAI 兼容 API。任选一个配:

```bash
# 通用方式(Sheaf 会自动检测):
set SHEAF_API_KEY=你的key

# 或用某个 Provider 的环境变量(任选其一):
set OPENAI_API_KEY=sk-xxx
set DEEPSEEK_API_KEY=ds-xxx
set SILICONFLOW_API_KEY=sk-xxx

# 或用交互式向导(推荐,会引导你选 provider):
sheaf config setup

# 或直接指定 provider 配 key:
sheaf config set-key --provider openai
```

**没 key 也能测** collect/search/stats,只是 crystallize 会降级。

---

## Step 3: 收藏 3 篇内容(5 分钟)⭐ 核心

测不同类型源,看抓取质量:

```bash
# arXiv 论文(学术源)
sheaf collect https://arxiv.org/abs/2401.15884

# 技术文档
sheaf collect https://docs.python.org/3/tutorial/index.html

# 中文技术文章
sheaf collect https://sspai.com/post/73145
```

**过线标准(人眼判断"差不多就行")**:
- [ ] 三篇都收藏成功,不报错
- [ ] arXiv 论文:标题对、摘要是 LLM 精炼的(不是原文一大坨)、标签合理
- [ ] Python 文档:抓到正文,有摘要
- [ ] 少数派文章:中文正常,不乱码

---

## Step 4: 搜索 + 浏览(2 分钟)

```bash
sheaf search "retrieval"
sheaf list
sheaf tags
sheaf stats
```

**过线标准**:
- [ ] search "retrieval" 能召回刚才收藏的 CRAG 论文
- [ ] list 显示 3 条收藏
- [ ] tags 显示自动提取的标签
- [ ] stats 显示条目数、主题数

---

## Step 5: 知识结晶 ⭐ 上线最大卖点(3 分钟)

```bash
sheaf crystallize "RAG"
sheaf insights
```

**过线标准(关键!)**:
- [ ] crystallize 输出一张**读得懂、有价值**的知识卡片
- [ ] 如果你觉得"也就那样,跟普通摘要没区别"——**上线前必须重新想 prompt**,这是 Sheaf 区别于普通剪藏工具的全部价值
- [ ] insights 能看到 3 篇文章之间的关联

---

## Step 6: 错误处理(1 分钟)

测 Agent 友好度:

```bash
sheaf collect 不存在的域名xxx.com
echo Exit code: %ERRORLEVEL%

sheaf collect https://arxiv.org/abs/2401.15884
echo Exit code: %ERRORLEVEL%
```

**过线标准**:
- [ ] 失败的 collect 退出码 ≠ 0
- [ ] 成功的 collect 退出码 = 0
- [ ] 错误信息是结构化的,不是 Python stack trace

---

## Step 7: MCP 联动(可选,5 分钟)

如果想测 MCP(WorkBuddy/Claude 等宿主集成),直接在对话里跟我说:

> "帮我用 sheaf 收藏 https://arxiv.org/abs/2306.05685"

我会调 MCP 工具,你观察结果跟 CLI 是否一致。

**过线标准**:
- [ ] MCP 调用成功
- [ ] 返回结果跟命令行一致

---

## 测完之后

### 全过 → 准备上线
- 决定版本号(v0.6.0 已打 tag,或直接 v0.6.1)
- README 补 Agent 安装提示词
- 准备发布物料

### 发现问题 → 告诉我
- 我分类 P0/P1/P2
- P0 立刻修,P1/P2 登记成 Issue

---

## 命令速查卡

```
sheaf --version              # 看版本
sheaf --help                 # 看所有命令
sheaf init                   # 初始化
sheaf doctor                 # 健康检查
sheaf collect <url>          # 收藏 ⭐
sheaf search <query>         # 搜索
sheaf crystallize <topic>    # 知识结晶 ⭐⭐
sheaf insights               # 关联分析
sheaf matrix <url>           # 矩阵分析(v0.6 新)
sheaf list                   # 列出所有
sheaf tags                   # 标签统计
sheaf stats                  # 数据统计
sheaf doctor --json          # 结构化健康检查
```

---

*清单 v2 — 简化版 | 2026-06-15*
