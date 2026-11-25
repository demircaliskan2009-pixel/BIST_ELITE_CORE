# S1 own-history measurement doctrine adoption V1

## Decision and effect

Contract `S1_OWN_HISTORY_MEASUREMENT_DOCTRINE_ADOPTION_V1` records the human-approved decision
`S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1` (D1–D7). Its scope is FCD-13 `EHS_V1` and FCD-14
`PAPER_EXECUTION_QUALITY_V1` with HC-13a, HC-13b, HC-13c, HC-14a and HC-14b, for the governed paper path of
`LIMITED_S1_PAPER_V1`. It is a Tier III methodology adoption. It selects how the own-history readings U1–U4 and the
edge health score will be measured by a later, separately authorized construction. It supplies no measurement
producer, production authority or admission permission.

This record and its phase-map entry acquire doctrine authority only prospectively. That requires the protected
independent audit and the required exact-head CI, then the human's separate exact-head standard-merge authorization,
the merge, and post-merge verification of the accepted bytes. Until then the accepted main governs. Nothing here is
retroactive. It authorizes no earlier action and changes no earlier decision, seal or evidence.

Authority order, highest first. Between two safety rules the stricter applies.

| Rank | Authority | Role here |
|---|---|---|
| 1 | [PRDV4] (§0.3, §1.5, §1.6, §1.7, §1.21, §1.24, §1.28) | Formulas, weights, thresholds, the state machine and the cold-start exception. Prevails over this record |
| 2 | Accepted adoption records: the [Companion], [RECORD A], [RECORD B], the [D-A1 decision], incubation `r1` ([incubation adoption record]) and `HD-INC-AUTH-1` `r2` ([registry adoption record]) | Covered classes U1–U5, evaluation of a covered reading, incubation lifecycle, allocation envelope, registry bases |
| 3 | This record | Subordinate measurement methodology inside ranks 1–2. It relaxes none of them |
| 4 | Phase map §§12–20 | Describes accepted executable behavior. Unchanged by this record |

## Provenance

| Field | Value |
|---|---|
| Decision | `S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1`, original D1–D7 packet presented in the controller conversation immediately before the human approval |
| Base | `main` `56218b2013234df8cc0b582121d7ff2a2a0ac997`, tree `6c2c01f099515a491370363998c8c2b08cced509` |
| Approval date | 2026-11-25, relayed by the ChatGPT controller. The exact approval instant, message identifier and signature are unknown |
| Approver identity | The human user of the controller conversation. No repository mechanism authenticates it |
| Signature | None. Accepted main defines no signature mechanism, and this record claims none |
| Direct action grant | In the executing Claude Code session, at 2026-11-25T04:46:26.371Z, the human answered `GRANT exact scope` to the question quoted below |
| Transcript binding | Question record SHA-256 `66506e635bd5fd2670afdfec09464f76b27dc04bc71cb2cb196415c2ca428f8b`; answer record SHA-256 `6dddf2c296e0383bd9ba7730770407a23c1d060ff6e4f7ffa13c37f86e006509` (raw JSONL line bytes without the line feed; tool-use id `toolu_01LGjuXyXvMfdnV2XeF1fz9D` binds both) |
| Binding act | The human's separate exact-head standard-merge authorization of this change |

The direct human approval statement, verbatim as relayed:

```text
S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1 — D1-D7 APPROVE. Doctrine adoption preparation authorized. No production or merge authorization.
```

The action-grant question, verbatim:

```text
Do you grant this action scope? Base 56218b20 (tree 6c2c01f0). One isolated docs-only writer branch, docs/crypto-core-s1-own-history-measurement-doctrine-adoption-v1. Exactly two files: A docs/crypto_core/s1_own_history_measurement_doctrine_adoption_v1.md, and M paper_trading_phase_map.md (append §21 only). Applicable docs-only validation, one commit, a normal push, and one DRAFT PR. No ready-for-review, no merge, no branch deletion, no thread actions.
```

The selected option's description read: "Authorizes the isolated edit, the validation, one commit, a normal push and one
DRAFT PR, exactly as stated." The methodology approval and the action grant are separate acts. Neither grants
production, ready-for-review or merge authority.

## The decision text

