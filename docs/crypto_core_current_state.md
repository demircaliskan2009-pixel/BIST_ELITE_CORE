# Crypto Core Current State

This note is a compact continuity aid for Codex setup and future crypto_core phases. It is not a PRD and does not replace `docs/PRDV4_MULTI_MARKET_CRYPTO.md`.

## Active Stream

- Active implementation scope is `src/crypto_core/**` and `tests/crypto_core/**`.
- Legacy BIST code is out of scope unless the user explicitly requests it.
- Future work should continue from the latest committed crypto_core state after checking `git status` and recent crypto_core commits.
- All future phases remain paper-only unless explicitly instructed otherwise.

## Verified Surfaces Present

The current tree contains crypto_core surfaces for:

- pipeline and service orchestration
- campaign, review, and readiness flows
- external-regime governance
- decision-pack and escalation workflow
- crypto sleeve portfolio state
- sleeve qualification and recommendation
- sleeve campaign evidence
- sleeve decision pack
- sleeve candidate workflow
- sleeve promotion review and admission flow

## Operating Reminder

Preserve deterministic replay, fail-closed behavior, explicit auditability, scoped git hygiene, and evidence-before-promotion. Do not add fake data, live trading enablement, credentials, or provider/network expansion unless the task explicitly asks for it.

## Known Blockers

### Blocker 1 — ServiceOrchestrator missing `_sleeve_candidate_workflow_controller` — RESOLVED

- **Commit:** `d2d8b893c85e16cb94b25dd6d5b6d4c800002b5a`
- `_sleeve_candidate_workflow_controller` added to `__init__` after `_sleeve_admission_controller = None`.
- Dead-code block (12 lines after `return` in `get_sleeve_admission_portfolio_summary`) removed.
- Full suite: all tests green.

### Phase 16L Status

- **Status:** Implemented by Codex (GPT-5.5). Targeted tests pass (`test_phase10a.py` + `test_phase10b.py` clean).
- **Files:** `src/crypto_core/service/promotion_review.py` and `tests/crypto_core/service/test_phase10a.py`.
- **Full suite:** Previously BLOCKED by Blocker 1 above — now UNBLOCKED (Blocker 1 resolved).
- **Next step:** Rerun `pytest -x -q tests/crypto_core` on the Phase 16L branch to confirm full suite green, then commit Phase 16L as an atomic commit.
