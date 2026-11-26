# S1 own-history residual doctrine adoption V1

## Decision and effect

Contract `S1_OWN_HISTORY_RESIDUAL_DOCTRINE_ADOPTION_V1` records the human-approved decision
`S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1` (P-1 to P-6). The decision resolves, as one closure, the six items that
the [own-history adoption record] left as `PENDING_HUMAN_DECISION`: the signal population, temporal completeness and
equal-instant order, the state machine's start and quarantine, the order submission boundary, the drawdown input and
the hit-rate trade population. It adds a shared numerical and authority contract and a list of required future
acceptance cases. Its scope is the governed paper path of `LIMITED_S1_PAPER_V1`. It is a Tier III methodology adoption:
it selects how a later, separately authorized construction will measure these readings. It supplies no producer,
production authority or admission permission, and this record makes no methodology choice of its own.

This record and its phase-map entry acquire doctrine authority only prospectively. That requires the protected
independent audit and the required exact-head CI, then the human's separate exact-head standard-merge authorization,
the merge, and post-merge verification of the accepted bytes. Until then the accepted main governs. Nothing here is
retroactive. It authorizes no earlier action and changes no earlier decision, seal or evidence.

Authority order, highest first. Between two safety rules the stricter applies.

| Rank | Authority | Role here |
|---|---|---|
| 1 | [PRDV4] (§0.3, §1.5, §1.6, §1.7, §1.21, §10.3) | Formulas, weights, thresholds, the state machine, hysteresis, the NO-TRADE conditions and the cold-start exception. Prevails over this record |
| 2 | Accepted adoption records: the [own-history adoption record] (D1–D7), the [Companion], [RECORD A], [RECORD B], the [D-A1 decision], incubation `r1` ([incubation adoption record]) and `HD-INC-AUTH-1` `r2` ([registry adoption record]) | Own-history methodology D1–D7, covered classes U1–U5, the incubation lifecycle, the allocation envelope, the registry bases and the Kelly closed-trade identity |
| 3 | This record | Subordinate methodology inside ranks 1–2. It relaxes none of them |
| 4 | Phase map §§12–21 and the accepted engine and verifiers they describe | Executable behavior. Unchanged by this record |

## Provenance