The approved packet, word for word, line for line. Its `STATUS=PROPOSED_NOT_ADOPTED` line and its
`HUMAN_DECISION=APPROVE / AMEND / REJECT` line are historical parts of the original packet. The separate direct
statement above selects APPROVE, and the adoption conditions of this record, not the packet's STATUS line, decide when
the methodology takes effect.

```text
HUMAN_DECISION_PACKET

DECISION_ID=S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1
STATUS=PROPOSED_NOT_ADOPTED
BASE_SHA=56218b2013234df8cc0b582121d7ff2a2a0ac997

SCOPE
FCD-13 EHS_V1
FCD-14 PAPER_EXECUTION_QUALITY_V1
HC-13a / HC-13b / HC-13c
HC-14a / HC-14b

Preserve PRDV4, accepted incubation r1/r2,
RECORD A, RECORD B and all independent risk gates.

D1 — RETURN AND SHARPE METHODOLOGY

Use consecutive completed UTC daily net returns
from the edge's own authenticated governed-paper
valuation history.

r_d = NAV_end / NAV_start - 1

The valuation basis must be publication-visible,
positive, attributable to the same edge and free
of unaccounted capital flows.

Do not substitute portfolio-wide returns,
backtest history, another edge or missing days.

Use:
- 30 completed daily returns for Sharpe_30d.
- 90 completed daily returns for Sharpe_90d.
- Arithmetic mean.
- Sample standard deviation, denominator n-1.
- Annualization sqrt(365).
- PRDV4's stated return formula without introducing
  an additional risk-free-rate assumption.

Zero variance is BLOCKED.
No epsilon, clipping of the raw Sharpe ratio,
infinity or fabricated neutral score.

Insufficient qualifying own history may be
COLD_START_EXCEPTED only under the exact accepted
incubation contract.

A completed but mathematically undefined window
does not restore incubation coverage.

Reuse accepted deterministic arithmetic where
semantically equivalent. Do not modify legacy
paper Sharpe artifacts in place.

D2 — SIGNAL STABILITY

Use the actual strategy-defined scalar signal values
from authenticated, complete, PIT-visible
own-history evaluation records.

Use the PRDV4 30-day signal window.
Use sample standard deviation consistently.

CV_signal = sample_stddev / arithmetic_mean

If the mean is non-positive, the sample is
insufficient or signal semantics are unproven:
BLOCKED.

No confidence substitution, absolute-value
transformation, epsilon or fabricated sample.

A constant positive signal with a complete
qualified window has CV=0.

Preserve the existing PRDV4 stability-score formula.

D3 — EHS EVALUATION AND STATE MACHINE

Retain PRDV4 EHS component weights:
0.30 Sharpe
0.25 hit rate
0.25 drawdown
0.20 stability

Retain every accepted threshold, Family B drawdown
limit, allocation adjustment and alert formula.

Hit-rate sample below 10 uses the existing
PRDV4 neutral component of 0.5 only when the
small sample count is itself proven.

Use deterministic publication-time evaluation
at each relevant authenticated input change,
decision, window boundary and lifecycle deadline.

This is offline replay semantics, not a scheduler.

Reconstruct the ordered state history from
verified events.

The 48-hour DISABLED-to-WARNING hysteresis requires
proven continuous EHS >= 0.40 over the interval.

A missing or unproven interval cannot advance
the recovery clock.

Preserve the 30-day repeated-disable window,
14-day minimum quarantine and independent
walk-forward revalidation requirement.

No automatic recovery from missing evidence.
No self-certified revalidation.

D4 — GOVERNED-PAPER ORDER POPULATION

Count each unique engine-native governed-paper
order attempt once, on the same lineage and
exchange.

Include exposure-increasing and close-only
attempts, including protective orders.

Exclude:
- Signals and decisions refused before submission.
- Duplicate replay identities.
- Unsubmitted intents.
- Backtest or foreign-lineage orders.

An actual submitted but unfilled order remains
in the population with zero executed quantity,
once its outcome is conclusively known.

Do not count unresolved in-flight orders as
known completed observations.

The latest-N population must be identifiable.
An unresolved member blocks the reading;
it cannot be silently skipped in favor of an
older favorable observation.

D5 — FILL-RATE METHOD

For each completed qualifying order j:

f_j = filled_quantity_j / intended_quantity_j

Require:
intended_quantity_j > 0
0 <= f_j <= 1

Fill rate over the latest N qualifying orders:

FR_N = sum(f_j) / N

Use N=10 for NT-X02.
Use N=20 for PRDV4 execution conditions.

Partial fills contribute their actual fraction.
Unfilled completed attempts contribute zero.
Equal order weighting prevents a single large
order from dominating the observation window.

No quantity-weighted substitution.
No successful-order-only denominator.
No rounding before threshold comparison.

If fewer than N qualifying observations exist,
apply only the accepted U3/U4 incubation rules.

Otherwise the ordinary reading applies.

Retain every PRDV4 execution threshold.
At overlapping threshold boundaries apply the
more restrictive classification.

Missing exchange-health, API-error or maintenance
evidence remains independently BLOCKED.

D6 — SHARED SAFETY AND PROVENANCE

One verified own-history measurement authority.
No caller-supplied EHS, fill rate or observation
count can establish admission authority.

Distinguish:
- Proven insufficient history.
- Missing or unproven history.
- Complete but mathematically undefined history.
- Defined PASS.
- Defined FAIL.

Only the first category may qualify for the
specific approved incubation exception.

FAIL dominates COLD_START_EXCEPTED.
No synthetic construction evidence becomes
production qualification.

Preserve NT-D01, HD-07, X-H1, M1, D1, C1-C9,
DEC-1 and every other unresolved prerequisite.

Do not infer INCUBATION_MEMBER from a partial
measurement or incomplete candidate universe.

D7 — ACCEPTANCE AND AUTHORIZATION BOUNDARY

This decision selects methodology for subsequent
doctrine adoption and separately authorized
construction only.

Before adoption, reconcile these decisions with
all accepted source clauses and identify any
remaining material ambiguity, including signal
population, temporal completeness and quarantine.

Do not silently resolve a conflicting doctrine
or invent an unavailable producer.

No production policy approval.
No implementation authorization.
No commit, push, PR or merge authorization.
No real paper, readiness, capital, shadow or live.

A separate protected docs-only adoption must
precede product construction.

HUMAN_DECISION=APPROVE / AMEND / REJECT
```

