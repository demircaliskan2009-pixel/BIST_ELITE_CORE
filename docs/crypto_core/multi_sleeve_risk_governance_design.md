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
   (exact `Fraction`, no rounding), re-pinning the envelope's ladder and portfolio-stop structure
   as provenance only. Prerequisite: the governed `paper_portfolio_performance_path_policy.py`,
   which carries one synthetic, dimensionless performance weight per envelope-declared sleeve
   (strictly positive, exact sum 1, GOVERNANCE_REQUIRED). These weights are never allocation,
   capital, risk-budget, cap or `paper_performance_reference_notional` semantics. Rules:
   - portfolio index `P_t = sum_i(w_i * I_i,t)` over the sleeves' exact normalized indices, with
     fixed initial weights and no rebalance within the evidence window
     (`NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1`), so `P_0 = 1`;
   - every covered sleeve supplies re-proven RG-3 evidence on the exact same ordered UTC-day
     grid; a missing or uncomputable sleeve makes the portfolio NOT_COMPUTABLE, and nothing is
     dropped, interpolated or carried forward;
   - the start index 1 is the first running-peak observation, then
     `M_t = max(M_(t-1), X_t)` and peak distance `(M_t - X_t) / M_t`;
   - RG-4 outputs both the current (end-of-window) and the maximum peak distance of every
     sleeve and of the portfolio, and decides nothing.
4. **RG-5 `paper_sleeve_correlation_evidence.py`**: pairwise sleeve return correlations over
   aligned UTC-day indices, measurement evidence only (`RG5_PEARSON_CORRELATION_METHODOLOGY_V1`).
   FAIL-CLOSED RULE: insufficient overlap or missing data → correlation is treated as WORST-CASE
   1.0 for budget math (never 0, never skipped). Rules:
   - the complete canonical pair matrix: every unordered pair of envelope-declared sleeves exactly
     once as `(min, max)`, lexicographically sorted; a one-sleeve envelope has none;
   - exact UTC-day alignment: RG-3 daily return `i` is the UTC day starting at `window_start_ns`
     plus `i` days, so pairs align by day identity, never by position, interpolation,
     carry-forward or backfill;
   - the governed trailing lookback `[evaluation_end - lookback_window_days, evaluation_end)` and
     the governed `min_overlap_days`, both only from the re-pinned RG-2 envelope, with an injected
     UTC-day-aligned evaluation end; a sleeve counts only when its evidence window ends exactly at
     the evaluation end, so no later observation, and no readiness that depends on one, takes part;
   - Pearson product-moment `rho = Sxy / sqrt(Sxx * Syy)` over exact `Fraction` moments, so the
     sample-versus-population denominator cancels; zero variance in either aligned vector makes
     the pair unknown;
   - public values follow `decimal_quantized_scale_18_round_half_even_internal_precision_80.v1`:
     exactly 18 fractional digits, ROUND_HALF_EVEN, signed zero normalized; an explicit precision-80
     context only proposes a candidate for the irrational value, and exact rational comparisons
     against the half-unit boundaries decide the published digit, so it is correctly rounded for
     every accepted input;
   - an unknown pair's effective correlation is exactly `1.000000000000000000`; READY means the
     complete conservative matrix, never that every pair was observed.
   RG-5 decides no cap breach, diversification credit or allocation: RG-7 applies worst-case
   correlation. Regime-stratified correlation is a pending field until the RF chain merges.
5. **RG-6 `paper_sleeve_promotion_demotion_decision.py`**: ladder transitions
   (PROBATION → STANDARD → EXPANDED, and demotions) of one sleeve from re-proven RG-3/4/5
   evidence against the re-pinned envelope thresholds
   (`RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1`). Rules:
   - genesis is a governed ladder seed whose tier is always PROBATION, entered at an explicit
     UTC-day-aligned coordinate; only an exact HUMAN_GOVERNANCE approval of the seed policy and
     the RG-6 rule set lets it advance;
   - a later decision takes its current tier and tier entry only from its prior RG-6 decision of
     the same sleeve, envelope and seed, rebuilt from that prior's exact inputs, at a strictly later
     evaluation end; only a READY prior carries state, and any other prior propagates its status;
   - the lineage is re-proven without recursion
     (`RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1`): the nested priors are
     walked back to the seed iteratively, the seed is re-proven, and each ancestor is rebuilt once,
     oldest first, on the same assembly path as the current decision, so supported history of any
     length verifies; there is no depth cap, checkpoint or trusted prefix;
   - no registry, head or latest lookup exists: `current_ladder_head_proven` is structurally
     False, and a decision is history, never the current ladder state;
   - tenure is the exact number of UTC days from the current tier entry to the evaluation end;
     performance is the RG-3 `paper_sharpe_annualized`. RG-6 owns how ladder thresholds consume
     RG-4 sleeve drawdown evidence: the target sleeve's RG-4 `max_peak_distance` for promotion
     and demotion alike (`MAX_PEAK_DISTANCE`), never the current peak distance and never
     portfolio drawdown; RG-3 and RG-4 end exactly at the evaluation end;
   - RG-5 at the same evaluation end is re-proven provenance only: its cap is never evaluated and
     no worst-case pair moves a sleeve;
   - promotion needs tenure `>= min_probation_days`, Sharpe `>=` its floor and maximum drawdown
     `<=` its ceiling; demotion needs Sharpe `<` its floor or maximum drawdown `>` its ceiling.
     STANDARD evaluates demotion first and evaluates promotion only when no demotion breach
     applies; a ladder that contradicts the RG-2 consistency invariant fails closed;
   - at most one adjacent transition per record: HOLD keeps the tier and its entry, while PROMOTE
     or DEMOTE moves one tier and enters it at the evaluation end;
   - single-stratum-concentrated returns (via RF conditioned performance) remain a demotion
     reason that stays pending and unevaluated until the RF chain merges.
   RG-6 decides no allocation, cap breach, diversification credit, kill or quarantine, portfolio
   stop or execution, and chooses no production number: every threshold is GOVERNANCE_REQUIRED.
