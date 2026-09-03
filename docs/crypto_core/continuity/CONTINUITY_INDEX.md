# crypto_core Continuity Index (durable)

`CONTEXT_CONTINUITY_PROTOCOL_V1` durable surface for `CRYPTO_CORE_AGENT_OS_V2`. This file exists so a new
chat can reach working competence without a giant pasted transcript.

**Durability rule.** Everything here is stable across tasks. This file MUST NOT contain volatile values:
current SHA, current branch, current PR number, current CI run, current reviews, current thread state, a
current temporary blocker run, temporary quota or model availability, a mutable readiness result, or a
mutable connector transition. Volatile state is proven fresh from `git` / `gh` / the GitHub connector at
the start of every task and lives only in an ephemeral `STATE_MANIFEST_V1` and `CURRENT_HANDOFF_V2`.

## 1. Canonical authority pointers

Precedence (`AGENT_OS_V2_PRECEDENCE`):

1. `AGENTS.md`
2. `docs/crypto_core/agent_os_v2.md` — `CRYPTO_CORE_AGENT_OS_V2`, the canonical control plane
3. Environment adapter — `.codex/skills/crypto-core-max-safe/SKILL.md` (Codex) or `CLAUDE.md` +
   `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` (Claude)
4. `docs/crypto_core/agent_lessons.md`

Companions: `docs/crypto_core/agent_workflow.md` (workflow companion; never an independent routing
authority), `docs/crypto_core/model_prompting_guide.md`,
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`,
`docs/crypto_core/agent_prompts/token_efficiency_v2.md`,
`docs/crypto_core/token_efficiency_playbook.md`, `docs/crypto_core/deep_research_protocol.md`.
Architecture authority: `docs/PRDV4_MULTI_MARKET_CRYPTO.md`.

## 2. Project scope

Active implementation scope is `src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, and
explicitly authorized `docs/crypto_core`. BIST is historical context only and never enters crypto_core
implementation. The target system is an institutional crypto trading operating system: paper-first,
deterministic, event-driven, point-in-time, fail-closed, audit-first, derivatives-first, multi-sleeve,
governance-first and risk-bounded.

Permanent non-goals without separate authorization and design: live or private API, credentials, real
orders, order routing, scheduler, auto-loop, shadow or live execution, capital mutation, readiness or
connector transitions, and any BIST mutation.

## 3. Stable architecture map

Edge-to-money pipeline, in dependency order:

`StrategySpec` → `LBR` (live backtest replay) → `PIT` / `DataRequirement` → `DecisionLedger` →
`EvidenceStore` → `BacktestAdmission` → replay bridge → paper sleeve → promotion path → allocator-risk
bridge → governor integration.

Cross-cutting stable layers: canonical JSON serialization and SHA-256 digests; digest-bound evidence
artifacts; fail-closed validation at trust boundaries; governance thresholds owned by humans; provenance
and replay guarantees; venue and derivatives abstraction (funding, basis, carry, mark/index spread).

## 4. Stable implemented-capability categories

These are durable capability categories, not a current-state dashboard. Prove the exact current contents
of any category from the repository before relying on it.

- Deterministic canonical serialization and digest recomputation helpers.
- Digest-bound evidence artifacts across the paper evidence chain.
- Paper session, paper PnL and paper return-series evidence surfaces.
- Paper methodology, Sharpe, edge-identity and Stage-4 baseline evidence surfaces (review-only).
- Deribit public market-data harness and provenance origin gating (paper-only, no private API).
- Machine-time qualification and trusted-attestation evidence surfaces under governed workflows.
- Service orchestration, sleeve qualification, campaign, promotion-review and admission flows.
- Repo-native validation tooling under `scripts/crypto_core`.

## 5. Stable design and frontier categories

Durable categories of remaining work. The specific next slice is a controller decision proven from live
state, never pinned here.

- Secondary comparison metrics enforcement (hit rate, fill, slippage) beyond declared-not-enforced.
- Stage-4 paper-versus-backtest comparison evidence and the Stage-4 completion decision.
- Operational-day evidence and an operational multi-day gate distinct from the return-series gate.
- Allocator-risk bridge and governor integration.
- Readiness, connector and promotion gates — each protected, each separately authorized.

## 6. Stable invariant IDs

