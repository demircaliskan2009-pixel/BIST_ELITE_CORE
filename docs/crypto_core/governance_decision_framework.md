# Governance Decision Framework (Fable-authored, 2026-07-08)

Purpose: every `GOVERNANCE_REQUIRED` constant across the SM/MT/EF/RG/RF/pilot families, with the
trade-off analysis a human needs to approve it. NO NUMBERS ARE CHOSEN HERE — models never own
these values; artifacts REJECT unapproved values by construction. Approving a number means
recording it in the relevant policy artifact under an explicit authorization.

## 1. How to use this file

For each decision: read the trade-off, pick a value (or a review cadence), record it in the named
policy artifact's approved-constants, and note the authorization in the PR body. Numbers here are
NOT recommendations unless marked "natural anchor" — a natural anchor is an existing merged
precedent, not advice.

## 2. SM — secondary metrics (consumer: `secondary_metrics_policy.py`)

| Constant | Trade-off | Notes |
|---|---|---|
| hit_rate_floor | Too high → rejects valid low-hit/high-payoff styles (carry/trend); too low → meaningless gate | Consider per-edge-family floors instead of one global; hit rate is style-dependent, not quality-dependent |
| fill_rate_floor | Too high → punishes passive/maker styles that legitimately miss fills; too low → fill illusion passes | Must be read together with the expected-fill model identity; changing the fill model resets calibration |
| slippage_ceiling_bps | Too tight → paper noise rejects honest strategies; too loose → cost illusion survives to v3 | Anchor to the pinned `fill_pricer` (mid + half-spread + impact) expectations per market |
| min_decided_episode_count | Too low → metrics are statistical noise; too high → delays v3 path | Natural anchor: the 30-day discipline suggests a per-window minimum consistent with daily activity |

## 3. MT — machine time (consumer: `machine_time_policy.py`, values post-DR)

| Constant | Trade-off |
|---|---|
| accepted source classes + quorum composition | More classes = harder forgery but higher operational failure rate (a dead beacon stalls sealing); quorum >= 2 independent classes per role is the structural minimum |
| clock-skew tolerance | Too tight → honest proofs fail on normal skew; too loose → sandwich interval loses meaning |
| spacing rule parameters | Must make 30 days incompressible while tolerating legitimate sealing delays |
| proof archival format/retention | Longer retention = re-verifiability years later vs storage/ops cost |

## 4. EF — edge factory (consumers: EF-2/5/7 artifacts)

| Constant | Trade-off |
|---|---|
| kill-criteria thresholds | Too sensitive → whipsaw kills on noise; too tolerant → slow bleed survives; asymmetric (fast kill, slow revive) is the safer shape |
| preregistered search-bound sizes | Wider bounds = more freedom but every variant is a multiple-testing ledger entry — the OOS bar must rise with the count |
| min OOS window count | More windows = robustness vs time-to-decision |
| capacity assumptions | Overstated capacity = fake scalability; understated = wasted edge |
| pre-paper PBO bands `a < c <= e` and the capped-band fraction (consumer: `edge_pre_paper_validation_policy.py`) | PRDV4 §1.20 sets the loosest legal values (0.20 / 0.40 / 0.60, cap 1/2); stricter bands reject more honest candidates but admit fewer overfit ones |
| LIMITED_S1_PAPER_V1 regime cap fraction | At most 1/4 while the regime-conditional PBO is UNPROVEN: PRDV4's worst case applied to every regime; a lower value shrinks every admitted sleeve's RG-7 room |
| Monte Carlo `p_max` and closed-trade floor | `p_max <= 0.05`, at least 50 closed trades (PRDV4 Stage 1); a stricter level rejects marginal significance, a higher floor needs longer frames |
| sensitivity retention floor | At least 0.5 (PRDV4: a drop of more than 50% within ±10% rejects); higher = demands flatter parameter landscapes |
| Stage-3 stress multipliers | At least PRDV4 Stage 3 (slippage x2.0; depth x0.2 and slippage x3.0; gap 10%, 5-minute recovery); harsher = fewer survivors |
| flash-crash depth, slippage and maintenance fraction | PRDV4 names none: governed modeling inputs only, never venue liquidation facts (E2 stays unproven) |
| trial-chain genesis and E1 (consumer: `edge_trial_count_chain.py`) | E1 is the human-attested count of variants tested before the chain; an understated E1 deflates the DSR too little. Never defaulted; its digest is pinned by the policy |
| per-evaluation currentness attestation | A human attests the chain head is current and no tested variant is off-chain; without it the DSR cannot advance |

## 5. RG — portfolio governance (consumer: `paper_portfolio_risk_envelope.py`)

