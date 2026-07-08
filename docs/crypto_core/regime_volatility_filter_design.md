# Regime / Volatility Filter Evidence (RF) — Design Contract (Fable-authored, 2026-07-08)

Status: DESIGN ONLY. Purpose: deterministic, PIT-grade regime LABELS as digest-bound evidence.
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
   from raw input digests — `feature_recompute_mismatch` → REJECTED.
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
