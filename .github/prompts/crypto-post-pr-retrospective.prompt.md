---
name: crypto-post-pr-retrospective
description: "Run after every merged or blocked crypto_core PR to classify outcomes, extract durable lessons, and decide whether setup protocol updates are required."
agent: agent
---

Run a post-PR retrospective for the latest crypto_core PR outcome.

Rules:
- crypto_core workflow/setup context only.
- Never weaken quality or fail-closed gates.
- Never auto-update protocol files without a scoped patch/PR request.
- Only propose broadly reusable improvements.

Outcome classification (choose one):
- `MERGED_AND_POST_VERIFIED`
- `BLOCKED_WITH_PROOF`
- `SPLIT_PLAN_REQUIRED`
- `REVIEW_FIX_REQUIRED`
- `CI_FIX_REQUIRED`
- `SCOPE_REPAIR_REQUIRED`
- `USER_DECISION_REQUIRED`

Extract lessons:
- root cause
- missed precheck
- missed fail-closed check
- prompt ambiguity
- review-thread category
- CI bottleneck
- scope hygiene issue
- merge-policy issue

Protocol decision (choose one):
- `NO_PROTOCOL_CHANGE`
- `UPDATE_PROMPT_TEMPLATE_REQUIRED`
- `UPDATE_AGENT_RULE_REQUIRED`
- `UPDATE_INSTRUCTIONS_REQUIRED`
- `ADD_TRIAGE_RULE_REQUIRED`
- `ADD_FAIL_CLOSED_PATTERN_REQUIRED`

Stop conditions:
- If lesson is not generalizable, output `NO_PROTOCOL_CHANGE`.
- If evidence is insufficient, output `INSUFFICIENT EVIDENCE`.

Output:
- outcome_class
- evidence_summary
- lesson_list
- recurrence_assessment
- protocol_decision
- proposed_file_targets
- proof_links_required
