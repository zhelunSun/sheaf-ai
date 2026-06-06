#!/usr/bin/env python3
"""
Sheaf LLM-Driven Depth Test — 真实用户行为模拟

与脚本测试（固定 URL + 固定断言）互补，LLM 驱动测试模拟真实用户决策路径：
  1. LLM 生成自然语言意图（"我想收藏一篇关于 agent 的论文"）
  2. 执行 sheaf 命令
  3. LLM 评判结果质量（"这个摘要覆盖了核心观点吗？"）

用法:
  python tests/llm_depth_test.py                     # 默认 Profile A
  python tests/llm_depth_test.py --profile B          # 指定 Profile
  python tests/llm_depth_test.py --all                # 全部 3 个 Profile
  python tests/llm_depth_test.py --profile A --steps 5  # 限制步数
  python tests/llm_depth_test.py --dry-run             # 只生成意图不执行

输出:
  reports/llm-depth-test-YYYY-MM-DD.md
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ── 配置 ────────────────────────────────────────────────────────

REPORTS_DIR = Path(tempfile.gettempdir()) / "sheaf-llm-test-reports"
# reports dir created lazily in generate_report() to avoid sandbox issues

SHEAF_CMD = None  # Lazy-initialized in run_sheaf_command() to handle different envs


# ── Test Fixtures: 分层 URL 池 ──────────────────────────────────

class TestFixtures:
    """
    分层 URL 固定装置，替代 LLM 编造 URL。

    三层设计:
      - GOOD: 已验证可访问的真实 URL，保证 collect 有内容
      - EDGE: 预期会失败的 URL（404/超时/不存在），测试错误处理
      - KEYWORDS: 用于 search/crystallize 的真实关键词池

    用法:
      fixtures = TestFixtures.for_profile("A")
      url = fixtures.pick_url(category="arxiv")         # 已知好的 arXiv
      url = fixtures.pick_url(tier="edge")               # 故意坏掉的 URL
      kw  = fixtures.pick_keyword()                      # 随机搜索关键词
    """

    # ── Tier 1: 已知好 URL（按类别） ──
    GOOD_URLS: dict[str, list[str]] = {
        "arxiv": [
            "https://arxiv.org/abs/2401.15884",   # Vision-Language Models
            "https://arxiv.org/abs/2305.10601",   # AutoGen (multi-agent)
            "https://arxiv.org/abs/2302.04761",   # GPT-4 Technical Report
            "https://arxiv.org/abs/2306.05685",   # LLM Agents survey
            "https://arxiv.org/abs/2309.00071",   # Foundation Models for RS
            "https://arxiv.org/abs/2103.00020",   # DINO (self-supervised)
        ],
        "tech_blog": [
            "https://realpython.com/python-async-await/",
            "https://realpython.com/python-f-strings/",
            "https://martinfowler.com/articles/2024-ai-llm.html",
            "https://lilianweng.github.io/posts/2023-06-23-agent/",
            "https://huyenchip.com/2023/04/11/llm-engineering.html",
        ],
        "docs": [
            "https://docs.python.org/3/tutorial/index.html",
            "https://docs.djangoproject.com/en/5.0/intro/tutorial01/",
            "https://fastapi.tiangolo.com/tutorial/",
        ],
        "cn_tech": [
            "https://sspai.com/post/73145",
            "https://www.36kr.com/p/2396489581718661",
            "https://www.jiqizhixin.com/articles/2024-01-15-3",
        ],
    }

    # ── Tier 2: Edge case URL（预期失败） ──
    EDGE_URLS: list[str] = [
        "https://arxiv.org/abs/9999.99999",       # 不存在的 arXiv ID
        "https://httpbin.org/status/404",          # 404
        "https://httpbin.org/status/500",          # 500
        "https://nonexistent-domain-xyz.com/abc",  # DNS 失败
        "https://httpbin.org/delay/30",            # 超时
        "",                                         # 空 URL
        "just-plain-text-not-a-url",               # 不是 URL
    ]

    # ── 关键词池（按 Profile 领域） ──
    KEYWORDS: dict[str, list[str]] = {
        "A": ["multi-agent", "remote sensing", "transformer", "attention mechanism",
               "SAM", "segment anything", "vision language model", "知识蒸馏",
               "self-supervised learning", "geospatial AI"],
        "B": ["Docker", "Kubernetes", "Python performance", "system design",
               "microservices", "CI/CD", "web framework", "API design",
               "monitoring", "DevOps"],
        "C": ["AI agent", "startup", "product design", "tech trend",
               "大模型应用", "AI创业", "行业趋势", "产品设计",
               "用户增长", "商业化"],
    }

    # ── 空结果/垃圾输入关键词（edge case） ──
    GARBAGE_KEYWORDS: list[str] = [
        "xyzzyfoo12345",       # 无意义字符串
        "",                     # 空关键词
        "!!!!!!!!!!!",         # 特殊字符
        "a",                   # 单字符
    ]

    def __init__(self, profile_id: str, rng_seed: int | None = None):
        self.profile_id = profile_id
        self.rng = __import__("random").Random(rng_seed)
        self._good_flat = [u for urls in self.GOOD_URLS.values() for u in urls]

    @classmethod
    def for_profile(cls, profile_id: str, **kwargs) -> "TestFixtures":
        return cls(profile_id, **kwargs)

    def pick_url(self, category: str | None = None, tier: str = "good") -> str:
        """Pick a URL. tier='good' for known-good, tier='edge' for adversarial."""
        if tier == "edge":
            return self.rng.choice(self.EDGE_URLS)
        if category and category in self.GOOD_URLS:
            return self.rng.choice(self.GOOD_URLS[category])
        return self.rng.choice(self._good_flat)

    def pick_keyword(self, allow_garbage: bool = True) -> str:
        """Pick a search/crystallize keyword. ~15% chance of garbage if allowed."""
        if allow_garbage and self.rng.random() < 0.15:
            return self.rng.choice(self.GARBAGE_KEYWORDS)
        return self.rng.choice(self.KEYWORDS.get(self.profile_id, self.KEYWORDS["A"]))

    def should_try_edge(self, probability: float = 0.2) -> bool:
        """Should this step attempt an edge-case input? Default ~20%."""
        return self.rng.random() < probability


# ── Profile 定义 ────────────────────────────────────────────────

PROFILES = {
    "A": {
        "name": "博士生（AI/遥感方向）",
        "persona": """你是一个 AI/遥感方向的博士生，正在写关于多智能体遥感分析系统的博士论文。
