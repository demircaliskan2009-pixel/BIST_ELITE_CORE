---
name: crypto-pr-closeout
description: "Use when a crypto_core PR is already open and needs review-thread handling, CI waiting, merge, and post-merge verification."
agent: agent
---

Close out the already-open PR without changing scope.

Rules:
- crypto_core only.
- No new implementation phase unless review or CI reveals a real blocker.
- No BIST leakage.
- No silent refactor.
- No squashing, rebasing, admin merge, or direct main push.
- Standard merge only.
- Fail closed on ambiguity.

Workflow:
1. Inspect PR state, checks, and review threads.
2. Wait for tests, CodeQL, and CI to finish if still running.
3. Classify every review thread.
4. Resolve only addressed threads.
5. Patch only real blockers or valid safety fixes.
6. Add a regression test only if the blocker is behavioral.
7. Rerun the required validation.
8. Merge by standard merge only.
9. Pull `main` and verify post-merge state.
10. Capture proof.
11. Run `crypto-post-pr-retrospective` for merge/blocker outcome.
12. If lessons are repeated and generalizable, propose `crypto-error-to-protocol-update`.
13. Append durable lessons to `docs/crypto_core/COPILOT_HIGH_THROUGHPUT_LESSONS_LEDGER.md`.

Thread classification:
- `REAL_BLOCKER`
- `VALID_SAFETY_FIX`
- `NON_BLOCKING_STYLE`
- `OUTDATED_AFTER_PUSH`
- `ALREADY_FIXED_AND_RESOLVED`
- `NEEDS_HUMAN_DECISION`

Do not merge if any `REAL_BLOCKER` or `VALID_SAFETY_FIX` remains unresolved.
Do not merge if any `NEEDS_HUMAN_DECISION` remains unresolved.

Closeout report format:
- PR state
- checks
- thread summary
- patches made, if any
- validation
- merge method
- main HEAD
- final git status
- next blocker, if any