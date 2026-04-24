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