6. **RG-7 `paper_portfolio_allocation_decision.py`**: the allocator — inputs: envelope + per-sleeve
   evidence + EF-7 admissions + kill states. ORDER OF OPERATIONS IS THE P1 INVARIANT:
   (a) kill/quarantine override FIRST (killed sleeve → allocation 0 BEFORE any arithmetic);
   (b) worst-case correlation applied to combined exposure; (c) envelope check — ANY breach →
   `ALLOCATION_REJECTED` for the whole proposal (NO silent scaling, no partial fits);
   (d) only then per-sleeve arithmetic. Output is digest-bound allocation EVIDENCE. Rules, under the
   controller structural authority `RG7_ALLOCATION_AUTHORITY_AND_MATH_POLICY_V1`:
   - current lifecycle authority (`RG7_HUMAN_GOVERNANCE_PAPER_CURRENT_HEAD_ATTESTATION_V1`): EF-8 stays
     historical only and is not changed. A `PaperLifecycleHeadAuthority` is the bounded paper-only claim
     that, at one exact evaluation end, HUMAN_GOVERNANCE attests one re-proven, advancing EF-8 receipt as
     the current lifecycle head of one allocation subject. The approval supplies the "no later successor"
     fact, which is never inferred from the lifecycle sequence, an effective time, the newest object, a
     state, a digest or caller ordering; `TEST_ONLY_SYNTHETIC` never establishes it, and no global or live
     currentness is claimed;
   - exactly one allocation subject per envelope-declared sleeve
     (`RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1`): one re-proven EF-7 PASS admission that opened the
     governed head's current cycle, one lifecycle-head authority and one intra-sleeve risk-budget source;
     no duplicate, missing or extra sleeve;
   - a sleeve's pre-kill proposal is exactly its re-proven intra-sleeve `total_reserved_budget`: no
     performance, Sharpe, Kelly, volatility, risk-parity or tier sizing. RG-6 has no numeric effect,
     because RG-2 defines no tier-to-budget multiplier;
   - (a) a DISABLED or QUARANTINE governed head zeroes the sleeve and every record, and no numeric field
     of it enters the total, a sleeve or market sum, the positive-sleeve count or a correlation pair; an
     unproven head is never ACTIVE and leaves the decision NEEDS_GOVERNANCE_APPROVAL with no exposure
     evaluated;
   - (b) `RG7_CORRELATION_ACTIVE_PAIR_CAP_RULE_V1`: a pair is exposed only when both of its sleeves carry a
     positive post-kill budget, and its RG-5 effective correlation (exactly 1 for WORST_CASE_UNKNOWN) must
     not exceed the envelope's pairwise cap. No covariance, square-root portfolio risk,
     correlation-weighted scaling, diversification credit, averaging or matrix inversion;
   - (c) every positive post-kill record's instrument must equal an envelope market inside the EF-7 pinned
     universe, a market's exposure is the exact sum across sleeves, and the total, sleeve, market,
     positive-sleeve-count and exposed-pair caps are inclusive. A rejected proposal allocates zero
     everywhere and keeps its requests and exact breach reasons as evidence;
   - (d) READY sets every final allocation to its exact post-kill reservation. READY is accepted paper
     allocation evidence, never capital allocated, an order or execution permitted, or live, shadow or
     operational readiness.
7. **RG-8 `paper_portfolio_governance_decision.py`**: the terminal governance record — binds
   envelope + all evidence + allocation into one decision; portfolio-stop conditions evaluated
   from envelope rules only (advisory regime-drift warnings never trigger stops by themselves).
   RG-8 owns how portfolio-stop levels consume RG-4 portfolio drawdown evidence.

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
levels, probation windows); portfolio-stop levels; portfolio performance weights
(`paper_portfolio_performance_path_policy.py`). See `governance_decision_framework.md`.

## 4. Test-matrix skeleton

Happy allocation; kill-override-before-arithmetic proof (killed sleeve with huge "performance"
gets 0 and arithmetic never sees it); worst-case-correlation on missing overlap; envelope breach
→ whole-proposal rejection (no partial fit); ladder transition matrix; digest tamper per input;
pending-RF fields correctness; structural-False AST.

## 5. Dependencies

RG-2 can merge early (structure + rejection of unapproved values). RG-3 needs only merged
substrate; RG-4 needs merged RG-3 plus the governed `paper_portfolio_performance_path_policy.py`.
RG-5 full value arrives with RF labels (pending pattern until then). RG-6/7/8 need
governance numbers. EF-7 admissions are allocator inputs — EF chain should land first.

## 6. Stop conditions

Any temptation to scale silently; any allocation to an unproven/killed sleeve; any envelope number
invented by a model; any coupling into `audit/portfolio_governor_*` readiness surfaces.
