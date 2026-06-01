---
name: "Toolchain Execution Rules"
description: "Active agent-driven toolchain — every VS Code extension is an active tool with deterministic triggers, execution order, and fail-closed blocking"
applyTo: "**"
---

# TOOLCHAIN EXECUTION RULES

Only use tools proven available in the current workspace.
Terminal commands and their outputs are source of truth for repository state and validation.
git, gh, ruff, pytest, and python command outputs are authoritative.
MCP servers, extensions, and UI integrations are helpers only and must not be claimed unless callable and verified.
Do not add external MCP servers, plugins, or cloud-agent dependencies as part of normal execution.

PR/CI closeout polling policy:
- Use JSON/API polling only for PR, CI, and CodeQL state checks.
- Forbidden: `gh pr checks --watch`, `gh run watch`, and `gh pr review --approve`.
- Self-approval is forbidden.

Search tooling fallback policy:
- `rg`/ripgrep is optional.
- If unavailable, use PowerShell `Get-ChildItem` + `Select-String` or Python file walks.

Legacy forbidden statement retained for audit context:
- FORBIDDEN legacy claim: Every extension is an active tool.

---

## 1. TOOL INVENTORY

### Code Quality Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| Ruff Lint | charliermarsh.ruff | Every file edit | `ruff check --fix <file>` |
| Ruff Format | charliermarsh.ruff | After lint fix | `ruff format <file>` |
| isort | ms-python.isort | After import changes | `ruff check --select I --fix <file>` |
| Black | ms-python.black-formatter | Fallback formatter | `black <file>` |
| Pylance | ms-python.vscode-pylance | After logic changes | `pylanceSyntaxErrors` MCP tool |
| Error Lens | usernamehw.errorlens | Continuous | `problems` tool on changed files |

### Testing Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| pytest | ms-python.python | After behavior change | `python -m pytest -x -q <target>` |
| Test Explorer | hbenl.vscode-test-explorer | Test discovery | `python -m pytest --collect-only` |
| Coverage | ryanluker.vscode-coverage-gutters | After test pass | `python -m pytest --cov=src --cov-report=term` |
| Python Debugger | ms-python.debugpy | During DEBUG tasks | Launch config + breakpoints |

### Git Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| GitLens | eamodio.gitlens | Before every commit | `git diff --stat` + `git diff` |
| Git Status | eamodio.gitlens | Before every commit | `gitkraken/git_status` MCP tool |
| Git Commit | eamodio.gitlens | After validation | `gitkraken/git_add_or_commit` MCP tool |
| Git Push | eamodio.gitlens | After commit | `gitkraken/git_push` MCP tool |
| Git Diff | eamodio.gitlens | Review changes | `gitkraken/git_log_or_diff` MCP tool |
| PR Create | eamodio.gitlens | When direct push blocked | `gitkraken/pull_request_create` MCP tool |

### Container Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| Docker | ms-azuretools.vscode-docker | Sandbox execution | `docker compose up <service>` |
| Dev Containers | ms-vscode-remote.remote-containers | Isolated environment | `.devcontainer/devcontainer.json` |
| Docker Explorer | ms-azuretools.vscode-docker | Container health | `docker ps`, `docker logs <id>` |

### API Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| Thunder Client | rangav.vscode-thunder-client | API validation | Import collection, run request |
| REST Client | humao.rest-client | Reproducible API calls | Execute `.http` file requests |

### Data & Notebook Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| Jupyter | ms-toolsai.jupyter | Data exploration | `run_notebook_cell` tool |
| Python REPL | ms-python.python | Quick validation | `python -c "<expr>"` |

### Remote Tools

| Tool | Extension | Agent Trigger | Command / MCP |
|------|-----------|---------------|---------------|
| Remote SSH | ms-vscode-remote.remote-ssh | Remote execution | SSH connection to remote host |

---

## 2. TASK-TYPE TOOL CHAINS

### PATCH (Code Change)

```
1. Edit file(s)
2. ruff check --fix <file>           ← Ruff Lint
3. ruff format <file>                ← Ruff Format
4. pylanceSyntaxErrors <file>        ← Pylance
5. python -m pytest -x -q <target>  ← pytest (targeted)
6. python -m pytest -x -q           ← pytest (full suite)
7. problems <file>                   ← Error Lens
8. git diff --stat                   ← GitLens (scope review)
9. git diff                          ← GitLens (content review)
10. git add + commit                 ← GitLens (conventional message)
11. git push                         ← GitLens
12. CI check                         ← Wait for CI result
13. If CI red → classify → fix → goto step 2
```

### DEBUG (Root Cause Analysis)

