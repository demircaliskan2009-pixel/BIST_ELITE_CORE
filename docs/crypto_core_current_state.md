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

### Blocker 1 — ServiceOrchestrator missing `_sleeve_candidate_workflow_controller` (P0)

- **File:** `src/crypto_core/service/service_orchestrator.py`
- **Symptom:** `AttributeError: 'ServiceOrchestrator' object has no attribute '_sleeve_candidate_workflow_controller'` in `test_phase10e.py::test_multi_campaign_pipeline`
- **Root cause:** `_sleeve_candidate_workflow_controller` is initialized in a dead-code block that appears after a `return` statement inside `get_sleeve_admission_portfolio_summary`. It is never executed and is therefore never set on the instance. `__init__` does not initialize it.
- **Fix (not yet applied):**
  1. In `ServiceOrchestrator.__init__`, add `self._sleeve_candidate_workflow_controller: SleeveCandidateWorkflowController | None = None` after `self._sleeve_admission_controller = None` (~line 386).
  2. Remove the entire dead-code block at lines 403–418 (unreachable code after the `return` in `get_sleeve_admission_portfolio_summary`).
  3. Confirm the `SleeveCandidateWorkflowController` import already exists in the live (non-dead) section of the file before removing the dead block.
- **Validation:** `python -m pytest -x -q tests/crypto_core/service/test_phase10e.py`
- **Must fix before:** Any commit containing Phase 16L changes.

### Phase 16L Status

- **Status:** Partially attempted (multiple failed Copilot patch attempts reverted); then implemented by Codex (GPT-5.5).
- **Files:** `src/crypto_core/service/promotion_review.py` and `tests/crypto_core/service/test_phase10a.py`.
- **Targeted tests:** Phase 16L tests pass (`test_phase10a.py` + `test_phase10b.py` clean).
- **Full suite:** BLOCKED by ServiceOrchestrator Blocker 1 above.
- **Next step:** Fix Blocker 1 first → rerun `pytest -x -q tests/crypto_core` → if green, commit Phase 16L + Blocker 1 fix together as one atomic commit.
