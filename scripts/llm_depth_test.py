#!/usr/bin/env python3
"""
Sheaf LLM-Driven Depth Test — 探索性模拟用户流程（不是真实用户验证）

与脚本测试（固定 URL + 固定断言）互补，LLM 驱动测试模拟真实用户决策路径：
  1. LLM 生成自然语言意图（"我想收藏一篇关于 agent 的论文"）
  2. 执行 sheaf 命令
  3. LLM 评判结果质量（"这个摘要覆盖了核心观点吗？"）

用法:
  python scripts/llm_depth_test.py --help
  # Paid calls require explicit authorization and these three environment names:
  python scripts/llm_depth_test.py --execute --allow-env OPENAI_API_KEY \
      --allow-env OPENAI_BASE_URL --allow-env DEFAULT_MODEL --profile A --steps 5
  # --dry-run still makes paid intent-generation calls and requires --execute.

The driver uses an explicitly configured OpenAI-compatible client; the tested
commands use Sheaf's production client. They receive the same explicit endpoint
and model configuration, but this is not a model-quality or user-value benchmark.
Only allowlisted argv are executed against a newly created test workspace.
This is process configuration isolation, NOT an OS sandbox: the child still has
the current user's permissions. No arbitrary URLs, files, or shell programs are
accepted from model output. Install the repository's dependencies first; child
imports are pinned to this script's repository, not an older installed Sheaf.

输出:
  internal/test-reports/llm-depth-test-YYYY-MM-DD.md (默认)
  可通过 --output 自定义路径
"""

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from importlib.metadata import PackageNotFoundError, version as package_version

# ── 配置 ────────────────────────────────────────────────────────

SOURCE_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = SOURCE_ROOT / "internal" / "test-reports"
# reports dir created lazily in generate_report() to avoid sandbox issues

PROVIDER_ENV_NAMES = frozenset({"OPENAI_API_KEY", "OPENAI_BASE_URL", "DEFAULT_MODEL"})
# Populated only by explicit --allow-env flags; never copied from user settings.
LIVE_PROVIDER_ENV: dict[str, str] = {}


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
    command: str         # 实际执行的 sheaf 命令（normalized）
    url: str | None = None  # 如果是 collect，记录 URL
    raw_command: str = ""    # LLM 生成的原始命令（normalize 之前）
    normalization_applied: bool = False  # 是否经过了 normalize 修正
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration: float = 0.0
    llm_judgment: dict | None = None  # LLM 评判结果
    quality_score: float | None = None  # None means unscored, never a fabricated 5/10
    execution_status: str = "not_run"
    judgment_status: str = "not_run"
    friction: str | None = None        # 摩擦点描述
    guard_issues: list | None = None   # OutputGuard 检测到的问题
    is_edge_case: bool = False         # 是否为 edge case 测试


@dataclass
class ProfileReport:
    """一个 Profile 的测试报告"""
    profile_id: str
    profile_name: str
    steps: list[TestStep] = field(default_factory=list)
    overall_score: float | None = None
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
        issues.extend(self._check_exit_mismatch())
        issues.extend(self._check_unstructured_error())
        issues.extend(self._check_no_suggestion())
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

    def _check_exit_mismatch(self) -> list:
        """Detect semantic mismatch between output content and exit code."""
        lower = self.output.lower()
        # Output looks successful but exit_code is non-zero
        if self.exit_code != 0 and self.output.strip():
            success_sigs = ["✓", "已收集", "successfully", "✅", "all checks passed"]
            for sig in success_sigs:
                if sig in lower:
                    return [self.GuardIssue("EXIT_MISMATCH", "critical",
                            f"exit_code={self.exit_code} 但输出含成功信号 '{sig}'")]
        # Output contains structured error but exit_code is 0
        if self.exit_code == 0 and '"success": false' in lower:
            return [self.GuardIssue("EXIT_MISMATCH", "critical",
                    "exit_code=0 但 JSON 输出含 success:false（退出码未传播）")]
        return []

    def _check_unstructured_error(self) -> list:
        """JSON-mode commands should return valid JSON even on error."""
        if "--json" not in self.command:
            return []
        if not self.output.strip():
            return []  # EMPTY already covers this
        try:
            json.loads(self.output)
        except json.JSONDecodeError:
            return [self.GuardIssue("UNSTRUCTURED_ERROR", "critical",
                    f"--json 命令返回了非 JSON 输出（前 50 字符: {self.output[:50]!r}）")]
        return []

    def _check_no_suggestion(self) -> list:
        """Empty/failed results should offer user a next step."""
        lower = self.output.lower()
        empty_signals = ["no results", "no entries", "not found", "未找到", "没有找到",
                         "no cards", "no data"]
        has_empty_signal = any(sig in lower for sig in empty_signals)
        if not has_empty_signal:
            return []
        guidance_signals = ["建议", "suggestion", "try", "试试", "tip:", "hint:",
                            "you can", "你可以", "run:", "use '"]
        has_guidance = any(sig in lower for sig in guidance_signals)
        if not has_guidance:
            return [self.GuardIssue("NO_SUGGESTION", "warning",
                    "空结果/失败输出无下一步建议，用户可能卡住")]
        return []

# ── LLM 集成 ────────────────────────────────────────────────────

def get_llm():
    """Explicit driver client; never load repo .env or the user's Sheaf settings."""
    if set(LIVE_PROVIDER_ENV) != PROVIDER_ENV_NAMES:
        raise ValueError("Explicit endpoint, model and API-key environment are required")
    from openai import OpenAI
    client = OpenAI(
        api_key=LIVE_PROVIDER_ENV["OPENAI_API_KEY"],
        base_url=LIVE_PROVIDER_ENV["OPENAI_BASE_URL"],
        max_retries=0,
        timeout=60,
    )
    return client, LIVE_PROVIDER_ENV["DEFAULT_MODEL"]


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
6. 不使用 shell 操作符、文件路径参数或未列出的子命令。search 支持 --json。
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

    result = json.loads(raw)
    if not isinstance(result, dict) or not all(
        isinstance(result.get(key), str) for key in ("intent", "command")
    ):
        raise ValueError("Invalid intent response shape")
    return result


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

    result = json.loads(raw)
    if not isinstance(result, dict):
        raise ValueError("Invalid judge response shape")
    for key in ("intent_match", "output_quality", "agent_friendliness", "friction_score", "overall"):
        value = result.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 10:
            raise ValueError("Invalid judge score")
    return result


# ── 命令执行 ────────────────────────────────────────────────────

class CommandRejected(ValueError):
    """Model output is outside the narrow profile command contract."""


class _CommandParser(argparse.ArgumentParser):
    def error(self, message):
        # Do not echo arbitrary model output or argparse's help to the terminal.
        raise CommandRejected("Command arguments are not allowed")