| Field | Value |
|---|---|
| Decision | `S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1`, the original P-1 to P-6 packet, relayed by the ChatGPT controller in the implementation contract `S1_OWN_HISTORY_RESIDUAL_DOCTRINE_ADOPTION_V1` |
| Base | `main` `ec70cd53ec9941b787c02a47e5b77b212ac85911`, tree `57eed5936d3854ecdbeb534b75a6bf1e7741ba6a` (the packet's own `BASE_SHA` and `BASE_TREE`) |
| Approval date | 2026-11-26, relayed by the ChatGPT controller. The exact approval instant, message identifier and signature are unknown |
| Approver identity | The human user of the controller conversation. No repository mechanism authenticates it |
| Signature | None. Accepted main defines no signature mechanism, and this record claims none |
| Relay binding | The controller packet is the opening user record of the executing Claude Code session (2026-11-26T03:50:57.885Z), raw JSONL line SHA-256 `1eaecba22a5c79d1485dde21f882ddbf8d6e9272e06da0d3a98d30d015cde27a` |
| Direct action grant | In the same session, at 2026-11-26T03:53:15.196Z, the human answered `GRANT exact scope` to the question quoted below |
| Transcript binding | Question record SHA-256 `964108e09c76b66a2b9642ed901fe4b81d368c3acb92ea9cb9838cdb7344fa8f`; answer record SHA-256 `b5833aef8e277edec1b719d52ba5e28f48f9e8c853329a3acc1a3c4d0ad19e61` (raw JSONL line bytes without the line feed; tool-use id `toolu_01DXf4Pd9TJPnz6odRbbxZQK` binds both). The same question record also carries a separate one-task effort question; that runtime matter belongs to the handoff, not to doctrine |
| Binding act | The human's separate exact-head standard-merge authorization of this change |

The direct human approval statement, verbatim as relayed:

```text
S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1 — P-1 through P-6 APPROVE. Doctrine adoption preparation authorized. No product implementation, production approval, publication or merge authorization.
```

The action-grant question, verbatim:

```text
Action grant for S1_OWN_HISTORY_RESIDUAL_DOCTRINE_ADOPTION_V1: base ec70cd53ec9941b787c02a47e5b77b212ac85911; one branch docs/crypto-core-s1-own-history-residual-doctrine-adoption-v1 created in writer worktree tau_20261124; exactly two files (new docs/crypto_core/s1_own_history_residual_doctrine_adoption_v1.md, and paper_trading_phase_map.md section 22 append-only); docs-only validation; one scoped commit; normal push; one DRAFT PR. No ready-for-review, merge, branch deletion, review submission or thread resolution. Do you grant this exact scope?
```

The selected option's description read: "Authorizes exactly the listed actions for this task only. It is not a methodology approval and grants no merge authority." The methodology approval and the action grant are separate
acts. Neither grants production, ready-for-review or merge authority.

## The decision text

The approved packet, word for word and line for line, between its begin and end markers. The approval covers this
complete text. Its `STATUS=PROPOSED_NOT_ADOPTED` line, its `AUTHORIZATION_BOUNDARY` section and its
`HUMAN_DECISION=APPROVE / AMEND / REJECT` line are historical parts of the original packet. The separate direct
statement above selects APPROVE, and the adoption conditions of this record, not the packet's STATUS line, decide when
the methodology takes effect.

```text
HUMAN_DECISION_PACKET

DECISION_ID=S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1
STATUS=PROPOSED_NOT_ADOPTED
BASE_SHA=ec70cd53ec9941b787c02a47e5b77b212ac85911
BASE_TREE=57eed5936d3854ecdbeb534b75a6bf1e7741ba6a

AUTHORITY
PRDV4
S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1
Accepted adoption PR451
Accepted incubation r1/r2 and PR450
RECORD A, RECORD B and D-A1

SCOPE
Resolve P-1 through P-6 of the accepted
own-history measurement adoption record.

Preserve every previously approved method,
threshold, risk bound and independent authority.

LIMITED_S1_PAPER_V1 only.

P-1 — AUTHENTIC SIGNAL POPULATION

For passive_funding_carry.v1, select the exact
signed arithmetic mean of the strategy's latest N
visible final funding rates as the strategy scalar.

N remains the approved strategy parameter
final_funding_lookback_count.

Reconstruct the exact scalar from verified
strategy inputs. Do not use a rounded feature_mean
for threshold decisions.

Include every scheduled authenticated strategy
evaluation, including NO_ACTION, HOLD and EXIT.

Admission refusals do not remove the evaluation
from the signal population.

Use the existing H2 evaluation schedule:
one evaluation per distinct publication coordinate
max(available_at_ns, finalized_at_ns).

No artificial additional signal samples.

At evaluation coordinate t, use the trailing
30-day window (t - 30 UTC days, t], restricted
to this lineage's own history from genesis G.

Before G + 30 days, an inception-truncated window
is permitted for signal stability only when its
entire eligible history is proven complete.

This does not shorten the 30/90 completed-day
Sharpe windows of D1.

Require at least two mathematically defined
scalar observations.

An undefined scheduled evaluation within the
applicable window blocks the stability reading.
Do not silently discard it.

No action-only sampling, confidence proxy,
absolute-value transformation, epsilon, carry
forward or fabricated observations.

If the signed sample mean is non-positive,
S_stability remains BLOCKED under accepted D2.

A negative-mean funding regime is not made
eligible by changing the signal's sign.

P-2 — TEMPORAL COMPLETENESS AND EVENT ORDER

Use one knowledge-time timeline ordered by:

(timestamp_ns, accepted_engine_phase, native_sequence)

Preserve HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES:

FUNDING
PROTECTIVE
DECISION
FILL
UTC_DAY_BOUNDARY
EVALUATION_END

Do not change legacy engine ordering.

Source publications become known only at their
verified publication/availability coordinates.

At DECISION, read preceding phases and the
current authenticated strategy evaluation,
but not this decision's resulting fills.

Resolve simultaneous inputs atomically within
their applicable phase.

Where native sequence affects the result, derive
it from authenticated engine/source ordering.
Do not use arbitrary digest sorting to invent
economic causality.

A complete interval requires:
- Verified lineage and initial anchor.
- Authenticated source coverage for each required
  input.
- Every expected observation or a proven valid
  absence.
- Verified sequence continuity where applicable.
- Every deterministic event and window boundary.
- Qualified knowledge-time evidence of coverage.

No events observed does not prove no events occurred.

Sparse equal-valued observations do not establish
continuous EHS.

For any interval with complete input coverage,
derive the piecewise state from the one engine and
measurement authority.

Recompute at input changes, decision instants,
window expiration boundaries and lifecycle deadlines.

An unknown interval interrupts the continuous
48-hour hysteresis proof. Restart the continuous
proof when adequate coverage resumes.

Do not treat an unknown interval as safe,
accumulate disjoint recovery spans or bridge gaps.

An observation learned later may influence future
readings at its actual knowledge coordinate.

It may not rewrite a prior decision, seal,
graduation event or admission prefix.

Preserve X1 prefix stability.

No real-time monitor, scheduler or auto-loop.

P-3 — EHS STATE MACHINE AND QUARANTINE

Keep the four PRDV4 states:
ACTIVE
WARNING
DISABLED
QUARANTINE

Before a state is established, record
STATE_NOT_ESTABLISHED as an evidence status,
not a fifth doctrinal FSM state.

No default ACTIVE or WARNING state.

The first fully defined EHS establishes the
ordinary state using the accepted thresholds,
provided the earlier lifecycle proof contains no
unresolved or binding disable/quarantine condition.

A proven Family B drawdown breach establishes
DISABLED even when another EHS component is
undefined.

Known FAIL conditions retain precedence.

If an undefined state/check depends solely on
the approved insufficient U1 history, apply only
the existing COLD_START_EXCEPTED rules.

Do not manufacture ordinary PASS or ACTIVE
from a partial EHS.

Unrelated missing history, lifecycle uncertainty
or incomplete provenance remains BLOCKED.

Ordinary state transitions:
- EHS >= 0.70: ACTIVE, unless recovery or
  quarantine restrictions apply.
- 0.30 <= EHS < 0.70: WARNING, subject to
  recovery restrictions.
- EHS < 0.30 or the applicable proven drawdown
  disable condition: DISABLED.

Once DISABLED, no direct transition to ACTIVE.

Recovery requires proven continuous
EHS >= 0.40 for at least 48 hours and every
independent applicable recovery condition.

The first permitted recovery transition is WARNING.
Subsequent evaluations may reach ACTIVE under
the ordinary rules.

Count each genuine new disable episode once.

Repeated observations during the same disabled
episode do not create additional transitions.

Use the trailing interval
(t - 30 UTC days, t] for disable episode counting.

The second distinct disable episode inside that
interval enters QUARANTINE and counts as the
second episode.

QUARANTINE is locked for at least 14 UTC days
from its entry.

Expiry alone never releases quarantine.

Require a fresh, independently re-proven
walk-forward revalidation through the accepted
EF-5/EF-6/EF-7 verification chain.

Bind it to the exact lifecycle subject, strategy,
parameters and applicable immutable authority.

The new OOS evidence must be after the triggering
disable and known before the release decision.

Previously consumed validation evidence,
self-reports and digest-only assertions cannot
release quarantine.

Require separate attributable, digest-bound
governance authorization for release.

After minimum duration, valid revalidation and
release authority, return to DISABLED recovery
status, not ACTIVE.

This administrative release is not a new
disable episode.

Require a new continuous 48-hour recovery proof
before WARNING.

EHS recovery never clears an independent EF-8
disable, quarantine or re-admission restriction.

EF-8 remains separately verified under its own
accepted authority and timing rules.

No reset of negative history, incubation bounds
or previously completed coverage.

P-4 — ENGINE-NATIVE SUBMISSION OBSERVATION

Introduce a logical simulated-submission event
within the one accepted economics engine.

This is a deterministic paper-model observation,
never a venue order or operational submission.

The submission boundary occurs when a valid
positive-quantity intent or protective attempt:

1. Passes every applicable pre-submission
   authority and intent-time gate.
2. Has its actual engine-native requested
   quantity fixed.
3. Is accepted into the engine's pending
   execution path.

Before that boundary, no order observation exists.

Use requested_quantity after any applicable
close-only clamp and approved quantity-grid
normalization.

Do not use the original unconstrained target delta
as the fill-rate denominator.

Bind each logical submission to:
- Lineage and exchange identity.
- Engine-native intent/attempt/child identity.
- Submission coordinate.
- Exact requested quantity.
- Canonical engine submission sequence.
- Relevant verified authority.

Count entry, reduction, exit and protective
submissions on the same basis.

A pre-submission refusal is excluded.

After submission:
- Full fill: fraction 1.
- Partial fill: actual filled/requested fraction.
- Terminal market rejection: fraction 0.
- Terminal governed fill-time refusal: fraction 0.
- Conclusive cancellation without fill: fraction 0.
- Unresolved pending execution: outcome UNKNOWN.

The classification depends on the proven
submission boundary and terminal state, not
a legacy outcome label or reason string alone.

A submitted order cannot be deleted from the
population because later governance refused it.

A pending order at evaluation end is not
automatically a terminal zero-fill observation.

Carry its identity and unresolved state across
day seals and replay extensions.

Each genuinely new protective retry that crosses
the submission boundary is a separate observation.

Replay of the same attempt is never a new order.

Order the latest-N population by the verified
engine submission coordinate and native sequence,
not fill time or completion time.

Any unresolved member of the latest-N population
blocks its defined reading.

Never skip an unresolved member to recover an
older successful fill.

Preserve D5 equal-order-weighted fill fractions.

Keep incubation admission attempts separate from
submitted-order observations.

No additional fill model, synthetic retry creation,
order generation or modified execution economics.

Construction fixtures may prove the semantics.
They do not qualify as production own history.

P-5 — OWN-EDGE DRAWDOWN

Use the same verified own-edge equity authority
required by D1.

NAV must incorporate:
- Attributable initial equity.
- Realized gross PnL.
- Fees.
- Publication-visible funding.
- Unrealized PnL at the authenticated,
  eligible mark.

No portfolio-wide NAV substitution.

For the supported one-edge lineage, the shared
engine equity may be used only after proving
exclusive attribution to that edge.

Reject unaccounted capital flows.
Do not invent a flow-adjustment method.

Define the high-water mark from genesis G:

peak(t) = max(verified own-edge NAV(s), G <= s <= t)

DD_current(t) = 1 - NAV(t) / peak(t)

Require a positive verified peak.

Measure the own-edge valuation path at every
relevant authenticated mark/economics change,
using the same knowledge-time authority as P-2.

No new market-price interpolation or
indefinite stale-mark valuation.

The peak is not reset at UTC midnight,
month boundaries, state changes or recovery.

A missing interval cannot be assumed to contain
no higher equity.

A decision-only sampled peak may establish a
proven lower bound on drawdown.

That lower bound can establish FAIL when it
already reaches the accepted limit.

It cannot establish exact DD_current, ordinary
PASS or a full S_drawdown score when the
required valuation path remains incomplete.

Apply the existing Family B maximum drawdown
threshold of 5 percent, inclusive.

Preserve the PRDV4 S_drawdown formula.

No new risk limit, capital commitment or
parallel portfolio valuation engine.

P-6 — HIT-RATE TRADE POPULATION

Count one complete engine-native position
excursion:

FLAT -> NONZERO -> FLAT

Multiple entry/exit fills inside one excursion
do not create multiple trades.

An open excursion is not a closed trade.

Use the exact realized net outcome:
gross realized PnL - fees + funding.

Use the accepted engine's closed-trade identity
and publication-knowledge derivation.

A closed trade becomes known only after its
closing fill and every required settlement's
final-rate visibility are established.

Select trade membership by closing coordinate
within the trailing 30-day or 90-day window.

At a decision, include only closures preceding
or visible at that decision's engine phase.

A relevant closed trade whose complete outcome
is not yet known blocks the dependent reading.
Do not discard it.

Count:
- Positive net outcome: win.
- Negative net outcome: non-win.
- Zero net outcome: non-win.

Each completed eligible excursion contributes
one to N_total.

HR_N = N_win / N_total

For S_hitrate:
If the complete known trade population contains
fewer than 10 trades, use the existing PRDV4
neutral component 0.5.

This includes proven zero closed trades.

If the population or an applicable outcome is
unproven, BLOCKED instead of neutral.

For HIT_RATE_ALERT:
Require complete 30-day and 90-day windows,
both raw hit rates mathematically defined.

Do not substitute S_hitrate=0.5 for an
undefined raw hit rate.

Use the existing strict PRDV4 comparison:
HR_30d < HR_90d - 0.10

No new alert threshold.

SHARED_NUMERICAL_AND_AUTHORITY_CONTRACT

Use exact rational arithmetic wherever possible.

For irrational Sharpe/CV/EHS quantities, use
mathematically justified exact comparisons or
certified enclosing bounds.

An unresolved threshold comparison is BLOCKED.

Do not decide a strict safety boundary from
rounded display decimals.

Preserve legacy serialized artifacts.

Where an existing consumer cannot accept the
new representation without changing its
normative semantics, report the remaining
representation decision instead of introducing
a silent rounding rule.

One verified engine-derived own-history authority.

No caller-supplied observation counts, scores,
submission flags, FSM states or NAV peaks.

Bind every derived reading to the exact subject,
source records, lineage and knowledge prefix.

Public verifiers must reconstruct the reading.

Preserve FAIL precedence, irreversible U1-U4
completion, and accepted U5 behavior.

No exception for mathematical undefinedness,
proven failure, missing external proof or
unapproved methodology.

REQUIRED_FUTURE_ACCEPTANCE

Demonstrate:
- Signal population includes non-trading events.
- No future publication rewrites an earlier reading.
- Same-instant decision cannot consume its fill.
- A completeness gap prevents recovery.
- Two distinct disable episodes trigger quarantine.
- Quarantine expiry cannot self-authorize release.
- EHS recovery cannot override EF-8.
- Pre-submission refusal is excluded.
- Post-submission refusal cannot disappear.
- Pending order cannot become terminal by truncation.
- Close-only requested quantity is the denominator.
- Replay and extension preserve submission counts.
- Incomplete valuation path cannot create false PASS.
- Exact 5 percent drawdown disables Family B.
- Partial fills do not inflate trade count.
- Zero-net trade is included as a non-win.
- Late funding cannot rewrite earlier hit rate.
- Proven FAIL dominates every incubation exception.
- Legacy bytes and independent gates remain intact.

RESIDUAL_GATES

Preserve C-1 through C-7 construction requirements.
Preserve E-1 through E-3 external/provenance gates.

HD-07, X-H1, M1, D1 venue facts, C1-C9, DEC-1,
NT-D01 and all other independent blockers remain.

No claimed production signal qualification,
continuous source coverage, readmission approval
or production observation history.

No guaranteed first-entry reachability.

AUTHORIZATION_BOUNDARY

This is a proposed human methodology decision only.

Approval selects P-1 through P-6 for subsequent
docs-only adoption preparation.

It does not authorize implementation, tracked
edits, commit, push, PR publication or merge.

Separate protected doctrine adoption and separate
construction authorization are mandatory.

No production approval, real paper, readiness,
credentials/private API, actual orders, fills,
positions, PnL/capital mutation, scheduler,
auto-loop, shadow or live transition.

HUMAN_DECISION=APPROVE / AMEND / REJECT
```

In `RESIDUAL_GATES`, "C-1 through C-7" are the construction items of the [own-history adoption record], "C1-C9" are
the governed paper constants ([Companion] §12.1), and "D1 venue facts" is the external venue-fact dependency
([Companion] §12.2), not decision clause D1.

## Relation to accepted doctrine

Each clause applies accepted authority and relaxes none of it.

| Clause | Accepted authority it applies | Effect |
|---|---|---|
| P-1 | [PRDV4] §1.6 Component 4 (`CV_signal` over `signal_values_30d`, `S_stability`); D2 (M-3 of the [own-history adoption record]); D6; the accepted profile `passive_funding_carry.v1` and its H2 schedule (`strategy_executable_profiles.py`, `historical_decision_run.py`); [Companion] §3.3 (`S_stability` is never covered) | Selects the scalar: the exact signed mean of the latest N visible final funding rates, with N = `final_funding_lookback_count`, reconstructed from verified inputs. The decision record's `feature_mean` is an 18-place ROUND_HALF_EVEN rendering and never decides a threshold. Selects the population: every H2 evaluation, NO_ACTION, HOLD and EXIT included, and evaluations whose entry was refused. Selects the window (t − 30 UTC days, t] from G, an inception-truncated window only on proven complete history, at least two defined values, and an undefined evaluation inside the window blocks the reading. A non-positive mean stays BLOCKED (D2). PRDV4 sets no minimum sample for Component 4, so the truncated window is the part of the trailing window in which the lineage exists, not an exception under §0.3. D1's 30 and 90 completed days are unchanged |
| P-2 | [PRDV4] §0.3 INV-001, INV-002 and INV-004, and §1.21 (point-in-time); D3 (M-5); the engine's equal-instant order `funding_then_protective_then_decision_then_fill_then_valuation_v1` (`HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES`); [RECORD B] L-9 (late data counts only from its knowledge instant); [registry adoption record] A4; phase map §20 (X1, the knowledge-stable prefix) | Fixes one knowledge-time order, `(timestamp_ns, accepted_engine_phase, native_sequence)`, over the six unchanged phases. A source publication is known at its verified coordinate. DECISION reads the earlier phases and its own evaluation, never its own fills. Completeness needs positive evidence. An unknown interval interrupts and restarts the 48-hour proof. Later knowledge acts forward only and never rewrites a decision, seal, graduation or prefix. This is offline replay: `MONITORING_CADENCE` ([RECORD B] C-19) is not decided |
| P-3 | [PRDV4] §1.6 state machine and hysteresis, §1.5 deactivation, §1.21 NT-E01, NT-E02 and NT-E04, and §0.3; D3 (M-4, M-5); [Companion] §3.4 and §4.1; EF-8 (`edge_kill_quarantine_decision.py`) and the accepted NT-E02 reading of EF-8 (`governed_paper_entry_safety.py`); [incubation adoption record] (negative evidence, no reset) | Keeps the four PRDV4 states and every threshold. Adds `STATE_NOT_ESTABLISHED` as an evidence status, no default state, the first fully defined EHS as the start, a proven drawdown breach establishing DISABLED, no direct DISABLED-to-ACTIVE step, WARNING as the first recovery step, episode counting over (t − 30 UTC days, t], the second episode entering QUARANTINE, a 14-day minimum lock, release only on a fresh EF-5/EF-6/EF-7 revalidation plus separate governance authorization, and release back to DISABLED recovery status. Each addition is stricter than PRDV4 or covers a case PRDV4 leaves open: it defines no state before the first EHS and none after quarantine. EF-8 is a separate lifecycle with its own timing (DISABLED, more than 30 UTC days, QUARANTINE, at least 14 UTC days, re-admission). It stays independently verified, and neither machine clears the other |
| P-4 | [PRDV4] §1.5 Execution Conditions ("last 20 orders"), §1.21 NT-X02 ("Last 10 orders", per exchange) and §0.3 INV-003; D4 and D5 (M-6, M-7); HC-14a; [Companion] §3.3 U3/U4 and §3.5 (attempts are not observations); the engine (an intent is "never an order"; its outcomes; the close-only clamp; protective attempts and children; PENDING at the evaluation end) | Defines the submitted order that D4 needs: a logical simulated-submission event inside the one engine at the three-condition boundary, never a venue order. Selects the denominator (the requested quantity after the close-only clamp and grid normalization), the bindings, the terminal classes (1, the filled fraction, 0, 0, 0 or UNKNOWN), the order of the latest-N window (submission coordinate, then native sequence) and the separation from incubation attempts. D5's equal weighting and every threshold are unchanged |
| P-5 | [PRDV4] §1.6 Component 3 (`S_drawdown`, the Family B limit of 5%, `DD_current >= DD_max,edge` gives `S_drawdown = 0` and DISABLED), §1.5 and §10.3; the D1 NAV authority (M-1 and the returns cases of the [own-history adoption record]); the engine's equity identity and valuation rules | Selects the input of `DD_current`: verified own-edge NAV (attributable initial equity, realized gross PnL, fees, publication-visible funding and unrealized PnL at an eligible mark), the high-water mark from G, `DD_current = 1 − NAV / peak`, a positive peak, valuation at every relevant mark and economics change, no reset, no gap assumed safe, a sampled lower bound that can prove FAIL only, and 5% inclusive. The inclusive comparison is §1.6's. §1.5 ("exceeds") and §10.3 (">") are weaker and give way to it |
| P-6 | [PRDV4] §1.6 Component 2 (`HR_30d`, `S_hitrate`, minimum sample 10 giving 0.5, HIT_RATE_ALERT) and §10.3; D3 (`S_hitrate = 0.5` only on a proven count); [RECORD A] §2.1 (one closed excursion FLAT → nonzero → FLAT, known at its closing fill and the publication of every settlement it carries); the engine's closed-trade records and `HistoricalExecutionTradeExactValues` | Selects the trade population: one closed excursion per trade, its exact realized net outcome, the engine's identity and knowledge instant, membership by closing coordinate, admissibility by knowledge, positive as a win, negative and zero as non-wins, `S_hitrate = 0.5` below 10 complete known trades (zero included), BLOCKED when unproven, and HIT_RATE_ALERT only on two complete, defined windows with the strict PRDV4 comparison. RECORD A's Kelly classes, in which a zero-net trade completes no class, are a different reading and are unchanged |
| Shared contract | [PRDV4] §1.7 (weights are exact rationals; a rendering never crosses the floor or the cap); D5 ("no rounding before threshold comparison"); C-2 of the [own-history adoption record] (no rounding convention for a Sharpe threshold is approved); D6; [Companion] §9.1 trust boundaries and §9.3 versioning; [incubation adoption record] (FAIL dominates; irreversible completion); [RECORD A] (U5) | Exact rationals where possible. Exact comparisons or certified enclosures for the irrational Sharpe, CV and EHS. An unresolved comparison is BLOCKED, and no rounded display decides a strict boundary. Legacy artifacts stay byte-identical. A consumer that cannot take the exact representation leaves a reported representation decision (R-1 below), never a rounding rule. One engine-derived authority; no caller-supplied count, score, flag, state or peak; every reading bound to its subject, records, lineage and knowledge prefix and reconstructed by a public verifier |
| Required future acceptance | [Companion] §12.3; the acceptance-case convention of the [own-history adoption record] | Acceptance criteria for a later construction. They set no governance value |
| Residual gates | [Companion] §§12.1–12.2; C-1..C-7, E-1..E-3 and G-1 of the [own-history adoption record] | Every gate stays. No signal qualification, source coverage, readmission approval, production history or first-entry reachability is claimed |
| Authorization boundary | [Companion] §12.3 | Methodology only. Construction, policy, production and merge stay separately gated. The draft publication of this record rests on the separate action grant above |

## Readings applied by this record

Each reading follows from the approved text and the accepted doctrine named in its row. None sets a value, threshold or
default. The independent audit confirms or rejects each one. A rejected reading leaves the dependent result BLOCKED,
never a permissive default.

| Id | Reading | Follows from |
|---|---|---|
| RD-1 | **Trailing windows.** P-6's "trailing 30-day or 90-day window" is (t − 30 UTC days, t] and (t − 90 UTC days, t]. That is the definition P-1 gives for the trailing 30-day window and the interval P-3 uses for episode counting. A UTC day is 86,400 s, as in the engine | P-1, P-3, P-6 |
| RD-2 | **Coordinates.** A reading is taken at one coordinate (t, phase). Time-defined conditions depend on t alone and hold alike in every phase of t: window membership, the 48-hour duration, the 14-day lock, the episode interval and lifecycle deadlines. Inputs enter in P-2's order. A reading at (t, DECISION) sees the FUNDING and PROTECTIVE events of t, the source publications visible at t (visibility at or before t, the engine's rule) and its own evaluation, but no fill of t. Each coordinate has one atomic evaluation. Re-evaluating or replaying it, or observing the same state again, creates no transition | P-2; P-3 ("Repeated observations ... do not create additional transitions"); D3 |
| RD-3 | **Recovery steps.** A recovery is a recorded DISABLED → WARNING transition at one coordinate. An ACTIVE transition needs a later coordinate with EHS ≥ 0.70 and no restriction, which the text calls a subsequent evaluation. The text sets no minimum time in WARNING, and none is added. When the 48 hours complete at t but an input of an earlier phase of t takes EHS below 0.40, no coordinate holds both conditions, so there is no recovery | P-3; P-2 ("Resolve simultaneous inputs atomically") |
| RD-4 | **Boundaries.** "At least 48 hours" and "at least 14 UTC days" are met at exactly 48 hours and exactly 14 UTC days; EF-8 reads its own 14 days the same way. An episode whose DISABLED transition lies exactly at t − 30 UTC days is outside (t − 30 UTC days, t]. EHS = 0.70 is ACTIVE unless a restriction applies, EHS = 0.30 is WARNING unless a recovery restriction applies, and EHS = 0.40 counts toward recovery. "After the triggering disable" and "known before the release decision" are strict | P-3; [PRDV4] §1.6 |
| RD-5 | **Episodes.** An episode starts at its transition into DISABLED, the event PRDV4 counts ("DISABLED transitions"). That includes a first established state of DISABLED from a proven drawdown breach. The only exclusion the text states is the administrative release from QUARANTINE | P-3; [PRDV4] §1.6 |
| RD-6 | **Quarantine lockout.** QUARANTINE is "locked out" under PRDV4 §1.6, so a consumer refuses entry in it. Which check carries the refusal is a construction mapping (C-7). The accepted entry safety already fails NT-E02 on an EF-8 DISABLED or QUARANTINE successor | [PRDV4] §1.6; `governed_paper_entry_safety.py` |
| RD-7 | **Previously consumed evidence.** Read literally, validation evidence already consumed by the subject's genesis admission, by an EF-8 transition or by an earlier release cannot release quarantine. One new EF-7 therefore cannot serve both an EF-8 re-admission and a later EHS release. Any shared use would need a human decision | P-3 |
| RD-8 | **Drawdown knowledge.** NAV(s) is D1's own-edge NAV: each settlement is booked at its liability instant and known only once its final rate is visible. A reading at t may use NAV(s) only when every input of NAV(s) is visible at t. Before that, that part of the path is unknown: an unpublished settlement is neither valued at zero nor dropped. The engine's admission view (booked equity minus unpublished settlements) is not substituted for the path. The two coincide when nothing is unpublished | P-5 ("the same verified own-edge equity authority required by D1"; "the same knowledge-time authority as P-2"); the [own-history adoption record] returns case of a NAV awaiting a settlement's publication |
| RD-9 | **Lower bound.** Let NAV(t) be verified, and let p_s > 0 be the maximum of verified NAV(s) over sampled s with G ≤ s ≤ t, so the true peak p ≥ p_s. Then DD_current(t) ≥ min(1, 1 − NAV(t) / p_s). For NAV(t) ≥ 0, 1 − NAV(t) / p does not decrease as p grows; for NAV(t) < 0, DD_current(t) > 1. So 1 − NAV(t) / p_s ≥ 1/20 proves FAIL. It never proves PASS, an exact DD_current or S_drawdown | P-5 |
| RD-10 | **Valuation path.** Between authenticated changes the own-edge NAV is the engine's valuation at the latest visible mark within `max_mark_staleness_ns`. Past that bound no valuation exists and the interval is unknown. The engine's valuation ledger holds only the initial, fill, settlement, UTC-day-boundary and end valuations, so the path at every mark visibility while positioned is C-1 construction inside the one engine | P-5; the engine's valuation rule |
| RD-11 | **Same-instant closes.** Every fill, a protective or flatten-child fill included, is a FILL-phase event at its book's visibility. A protective rule (deadline, tightening, stop, attempt) is a PROTECTIVE-phase event before DECISION. A close at t therefore follows any DECISION of t: at that phase the excursion is still open, so the close neither counts for that decision nor blocks it. An ordinary decision's fill lies strictly before the next decision, and while a protective or child order is in flight every decision intent is refused. [RECORD A]'s rule that "at one instant a closing fill is ordered before an entry decision" therefore never meets an admitted entry with a same-instant, later-phase close. The Kelly reading keeps RECORD A's rule, and the hit-rate reading follows P-6 | P-2, P-6; [RECORD A] §2.1; the engine's event loop |
| RD-12 | **Submission mapping.** Decision-time refusals (position management, then the schedule's intent admission) lie before the boundary. Book selection, the market gates (spread, depth, zero fill) and every fill-time refusal lie after it. An intent left UNFILLED because its delay bound passed or the next decision closed its window is a conclusive non-fill (0), provided the book coverage of that window is complete ("no events observed does not prove no events occurred"; E-1). Its terminal coordinate is that close, the engine's own resolution instant `min(decision + max_execution_delay_ns, window end)`, not the decision instant at which the engine selects its book; before that coordinate it is unresolved. An intent whose window was closed by the evaluation end or by the end of the dataset's books is unresolved: UNKNOWN (the engine reports the last decision's as PENDING). A protective attempt or child enters its ledger before its attempt-time protective admission: one refused there never crossed the boundary, and ledger presence is not submission. One without a book stays in flight to the end: UNKNOWN. The legacy label REJECTED covers both sides of the boundary, so classification needs boundary instrumentation (C-5), never the label or reason alone | P-4, P-2; the engine (`_intent_admission`, `_select_book`, `_fill_core`, `_issue_child`, PENDING) |
| RD-13 | **Signal consequences.** An evaluation with fewer than N visible final rates has no scalar. It is undefined and blocks every window that holds it. A negative-mean regime never yields `S_stability`. Whether the dataset holds every funding publication that occurred is source qualification (E-1), which deterministic replay cannot prove | P-1; D2; E-1 |
| RD-14 | **Hit-rate history.** The lineage starts flat at G, so the part of a window before G provably holds none of its trades. `S_hitrate = 0.5` is therefore available before G + 30 days when the population since G is complete and known. A complete window for HIT_RATE_ALERT lies wholly at or after G, because P-1 contrasts complete and inception-truncated windows. HIT_RATE_ALERT's only PRDV4 action is "increase monitoring" (§10.3), so its undefinedness blocks no admission reading | P-6; P-1; [PRDV4] §10.3 |
| RD-15 | **Native sequence.** The engine's own deterministic tie-breaks, such as its book order by visibility, event time, sequence and digest, are authenticated engine ordering and stay. A measurement adds no ordering of its own. Where neither engine nor source orders two inputs and the result depends on their order, the reading is not proven: BLOCKED | P-2 ("Do not change legacy engine ordering"; "Do not use arbitrary digest sorting") |