In D6, "M1, D1" names the pending source-qualification and venue-fact dependencies ([Companion] §12.2), not decision
clause D1.

## Relation to accepted doctrine

Each clause applies accepted authority and relaxes none of it.

| Clause | Accepted authority it applies | Effect |
|---|---|---|
| D1 | [PRDV4] §1.6 Component 1 (`Sharpe_30d = mean / sigma x sqrt(365)`, the S_sharpe clamp, DECAY_ALERT); §1.21 PAPER_INCUBATION_V1 coverage of Sharpe_30d and Sharpe_90d; [Companion] §3.3 U1/U2, §3.4, §3.5; [incubation adoption record] F-4; [RECORD A] LR-3 | Selects the estimator: daily NAV return of the edge, 30 and 90 consecutive completed UTC days, arithmetic mean, sample standard deviation (n−1), sqrt(365), no risk-free term. Zero variance stays BLOCKED (the HC-13a convention). The PRDV4 S_sharpe clamp is the score formula and stays; D1 forbids clipping the raw ratio only |
| D2 | [PRDV4] §1.6 Component 4 | Selects the sample standard deviation and the scalar signal population source. A non-positive mean is BLOCKED. That is stricter than a literal reading of the PRDV4 formula, under which a negative CV would give S_stability = 1 |
| D3 | [PRDV4] §1.6 weights, components, α_edge, state machine and hysteresis; §1.7 rebalance and BOOST/DE-WEIGHT; §1.21 NT-E01, NT-E02, NT-E04; [Companion] §3.4 and §4.1 | Keeps every PRDV4 constant. Selects event-time replay at authenticated input changes, decisions, window boundaries and deadlines. It does not decide `MONITORING_CADENCE` ([RECORD B]), which stays pending |
| D4 | [PRDV4] §1.5 Execution Conditions ("last 20 orders"); §1.21 NT-X02 ("Last 10 orders", per exchange) and the lineage's "last-10 and last-20 governed-paper order fill rates on the exchange"; [Companion] §3.3 U3/U4, §3.6 (HC-14a) | Exits, close-only and protective orders are orders for FCD-14 (HC-14a). Pre-submission refusals, duplicates, unsubmitted intents and foreign orders are not |
| D5 | [PRDV4] §1.5 Execution Conditions and §1.21 NT-X02 thresholds | Selects the equal-weighted mean of per-order fill fractions over the latest 10 or 20 orders. Thresholds unchanged |
| D6 | [PRDV4] §0.3 cold-start exception and §1.21; [Companion] §3.4 and §9.1; [incubation adoption record] (FAIL dominates, own history only); [registry adoption record] O1 | One verified authority. Five evidence categories, of which only proven insufficient history can be excepted |
| D7 | [Companion] §12.3 | Methodology only. Construction, policy, production and merge stay separately gated |