```
1. Read error / failure evidence
2. python -m pytest -x -v <failing>  ← pytest (verbose, targeted)
3. Read test output + traceback
4. Read source files along traceback
5. pylanceSyntaxErrors <files>       ← Pylance (type issues)
6. problems <files>                  ← Error Lens (all diagnostics)
7. If needed: debugpy launch config  ← Python Debugger
8. Route to forensic-debug.prompt.md
9. Apply fix → enter PATCH chain
```

### ANALYSIS (Read-Only Investigation)

```
1. Search codebase (grep, semantic)
2. Read relevant files
3. pylanceSyntaxErrors <files>       ← Pylance (health check)
4. python -m pytest --collect-only   ← Test Explorer (test inventory)
5. git log --oneline -20             ← GitLens (recent history)
6. Produce structured report
```

### VALIDATION (Verify Correctness)

```
1. python -m pytest -x -q            ← pytest (full suite)
2. python -m pytest --cov=src        ← Coverage
3. ruff check src/ tests/            ← Ruff (full project lint)
4. pylanceSyntaxErrors               ← Pylance (all files)
5. problems                          ← Error Lens (all diagnostics)
6. git status                        ← GitLens (clean working tree)
7. Report: pass/fail per tool
```

### API VALIDATION

```
1. Start service: docker compose up  ← Docker
2. Wait for health check endpoint
3. Execute .http request             ← REST Client
4. OR: Thunder Client collection run ← Thunder Client
5. Compare response vs expected
6. docker compose down               ← Docker (cleanup)
```

### EXPERIMENT (Sandbox)

```
1. Create sandbox snapshot           ← crypto-sandbox skill
2. docker compose -f docker-compose.sandbox.yml up  ← Docker
3. Run experiment inside container
4. Collect results
5. Compare vs production baseline
6. Destroy sandbox                   ← Docker cleanup
```

### DATA EXPLORATION

```
1. Open/create notebook              ← Jupyter
2. Load data snapshot
3. Run cells sequentially            ← run_notebook_cell
4. Validate data integrity
5. Export findings
```

---

## 3. TOOL EXECUTION MATRIX

| Tool | Trigger Event | Execution | Block Condition | Fallback |
|------|--------------|-----------|-----------------|----------|
| Ruff Lint | File saved/edited | `ruff check --fix <file>` | Any unfixable `E`/`F` diagnostic | Manual fix required |
| Ruff Format | After lint clean | `ruff format <file>` | File not formatted | `black <file>` |
| isort | Import changed | `ruff check --select I --fix <file>` | Import order broken | `isort <file>` |
| Pylance | Logic changed | `pylanceSyntaxErrors` MCP | Type error in changed file | Read error, fix manually |
| Error Lens | Continuous | `problems` tool | Error-level diagnostic | — |
| pytest | Behavior changed | `python -m pytest -x -q` | Any FAILED | Route to DEBUG chain |
| pytest | Behavior changed | `python -m pytest -x -q` | Unexpected SKIP/XFAIL | Investigate as DEFECT |
| Coverage | After tests pass | `pytest --cov=src` | Coverage drop >5% | Add tests |
| GitLens Diff | Pre-commit | `git diff --stat` | >200 lines | Split commits |
| GitLens Diff | Pre-commit | `git diff` | Mixed-purpose changes | Separate by concern |
| Git Commit | Post-validation | `git add + commit` | Dirty lint/test state | Restart chain |
| Git Push | Post-commit | `git push` | Branch protection | Switch to PR workflow |
| Docker | Sandbox/API test | `docker compose up` | Container fails to start | Fix Dockerfile/compose |
| Thunder Client | API validation | Run collection | Response mismatch | Investigate API |
| REST Client | API validation | Execute .http file | Status code ≠ expected | Investigate API |
| Jupyter | Data exploration | `run_notebook_cell` | Cell error | Fix cell, re-run |
| Debugger | DEBUG task | Launch config | — | Print-based debugging |
| Remote SSH | Remote execution | SSH connect | Connection failed | Fix SSH config |

---

## 4. INTERPRETATION RULES

### Ruff Output
- `E` prefix = error → **BLOCK**, must fix
- `W` prefix = warning → **BLOCK** unless justified in code comment
- `F` prefix = pyflakes → **BLOCK**, must fix
- `I` prefix = import order → **BLOCK**, auto-fixable
- `D` prefix = docstring → note only (not enforced)
- `N` prefix = naming → investigate, fix if genuine
- `S` prefix = security → **BLOCK**, must fix (bandit rules)
- `B` prefix = bugbear → **BLOCK**, likely bug
- `C` prefix = complexity → investigate if >15

### pytest Output
- `PASSED` → proceed
- `FAILED` → **BLOCK** → route to forensic-debugger if non-obvious
- `SKIP` → **DEFECT** unless test contract documents the skip reason
- `XFAIL` → **DEFECT** unless test contract documents the expected failure
- `WARNING` → **DEFECT**, investigate cause before proceeding
- `ERROR` → **BLOCK**, collection error = broken imports or fixtures

