---
name: "Crypto High-Throughput Instructions"
description: "Persistent workspace instructions for high-throughput crypto_core setup, triage, closeout, and bounded phase dispatch."
applyTo: "docs/crypto_core/**, .github/prompts/crypto-*.prompt.md, .github/agents/crypto-throughput-commander.agent.md"
---

# CRYPTO HIGH-THROUGHPUT WORKSPACE RULES

- Use premium requests aggressively only for validated `crypto_core` work.
- Prefer small, mergeable PRs over huge diffs.
- If a diff grows large or unclear, trigger current-branch triage before proceeding.
- Do not start a new phase while a current PR is unresolved.
- During CI waits, gather proof only; do not widen scope.
- Classify all reviewThreads before merge.
- Unresolved `REAL_BLOCKER`, `VALID_SAFETY_FIX`, or `NEEDS_HUMAN_DECISION` blocks merge.
- Preserve deterministic, fail-closed, audit-first behavior.
- No BIST assumptions.
- No live/private/execution/order-routing drift unless explicitly authorized by the current phase.
- No silent refactor.
- No speculative code.
- No request-spend without merge, proof, or an explicit blocker.

## Operating Preference

- Default to the `Crypto Throughput Commander` agent for bounded `crypto_core` setup, triage, closeout, and review-thread repair.
- Use Copilot Auto for deterministic docs, prompts, telemetry artifacts, and closeout phases.
- Escalate to Codex only when the current slice is too broad, too risky, or too reasoning-heavy for Auto.
- Require Deep Research only when external evidence is needed and the repository cannot prove the answer.

## Merge Discipline

- Standard merge only.
- No squash merge.
- No rebase merge.
- No direct push to `main`.
- No admin merge.
- No branch deletion.

## Safety Gate

Before any merge or phase handoff, verify:

- branch scope is still `crypto_core` only
- no open PR accumulation is hiding the current task
- review threads are resolved or classified and blocked appropriately
- CI and CodeQL are green when present
- the requested phase still matches the current repository state

## Failure Mode

If the requested work would cross into BIST or non-crypto implementation space, stop and report the blocker.
If the evidence is insufficient, report `INSUFFICIENT EVIDENCE`.
