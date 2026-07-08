# Secondary Metrics Enforcement (SM) — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. Purpose: replace `declared_not_enforced_review_only` hit/fill/slippage with
an ENFORCED, digest-bound trade-record chain. This is one of the two hard prerequisites of
completion v3 (the other is machine-time provenance, `machine_time_provenance_design.md`).
No Deep Research needed — everything builds on merged paper substrate.

## 1. Why (source-grounded gap)

Merged #316 passes `paper_hit_rate=None, paper_slippage_bps=None, paper_fill_rate=None,
paper_trade_count=0` with source `not_carried_zero_placeholder.v1`
(`paper_stage4_comparison_evidence.py:1173-1176`). Merged methodology v1 declares the three
metrics `declared_not_enforced_review_only` with structural-False enforced flags. Existing
substrate to consume (never modify): `PaperEndToEndEpisode` (intent→fill→realized lineage),
`PaperFillSimulationResult` (FILLED/PARTIAL/REJECTED), `fill_pricer` (mid + half-spread + impact),
`PaperRealizedPnlEvent` (per-fill realized PnL).

## 2. Artifact sequence (5 slices, each its own PR after SM-2 policy exists)

1. **SM-2 `secondary_metrics_policy.py` — `SecondaryMetricsPolicy`** (policy-only, consumes no
   evidence). Pins: hit-rate definition (realized-PnL-positive episode / decided episodes),
   fill-rate definition (filled quantity / intended quantity, and/or filled-episode ratio — BOTH
   pinned explicitly), slippage definition (signed bps vs expected-fill reference price),
   expected-fill model REFERENCE (policy carries the `fill_pricer` model identity + parameters
   digest — no separate evidence artifact), rounding/Decimal policy (scale-18 ROUND_HALF_EVEN,
   Fraction intermediates), threshold STRUCTURE (floor/ceiling fields exist; numeric values are
   GOVERNANCE_REQUIRED and rejected unless approved values are supplied), verdict
   {POLICY_READY, POLICY_REJECTED}.
2. **SM-3 `paper_trade_record_evidence.py` — `PaperTradeRecordEvidence`**. Consumes the episode
   set + REJECTED fill results + realized-PnL events for one window; digest-anchors each episode;
   requires ledger reconciliation (sum of per-fill realized == window realized totals; count
   coherence); rejected fills are first-class records (fill-rate denominator integrity — a chain
   that hides rejects must fail); replay/duplicate defense on episode ids + digests.
3. **SM-4 `secondary_metrics_evidence.py` — `SecondaryMetricsEvidence`**. Decimal-authoritative
   hit/fill/slippage computed FROM SM-3 raw records (builder recomputes; carried values never
   trusted); binds policy digest + trade-record digest; float echoes advisory-only; Decimal/float
   divergence → REJECTED.
4. **SM-5 `paper_vs_backtest_methodology_v2.py`** (NEW module; v1 untouched). Same governance
   anchors as v1 PLUS `hit_rate_floor_enforced=True`, `fill_rate_floor_enforced=True`,
   `slippage_ceiling_enforced=True` — legal ONLY here, bound to approved numeric thresholds and
   the SM policy digest. Schema `paper-vs-backtest-methodology.v2`.
5. **SM-6 `paper_stage4_comparison_evidence_v2.py`** (NEW module; #316 untouched). Feeds REAL
   `paper_*` values from SM-4 into `compare_stage4` only for existing comparison/retention behavior;
   `None` paper metrics → REJECTED (the v1 placeholder path is structurally impossible here);
   carries methodology-v2 digest; retention verdict still recomputed in Decimal. Current
   `compare_stage4` is NOT the enforcement authority for secondary metric thresholds unless it is
   separately extended in a scoped PR. Passing values into `compare_stage4` is insufficient to claim
   secondary metric enforcement.

## 3. Enforcement boundary

- SM-4/SM-6 explicitly compare computed Decimal metrics against approved thresholds from
  `SecondaryMetricsPolicy`; enforcement does not rely on current `compare_stage4` echo behavior.
  Required checks: `paper_hit_rate >= approved_hit_rate_floor`, `paper_fill_rate >=
  approved_fill_rate_floor`, `paper_slippage_bps <= approved_slippage_ceiling_bps`, and decided / trade
  count meets the approved minimum. Computation is Decimal/Fraction authoritative; carried float
  echoes are advisory-only.
- `paper_stage4_comparison_evidence_v2.py` may consume `compare_stage4` only for existing
  comparison/retention behavior while secondary metric threshold enforcement is performed explicitly
  in v2 evidence logic, or later in a separately extended comparator with its own scoped PR. `None`
  paper secondary metrics remain structurally rejected. This design makes no enforced-now claim.

## 4. Cross-cutting invariants

- Every artifact: canonical-JSON SHA-256 self-digest (self-field excluded); recompute == carried
  == expected anchor; raise (malformed caller input) vs REJECTED (trust/value failure) split as in
  v1 modules; reason prefix `<module_snake>:<code>`; scope/BIST/clock token guards copied.
- Non-overclaim: SM proves measurement enforcement only — never edge, profitability, completion,
  readiness, machine-time. All such flags structurally False in every SM artifact.
- Denominator integrity is the SM-specific P1 class: hit-rate and fill-rate are trivially gamed by
  dropping losing/rejected records; SM-3's reconciliation + rejected-fill first-classing exists
  precisely to make that structurally visible.

## 5. GOVERNANCE_REQUIRED (numbers are human-owned)

Hit-rate floor, fill-rate floor, slippage ceiling (bps), minimum decided-episode count for a valid
window. See `governance_decision_framework.md` for the trade-off analysis; artifacts REJECT
unapproved values.

## 6. Test-matrix skeleton per slice

Happy READY; digest tamper per anchor; reseal (carried metric != recompute); denominator attacks
(dropped reject, dropped losing episode, duplicate episode); ledger mismatch; Decimal/float
divergence; threshold-structure violations (unapproved number, wrong operator); structural-False
AST + forbidden-import AST; determinism roundtrip. Required named regressions:
test_secondary_metrics_thresholds_enforced_outside_current_comparator,
test_compare_stage4_echo_does_not_satisfy_secondary_metric_enforcement,
test_hit_rate_below_floor_blocks_secondary_metric_enforcement,
test_fill_rate_below_floor_blocks_secondary_metric_enforcement,
test_slippage_above_ceiling_blocks_secondary_metric_enforcement,
test_unapproved_thresholds_rejected.

## 7. Dependencies and order

SM-2 needs governance numbers only at USE time (policy can merge with structure + rejection of
unapproved values first). SM-3/4 need no external facts. SM-5/6 need approved numbers. v3 consumes
SM-6 + MT chain. Comparator (`stage4_comparator.py`) already carries hit/fill/slippage end-to-end
(`Stage4BacktestBaseline` requires backtest_hit_rate; optional slippage/fill), but current
`compare_stage4` echo/retention behavior is not enough for threshold enforcement. No comparator
change is needed only if SM-6 performs the approved-threshold comparisons explicitly in v2 evidence
logic; a comparator-owned enforcement path would require a separate scoped comparator PR.

## 8. Stop conditions

Any need to modify episode/fill/pnl substrate modules; any pressure to invent threshold numbers;
any fill-model change (that is a separate governance decision); scope beyond the named slice.
