---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation/audit loops in BIST_ELITE_CORE — task-class context budgets (T0-T4), intake, validation ladder, and report shape. Use when starting a crypto_core task to minimize tokens without weakening gates.
---

# Crypto Core Token-Efficient Loop

Full doctrine: `docs/crypto_core/token_efficiency_playbook.md` (T0-T4 budgets, intake, report
compression, prompt reuse, anti-patterns). This checklist is the on-demand short form. Token
saving is subordinate to correctness; no gate may be skipped to save tokens.

## Loop

1. **Classify** the task T0-T4 (status / docs / bounded impl / high-risk contract / external fact)
   and pick the lane: Sonnet/Fast = mechanical; Opus 4.8 (xhigh for T3) = implementation/design;
   Codex = read-only P1/P2 audit; Deep Research = external facts only. Never an expensive lane for
   CI polling, status, or merge mechanics.
2. **Prove state** with one `git`/`gh` snapshot (HEAD, tree, open PRs; checks if merging).
3. **Name the read set** before reading; symbol grep before full-file reads; build one source
   surface map and work from it; don't reread unchanged files.
4. **Patch** only named allowed files (crypto_core scope; fail-closed; digest-boundary rule).
5. **Validate** the ladder: `ruff check` / `ruff format --check` on the patched scope → targeted
   pytest → logged full suite where doctrine requires (`run_full_tests_logged.ps1`, PYTEST_EXIT=0)
   → `git diff --check`. One command at a time.
6. **Publish**: scoped `git add` exact paths; commit; push; one open PR; CI one-shot snapshots —
   pending = NOT_READY.
7. **Report** compact fixed fields: RESULT / verdict-first summary / FILES_CHANGED / VALIDATION /
   PR-CI evidence / NEXT_SAFE_ACTION. Failure tails only; no doctrine restating.

## Hard limits (unchanged by this skill)

No merge without explicit human authorization; no direct `main` push; no admin/squash/rebase;
Codex design audit before high-risk implementation and impl audit before the connector gate;
GitHub-connector final gate never waived; no BIST leakage; no live/order/capital/readiness
surface; no Stage-4 completion / machine-time / secondary-metrics-enforced claims.