| Constant | Trade-off |
|---|---|
| total budget / per-sleeve / per-market caps | Caps define blast radius; per-market caps guard against many sleeves holding the same underlying risk |
| admission cap fraction (not an RG-2 value; consumer: RG-7) | Carried by the authenticated EF-7 v2 admission (`min` of the PBO band cap and the LIMITED_S1 regime cap); RG-7 requires each sleeve's reservation to be at most this fraction of its RG-2 sleeve cap, inclusive, rejecting (never scaling) a breach |
| correlation cap | With unknown-correlation=1.0 fail-closed, a tight cap effectively forces evidence production before diversification credit is granted — that is intended |
| ladder thresholds + probation windows | Fast promotion = capital efficiency vs regime-luck promotion; slow demotion = stability vs bleed |
| portfolio-stop levels | Hard stops protect capital but crystallize drawdowns; levels must be pre-committed to avoid discretionary panic/greed |
| portfolio performance weights (consumer: `paper_portfolio_performance_path_policy.py`) | They fix the one synthetic path RG-4 measures portfolio drawdown on: concentrated weight makes portfolio drawdown track one sleeve, while spread weight can hide one sleeve's drawdown inside the blend. They are synthetic performance weights only, never derived from or read as budgets, caps, reference notionals, capital or RG-7 allocation. One strictly positive weight per declared sleeve, exact sum one, fixed for the evidence window |

## 6. RF — regime filter (consumer: `regime_feature_policy.py`)

| Constant | Trade-off |
|---|---|
| label-set members | More labels = finer gating but thinner strata (p-hacking surface grows); start minimal (e.g. vol high/low + drawdown-state class), grow only with governance |
| window lengths | Short = responsive but noisy labels; long = stable but laggy |
| min-observation per stratum (RF-7 `RegimeConditionedPerformancePolicy`, consumer: `regime_conditioned_performance_evidence.py`) | Below it, stratum stats are decoration — `insufficient_sample` exists so nobody trades decoration. Its own exact human approval, an integer of at least 2 (a sample variance needs two observations), never borrowed from the RF-5 overlap minimum: a low floor publishes noisy strata, a high one withholds most metrics |
| UNLABELED cap | High cap tolerates data gaps but a mostly-UNLABELED series labels nothing meaningful |
| drift cap (RF-5) | Tight = rejects regime-definition instability early; loose = accepts drifting definitions that repaint slowly |
| feature definitions (V1: F1 realized vol, F2 drawdown state) | Each binds an EF-3 series, an instrument, the governed PIT value name read as the close, a lookback and its formula id; more features = richer labels but more ways to overfit the label set |
| label rule thresholds and priorities | Pinned before any label exists; the first matching rule wins, so priority order is part of the methodology and re-ordering is a new policy version |
| stability minimum overlap days / minimum as-of gap days (RF-5) | A short overlap or a small gap proves little about repaint; long ones delay stability evidence |
| regime filters preregistered per spec (EF-5 V2 ledger, consumer: `regime_filter_admission_decision.py`) | The preregistration approval commits the exact set of governed RF-2 policies a spec may later admit. Each one is one more preregistered hypothesis, so a wide set widens the search a regime-conditioned evaluation must count, and an empty set leaves RF-6 nothing to admit. Adding a filter after results needs a new preregistration |

## 6a. GP — governed paper execution (consumers: `governed_paper_execution_authority.py`, `governed_admitted_variant_paper_execution.py`)

None of these is needed to construct the code or its synthetic tests. Every one is needed before any real governed
paper evidence exists; until then real paper execution stays BLOCKED. Tests record them only as `test-fixture:`
values.

| Commitment | Trade-off |
|---|---|
| C1 paper adoption of the economics and parameter approvals | The economics and parameter approvals carry no time or purpose field; adopting them for a paper period is a separate decision, never an implicit extension of a backtest approval |
| C2 bootstrap authority and horizon H (at least 30 UTC days) | A longer H gives a zero-history sleeve more time to reach 30 daily returns, but it also extends the period run without RG-8. One-use, one sleeve, one genesis |
| C3 per-cycle approval | Approves exactly one derived cycle (reservation, RG chain, phase). Approval fatigue against unreviewed cycles; no blanket approval exists |
| C4 head attestation per cycle opening and close | Only a human can attest that no later lifecycle successor exists at an instant. A stale or missing attestation stops the day |
| C5 equity-basis reference notional equal to the economics initial equity | Structural equality; if the policies disagree, aligning them is a human decision, never a default |
| C6 capacity measures other than the supported open-position notional | Equating measures with different units or scopes fakes capacity; each new measure needs its own semantics decision |
| C7 governor policy thresholds of the time-window chain | The RG-3 time window rebuilds from a metrics summary whose governor thresholds are human values |
| C8 reservation band beta | A tight band refuses fills (including exits) on ordinary price drift; a loose band reserves more risk budget per unit. It bounds the fill notional the generic overfill guard checks |
| C9 RG-6 ladder seed | The seed's tier entry is the paper genesis; ORDINARY needs a READY RG-6 from it |
| D1 venue-fact currency (Deep Research) | The economics policy's cited venue facts (taker fee, funding interval, contract and quantity semantics, latency) must be current for the paper period's dates before any non-synthetic period |

## 7. Pilot — funding/basis/carry (values post-DR, PRM-16)

Venue fee/funding mechanics constants (from DR citations only); per-candidate go/no-go (S1 passive
carry → S4 vol-gated → S3 continuation → S2 basis MR → S5 two-leg, S5 blocked until SM enforced);
position sizing bounds within RG envelope.

## 8. Standing rules

1. A model may PROPOSE analysis; only a human APPROVES a number. 2. Every approved number lives in
exactly one policy artifact and is re-pinned by consumers (digest-bound). 3. Changing a number =
new policy version + new digest — old evidence stays historical under the old digest, never
retro-edited. 4. Unapproved value in any input → artifact REJECTS (fail-closed), never defaults.