The incubation attempt and the order observation stay distinct. An attempt is an entry admitted on the incubation
basis, counted at admission whether or not it fills, and bounded by `A_max = 21` ([incubation adoption record]). An
order observation is a submitted order whose outcome is conclusively known (D4). Counting exits and protective orders
in the fill-rate population does not change `A_max`, `T_max = 91` UTC days or `W_INC = 0.08`.

**Execution boundaries, by arithmetic on D5 and [PRDV4].** For the §1.5 fill leg: `FR_20 > 0.90` is OPTIMAL and
`FR_20 = 0.90` is DEGRADED, because OPTIMAL needs more than 90%. Only `0.70` lies in two closed ranges, DEGRADED
`[70%, 90%]` and IMPAIRED `[50%, 70%]`, so it takes the more restrictive class, IMPAIRED. `FR_20 = 0.50` is IMPAIRED,
because HALTED needs less than 50%, and `FR_20 < 0.50` is HALTED. NT-X02 fails only on
`FR_10 < 0.50`, so `FR_10 = 0.50` does not trigger it. The latency and API-error legs stay outside this decision (X-H1).

**Scope identifiers.** HC-13a is the zero-variance Sharpe convention ([Companion] §3.7; [incubation adoption record]
F-4; [RECORD A] LR-3), which D1 settles as BLOCKED. HC-14a is whether exits count as orders ([Companion] §3.6), which
D4 settles for FCD-14. The accepted repository does not hold the decision-register wording of HC-13b, HC-13c or
HC-14b. This record disposes of them as members of the approved scope, under D1–D7 as written. It reconstructs no
register text and asserts no clause-level mapping for them. FCD-08's turnover reading ([RECORD B]) is unchanged.

## Forward-only disposition

The texts below keep their bytes and their meaning at their own dates. This table states their status after the
adoption conditions hold.

| Source passage | Status there | After this adoption |
|---|---|---|
| [Companion] §12.1, row `HC-13a..c, HC-14a..b, HC-16a, HC-16c, HC-16d` | Pending | HC-13a..c and HC-14a..b: methodology selected by D1–D7. HC-16a, HC-16c and HC-16d: pending, unchanged |
| [Companion] §12.1, row `FCD-01..17`, and §11.2, row `Other` | Pending | FCD-13 and FCD-14: methodology selected, with the residual items below. Every other FCD and HD-07: unchanged |
| [Companion] §0.5, allocation membership row (EHS and Sharpe_30d unprovable while FCD-13 is pending) | UNKNOWN | Still UNKNOWN and every weight BLOCKED: the method is selected, but no producer exists |
| [Companion] §3.7 and [incubation adoption record] F-4 (zero-variance window BLOCKED pending HC-13a) | BLOCKED pending | BLOCKED under the approved convention. Incubation supplies no exception for a complete window |
| [RECORD A] LR-3 (FCD-13, HC-13a, item 1.8) | Pending | Consistent. A fully idle 30-day window stays BLOCKED |
| [RECORD B] pending table, row `FCD-13, FCD-14 / HC-14a, HD-07` | Pending, unchanged | FCD-13, FCD-14 and HC-14a: methodology selected. HD-07: unchanged |
| [registry adoption record], pending prerequisites (FCD-13, HC-13a, HC-14a/b) | Pending | Methodology selected. Producers absent, so the gate is unchanged in effect |
| Phase map §15, pending list (FCD-05, FCD-13, FCD-14, HD-07) | Pending | FCD-13 and FCD-14 selected. FCD-05 and HD-07 unchanged |
| Phase map §20, "U1-U4 have no producer" | Accepted construction | Unchanged. U1–U4 still have no producer, so no record selecting them graduates or yields an exception |

