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
- Never run bare `python -m pytest -x -q tests/crypto_core`. Use the logged wrapper:
  `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_full_tests_logged.ps1`
  or an equivalent command with a unique `cache_dir`, unique `--basetemp`, and log captured from
  start.
- Do not start a second full pytest while a prior full run may be active. If a run is overlong,
  sample Python process start time, CPU, responsiveness, and command line if accessible; stop only a
  proven matching pytest PID. Never use broad Python process kills.
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
