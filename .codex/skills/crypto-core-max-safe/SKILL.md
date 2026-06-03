---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core implementation, repair, salvage, PR closeout, or setup tasks that require maximum safe throughput with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

Use this skill only for `crypto_core` work in BIST_ELITE_CORE when the task asks for implementation,
repair, dirty-branch salvage, PR closeout, or setup hardening.

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
- Run `git diff --check` and prove exact changed-file scope.
- Stage exact paths only.
- Never push directly to `main`; never force push; never merge without exact PR authorization.
- For automated review repair: fix only real in-scope findings, add regression proof, rerun
  validation, push, re-prove checks, and resolve only proven-fixed automated threads.

## Report

Keep reports short: result, proof, changed files, validation, PR/check state, blockers, next safe
action.
