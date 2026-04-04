# CURSOR RULES — PRDV3 FINAL

Follow `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md` as the architecture constitution.

## MUST
- BIST-only.
- Keep PRDV2 invariants: deterministic core, fail-closed, audit-first, test-sealed.
- Use hybrid swing-dominant logic.
- Support manual, semi-auto, and full-auto modes.
- Produce explainable decisions.
- Preserve state across cycles.
- Enforce risk limits.
- Validate before promotion.
- Allow AI agents only as optional, modular assistants.
- Keep the live core deterministic; no black-box core control.
- Use dynamic risk bands: 0.5%, 1.0%, 1.5%, 2.0%.
- Respect BIST structure, session rules, liquidity, tavan/taban, corporate actions.
- Log everything important.

## MUST NOT
- Use hidden defaults for missing critical data.
- Break execution or risk contracts.
- Add random behavior to core trading decisions.
- Trade purely to create activity.
- Bypass portfolio constraints.
- Let AI agents directly bypass the execution/risk stack.
- Convert the bot into a non-auditable black box.
- Add non-BIST assets to the core.
- Ignore validation gates.

## DEFAULT PRODUCT BEHAVIOR
- Profit-first.
- Capital-preserving.
- Regime-aware.
- Explainable.
- Adaptive.
- AI-agent-ready.
- Manual + semi-auto + full-auto compatible.
