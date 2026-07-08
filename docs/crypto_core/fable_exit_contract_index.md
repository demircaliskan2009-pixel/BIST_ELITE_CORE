# Fable 5 Exit Contract Index (recorded 2026-07-07, consolidated 2026-07-08)

Durable index of every design contract Fable 5 (`claude-fable-5`) locked on its exit day.
These are **archived design contracts — never repo current-state proof**. Rules of use:

- **Do not implement from this file without fresh current repo proof (`git`/`gh`) and a scoped PR.**
- Contracts define invariants and artifact shapes; they do not prove that anything is built, merged,
  ready, or complete. Repo/PR/CI state is proven only per `agent_workflow.md` §11 (state-claim policy).
- All hard gates bind unchanged: paper-only, fail-closed, deterministic, digest-bound, one open PR,
  Codex audit for high-risk work, GitHub-connector final gate (never waived), explicit per-PR user
  merge authorization (`agent_workflow.md` §21).
- Numeric thresholds marked GOVERNANCE_REQUIRED are decided by the controller/user — never invented
  by any model.

## 1. Non-overclaim doctrine (binding for every contract below)

`agent_workflow.md` §21.5 binds: attestation-only evidence is never machine proof; injected
deterministic time is never wall-clock proof; `prdv4_stage4_complete`, machine-time/timestamp-origin,
live/shadow/Deribit/readiness, real orders/capital, profitability/edge flags stay structurally False
in every artifact until the exact gate designed to prove them does so, under its own authorization.

## 2. Contract families

| Family | Purpose | Artifact/PR family | Key invariants | DR needed |
|---|---|---|---|---|
| **Stage4 v2** (Path A) | Conservative completion decision v2; narrows v1's 4 blockers to 3; stays BLOCKED | `paper_stage4_completion_decision_v2.py` — next technical PR | 8 anchored inputs (v1's 6 + attested 30-day gate #319 + predecessor v1 with chain-continuity via v1's `verified_*` digests); UTC day-index alignment `*_bucket_*_ns // 86_400_000_000_000` vs `selected_utc_day_indices` with %DAY re-pin before division; `prdv4_stage4_complete=False` structural | No |
| **MT** (machine-time provenance) | Replace operator attestation with machine-proven time (sandwich model) | MT-1 design doc; MT-2..6 slices | Not-before = external beacon value sealed into attested-day metadata; not-after = signed timestamp committing to the day self-digest; quorum >= 2 independent source classes on both roles; spacing forces ~30 real elapsed days; only the proven-day artifact may ever set `machine_time_origin_proven=True`; MT-2 abstract policy is pre-DR-safe, MT-3 concrete registry is post-DR | Yes (beacon/TSA/roughtime/exchange-time facts) |
| **SM** (secondary metrics) | Enforce hit/fill/slippage instead of `declared_not_enforced_review_only` | SM-1 design doc; SM-2..6 slices | Builds on existing `PaperEndToEndEpisode` / `PaperFillSimulationResult` / `fill_pricer` / `PaperRealizedPnlEvent`; sequence SecondaryMetricsPolicy → TradeRecordEvidence (episodes + rejected fills + ledger reconciliation) → SecondaryMetricsEvidence (Decimal) → methodology v2 (`enforced=True`, NEW module) → comparison evidence v2 (real `paper_*` into `compare_stage4`; None → REJECTED). Today #316 passes `paper_*` as None placeholders (`paper_stage4_comparison_evidence.py:1173-1176`). Policy carries the expected-fill model reference (no separate evidence artifact) | No |
| **EF** (edge factory) | 7-gate idea→spec→admission→kill pipeline for new edges | EF-1 design doc; EF-2..8 slices (`edge_` module namespace) | `status` (trust) vs `gate_verdict` (outcome) separation; dual anchor = root intake digest + predecessor digest; `NEEDS_*` never advances; kill-criteria lifecycle draft→superset→seal→immutable; preregistered search bounds (multiple-testing ledger); gate 6 re-proves the full back-chain; gate 7 lifecycle state machine (DISABLED >30d → QUARANTINE >=14d → revalidation; no auto-reactivation) | No |
| **RG** (multi-sleeve risk governance) | Portfolio-level paper risk envelope + allocator governance over isolated sleeves | RG-1 design doc; RG-2..8 slices | 7 artifacts: portfolio risk envelope → sleeve performance/drawdown → correlation (unknown correlation = worst-case 1, fail-closed) → promotion/demotion ladder → allocator (envelope exceeded = REJECTED, no silent scaling; kill-override BEFORE arithmetic) → `paper_portfolio_governance_decision`; existing `paper_sleeve_risk_budget_decision` reused as intra-sleeve layer; `audit/portfolio_governor_*` readiness surfaces stay out of scope | No |
| **RF** (regime/vol filter) | Deterministic PIT-grade regime labels as evidence (regime filter is NOT an edge) | RF-1 design doc; RF-2..7 slices (`validation/regime_*` namespace) | RegimeFeaturePolicy (preregistration core) → FeatureSeriesEvidence (builder recomputes values from raw-input digests) → LabelEvidence (per-UTC-day, prior-day-close discipline, UNLABELED fail-closed + cap) → StabilityEvidence (dual-as-of label recompute equality = structural repaint proof) → FilterAdmissionDecision (policy digest must be a member of the EF-5 preregistration ledger — post-performance filter creation structurally impossible) → ConditionedPerformanceEvidence (feeds EF gate-6 `regime_split` + RG correlation stratification via a digest-bound pending pattern). `regime/tracker.py` (stateful/float/wall-clock) is runtime reference only — never imported by the evidence chain | Only F5/F6 feature classes (packet-conditional) |
| **Funding pilot** (funding/basis/carry) | First edge-family pilot through the EF pipeline | Pilot slices after EF/RG/RF substrate | Repo already has `FundingRateEdge` + PIT-grade `FUNDING_RATE` DataRequirement (`funding_published_ns`/`funding_finalized_ns`, `predicted`/`final`); candidate order S1 passive carry → S4 vol-gated → S3 continuation → S2 basis mean-reversion → S5 two-leg (S5 blocked until SM enforced); features consume `final` funding semantics only | Yes (11-question venue-mechanics set, PRM-16) |