### Pylance Output
- Error → **BLOCK**, fix before proceeding
- Warning → investigate, fix if genuine
- Information → note only

### Coverage Output
- ≥80% → proceed
- 70-80% → WARNING, add tests for uncovered paths
- <70% → **BLOCK** for new code, investigate for existing

### git diff Output
- 1-50 lines → normal commit
- 51-200 lines → review carefully, consider splitting
- 200+ lines → **STOP**, must split into atomic commits
- Mixed-purpose → **STOP**, separate by concern

### Docker Output
- Container healthy → proceed
- Container restart loop → **BLOCK**, fix configuration
- Build failure → **BLOCK**, fix Dockerfile
- Network error → investigate, retry once

---

## 5. MANDATORY EXECUTION SEQUENCE

For **EVERY** code change, execute in this exact order:

```
┌─────────────────────────────────────────────────┐
│ 1. EDIT    │ Make the code change               │
│ 2. LINT    │ ruff check --fix + ruff format     │
│ 3. TYPE    │ pylanceSyntaxErrors on changed files│
│ 4. TEST    │ pytest -x -q (targeted then full)  │
│ 5. ERRORS  │ problems tool (Error Lens check)   │
│ 6. DIFF    │ git diff --stat + git diff         │
│ 7. COMMIT  │ Atomic conventional commit          │
│ 8. PUSH    │ git push origin <branch>           │
│ 9. CI      │ Wait for CI result                 │
│ 10. LOOP   │ If red → fix → goto step 2        │
└─────────────────────────────────────────────────┘
```

**ANY block at ANY step → fix and restart from step 2.**

---

## 6. FAIL-CLOSED RULES

### Hard Blocks (NEVER bypass)

- NO commit without clean Ruff
- NO commit without passing tests
- NO commit with Pylance errors in changed files
- NO commit with unreviewed diff
- NO commit with >200 line diff (must split)
- NO commit with mixed-purpose changes (must separate)
- NO push without commit
- NO `--no-verify` or `--force` EVER
- NO deploy without all tests green
- NO sandbox promotion without all gates passed

### Soft Blocks (Investigate, may proceed with justification)

- Pylance warning (may be false positive)
- Coverage below 80% on existing code
- Docker build warning
- Ruff `N` naming convention

### Auto-Recovery

| Failure | Recovery Action |
|---------|----------------|
| Ruff fixable diagnostic | `ruff check --fix` auto-resolves |
| Import order wrong | `ruff check --select I --fix` auto-resolves |
| Format drift | `ruff format` auto-resolves |
| Test failure (obvious) | Apply fix, re-run |
| Test failure (non-obvious) | Route to forensic-debug chain |
| Branch protection blocks push | Switch to PR workflow |
| Docker build fails | Read error, fix Dockerfile |

---

## 7. AUTONOMOUS LOOP PROTOCOL

```
code → lint → test → validate → commit → push → CI → feedback → fix → repeat
```

### Loop Governance

| Parameter | Value |
|-----------|-------|
| Max retries per task | 5 |
| Max same-failure retries | 3 (then switch strategy) |
| Lint fix retries | 3 (then report unfixable) |
| Test fix retries | 5 (then report structural failure) |
| CI fix-push cycles | 5 (then report blocking CI issue) |
| Type error fix retries | 3 (then report type system conflict) |

### Progress Tracking

Every retry MUST demonstrate measurable progress:
- Fewer failing tests
- Different failure message
- Reduced error count

If retry produces identical output → **STOP immediately**.

### Loop Termination

- CI GREEN + all gates passed → **DONE**
- Retries exhausted → **STOP** with evidence
- Same failure 3× → **STOP**, approach is wrong
- Working tree has unrelated changes → **STOP**
- More than 10 files modified → **STOP**, must split

---

## 8. TOOL SYNERGY PATTERNS

### Pattern: Lint-Fix-Test (LFT)
Most common. Used for every code change.
```
ruff check --fix → ruff format → pylance → pytest
```

### Pattern: Debug-Fix-Verify (DFV)
For test failures.
```
pytest -v (verbose) → read traceback → fix → LFT
```

### Pattern: Sandbox-Test-Promote (STP)
For experiments and risky changes.
```
docker compose up → run in sandbox → compare → promote or discard
```

### Pattern: API-Validate-Record (AVR)
For API endpoint validation.
```
docker compose up → REST Client .http → assert response → docker compose down
```

### Pattern: Explore-Validate-Export (EVE)
For data investigation.
```
jupyter notebook → load data → run cells → validate → export findings
```

### Pattern: Review-Commit-Push (RCP)
For git operations.
```
git status → git diff --stat → git diff → git add → git commit → git push
```