## Forward-only disposition

The texts below keep their bytes and their meaning at their own dates. This table states their status after the
adoption conditions hold.

| Source passage | Status there | After this adoption |
|---|---|---|
| [own-history adoption record], "Approved methodology and remaining items", rows P-1 to P-6 | PENDING_HUMAN_DECISION | Resolved as M-9 to M-14 below. The rows keep their bytes |
| Same table, C-3 "(after P-1)", C-4 "(after P-2, P-3, P-5 and P-6)" and C-5 "(after P-4)" | MISSING_CONSTRUCTION, waiting on the P items | MISSING_CONSTRUCTION. The methodology they waited on is selected; no producer exists |
| Same record, "Construction acceptance cases" that name a P item: missing records or unknown semantics (P-1, E-2); a proven trade count below 10 (P-6); drawdown at the limit "once P-5 defines the measurement"; the unknown initial state (P-3); sparse observations and equal-instant changes (P-2); the pre-submission refusal and same-nanosecond identities (P-4) | Dependent reading BLOCKED until decided | Decided by the clause named. The cases of this record give the outcome. E-2 stays open |
| Same record, "Incubation and allocation trace": U3/U4 "subject to P-4"; other EHS components "Blocked by P-1, P-5 and P-6" | Pending | Methods selected. No producer; BLOCKED |
| Same record, "Construction dependency matrix", residual gates P-1 to P-6 | Pending | Selected. The residual gates of the matrix below apply |
| Same record, "the decision's own approval does not approve P-1..P-6" | Fact about D1–D7 | Still true of that decision. P-1 to P-6 are approved by the separate decision recorded here |
| Phase map §21, "... remain pending human decisions" | Pending | Selected by this record. §21 keeps its bytes |
| [Companion] §0.5, allocation membership row | UNKNOWN | Still UNKNOWN and every weight BLOCKED: no producer exists |
| Entry safety NT-E02, BLOCKED as `prdv4_edge_state_machine_not_produced` unless EF-8 fails it | Accepted executable behavior | Unchanged. The state machine is now specified, not produced |

