# crypto_core — Durable Scope and Capability Pointer

This file is a **durable pointer**, not a live-state dashboard. It pins no current SHA, branch, PR, CI
result, review state, blocker run, or readiness/connector transition. Under `LIVE_STATE_POLICY`
(`docs/crypto_core/agent_workflow.md` section 24.11) all volatile state is re-proven from `git` / `gh` /
the GitHub connector at the start of every task.

It is not a PRD and does not replace `docs/PRDV4_MULTI_MARKET_CRYPTO.md`.

## Control plane

Active authority is `CRYPTO_CORE_AGENT_OS_V2` in `docs/crypto_core/agent_os_v2.md`. Precedence
(`AGENT_OS_V2_PRECEDENCE`): `AGENTS.md` → `docs/crypto_core/agent_os_v2.md` → the environment adapter
(`.codex/skills/crypto-core-max-safe/SKILL.md`, or `CLAUDE.md` +
`.claude/skills/crypto-core-token-efficient-loop/SKILL.md`) → `docs/crypto_core/agent_lessons.md`.
`docs/crypto_core/agent_workflow.md` is the workflow companion and never forks routing truth.

## Continuity

Durable continuity for a new session is `docs/crypto_core/continuity/CONTINUITY_INDEX.md`
(`CONTEXT_CONTINUITY_PROTOCOL_V1`): authority pointers, scope, stable architecture and capability maps,
stable design/frontier categories, invariant IDs, retired-surface classification, and the read-only
bootstrap procedure. Ephemeral task state is a `STATE_MANIFEST_V1`
(`docs/crypto_core/continuity/state_manifest.schema.json`) plus a `CURRENT_HANDOFF_V2` packet — compiled
per task, never committed as durable doctrine.

## Stable project boundary

- Active implementation scope: `src/crypto_core/**`, `tests/crypto_core/**`, `scripts/crypto_core/**`,
  and explicitly authorized `docs/crypto_core/**`.
- Legacy BIST code is historical context only and is never implemented here.
- All work is paper-only. No live or private API, credentials, real orders, order routing, scheduler,
  auto-loop, shadow or live execution, capital mutation, or readiness/connector transition occurs without
  separate authorization and design.
- Preserve deterministic replay, fail-closed behavior, explicit auditability, digest and provenance
  boundaries, scoped git hygiene, and evidence-before-promotion. Never add fabricated data.

## Durable capability categories

Durable historical/capability state, **not** mutable current state. Prove the exact current contents of
any category from the repository before relying on it.

- Deterministic canonical serialization and digest recomputation surfaces.
- Digest-bound paper evidence chain: session, PnL, daily return series, methodology, Sharpe, edge identity
  and Stage-4 baseline evidence (review-only, non-overclaiming).
- Pipeline and service orchestration; campaign, review and readiness flows; external-regime governance;
  decision-pack and escalation workflow.
- Crypto sleeve portfolio state; sleeve qualification, recommendation, campaign evidence, decision pack,
  candidate workflow, promotion review and admission flow.
- Deribit public market-data harness with provenance origin gating — public data only, no private API.
- MT4 machine-time work closed under governed qualification and trusted-attestation workflows. This is a
  durable historical/capability statement, not a claim about current CI, current readiness, or any current
  branch.

## Re-prove before acting

```text
git status --short
git rev-parse HEAD
git rev-parse HEAD^{tree}
git fetch origin
git rev-parse origin/main
gh pr list --state open
```

Full-suite proof runs only through `scripts/crypto_core/run_full_tests_logged.ps1`; targeted commands run
through `scripts/crypto_core/run_logged_command.ps1`. Control-plane changes must keep
`python scripts/crypto_core/validate_agent_os_v2.py` at exit 0.

## Non-claims

Nothing in this file proves repository, PR or CI state; grants merge, readiness, connector, live or
capital authority; or satisfies an independent audit.
