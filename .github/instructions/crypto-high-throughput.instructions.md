---
name: "Crypto High-Throughput Instructions"
description: "Persistent workspace instructions for high-throughput crypto_core setup, triage, closeout, and bounded phase dispatch."
applyTo: "docs/crypto_core/**, .github/prompts/crypto-*.prompt.md, .github/agents/crypto-throughput-commander.agent.md"
---

# LEGACY: CRYPTO HIGH-THROUGHPUT WORKSPACE RULES

Status: legacy profile for closeout and CI polling only.
Default product implementation mode now lives in .github/instructions/product-value-implementation.instructions.md.
This file is not the default implementation policy.

- Do not optimize for premium request burn.
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
- Every failure must produce a lesson classification.
- Do not repeat the same failure class without updating prompt/protocol guidance.
- Unresolved `NEEDS_HUMAN_DECISION` blocks merge.
- Do not weaken fail-closed rules for speed.

## Operating Preference

- Use this profile for PR closeout, check polling, and mechanical follow-through only.
- Copilot Auto remains valid for deterministic closeout operations.
- Codex quota is unavailable in this sprint mode; do not stop with `CODEX_REQUIRED`.
- If a slice is too broad, too risky, or too reasoning-heavy for Auto, split into smaller Copilot-safe PR slices and use `COPILOT_SLICE_REQUIRED`, `HIGH_REASONING_SPLIT_REQUIRED`, `SPLIT_PLAN_REQUIRED`, or `BLOCKED_WITH_PROOF`.
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

## Retrospective Loop

- After every merged or blocked PR, run `crypto-post-pr-retrospective`.
- For repeated, generalizable failures, propose `crypto-error-to-protocol-update`.
- Record durable lessons in `docs/crypto_core/COPILOT_HIGH_THROUGHPUT_LESSONS_LEDGER.md` with proof references.