你的工作流程：
- 日常浏览 arXiv、Google Scholar、微信公众号（AI 相关）
- 收藏论文、技术博客、行业分析
- 需要按主题分类和生成知识卡片辅助写作
- 会用中英文搜索，偏好英文技术内容
- 时间充裕但需要高质量整理

你的性格：学术严谨，喜欢追根溯源，关注方法论和实验设计。
""",
        "domains": ["AI agents", "remote sensing", "multimodal learning", "earth observation"],
        "sample_queries": [
            "我想找一篇关于 LLM agent 的最新论文",
            "帮我搜一下遥感领域的多模态方法",
            "我想收藏这个微信公众号文章关于世界模型的",
            "搜索一下我之前收藏的关于 attention 机制的内容",
            "把这些 AI 相关的内容整理成知识卡片",
        ],
    },
    "B": {
        "name": "大厂上班族（技术方向）",
        "persona": """你是一个大厂技术员工，工作忙碌，每天只有碎片时间。
你的工作流程：
- 快速浏览技术博客、文档、Hacker News
- 收藏有用的技术文章，留待周末细读
- 用标签分类（前端/后端/DevOps/AI）
- 偶尔搜索之前收藏的内容
- 追求效率，不能容忍卡顿和复杂操作

你的性格：务实高效，喜欢简洁工具，讨厌多余步骤。
""",
        "domains": ["web development", "DevOps", "system design", "programming"],
        "sample_queries": [
            "快速收藏这篇 Python 性能优化的文章",
            "帮我搜一下之前收藏的关于 Docker 的内容",
            "收藏这个 GitHub README",
            "看看我收藏了多少技术文章",
            "搜一下 Kubernetes 相关的",
        ],
    },
    "C": {
        "name": "知识博主（多源内容创作）",
        "persona": """你是一个小红书/知乎知识博主，关注 AI 行业动态，需要素材创作内容。
你的工作流程：
- 浏览 36kr、极客公园、即刻、Twitter
- 收藏有趣的文章和观点，用于后续创作
- 需要跨平台对比和整理
- 喜欢发现趋势和洞察
- 用中文为主，偶尔收藏英文内容