The blocker identities `INCUBATION_FUTURE_APPROVAL_REWRITES_PAST`,
`INCUBATION_KNOWN_SIGNAL_BLOCK_DELAYED_UNTIL_EFFECTIVE_TIME` and `INCUBATION_ACTIVE_WITH_EMPTY_FILL_WINDOW` (phase map
§20) stay closed by the accepted construction and are not reopened here.

## Classified inventory

Classes: `RESOLVED_METHODOLOGY`, `MISSING_CONSTRUCTION`, `PENDING_HUMAN_DECISION`, `BLOCKED_EXTERNAL` and
`UNPROVEN_PROVENANCE`. Existing identities keep their meaning. A pending, missing, external or unproven item blocks every
reading that depends on it. No item is resolved by default, by a proxy or by the absence of a decision.

| Id | Item | Class |
|---|---|---|
| M-1..M-8 | D1–D7 of the [own-history adoption record] | RESOLVED_METHODOLOGY, unchanged |
| M-9 | P-1: the exact scalar, every H2 evaluation, the window from G, truncation only on proven complete history, two or more defined values, undefined evaluations blocking, a non-positive mean BLOCKED | RESOLVED_METHODOLOGY |
| M-10 | P-2: one knowledge-time order, publications at their coordinates, no decision reading its own fills, positive completeness, gaps restarting the 48-hour proof, forward-only knowledge, X1 | RESOLVED_METHODOLOGY |
| M-11 | P-3: `STATE_NOT_ESTABLISHED`, start, transitions, recovery, episodes, QUARANTINE, release, EF-8 independence | RESOLVED_METHODOLOGY |
| M-12 | P-4: logical simulated submission, denominator, bindings, terminal classes, latest-N order, attempts kept separate | RESOLVED_METHODOLOGY |
| M-13 | P-5: own-edge NAV, peak from G, `DD_current`, the full valuation path, lower bound for FAIL only, 5% inclusive | RESOLVED_METHODOLOGY |
| M-14 | P-6: closed excursions, exact net outcome, closing-coordinate membership, knowledge admissibility, win and non-win, the neutral 0.5, HIT_RATE_ALERT | RESOLVED_METHODOLOGY |
| M-15 | The shared numerical and authority contract | RESOLVED_METHODOLOGY |
| P-1..P-6 | The six residual items of the [own-history adoption record] | Resolved as M-9 to M-14 once the adoption conditions hold; until then PENDING_HUMAN_DECISION as recorded there |
| C-1 | Own-edge NAV path at every mark visibility and economics change, with knowledge coordinates, flow attribution and proof of one-edge exclusivity (RD-8 to RD-10) | MISSING_CONSTRUCTION |
| C-2 | Sharpe_30d and Sharpe_90d evidence over C-1, with exact or certified comparisons | MISSING_CONSTRUCTION |
| C-3 | Scalar signal history (M-9) | MISSING_CONSTRUCTION |
| C-4 | EHS evaluation and state-history replay, with the hit-rate population (M-10, M-11, M-13, M-14) | MISSING_CONSTRUCTION |
| C-5 | Submission instrumentation and the order-observation ledger (M-12, RD-12) | MISSING_CONSTRUCTION |
| C-6 | U1–U4 coverage and per-reading graduation inside the incubation authority | MISSING_CONSTRUCTION |
| C-7 | Rule-set, seal and allocation consumers, including a consumer able to take exact readings or decided comparisons | MISSING_CONSTRUCTION |
| E-1 | X-H1 exchange health (latency, API error, maintenance; NT-X01, NT-X04); M1 source qualification, including the mark archive and the completeness of funding, mark and book publications ("every expected observation or a proven valid absence"); D1 venue facts | BLOCKED_EXTERNAL |
| E-2 | Strategy scalar provenance. P-1 selects the scalar of `passive_funding_carry.v1`. That the S1 edge's executed binding is this profile on qualified, authenticated inputs stays unproven | UNPROVEN_PROVENANCE |
| E-3 | The registry bases A4–A6 and the O2 signed-decision requirement ([registry adoption record]) | UNPROVEN_PROVENANCE |
| R-1 | **Representation at a rational consumer.** EHS, Sharpe_30d and their product are irrational in general. The allocation envelope reads them as canonical decimals, and [PRDV4] §1.7 requires exact rational weights, but with two or more members a projected weight inside (0.05, 0.40) is in general irrational. No representation decision is needed where every consumed fact is an exact comparison: SCALE-1 reads α_edge only as exactly 1 or below 1 (EHS ≥ 0.70 or not), and a proven single-member universe has the exact bounded weight 0.40 ([PRDV4] §1.7; [Companion] §4.3), apart from the separate 0.08 incubation exposure envelope | PENDING_HUMAN_DECISION |
| R-2 | **EHS quarantine release authorization.** A digest-bound artifact naming the QUARANTINE state, the subject, the revalidation and the release coordinate is construction. The provenance of its human approver and of its effective time (A3, A4, O2, O3 of the [registry adoption record]) is unproven | MISSING_CONSTRUCTION; provenance UNPROVEN_PROVENANCE |
| R-3 | **Knowledge coordinate of a revalidation.** EF-5, EF-6 and EF-7 carry caller coordinates, not qualified publication time, so "known before the release decision" cannot yet be proven | UNPROVEN_PROVENANCE |
| G-1 | HD-07, HC-16a/c/d, KD-7 at `n_w = 100`, FCD-05, FCD-17 and `H^(e)`, `MONITORING_CADENCE`, NT-D01, C1–C9, DEC-1, risk-policy production approval, every individual incubation record and policy artifact | Independent gates, unchanged |

