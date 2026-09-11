# Crypto Core Current State — Durable Pointer

<!-- CONTROL_PLANE_ROLE: DURABLE_STATE_POINTER -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **This file deliberately contains no current state.** It is a durable POINTER to where current state
> actually lives. It defines no routing, task family, effort, PR sizing or merge authority; those live
> in `docs/crypto_core/agent_os_v2.md`.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.

## Why this file holds no state

A committed file cannot stay current. Every previous version of this note pinned a head, a blocker
and a phase status that were true on the day they were written and misleading afterwards — and a
stale pin read as current is exactly the failure this control plane exists to prevent. So the pins
are gone, and the durable-surface scan in `scripts/crypto_core/validate_agent_os_v2.py` now fails the
build if a commit hash, a PR number or an open-PR count reappears in the active region of this file.

## Where current state lives

| Question | Where the answer actually is |
|---|---|
| Current `main` head and tree | `git rev-parse origin/main`, `git rev-parse origin/main^{tree}` |
| Current branch, head, clean tree | `git status --short --branch`, `git rev-parse HEAD` |
| Open PR count and identity | `gh pr list --state open` |
| PR state, mergeability, head oid | `gh pr view <n> --json state,mergeable,mergeStateStatus,headRefOid` |
| CI and security-scan results | `gh pr checks <n>`, `gh run list`, the commit check-runs |
| Review threads and resolution | the PR review-threads GraphQL query |
| Current blocker set and next slice | the ephemeral state manifest and the current handoff |
| Completed-gate reuse validity | the gate's evidence key in the ephemeral state manifest |

Compile the ephemeral manifest from `docs/crypto_core/continuity/state_manifest.schema.json`. A value
that cannot be proven is `UNKNOWN` — never a plausible guess. A worked instance is in
`docs/crypto_core/continuity/state_manifest.example.json`, which is an illustrative fixture and not
state.

## Durable orientation

- Active implementation scope is `src/crypto_core/**`, `tests/crypto_core/**`,
  `scripts/crypto_core/**` and explicitly authorized `docs/crypto_core/**`.
- Legacy BIST code is out of scope unless the user explicitly requests it.
- All phases remain paper-only unless explicitly instructed otherwise.
- The durable capability map — the chain from strategy specification through admission to the paper
  sleeve and beyond — is in `docs/crypto_core/continuity/CONTINUITY_INDEX.md`. Progress along that
  chain is proven from the repository, never read from a document.
- The product architecture authority is `docs/PRDV4_MULTI_MARKET_CRYPTO.md`. This note is not a PRD
  and does not replace it.

## Operating reminder

Preserve deterministic replay, fail-closed behavior, explicit auditability, scoped git hygiene and
evidence-before-promotion. Do not add fake data, live-trading enablement, credentials, or provider and
network expansion unless the task explicitly asks for it.

<!-- HISTORICAL_RECORD_BEGIN -->

## Historical note

Earlier revisions of this file carried a "Verified Surfaces Present" inventory and a "Known Blockers"
section pinning a specific resolved blocker commit and a dated phase status. Both were point-in-time
records. They were removed rather than updated, because a committed inventory of what exists is
re-derivable from the tree at any moment and a committed blocker list goes stale silently. The
surfaces that note listed — pipeline and service orchestration, campaign, review and readiness flows,
external-regime governance, decision-pack and escalation workflow, sleeve portfolio state,
qualification and recommendation, campaign evidence, decision pack, candidate workflow, and promotion
review and admission — are all still discoverable directly under `src/crypto_core/`.

<!-- HISTORICAL_RECORD_END -->