The blocker identities `INCUBATION_FUTURE_APPROVAL_REWRITES_PAST`,
`INCUBATION_KNOWN_SIGNAL_BLOCK_DELAYED_UNTIL_EFFECTIVE_TIME` and `INCUBATION_ACTIVE_WITH_EMPTY_FILL_WINDOW` (phase map
§20) stay closed by the accepted construction and are not reopened here.

## Approved methodology and remaining items

Classes: `RESOLVED_METHODOLOGY`, `MISSING_CONSTRUCTION`, `PENDING_HUMAN_DECISION`, `BLOCKED_EXTERNAL` and
`UNPROVEN_PROVENANCE`. A pending, missing, external or unproven item blocks every reading that depends on it. No item
is resolved by default, by a proxy or by the absence of a decision.

| Id | Item | Class |
|---|---|---|
| M-1 | Daily return `r_d`, NAV basis conditions, 30/90 completed UTC days, mean, n−1, sqrt(365), no risk-free term (D1) | RESOLVED_METHODOLOGY |
| M-2 | Zero variance BLOCKED; no epsilon, clipping, infinity or neutral score (D1; HC-13a) | RESOLVED_METHODOLOGY |
| M-3 | `CV_signal` with sample standard deviation; non-positive mean, insufficient sample or unproven semantics BLOCKED; constant positive complete window gives CV = 0 (D2) | RESOLVED_METHODOLOGY |
| M-4 | EHS weights, thresholds, α_edge, alerts; S_hitrate = 0.5 only on a proven count below 10 (D3) | RESOLVED_METHODOLOGY |
| M-5 | Event-time replay; hysteresis only on proven continuous EHS >= 0.40; a gap never advances the clock; no automatic recovery; no self-certified revalidation (D3) | RESOLVED_METHODOLOGY |
| M-6 | Order population inclusion and exclusion; unresolved members block (D4; HC-14a for FCD-14) | RESOLVED_METHODOLOGY |
| M-7 | `FR_N` equal-weighted, N = 10 and 20, no rounding before comparison, the restrictive boundary class (D5) | RESOLVED_METHODOLOGY |
| M-8 | One verified authority; five evidence categories; FAIL dominates (D6) | RESOLVED_METHODOLOGY |
| P-1 | **Signal population.** Which evaluation records form `signal_values_30d`, their cadence, the completeness criterion of the window, and any minimum sample beyond mathematical definability (named in D7). Blocks S_stability and so EHS | PENDING_HUMAN_DECISION |
| P-2 | **Temporal completeness.** What evidence proves that an interval holds no unobserved input change, for every window and the 48-hour hysteresis, and the order among equal-instant inputs when a transition depends on it (named in D7). Until decided, a reading that differs between orderings or rests on an unproven interval is not proven | PENDING_HUMAN_DECISION |
| P-3 | **State machine start and quarantine** (named in D7). The state before the first defined EHS; whether the transition that enters QUARANTINE counts as a DISABLED transition; the state after a 14-day quarantine with a passing revalidation; which artifact qualifies as the independent walk-forward revalidation. Blocks NT-E02, E_active and allocation | PENDING_HUMAN_DECISION |
| P-4 | **Order submission boundary.** The one engine's intent is "never an order", and it has no submission event. Its fill outcomes are `FILLED`, `PARTIALLY_FILLED`, `REJECTED` (both market-gate rejections and governed fill-time refusals), `UNFILLED`, re-attempted protective orders and an attempt left in flight at the evaluation end. Which of these are submitted orders, which quantity is `intended_quantity` (the requested quantity after a close-only clamp, or the target delta), and the order key of the latest-N window are not selected. Blocks U3, U4, NT-X02 and the §1.5 fill leg | PENDING_HUMAN_DECISION |
| P-5 | **Drawdown input.** No accepted text defines the peak reference or equity basis of an edge's `DD_current`. D3 keeps the formula and the per-edge limits only. Blocks S_drawdown and so EHS | PENDING_HUMAN_DECISION |
| P-6 | **Hit-rate trade population.** Which trades enter `N_total,30d` and `N_win,30d` (the closing and knowledge instants, and a zero-net trade), and the same for `HR_90d` in HIT_RATE_ALERT. The PRDV4 §1.21 win/loss definition is written for Kelly coverage and is not extended here. Blocks S_hitrate, including the proof of a count below 10 | PENDING_HUMAN_DECISION |
| C-1 | A per-edge governed-paper daily NAV series with capital-flow attribution and per-day knowledge instants | MISSING_CONSTRUCTION |
| C-2 | Sharpe_30d and Sharpe_90d evidence over C-1. The legacy evidence covers 30 buckets of a caller-supplied normalized index, renders at scale 18 and serves Stage-4 review only. No rounding convention for a Sharpe threshold is approved, so a classification is decided on the exact value. A rendering that could decide a threshold needs a human decision | MISSING_CONSTRUCTION |
| C-3 | Scalar signal history (after P-1) | MISSING_CONSTRUCTION |
| C-4 | EHS and state-history replay authority (after P-2, P-3, P-5 and P-6) | MISSING_CONSTRUCTION |
| C-5 | Order-observation ledger and fill-rate producer (after P-4) | MISSING_CONSTRUCTION |
| C-6 | U1–U4 coverage and per-reading graduation inside the incubation authority | MISSING_CONSTRUCTION |
| C-7 | Rule-set, seal and allocation consumers of the readings | MISSING_CONSTRUCTION |
| E-1 | X-H1 exchange health (latency, API error, maintenance; NT-X01, NT-X04); M1 source qualification, including the mark archive; D1 venue facts | BLOCKED_EXTERNAL |
| E-2 | Authentic strategy-defined scalar signal semantics for the S1 edge | UNPROVEN_PROVENANCE |
| E-3 | The registry bases A4–A6 and the O2 signed-decision requirement ([registry adoption record]) | UNPROVEN_PROVENANCE |
| G-1 | HD-07, HC-16a/c/d, KD-7 at `n_w = 100`, FCD-05, FCD-17 and `H^(e)`, `MONITORING_CADENCE`, C1–C9, DEC-1, risk-policy production approval, every individual incubation record and policy artifact | Independent gates, unchanged |

## Construction acceptance cases

These cases state the outcome D1–D6 and accepted doctrine already require. They are acceptance criteria for a later
construction, not new doctrine. Where a case depends on a pending item, it names the item, and the dependent reading
stays BLOCKED until that item is decided.

**Returns and Sharpe (D1).**

| Case | Required outcome |
|---|---|
| 30 or 90 consecutive completed UTC days of the edge's own verified NAV | Defined reading, computed as M-1. DECAY_ALERT needs both Sharpe readings defined |
| Partial genesis UTC day | Not a completed UTC day, so never counted. The engine's own start-of-day NAV is unavailable on a partial first day |
| A missing or unverifiable day inside the window | Missing or unproven history: BLOCKED. Never skipped, never substituted, and never proven insufficient history |
| A completed day whose NAV_end awaits a funding settlement's publication | Unproven at that instant: BLOCKED, not insufficient. It becomes known only at the publication of its last input |
| Negative or zero daily returns | Ordinary members of the sample |
| Positive constant returns | Zero variance: BLOCKED |
| A capital flow not accounted for | BLOCKED. No adjustment is invented |
| Another edge or lineage, portfolio-wide or backtest returns | Never own history. A series that mixes them is BLOCKED, not insufficient |
| U1 or U2 completed, later window undefined | Stays ordinary and BLOCKED. Coverage never returns ([incubation adoption record]) |
| Later valuation knowledge | Never rewrites an earlier reading or decision. Each reading binds only knowledge visible at its own instant |

**Stability and EHS (D2, D3).**

