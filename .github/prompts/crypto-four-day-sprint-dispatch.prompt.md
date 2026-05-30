---
name: crypto-four-day-sprint-dispatch
description: "Dispatch every new crypto_core request into exactly one high-throughput lane with fail-closed boundaries."
agent: agent
---

You are dispatching a new request for the next four days of high-throughput crypto_core work.

Choose exactly one:
- PR_CLOSEOUT_ONLY
- CURRENT_BRANCH_TRIAGE
- PHASE_RUNNER_HIGH_THROUGHPUT
- REVIEW_THREAD_RESOLVER
- NEXT_PHASE_PLANNER
- COPILOT_SLICE_REQUIRED
- HIGH_REASONING_SPLIT_REQUIRED
- DEEP_RESEARCH_REQUIRED

Rules:
- crypto_core only.
- No unresolved PR accumulation.
- No new phase while the current PR is blocked.
- High-throughput, but not reckless.
- Every request should attempt merge and post-verify if safe.
- Auto model should execute autonomously until proof, merge, or blocker.
- Do not widen scope just to spend a premium request.
- Do not start a phase if a review gate or CI gate is still unresolved.
- After merge or blocker outcome, run `crypto-post-pr-retrospective`.
- Propose `crypto-error-to-protocol-update` only for broadly reusable lessons.
- Log durable lessons in `docs/crypto_core/COPILOT_HIGH_THROUGHPUT_LESSONS_LEDGER.md`.

Dispatch logic:
1. If an open crypto_core PR exists and the task is closeout only, choose `PR_CLOSEOUT_ONLY`.
2. If the current branch has dirty, mixed, or oversized changes, choose `CURRENT_BRANCH_TRIAGE`.
3. If the task is a bounded phase with known files and validation, choose `PHASE_RUNNER_HIGH_THROUGHPUT`.
4. If a PR has review comments or threads that need repair, choose `REVIEW_THREAD_RESOLVER`.
5. If the task is planning-only and must not patch, choose `NEXT_PHASE_PLANNER`.
6. If Auto is not enough for a safe answer, choose `COPILOT_SLICE_REQUIRED` or `HIGH_REASONING_SPLIT_REQUIRED` with a smaller PR order.
7. If the next decision depends on external evidence or current venue/API facts, choose `DEEP_RESEARCH_REQUIRED`.

Output exactly this:

DISPATCH:
REASON:
PR_STATE:
SCOPE:
NEXT_ACTION:
