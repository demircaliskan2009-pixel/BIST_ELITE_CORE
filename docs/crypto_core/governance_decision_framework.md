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

## 5. RG — portfolio governance (consumer: `paper_portfolio_risk_envelope.py`)

| Constant | Trade-off |
|---|---|
| total budget / per-sleeve / per-market caps | Caps define blast radius; per-market caps guard against many sleeves holding the same underlying risk |
| correlation cap | With unknown-correlation=1.0 fail-closed, a tight cap effectively forces evidence production before diversification credit is granted — that is intended |
| ladder thresholds + probation windows | Fast promotion = capital efficiency vs regime-luck promotion; slow demotion = stability vs bleed |
| portfolio-stop levels | Hard stops protect capital but crystallize drawdowns; levels must be pre-committed to avoid discretionary panic/greed |

## 6. RF — regime filter (consumer: `regime_feature_policy.py`)

| Constant | Trade-off |
|---|---|
| label-set members | More labels = finer gating but thinner strata (p-hacking surface grows); start minimal (e.g. vol high/low + drawdown-state class), grow only with governance |
| window lengths | Short = responsive but noisy labels; long = stable but laggy |
| min-observation per stratum | Below it, stratum stats are decoration — `insufficient_sample` exists so nobody trades decoration |
| UNLABELED cap | High cap tolerates data gaps but a mostly-UNLABELED series labels nothing meaningful |
| drift cap (RF-5) | Tight = rejects regime-definition instability early; loose = accepts drifting definitions that repaint slowly |

## 7. Pilot — funding/basis/carry (values post-DR, PRM-16)

Venue fee/funding mechanics constants (from DR citations only); per-candidate go/no-go (S1 passive
carry → S4 vol-gated → S3 continuation → S2 basis MR → S5 two-leg, S5 blocked until SM enforced);
position sizing bounds within RG envelope.

## 8. Standing rules

1. A model may PROPOSE analysis; only a human APPROVES a number. 2. Every approved number lives in
exactly one policy artifact and is re-pinned by consumers (digest-bound). 3. Changing a number =
new policy version + new digest — old evidence stays historical under the old digest, never
retro-edited. 4. Unapproved value in any input → artifact REJECTS (fail-closed), never defaults.
