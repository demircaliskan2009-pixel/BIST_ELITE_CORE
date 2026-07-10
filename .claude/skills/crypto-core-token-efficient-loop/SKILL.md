---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation/audit loops in BIST_ELITE_CORE - common task classes, validation ladder, and report shape without weakening gates.
---

# Crypto Core Token-Efficient Loop

Full doctrine: `docs/crypto_core/token_efficiency_playbook.md` and `agent_workflow.md` section 23. Token
saving is subordinate to correctness; no gate may be skipped to save tokens.

## Loop

1. Classify: T0 Luna mechanical; T1 Luna or Terra read-only; T2 Terra bounded code; T3 Terra repair or
   Opus heavy local; T4 Sol cross-contract; XR Deep Research; controller/connector final evidence gate.
2. Prove state once with `git`/`gh`: HEAD, clean tree, open PRs, and checks when relevant.
3. Name the read set before reading; use symbol search before full files; build one source surface map.
4. Patch only named files, preserving paper-only, fail-closed, and digest-boundary rules.
5. Validate one command at a time: scoped Ruff/format, targeted tests, logged full suite when required,
   then `git diff --check`.
6. Publish with scoped `git add`, one PR, and bounded CI snapshots. Pending is `NOT_READY`.
7. Report actual/requested model and reasoning, exact scope, validation, PR/CI evidence, and next action.

## Boundaries

- Claude Opus 4.8 owns broad local implementation and long loops; it hands high-risk design/implementation
  to a fresh pinned-head Terra or Sol Codex audit as required.
- Terra implementation never self-satisfies independent review in the same context.
- Sol is scarce and never used for mechanics. Luna never performs broad design or feature implementation.
- Codex Pursue Goal is a bounded terminal preflight/sync/CI/status/closeout/authorized-postverify loop only.
- No BIST, live/order/capital/readiness surface, direct main push, non-standard merge, or unproven claim.