## Construction dependency matrix

Read-only inputs only: nothing below is constructed by this record.

| Item | Approved clauses | Existing engine input | Missing producer | Provenance and completeness | Derived evidence | Consumers | Public verifier | Acceptance | Residual gates |
|---|---|---|---|---|---|---|---|---|---|
| C-1 | D1, P-5, P-2, shared contract | Exact equity state and identity; valuations at the initial anchor, fills, settlements, UTC-day boundaries and the end; the latest visible mark within `max_mark_staleness_ns`; settlements with liability instants and final-rate visibility; the decision portfolio's exact NAV | NAV at every mark visibility and economics change while positioned, each with its knowledge coordinate; daily endpoints; exclusive attribution and flow proof; peak and `DD_current` or its lower bound | Verified lineage and initial anchor; complete mark and funding coverage or proven valid absence (E-1); no unaccounted flow | NAV(s) as known at t, `r_d`, peak(t), `DD_current(t)`, `S_drawdown` | C-2, C-4, C-6, C-7 | A re-run of the one engine from the sealed lineage that recomputes every value and rejects a mismatch | FA-13, FA-14; drawdown cases | E-1 (M1 mark archive); G-1 (C2's G and H) |
| C-2 | D1, shared contract | C-1 daily returns; the exact mean, n−1 variance, sqrt(365) and zero-variance refusal of `paper_sharpe_evidence.py`, as arithmetic only | Sharpe_30d and Sharpe_90d with exact or certified comparisons; DECAY_ALERT; the BOOST condition | 30 and 90 consecutive completed, known UTC days | `S_sharpe`, DECAY_ALERT | C-4, C-6 (U1, U2), C-7 | Recomputation from C-1 | The returns cases of the [own-history adoption record]; numbers cases | R-1; E-1 |
| C-3 | D2, P-1, P-2 | Decision-run records (every H2 evaluation and action, input record digests, used observation count); the profile's exact mean | The exact scalar of each evaluation from verified inputs; window membership from G; definedness; completeness proof; `CV_signal`, `S_stability` | A complete funding publication series (E-1); a qualified executed profile binding (E-2) | Signal series, `CV_signal`, `S_stability` | C-4 | Re-execution of the run through its public verifier, recomputing every mean | FA-1; signal cases | E-1, E-2 |
| C-4 | D3, P-2, P-3, P-5, P-6, shared contract | C-1 to C-3; closed-trade records with their exact net PnL, knowledge instants and close phases; EF-8 receipts; the EF-5, EF-6 and EF-7 verifiers | The hit-rate population; EHS at every recompute point; state history with `STATE_NOT_ESTABLISHED`, episodes and QUARANTINE; release verification | Completeness intervals; release provenance (R-2); revalidation knowledge (R-3) | EHS, state history, the inputs of NT-E01, NT-E02 and NT-E04, α_edge, HIT_RATE_ALERT | C-6, C-7 | Replay from the sealed lineage, one evaluation per coordinate, X1 | FA-2 to FA-7, FA-15 to FA-17; state-machine and hit-rate cases | R-1, R-2, R-3, E-1; G-1 (`MONITORING_CADENCE`) |
| C-5 | D4, D5, P-4, P-2 | Intents with the requested quantity after the clamp; decision-time and fill-time admissions; fill outcomes; protective attempts and children; the PENDING intent, attempt and child; the governed prefix digest | Submission events at the boundary with coordinate, canonical submission sequence and identity; terminal classes independent of labels; unresolved state carried across seals and extensions; latest-N windows per lineage and exchange | Lineage and exchange identity. No venue fact | `f_j` or UNKNOWN; `FR_10`, `FR_20` | C-6 (U3, U4); C-7 (NT-X02, the §1.5 fill leg, A_e, FB-ACTIVATION) | A re-run of the engine that rebuilds the ledger and rejects a mismatch | FA-8 to FA-12; submission cases | E-1 (X-H1 latency and API legs) |
| C-6 | D6, P-1 to P-6, shared contract; incubation `r1` and `r2` | `governed_paper_incubation_authority.py`: one point-in-time authority, U5 graduation, the attempt ledger | U1–U4 counts from C-2 and C-5; irreversible graduation; an exception only for proven insufficient history; the INCUBATION_MEMBER inputs | A4–A6 and O2 (E-3) | Coverage state per reading | C-7 | The public incubation verifier, extended | FA-18; numbers and incubation cases | E-3; the policy artifact; record approvals |
| C-7 | All of the above; [Companion] §4 and §9.3; [PRDV4] §1.5, §1.6, §1.7 and §1.21 | Entry rule set v12, day seal v13, lineage evidence v13, schedule v9; the allocation envelope (canonical decimal EHS and Sharpe inputs); entry safety (NT-E02 FAIL only on EF-8) | Opt-in successor versions binding C-1 to C-6 and their prefixes; NT-E01, NT-E02, NT-E04, NT-X02, the §1.5 fill leg, α_edge, E_active and the QUARANTINE refusal; a consumer that takes exact readings or decided comparisons | Production approvals | Admission and allocation verdicts | The governed entry path | The seal and lineage-evidence verifiers | FA-18, FA-19 | R-1; G-1 |

