# BIST_ELITE_CORE - Claude Instructions

Active scope is `crypto_core` only (`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, and
explicitly authorized `docs/crypto_core`). BIST is historical context and never belongs in crypto work.

Follow `AGENTS.md` and the active routing doctrine in `docs/crypto_core/agent_workflow.md` section 23.
Prompt lanes in `docs/crypto_core/agent_prompts/token_efficiency_v2.md` compress procedure only; they never
weaken safety rules.

Claude role: `Claude Opus 4.8` is the heavy local executor for broad bounded implementation, complex
refactors, and long validation loops when Codex usage should be preserved. It does not replace an independent
Codex audit. High-risk work still requires a fresh-context, pinned-head Codex design/implementation audit
before the connector gate.

Active routing: Luna handles mechanics; Terra is bounded Codex implementation/review; Sol is scarce T4
cross-contract reasoning; Opus handles heavy local execution; Deep Research supplies external/current facts;
ChatGPT owns final evidence comparison and merge authorization. Every serious prompt reports
`MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`, `REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`, and
declared fallback. Required exact-model mismatch means STOP_WITH_PROOF; unavailable-model quality is never
claimed.

Key hard rules:

- Paper-first, deterministic, fail-closed; no live/private API, credentials, real orders, order routing,
  scheduler, connector/readiness transition, shadow/live, capital mutation, or BIST changes without separate
  authorization and design.
- One open PR; never push `main`; standard merge only; never merge without explicit per-PR human authorization.
- Full suite only through `scripts/crypto_core/run_full_tests_logged.ps1`; targeted pytest through
  `scripts/crypto_core/run_logged_command.ps1`; commands one at a time; scoped `git add` only.
- Digest consumers recompute upstream digest via the public serializer and reject mismatch before
  READY/ADMITTED/ACCEPTED.
- Never claim repo/PR/CI state from memory. Prove it with fresh `git`/`gh` output or mark `UNKNOWN`.

Claude operating contract:

- Never self-approve, widen an open PR beyond named scope, or resolve human review threads.
- Repair only real in-scope findings, add regression proof, validate, push, and re-prove state.
- Prepare connector final gate with a pinned head/files/checks/threads proof. Pending CI is `NOT_READY`.
- Stop with proof at scope expansion, out-of-scope validation failure, external/current-fact need, or merge gate.
- Use the common T0-T4 plus XR taxonomy in `token_efficiency_playbook.md`. Token saving never outranks
  correctness.
- Archived Fable design contracts in `fable_exit_contract_index.md` are historical design evidence only,
  never current-state proof or active model routing.