| Case | Required outcome |
|---|---|
| Positive mean, complete qualified window | CV defined; S_stability by the PRDV4 formula |
| Zero or negative mean | BLOCKED |
| Constant positive signal, complete qualified window | CV = 0 and S_stability = 1 |
| Missing records or unknown signal semantics | BLOCKED (P-1, E-2) |
| Confidence, absolute-score or valid-signal-ratio proxies, as in `src/crypto_core/edge_health/tracker.py` | Never EHS evidence |
| Proven trade count below 10 | S_hitrate = 0.5. An unproven count is BLOCKED (P-6) |
| Drawdown at or above the edge's PRDV4 limit | S_drawdown = 0 and DISABLED, which is FAIL whatever Sharpe becomes ([Companion] §3.4), once P-5 defines the measurement |

**State machine (D3).**

| Case | Required outcome |
|---|---|
| Unknown initial state | BLOCKED (P-3). No INITIALIZING state or allocation factor is adopted |
| 48-hour recovery interval with a gap or unproven span | The recovery clock does not advance over it. No recovery |
| Sparse observations of EHS >= 0.40 | Never prove continuity on their own (P-2) |
| Equal-instant input changes | Decided by P-2. A transition that differs between orderings is not proven |
| A second DISABLED transition within 30 days | QUARANTINE per [PRDV4] §1.6 |
| 14 days elapsed without the independent revalidation | Stays locked out |
| Revalidation produced by the edge's own run or caller text | Not accepted |

**Execution quality (D4, D5).**

| Case | Required outcome |
|---|---|
| Decision or signal refused before submission | Excluded. The engine mapping of "submitted" is P-4 |
| Submitted order, conclusively unfilled | Included with `f_j = 0` |
| Partial or full fill | `f_j` = executed quantity over intended quantity, exact, from quantities, never from a rendered ratio |
| Close-only or protective order | Included |
| Unresolved in-flight order inside the latest N | The reading is BLOCKED. It is never skipped and never counted as insufficient history |
| Duplicate replay identity | Counted once. Under an incubation record, a duplicate or out-of-order observation terminates the record ([incubation adoption record]) |
| Distinct identities at the same nanosecond | Distinct observations. Their order in the window is decided by P-4 |
| Another lineage or exchange, or a backtest order | Excluded |
| Latest 10 and latest 20 | NT-X02 and the §1.5 fill leg respectively |
| Unequal intended quantities | Equal order weighting. No quantity weighting |
| Exactly 0.50, 0.70 and 0.90 | As in "Execution boundaries" above |
| Fewer than N completed observations, none unresolved | Proven insufficient history. `COLD_START_EXCEPTED` only under the accepted U3/U4 incubation rules ([incubation adoption record]); otherwise BLOCKED |
| Simulated fill rates | Never evidence of venue health. X-H1 stays a separate gate |

## Incubation and allocation trace

| Reading | Consumers | After this adoption |
|---|---|---|
| U1 Sharpe_30d | S_sharpe, EHS, NT-E01, NT-E02, NT-E04, α_edge, E_active, selection by EHS × Sharpe_30d, the allocation numerator, BOOST | Method selected (D1). No producer; BLOCKED |
| U2 Sharpe_90d and DECAY_ALERT | DE-WEIGHT and BOOST | Method selected (D1). No producer; BLOCKED |
| U3 FR_10 | NT-X02 | Method selected (D4, D5), subject to P-4. No producer; BLOCKED |
| U4 FR_20 | The §1.5 fill leg, A_e, FB-ACTIVATION | Method selected (D4, D5), subject to P-4. No producer; BLOCKED |
| EHS components other than Sharpe | S_hitrate, S_drawdown, S_stability | Not covered by incubation. Blocked by P-1, P-5 and P-6 |

`INCUBATION_MEMBER` still requires exactly one candidate, U4 as the only non-PASS leg of A_e and U1 as the only
undefined EHS input, each `COLD_START_EXCEPTED` and neither FAIL ([Companion] §4.1; [incubation adoption record]). It
therefore also needs S_hitrate, S_drawdown and S_stability defined, the latency and API legs proven (X-H1) and the
candidate universe proven complete. No partial EHS, partial activation proof or assumed universe grants allocation.
The bounds of 21 attempts, 91 UTC days and 0.08 of NAV are unchanged.

## Construction dependency matrix

| Decision | Required producer | Verified input | Consumer | Acceptance test | Residual gate |
|---|---|---|---|---|---|
| D1 | Per-edge daily NAV series and Sharpe evidence (C-1, C-2) | The engine's UTC-day-boundary valuations, fills, fees and published settlements of the sealed lineage | U1, U2, EHS, allocation | The returns table above | M1 mark archive; C2's G and H; the registry bases |
| D2 | Scalar signal history (C-3) | Authenticated, PIT-visible evaluation records | S_stability | The stability table above | P-1, E-2 |
| D3 | EHS and state replay (C-4) | C-2, C-3, the trade and equity records | NT-E01, NT-E02, NT-E04, α_edge, E_active | The state machine table above | P-2, P-3, P-5, P-6 |
| D4, D5 | Order-observation ledger and fill rate (C-5) | The engine's intents, fill outcomes and protective attempts | U3, U4, NT-X02, A_e, FB-ACTIVATION | The execution table above | P-4, X-H1 |
| D6 | One public verifier over C-1..C-5 (C-6) | The sealed lineage, recomputed by public serializers | Incubation authority, entry rule set, seal | Each of the five categories on its own fixture, FAIL dominating | A4–A6, O2, production approvals |

Arithmetic that a construction may reuse without changing its semantics: the exact-fraction mean and sample variance,
sqrt(365) annualization and zero-variance refusal of `paper_sharpe_evidence.py`; the exact `(end - start) / start`
bucket return of `paper_daily_return_series_evidence.py`; and the requested and filled quantities, outcomes and
UTC-day-boundary valuations of `historical_execution_economics.py`, as inputs only. Reuse of arithmetic is not reuse of
authority. None of these artifacts carries per-edge, publication-visible, flow-attributed own history, and they are not
modified in place. `paper_sleeve_performance_evidence.py` is per sleeve on legacy session metrics and is not an
own-history source. The attempt ledger of `governed_paper_incubation_authority.py` counts attempts, not orders. The
edge-health tracker is not reused: it computes float proxies with an epsilon and an INITIALIZING state. No parallel EHS
or economics engine is proposed.

## Admission effect and non-claims

- **Admission effect: none.** This change edits no code, test, rule set, schedule, seal, policy artifact, approval
  table or registry. Every governed S1 entry stays refused as before.
- **Not claimed:** a Sharpe, EHS, signal-stability or fill-rate measurement; a producer; an ACTIVE record;
  `COLD_START_EXCEPTED` or `INCUBATION_MEMBER` for any edge; venue health; construction readiness; Stage-4
  eligibility or credit; readiness; profitability or edge.
- **No authority** for implementation, production policy or approval-table entries, registry rows, record approvals,
  qualification, real paper (`REAL_PAPER_EXECUTION`), shadow, live, orders, fills, positions, PnL or capital, a
  scheduler or monitor, readiness or connector transitions, ready-for-review or merge.
- No historical FCD proposal is adopted by this record, and the decision's own approval does not approve P-1..P-6.

## Verification of this adoption

| Check | Requirement |
|---|---|
| Decision text | The decision block equals the packet's text between its begin and end markers, line for line |
| Approval and grant | The relayed approval statement and the direct action grant are quoted verbatim, with the grant's transcript record digests |
| Doctrine | Each clause maps to accepted authority. No value, threshold or gate is relaxed, and each residual item is classified |
| Scope | The change adds this record and phase-map §21. No other byte changes, and no source, test, script, setup or PRDV4 change |
| Format | `git diff --check` is clean, and every relative link resolves |

[PRDV4]: ../PRDV4_MULTI_MARKET_CRYPTO.md
[Companion]: s1_approved_doctrine_adoption_v1.md
[RECORD A]: s1_kelly_class_completion_amendment_v1.md
[RECORD B]: s1_native_risk_measurement_doctrine_adoption_v1.md
[D-A1 decision]: s1_kelly_da1_doctrine_adoption_v1.md
[incubation adoption record]: s1_paper_incubation_doctrine_adoption_v1.md
[registry adoption record]: s1_incubation_authority_registry_doctrine_adoption_v1.md
