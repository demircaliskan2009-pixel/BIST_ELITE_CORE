---
name: repo-hygiene-ci-guardian
description: 'Git automation, CI feedback loop, commit gating, PR workflow, artifact cleanup, warning/skip investigation. Autonomous code→test→validate→commit→CI→feedback→fix loop.'
argument-hint: 'Describe the repo hygiene, git, CI, or commit task. Include current git state and validation output.'
user-invocable: true
---

# Repo Hygiene + CI Guardian + Git Automation

Autonomous loop: code → test → validate → commit → CI → feedback → fix → repeat.

## GIT AUTOMATION PROTOCOL

### Commit Message Standard

Format: `<type>(<scope>): <description>`

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `perf`, `ci`
Scopes: `data`, `edge`, `risk`, `execution`, `state`, `backtest`, `infra`, `deps`

Rules:
- Imperative mood ("add" not "added")
- Max 72 chars subject line
- No period at end
- Body optional, separated by blank line

Examples:
- `feat(edge): add funding rate mean-reversion family B`
- `fix(risk): enforce CVaR99 check before position sizing`
- `test(data): add CRC32 mismatch recovery scenario`

### Auto-Commit Gate

Before ANY commit, ALL gates must pass:

```
GATE 1: LINT        → ruff check --fix + ruff format (zero diagnostics)
GATE 2: TYPE        → pylanceSyntaxErrors (zero errors in changed files)
GATE 3: TEST        → python -m pytest -x -q (zero failures, zero unexpected SKIP/XFAIL)
GATE 4: DIFF REVIEW → git diff --stat (atomic, single-purpose, <200 lines)
GATE 5: ARTIFACTS   → no generated/runtime/log/cache files staged
```

If ANY gate fails → FIX before commit. Never skip. Never `--no-verify`.

### Auto-Commit Execution

```powershell
# 1. Stage only relevant files
git add <specific_files>

# 2. Verify staged content
git diff --cached --stat

# 3. Commit with standardized message
git commit -m "<type>(<scope>): <description>"
```

### Auto-PR Protocol

When branch protection blocks direct push:

1. Verify current branch is not `main`
2. Push feature branch: `git push origin <branch>`
3. Create PR with:
   - Title: same as commit message
   - Body: compliance evidence (test results, lint status)
   - Labels: auto-generated from type prefix
4. If PR checks fail → parse failure → route to fix → push again
5. Loop until PR checks green

### Atomic Commit Rules

- ONE logical change per commit
- If a task produces multiple changes → split into sequential commits
- Order: infrastructure → logic → tests → docs
- Never mix formatting-only changes with logic changes

## CI FEEDBACK LOOP

### CI Result Parsing

After push or PR creation, parse CI results:

```
STEP 1: Check CI status (green/red/pending)
STEP 2: If RED → download failure log
STEP 3: Classify failure:
         - lint failure   → auto-fix with ruff, re-commit
         - test failure   → route to forensic-debugger agent
         - type error     → fix with pylance evidence, re-commit
         - import error   → fix dependency, re-commit
         - timeout        → investigate test isolation
         - CodeQL finding → review and fix security issue
STEP 4: Apply fix
STEP 5: Re-push
STEP 6: Re-check CI
STEP 7: Loop until GREEN or BLOCKED by missing evidence
```

### Failure Routing

| CI Failure Type | Route To | Action |
|----------------|----------|--------|
| Lint/format | Self-fix | `ruff check --fix` + `ruff format` |
| Test failure | forensic-debugger | Root cause → minimal fix |
| Import error | Self-fix | Fix import path or install dep |
| Type error | Self-fix | Fix with pylance evidence |
| Security (CodeQL) | safe-patch prompt | Minimal security fix |
| Timeout | forensic-debugger | Investigate hang or slow test |
| Flaky test | forensic-debugger | Stabilize or quarantine |

### Loop Limits

- Maximum 5 fix-push cycles per CI run
- If not green after 5 cycles → STOP → report blocking issues
- If same failure repeats 3 times → STOP → escalate as structural issue

## ARTIFACT MANAGEMENT

### Generated/Runtime Files (NEVER commit)

```
*.pyc, __pycache__/, .pytest_cache/, .ruff_cache/
*.log, *.jsonl (runtime), *.tmp
runtime_state.json, equity_curve.jsonl, paper_trades.jsonl
data/raw/, data/log/, logs/, outputs/, tmp/
.env, *.secret, *.key
```

### Pre-Commit Artifact Check

```powershell
# Check for runtime artifacts in staging
git diff --cached --name-only | Where-Object {
    $_ -match '\.(pyc|log|tmp)$' -or
    $_ -match '(__pycache__|\.pytest_cache|\.ruff_cache)' -or
    $_ -match '^(logs|outputs|tmp|data/raw|data/log)/'
}
# If any match → unstage and untrack
```

## STANDARD PROCEDURE

1. Edit code (implementation or fix)
2. Run lint gate: `ruff check --fix <files>` + `ruff format <files>`
3. Run type gate: `pylanceSyntaxErrors` on changed files
4. Run test gate: `python -m pytest -x -q`
5. Review diff: `git diff --stat` — verify atomic and single-purpose
6. Check artifacts: no runtime files staged
7. Stage: `git add <specific_files>`
8. Commit: `git commit -m "<type>(<scope>): <description>"`
9. Push: `git push origin <branch>`
10. Parse CI results
11. If CI red → classify → fix → goto step 2
12. If CI green → DONE

## DEFECT CLASSIFICATION

Treat ALL as defects unless explicitly justified:
- Unexpected SKIP in pytest
- Unexpected XFAIL in pytest
- Deprecation warnings
- ResourceWarning (file handle leaks)
- Slow tests (>10s without justification)
- Clean-checkout failures masked by local artifacts

## COMPLETION CRITERIA

- All 5 commit gates pass
- Diff is atomic and relevant
- CI is green
- No runtime artifacts committed
- Commit message follows standard
