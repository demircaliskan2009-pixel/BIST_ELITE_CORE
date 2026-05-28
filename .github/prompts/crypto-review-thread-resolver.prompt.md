---
name: crypto-review-thread-resolver
description: "Use to classify and resolve review threads on a crypto_core PR with minimal safe patches and no style-only churn."
agent: agent
---

Resolve review threads on the active crypto_core PR.

Rules:
- crypto_core only.
- No BIST leakage.
- No style-only churn.
- No broad refactor.
- Patch only `REAL_BLOCKER` and `VALID_SAFETY_FIX` threads.
- Add a regression test when the fix changes behavior.
- Re-run validation before resolving threads.
- Resolve threads only after the fix is proven.
- After thread-driven PR closeout, run `crypto-post-pr-retrospective`.
- If the same review issue class repeats, propose `crypto-error-to-protocol-update`.
- Record durable, proven lessons in `docs/crypto_core/COPILOT_HIGH_THROUGHPUT_LESSONS_LEDGER.md`.

Workflow:
1. Fetch PR details, reviewThreads, comments, and reviews.
2. Classify every thread.
3. Identify the smallest safe patch for each actionable thread.
4. Apply only the real fix.
5. Add or update validation if the behavior changed.
6. Re-run the required checks.
7. Resolve the addressed thread.
8. Repeat until only non-actionable threads remain.

Thread classes:
- `REAL_BLOCKER`
- `VALID_SAFETY_FIX`
- `NON_BLOCKING_STYLE`
- `OUTDATED_AFTER_PUSH`
- `ALREADY_FIXED_AND_RESOLVED`
- `NEEDS_HUMAN_DECISION`

Stop conditions:
- evidence is insufficient
- a thread requires a larger phase than the current slice
- the thread is style-only
- the fix would create scope drift

Report format:
- thread id
- classification
- fix applied
- validation
- resolution status
- remaining blockers