`V2-I01` … `V2-I22` are defined in `docs/crypto_core/agent_os_v2.md` section 1 and are the durable
governance invariants (crypto_core only, one repository writer, one open PR, no direct main push, no force
push, standard merge only, explicit human merge authorization, mandatory independent Class-C Codex audit,
self-review is never independent, pending CI is `NOT_READY`, current valid P1/P2 blocks merge, mutable
state is never durable doctrine, no scheduler, no hidden auto-loop, no self-approval, no inferred
readiness or capital authority).

Protocol identifiers: `PR_CLOSURE_CONTRACT_V1`, `BLOCKER_ESCAPE_PROTOCOL_V1`,
`CONTEXT_CONTINUITY_PROTOCOL_V1`, `PROMPT_COMPILER_V2`, `DAILY_BATCH_MANIFEST_V1`, `STATE_MANIFEST_V1`,
`CURRENT_HANDOFF_V2`, `AGENT_OS_HANDOFF_V1`.

## 7. Historical and retired-surface classification

- `CRYPTO_CORE_AGENT_OS_V1` (`agent_workflow.md` section 24) — superseded by `CRYPTO_CORE_AGENT_OS_V2`
  for authority and routing; retained as workflow companion and history.
- `agent_workflow.md` sections 20-23 — HISTORICAL / SUPERSEDED routing eras. Never active.
- Claude Fable 5 — `INACTIVE_EXPIRED_RETIRED`. Not a lane, fallback or dependency.
  `docs/crypto_core/fable_exit_contract_index.md` is archival only.
- Claude Opus 4.8 — `SUPERSEDED_BY_OPUS_5`. Dated execution records are historical evidence only.
- Copilot — `INACTIVE_UNAVAILABLE`. `.github/copilot-instructions.md` is a thin compatibility shim only.
- Retired legacy control-plane surfaces (removed, must not be reintroduced): `.github/instructions/**`,
  `.github/agents/crypto-core-engineer.agent.md`, `.github/agents/crypto-product-auditor.agent.md`,
  `.github/agents/crypto-throughput-commander.agent.md`, `.github/prompts/crypto-*.prompt.md`,
  `.github/skills/crypto-*`, `.github/skills/_shared/references/contract-schema.md`, `.github/hooks/**`,
  `docs/crypto_core/COPILOT_HIGH_THROUGHPUT_OPERATING_PROTOCOL.md`,
  `docs/crypto_core/COPILOT_CUSTOM_AGENT_CRYPTO_THROUGHPUT_COMMANDER.md`,
  `docs/crypto_core/CLAUDE_COLLABORATION_AND_PROJECT_GUIDE.md`.
- Blueprint sizing wording such as "each artifact is one PR" is `NON_AUTHORITATIVE_SIZING_HISTORY`.

## 8. Bootstrap procedure for a new chat

```text
MODE=READ_ONLY.
Load AGENTS.md, docs/crypto_core/agent_os_v2.md,
and docs/crypto_core/continuity/CONTINUITY_INDEX.md.
Re-prove repo/branch/base/head/tree/divergence/worktree/open PRs.
Never trust cached volatile state.
Classify TASK_INTENT and risk.
Compile STATE_MANIFEST_V1.
Route exactly one lane.
Return STATE_PIN, P1/P2/P3, and exactly one NEXT_SAFE_ACTION.
```

Local proof commands (read-only): `git status --short`, `git rev-parse HEAD`,
`git rev-parse HEAD^{tree}`, `git fetch origin`, `git rev-parse origin/main`, `git branch --show-current`,
`gh pr list --state open`. Full-suite proof runs only through
`scripts/crypto_core/run_full_tests_logged.ps1`; targeted commands run through
`scripts/crypto_core/run_logged_command.ps1`.

## 9. Ephemeral packet location and format

`STATE_MANIFEST_V1` is an ephemeral, task-scoped JSON packet. Its schema is
`docs/crypto_core/continuity/state_manifest.schema.json` and an illustration is
`docs/crypto_core/continuity/state_manifest.example.json` (`EXAMPLE_ONLY`). Generated manifests live
outside the repository — in the session scratch directory or in the controller handoff — and are never
committed as durable doctrine.

`CURRENT_HANDOFF_V2` is the ephemeral model-boundary report: what was done, exact current state proof,
files, tests, CI, audit, blockers, authority used, and exactly one next safe action. It travels between
lanes and is never a durable live-state dashboard.