## Largest safe future construction

The largest coherent future construction is one closure of C-1 to C-7 in the one engine. It has four parts. One
schedule successor carries the submission instrumentation (C-5) and derives the own-edge valuation path (C-1) in memory,
as schedule v8 carries the closed trades' exact values. One own-history derivation builds C-2, C-3 and C-4 from that
re-run and the decision run. The U1–U4 coverage of C-6 sits inside the existing incubation authority. Successor rule
set, day seal and lineage evidence versions, with their public verifiers, form C-7. Every existing artifact, schedule,
rule set and seal stays byte-identical.

No §24.8 split reason is demonstrated. Every item has the same authorization path and the same protected boundary.
All share one knowledge-time authority (P-2) and one engine re-run, and EHS needs every component. A split would
version the engine and the seal twice and risk two own-history authorities, which the shared contract forbids. The
whole can be validated with the existing exact arithmetic and synthetic lineages. A per-metric split is not
recommended.

These stay outside that construction and keep blocking production use after it: R-1 for a universe of two or more
members, R-2, R-3, E-1 to E-3 and G-1. Production would still refuse every entry after such a construction, and
synthetic construction fixtures never become production own history. This record neither authorizes nor executes the
construction.

## Required future acceptance cases

These cases state the outcomes that P-1 to P-6, D1–D7 and accepted doctrine already require. They are acceptance
criteria for a later construction, not new doctrine. FA-1 to FA-19 are the decision's own list, in its order.

