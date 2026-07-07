# BIST_ELITE_CORE — Claude Instructions

Active scope is `crypto_core` only (`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`,
`docs/crypto_core`). BIST is historical context — never leak it into crypto implementation.

Follow the canonical agent workflow: `docs/crypto_core/agent_workflow.md`
(working loop, model routing, digest-boundary rule, guardrails, validation policy, state-claim
policy, skills policy, report templates). Durable operating rails: `AGENTS.md`.
Prompts may reference **named lanes** (LANE:PRECHECK-STD, GATE-MODULE-STD, LANE:FABLE-ARCH, VALIDATE-STD,
PR-STD, MERGE-STD, REPORT-STD) — expand them from `docs/crypto_core/agent_prompts/token_efficiency_v2.md`;
lanes compress procedure text only, never safety rules.

Model-tier routing (canonical: `docs/crypto_core/agent_workflow.md` §20 + §21 post-Fable): Fable 5
availability is NOT assumed after 2026-07-07 — when absent, §21 governs: Opus 4.8 xhigh = repo-internal
design first-drafts + bounded high-risk implementation/repair; Codex GPT-5.5 extra-high = mandatory
read-only P1/P2 audit after every high-risk design (before implementation) and after every high-risk
implementation (before the connector gate) — increased use; Fast Auto/Sonnet = mechanical
(hygiene/CI/merge/post-verify — never Opus/Codex for these); GitHub connector = mandatory final
merge-readiness gate, never waived; Deep Research = external/current facts only. Attestation-only evidence
is never machine proof. Model strength is never proof — every lane runs under the unchanged hard gates
below.

Key hard rules (full list in the workflow doc):

- Paper-first, deterministic, fail-closed; no live/private API, credentials, real orders,
  order routing, scheduler, connector-readiness, or BIST changes without explicit authorization.
- One open PR; never push `main`; never merge without explicit per-PR user authorization.
- Full test suite only via `scripts/crypto_core/run_full_tests_logged.ps1`; targeted pytest via
  `scripts/crypto_core/run_logged_command.ps1`; commands one at a time; scoped `git add` only.
- Digest-boundary rule: consumers of digest-carrying objects recompute the upstream digest via the
  public serializer and reject mismatch before READY/ADMITTED/ACCEPTED.
- Never claim repo/PR/CI state from memory — prove with fresh `git`/`gh` output or mark UNKNOWN.

Claude operating contract (post-Fable, canonical detail in `agent_workflow.md` §21):

- Never self-approve (`gh pr review --approve`), never expand an open PR beyond its named scope;
  review-blocker repair happens on the same branch only.
- Consume Codex findings surgically: fix only real in-scope findings, add regression proof, rerun
  validation, push, re-prove checks; resolve only proven-fixed automated threads, never human ones.
- Prepare the connector final gate with a head-pinned state proof (PR state, head SHA, files,
  checks, threads); pending/queued/in-progress/no-checks = NOT_READY.
- Stop with proof when scope would widen, validation fails out of scope, an external/current fact
  is needed (DEEP_RESEARCH_REQUIRED), or a merge/authorization gate is reached.
- Anti-waste: never an expensive lane for CI polling/status/merge mechanics; named files first;
  failure tails only, no full log dumps. Reports carry at minimum RESULT / FILES_CHANGED /
  VALIDATION / NEXT_SAFE_ACTION.
- Archived Fable design contracts live in `docs/crypto_core/fable_exit_contract_index.md` — design
  doctrine only, never current-state proof.
