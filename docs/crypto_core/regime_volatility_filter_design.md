# Regime / Volatility Filter Evidence (RF) — Design Contract (Fable-authored, 2026-07-08)

Status: RF-2..RF-5 IMPLEMENTED (V1 closure, section 7); RF-6/RF-7 DESIGN ONLY. Purpose: deterministic,
PIT-grade regime LABELS as digest-bound evidence.
A regime filter is NOT an edge — it labels market state so strategies can be gated and performance
stratified; it never produces direction/profit signals. The existing `regime/tracker.py`
(`MarketRegimeTracker`: stateful deque, `update()` mutation, wall-clock ns, float scores) is
RUNTIME REFERENCE ONLY — the evidence chain must NEVER import `crypto_core.regime` (AST-enforced).
Module namespace: `validation/regime_*` (no collision with the runtime package).

## 1. Artifact sequence (RF-2..RF-7)

1. **RF-2 `regime_feature_policy.py` — `RegimeFeaturePolicy`**: the preregistration core — pinned
   feature-class set, window lengths, formula-policy ids, label RULE STRUCTURES (threshold values
   GOVERNANCE_REQUIRED), parameter search bounds (same digest discipline as the EF-5 ledger),
   min-observation counts, UNLABELED cap. Verdict {POLICY_READY, POLICY_REJECTED}.
2. **RF-3 `regime_feature_series_evidence.py`**: per-UTC-day feature values computed from
   packet-registered series only (Fraction/Decimal; float forbidden); every value carries
   (day_index, value, inputs_window_digest); the builder RECOMPUTES every caller-supplied value
   from the authenticated records of an accepted `HistoricalPitDataset` (section 7) —
   `feature_recompute_mismatch` → REJECTED.
3. **RF-4 `regime_label_evidence.py`**: label(D) = rule_set(features[<= D-1]) — PRIOR-DAY-CLOSE
   discipline: only features finalized by end of D-1 may label day D. Missing feature day →
   UNLABELED (never silently filled); UNLABELED ratio above cap → REJECTED. Label set is a pinned
   enum in the policy (growth requires new governance approval — stratum inflation is p-hacking).