| Id | Case | Required outcome | Clauses |
|---|---|---|---|
| FA-1 | Signal population includes non-trading events | NO_ACTION, HOLD and EXIT evaluations, and evaluations whose entry was refused, are members of the window. A sample of entry evaluations only is not the population | P-1 |
| FA-2 | No future publication rewrites an earlier reading | A publication at u influences readings at u and later only. Every reading, seal, graduation and prefix before u is the same with or without it (X1) | P-2 |
| FA-3 | Same-instant decision cannot consume its fill | A reading at (t, DECISION) excludes every FILL-phase event of t, the fills of that decision included | P-2 |
| FA-4 | A completeness gap prevents recovery | An unknown interval inside the 48 hours interrupts the proof, which restarts when coverage resumes. Disjoint spans never add up | P-2, P-3 |
| FA-5 | Two distinct disable episodes trigger quarantine | The second distinct DISABLED transition inside (t − 30 UTC days, t] enters QUARANTINE. Repeated observations of one episode count once | P-3 |
| FA-6 | Quarantine expiry cannot self-authorize release | After 14 UTC days without a fresh revalidation and a separate release authorization the state stays QUARANTINE | P-3 |
| FA-7 | EHS recovery cannot override EF-8 | With an EF-8 DISABLED or QUARANTINE successor in force, an EHS state of WARNING or ACTIVE leaves the entry refused | P-3 |
| FA-8 | Pre-submission refusal is excluded | A decision refused at a decision-time gate has no order observation, whatever its legacy REJECTED label | P-4 |
| FA-9 | Post-submission refusal cannot disappear | A fill-time governed refusal or a market rejection stays in the population with fraction 0 | P-4 |
| FA-10 | Pending order cannot become terminal by truncation | An order unresolved at the evaluation end is UNKNOWN, keeps its identity across seals and extensions, and blocks every latest-N window that holds it | P-4 |
| FA-11 | Close-only requested quantity is the denominator | For an intent clamped to close-only, `f_j` is the filled quantity over the clamped requested quantity, never over the unconstrained target delta | P-4, D5 |
| FA-12 | Replay and extension preserve submission counts | A replay adds no observation. An extension keeps every earlier submission with its coordinate and sequence, and resolves a pending one only at its actual terminal coordinate | P-4, P-2 |
| FA-13 | Incomplete valuation path cannot create false PASS | With an unknown or stale interval since G there is no exact `DD_current`, no `S_drawdown` and no PASS; only a lower-bound FAIL can be proven | P-5 |
| FA-14 | Exact 5 percent drawdown disables Family B | NAV(t) = 0.95 × peak(t) gives `DD_current = 1/20`, `S_drawdown = 0` and DISABLED | P-5 |
| FA-15 | Partial fills do not inflate trade count | Several entry and exit fills inside one FLAT → nonzero → FLAT excursion are one trade | P-6 |
| FA-16 | Zero-net trade is included as a non-win | A closed trade with realized net PnL 0 adds one to `N_total` and none to `N_win` | P-6 |
| FA-17 | Late funding cannot rewrite earlier hit rate | A trade known only at a later settlement publication blocks readings before that publication and is admissible after it. No earlier reading changes | P-6, P-2 |
| FA-18 | Proven FAIL dominates every incubation exception | A proven drawdown breach, NT-X02 failure or any other proven FAIL refuses the entry under an ACTIVE record, whatever is `COLD_START_EXCEPTED` | Shared contract; [PRDV4] §0.3 |
| FA-19 | Legacy bytes and independent gates remain intact | Every existing artifact, schedule, rule set, seal and digest stays byte-identical, and every gate of E-1 to E-3 and G-1 stays in force | Shared contract |

**Signal population (P-1).**

| Case | Required outcome |
|---|---|
| Positive mean, two or more defined values, complete window | `CV_signal` defined; `S_stability` by the PRDV4 formula |
| Zero or negative mean | BLOCKED. No sign change or absolute value |
| Constant positive values | `CV_signal = 0`, `S_stability = 1` |
| Two final records with the same publication coordinate | One evaluation (H2) |
| An evaluation with fewer than N visible final rates inside the window | Undefined. The reading is BLOCKED while that evaluation is in the window, and it is never discarded |
| One defined value in the window | BLOCKED |
| A window holding only entry evaluations, or only admitted ones | Not the population. Such a sample never yields a reading |
| A delayed publication | Its evaluation sits at its actual coordinate; earlier evaluations keep their scalars |
| A missing expected funding record | Incomplete: BLOCKED. Completeness is source qualification (E-1) |
| t < G + 30 days, complete history since G, two or more defined values | Defined on the truncated window. Sharpe_30d stays undefined until 30 completed days (D1) |
| t < G + 30 days, completeness unproven | BLOCKED |
| The rendered `feature_mean` and the exact mean fall on different sides of a comparison | The exact mean decides |

**Temporal order and completeness (P-2).**

| Case | Required outcome |
|---|---|
| Several publications at one coordinate | Resolved together, atomically, in their phase |
| A window expiring at the timestamp of a decision | Membership depends on the timestamp alone and is the same in every phase |
| A protective rule firing at t | It precedes DECISION at t, which reads it |
| A protective or ordinary fill at t | A FILL-phase event, after any DECISION of t (RD-11) |
| Distinct native observations at one coordinate | Distinct, ordered by authenticated native sequence |
| An order that changes the result but follows from neither engine nor source | Not proven: BLOCKED |
| An unobserved interval | Unknown, never "no events" |
| A later replay that contains an earlier interval | The interval is known only from its actual knowledge coordinates. The replay makes no earlier reading known |
| A discovery later than an earlier seal | Acts from its knowledge coordinate. The sealed prefix is unchanged (X1) |

**State machine and quarantine (P-3).**

| Case | Required outcome |
|---|---|
| No fully defined EHS yet | `STATE_NOT_ESTABLISHED`, an evidence status. No ACTIVE or WARNING default. NT-E01 and NT-E02 are BLOCKED, or `COLD_START_EXCEPTED` only where undefined solely by covered U1 history |
| First fully defined EHS after an unknown prefix | Not established while the prefix may hold an unresolved disable or quarantine condition: BLOCKED |
| Proven Family B breach with Sharpe_30d undefined | DISABLED established: FAIL |
| EHS exactly 0.70, exactly 0.30, below 0.30 | ACTIVE, WARNING, DISABLED, each subject to the recovery and quarantine restrictions |
| DISABLED with EHS ≥ 0.70 | Never a direct ACTIVE transition |
| EHS ≥ 0.40 continuously for exactly 48 hours with full coverage | Recovery to WARNING |
| The 48 hours interrupted by EHS < 0.40 or an unknown interval | No recovery; the proof restarts |
| A same-coordinate re-evaluation after a recovery | No second transition (RD-2) |
| Repeated observations within one episode | One episode |
| A second episode at t − 30 UTC days + 1 ns, or exactly at t − 30 UTC days | Inside, so QUARANTINE; or outside, so not counted |
| A release before entry + 14 UTC days | Refused |
| At entry + 14 UTC days, with a fresh revalidation and a release authorization | Release to DISABLED recovery status. Not a new episode. A new 48-hour proof precedes WARNING |
| A revalidation of another subject, one already consumed, one whose OOS evidence is not after the triggering disable, or one known only at or after the release decision | Refused |
| A release authority known after the release coordinate | No release at that coordinate |
| An EF-8 re-admission or an EF-8 ACTIVE receipt | Never an EHS state or release. An EHS recovery is never an EF-8 re-admission |