你的性格：好奇心强，喜欢发现新角度，关注表达和叙事。
""",
        "domains": ["AI industry", "tech trends", "startups", "product design"],
        "sample_queries": [
            "收藏这篇关于 AI Agent 的行业分析",
            "搜一下我之前收藏的关于创业的内容",
            "帮我整理一下 AI 趋势相关的收藏",
            "看看这周有什么热门话题",
            "搜一下关于产品思维的文章",
        ],
    },
}


# ── 数据结构 ────────────────────────────────────────────────────

@dataclass
class TestStep:
    """一步测试动作"""
    step_num: int
    intent: str          # 用户意图（自然语言）
    command: str         # 实际执行的 sheaf 命令
    url: str | None = None  # 如果是 collect，记录 URL
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration: float = 0.0
    llm_judgment: dict | None = None  # LLM 评判结果
    quality_score: float = 0.0         # 0-10
    friction: str | None = None        # 摩擦点描述
    guard_issues: list | None = None   # OutputGuard 检测到的问题
    is_edge_case: bool = False         # 是否为 edge case 测试


@dataclass
class ProfileReport:
    """一个 Profile 的测试报告"""
    profile_id: str
    profile_name: str
    steps: list[TestStep] = field(default_factory=list)
    overall_score: float = 0.0
    frictions: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


# ── OutputGuard: 轻量输出质量预检 ──────────────────────────────

class OutputGuard:
    """
    在 LLM judge 之前运行的轻量输出质量检测。

    捕获以下问题:
      - EMPTY: 完全空输出（exit_code=0 但没内容）
      - HEADERS_ONLY: 只有标题没有实质内容
      - ERROR_LEAKED: 输出中包含错误信息但 exit_code=0
      - NO_RESULT: "no results"/"未找到" 但没有友好提示
      - GARBAGE: 乱码/编码错误

    用法:
      guard = OutputGuard(step)
      issues = guard.check()
      if issues:
          step.guard_issues = issues  # 附带传给 LLM judge
    """

    # 错误信号词（出现在 stdout 中但 exit_code=0 就算问题）
    ERROR_SIGNALS = ["traceback", "exception", "error:", "failed", "unhandled"]
    # 无结果信号
    NO_RESULT_SIGNALS = ["no results", "no entries", "no items", "未找到", "没有找到", "no data", "空"]
    # 编码问题信号
    ENCODING_SIGNALS = ["\ufffd", "???"]  # replacement char

    @dataclass
    class GuardIssue:
        code: str          # EMPTY, HEADERS_ONLY, ERROR_LEAKED, NO_RESULT, GARBAGE
        severity: str      # critical, warning, info
        detail: str

        def __str__(self):
            return f"[{self.severity}] {self.code}: {self.detail}"

    def __init__(self, step: TestStep):
        self.output = step.stdout or ""
        self.stderr = step.stderr or ""
        self.exit_code = step.exit_code
        self.command = step.command

    def check(self) -> list["OutputGuard.GuardIssue"]:
        """Run all checks, return list of issues found."""
        issues: list[OutputGuard.GuardIssue] = []
        issues.extend(self._check_empty())
        issues.extend(self._check_headers_only())
        issues.extend(self._check_error_leaked())
        issues.extend(self._check_no_result_without_hint())
        issues.extend(self._check_garbage())
        return issues

    def _check_empty(self) -> list:
        if not self.output.strip() and self.exit_code == 0:
            return [self.GuardIssue("EMPTY", "critical",
                    "stdout 为空但 exit_code=0（应返回有意义的反馈）")]
        return []

    def _check_headers_only(self) -> list:
        lines = [line for line in self.output.strip().splitlines() if line.strip()]
        if 0 < len(lines) <= 2 and all(line.strip().startswith("#") for line in lines):
            return [self.GuardIssue("HEADERS_ONLY", "warning",
                    f"输出仅含 {len(lines)} 行标题，无实质内容")]
        return []

    def _check_error_leaked(self) -> list:
        if self.exit_code == 0:
            lower = self.output.lower()
            for sig in self.ERROR_SIGNALS:
                if sig in lower:
                    return [self.GuardIssue("ERROR_LEAKED", "critical",
                            f"exit_code=0 但输出含 '{sig}'（错误未正确传播）")]
        return []

    def _check_no_result_without_hint(self) -> list:
        if self.exit_code == 0 and self.output.strip():
            lower = self.output.lower()
            for sig in self.NO_RESULT_SIGNALS:
                if sig in lower:
                    # 有信号但不是明确的结构化空结果提示 → 可能是裸输出
                    if "建议" not in self.output and "suggestion" not in self.output.lower():
                        return [self.GuardIssue("NO_RESULT", "info",
                                f"输出含 '{sig}' 但无引导用户下一步的建议")]
        return []

    def _check_garbage(self) -> list:
        for sig in self.ENCODING_SIGNALS:
            if sig in self.output:
                return [self.GuardIssue("GARBAGE", "critical",
                        f"输出含编码异常 '{repr(sig)}'")]
        return []


# ── LLM 集成 ────────────────────────────────────────────────────

def get_llm():
    """获取 LLM client（复用 sheaf 的 llm_client）"""
    from sheaf_ai.llm_client import get_client, get_model
    client = get_client()
    model = get_model()
    return client, model


def llm_generate_intent(
    profile: dict,
    history: list[TestStep],
    step_num: int,
    fixtures: TestFixtures | None = None,
    *,
    force_edge: bool = False,
) -> dict:
    """
    让 LLM 根据用户画像和历史操作，生成下一步自然语言意图。

    增强逻辑:
      - fixtures 提供真实 URL 池，避免 LLM 编造
      - ~20% 概率注入 edge case（坏 URL / 垃圾关键词 / 空输入）
      - force_edge=True 强制生成 edge case（用于专项测试）
    """

    client, model = get_llm()
    if fixtures is None:
        fixtures = TestFixtures.for_profile("A")

    history_text = ""
    for s in history[-3:]:  # 最近 3 步作为上下文
        history_text += f"\n- Step {s.step_num}: 意图\"{s.intent}\" → 执行 `{s.command}` → 结果: {s.stdout[:100]}..."

    # ── Edge case 决策 ──
    is_edge = force_edge or fixtures.should_try_edge(probability=0.2)

    # ── 为 collect 准备 URL 建议 ──
    if is_edge:
        suggested_url = fixtures.pick_url(tier="edge")
        url_note = f"（edge case 测试）请使用这个 URL：{suggested_url or '(空)'}"
    else:
        category = fixtures.rng.choice(list(TestFixtures.GOOD_URLS.keys()))
        suggested_url = fixtures.pick_url(category=category)
        url_note = f"请使用这个真实 URL：{suggested_url}"

    # ── 为 search 准备关键词建议 ──
    search_kw = fixtures.pick_keyword(allow_garbage=is_edge)

    prompt = f"""{profile['persona']}

