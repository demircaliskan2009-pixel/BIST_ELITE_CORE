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