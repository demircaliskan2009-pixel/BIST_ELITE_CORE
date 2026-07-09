---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core implementation, repair, salvage, PR closeout, or setup tasks that require maximum safe throughput with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

Use this skill only for `crypto_core` work in BIST_ELITE_CORE. Canonical precedence is `AGENTS.md`,
`docs/crypto_core/agent_workflow.md` section 23, this skill, then `CLAUDE.md`.

## Active routing

- T0 Luna mechanical: git/gh status, CI polling, PR metadata, review-thread state, and postverify runner.
- T1 Luna or Terra read-only: bounded proof, docs, and direct-dependency audit.
- T2 Terra bounded code: exact-file deterministic implementation, tests/docs, and small P1/P2 repairs.
- T3 Terra repair or Opus heavy: current fail-closed/review-blocker repair; Opus 4.8 xhigh when broad reads
  or long local validation loops are needed.
- T4 Sol cross-contract: scarce trust-boundary, governance/safety, SM-5/SM-6 design/audit, and
  readiness/Deribit provenance reasoning. Use `xhigh` by default; `max` only with explicit controller gate.
- XR: Deep Research for external/current facts, advisory only.
- ChatGPT/controller plus connector/`gh`: final evidence comparison and merge authority.

Every serious prompt/report contains `MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`,
`REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`, and declared fallback. Required exact-model mismatch stops.
Otherwise report the actual runtime and never claim unavailable-model quality.

## Role boundaries

Codex is an adversarial P1/P2 reviewer, read-only by default. Patch only when explicitly authorized and
scoped; never patch a PR concurrently with Claude or merge as a reviewer. A Terra implementation cannot
self-satisfy the independent audit gate in the same context. Independent audits are fresh-context,
pinned-head tasks.

Codex Pursue Goal is a bounded single-goal terminal loop for preflight, sync, CI/status, closeout, and
explicitly authorized merge/postverify. It is not broad repo pursuit, unscoped design, or unscoped repair.

Deep Research is external/current-fact advisory only. It never mutates repo or GitHub state, approves a
governance value, replaces a Codex audit, or waives a safety gate.

## Safety and audit contract

- Stay crypto-only, paper-only, deterministic, fail-closed, and audit-first.
- No BIST, live/private API, credentials, orders, scheduler, runtime/readiness/Deribit transition,
  shadow/live, or capital work unless separately authorized and designed.
- P1 is a correctness/safety break; P2 is a real defect or missing negative-path proof; P3 is advisory.
- Recompute digest-carrying inputs through their public serializer and reject mismatches before
  READY/ADMITTED/ACCEPTED. Forged or non-serializable input must fail closed, never raw-raise unexpectedly.
- Overclaim of completion/readiness/live/shadow/Deribit/machine-time/capital/profitability without its exact
  gate is P1.
- Current valid P1/P2 threads block. Outdated threads do not block code; resolve only with explicit guarded
  closeout authority. Never resolve human threads.

## Gate, patch, and validation discipline

- Prove workspace, branch, HEAD, dirty files, and open PRs before editing. Stop if dirt exceeds scope.
- Setup/doctrine work uses a separate `chore/<scope>-prN` PR and never mixes feature code.
- Use named files and targeted `rg`; no broad scans without justification.
- Product patches validate focused Ruff/tests then logged full suite when required. Docs/setup-only changes
  prove exact scope and run `git diff --check` unless an executable/config surface changed.
- Stage exact paths only. Never push directly to `main`, force-push, self-approve, or merge without exact
  human authorization.

## Report

Report result, actual model/effort, proof, changed files, validation, PR/check/thread state, blockers, and
one next safe action. No full logs or unsupported state claims.