你正在进行一次知识管理工具的使用体验。

已完成的操作:{history_text or "（这是第一步）"}

现在请生成你的第 {step_num} 步操作意图。要求：
1. 必须是一个真实用户会有的自然想法（不是测试指令）
2. 应该使用 sheaf 的某个命令：
   - `collect <URL>`: 收藏一个网页/论文（**第一步必须是 collect**，否则后续功能无数据可用）
   - `search <关键词>`: 搜索已收藏的内容
   - `crystallize <主题>`: 生成知识卡片
   - `stats`: 查看统计
   - `insights`: 查看跨主题洞察
   - `tags`: 查看标签
3. 如果是 collect，{url_note}
4. 如果是 search，建议搜索词："{search_kw}"
5. 意图要多样化，不要连续两步做同样的事
6. **注意**: search 命令不支持 --json 参数，直接写 `search <关键词>` 即可
7. **重要**: 前 2 步必须至少有 1 步是 collect（收藏内容），否则搜索和 crystallize 都没有数据
8. **Edge case**: 真实用户有时会犯迷糊——输错 URL、搜不存在的东西、忘记先 collect 就 search。
   偶尔模拟这种真实失误（约 1/5 概率），比如：
   - 输入一个打错的 URL 或不存在的页面
   - 搜索一个不相关/奇怪的词
   - 在还没收藏任何内容时就 search 或 crystallize

请用 JSON 格式返回：
{{
  "intent": "你的自然语言想法",
  "command": "sheaf 具体命令（注意格式要求）",
  "rationale": "为什么想做这个操作（一句话）"
}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是用户行为模拟器。只输出 JSON，不要任何其他文字。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.8,
        max_tokens=300,
    )

    raw = response.choices[0].message.content.strip()
    # 尝试提取 JSON
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"intent": raw, "command": "sheaf stats", "rationale": "fallback"}