Companion doctrine locked the same day: post-Fable operating model (`agent_workflow.md` §21), CTO
council pack (agent council protocol: Opus draft + Codex counter + internal-council synthesis for
T4 decisions; paste-ready Claude/Codex setup packs; gap register).

**Full design documents (Fable-authored 2026-07-08; supersede the one-line rows above as the
detailed source):** `paper_stage4_completion_decision_v2_design.md` (v2 — the Codex design-audit
input), `secondary_metrics_enforcement_design.md` (SM), `machine_time_provenance_design.md` (MT),
`edge_factory_design.md` (EF), `multi_sleeve_risk_governance_design.md` (RG),
`regime_volatility_filter_design.md` (RF), `governance_decision_framework.md` (every
GOVERNANCE_REQUIRED constant with trade-offs; numbers stay human-owned),
`stage4_completion_v3_skeleton.md` (v3 invariant skeleton — MT/SM-independent). All DESIGN ONLY:
same usage rules as this index (fresh repo proof + scoped PR before any implementation).

## 3. Canonical execution queue

Roadmap order — NOT current implementation state; every step needs its own authorization and fresh
state proof:

1. PR #320 merge (docs/setup) → 2. `PaperStage4CompletionDecisionV2` (Path A) → 3. docs-sync →
4. completion review dossier → 5. design-doc chores `[SM-1, MT-1, EF-1, RG-1, RF-1]` →
6. combined Deep Research round `[PRM-07 + PRM-16]` → 7. governance threshold approvals →
8. SM-2..6 → 9. EF-2..8 → 10. RG-2..8 → 11. RF-2..7 → 12. MT-2..6 → 13. funding pilot slices →
14. completion decision v3 — the ONLY artifact that may ever set `prdv4_stage4_complete=True`, and
only with machine-proven 30-day gate + enforced secondary metrics + 3-step council review + explicit
human authorization.

