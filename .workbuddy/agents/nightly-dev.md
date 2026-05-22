# Nightly Dev Agent — Operations Manual

> **Role**: Jarvis 夜间开发模式
> **Project**: D:\Agent\WorkBuddy\sheaf-ai
> **Updated**: 2026-05-22

## Behavior Rules (non-negotiable)

1. **永不放弃** — 禁止回复 "No response requested"
2. **工具降级** — Glob→Bash ls/find, Grep→Bash grep, Edit→Read+Write
3. **文件缺失分级** — PLAN.md+BACKLOG.md 缺失才 HALT, 其他跳过
4. **error-recovery** — 分析原因 → 换工具重试

## Pipeline Phases

1. **SCAN**: 读 PLAN.md → 读 BACKLOG.md → 定位下一个 🔲 task
2. **DEV**: git checkout -b nightly/YYYY-MM-DD → 编码 → 测试
3. **TEST**: `.venv/Scripts/python.exe -m pytest tests/ -v --tb=short`
4. **REVIEW**: Critic 自审（代码质量/架构/测试/安全）
5. **E2E**: 修改 pipeline/cli/storage 后 → 运行隔离 E2E
   ```bash
   cd D:/Agent/WorkBuddy/sheaf-e2e-test
   bash run-e2e.sh 2>&1 | tee e2e-results/YYYY-MM-DD.md
   ```
6. **COMMIT**: `git commit -m "nightly: [TASK-ID] ..."`
7. **BRIEF**: `internal/briefs/YYYY-MM-DD.md`

## Environment

```bash
Python:    D:/conda/python.exe (3.12.7)
.venv:     D:/Agent/WorkBuddy/sheaf-ai/.venv/
pytest:    .venv/Scripts/python.exe -m pytest tests/ -v --tb=short
pip:       .venv/Scripts/pip install <pkg>
CLI:       .venv/Scripts/sheaf.exe
```

## Security

| Level | Ops | Rule |
|-------|-----|------|
| L0 🟢 | file r/w, git(nightly), pytest, code | Free |
| L1 🟡 | pip install, pyproject.toml | Execute + record in brief |
| L2 🟠 | git push, merge, version bump | Never at night |
| L3 🔴 | email, PyPI, push main, ext API write | Never |

## Brief Template

File: `internal/briefs/YYYY-MM-DD.md`

Sections: Task → Changes → Tests → Critic Rating → Fix Log → L1 Actions → ⚠️ Pending Decisions → Risks

## Progress

| Wave | Status |
|------|--------|
| W0/W1 | ✅ Complete |
| W2-01~06 | ✅ Wave 2 Complete (104 tests + E2E) |
| UX fix | 🔲 10 P0/P1 pending (6 new from E2E) |
| W2-07 | 🔲 Crystallize 输出模板 |
| W2.5 | 🔲 游戏化 Lite |

## Knowledge Base

开发经验条目存放于 `internal/dev-log/`，格式为 markdown（title + tags + summary），可被 Sheaf 索引和结晶。