**Submission and fill rate (P-4).**

| Case | Required outcome |
|---|---|
| A decision refused at a decision-time gate | Excluded |
| A market rejection after submission | 0 |
| A governed fill-time refusal | 0 |
| A partial fill with the remainder cancelled | Filled over requested quantity, exact |
| A zero target delta | No intent and no observation |
| A close-only clamp | The denominator is the clamped requested quantity |
| Pending at the evaluation end | UNKNOWN; blocks the latest-N window |
| A protective retry with a new identity | A new observation |
| A replay of the same attempt | The same observation |
| Two submissions at one nanosecond | Two observations, ordered by native sequence |
| A seal boundary or an extension | Identity and state carried; no recount |
| Latest 10 and latest 20 | NT-X02 and the §1.5 fill leg, over one population in one order |
| An incubation attempt refused at its fill | One attempt and one order observation of 0. Neither counts as the other |

**Own-edge drawdown (P-5).**

| Case | Required outcome |
|---|---|
| One-edge lineage | The engine equity is used only with proven exclusive attribution |
| Foreign sleeve capital or an unaccounted flow | BLOCKED. No adjustment is invented |
| A late funding publication | That part of the path is unknown before the publication (RD-8) |
| A missing or stale mark | No valuation; the interval is unknown |
| An incomplete peak history | No exact `DD_current`; a lower bound only |
| Genesis | peak(G) = NAV(G), the attributable initial equity, which must be positive |
| UTC midnight, a month end, a state change, a recovery | The peak is not reset |
| `DD_current` exactly 0.05 | DISABLED (inclusive) |
| `DD_current` below 0.05 | No drawdown disable; `S_drawdown` by the formula |
| A lower bound at or above 0.05 on an incomplete path | FAIL proven (RD-9) |
| A lower bound below 0.05 on an incomplete path | BLOCKED, never PASS |

**Hit rate (P-6).**

| Case | Required outcome |
|---|---|
| Partial fills inside one excursion | One trade |
| An open excursion | Not a trade |
| A zero-net trade | A non-win, counted |
| Fees turning a positive gross into a negative net | A non-win |
| A final funding rate not yet published | Unknown outcome: the reading is BLOCKED |
| Knowledge after the window has moved | Membership by closing coordinate, admissibility from knowledge; never shifted to publication time |
| A close at t and a DECISION at t | Not a closure at that DECISION (RD-11) |
| A proven count of 0 or 9 | `S_hitrate = 0.5` |
| A proven count of 10 | `HR_30d` by the formula |
| A raw hit rate undefined (`N_total = 0`) | HIT_RATE_ALERT undefined. 0.5 is never substituted |
| `HR_30d = HR_90d − 0.10` exactly | No alert (strict comparison) |

**Numbers and incubation (shared contract).**

| Case | Required outcome |
|---|---|
| Sharpe, CV or EHS exactly at a threshold | Decided exactly. Equality is decidable for these values |
| A value within a rendering's rounding of a threshold | An exact comparison or a certified enclosure; unresolved is BLOCKED |
| An irrational reading entering a decimal consumer | R-1, never a rounding rule |
| A blocked non-covered stability input under an ACTIVE record | BLOCKED, never excepted |
| U1–U4 graduated, later window undefined | Ordinary and BLOCKED. Coverage never returns |
| Incubation attempts and submitted orders | Counted separately |

## Incubation and allocation trace

| Reading | After this adoption |
|---|---|
| U1 Sharpe_30d, U2 Sharpe_90d and DECAY_ALERT | Method D1, unchanged. No producer; BLOCKED |
| U3 `FR_10`, U4 `FR_20` | Submission boundary selected (P-4). No producer; BLOCKED |
| `S_hitrate` | Population selected (P-6). A proven count below 10 gives 0.5, an ordinary defined value, not an exception |
| `S_drawdown` | Input selected (P-5). No producer; BLOCKED |
| `S_stability` | Population selected (P-1). Never covered. No producer; BLOCKED |
| The edge state | Start, recovery and quarantine selected (P-3). No producer; NT-E02 stays BLOCKED unless EF-8 fails it |

`INCUBATION_MEMBER` still requires exactly one candidate, U4 as the only non-PASS leg of A_e and U1 as the only
undefined EHS input, each `COLD_START_EXCEPTED` and neither FAIL ([Companion] §4.1; [incubation adoption record]). P-1,
P-5 and P-6 make `S_stability`, `S_drawdown` and `S_hitrate` definable by a future producer, but none exists, and the
latency and API legs (X-H1) and a complete candidate universe stay unproven. No partial EHS, partial activation proof
or assumed universe grants allocation. A blocked non-covered stability input cannot be excepted, even under an ACTIVE
record. The bounds of 21 attempts, 91 UTC days and 0.08 of NAV are unchanged.

## Admission effect and non-claims

- **Admission effect: none.** This change edits no code, test, rule set, schedule, seal, policy artifact, approval
  table or registry. Every governed S1 entry stays refused as before.
- **Not claimed:** a signal, Sharpe, EHS, state, drawdown, hit-rate or fill-rate measurement; a producer; qualified
  signal provenance; continuous source coverage; a readmission or release approval; production observation history; an
  ACTIVE record; `COLD_START_EXCEPTED` or `INCUBATION_MEMBER` for any edge; venue health; construction readiness;
  first-entry reachability; Stage-4 eligibility or credit; readiness; profitability or edge.
- **No authority** for implementation, production policy or approval-table entries, registry rows, record approvals,
  qualification, real paper (`REAL_PAPER_EXECUTION`), shadow, live, orders, fills, positions, PnL or capital, a
  scheduler, monitor or auto-loop, readiness or connector transitions, ready-for-review or merge.
- No historical proposal is adopted by this record beyond the approved P-1 to P-6 text.

## Verification of this adoption

| Check | Requirement |
|---|---|
| Decision text | The decision block equals the packet's text between its begin and end markers, line for line. SHA-256 of the block's UTF-8 text, lines joined by line feeds, without a final line feed: `69ed4889c09092d4da0113f658a5651881071890bb6840efe3e063a451219654` |
| Approval and grant | The relayed approval statement and the direct action grant are quoted verbatim, with the grant's transcript record digests |
| Doctrine | Each clause maps to accepted authority and each reading names its source. No value, threshold or gate is relaxed, and each remaining item is classified |
| Scope | The change adds this record and phase-map §22. The base phase map is an exact byte prefix of the new one. No other byte changes, and no source, test, script, setup or PRDV4 change |
| Format | `git diff --check` is clean, and every relative link resolves |

[PRDV4]: ../PRDV4_MULTI_MARKET_CRYPTO.md
[own-history adoption record]: s1_own_history_measurement_doctrine_adoption_v1.md
[Companion]: s1_approved_doctrine_adoption_v1.md
[RECORD A]: s1_kelly_class_completion_amendment_v1.md
[RECORD B]: s1_native_risk_measurement_doctrine_adoption_v1.md
[D-A1 decision]: s1_kelly_da1_doctrine_adoption_v1.md
[incubation adoption record]: s1_paper_incubation_doctrine_adoption_v1.md
[registry adoption record]: s1_incubation_authority_registry_doctrine_adoption_v1.md
