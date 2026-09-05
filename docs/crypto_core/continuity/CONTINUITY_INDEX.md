# crypto_core Continuity Index

<!-- CONTROL_PLANE_ROLE: CONTINUITY_INDEX -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> Canonical pointers plus the stable capability and architecture map for `crypto_core`. This is layer
> 2 of `CONTEXT_CONTINUITY_PROTOCOL_V2` (`docs/crypto_core/agent_os_v2.md` section 15). It pins NO
> live state: no current `main` SHA, no current PR number, no open-PR count, no current CI result, no
> current blocker set. Those are layer 3 (ephemeral) and are re-proven every session.
>
> This file defines no routing, task family, effort, PR sizing or merge authority of its own.
> MERGE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md section 2.1.
> PR_SIZING_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md section 2.2.
> TASK_FAMILY_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md section 3.
> EFFORT_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md section 3.2.

## 1. Bootstrap order

`FRESH_CHAT_BOOTSTRAP` (canonical definition: `agent_os_v2.md` section 15.1):

```text
AGENTS.md
  -> docs/crypto_core/agent_os_v2.md
  -> the environment adapter for this host
  -> docs/crypto_core/continuity/CONTINUITY_INDEX.md   (this file)
  -> the current ephemeral STATE_MANIFEST / CURRENT_HANDOFF
  -> fresh GitHub and local state re-proof
  -> continue only from proven state
```

Nothing below this line is a substitute for that re-proof. A pointer tells you WHERE the truth lives;
it never tells you WHAT the truth currently is.

## 2. Canonical pointer map

| Need | Canonical source |
|---|---|
| Routing, task families, effort, authority | `docs/crypto_core/agent_os_v2.md` |
| Durable rails and entrypoint | `AGENTS.md` |
| Claude host adapter | `CLAUDE.md`, `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` |
| Codex host adapter | `.codex/skills/crypto-core-max-safe/SKILL.md` |
| Git/PR/validation/CI/postmerge mechanics | `docs/crypto_core/agent_workflow.md` |
| Per-lane prompt authoring | `docs/crypto_core/model_prompting_guide.md` |
| Heavy-implementation prompt authoring | `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md` |
| Prompt/report compression | `docs/crypto_core/agent_prompts/token_efficiency_v2.md`, `docs/crypto_core/token_efficiency_playbook.md` |
| External/current-fact research | `docs/crypto_core/deep_research_protocol.md` |
| Evidence-backed lessons | `docs/crypto_core/agent_lessons.md` |
| Ephemeral state shape | `docs/crypto_core/continuity/state_manifest.schema.json` |
| Ephemeral state worked example | `docs/crypto_core/continuity/state_manifest.example.json` |
| Product architecture authority | `docs/PRDV4_MULTI_MARKET_CRYPTO.md` |
| Deterministic control-plane gate | `scripts/crypto_core/validate_agent_os_v2.py` |
| Local setup audit | `scripts/crypto_core/audit_agent_setup.ps1` |
| Control-plane contract tests | `tests/crypto_core/test_agent_os_v2_contract.py` |

## 3. Stable capability map

This is the durable shape of the system, not its current progress. Progress is proven from the
repository, never read from here.

```text
StrategySpec
  -> LBR (live backtest replay)
  -> PIT / DataRequirement
  -> DecisionLedger
  -> EvidenceStore
  -> BacktestAdmission
  -> Replay bridge
  -> PaperSleeve
  -> Promotion path
  -> Allocator / risk bridge
  -> ExecutionSim
```

Paper-first: no live, order-routing, scheduler, auto-loop or shadow stage exists in this chain
without separate authorization and design.

Durable architectural invariants:

- Digest-carrying artifacts are re-proven by the consumer through the public serializer before any
  READY/ADMITTED/ACCEPTED transition. A matching identifier is never sufficient.
- Identity is not freshness. Where output evidence must match the current result, the current-result
  digest is what must match — not only the specification digest.
- Every governance threshold is human-owned. No agent sets or relaxes one.
- Every trust transition fails closed with an explicit reason.
- Deterministic and reproducible: canonical JSON, exact decimal arithmetic, no float drift, no hidden
  clock, IO, environment or randomness in product code.

## 4. Frozen and protected areas

- **MT4** is `CLOSED_FROZEN`. It is not reopened, re-planned or re-litigated by continuity work.
- **Readiness, connector and Deribit promotion** surfaces do not transition without separate
  authorization and a protected independent design/audit.
- **Live, private API, credentials, orders, order routing, scheduler, auto-loop, shadow and capital**
  surfaces are out of scope by default.
- **BIST** is historical context and never enters crypto_core.

## 5. What belongs in ephemeral state, not here

Anything in this list that appears in a durable surface is a defect, and the durable-surface scan in
`scripts/crypto_core/validate_agent_os_v2.py` fails on it:

- current `main` head, tree or any commit hash
- current branch, current PR number, PR state, head SHA
- open-PR count
- current CI or CodeQL result
- current review threads and their resolution state
- the current active blocker and the current next slice
- current authorization state
- current model and effort runtime evidence
- current provider capacity readings and the selected capacity routing mode
- the current next safe action — a live decision, proof-paired like any other current fact

These live only in `STATE_MANIFEST_V1` and `CURRENT_HANDOFF_V2`, which are compiled per session from
live proof and are not committed as doctrine.

## 6. Continuity failure modes to check every session

- A handoff head that no longer matches the live head — the handoff is stale; re-prove, do not trust.
- A completed-gate claim whose evidence key (head/tree, path set, command, environment) has changed —
  the gate is invalidated and must run again.
- A prepared future packet being read as authorization to act — it never is
  (`WORK_PREPARED_NOT_AUTHORIZED`).
- A snapshot of the repository taken elsewhere being read as current GitHub state — it never is.
- A missing fact being filled with a plausible value instead of `UNKNOWN`.
- A historical routing record being read as current routing authority.
- A provider capacity reading being carried forward from an earlier session instead of re-proven, or
  guessed instead of recorded as `UNKNOWN`.
- One exhausted provider being treated as a project stop, or an available provider being treated as
  satisfying a gate that required a different one.
- A routing mode chosen while the capacity it depends on is still `UNKNOWN`. An unproven capacity
  leaves the mode null; it never becomes a guessed continuation.
- A runtime-proof block omitted entirely rather than declaring `UNKNOWN`. Absence is not a quieter
  way of saying unproven — it is an unstated claim.