## 4. Prompt index (PRM-01..32)

Owner lanes: Opus = Opus 4.8 xhigh implementation/design draft; Codex = read-only P1/P2 audit;
Sonnet = mechanical; DR = Deep Research (advisory only); Connector = final gate.

- **PRM-01..15 — post-#320 execution-loop pack (CTO council pack).** Proven anchors: PRM-01 Opus
  v2-completion implementation; PRM-03 Codex audit of PR #320; PRM-04 Connector final gate for
  PR #320; PRM-05 Sonnet standard head-pinned merge + post-verify; PRM-07 Deep Research round
  (runs combined with PRM-16). Remaining slots cover the loop chores (docs-sync, dossier,
  SM-1/MT-1 design-doc prompts, repair/closeout variants) — exact texts are preserved in the
  controller's archived Fable session reports (2026-07-07); re-issue from there and do not renumber.
- **PRM-16..22 — funding/basis/carry pilot pack.** PRM-16 = the 11-question venue-mechanics Deep
  Research set (may run while a PR is open — not a repo action); PRM-17..22 = pilot design/impl/audit
  prompts per candidate slice (texts in the archived pilot report).
- **PRM-23 — Codex edge-factory audit** (EF gate contracts: trust/outcome separation, dual anchor,
  kill lifecycle, preregistration ledger).
- **PRM-24..27 — multi-sleeve risk governance pack** (RG design/impl/audit prompts; worst-case
  correlation, envelope-rejection, kill-override ordering focus).
- **PRM-28..32 — regime/vol filter pack.** PRM-28 Opus RF design doc; PRM-29 Opus RF artifact
  implementation; PRM-30 Codex lookahead/repaint audit (prior-day-close boundary arithmetic,
  delayed-feature backfill, UNLABELED-cap bypass, predicted-funding leakage); PRM-31 Codex overfit
  audit (preregistration membership, label-set growth, parameter-bound escape); PRM-32 Codex
  allocator-interaction audit (pending-vs-available regime_split consumption, day-index joins).

## 5. Governance-required decisions (controller/user owns the numbers)

- SM: hit-rate floor, fill-rate floor, slippage ceiling numeric values.
- MT: accepted source classes, quorum composition, spacing parameters (post-DR).
- EF: kill-criteria thresholds; preregistered search-bound sets; gate minimums.
- RG: envelope budgets, correlation caps, ladder promotion/demotion thresholds.
- RF: label set members, feature windows, min-observation counts, UNLABELED cap, drift cap.
- Pilot: S1..S5 candidate parameters and go/no-go per slice.

## 6. Deep Research obligations (advisory-only, §19 binds)

- Combined round `[PRM-07 + PRM-16]`: funding/basis/carry venue mechanics (11 questions) + MT-3
  machine-time source facts (beacon / RFC 3161 TSA / roughtime / exchange-time behavior).
- Packet-conditional: RF F5 (depth/spread proxy) and F6 (liquidation events) data availability.
- DR never mutates repo/GitHub state, never waives a gate, never proves repo state.

## 7. Codex audit obligations (read-only; before the connector gate on high-risk PRs)

- PR #320 (PRM-03), then every family design doc BEFORE implementation and every high-risk
  implementation BEFORE the connector gate (§21.3).
- Standing rubrics: digest/reseal/provenance; AST forbidden-surface; overclaim (completion/
  readiness/live/machine-time/capital/profitability/edge); prompt/workflow consistency; P1/P2/P3
  taxonomy per `.codex/skills/crypto-core-max-safe/SKILL.md`.

## 8. Stop conditions (any lane, any family)

STOP_WITH_PROOF when: repo/PR/CI state cannot be proven fresh; scope would exceed named files;
a source/test edit is needed inside a docs task (or vice versa); validation fails and the fix is
out of scope; an external/current fact is required (route to DR); a governance number is missing
(route to controller); a claim would overreach §1; merge/authorization gates are reached.
