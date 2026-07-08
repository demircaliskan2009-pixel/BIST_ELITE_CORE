---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core implementation, repair, salvage, PR closeout, or setup tasks that require maximum safe throughput with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

Use this skill only for `crypto_core` work in BIST_ELITE_CORE when the task asks for implementation,
repair, dirty-branch salvage, PR closeout, or setup hardening.

## Roles & Canonical Doctrine

Canonical doctrine (precedence): `AGENTS.md` → `docs/crypto_core/agent_workflow.md` → this skill →
`CLAUDE.md`; evidence-backed lessons in `docs/crypto_core/agent_lessons.md`. Codex here is an **adversarial
P1/P2 reviewer, read-only by default** — hunt hidden bugs / exploits and audit digest/schema/API contracts
and provenance/evidence chains; **patch only when patching is explicitly authorized and scoped**, same
branch only. Use **Codex Pursue Goal only** for bounded single-goal GitHub/CI loops (CI polling, repo/branch
sync, PR closeout/status, review-thread disposition planning, `gh` state `PASS/FAIL/BLOCKED`, authorized
merge/post-merge verify) — **never** for complex implementation, design, digest/provenance architecture,
ambiguous slicing, or unscoped multi-file repair. Setup/doctrine changes go in a separate `chore/<scope>-prN`
PR, never mixed into a feature PR. **Deep Research** is the external/current-fact + architecture-benchmark
tool (and combined repo+external review in the GitHub connector chat): **strictly read-only / advisory**,
never an executor lane, never merge authority, never a safety-gate waiver. It never mutates repo or GitHub
state (branch/file/commit/push/PR/comment/thread-resolve/workflow-rerun/merge/auto-merge), even when the
underlying work is authorized; it may only **recommend** a mutation task, and the controller routes any
authorized mutation to Claude/`gh`, the GitHub connector, or Codex. ChatGPT decides when it runs and Claude
only recommends it (`DEEP_RESEARCH_REQUIRED`) when blocked by a current/external fact. Full protocol:
`docs/crypto_core/deep_research_protocol.md` (`docs/crypto_core/agent_workflow.md` §19).

**Post-Fable increased-use policy (`agent_workflow.md` §21, 2026-07-07):** Fable 5 availability is no
longer assumed; Codex inherits its adversarial-reasoning share and runs MORE often — a read-only P1/P2
audit after every high-risk design (before implementation), after every high-risk implementation (before
the GitHub-connector final gate), and whenever a claim could overreach (completion / readiness /
live / shadow / Deribit / machine-time proof / real orders / capital / profitability / edge). Codex stays
read-only unless explicitly rerouted as implementation fallback. Attestation-only evidence
(`operator_attested_not_machine_proven.v1`, all five machine-proof flags structurally False) is never
machine proof and never Stage-4 completion.

## Codex Audit Contract

- Default mode: independent **read-only** P1/P2 auditor. Never merge; never patch a PR concurrently
  with Claude; never resolve human review threads.
- Severity taxonomy: **P1** = correctness/safety break (wrong digest boundary, silent trust,
  overclaim, forbidden surface) — blocks merge; **P2** = real defect or missing negative-path proof
  that should be fixed pre-merge; **P3** = advisory/style — never blocks.
- Digest/reseal/provenance rubric: can a resealed, tampered, or exact-typed lookalike input reach
  READY/ACCEPTED? Is every carried digest recomputed via the public serializer
  (`recompute == carried == expected anchor`)? Are carried flags/summaries ever trusted instead of
  recomputed from raw canonical fields?
- AST forbidden-surface rubric: no imports of live/order/scheduler/readiness/runtime surfaces in
  evidence modules; structural-False flags provably unassignable-True (AST + source scan).
- Overclaim rubric: any affirmative completion/readiness/live/shadow/Deribit/machine-time/real
  capital/profitability/edge claim without the exact proving gate = P1.
- Prompt/workflow consistency rubric: prompts must match `AGENTS.md` / `agent_workflow.md` §20-§21
  lanes and the archived contracts in `docs/crypto_core/fable_exit_contract_index.md`; contradictions
  are findings, not silently reconciled.
- Audit report format: verdict `READY | NOT_READY`, findings as `P1/P2/P3 | file:line | failure
  scenario`, plus `CLEAN` sections explicitly named. A Codex audit is REQUIRED before the
  GitHub-connector final gate on every high-risk PR.
- Audit token discipline (`docs/crypto_core/token_efficiency_playbook.md`; correctness always wins):
  two distinct audit types — DESIGN audit (contract/invariants, before implementation) and
  IMPLEMENTATION audit (diff at the pinned head, before the connector gate) — never conflate them.
  Read the changed files and their direct dependencies only; no repo-wide rereads per audit; no CI
  polling with model tokens (state comes from the prompt or one `gh` snapshot). Keep findings
  concise: P1/P2 with file:line and failure scenario; flag pure token waste as P3 unless it caused
  a missed proof (then it is the appropriate higher class). Never shallow an audit to save tokens.

## Gate First

- Prove workspace, branch, HEAD, open PRs, and dirty files before editing.
- Stop if dirty files exceed the user-approved scope.
- Read named files first; use targeted `rg` before broader exploration.

## Patch Discipline

- Stay crypto-only and paper-only.
- No live/private APIs, credentials, real orders, scheduler/auto-loop, connector readiness, B5,
  venue/runtime expansion, BIST edits, or setup edits unless explicitly scoped.
- Prefer additive changes and existing service surfaces.
- Preserve deterministic digests, provenance, fail-closed errors, and audit evidence.

## Validate and Publish

- Run focused Ruff/tests, then full `tests/crypto_core` when release-gating or requested.
- Run local validation commands one at a time; do not chain Ruff, format, pytest, or git checks in a
  single shell command.
- For validation that can hang or run longer than a trivial Ruff check, use a logged timeout wrapper
  such as `scripts/crypto_core/run_logged_command.ps1`. Reports should include command name, exit
  code, log paths, and stdout/stderr tails.
- Never run bare `python -m pytest -x -q tests/crypto_core`. Use the logged wrapper:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_full_tests_logged.ps1`
  or an equivalent command with a unique `cache_dir`, unique `--basetemp`, and log captured from
  start.
- Do not start a second local validation run while a matching prior run may be active. If a run is
  overlong, sample process start time, CPU, responsiveness, and command line if accessible; stop only
  a proven matching validation PID. Never broad-kill Python, Ruff, or PowerShell processes.
- For dependency PRs, do not repeat full local pytest after logged proof unless a new repair is made.
  Poll remote CI separately; pending CI is not failure.
- Run `git diff --check` and prove exact changed-file scope.
- Stage exact paths only.
- Never push directly to `main`; never force push; never merge without exact PR authorization.
- For automated review repair: fix only real in-scope findings, add regression proof, rerun
  validation, push, re-prove checks, and resolve only proven-fixed automated threads.

## Report

Keep reports short: result, proof, changed files, validation, PR/check state, blockers, next safe
action.