def llm_judge_result(profile: dict, step: TestStep) -> dict:
    """让 LLM 评判命令执行结果的质量"""

    client, model = get_llm()

    # 截取输出防止 token 爆炸
    output_preview = step.stdout[:2000] if step.stdout else "(empty)"
    error_preview = step.stderr[:500] if step.stderr else "(none)"

    prompt = f"""你是一个产品质量评审专家。请评估以下工具使用体验。

用户画像: {profile['name']}
用户意图: {step.intent}
执行的命令: {step.command}
耗时: {step.duration:.1f}s

标准输出:
{output_preview}

错误输出:
{error_preview}

退出码: {step.exit_code}

请从以下维度评分（0-10），并用一句话说明扣分原因：

1. **意图匹配**: 命令结果是否满足用户意图？
2. **输出质量**: 内容是否有用、结构是否清晰？
3. **Agent友好度**: 如果是 Agent 读取这个输出，能否正确理解？
4. **摩擦程度**: 用户需要额外操作吗？（10=零摩擦, 0=完全卡住）
5. **总体满意**: 真实用户会给几分？

请用 JSON 返回：
{{
  "intent_match": <0-10>,
  "output_quality": <0-10>,
  "agent_friendliness": <0-10>,
  "friction_score": <0-10>,
  "overall": <0-10>,
  "reason": "一句话总评",
  "friction": "摩擦点描述（如果有的话，没有则为 null）",
  "highlight": "亮点描述（如果有的话，没有则为 null）"
}}"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是质量评审专家。只输出 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        max_tokens=400,
    )

    raw = response.choices[0].message.content.strip()
    if "```json" in raw:
        raw = raw.split("```json")[1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[1].split("```")[0].strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "intent_match": 5, "output_quality": 5, "agent_friendliness": 5,
            "friction_score": 5, "overall": 5, "reason": raw[:100],
            "friction": None, "highlight": None,
        }


# ── 命令执行 ────────────────────────────────────────────────────

def normalize_command(command: str) -> str:
    """Normalize LLM-generated command to valid sheaf CLI format."""
    # Remove leading "sheaf" if present (we add SHEAF_CMD prefix)
    if command.strip().startswith("sheaf "):
        command = command.strip()[6:]
    elif command.strip() == "sheaf":
        command = "stats"

    # Fix common LLM mistakes
    # "search --query X" → "search X"
    import re
    command = re.sub(r"search\s+--query\s+", "search ", command)
    # "search --json X" → "search X" (search doesn't support --json)
    command = re.sub(r"search\s+--json\s+(.+)", r"search \1", command)
    # "search X --json" → "search X" (also remove trailing --json)
    command = re.sub(r"search\s+(.+)\s+--json", r"search \1", command)
    # "stats --json" → "stats" (stats doesn't support --json either)
    command = re.sub(r"stats\s+--json", "stats", command)
    # "crystallize --id=latest" → "crystallize" (no such flag)
    command = re.sub(r"crystallize\s+--id=\S+", "crystallize", command)
    # "crystallize --template=\S+" → remove template flag
    command = re.sub(r"crystallize\s+--template=\S+\s*", "crystallize ", command)

    # Ensure search/crystallize have arguments
    parts = command.strip().split()
    if parts and parts[0] == "search" and len(parts) == 1:
        command = "stats"  # fallback
    if parts and parts[0] == "crystallize" and len(parts) == 1:
        command = "crystallize AI"  # default topic

    return command.strip()


def run_sheaf_command(command: str, data_dir: str, timeout: int = 30) -> tuple[str, str, int, float]:
    """执行 sheaf 命令，返回 (stdout, stderr, exit_code, duration)"""
    global SHEAF_CMD
    if SHEAF_CMD is None:
        # Use the same Python that's running this script
        SHEAF_CMD = sys.executable + " -m sheaf_ai.cli"

    # 构建 env
    env = os.environ.copy()
    env["SHEAF_DATA_DIR"] = data_dir

    # 确保命令以 python -m sheaf_ai.cli 开头
    if command.startswith("sheaf "):
        cmd = SHEAF_CMD + command[5:]
    else:
        cmd = SHEAF_CMD + " " + command

    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, env=env, encoding="utf-8", errors="replace",
        )
        duration = time.time() - start
        return result.stdout, result.stderr, result.returncode, duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return "", "TIMEOUT", -1, duration
    except Exception as e:
        duration = time.time() - start
        return "", str(e), -1, duration


# ── 主流程 ──────────────────────────────────────────────────────

def run_profile_test(profile_id: str, steps: int = 5, dry_run: bool = False) -> ProfileReport:
    """运行一个 Profile 的深度测试"""

    profile = PROFILES[profile_id]
    report = ProfileReport(profile_id=profile_id, profile_name=profile["name"])

    # 创建 fixtures
    fixtures = TestFixtures.for_profile(profile_id)

    # 创建临时数据目录
    data_dir = tempfile.mkdtemp(prefix=f"sheaf-llm-test-{profile_id}-")
    if not dry_run:
        os.environ["SHEAF_DATA_DIR"] = data_dir

    print(f"\n{'='*60}")
    print(f"  Profile {profile_id}: {profile['name']}")
    print(f"  Data dir: {data_dir}")
    print(f"  Steps: {steps}")
    print(f"{'='*60}\n")

    judgment = {}  # define outside loop for safety
    for i in range(1, steps + 1):
        print(f"  Step {i}/{steps}:", end=" ", flush=True)

        # 确定是否强制 edge case（每 5 步至少 1 次）
        force_edge = (i % 5 == 0) and i > 1

        # 1. LLM 生成意图（带 fixtures）
        try:
            intent_data = llm_generate_intent(
                profile, report.steps, i, fixtures=fixtures, force_edge=force_edge,
            )
        except Exception as e:
            print(f"INTENT FAILED: {e}")
            # fallback: 从 sample_queries 中选一个
            query = profile["sample_queries"][min(i-1, len(profile["sample_queries"])-1)]
            intent_data = {"intent": query, "command": "sheaf stats", "rationale": "fallback"}

        intent = intent_data.get("intent", "unknown intent")
        command = intent_data.get("command", "sheaf stats")

        print(f'"{intent[:50]}..."', end=" ", flush=True)

        # 提取 URL（如果是 collect）
        url = None
        if "collect" in command:
            parts = command.split()
            for p in parts:
                if p.startswith("http"):
                    url = p
                    break

        # Normalize command
        command = normalize_command(command)

        # 检测 edge case
        is_edge = force_edge or (url is not None and url in TestFixtures.EDGE_URLS)
        edge_tag = " [EDGE]" if is_edge else ""

        if dry_run:
            step = TestStep(
                step_num=i, intent=intent, command=command, url=url,
                is_edge_case=is_edge,
            )
            report.steps.append(step)
            print(f"→ {command}{edge_tag} (dry-run)")
            continue

        # 2. 执行命令
        stdout, stderr, exit_code, duration = run_sheaf_command(command, data_dir)
        print(f"→ {command.split()[-1] if command.split() else command} ({duration:.1f}s)", end=" ", flush=True)

        step = TestStep(
            step_num=i, intent=intent, command=command, url=url,
            stdout=stdout, stderr=stderr, exit_code=exit_code, duration=duration,
            is_edge_case=is_edge,
        )

        # 3. OutputGuard 预检（在 LLM judge 之前）
        guard = OutputGuard(step)
        guard_issues = guard.check()
        if guard_issues:
            step.guard_issues = guard_issues
            issue_tags = ", ".join(g.code for g in guard_issues)
            print(f"[GUARD: {issue_tags}]", end=" ", flush=True)

        # 4. LLM 评判
        try:
            judgment = llm_judge_result(profile, step)
            step.llm_judgment = judgment
            step.quality_score = judgment.get("overall", 5)
            step.friction = judgment.get("friction")
            print(f"→ {step.quality_score:.0f}/10{edge_tag}")
        except Exception as e:
            print(f"→ JUDGE FAILED: {e}")
            step.quality_score = 5

        if step.friction:
            report.frictions.append(f"Step {i}: {step.friction}")
        if judgment.get("highlight"):
            report.highlights.append(f"Step {i}: {judgment['highlight']}")
        # Guard issues 也作为摩擦点记录
        if step.guard_issues:
            for gi in step.guard_issues:
                report.frictions.append(f"Step {i} [GUARD]: {gi}")

        report.steps.append(step)

    # 计算总分
    if report.steps:
        report.overall_score = sum(s.quality_score for s in report.steps) / len(report.steps)

    return report


def generate_report(reports: list[ProfileReport], output_path: Path):
    """生成 Markdown 测试报告"""

    now = datetime.now()
    lines = [
        "# Sheaf LLM 深度测试报告",
        "",
        f"> **日期**: {now.strftime('%Y-%m-%d %H:%M')} | **测试类型**: LLM 驱动（真实用户行为模拟）",
        "> **模型**: sheaf_ai.llm_client (default provider)",
        "",
        "---",
        "",
    ]

    # 汇总表
    lines.append("## 汇总")
    lines.append("")
    lines.append("| Profile | 步数 | 平均分 | 摩擦点 | 亮点 |")
    lines.append("|---------|------|--------|--------|------|")
    for r in reports:
        lines.append(f"| {r.profile_id}: {r.profile_name} | {len(r.steps)} | {r.overall_score:.1f}/10 | {len(r.frictions)} | {len(r.highlights)} |")
    lines.append("")

    # 每个 Profile 详细报告
    for r in reports:
        lines.append(f"## Profile {r.profile_id} — {r.profile_name}")
        lines.append("")
        lines.append(f"**平均质量分**: {r.overall_score:.1f}/10")
        lines.append("")

        # Guard 检测汇总
        guard_issues_flat = [gi for s in r.steps if s.guard_issues for gi in s.guard_issues]
        if guard_issues_flat:
            lines.append("### OutputGuard 检测汇总")
            lines.append("")
            from collections import Counter
            issue_counts = Counter(gi.code for gi in guard_issues_flat)
            for code, count in issue_counts.most_common():
                lines.append(f"- **{code}**: {count} 次")
            lines.append("")

        # 步骤详情
        lines.append("### 测试步骤")
        lines.append("")
        lines.append("| # | 意图 | 命令 | 耗时 | 分数 | Guard | Edge | 摩擦点 |")
        lines.append("|---|------|------|------|------|-------|------|--------|")
        for s in r.steps:
            friction_mark = "⚠️" if s.friction else "✅"
            guard_mark = ",".join(g.code for g in s.guard_issues) if s.guard_issues else "-"
            edge_mark = "🔴" if s.is_edge_case else "-"
            lines.append(f"| {s.step_num} | {s.intent[:40]} | `{s.command[:30]}` | {s.duration:.1f}s | {s.quality_score:.0f}/10 {friction_mark} | {guard_mark} | {edge_mark} | {s.friction or '-'} |")
        lines.append("")

        # 评判详情
        lines.append("### LLM 评判详情")
        lines.append("")
        for s in r.steps:
            if s.llm_judgment:
                j = s.llm_judgment
                lines.append(f"**Step {s.step_num}**: {s.intent[:60]}")
                lines.append(f"- 意图匹配: {j.get('intent_match', '?')}/10")
                lines.append(f"- 输出质量: {j.get('output_quality', '?')}/10")
                lines.append(f"- Agent 友好: {j.get('agent_friendliness', '?')}/10")
                lines.append(f"- 摩擦程度: {j.get('friction_score', '?')}/10")
                lines.append(f"- 总评: {j.get('reason', '?')}")
                lines.append("")

        # 摩擦点和亮点
        if r.frictions:
            lines.append("### 摩擦点汇总")
            lines.append("")
            for f in r.frictions:
                lines.append(f"- ⚠️ {f}")
            lines.append("")

        if r.highlights:
            lines.append("### 亮点汇总")
            lines.append("")
            for h in r.highlights:
                lines.append(f"- ✨ {h}")
            lines.append("")

    lines.append("---")
    lines.append(f"*报告生成: {now.strftime('%Y-%m-%d %H:%M')} CST | Jarvis 🤖 LLM Depth Test*")

    REPORTS_DIR.mkdir(exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sheaf LLM-Driven Depth Test")
    parser.add_argument("--profile", "-p", default="A", choices=["A", "B", "C"],
                       help="Which profile to test (default: A)")
    parser.add_argument("--all", action="store_true", help="Test all 3 profiles")
    parser.add_argument("--steps", "-n", type=int, default=5,
                       help="Number of steps per profile (default: 5)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Generate intents only, don't execute commands")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    output_path = REPORTS_DIR / f"llm-depth-test-{today}.md"

    profiles = ["A", "B", "C"] if args.all else [args.profile]
    reports = []

    for pid in profiles:
        report = run_profile_test(pid, steps=args.steps, dry_run=args.dry_run)
        reports.append(report)

    generate_report(reports, output_path)

    # 打印汇总
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for r in reports:
        print(f"  Profile {r.profile_id}: {r.overall_score:.1f}/10 ({len(r.frictions)} frictions)")
    print(f"\n  Report: {output_path}")


if __name__ == "__main__":
    main()