4. **RF-5 `regime_stability_evidence.py` — THE REPAINT PROOF**: takes two label evidences built
   from the SAME policy at two DIFFERENT as-of points; verifies label equality day-by-day on the
   overlapping day-index range — a SINGLE mismatch → STABILITY_REJECTED (later data may never
   change an earlier day's label); also reports distribution drift (Decimal) with a
   GOVERNANCE_REQUIRED cap. Verdicts {STABILITY_PROVEN, STABILITY_REJECTED, INSUFFICIENT_OVERLAP}
   — INSUFFICIENT_OVERLAP never advances.
5. **RF-6 `regime_filter_admission_decision.py`**: admits a filter for a specific spec ONLY when
   (a) stability is STABILITY_PROVEN and (b) the policy digest is a MEMBER of that spec's EF-5
   preregistration ledger — a policy created AFTER performance was seen can never be admitted
   (post-hoc filter fitting is structurally impossible, not just forbidden).
6. **RF-7 `regime_conditioned_performance_evidence.py`**: regime-stratified performance report
   (day-index join of labels with sleeve returns); per-stratum count/mean/Sharpe-if-sufficient/
   max-DD in Decimal; strata below min-observation are marked `insufficient_sample` and never
   trusted; NO threshold decisions here — pure report. Feeds EF-6 `regime_split_report` and RG-5
   regime-stratified correlation.

## 2. Feature classes (ids pinned in policy; no current-market facts invented)

F1 realized-vol (rolling return stddev, n-1, closed-finalized prices); F2 drawdown-state (rolling
peak distance); F3 trend/range persistence (HIGHEST overfit risk — second wave, narrow
preregistered bounds + mandatory RF-5); F4 funding-regime hook (packet FUNDING_RATE with
`final` semantics ONLY — `predicted` may never feed a feature); F5 liquidity/spread hook and
F6 liquidation-event hook are packet/DR-conditional (disabled in policy unless the data exists).
Recommended v1 scope: F1 + F2 (+F4 for the funding pilot).

## 3. No-lookahead / no-repaint rules (binding)

Windows use [D-w, D-1] finalized data only; label(D) labels day D but derives only from pre-D
data (decision moments within D may read it); rule parameters are policy-pinned BEFORE
application windows (re-fitting = new policy version + new EF-5 entry — old labels stay
historical under the old digest); late-finalizing sources may feed only later days, never rewrite
earlier labels (RF-5 catches violations); interpolation is forbidden.

## 4. GOVERNANCE_REQUIRED

Label-set members; all thresholds; window lengths; min-observation counts; UNLABELED cap; drift
cap; standard as-of pair for RF-5 (recommendation: walk-forward window boundaries). See
`governance_decision_framework.md`.

## 5. Test-matrix skeleton

Recompute-equality tamper (RF-3); prior-day-close boundary arithmetic (D-1 finalization edges —
top P1 focus); UNLABELED cap bypass; predicted-funding leakage into F4; dual-as-of single-mismatch
rejection (RF-5); post-performance policy admission attempt (RF-6 vs EF-5 ledger); insufficient-
sample stratum trust (RF-7); `crypto_core.regime` import attempt (AST); structural-False AST.

## 6. Stop conditions

Any import of the runtime regime package; any threshold/label-set invention; any silent UNLABELED
fill; any admission without ledger membership proof; scope beyond the named slice.

## 7. V1 closure — `RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1`

Implemented under the controller structural authority `RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1` in
`validation/regime_feature_policy.py`, `regime_feature_series_evidence.py`, `regime_label_evidence.py` and
`regime_stability_evidence.py`. RF-6 admission, RF-7 conditioned performance and every EF/RG consumer integration
remain the next protected closure; the accepted EF/RG regime fields stay pending/unavailable.

- **RF-2**: only `F1_REALIZED_VOL` (`RF_F1_SIMPLE_RETURN_SAMPLE_STDDEV_V1`, lookback >= 3) and `F2_DRAWDOWN_STATE`
  (`RF_F2_ROLLING_PEAK_DISTANCE_V1`, lookback >= 2); `F3`-`F6` are refused explicitly, never stubbed. Each feature
  binds an EF-3 series, an instrument, a mandatory governed `value_name` (the accepted PIT value-name token grammar;
  no default and no production name), a lookback and its formula id. The policy digest commits the `value_name`, so
  changing only it invalidates an existing approval. Label rules have contiguous priorities from 1
  and conjunctive `LT`/`LTE`/`GT`/`GTE` predicates on canonical scale-18 thresholds; the first matching rule wins and
  no match is the reserved `UNLABELED`, never a label-set member. Every number is a governance value with no
  default; only an exact `HUMAN_GOVERNANCE` approval advances. Verdicts use the shared kernel: `PASS` or
  `NEEDS_GOVERNANCE_APPROVAL`, and malformed or inconsistent input raises (the `POLICY_REJECTED` of section 1).
- **RF-3** (`RF3_AUTHENTICATED_HISTORICAL_PIT_DATASET_BINDING_V1`): the source authority is the accepted
  `HistoricalPitDataset` (`validation/historical_pit_dataset.py`, reused unchanged). There is no caller close and no
  caller source digest.
  - Re-proof: the exact EF-3 manifest is re-proven (intact, READY, anchor-equal). The exact dataset is re-proven by
    `verify_historical_pit_dataset`, which recomputes every record digest and re-proves the dataset's embedded EF-3
    binding. The dataset must be intact, anchor-equal, READY, PASS and advancing.
  - Same world: the dataset's `source_manifest_digest` and its embedded manifest snapshot must be the supplied
    manifest's.
  - Correlation: `pit_dataset.correlation_id == source_manifest.correlation_id == correlation_id`.
  - Feature series: each must be finalized-only, point-in-time revision-safe, rights-usable, feature-input eligible,
    a price series, and must cover the instrument.
  - Cutoff: feature day D reads only source days D-w..D-1, from the records `select_visible_pit_records` shows for
    the exact series and instrument at `decision_time_ns = start(D)`. The boundary is INCLUSIVE, the accepted PIT
    convention (`available_at_ns <= t`, `finalized_at_ns <= t`, the latest visible revision vintage). One nanosecond
    later is excluded, and day D or later is never read.
  - One record per day: source day d's close is the governed `value_name` value of the ONE visible record with
    `start(d) < event_time_ns <= start(d + 1)`. The feature-day is unavailable, and never filled, substituted,
    interpolated, carried forward or backfilled, when there are zero such records (`window_day_not_visible_at_cutoff`),
    more than one (`window_day_ambiguous`, never an arbitrary or latest pick), no governed value, or a close that is
    not strictly positive.
  - Provenance: every consumed close is a `RegimeDailyCloseObservation` derived from one record and bound to its
    `source_record_digest`, which is that record's own digest, recomputed by the accepted verifier from every other
    record field. Each feature record binds its `source_record_digests` and an `inputs_window_digest` over the dataset
    digest and every consumed close's full provenance (series, instrument, source day, value name, value, and event,
    availability and finality coordinates). So no value, identity or coordinate can change under a retained digest.
  - Numerics: values follow `RF_FIXED_SCALE18_DECIMAL_HALF_EVEN_P80_V1` (exact half-even scale 18; the F1 square root
    is a precision-80 candidate adjudicated exactly). Every claimed value is recomputed, and a mismatch raises
    `feature_recompute_mismatch`, so no artifact carries it.
  - Non-claim: record authentication proves internal provenance only, never that an external archive was honest or
    complete, so `external_market_truth_proven` stays False.
- **RF-4**: label(D) reads only D's RF-3 records, and any unavailable policy feature makes D `UNLABELED`. Every window
  day stays in the denominator, and `unlabeled_days / label_days <= max_unlabeled_fraction` passes; above the cap
  the evidence is `FAIL` and never advances.
- **RF-5**: two RF-4 evidences of the same exact policy, the earlier as-of strictly before the later by at least the
  governed day gap. Every overlapping day's label must be identical (one mismatch is `STABILITY_REJECTED`), the
  overlap must reach the governed minimum (else `INSUFFICIENT_OVERLAP`), and the exact total variation distance of
  the full-window label distributions over the label set plus `UNLABELED`
  (`RF5_TOTAL_VARIATION_LABEL_DISTRIBUTION_DRIFT_V1`) must be at most the governed cap. A label evidence that fails
  its own UNLABELED cap also makes the status `STABILITY_REJECTED`. A policy without exact human governance is
  `NEEDS_GOVERNANCE_APPROVAL`, never `STABILITY_PROVEN`, and only `STABILITY_PROVEN` advances.
