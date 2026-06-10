# BIST_ELITE_CORE — Claude Instructions

Active scope is `crypto_core` only (`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`,
`docs/crypto_core`). BIST is historical context — never leak it into crypto implementation.

Follow the canonical agent workflow: `docs/crypto_core/agent_workflow.md`
(working loop, model routing, digest-boundary rule, guardrails, validation policy, state-claim
policy, skills policy, report templates). Durable operating rails: `AGENTS.md`.

Key hard rules (full list in the workflow doc):

- Paper-first, deterministic, fail-closed; no live/private API, credentials, real orders,
  order routing, scheduler, connector-readiness, or BIST changes without explicit authorization.
- One open PR; never push `main`; never merge without explicit per-PR user authorization.
- Full test suite only via `scripts/crypto_core/run_full_tests_logged.ps1`; targeted pytest via
  `scripts/crypto_core/run_logged_command.ps1`; commands one at a time; scoped `git add` only.
- Digest-boundary rule: consumers of digest-carrying objects recompute the upstream digest via the
  public serializer and reject mismatch before READY/ADMITTED/ACCEPTED.
- Never claim repo/PR/CI state from memory — prove with fresh `git`/`gh` output or mark UNKNOWN.
