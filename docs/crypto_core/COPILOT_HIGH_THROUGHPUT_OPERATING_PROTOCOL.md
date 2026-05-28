# Copilot High-Throughput Operating Protocol

## Objective

Maximize useful merged `crypto_core` work per premium request.
The goal is not maximum diff size.
The goal is to produce validated, reviewable, mergeable work that ends in one of these states:

- `MERGED_AND_POST_VERIFIED`
- `BLOCKED_WITH_PROOF`
- `SPLIT_PLAN_REQUIRED`

## Scope

- `crypto_core` only.
- No BIST work.
- No non-crypto implementation work.
- No leakage into runtime trading logic unless the current phase explicitly authorizes it.
- No live, private, execution, or order-routing drift unless the current phase explicitly authorizes it.

## Operating Rules

- Keep PRs small and bounded.
- Prefer small, sequential PR-safe slices over large uncontrolled diffs.
- Split phases when the change set grows beyond a reviewable slice, when unrelated concerns appear, when validation scope becomes ambiguous, or when a single PR would exceed the repo gate for intended files.
- Use Copilot for narrow, local, deterministic, well-scoped work.
- Use Codex when the phase is broader, cross-file, review-thread heavy, or requires stronger multi-step reasoning to keep the slice safe.
- Use Deep Research only when a decision depends on external evidence, architectural confirmation, or a document-level comparison that cannot be proven from the repository alone.

## Small PR Policy

- Prefer one logical change per PR.
- Keep diffs focused on the minimum files needed for the phase.
- If unrelated files appear, stop and split before PR.
- If generated, cache, or artifact files appear, remove them before PR.
- If the phase cannot stay bounded, stop and produce a split plan instead of forcing a large PR.

## Mandatory Validation Set

For every bounded phase, run the required validation for the touched slice and the crypto_core baseline:

- targeted tests for the touched area
- full `tests/crypto_core`
- Ruff on the scoped crypto_core paths
- readiness probe
- connector probe
- `git diff --check`
- `git diff --stat`
- `git diff --name-only`
- clean branch/status verification before PR and before merge

## Review-Thread Gate

- Do not merge with unresolved review threads.
- Classify every thread before merge.
- Resolve only threads that are addressed by the current patch or are valid safety fixes.
- Leave style-only churn out of the patch.
- If a thread requires a real code change, patch and rerun validation before resolving it.

## Standard Merge Policy

- Standard merge only.
- No squash merge.
- No rebase merge.
- No direct push to `main`.
- No admin merge.
- No branch deletion.

## Post-Merge Proof Package

After merge, capture proof that the merged result is present and healthy:

- merge commit identity
- merge method
- main HEAD after pull
- final `git status --short --branch`
- Ruff result on `src/crypto_core tests/crypto_core scripts/crypto_core`
- `tests/crypto_core` result
- readiness probe result
- connector probe result
- any remaining blocker, if present

## Decision Summary

If a change cannot be kept small, validated, and reviewable, do not force it.
Return `BLOCKED_WITH_PROOF` or `SPLIT_PLAN_REQUIRED` instead.

## Setup V2 Complete Definition

Setup v2 is complete only when all of the following are true:

- the agent spec exists at `.github/agents/crypto-throughput-commander.agent.md`
- the persistent instruction file exists at `.github/instructions/crypto-high-throughput.instructions.md`
- the sprint dispatcher exists at `.github/prompts/crypto-four-day-sprint-dispatch.prompt.md`
- the model escalation policy exists at `.github/prompts/crypto-model-escalation-policy.prompt.md`
- the operator guidance in this document is aligned with the agent spec
- the ready-to-paste custom agent spec in [COPILOT_CUSTOM_AGENT_CRYPTO_THROUGHPUT_COMMANDER.md](COPILOT_CUSTOM_AGENT_CRYPTO_THROUGHPUT_COMMANDER.md) matches the workspace agent
- the setup has been merged and post-merge verified on `main`

## Actual Agent Path

Default execution path for high-throughput crypto_core work:

1. `Crypto Throughput Commander` agent
2. `Copilot Auto` as the default model
3. `crypto-four-day-sprint-dispatch` for request routing
4. `crypto-model-escalation-policy` for escalation decisions
5. bounded phase or closeout prompt from the prompt library

## Auto Default Policy

- Use Copilot Auto first for deterministic setup, closeout, and bounded docs work.
- Escalate only when the request is not safely bounded, needs broader reasoning, or depends on outside evidence.
- Do not spend premium requests on broad exploration when a smaller lane can prove the answer.

## Four-Day Sprint Cadence

- Day 1: triage and closeout first, then the smallest safe bounded phase.
- Day 2: continue the highest-value merged slice only.
- Day 3: resolve blockers, review threads, or split the remaining work into safer PR-sized units.
- Day 4: finish with merge, post-merge proof, or a blocked split plan.

## Throughput Safety Gates

- never start a new phase while the current PR is unresolved
- never merge with pending CodeQL
- never merge with unresolved review threads
- never widen scope during CI waits
- never let a large uncontrolled diff bypass current-branch triage

## Anti-Patterns

- huge uncontrolled diffs
- starting a new phase during a pending PR
- merging with pending CodeQL
- skipping reviewThreads
- repeated boilerplate prompts that do not create proof
- request-spend without merge or blocker evidence

## Setup V3 Scope Rule

High-throughput instructions must apply only to:

- `docs/crypto_core/**`
- `.github/prompts/crypto-*.prompt.md`
- `.github/agents/crypto-throughput-commander.agent.md`

They must not apply to BIST or other non-crypto files.