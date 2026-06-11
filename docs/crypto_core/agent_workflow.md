# crypto_core Agent Workflow (canonical)

Single source of truth for the Claude + ChatGPT + Codex working loop on `crypto_core`.
Future prompts may simply say: *"Follow repo agent workflow; this slice adds X; extra forbidden: Y."*
Durable rails live here and in `AGENTS.md` — do not re-paste them into prompts.

## 1. Project scope

- Active scope: `src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, `docs/crypto_core` only.
- BIST is historical context only; no BIST leakage into crypto implementation.
- Standard: paper-first, deterministic, fail-closed, audit-first, derivatives-first,
  governance-first, risk-bounded.
- Current evidence chain (validated end-to-end, merged through PR #246):
  `SourcePacket -> StrategyValidationBundle -> BacktestAdmissionDecision -> BacktestReplayBridge
  -> ReplayEvidenceManifest -> PaperReplayIntake -> PaperReplayRunPlan -> PaperReplayResultReport`

## 2. Working loop (proven on #244/#245/#246)

1. **Claude** — implements one bounded slice (usually 2 files: module + tests), validates locally,
   opens one PR, stops. No merge, no CI polling unless the prompt asks.
2. **ChatGPT** — audits live GitHub state: head SHA, files, checks, reviews, threads, open-PR rule.
3. **Codex** — repairs real blockers, validates, pushes, polls CI/reviews/threads to terminal,
   and merges **only with explicit per-PR user authorization**; then postverifies main.

Rules: no direct push to `main`; one open PR at a time; standard merge only; CI/CodeQL *pending*
is never final — poll until terminal or merged/closed.

## 3. Model routing

| Lane | Use for |
|---|---|
| Claude Default/Opus | known-pattern implementation; 1–3 file validation contracts; tests/docs/setup patches; PR creation |
| Fable High | scarce window for architecture, high-risk safety semantics, invariant audits, chain red-team, EvidenceStore/persistence/Deribit readiness design, and top-1 roadmap decisions |
| Codex | default executor for merge/postverify, CI/thread polling, PR closeout, docs/setup edits, mechanical repair, validation reruns, compact execution, and local validation proof |

Fable must not be used for pure polling, merge mechanics, full-log handling, broad repo scans, or
routine closeout unless no viable alternative exists and the user explicitly authorizes that use.

## 4. Digest-boundary rule (recurring P1 class — always apply)

Any downstream consumer of a dataclass/result carrying a digest MUST:
recompute the upstream digest via the **public serializer**, remove the digest field itself,
canonical-JSON hash (`sort_keys=True`, `separators=(",", ":")`, `ensure_ascii=True`, SHA-256),
and **reject mismatch before READY/ADMITTED/ACCEPTED**. A matching id alone is never sufficient;
stale/forged/tampered upstream objects must fail closed. Tests must include a tampered-field case.

## 5. Safety guardrails

Forbidden unless explicitly authorized and separately designed:
live/private API; credentials; real orders; order routing; scheduler; auto-loop;
connector-readiness changes; shadow/live execution; Deribit readiness transition;
EvidenceStore/persistence unless that is the objective; backtest/replay engine unless that is the
objective; BIST behavior.

## 6. Validation policy

- Full crypto_core tests: `scripts/crypto_core/run_full_tests_logged.ps1` only — never bare full pytest.
- Targeted/area pytest through `scripts/crypto_core/run_logged_command.ps1` with unique
  `cache_dir`/`--basetemp` under `C:\tmp`.
- Run commands one at a time; no chained validation lines; no broad `git add .` (scoped paths only).
- Ladder: ruff check --fix -> ruff format -> ruff format --check -> ruff check -> targeted tests ->
  validation-area tests -> full helper.
- Always end with `git diff --check` and `git status --short --branch`; prove changed files are
  exactly the intended scope before commit.

## 7. State-claim policy

- Never claim repo/PR/main/CI state from memory. Every current-state claim requires terminal output,
  GitHub (`gh`) output, or explicit fresh user-provided output.
- If unverified, mark **UNKNOWN** or **UNPROVEN** — never guess.
- Stale "stacked all open" summaries are not accepted; verify open PRs live
  (`gh pr list --state open`) at the start of every task.

## 8. Claude Skills policy

- Do not install third-party skill ZIPs. No MCP servers, Playwright, or browser automation unless
  the current objective needs them and the user authorizes.
- Repo-local skill convention exists for Codex only (`.codex/skills/<name>/SKILL.md`, plain markdown,
  non-executable). The active Claude repo-local skills path is not established — for Claude, this
  policy file is authoritative; do not create active Claude skill packages.
- Future project-specific skill candidates (plain markdown only, on explicit request):
  `crypto_core_product_slice`, `crypto_core_pr_closeout`, `crypto_core_architect_fable`.
- Any skill must be non-executable markdown, must not bypass permissions, touch credentials,
  call live APIs, or change trading/runtime state.

## 9. Report templates (compact; no full logs — failure tails only)

Every report includes `FILES_READ_COUNT` and `CMDS_RUN_COUNT`. Keep reports compact; never paste full
logs unless the failure tail itself is required to prove a blocker.

**Claude implementation handoff**
```
RESULT / DECISION / FILES_CHANGED / API_ADDED / FAIL_CLOSED / VALIDATION (ruff + targeted N passed +
area + full PYTEST_EXIT) / PR (number, head SHA, files) / FINAL_GIT_STATUS / FILES_READ_COUNT /
CMDS_RUN_COUNT / NEXT_SAFE_ACTION
```

**Codex repair/closeout**
```
BLOCKER (source, claim, real?) / REPAIR (diff summary) / VALIDATION / CHECKS (name=conclusion,
terminal) / THREADS (unresolved count; only proven-fixed automated resolved) / HEAD SHA /
FILES_READ_COUNT / CMDS_RUN_COUNT / NEXT
```

**Merge/postverify (only after explicit per-PR authorization)**
```
MERGE (PR, merge SHA, standard) / POSTVERIFY (main pulled, ruff, full helper PYTEST_EXIT,
smoke if applicable) / REMOTE_SETTLE (merge-commit checks terminal) / FINAL_GIT_STATUS /
FILES_READ_COUNT / CMDS_RUN_COUNT
```

**Setup optimization**
```
RESULT / DECISION / FILES_CHANGED / SETUP_SUMMARY / TOKEN_REDUCTION_EFFECT / VALIDATION / PR /
FILES_READ_COUNT / CMDS_RUN_COUNT / NEXT
```

## 10. Token Efficiency V2 — named lanes (prompt-template layer)

Repeated procedure blocks (env/precheck, gate-module contract, validation ladder, PR ceremony,
merge closeout, report format) are versioned as **named lanes** in
`docs/crypto_core/agent_prompts/token_efficiency_v2.md`, with 20–60-line prompt templates, token
hygiene rules (clear/compact discipline, no full logs, FILES_READ/CMDS_RUN counts), and model
routing v2. Prompts reference lanes and supply only deltas. Lanes compress procedure text only —
§4–§7 and `AGENTS.md` hard rails bind in every lane; on any apparent conflict the safety rule wins.
