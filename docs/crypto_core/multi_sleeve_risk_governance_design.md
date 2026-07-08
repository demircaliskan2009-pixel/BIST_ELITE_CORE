# Multi-Sleeve Risk Governance (RG) — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. Purpose: portfolio-level paper risk envelope + allocator governance over
isolated sleeves. Extends (never replaces) the merged intra-sleeve layer
`paper_sleeve_risk_budget_decision.py` ("reservation never execution permission",
`total_reserved <= total_budget`). The existing `audit/portfolio_governor_*` readiness surfaces
stay OUT of scope. Everything is paper-only; allocation is evidence output, never an order.

## 1. Artifact sequence (RG-2..RG-8)

1. **RG-2 `paper_portfolio_risk_envelope.py`**: the portfolio constitution — total paper budget,
   per-sleeve caps, per-market caps, max sleeve count, correlation cap structure, drawdown ladder
   structure. Policy-only; numeric values GOVERNANCE_REQUIRED; digest is the anchor every later
   artifact re-pins.
2. **RG-3 `paper_sleeve_performance_evidence.py`**: per-sleeve deterministic performance snapshot
   (consumes merged return-series/Sharpe substrate per sleeve; day-index aligned).
3. **RG-4 `paper_sleeve_drawdown_evidence.py`**: per-sleeve + portfolio rolling peak-distance
   (Decimal), against the envelope's ladder structure.
4. **RG-5 `paper_sleeve_correlation_evidence.py`**: pairwise sleeve return correlations over
   aligned UTC-day indices. FAIL-CLOSED RULE: insufficient overlap or missing data → correlation
   is treated as WORST-CASE 1.0 for budget math (never 0, never skipped). Regime-stratified
   correlation is a pending field until the RF chain merges.
5. **RG-6 `paper_sleeve_promotion_demotion_decision.py`**: ladder transitions
   (PROBATION → STANDARD → EXPANDED, and demotions) from RG-3/4/5 evidence against envelope
   thresholds; single-stratum-concentrated returns (via RF conditioned performance, when
   available) is a valid demotion reason.
6. **RG-7 `paper_portfolio_allocation_decision.py`**: the allocator — inputs: envelope + per-sleeve
   evidence + EF-7 admissions + kill states. ORDER OF OPERATIONS IS THE P1 INVARIANT:
   (a) kill/quarantine override FIRST (killed sleeve → allocation 0 BEFORE any arithmetic);
   (b) worst-case correlation applied to combined exposure; (c) envelope check — ANY breach →
   `ALLOCATION_REJECTED` for the whole proposal (NO silent scaling, no partial fits);
   (d) only then per-sleeve arithmetic. Output is digest-bound allocation EVIDENCE.
7. **RG-8 `paper_portfolio_governance_decision.py`**: the terminal governance record — binds
   envelope + all evidence + allocation into one decision; portfolio-stop conditions evaluated
   from envelope rules only (advisory regime-drift warnings never trigger stops by themselves).

## 2. Cross-cutting invariants

- Sleeve isolation is preserved: RG reads sleeve evidence, never reaches into sleeve internals.
- Unknown = worst case, everywhere (correlation 1.0, missing evidence → REJECTED, stale digest →
  REJECTED). A sleeve that cannot prove its state gets NOTHING allocated.
- No silent scaling: an allocator that quietly shrinks requests hides envelope pressure; breach
  must be loud (`ALLOCATION_REJECTED` + exact breach reasons).
- Non-overclaim: allocation evidence is paper governance output — never an order, never capital,
  never readiness. All execution/live/capital flags structurally False.

## 3. GOVERNANCE_REQUIRED

Total budget; per-sleeve/per-market caps; correlation cap; ladder thresholds (promotion/demotion
levels, probation windows); portfolio-stop levels. See `governance_decision_framework.md`.

## 4. Test-matrix skeleton

Happy allocation; kill-override-before-arithmetic proof (killed sleeve with huge "performance"
gets 0 and arithmetic never sees it); worst-case-correlation on missing overlap; envelope breach
→ whole-proposal rejection (no partial fit); ladder transition matrix; digest tamper per input;
pending-RF fields correctness; structural-False AST.

## 5. Dependencies

RG-2 can merge early (structure + rejection of unapproved values). RG-3/4 need only merged
substrate. RG-5 full value arrives with RF labels (pending pattern until then). RG-6/7/8 need
governance numbers. EF-7 admissions are allocator inputs — EF chain should land first.

## 6. Stop conditions

Any temptation to scale silently; any allocation to an unproven/killed sleeve; any envelope number
invented by a model; any coupling into `audit/portfolio_governor_*` readiness surfaces.
