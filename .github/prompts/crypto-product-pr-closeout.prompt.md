---
name: crypto-product-pr-closeout
description: "Close out an existing product PR: checks, reviews, merge, and postverify only."
agent: agent
---

Close out an already-open PR without adding new implementation scope.

Rules:
- no new product implementation
- checks/review/merge/postverify only
- standard merge only
- use JSON/API polling only for PR and check status
- do not use `gh pr checks --watch` or `gh run watch`
- do not run `gh pr review --approve` and do not self-approve

Pending CI or CodeQL is a polling state, not a blocker.
Block only on terminal failed checks, unresolved required reviews, or merge-policy violations.

Closeout steps:
1. inspect PR status and reviews
2. poll checks until terminal state
3. merge with standard merge when gates pass
4. pull main and post-verify required checks
5. report terminal result and next blocker if any