def _bounded_integer(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 50:
        raise ValueError("Expected a number in [1, 50]")
    return number


def parse_command(command: str) -> list[str]:
    """Parse, never repair, an allowlisted command; return only Sheaf arguments."""
    if not isinstance(command, str) or not command.strip() or len(command) > 4096:
        raise CommandRejected("Empty or oversized command")
    if any(character in command for character in "\r\n\x00;&|<>`$%"):
        raise CommandRejected("Shell syntax is not allowed")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise CommandRejected("Unbalanced command quoting") from exc
    if argv and argv[0] == "sheaf":
        argv = argv[1:]
    parser = _CommandParser(add_help=False, allow_abbrev=False)
    commands = parser.add_subparsers(dest="action", required=True, parser_class=_CommandParser)
    for name in ("stats", "tags", "weekly", "trends", "urgent"):
        commands.add_parser(name, add_help=False, allow_abbrev=False)
    collect = commands.add_parser("collect", add_help=False, allow_abbrev=False)
    collect.add_argument("url")
    collect.add_argument("--json", action="store_true")
    collect.add_argument("--force", action="store_true")
    search = commands.add_parser("search", add_help=False, allow_abbrev=False)
    search.add_argument("query", nargs="+")
    search.add_argument("--json", action="store_true")
    search.add_argument("--limit", "-n", type=_bounded_integer)
    listing = commands.add_parser("list", add_help=False, allow_abbrev=False)
    listing.add_argument("--json", action="store_true")
    listing.add_argument("--recent", action="store_true")
    listing.add_argument("--limit", "-n", type=_bounded_integer)
    listing.add_argument("--page", type=_bounded_integer)
    for flag in ("--topic", "--tag", "--type"):
        listing.add_argument(flag)
    insights = commands.add_parser("insights", add_help=False, allow_abbrev=False)
    insights.add_argument("--json", action="store_true")
    crystal = commands.add_parser("crystallize", add_help=False, allow_abbrev=False)
    crystal.add_argument("topic", nargs="?")
    view = crystal.add_mutually_exclusive_group()
    view.add_argument("--list", action="store_true")
    view.add_argument("--stats", action="store_true")
    crystal.add_argument("--format", choices=("text", "json", "detailed"))
    parsed = parser.parse_args(argv)
    if parsed.action == "collect":
        allowed_urls = set(TestFixtures.EDGE_URLS)
        allowed_urls.update(url for urls in TestFixtures.GOOD_URLS.values() for url in urls)
        if parsed.url not in allowed_urls:
            raise CommandRejected("Only the fixed public/invalid URL fixtures are allowed")
    if parsed.action == "crystallize":
        if not parsed.topic and not (parsed.list or parsed.stats):
            raise CommandRejected("A topic or read-only card view is required")
        if parsed.topic and (parsed.list or parsed.stats):
            raise CommandRejected("Choose a topic or a card view, not both")
    return argv


def normalize_command(command: str) -> str:
    """Only normalize quoting and the optional sheaf prefix; never change intent."""
    return shlex.join(parse_command(command))


@dataclass(frozen=True)
class ProfileWorkspace:
    """Harness-created paths, not paths supplied by a generated command."""
    root: Path
    data: Path
    cwd: Path
    home: Path

    @classmethod
    def create(cls, profile_id: str) -> "ProfileWorkspace":
        root = Path(tempfile.mkdtemp(prefix=f"sheaf-llm-test-{profile_id}-")).resolve()
        workspace = cls(root, root / "data", root / "cwd", root / "home")
        for path in (workspace.data, workspace.cwd, workspace.home):
            path.mkdir()
        return workspace


def isolated_environment(workspace: ProfileWorkspace, provider_env: dict[str, str]) -> dict[str, str]:
    """Minimal inherited environment; no real home, repo dotenv or path overrides."""
    if set(provider_env) - PROVIDER_ENV_NAMES:
        raise ValueError("Unexpected provider environment name")
    env = {
        name: os.environ[name]
        for name in ("SYSTEMROOT", "SystemRoot", "WINDIR", "PATH", "LANG", "LC_ALL")
        if name in os.environ
    }
    env.update(provider_env)
    env.update({
        "HOME": str(workspace.home), "USERPROFILE": str(workspace.home),
        "APPDATA": str(workspace.home / "appdata"),
        "LOCALAPPDATA": str(workspace.home / "localappdata"),
        "XDG_CONFIG_HOME": str(workspace.home / "config"),
        "TEMP": str(workspace.root), "TMP": str(workspace.root),
        "TMPDIR": str(workspace.root),
        "SHEAF_DATA_DIR": str(workspace.data), "SHEAF_LOAD_DOTENV": "0",
        # Deliberately replace (never inherit) PYTHONPATH with the reviewed tree.
        # This prevents an older installed Sheaf from satisfying the profile test.
        "PYTHONPATH": str(SOURCE_ROOT),
        "DEFAULT_PROVIDER": "openai", "NO_COLOR": "1", "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8", "PYTHONNOUSERSITE": "1",
    })
    return env


def run_sheaf_command(
    command: str, workspace: ProfileWorkspace, timeout: int = 30,
    *, provider_env: dict[str, str] | None = None,
) -> tuple[str, str, int, float]:
    """Run fixed Sheaf argv in test paths, without a shell. Not an OS sandbox."""
    try:
        argv = parse_command(command)
    except CommandRejected as exc:
        return "", f"COMMAND_REJECTED: {exc}", 2, 0.0
    env = isolated_environment(workspace, provider_env or {})
    cmd = [sys.executable, "-m", "sheaf_ai.cli", *argv]

    start = time.time()
    try:
        result = subprocess.run(
            cmd, shell=False, capture_output=True, text=True,
            timeout=timeout, env=env, cwd=workspace.cwd,
            stdin=subprocess.DEVNULL, encoding="utf-8", errors="replace",
        )
        duration = time.time() - start
        return result.stdout, result.stderr, result.returncode, duration
    except subprocess.TimeoutExpired:
        duration = time.time() - start
        return "", "TIMEOUT", -1, duration
    except Exception as e:
        duration = time.time() - start
        return "", str(e), -1, duration


def execution_status(exit_code: int, stderr: str) -> str:
    """Execution facts come from the process, never from the judge's rating."""
    if exit_code == -1 and stderr == "TIMEOUT":
        return "timeout"
    if exit_code == 0:
        return "executed"
    if exit_code == 1:  # Sheaf's documented PARTIAL exit code.
        return "partial"
    return "command_failed"


# ── 主流程 ──────────────────────────────────────────────────────

def run_profile_test(profile_id: str, steps: int = 5, dry_run: bool = False,
                     seed: int | None = None) -> ProfileReport:
    """运行一个 Profile 的深度测试"""

    profile = PROFILES[profile_id]
    report = ProfileReport(profile_id=profile_id, profile_name=profile["name"])

    # 创建 fixtures（带 seed 以保证可复现）
    fixtures = TestFixtures.for_profile(profile_id, rng_seed=seed)

    # 创建临时数据目录
    workspace = ProfileWorkspace.create(profile_id)

    print(f"\n{'='*60}")
    print(f"  Profile {profile_id}: {profile['name']}")
    print(f"  Test workspace: {workspace.root}")
    print(f"  Steps: {steps}")
    print(f"{'='*60}\n")

    for i in range(1, steps + 1):
        judgment = {}
        print(f"  Step {i}/{steps}:", end=" ", flush=True)

        # 确定是否强制 edge case（每 5 步至少 1 次）
        force_edge = (i % 5 == 0) and i > 1

        # 1. LLM 生成意图（带 fixtures）
        try:
            intent_data = llm_generate_intent(
                profile, report.steps, i, fixtures=fixtures, force_edge=force_edge,
            )
            if not isinstance(intent_data, dict) or not all(
                isinstance(intent_data.get(key), str) for key in ("intent", "command")
            ):
                raise ValueError("Invalid intent response shape")
        except Exception as exc:
            # Provider errors can contain request details. Record type, not secrets.
            print(f"INTENT FAILED: {type(exc).__name__}")
            report.steps.append(TestStep(
                step_num=i, intent="intent generation failed", command="",
                execution_status="intent_failed", exit_code=-1,
                stderr=type(exc).__name__,
            ))
            continue

        intent = intent_data["intent"]
        raw_command = intent_data["command"]

        print(f'"{intent[:50]}..."', end=" ", flush=True)

        # 提取 URL（如果是 collect）
        url = None
        if "collect" in raw_command:
            parts = raw_command.split()
            for p in parts:
                if p.startswith("http"):
                    url = p
                    break

        # Normalize command — preserve raw for report
        try:
            command = normalize_command(raw_command)
        except CommandRejected as exc:
            report.steps.append(TestStep(
                step_num=i, intent=intent, command="", raw_command=raw_command,
                execution_status="command_rejected", exit_code=2,
                stderr=f"COMMAND_REJECTED: {exc}",
            ))
            print("COMMAND REJECTED")
            continue
        normalization_applied = (command != raw_command)

        # 检测 edge case
        is_edge = force_edge or (url is not None and url in TestFixtures.EDGE_URLS)
        edge_tag = " [EDGE]" if is_edge else ""

        if dry_run:
            step = TestStep(
                step_num=i, intent=intent, command=command, url=url,
                raw_command=raw_command, normalization_applied=normalization_applied,
                is_edge_case=is_edge, execution_status="dry_run",
            )
            report.steps.append(step)
            print(f"→ {command}{edge_tag} (dry-run)")
            continue

        # 2. 执行命令
        stdout, stderr, exit_code, duration = run_sheaf_command(
            command, workspace, provider_env=LIVE_PROVIDER_ENV,
        )
        print(f"→ {command.split()[-1] if command.split() else command} ({duration:.1f}s)", end=" ", flush=True)

        step = TestStep(
            step_num=i, intent=intent, command=command, url=url,
            raw_command=raw_command, normalization_applied=normalization_applied,
            stdout=stdout, stderr=stderr, exit_code=exit_code, duration=duration,
            is_edge_case=is_edge, execution_status=execution_status(exit_code, stderr),
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
            step.judgment_status = "scored"
            step.llm_judgment = judgment
            step.quality_score = judgment["overall"]
            step.friction = judgment.get("friction")
            print(f"→ {step.quality_score:.0f}/10{edge_tag}")
        except Exception as exc:
            print(f"→ JUDGE FAILED: {type(exc).__name__}")
            step.judgment_status = "failed"
            step.quality_score = None

        if step.friction:
            report.frictions.append(f"Step {i}: {step.friction}")
        if judgment.get("highlight") and step.execution_status == "executed":
            report.highlights.append(f"Step {i}: {judgment['highlight']}")
        # Guard issues 也作为摩擦点记录
        if step.guard_issues:
            for gi in step.guard_issues:
                report.frictions.append(f"Step {i} [GUARD]: {gi}")

        report.steps.append(step)

    # 计算总分
    measured = [step.quality_score for step in report.steps if step.quality_score is not None]
    if measured:
        report.overall_score = sum(measured) / len(measured)

    return report


def _score_text(value: float | None) -> str:
    return "unscored" if value is None else f"{value:.1f}/10"


def _source_identity() -> dict[str, str]:
    """Local checkout identity, not a claim that an editable tree is frozen."""
    identity = {
        "source_root": str(SOURCE_ROOT),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "commit": "unavailable",
        "tracked_changes": "unknown",
    }
    try:
        revision = subprocess.run(
            ["git", "-C", str(SOURCE_ROOT), "rev-parse", "HEAD"],
            shell=False, capture_output=True, text=True, timeout=5,
        )
        changes = subprocess.run(
            ["git", "-C", str(SOURCE_ROOT), "status", "--porcelain", "--untracked-files=no"],
            shell=False, capture_output=True, text=True, timeout=5,
        )
        if revision.returncode == 0:
            identity["commit"] = revision.stdout.strip()
        if changes.returncode == 0:
            identity["tracked_changes"] = "yes" if changes.stdout.strip() else "no"
    except (OSError, subprocess.SubprocessError):
        pass
    return identity


def generate_report(reports: list[ProfileReport], output_path: Path,
                    seed: int | None = None):
    """生成 Markdown 测试报告"""

    now = datetime.now()

    # Gather runtime metadata
    model_name = LIVE_PROVIDER_ENV.get("DEFAULT_MODEL", "unconfigured")
    try:
        version = f"v{package_version('sheaf-ai')}"
    except PackageNotFoundError:
        version = "unknown"
    provider = "explicit OpenAI-compatible configuration"
    identity = _source_identity()

    lines = [
        "# Sheaf LLM 深度测试报告",
        "",
        f"> **日期**: {now.strftime('%Y-%m-%d %H:%M')} | **测试类型**: 探索性 LLM 模拟（非真实用户验证）",
        f"> **模型**: {model_name} | **Provider**: {provider}",
        f"> **Installed package metadata**: sheaf-ai {version} | **Seed**: {seed if seed is not None else '(random)'}",
        "> Driver uses its explicit client; commands use the production Sheaf client.",
        "> This report is not a deterministic benchmark or an OS-sandbox guarantee.",
        f"> Tested source: {identity['source_root']} | Commit: {identity['commit']}",
        f"> Tracked changes: {identity['tracked_changes']} | Driver SHA256: {identity['driver_sha256']}",
        "",
        "---",
        "",
    ]

    # 汇总表
    lines.append("## 汇总")
    lines.append("")
    lines.append("体验评分不代表命令执行成功；退出码与执行状态单独记录。")
    lines.append("")
    lines.append("| Profile | 步数 | 已评分 | 已评分平均体验分 | 执行成功/总步数 | 摩擦点 | 亮点 |")
    lines.append("|---------|------|--------|------------------|-----------------|--------|------|")
    for r in reports:
        measured = sum(step.quality_score is not None for step in r.steps)
        succeeded = sum(step.execution_status == "executed" for step in r.steps)
        lines.append(f"| {r.profile_id}: {r.profile_name} | {len(r.steps)} | {measured} | {_score_text(r.overall_score)} | {succeeded}/{len(r.steps)} | {len(r.frictions)} | {len(r.highlights)} |")
    lines.append("")

    # 每个 Profile 详细报告
    for r in reports:
        lines.append(f"## Profile {r.profile_id} — {r.profile_name}")
        lines.append("")
        lines.append(f"**已评分平均体验分**: {_score_text(r.overall_score)}（非执行成功率；未评分不补分）")
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
        lines.append("| # | 意图 | 命令 | 执行状态 | 退出码 | 评判状态 | 耗时 | 体验分 | Guard | Edge | Norm | 摩擦点 |")
        lines.append("|---|------|------|----------|--------|----------|------|--------|-------|------|------|--------|")
        for s in r.steps:
            friction_mark = "✅" if s.execution_status == "executed" and not s.friction and not s.guard_issues else "⚠️"
            guard_mark = ",".join(g.code for g in s.guard_issues) if s.guard_issues else "-"
            edge_mark = "🔴" if s.is_edge_case else "-"
            norm_mark = "🔧" if s.normalization_applied else "-"
            lines.append(f"| {s.step_num} | {s.intent[:40]} | `{s.command[:30]}` | {s.execution_status} | {s.exit_code} | {s.judgment_status} | {s.duration:.1f}s | {_score_text(s.quality_score)} {friction_mark} | {guard_mark} | {edge_mark} | {norm_mark} | {s.friction or '-'} |")
        lines.append("")
        for s in r.steps:
            if s.stderr:
                # Raw stderr stays on the step; the report uses bounded JSON escaping.
                lines.append(f"- Step {s.step_num} stderr: {json.dumps(s.stderr[:1000], ensure_ascii=False)}")
        lines.append("")

        # Raw/normalized command details (for debugging LLM command generation)
        normalized_steps = [s for s in r.steps if s.normalization_applied or s.execution_status == "command_rejected"]
        if normalized_steps:
            lines.append("### 命令修正记录")
            lines.append("")
            lines.append("以下步骤中 LLM 生成的命令被 normalize_command() 修正：")
            lines.append("")
            for s in normalized_steps:
                lines.append(f"- **Step {s.step_num}** ({s.execution_status}): `{s.raw_command}` → `{s.command}`")
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    rendered = "\n".join(lines)
    key = LIVE_PROVIDER_ENV.get("OPENAI_API_KEY")
    if key:
        rendered = rendered.replace(key, "[REDACTED_API_KEY]")
    with output_path.open("x", encoding="utf-8") as handle:
        handle.write(rendered)
    print(f"\n报告已保存: {output_path}")


# ── CLI ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Sheaf LLM-Driven Depth Test")
    parser.add_argument("--profile", "-p", default="A", choices=["A", "B", "C"],
                       help="Which profile to test (default: A)")
    parser.add_argument("--all", action="store_true", help="Test all 3 profiles")
    parser.add_argument("--steps", "-n", type=int, default=5,
                       help="Number of steps per profile (default: 5)")
    parser.add_argument("--seed", type=int, default=None,
                       help="RNG seed for reproducibility (default: random)")
    parser.add_argument("--output", "-o", default=None,
                       help="Report output path (default: internal/test-reports/llm-depth-test-YYYY-MM-DD.md)")
    parser.add_argument("--dry-run", action="store_true",
                       help="Generate paid LLM intents only; still requires --execute")
    parser.add_argument("--execute", action="store_true",
                       help="Explicitly authorize paid driver and product-model calls")
    parser.add_argument("--allow-env", action="append", default=[], choices=sorted(PROVIDER_ENV_NAMES),
                       help="Explicit environment name to pass, never an API-key value")
    args = parser.parse_args()
    if not args.execute:
        parser.error("No calls made. Live intent generation requires --execute (including --dry-run).")
    if not 1 <= args.steps <= 20:
        parser.error("--steps must be between 1 and 20")
    if set(args.allow_env) != PROVIDER_ENV_NAMES:
        parser.error("Explicitly allow OPENAI_API_KEY, OPENAI_BASE_URL and DEFAULT_MODEL")
    selected_env = {name: os.environ.get(name, "").strip() for name in args.allow_env}
    if not all(selected_env.values()):
        parser.error("An explicitly allowed provider variable is empty; no calls made")
    from urllib.parse import urlsplit
    endpoint = urlsplit(selected_env["OPENAI_BASE_URL"])
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.username or endpoint.password:
        parser.error("OPENAI_BASE_URL must be an explicit HTTPS endpoint without embedded credentials")
    LIVE_PROVIDER_ENV.clear()
    LIVE_PROVIDER_ENV.update(selected_env)

    seed = args.seed
    today = datetime.now().strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else REPORTS_DIR / f"llm-depth-test-{today}.md"
    if output_path.exists():
        parser.error("Report already exists; choose a new --output path before making calls")

    profiles = ["A", "B", "C"] if args.all else [args.profile]
    reports = []

    for pid in profiles:
        report = run_profile_test(pid, steps=args.steps, dry_run=args.dry_run, seed=seed)
        reports.append(report)

    generate_report(reports, output_path, seed=seed)

    # 打印汇总
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    for r in reports:
        succeeded = sum(step.execution_status == "executed" for step in r.steps)
        print(f"  Profile {r.profile_id}: experience={_score_text(r.overall_score)}, executed={succeeded}/{len(r.steps)} ({len(r.frictions)} frictions)")
    print(f"\n  Report: {output_path}")


if __name__ == "__main__":
    main()
