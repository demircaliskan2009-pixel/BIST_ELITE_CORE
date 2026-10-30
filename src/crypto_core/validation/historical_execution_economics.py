"""Deterministic historical execution economics (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V2).

A ``HistoricalExecutionEconomicsResult`` turns one authenticated ``HistoricalDecisionRun`` (P1) into raw, digest-bound
historical economic authority under one governed ``HistoricalExecutionEconomicsPolicy`` and its approval:

authenticated decision trace → target-delta intents → next-observation simulated fills (fill-ratio model, spread,
participation impact, slippage floor, taker fee) → signed position transitions → final funding settlements → mark-to-
market valuations and equity observations → closed/open trade records → terminal state.

Authority. The run is re-proven through its public verifier against the caller's anchor (same correlation, READY);
its own PIT dataset snapshot is the ONLY source of market observations (no separate execution dataset, no transplant
seam). The StrategySpec is re-derived from the run's executable binding → EF-4 admission → spec snapshot and must hash
to the run's ``strategy_spec_digest``. The policy is re-proven against its anchor. The approval must match the exact
policy digest, spec digest, instrument, market type, DataRequirementRegistry digest, quantity semantics and execution/
funding identity digests. The P1 decisions are consumed as frozen facts; no decision is re-computed or altered.

Accounting representation (``EXACT_INTERNAL_COST_BASIS_NEVER_ROUNDED_FOR_STATE``). Internal accounting state is one
exact pair — signed ``quantity`` and signed ``cost_basis`` — plus exact cumulative realized, fee and funding totals.
The average entry price is DERIVED exactly as ``cost_basis / quantity`` and is never stored, never rounded and never
read back from a rendered field. Every scale-18 string this module emits (average entry price, realized and
unrealized PnL, equity, fees, funding, notionals, ratios and bps) is ARTIFACT OUTPUT rendered once from exact state,
and no emitted string is ever converted back into accounting authority. Exactly two values are quantized once as an
ECONOMIC rule rather than for display — the executed price (ROUND_HALF_EVEN onto the scale-18 price grid) and the
executable quantity (truncated toward zero) — and both are produced by exact integer arithmetic that returns the grid
value and its canonical text together, so the artifact text and the number used by the economics are the same value.
Because rendering is output only, rendered components of an identity need not sum bit-exactly to the rendered total:
the identities hold EXACTLY on the exact state, and each field carries one ROUND_HALF_EVEN rendering of its own exact
value (never a re-rounded one). Every closed trade additionally re-proves its own economics against the signed fill
cashflows it was built from (``trade_cashflow_reconciliation_failed`` otherwise).

Leverage authority is exact. ``max_leverage`` is consumed only as a positive native ``int``; a ``float``, ``bool``,
string, ``Decimal`` or any other representation is refused with ``strategy_max_leverage_representation_unsupported``
and there is no coercion through ``repr``, ``float`` or a decimal context.

Outcomes. Integrity failure → ``REJECTED``/``NOT_EVALUATED``. A non-advancing run or policy propagates its verdict.
Missing external facts → ``NEEDS_EXTERNAL_FACTS``; missing/mismatched approval → ``NEEDS_GOVERNANCE_APPROVAL``; an
economic incompatibility or data insufficiency → ``FAIL``. Only ``READY`` + ``PASS`` carries economics; every other
outcome carries empty ledgers and no terminal state (nothing is fabricated).

Execution semantics (linear USDT perpetual, base-asset quantity):

* intent: target = resulting_direction × unit_size (FLAT → 0); delta = target − actual simulated position; delta 0 →
  no intent; a delta that would cross zero is clamped to close-only (an opposite entry can only follow at a later
  decision instant);
* observation: the first order-book record, ordered by PIT visibility (``max(available_at, finalized_at)``), then event
  time, sequence and digest, whose visibility is ``>= decision_time + latency_ns`` and whose event time is strictly
  after the decision; it must be visible within ``max_execution_delay_ns`` of the decision and before the next decision
  (or evaluation end), otherwise the intent is ``UNFILLED``;
* gates: positive prices and quantities, ask > bid, spread <= ``max_spread_bps``, positive visible side depth;
* fill ratio (``visible_depth_linear_v1``): filled = min(requested, cap × visible side depth), truncated to scale 18;
  the remainder is cancelled; zero → ``REJECTED``;
* price: mid × (1 ± max(slippage_floor_bps, half_spread_bps + coefficient × participation_pct) / 10 000), where
  mid = (bid + ask) / 2, spread_bps = (ask − bid) / mid × 10 000 and participation_pct = filled / depth × 100;
* risk: an exposure-increasing fill is ``REJECTED`` (``risk_limit_exceeded``, never clipped) when its EXACT candidate
  post-fill equity — including this fill's own fee and its mark-to-market at the fill mark, computed from the exact
  candidate cost basis — is not positive, or when post-fill |q| × mark exceeds spec ``max_leverage`` × that candidate
  equity; one shared exact transition preview serves the decision and the applied transition, so a rejected fill
  leaves no fee, no transition and no state change;
* fee: every fill is taker; fee = fill_price × filled × taker_fee_bps / 10 000, always a cost;
* funding: each final settlement at most once; liability time = event_time + funding_interval_ns; the liable position
  is the one before any fill at the same nanosecond; cashflow = −q × mark(liability) × rate (positive rate: LONG pays,
  SHORT receives); the settlement grid must be spaced by the approved interval and EVERY governed grid liability
  inside EVERY liable interval — leading, interior and trailing alike — must be an actual settlement
  (``funding_coverage_incomplete``); a record whose ``finalized_at_ns`` precedes its own liability instant is ``FAIL``
  (``funding_finalized_before_cycle_close``), because under the authenticated ``funding_cycle_closed`` finality a
  final rate cannot exist before its own cycle closed; settlement itself stays at the governed liability instant even
  when the archive finalizes or publishes the record later (ex-post settlement accounting);
* valuation: latest visible mark (by event time) not older than ``max_mark_staleness_ns``; observations at the initial
  anchor, every fill, every settlement, every UTC day boundary (integer nanoseconds) and evaluation end;
  equity = initial_equity + realized gross − fees + funding + unrealized;
* terminal: no forced close; an open excursion is an OPEN trade with its unrealized MTM.

Canonical event order: time, then class (FUNDING_SETTLEMENT < DECISION < FILL < UTC_DAY_BOUNDARY < EVALUATION_END), then
sequence. An unrepresentable derived value is ``FAIL`` (``economic_value_out_of_representation:<field>``). There is no
``decimal`` context and no float.

The result proves deterministic simulated historical economics under the approved policy only: not venue fill truth,
not edge, profitability, performance metrics or readiness. One assembly path serves the builder and verifier
reassembly; ``verify_historical_execution_economics`` re-proves every authority and re-derives every ledger. Total.

Stage-3 synthetic stress (``STRESS_PIT_TRANSFORM_V1``). ``simulate_historical_execution_stress`` re-runs THIS engine —
the same frozen decision trace, policy, fill model, fees, funding and valuation rules — over a declared, digest-bound
transformation of the authenticated observations of one READY + PASS result. It is a modeled synthetic scenario,
never an authenticated market event, and it never mutates or replaces the authenticated dataset. The historical
simulation itself is unchanged: its only six hooks (the mark and book observations it is constructed over, the
effective slippage, the observed book and the two admission hooks below) are identities.

* HIGH_VOLATILITY: every observed price is moved so that its log-deviation from the anchor mark ``m0`` (the latest mark
  visible at the evaluation start) is multiplied by exactly 3/2: ``p' = p × g`` with ``g = sqrt(p / m0)`` rendered once
  by exact integer square root at scale 18 (ROUND_HALF_EVEN with an exact tie); a book is moved by the ``g`` of its own
  mid, so its spread in bps is unchanged; depth and funding rates are unchanged; the effective slippage is multiplied
  by the governed slippage multiplier;
* LOW_LIQUIDITY: every visible side depth is multiplied by the governed depth multiplier (truncated toward zero on the
  quantity grid) and the effective slippage by the governed slippage multiplier;
* FLASH_CRASH: the shock instant ``tau`` is the earliest UTC day-boundary valuation of the authenticated result with
  the maximal gross leverage ``|q| × mark / equity``; every price observed in ``[tau, tau + recovery)`` is moved by the
  governed gap against the position held at ``tau`` (long: down, short: up), every book observed there has its depth
  multiplied by the governed depth multiplier and its effective slippage by the governed slippage multiplier, and the
  original path resumes at ``tau + recovery``. No liquidation is executed and no venue liquidation rule is modeled: a
  valuation inside the window whose exact equity is below the governed maintenance fraction × gross notional is
  recorded as a maintenance-zone breach. Without any exposure at a day boundary no shock is applied.

A stress outcome records the scenario, its anchors, the breach and the daily endpoint equities; it carries no pass or
fail and proves no venue mechanics, liquidation behavior or real-market stress.

Governed paper admission (``GOVERNED_PAPER_ADMISSION_HOOKS_V1``). ``simulate_historical_execution_governed_paper``
re-runs THIS engine over one authenticated READY + PASS result under one neutral ``HistoricalExecutionAdmissionSchedule``
(ordered disjoint windows, each with long and short post-fill ceilings and a reservation price, an optional
invalidation instant and the decision sequences whose entries are refused); the engine never learns which governance
produced the schedule. The two hooks only refuse:

* at the decision instant ``t0``: no window contains ``t0`` (``governed_paper_no_cycle_authority``), the schedule is
  invalidated at or before ``t0`` (``governed_paper_lifecycle_invalidated``), the window's ceiling on the intent's own
  side is zero, so that side is not permitted at all, exits included (``governed_paper_direction_not_authorized``), the
  intent adds to an open position on its own side (``governed_paper_same_side_add_unsupported``), the intent increases
  the magnitude of the position (an entry) and the schedule lists its decision sequence among the refused entries
  (``governed_paper_entry_safety_refused``; an exit or a reduction is never refused by that list), or its post-fill
  position exceeds the window's long or short ceiling (``governed_paper_unit_ceiling_exceeded``); the intent is
  ``REJECTED`` before any book is selected;
* at the fill instant ``tf``: no window contains ``tf`` (``governed_paper_no_cycle_authority_at_fill``), the schedule is
  invalidated at or before ``tf`` (``governed_paper_lifecycle_invalidated_before_fill``), the windows from the one that
  contained ``t0`` to the one that contains ``tf`` are not contiguous, so some intervening instant had no authority
  (``governed_paper_cycle_authority_discontinuous``), or ``filled × fill_price`` exceeds ``requested × L``, where ``L``
  is the reservation price of the window that contained ``t0`` (``governed_paper_price_ceiling_exceeded``); the fill is
  ``REJECTED`` exactly like a risk refusal: no fee, no transition and no state change.

Every ceiling and instant is the caller's declared value. The intent of the LAST decision, left ``UNFILLED`` only
because the evaluation end closed its window (``execution_window_closed``) or no later book exists in the dataset
(``no_eligible_book_observation``), is reported as PENDING: the evaluation end, not the market, ended it.
``historical_execution_governed_paper_prefix_digest`` is the content identity of every event strictly before one instant
with the run-derived identifiers removed, so a longer replay can prove that it preserved a shorter one. This engine
stays independent of every consumer: the governed outcome's public verifier belongs to the governed paper execution
contract, which re-proves it by typed identity against a re-run. ``build_historical_execution_economics`` and
``verify_historical_execution_economics`` never consult a schedule, and a governed outcome proves no venue fill,
execution permission or readiness.

Protective position management (``PROTECTIVE_POSITION_LIFECYCLE_V1``). A result built with a
``HistoricalPositionManagementPolicy`` and its authenticated ``HistoricalOhlcBarArchive`` is schema v2. The policy is
bound like the run and the economics policy (snapshot + anchor, re-proven) and applied identically by
``build_historical_execution_economics`` (the backtest), by the verifier and by every governed re-run, which derives it
from the result's own bindings. A result without one is schema v1, and its payload and digest are exactly the accepted
v1 ones. Under the policy:

* entry: an intent that opens a position from FLAT is admitted only when the DEC-7 ATR_4h reading at its decision
  instant is available (``position_management_atr_unavailable:<reason>``). Its opening fill must leave a positive LONG
  stop (``position_management_stop_price_not_positive``). That fill arms the excursion's protection: the basis is the
  opening fill price, the stop distance is ``1.5 x ATR_4h``, and the 24 h deadline is the opening fill instant + 24 h.
  Later fills of the same excursion never move the anchor, the basis or the stop. Under the DEC-9 reading the distance
  becomes ``d0 x 0.8^k`` after each complete 8 h period (k = 1, 2), so the stop never loosens. No human has approved
  that reading: a ``HUMAN_GOVERNANCE`` approval of a policy that applies it needs governance, so it runs only under a
  ``TEST_ONLY_SYNTHETIC`` position-management approval;
* triggers: the deadline itself, and a PIT-visible fresh mark at or beyond the stop in force (LONG: at or below, SHORT:
  at or above). The stop is evaluated at the opening fill, at every later mark visibility and at every tightening
  milestone. A trigger opens one close-only obligation per excursion; a later deadline is appended to an obligation
  a stop opened. A trigger is never a fill;
* attempts: at most one order is in flight at a time. An attempt is the whole open position, close-only, under the
  unchanged fill model (latency, next eligible book, spread, depth cap, slippage, impact, taker fee). It is a standing
  obligation: ``max_execution_delay_ns`` bounds the staleness of a decision intent, so an attempt waits for the first
  eligible book instead of expiring. A rejected or partial fill is re-attempted at its own instant. A governed refusal is
  re-attempted at the next protective window, and a book that only arrives at or after the evaluation end leaves the
  attempt pending (still in flight). A gap never fills at the stop price;
* decisions: while an attempt is in flight, every decision intent is refused
  (``position_management_protective_close_in_flight``). While an obligation is outstanding, an exposure-increasing
  intent or fill is refused (``position_management_protective_obligation_outstanding`` / ``..._at_fill``). A decision
  intent waiting for its book defers a triggered attempt until it resolves: at its fill, or, when unfilled, at
  ``min(decision + max_execution_delay_ns, its window end)``. Re-entry after a protective close is a fresh entry under
  every rule above, never an inherited one;
* ledgers: every excursion protection, obligation (its triggers, its attempts, how and when it was discharged, or that
  it is still outstanding, with the exact breach duration) and attempt, digest-bound. Protective fills share the fill,
  fee, transition, valuation and trade ledgers; a protective fill's ``decision_digest`` is the id of the obligation it
  serves.

Equal-instant order under the policy (``funding_then_protective_then_decision_then_fill_then_valuation_v1``):
funding settlement, then protective rules (deadline, tightening, stop, attempt), then decisions, then fills, then the
day-boundary and end valuations. A settlement therefore always binds the position held before any fill at its
nanosecond, as in v1. In a governed re-run, schedule v3 adds the neutral protective windows (DEC-1): a protective
attempt and its fill need a protective window, never a cycle window, a direction ceiling, the reservation price, the
entry refusals or the absence of an invalidation; outcome v3 carries the protective ledgers and the pending attempt.
The synthetic stress method does not support position-managed results and refuses them.

Information-time admission (``S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1``, schedule v4). The settlement ledger books a
funding settlement at its liability instant from its final rate, also when the archive publishes that rate later
(ex-post settlement accounting, unchanged): its cashflow, valuations, trades and terminal state. A liability and the
knowledge of its amount are different facts, so a governed re-run under schedule v4 (the v3 schedule of a
position-managed baseline) ADMITS on information time: at every admission instant ``t`` it reads the booked equity
minus every settlement whose final rate is not visible at ``t`` (the publication-visible equity), the same view the
decision portfolio records. An exposure-increasing fill is

* ``risk_limit_exceeded`` under the risk rule above, evaluated on that publication-visible candidate equity;
* refused (``governed_paper_position_concentration_exceeded_at_fill``) when its post-fill |q| × fill mark strictly
  exceeds 25% of that candidate equity (PRDV4 §1.21 NT-R04 and §8.2; equality admits). The bound reads the quantity
  actually filled, the execution price, this fill's own taker fee and the mark of the fill instant. It never reaches a
  reduction, a close or a protective close-only fill.

A final rate therefore reaches no intent, fill, transition, fee, protective record or snapshot before it is visible:
before its publication, two archives that differ only in that rate produce the same admissions and the same snapshots
(a booked amount outside the representation domain fails the whole run closed, like every ledger amount). Schedules v2
and v3 keep the accepted admission on the booked equity, unchanged.

Governed decision portfolio. ``simulate_historical_execution_governed_paper_decision_portfolio`` (schedule v4 only) is the
same governed re-run, which also records, at every decision of the frozen trace, the portfolio as known at that instant
BEFORE the decision is admitted (after the funding settlements and protective rules of the same nanosecond, before its
fills). Its outcome is byte-identical to ``simulate_historical_execution_governed_paper`` under the same schedule, and
the recording changes no ledger. One snapshot holds:

* the exact position, and whether an order (a decision intent or a protective attempt) is still in flight;
* the latest fresh visible mark of the instant, open position or not (none when none is fresh and positive);
* the NAV as known then: the publication-visible equity, with an open position valued at that mark (none needed while
  flat). ``unpublished_settlement_count`` counts the excluded settlements; their amounts are unknown at the instant, so
  the snapshot records none of them. The NAV is unavailable, with its ``nav_reason``, for an open position without a
  fresh mark and for an exact NAV outside the numeric policy's representation domain;
* the NAV at the start of the decision's UTC day, as known at the decision instant: the engine's own valuation at that
  UTC midnight (the initial valuation when the run starts exactly then, a day-boundary valuation otherwise), with the
  same unpublished settlements excluded. It is unavailable, never substituted, on a partial first day (the run started
  after that midnight), for a decision exactly at the boundary (the boundary valuation follows the decision) and when
  it lies outside the representation domain;
* the candidate: the position the decision's intent targets if admitted and filled in full (the current position when
  the decision makes no intent; a clamped intent targets flat) and, when it increases the magnitude of the position,
  its projected NAV: the NAV minus the candidate's own taker fee at that mark. The projection is unavailable, with its
  reason, without a fresh mark, without a NAV or outside the representation domain. It is the decision-time reading of
  the candidate; the fill-time bound above is the exact one.

Only admitted economic transitions earlier in the event order reach a snapshot: a rejected or unfilled intent leaves no
state, and no later mark, fill, rate or admission is read. Each amount is rendered once from exact state.
``simulate_historical_execution_governed_paper_derivation`` returns that portfolio together with the governed outcome of
the same one re-run, the exact values behind every rendered NAV of its snapshots and the equal-instant phase
(``HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES``) of every trade close, all in memory only: a consumer that compares a
strict threshold or orders one nanosecond's events (the kill-switch ladder) reads the engine's own exact state, never a
rendered amount or a timestamp alone.
"""

from __future__ import annotations

import bisect
import heapq
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_strategy_spec_admission import edge_strategy_spec_admission_from_payload
from crypto_core.validation.historical_decision_run import (
    HistoricalDecisionRecord,
    HistoricalDecisionRun,
    historical_decision_run_from_payload,
    historical_decision_run_payload_is_well_formed,
    historical_decision_run_to_dict,
    verify_historical_decision_run,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HISTORICAL_EXECUTION_MAX_WIRE_INT,
    HistoricalExecutionApprovalKind,
    HistoricalExecutionConformance,
    HistoricalExecutionEconomicsApproval,
    HistoricalExecutionEconomicsPolicy,
    HistoricalExecutionEconomicsPolicyError,
    canonical_historical_execution_economics_approval,
    historical_execution_decimal_is_canonical,
    historical_execution_economics_approval_mismatches,
    historical_execution_economics_policy_from_payload,
    historical_execution_economics_policy_payload_is_well_formed,
    historical_execution_economics_policy_to_dict,
    historical_execution_quantize_price,
    historical_execution_quantize_quantity,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
    verify_historical_execution_economics_policy,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcAtrReading,
    HistoricalOhlcBarArchive,
    historical_ohlc_bar_archive_from_payload,
    historical_ohlc_bar_archive_payload_is_well_formed,
    historical_ohlc_bar_archive_to_dict,
    historical_ohlc_wilder_atr,
    verify_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    historical_pit_dataset_from_payload,
    verify_historical_pit_dataset,
)
from crypto_core.validation.historical_position_management_policy import (
    MAX_HOLD_NS,
    STOP_ATR_MULTIPLE,
    TIGHTENING_FACTOR,
    TIGHTENING_PERIOD_NS,
    HistoricalPositionManagementApproval,
    HistoricalPositionManagementPolicy,
    HistoricalPositionManagementPolicyError,
    canonical_historical_position_management_approval,
    historical_position_management_approval_from_payload,
    historical_position_management_approval_mismatches,
    historical_position_management_methods_requiring_human_approval,
    historical_position_management_policy_from_payload,
    historical_position_management_policy_payload_is_well_formed,
    historical_position_management_policy_to_dict,
    historical_position_management_tightening_applied,
    verify_historical_position_management_policy,
)
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableParameterApproval,
    strategy_executable_binding_from_payload,
)

_SCHEMA_VERSION = "historical-execution-economics.v1"
_POSITION_MANAGED_SCHEMA_VERSION = "historical-execution-economics.v2"
_STRESS_SCHEMA_VERSION = "historical-execution-stress-outcome.v1"
_STRESS_METHOD_ID = "STRESS_PIT_TRANSFORM_V1"
_REASON_PREFIX = "historical_execution_economics"
_SELF_DIGEST_FIELD = "result_digest"
_STRESS_DIGEST_FIELD = "outcome_digest"
# HIGH_VOLATILITY multiplies log-price deviations from the anchor by exactly 3/2 (the PRDV4 §1.13 Stage 3 ``returns ×
# 1.5``), implemented as one exact scale-18 square root; no other return multiplier is representable in this method.
_HIGH_VOLATILITY_RETURN_MULTIPLIER = Fraction(3, 2)
_STRESS_SCALE_FACTOR = 10**18
_UTC_DAY_NS = 86_400_000_000_000
_BPS = Fraction(10_000)
_HUNDRED = Fraction(100)

# Equal-instant class order. Without a position-management policy there is no protective event, so the v1 order
# (funding < decision < fill < day boundary < end) is unchanged.
_PRIORITY_FUNDING = 0
_PRIORITY_PROTECTIVE = 1
_PRIORITY_DECISION = 2
_PRIORITY_FILL = 3
_PRIORITY_DAY_BOUNDARY = 4
_PRIORITY_END = 5
# The name of each equal-instant class, indexed by its priority: the phase a consumer orders one nanosecond's events by.
HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES: tuple[str, ...] = (
    "FUNDING",
    "PROTECTIVE",
    "DECISION",
    "FILL",
    "UTC_DAY_BOUNDARY",
    "EVALUATION_END",
)
_CURRENT_PROTECTION = 0  # the owner of a wake event: whichever protection is open when it fires

HISTORICAL_EXECUTION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("pbo_passed", False),
    ("stress_passed", False),
    ("performance_metrics_computed", False),
    ("external_archive_truth_proven", False),
    ("venue_fill_truth_proven", False),
    ("venue_facts_proven", False),
    ("semantic_equivalence_machine_proven", False),
    ("venue_orders_created", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_EXECUTION_NON_CLAIM_FLAGS)


class HistoricalExecutionEconomicsError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class HistoricalExecutionIntentAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE_LONG = "CLOSE_LONG"
    CLOSE_SHORT = "CLOSE_SHORT"


class HistoricalExecutionSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class HistoricalExecutionFillOutcome(str, Enum):
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    UNFILLED = "UNFILLED"


class HistoricalExecutionTransitionKind(str, Enum):
    OPEN = "OPEN"
    INCREASE = "INCREASE"
    REDUCE = "REDUCE"
    CLOSE = "CLOSE"


class HistoricalExecutionValuationKind(str, Enum):
    INITIAL = "INITIAL"
    FILL = "FILL"
    FUNDING_SETTLEMENT = "FUNDING_SETTLEMENT"
    UTC_DAY_BOUNDARY = "UTC_DAY_BOUNDARY"
    EVALUATION_END = "EVALUATION_END"


class HistoricalExecutionTradeStatus(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"


@dataclass(frozen=True)
class HistoricalExecutionIntent:
    """Deterministic target-delta intent for one P1 decision. Never an order; binds its decision digest."""

    intent_id: str
    decision_sequence: int
    decision_digest: str
    decision_time_ns: int
    resulting_direction: str
    target_quantity: str
    actual_quantity: str
    delta_quantity: str
    requested_quantity: str
    action: HistoricalExecutionIntentAction
    side: HistoricalExecutionSide
    close_only_clamped: bool
    earliest_execution_time_ns: int
    intent_digest: str


@dataclass(frozen=True)
class HistoricalExecutionFill:
    """Deterministic simulated fill outcome of one intent (filled, partial, rejected or unfilled)."""

    fill_id: str
    intent_id: str
    intent_digest: str
    decision_digest: str
    outcome: HistoricalExecutionFillOutcome
    reason: str
    side: HistoricalExecutionSide
    requested_quantity: str
    filled_quantity: str
    cancelled_quantity: str
    fill_ratio: str
    book_record_digest: str | None
    book_event_time_ns: int | None
    execution_time_ns: int | None
    best_bid_price: str | None
    best_ask_price: str | None
    mid_price: str | None
    spread_bps: str | None
    half_spread_bps: str | None
    side_visible_quantity: str | None
    max_executable_quantity: str | None
    participation_pct: str | None
    impact_bps: str | None
    effective_slippage_bps: str | None
    fill_price: str | None
    fill_notional: str | None
    fill_digest: str


@dataclass(frozen=True)
class HistoricalExecutionPositionTransition:
    """Signed position change produced by one executed fill; realized gross PnL on the closed part.

    ``prior_average_entry_price`` and ``post_average_entry_price`` are RENDERED VIEWS of the exact internal cost
    basis. The economics never read them back.
    """

    transition_id: str
    fill_digest: str
    transition_kind: HistoricalExecutionTransitionKind
    time_ns: int
    prior_quantity: str
    prior_average_entry_price: str | None
    delta_quantity: str
    post_quantity: str
    post_average_entry_price: str | None
    closed_quantity: str
    realized_gross_pnl: str
    transition_digest: str


@dataclass(frozen=True)
class HistoricalExecutionFeeCashflow:
    """Taker fee of one executed fill; ``fee_amount`` is always a non-negative cost."""

    fee_id: str
    fill_digest: str
    time_ns: int
    taker_fee_bps: str
    fill_notional: str
    fee_amount: str
    fee_digest: str


@dataclass(frozen=True)
class HistoricalExecutionFundingCashflow:
    """One final funding settlement applied to the liable signed position (positive rate: LONG pays)."""

    cashflow_id: str
    funding_record_digest: str
    funding_series_id: str
    funding_sequence_id: int
    funding_event_time_ns: int
    liability_time_ns: int
    funding_rate: str
    position_quantity: str
    mark_record_digest: str
    mark_price: str
    funding_notional: str
    cashflow_amount: str
    cashflow_digest: str


@dataclass(frozen=True)
class HistoricalExecutionValuation:
    """Mark-to-market equity observation at one canonical instant (every amount rendered from exact state)."""

    valuation_sequence: int
    valuation_kind: HistoricalExecutionValuationKind
    time_ns: int
    trigger_digest: str | None
    position_quantity: str
    average_entry_price: str | None
    mark_record_digest: str | None
    mark_price: str | None
    unrealized_pnl: str
    cumulative_realized_gross_pnl: str
    cumulative_fees: str
    cumulative_funding: str
    equity: str
    valuation_digest: str


@dataclass(frozen=True)
class HistoricalExecutionTrade:
    """One excursion FLAT → nonzero → ... → FLAT (CLOSED) or still open at evaluation end (OPEN)."""

    trade_id: str
    status: HistoricalExecutionTradeStatus
    direction: str
    start_time_ns: int
    end_time_ns: int | None
    entry_fill_digests: tuple[str, ...]
    exit_fill_digests: tuple[str, ...]
    fee_digests: tuple[str, ...]
    funding_cashflow_digests: tuple[str, ...]
    realized_gross_pnl: str
    total_fees: str
    total_funding: str
    realized_net_pnl: str
    unrealized_pnl: str | None
    terminal_valuation_digest: str | None
    trade_digest: str


@dataclass(frozen=True)
class HistoricalExecutionTerminalState:
    """Position and cumulative economics at evaluation end (no forced close)."""

    position_quantity: str
    average_entry_price: str | None
    open_trade_id: str | None
    end_valuation_digest: str
    cumulative_realized_gross_pnl: str
    cumulative_fees: str
    cumulative_funding: str
    unrealized_pnl: str
    equity: str


class HistoricalExecutionProtectiveTriggerKind(str, Enum):
    MAX_HOLD = "MAX_HOLD_24H"
    STOP = "STOP_ATR_4H"


class HistoricalExecutionProtectiveObligationStatus(str, Enum):
    DISCHARGED = "DISCHARGED"
    OUTSTANDING = "OUTSTANDING"


@dataclass(frozen=True)
class HistoricalExecutionStopLevel:
    """One stop level of an excursion, in force from ``effective_from_ns`` (tightening milestone ``milestone``)."""

    milestone: int
    effective_from_ns: int
    stop_distance: str
    stop_price: str


@dataclass(frozen=True)
class HistoricalExecutionExcursionProtection:
    """The position-management protection one excursion's opening fill armed (PROTECTIVE_POSITION_LIFECYCLE_V1).

    ``basis_price`` is the executed price of the opening fill and the ATR is the DEC-7 reading at the decision instant
    of the opening intent. Every amount is rendered once from exact state (artifact output). ``closed_at_ns`` is None
    while the excursion is still open at the evaluation end.
    """

    protection_id: str
    trade_id: str
    opening_intent_id: str
    opening_fill_digest: str
    direction: str
    opened_at_ns: int
    basis_price: str
    atr_method_id: str
    atr_interval_ns: int
    atr_at_ns: int
    atr_value: str
    atr_run_bar_count: int
    atr_latest_bar_close_ns: int
    atr_window_digest: str
    stop_atr_multiple: str
    stop_tightening_method_id: str
    stop_levels: tuple[HistoricalExecutionStopLevel, ...]
    max_hold_deadline_ns: int
    closed_at_ns: int | None
    closing_fill_digest: str | None
    obligation_id: str | None
    protection_digest: str


@dataclass(frozen=True)
class HistoricalExecutionProtectiveTrigger:
    """One protective trigger: the 24 h deadline, or a PIT-visible fresh mark at or beyond the stop in force."""

    trigger_kind: HistoricalExecutionProtectiveTriggerKind
    trigger_time_ns: int
    mark_record_digest: str | None
    mark_price: str | None
    stop_price: str | None
    stop_milestone: int | None


@dataclass(frozen=True)
class HistoricalExecutionProtectiveObligation:
    """One close-only protective obligation: its triggers, its attempts, and how (or whether) it was discharged.

    ``breach_duration_ns`` runs from the first trigger to the fill that left the position FLAT, or to the evaluation end
    while the obligation is still OUTSTANDING; ``outstanding_quantity`` is the signed position then.
    """

    obligation_id: str
    protection_id: str
    status: HistoricalExecutionProtectiveObligationStatus
    triggers: tuple[HistoricalExecutionProtectiveTrigger, ...]
    created_at_ns: int
    attempt_ids: tuple[str, ...]
    discharged_at_ns: int | None
    discharging_fill_digest: str | None
    outstanding_quantity: str
    breach_duration_ns: int
    obligation_digest: str


@dataclass(frozen=True)
class HistoricalExecutionProtectiveAttempt:
    """One close-only attempt of an obligation: the whole open position. Never an order, never a fill by itself."""

    attempt_id: str
    obligation_id: str
    attempt_sequence: int
    attempt_time_ns: int
    position_quantity: str
    requested_quantity: str
    action: HistoricalExecutionIntentAction
    side: HistoricalExecutionSide
    earliest_execution_time_ns: int
    attempt_digest: str


@dataclass(frozen=True)
class HistoricalExecutionPositionManagementInputs:
    """The position-management authorities one economics build consumes, each re-proven against its anchor."""

    policy: HistoricalPositionManagementPolicy
    expected_policy_digest: str
    approval: HistoricalPositionManagementApproval | None
    ohlc_archive: HistoricalOhlcBarArchive
    expected_ohlc_archive_digest: str


@dataclass(frozen=True)
class HistoricalExecutionEconomicsResult:
    """Immutable, digest-bound raw historical execution economics authority. Proves no edge or venue truth."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    result_id: str
    correlation_id: str
    run_binding: EdgeAuthorityBinding
    run_digest: str
    dataset_digest: str
    source_manifest_digest: str
    data_requirement_registry_digest: str
    executable_binding_digest: str
    strategy_spec_digest: str
    profile_semantics_digest: str
    parameter_assignment_digest: str
    parameter_approval: StrategyExecutableParameterApproval | None
    instrument: str
    market_type: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    policy_binding: EdgeAuthorityBinding
    economics_policy_digest: str
    economics_approval: HistoricalExecutionEconomicsApproval | None
    conformance: HistoricalExecutionConformance | None
    synthetic_test_facts_used: bool
    synthetic_test_approval_used: bool
    funding_series_id: str
    mark_series_id: str
    order_book_series_id: str
    intents: tuple[HistoricalExecutionIntent, ...]
    fills: tuple[HistoricalExecutionFill, ...]
    position_transitions: tuple[HistoricalExecutionPositionTransition, ...]
    fee_cashflows: tuple[HistoricalExecutionFeeCashflow, ...]
    funding_cashflows: tuple[HistoricalExecutionFundingCashflow, ...]
    valuations: tuple[HistoricalExecutionValuation, ...]
    trades: tuple[HistoricalExecutionTrade, ...]
    terminal_state: HistoricalExecutionTerminalState | None
    intent_ledger_digest: str
    fill_ledger_digest: str
    position_transition_ledger_digest: str
    fee_ledger_digest: str
    funding_ledger_digest: str
    valuation_ledger_digest: str
    trade_ledger_digest: str
    simulated_economics_computed: bool
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    result_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
    performance_data_consumed: bool = False
    oos_evidence_consumed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    pbo_passed: bool = False
    stress_passed: bool = False
    performance_metrics_computed: bool = False
    external_archive_truth_proven: bool = False
    venue_fill_truth_proven: bool = False
    venue_facts_proven: bool = False
    semantic_equivalence_machine_proven: bool = False
    venue_orders_created: bool = False
    # Schema v2 only (PROTECTIVE_POSITION_LIFECYCLE_V1): a v1 payload carries none of these fields.
    position_management_policy_binding: EdgeAuthorityBinding | None = None
    position_management_approval: HistoricalPositionManagementApproval | None = None
    ohlc_archive_binding: EdgeAuthorityBinding | None = None
    position_management_policy_digest: str = ""
    ohlc_archive_digest: str = ""
    synthetic_position_management_approval_used: bool = False
    stop_tightening_applied: bool = False
    excursion_protections: tuple[HistoricalExecutionExcursionProtection, ...] = ()
    protective_obligations: tuple[HistoricalExecutionProtectiveObligation, ...] = ()
    protective_attempts: tuple[HistoricalExecutionProtectiveAttempt, ...] = ()
    protection_ledger_digest: str = ""
    obligation_ledger_digest: str = ""
    attempt_ledger_digest: str = ""


_RESULT_V2_FIELDS = (
    "position_management_policy_binding",
    "position_management_approval",
    "ohlc_archive_binding",
    "position_management_policy_digest",
    "ohlc_archive_digest",
    "synthetic_position_management_approval_used",
    "stop_tightening_applied",
    "excursion_protections",
    "protective_obligations",
    "protective_attempts",
    "protection_ledger_digest",
    "obligation_ledger_digest",
    "attempt_ledger_digest",
)


class HistoricalExecutionStressScenarioKind(str, Enum):
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_LIQUIDITY = "LOW_LIQUIDITY"
    FLASH_CRASH = "FLASH_CRASH"


@dataclass(frozen=True)
class HistoricalExecutionStressScenario:
    """One declared synthetic Stage-3 transformation (``STRESS_PIT_TRANSFORM_V1``); never an authenticated event.

    Decimals are canonical scale-18 texts. A field the kind does not use holds its neutral value: the return multiplier
    is exactly ``1.5`` for HIGH_VOLATILITY and ``1`` otherwise, the depth multiplier is ``1`` for HIGH_VOLATILITY, and
    the gap, recovery and maintenance fraction are zero outside FLASH_CRASH. Governed minimums belong to the consumer's
    policy; this engine only defines and applies the transformation.
    """

    scenario_kind: HistoricalExecutionStressScenarioKind
    return_multiplier: str
    slippage_multiplier: str
    depth_multiplier: str
    gap_fraction: str
    recovery_ns: int
    maintenance_margin_fraction: str


@dataclass(frozen=True)
class HistoricalExecutionStressOutcome:
    """The deterministic, digest-bound outcome of one synthetic stress re-simulation. Modeled only; no pass or fail.

    ``daily_endpoint_equities`` are the rendered equities of the stressed run's INITIAL, every UTC day boundary and
    EVALUATION_END valuation, in order. ``simulated`` is False exactly when the stressed run could not be computed
    (``reason_codes`` says why); nothing is fabricated then.
    """

    schema_version: str
    stress_method_id: str
    scenario: HistoricalExecutionStressScenario
    scenario_digest: str
    baseline_result_id: str
    baseline_result_digest: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    simulated: bool
    anchor_mark_price: str | None
    shock_time_ns: int | None
    shock_direction: str
    maintenance_breached: bool
    first_breach_time_ns: int | None
    closed_trade_count: int
    rejected_fill_count: int
    daily_endpoint_equities: tuple[str, ...]
    daily_endpoint_digest: str
    reason_codes: tuple[str, ...]
    outcome_digest: str
    paper_only: bool = True
    authenticated_market_event: bool = False
    venue_liquidation_modeled: bool = False
    venue_facts_proven: bool = False
    stress_passed: bool = False
    live_ready: bool = False


# --- helpers ------------------------------------------------------------------------------------------------------------


class _EconomicFailure(Exception):
    """Internal: a data-driven FAIL discovered while simulating; never escapes the module."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalExecutionEconomicsError:
    return HistoricalExecutionEconomicsError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _is_neutral(value: object) -> bool:
    return (
        value is None
        or (type(value) is tuple and value == ())
        or (type(value) is str and value == "")
        or (type(value) is bool and value is False)
    )


def _to_payload(artifact: object) -> dict[str, object]:
    """The wire payload of one artifact. A versioned artifact of its legacy schema carries exactly its legacy fields.

    An artifact of a legacy schema version that holds a non-neutral extension field is never serialized (``ValueError``),
    so a forged extension can never hide behind the legacy payload.
    """

    payload = {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]
    versioned = _VERSIONED_PAYLOADS.get(type(artifact))
    if versioned is not None and getattr(artifact, "schema_version", None) == versioned[0]:
        for name in versioned[1]:
            if not _is_neutral(getattr(artifact, name)):
                raise ValueError(f"{_REASON_PREFIX}:legacy_schema_carries_an_extension_field:{name}")
            del payload[name]
    return payload


def _sealed(record: object, digest_field: str) -> object:
    return replace(record, **{digest_field: edge_payload_digest(_to_payload(record), digest_field)})  # type: ignore[type-var]


def _ledger_digest(records: Sequence[object]) -> str:
    return edge_sha256_text(edge_canonical_json([_to_payload(record) for record in records]))


def _derived_id(kind: str, *parts: object) -> str:
    return edge_sha256_text(edge_canonical_json([kind, *parts]))


def _amount(value: Fraction, field_name: str) -> str:
    """Render one exact value as artifact output. The result is never read back into accounting state."""

    rendered = historical_execution_render_amount(value)
    if rendered is None:
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return rendered


def _optional_amount(value: Fraction | None, field_name: str) -> str | None:
    return None if value is None else _amount(value, field_name)


def _price_on_grid(value: Fraction, field_name: str) -> tuple[Fraction, str]:
    """Quantize an executed price onto the scale-18 grid: the exact grid value and its canonical text together."""

    quantized = historical_execution_quantize_price(value)
    if quantized is None:
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return quantized


def _quantity_on_grid(value: Fraction, field_name: str) -> tuple[Fraction, str]:
    """Quantize an executable quantity onto the scale-18 grid (truncated toward zero), value and text together."""

    quantized = historical_execution_quantize_quantity(value)
    if quantized is None:
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return quantized


def _wire_int(value: int, field_name: str) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return value


def _sign(value: Fraction) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _grid_instant_count(anchor: int, interval: int, low: int, high: int) -> int:
    """Number of governed grid instants ``anchor + m*interval`` inside the inclusive integer range ``[low, high]``."""

    if high < low:
        return 0
    last = (high - anchor) // interval
    first = -((anchor - low) // interval)
    return last - first + 1 if last >= first else 0


# --- authorities --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _RunContext:
    dataset: HistoricalPitDataset
    spec: StrategySpec
    data_requirement_registry_digest: str


def _run_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str
) -> tuple[list[str], HistoricalDecisionRun | None]:
    run = historical_decision_run_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_decision_run(run)
    if not verification.intact:
        return [_reason(f"run_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("run_digest_mismatch")], None
    if run.correlation_id != correlation_id:
        return [_reason("run_correlation_mismatch")], None
    if run.status is not EdgeEvidenceStatus.READY:
        return [_reason("run_rejected")], None
    return [], run


def _policy_authority(binding: EdgeAuthorityBinding) -> tuple[list[str], HistoricalExecutionEconomicsPolicy | None]:
    policy = historical_execution_economics_policy_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_execution_economics_policy(policy)
    if not verification.intact:
        return [_reason(f"policy_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("policy_digest_mismatch")], None
    if policy.status is not EdgeEvidenceStatus.READY:
        return [_reason("policy_rejected")], None
    return [], policy


def _run_context(run: HistoricalDecisionRun) -> tuple[list[str], _RunContext | None]:
    """Re-derive the authenticated dataset and StrategySpec from the verified run's own bindings."""

    try:
        dataset = historical_pit_dataset_from_payload(edge_authority_binding_snapshot(run.dataset_binding))
        executable = strategy_executable_binding_from_payload(edge_authority_binding_snapshot(run.executable_binding))
        admission = edge_strategy_spec_admission_from_payload(
            edge_authority_binding_snapshot(executable.admission_binding)
        )
        result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    except Exception:  # noqa: BLE001 - an underivable context is an integrity failure, never a receipt
        return [_reason("run_context_unavailable")], None
    if result.accepted is not True or type(result.spec) is not StrategySpec:
        return [_reason("run_strategy_spec_unavailable")], None
    if strategy_spec_digest(result.spec) != run.strategy_spec_digest:
        return [_reason("run_strategy_spec_digest_mismatch")], None
    return [], _RunContext(dataset, result.spec, dataset.data_requirement_registry_digest)


def _propagate(prefix: str, verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"{prefix}_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


def _max_leverage(spec: StrategySpec) -> tuple[Fraction | None, str | None]:
    """The exact leverage cap, or the reason it is unusable at this exact-numeric boundary.

    Only a positive native ``int`` is an exact representation of the digest-bound cap. ``float`` (even an integral
    one), ``bool`` and every other type are refused: this layer never coerces through ``repr``, ``float`` or a
    decimal context, and never invents a fractional-leverage encoding.
    """

    value = spec.risk_caps.get("max_leverage") if isinstance(spec.risk_caps, Mapping) else None
    if value is None:
        return None, "strategy_max_leverage_unavailable"
    if type(value) is int and 0 < value <= HISTORICAL_EXECUTION_MAX_WIRE_INT:
        return Fraction(value), None
    return None, "strategy_max_leverage_representation_unsupported"


def _unit_size(run: HistoricalDecisionRun) -> Fraction | None:
    values = [item.value for item in run.parameter_assignment if item.parameter_id == "unit_size"]
    if len(values) != 1 or not historical_execution_decimal_is_canonical(values[0]):
        return None
    unit = Fraction(values[0])
    return unit if unit > 0 else None


def _visibility(record: HistoricalPitRecord) -> int | None:
    if record.finalized_at_ns is None:
        return None
    return max(record.available_at_ns, record.finalized_at_ns)


def _select_series(
    dataset: HistoricalPitDataset, *, key: str, instrument: str, policy: HistoricalExecutionEconomicsPolicy
) -> tuple[list[str], str]:
    candidates = [
        item
        for item in dataset.series_semantics
        if item.data_requirement_key == key and instrument in item.instrument_coverage
    ]
    if not candidates:
        return [_reason(f"economic_series_missing:{key}")], ""
    if len(candidates) > 1:
        return [_reason(f"economic_series_ambiguous:{key}")], ""
    series = candidates[0]
    codes: list[str] = []
    if series.final_required is not True:
        codes.append(_reason(f"economic_series_not_final:{key}"))
    if series.revision_policy != policy.required_revision_policy:
        codes.append(_reason("economic_series_revision_semantics_unsupported"))
    return codes, series.series_id


def _economic_series(
    dataset: HistoricalPitDataset, run: HistoricalDecisionRun, policy: HistoricalExecutionEconomicsPolicy
) -> tuple[list[str], str, str]:
    codes: list[str] = []
    funding = [item for item in dataset.series_semantics if item.series_id == run.funding_series_id]
    if len(funding) != 1:
        codes.append(_reason(f"economic_series_missing:{policy.funding_data_key}"))
    elif funding[0].revision_policy != policy.required_revision_policy:
        codes.append(_reason("economic_series_revision_semantics_unsupported"))
    mark_codes, mark_series = _select_series(
        dataset, key=policy.mark_data_key, instrument=run.instrument, policy=policy
    )
    book_codes, book_series = _select_series(
        dataset, key=policy.order_book_data_key, instrument=run.instrument, policy=policy
    )
    codes.extend(mark_codes + book_codes)
    required = {
        run.funding_series_id: (policy.funding_value_name,),
        mark_series: (policy.mark_value_name,),
        book_series: (
            policy.best_bid_price_name,
            policy.best_ask_price_name,
            policy.best_bid_quantity_name,
            policy.best_ask_quantity_name,
        ),
    }
    for record in dataset.records:
        names = required.get(record.series_id) if record.instrument == run.instrument else None
        if names is None:
            continue
        present = {value.name for value in record.values}
        if not set(names) <= present:
            codes.append(_reason(f"economic_value_missing:{record.record_digest}"))
    return codes, mark_series, book_series


# --- exact accounting state -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Position:
    """EXACT internal accounting state: signed quantity and signed cost basis.

    The average entry price is derived (``cost_basis / quantity``) and never stored rounded. Nothing in this module
    reconstructs a ``_Position`` from a rendered artifact field.
    """

    quantity: Fraction
    cost_basis: Fraction

    @property
    def average(self) -> Fraction | None:
        return None if self.quantity == 0 else self.cost_basis / self.quantity

    def unrealized(self, mark: Fraction | None) -> Fraction:
        if self.quantity == 0 or mark is None:
            return Fraction(0)
        return self.quantity * mark - self.cost_basis


_FLAT = _Position(Fraction(0), Fraction(0))


@dataclass(frozen=True)
class _Transition:
    """Exact candidate position change of one priced fill; the risk decision and the applied change share it."""

    kind: HistoricalExecutionTransitionKind
    prior: _Position
    signed: Fraction
    price: Fraction
    post: _Position
    closed_quantity: Fraction
    realized_gross: Fraction
    cash_flow: Fraction


def _preview_transition(prior: _Position, signed: Fraction, price: Fraction) -> _Transition:
    """Pure exact transition arithmetic. No state mutation: a rejected fill leaves the position untouched.

    ``cash_flow`` is the signed cash effect of the fill (``-signed * price``); a closed excursion reconciles its
    realized gross PnL against the sum of its cashflows.
    """

    cash_flow = -signed * price
    if prior.quantity == 0:
        post = _Position(signed, signed * price)
        return _Transition(
            HistoricalExecutionTransitionKind.OPEN, prior, signed, price, post, Fraction(0), Fraction(0), cash_flow
        )
    if _sign(signed) == _sign(prior.quantity):
        post = _Position(prior.quantity + signed, prior.cost_basis + signed * price)
        return _Transition(
            HistoricalExecutionTransitionKind.INCREASE, prior, signed, price, post, Fraction(0), Fraction(0), cash_flow
        )
    closed = abs(signed)
    if closed > abs(prior.quantity):
        raise _EconomicFailure("position_cross_zero_unsupported")
    average = prior.cost_basis / prior.quantity
    realized = closed * (price - average) * _sign(prior.quantity)
    post_quantity = prior.quantity + signed
    if post_quantity == 0:
        return _Transition(
            HistoricalExecutionTransitionKind.CLOSE, prior, signed, price, _FLAT, closed, realized, cash_flow
        )
    post = _Position(post_quantity, average * post_quantity)
    return _Transition(
        HistoricalExecutionTransitionKind.REDUCE, prior, signed, price, post, closed, realized, cash_flow
    )


# --- simulation ---------------------------------------------------------------------------------------------------------


@dataclass
class _Ledgers:
    intents: list[HistoricalExecutionIntent] = field(default_factory=list)
    fills: list[HistoricalExecutionFill] = field(default_factory=list)
    transitions: list[HistoricalExecutionPositionTransition] = field(default_factory=list)
    fees: list[HistoricalExecutionFeeCashflow] = field(default_factory=list)
    funding: list[HistoricalExecutionFundingCashflow] = field(default_factory=list)
    valuations: list[HistoricalExecutionValuation] = field(default_factory=list)
    trades: list[HistoricalExecutionTrade] = field(default_factory=list)
    terminal: HistoricalExecutionTerminalState | None = None
    protections: list[HistoricalExecutionExcursionProtection] = field(default_factory=list)
    obligations: list[HistoricalExecutionProtectiveObligation] = field(default_factory=list)
    attempts: list[HistoricalExecutionProtectiveAttempt] = field(default_factory=list)
    pending_attempt: HistoricalExecutionProtectiveAttempt | None = None


@dataclass(frozen=True)
class _PositionManagement:
    """The verified position-management authorities one simulation applies."""

    policy: HistoricalPositionManagementPolicy
    archive: HistoricalOhlcBarArchive
    tightening: bool


@dataclass
class _Obligation:
    obligation_id: str
    created_at: int
    triggers: list[HistoricalExecutionProtectiveTrigger]
    attempt_ids: list[str] = field(default_factory=list)
    resume_at: int | None = None
    next_sequence: int = 0


@dataclass
class _Protection:
    sequence: int
    protection_id: str
    trade_id: str
    opening_intent_id: str
    opening_fill_digest: str
    sign: int
    opened_at: int
    basis: Fraction
    reading: HistoricalOhlcAtrReading
    levels: tuple[tuple[int, int, Fraction, Fraction], ...]  # (milestone, in force from, distance, stop price)
    deadline: int
    obligation: _Obligation | None = None


@dataclass(frozen=True)
class _Attempt:
    """A sealed protective attempt together with the EXACT quantity it requests."""

    record: HistoricalExecutionProtectiveAttempt
    requested: Fraction


@dataclass
class _Trade:
    trade_id: str
    direction: str
    start_time_ns: int
    entry_fills: list[str] = field(default_factory=list)
    exit_fills: list[str] = field(default_factory=list)
    fees: list[str] = field(default_factory=list)
    funding: list[str] = field(default_factory=list)
    realized_gross: Fraction = Fraction(0)
    total_fees: Fraction = Fraction(0)
    total_funding: Fraction = Fraction(0)
    cash_flow: Fraction = Fraction(0)


@dataclass(frozen=True)
class _Intent:
    """A sealed intent record together with the EXACT requested quantity it was derived from."""

    record: HistoricalExecutionIntent
    requested: Fraction


@dataclass(frozen=True)
class _Book:
    visibility: int
    record: HistoricalPitRecord
    bid: Fraction
    ask: Fraction
    bid_quantity: Fraction
    ask_quantity: Fraction


@dataclass(frozen=True)
class _Mark:
    visibility: int
    record: HistoricalPitRecord
    price: Fraction


class _MarkCursor:
    """Latest visible mark (by event time, then sequence) for non-decreasing query times."""

    def __init__(self, marks: list[_Mark], max_staleness_ns: int) -> None:
        self._marks = marks
        self._index = 0
        self._best: _Mark | None = None
        self._max_staleness_ns = max_staleness_ns

    def at(self, time_ns: int, purpose: str) -> _Mark:
        while self._index < len(self._marks) and self._marks[self._index].visibility <= time_ns:
            candidate = self._marks[self._index]
            key = (candidate.record.event_time_ns, candidate.record.sequence_id)
            if self._best is None or key > (self._best.record.event_time_ns, self._best.record.sequence_id):
                self._best = candidate
            self._index += 1
        if self._best is None:
            raise _EconomicFailure(f"mark_missing:{purpose}")
        if time_ns - self._best.record.event_time_ns > self._max_staleness_ns:
            raise _EconomicFailure(f"mark_stale:{purpose}")
        if self._best.price <= 0:
            raise _EconomicFailure(f"mark_price_invalid:{purpose}")
        return self._best


def _value(record: HistoricalPitRecord, name: str) -> Fraction:
    return Fraction(next(item.value for item in record.values if item.name == name))


class _Simulation:
    """One deterministic pass over the canonical event order. Raises ``_EconomicFailure`` on a data-driven FAIL."""

    def __init__(
        self,
        *,
        run: HistoricalDecisionRun,
        run_digest: str,
        dataset: HistoricalPitDataset,
        policy: HistoricalExecutionEconomicsPolicy,
        unit_size: Fraction,
        max_leverage: Fraction,
        mark_series: str,
        book_series: str,
        position_management: _PositionManagement | None = None,
    ) -> None:
        self.run = run
        self.run_digest = run_digest
        self.policy = policy
        self.pm = position_management
        self.unit_size = unit_size
        self.max_leverage = max_leverage
        self.latency = policy.latency_ns
        self.max_delay = policy.max_execution_delay_ns
        self.depth_cap = Fraction(policy.visible_depth_cap_fraction)
        self.max_spread = Fraction(policy.max_spread_bps)
        self.floor = Fraction(policy.slippage_floor_bps)
        self.impact = Fraction(policy.impact_coefficient_bps_per_participation_pct)
        self.fee_bps = Fraction(policy.taker_fee_bps)
        self.initial_equity = Fraction(policy.initial_equity)
        instrument = run.instrument
        self.funding = sorted(
            (r for r in dataset.records if r.series_id == run.funding_series_id and r.instrument == instrument),
            key=lambda record: record.sequence_id,
        )
        marks = [
            _Mark(visible, record, _value(record, policy.mark_value_name))
            for record in dataset.records
            if record.series_id == mark_series and record.instrument == instrument
            for visible in (_visibility(record),)
            if visible is not None
        ]
        marks.sort(key=lambda mark: (mark.visibility, mark.record.event_time_ns, mark.record.sequence_id))
        self.marks = self._transformed_marks(_MarkCursor(marks, policy.max_mark_staleness_ns))
        # The stop observations: the authenticated marks by visibility, each with the latest one visible with it (the
        # valuation rule). A position-managed result is never stressed, so these are never transformed.
        self.mark_visibilities = [mark.visibility for mark in marks]
        self.mark_best: list[_Mark] = []
        for mark in marks:
            best = self.mark_best[-1] if self.mark_best else None
            key = (mark.record.event_time_ns, mark.record.sequence_id)
            self.mark_best.append(
                mark if best is None or key > (best.record.event_time_ns, best.record.sequence_id) else best
            )
        books = [
            _Book(
                visible,
                record,
                _value(record, policy.best_bid_price_name),
                _value(record, policy.best_ask_price_name),
                _value(record, policy.best_bid_quantity_name),
                _value(record, policy.best_ask_quantity_name),
            )
            for record in dataset.records
            if record.series_id == book_series and record.instrument == instrument
            for visible in (_visibility(record),)
            if visible is not None
        ]
        books.sort(
            key=lambda book: (
                book.visibility,
                book.record.event_time_ns,
                book.record.sequence_id,
                book.record.record_digest,
            )
        )
        self.books = self._transformed_books(books)
        self.book_visibilities = [book.visibility for book in self.books]
        self.position = _FLAT
        self.realized = Fraction(0)
        self.fees = Fraction(0)
        self.funding_total = Fraction(0)
        self.trade: _Trade | None = None
        self.segments: list[tuple[int, Fraction]] = []
        self.settled: set[tuple[str, str, int]] = set()
        self.ledgers = _Ledgers()
        # Position management state (PROTECTIVE_POSITION_LIFECYCLE_V1); inert without a policy.
        self.end_ns = run.evaluation_end_ns
        self.events: list[tuple[int, int, int]] = []
        self.protection: _Protection | None = None
        self.protection_sequence = 0
        self.entry_readings: dict[str, HistoricalOhlcAtrReading] = {}
        self.decision_in_flight = False
        self.decision_busy_until: int | None = None
        self.attempt_in_flight = False
        self.event_owner: dict[int, int] = {}
        self.event_sequence = 0
        self.next_mark_check: tuple[int, int] | None = None
        self.protective_fills: dict[int, tuple[_Attempt, _Book]] = {}
        self.fill_index = len(run.decisions)  # protective fill events follow the decision indexes
        # Information-time admission and the governed decision portfolio (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1): a
        # governed re-run under schedule v4 only. The snapshots are recorded only when such a re-run asks for them, and
        # neither is ever part of a ledger.
        self.information_time = False
        self.decision_snapshots: list[HistoricalExecutionDecisionPortfolioSnapshot] | None = None
        self.day_start: tuple[int, Fraction] | None = None  # (instant, exact equity) of the latest day-start valuation
        self.settlements: list[tuple[int, int, Fraction]] = []  # (liability, rate visibility, exact cashflow)
        # The exact values behind each recorded snapshot, the priority of the event being applied and that of every
        # trade close (S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1): read by a governed derivation only, never a ledger.
        self.decision_exact_values: list[HistoricalExecutionDecisionExactValues] = []
        self.event_priority = -1
        self.trade_close_priorities: list[int] = []

    def _transformed_marks(self, marks: _MarkCursor) -> _MarkCursor:
        """Construction hook: the mark observations as the simulation reads them (identity; a stress run overrides)."""

        return marks

    def _transformed_books(self, books: list[_Book]) -> list[_Book]:
        """Construction hook: the book observations as the simulation reads them (identity; a stress run overrides)."""

        return books

    # -- exact identities --

    def _equity(
        self, unrealized: Fraction, *, realized: Fraction | None = None, fees: Fraction | None = None
    ) -> Fraction:
        """The one exact equity identity; a candidate state passes its own realized/fees totals."""

        realized = self.realized if realized is None else realized
        fees = self.fees if fees is None else fees
        return self.initial_equity + realized - fees + self.funding_total + unrealized

    # -- events --

    def _valuation(self, kind: HistoricalExecutionValuationKind, time_ns: int, trigger: str | None) -> None:
        mark = self.marks.at(time_ns, kind.value.lower()) if self.position.quantity != 0 else None
        unrealized = self.position.unrealized(None if mark is None else mark.price)
        equity = self._equity(unrealized)
        record = HistoricalExecutionValuation(
            valuation_sequence=len(self.ledgers.valuations),
            valuation_kind=kind,
            time_ns=time_ns,
            trigger_digest=trigger,
            position_quantity=_amount(self.position.quantity, "position_quantity"),
            average_entry_price=_optional_amount(self.position.average, "average_entry_price"),
            mark_record_digest=None if mark is None else mark.record.record_digest,
            mark_price=None if mark is None else _amount(mark.price, "mark_price"),
            unrealized_pnl=_amount(unrealized, "unrealized_pnl"),
            cumulative_realized_gross_pnl=_amount(self.realized, "cumulative_realized_gross_pnl"),
            cumulative_fees=_amount(self.fees, "cumulative_fees"),
            cumulative_funding=_amount(self.funding_total, "cumulative_funding"),
            equity=_amount(equity, "equity"),
            valuation_digest="",
        )
        self.ledgers.valuations.append(_sealed(record, "valuation_digest"))  # type: ignore[arg-type]
        if kind in (HistoricalExecutionValuationKind.INITIAL, HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY):
            self.day_start = (time_ns, equity)

    def _settle(self, record: HistoricalPitRecord, liability_ns: int) -> None:
        key = (record.series_id, record.instrument, record.sequence_id)
        if key in self.settled:
            raise _EconomicFailure("funding_settlement_duplicate")
        self.settled.add(key)
        if self.position.quantity == 0:
            return
        if record.finalized_at_ns is None:
            raise _EconomicFailure("funding_coverage_incomplete")
        mark = self.marks.at(liability_ns, "funding_settlement")
        rate = _value(record, self.policy.funding_value_name)
        notional = abs(self.position.quantity) * mark.price
        amount = -self.position.quantity * mark.price * rate
        cashflow = HistoricalExecutionFundingCashflow(
            cashflow_id=_derived_id("funding", self.run_digest, record.record_digest),
            funding_record_digest=record.record_digest,
            funding_series_id=record.series_id,
            funding_sequence_id=record.sequence_id,
            funding_event_time_ns=record.event_time_ns,
            liability_time_ns=liability_ns,
            funding_rate=_amount(rate, "funding_rate"),
            position_quantity=_amount(self.position.quantity, "position_quantity"),
            mark_record_digest=mark.record.record_digest,
            mark_price=_amount(mark.price, "mark_price"),
            funding_notional=_amount(notional, "funding_notional"),
            cashflow_amount=_amount(amount, "funding_cashflow_amount"),
            cashflow_digest="",
        )
        sealed: HistoricalExecutionFundingCashflow = _sealed(cashflow, "cashflow_digest")  # type: ignore[assignment]
        self.ledgers.funding.append(sealed)
        self.funding_total += amount
        if self.information_time:  # booked at the liability, its amount known only from its final rate's visibility
            self.settlements.append((liability_ns, _visibility(record), amount))  # type: ignore[arg-type]
        _amount(self.funding_total, "cumulative_funding")
        if self.trade is not None:
            self.trade.funding.append(sealed.cashflow_digest)
            self.trade.total_funding += amount
        self._valuation(HistoricalExecutionValuationKind.FUNDING_SETTLEMENT, liability_ns, sealed.cashflow_digest)

    def _intent(self, decision: HistoricalDecisionRecord) -> _Intent | None:
        direction = {"LONG": 1, "SHORT": -1, "FLAT": 0}.get(decision.resulting_direction)
        if direction is None:
            raise _EconomicFailure("decision_direction_unsupported")
        target = self.unit_size * direction
        actual = self.position.quantity
        delta = target - actual
        if delta == 0:
            return None
        clamped = actual != 0 and target != 0 and _sign(target) != _sign(actual)
        if clamped:
            delta = -actual
        post = actual + delta
        if delta > 0:
            side = HistoricalExecutionSide.BUY
            action = (
                HistoricalExecutionIntentAction.CLOSE_SHORT
                if actual < 0 and post == 0
                else HistoricalExecutionIntentAction.BUY
            )
        else:
            side = HistoricalExecutionSide.SELL
            action = (
                HistoricalExecutionIntentAction.CLOSE_LONG
                if actual > 0 and post == 0
                else HistoricalExecutionIntentAction.SELL
            )
        target_text = _amount(target, "target_quantity")
        actual_text = _amount(actual, "actual_quantity")
        delta_text = _amount(delta, "delta_quantity")
        earliest = _wire_int(decision.decision_time_ns + self.latency, "earliest_execution_time_ns")
        intent = HistoricalExecutionIntent(
            intent_id=_derived_id(
                "intent",
                self.run_digest,
                decision.decision_digest,
                decision.decision_sequence,
                target_text,
                actual_text,
                delta_text,
            ),
            decision_sequence=decision.decision_sequence,
            decision_digest=decision.decision_digest,
            decision_time_ns=decision.decision_time_ns,
            resulting_direction=decision.resulting_direction,
            target_quantity=target_text,
            actual_quantity=actual_text,
            delta_quantity=delta_text,
            requested_quantity=_amount(abs(delta), "requested_quantity"),
            action=action,
            side=side,
            close_only_clamped=clamped,
            earliest_execution_time_ns=earliest,
            intent_digest="",
        )
        sealed: HistoricalExecutionIntent = _sealed(intent, "intent_digest")  # type: ignore[assignment]
        self.ledgers.intents.append(sealed)
        return _Intent(sealed, abs(delta))

    def _select_book(self, intent: HistoricalExecutionIntent, boundary_ns: int) -> tuple[_Book | None, str]:
        index = bisect.bisect_left(self.book_visibilities, intent.earliest_execution_time_ns)
        while index < len(self.books):
            book = self.books[index]
            index += 1
            if book.record.event_time_ns <= intent.decision_time_ns:
                continue
            if book.visibility - intent.decision_time_ns > self.max_delay:
                return None, "execution_delay_expired"
            if book.visibility >= boundary_ns:
                return None, "execution_window_closed"
            return book, ""
        return None, "no_eligible_book_observation"

    def _fill_record(
        self, order: HistoricalExecutionIntent | HistoricalExecutionProtectiveAttempt, **values: object
    ) -> HistoricalExecutionFill:
        """One fill outcome of a decision intent, or of a protective attempt (whose obligation id is its decision)."""

        if type(order) is HistoricalExecutionProtectiveAttempt:
            intent_id, intent_digest, decision_digest = order.attempt_id, order.attempt_digest, order.obligation_id
        else:
            intent_id, intent_digest, decision_digest = order.intent_id, order.intent_digest, order.decision_digest  # type: ignore[union-attr]
        base: dict[str, object] = {
            "fill_id": _derived_id("fill", intent_id),
            "intent_id": intent_id,
            "intent_digest": intent_digest,
            "decision_digest": decision_digest,
            "side": order.side,
            "requested_quantity": order.requested_quantity,
            "filled_quantity": _amount(Fraction(0), "filled_quantity"),
            "cancelled_quantity": order.requested_quantity,
            "fill_ratio": _amount(Fraction(0), "fill_ratio"),
            "book_record_digest": None,
            "book_event_time_ns": None,
            "execution_time_ns": None,
            "best_bid_price": None,
            "best_ask_price": None,
            "mid_price": None,
            "spread_bps": None,
            "half_spread_bps": None,
            "side_visible_quantity": None,
            "max_executable_quantity": None,
            "participation_pct": None,
            "impact_bps": None,
            "effective_slippage_bps": None,
            "fill_price": None,
            "fill_notional": None,
            "fill_digest": "",
        }
        base.update(values)
        sealed: HistoricalExecutionFill = _sealed(HistoricalExecutionFill(**base), "fill_digest")  # type: ignore[arg-type,assignment]
        self.ledgers.fills.append(sealed)
        return sealed

    def _unfilled(self, order: HistoricalExecutionIntent | HistoricalExecutionProtectiveAttempt, reason: str) -> None:
        self._fill_record(order, outcome=HistoricalExecutionFillOutcome.UNFILLED, reason=reason)

    def _effective_slippage(self, effective: Fraction, book: _Book) -> Fraction:
        """The effective slippage of one fill; the historical model uses the governed value unchanged."""

        return effective

    def _observed_book(self, book: _Book) -> _Book:
        """The book observation one fill executes against; the historical model uses the authenticated record."""

        return book

    def _intent_admission(self, intent: _Intent) -> str | None:
        """Admission hook at the decision instant: a refusal reason, or None (the historical model admits every one)."""

        return None

    def _fill_admission(self, intent: _Intent, execution_time_ns: int, price: Fraction, filled: Fraction) -> str | None:
        """Admission hook at the fill instant: a refusal reason, or None (the historical model admits every fill)."""

        return None

    def _exposure_fill_admission(self, notional: Fraction, equity: Fraction) -> str | None:
        """Admission hook of an exposure-increasing fill past the risk rule, on its exact post-fill notional at the fill
        mark and its positive candidate equity: a refusal reason, or None (the historical model admits every one)."""

        return None

    def _unpublished_funding(self, time_ns: int) -> Fraction:
        """The booked cashflow of every settlement whose final rate is not visible at ``time_ns``.

        Every settlement booked so far is liable at or before ``time_ns``. Outside information time none is recorded, so
        this is exactly zero and an admission reads the booked equity, as accepted.
        """

        return sum((amount for _, visible, amount in self.settlements if visible > time_ns), Fraction(0))

    def _decision_snapshot(self, decision: HistoricalDecisionRecord, time_ns: int, intent: _Intent | None) -> None:
        """Record the portfolio as known at this decision instant, before its admission (only when asked to)."""

        if self.decision_snapshots is None:
            return
        # Every settlement so far is liable at or before this instant; one whose final rate is not visible yet is unknown.
        unpublished = [(liability, amount) for liability, visible, amount in self.settlements if visible > time_ns]
        quantity = self.position.quantity
        mark = self._fresh_mark(time_ns)
        exact = Fraction(0)
        nav: str | None = None
        nav_reason = "no_fresh_visible_mark"
        if quantity == 0 or mark is not None:
            unrealized = self.position.unrealized(None if mark is None else mark.price)
            exact = self._equity(unrealized) - self._unpublished_funding(time_ns)
            nav = historical_execution_render_amount(exact)
            nav_reason = "" if nav is not None else "nav_unrepresentable"
        # The candidate the decision's intent targets, and its entry projected at the fresh mark with its own taker fee.
        signed = Fraction(0)
        if intent is not None:
            signed = intent.requested if intent.record.side is HistoricalExecutionSide.BUY else -intent.requested
        candidate = quantity + signed
        candidate_nav: str | None = None
        candidate_reason = ""
        if abs(candidate) > abs(quantity):
            if mark is None:
                candidate_reason = "no_fresh_visible_mark"
            elif nav is None:
                candidate_reason = "nav_unavailable"
            else:
                candidate_nav = historical_execution_render_amount(
                    exact - abs(signed) * mark.price * self.fee_bps / _BPS
                )
                candidate_reason = "" if candidate_nav is not None else "candidate_nav_unrepresentable"
        day = time_ns // _UTC_DAY_NS * _UTC_DAY_NS
        day_nav: str | None = None
        day_exact = Fraction(0)
        if self.day_start is None or self.day_start[0] > day:
            reason = "partial_first_utc_day"
        elif self.day_start[0] < day:
            reason = "day_start_valued_after_the_decision"
        else:
            day_exact = self.day_start[1] - sum(
                (amount for liability, amount in unpublished if liability <= day), Fraction(0)
            )
            day_nav = historical_execution_render_amount(day_exact)
            reason = "" if day_nav is not None else "day_start_nav_unrepresentable"
        record = HistoricalExecutionDecisionPortfolioSnapshot(
            decision_sequence=decision.decision_sequence,
            decision_time_ns=time_ns,
            decision_digest=decision.decision_digest,
            position_quantity=_amount(quantity, "position_quantity"),
            order_in_flight=self.decision_in_flight or self.attempt_in_flight,
            mark_record_digest=None if mark is None else mark.record.record_digest,
            mark_price=None if mark is None else historical_execution_render_amount(mark.price),
            nav=nav,
            nav_reason=nav_reason,
            day_start_ns=day,
            day_start_nav=day_nav,
            day_start_reason=reason,
            unpublished_settlement_count=len(unpublished),
            candidate_position_quantity=_amount(candidate, "candidate_position_quantity"),
            candidate_nav=candidate_nav,
            candidate_nav_reason=candidate_reason,
            snapshot_digest="",
        )
        self.decision_snapshots.append(_sealed(record, "snapshot_digest"))  # type: ignore[arg-type]
        self.decision_exact_values.append(
            HistoricalExecutionDecisionExactValues(
                decision_sequence=decision.decision_sequence,
                nav=None if nav is None else exact,
                day_start_nav=None if day_nav is None else day_exact,
            )
        )

    # -- position management (PROTECTIVE_POSITION_LIFECYCLE_V1); every method below is inert without a policy --

    def _protective_admission(self, time_ns: int) -> str | None:
        """Admission hook of a protective attempt: a refusal reason, or None (the historical model admits every one)."""

        return None

    def _protective_fill_admission(self, time_ns: int) -> str | None:
        """Admission hook of a protective fill: a refusal reason, or None (the historical model admits every one)."""

        return None

    def _next_protective_window_start(self, time_ns: int) -> int | None:
        """The next instant a refused protective attempt may be retried, or None (no refusal exists historically)."""

        return None

    def _fresh_mark(self, time_ns: int) -> _Mark | None:
        """The latest mark visible at ``time_ns`` under the valuation rule, or None when none is fresh and positive."""

        index = bisect.bisect_right(self.mark_visibilities, time_ns)
        if not index:
            return None
        mark = self.mark_best[index - 1]
        if time_ns - mark.record.event_time_ns > self.policy.max_mark_staleness_ns or mark.price <= 0:
            return None
        return mark

    def _push_protective(self, time_ns: int, owner: int) -> None:
        """Schedule one protective evaluation; nothing protective happens at or after the evaluation end."""

        if time_ns >= self.end_ns:
            return
        index = self.event_sequence
        self.event_sequence += 1
        self.event_owner[index] = owner
        heapq.heappush(self.events, (time_ns, _PRIORITY_PROTECTIVE, index))

    def _push_next_mark_check(self, time_ns: int, protection: _Protection) -> None:
        index = bisect.bisect_right(self.mark_visibilities, time_ns)
        if index < len(self.mark_visibilities):
            check = (protection.sequence, self.mark_visibilities[index])
            if self.next_mark_check != check:
                self.next_mark_check = check
                self._push_protective(check[1], protection.sequence)

    def _busy(self, time_ns: int) -> bool:
        """Whether an order is unresolved at ``time_ns``: a decision fill or attempt in flight, or a waiting intent."""

        return (
            self.decision_in_flight
            or self.attempt_in_flight
            or (self.decision_busy_until is not None and time_ns < self.decision_busy_until)
        )

    def _position_management_admission(self, intent: _Intent) -> str | None:
        """The policy at a decision instant: nothing while a protective close is in flight, no increase while an
        obligation is outstanding, and an entry from FLAT only with an available ATR_4h at the decision instant."""

        pm = self.pm
        if pm is None:
            return None
        if self.attempt_in_flight:
            return "position_management_protective_close_in_flight"
        actual = self.position.quantity
        signed = intent.requested if intent.record.side is HistoricalExecutionSide.BUY else -intent.requested
        if abs(actual + signed) <= abs(actual):
            return None
        protection = self.protection
        if protection is not None and protection.obligation is not None:
            return "position_management_protective_obligation_outstanding"
        if actual != 0:
            return None
        reading = historical_ohlc_wilder_atr(
            pm.archive,
            interval_ns=pm.policy.atr_interval_ns,
            at_ns=intent.record.decision_time_ns,
            max_bar_age_ns=pm.policy.atr_max_bar_age_ns,
        )
        if not reading.available:
            return f"position_management_atr_unavailable:{reading.reason}"
        self.entry_readings[intent.record.intent_id] = reading
        return None

    def _position_management_fill_admission(self, intent: _Intent, price: Fraction, filled: Fraction) -> str | None:
        """The policy at a decision fill: no increase while an obligation is outstanding, and a positive LONG stop."""

        if self.pm is None:
            return None
        actual = self.position.quantity
        signed = filled if intent.record.side is HistoricalExecutionSide.BUY else -filled
        if abs(actual + signed) <= abs(actual):
            return None
        protection = self.protection
        if protection is not None and protection.obligation is not None:
            return "position_management_protective_obligation_outstanding_at_fill"
        if actual == 0:
            reading = self.entry_readings.get(intent.record.intent_id)
            if reading is None or reading.value is None:
                raise _EconomicFailure("position_management_open_without_atr")
            if signed > 0 and price - STOP_ATR_MULTIPLE * reading.value <= 0:
                return "position_management_stop_price_not_positive"
        return None

    def _arm_protection(self, fill: HistoricalExecutionFill, transition: _Transition, time_ns: int) -> None:
        """Arm the protection of the excursion this OPEN fill starts, then evaluate it at the fill instant."""

        pm = self.pm
        reading = self.entry_readings.get(fill.intent_id)
        if pm is None or reading is None or reading.value is None or self.trade is None:
            raise _EconomicFailure("position_management_open_without_atr")
        sign = _sign(transition.signed)
        distance = STOP_ATR_MULTIPLE * reading.value
        milestones = (0, 1, 2) if pm.tightening else (0,)
        levels = tuple(
            (
                milestone,
                _wire_int(time_ns + milestone * TIGHTENING_PERIOD_NS, "stop_effective_from_ns"),
                distance * TIGHTENING_FACTOR**milestone,
                transition.price - sign * distance * TIGHTENING_FACTOR**milestone,
            )
            for milestone in milestones
        )
        self.protection_sequence += 1
        protection = _Protection(
            sequence=self.protection_sequence,
            protection_id=_derived_id("protection", self.run_digest, fill.fill_digest),
            trade_id=self.trade.trade_id,
            opening_intent_id=fill.intent_id,
            opening_fill_digest=fill.fill_digest,
            sign=sign,
            opened_at=time_ns,
            basis=transition.price,
            reading=reading,
            levels=levels,
            deadline=_wire_int(time_ns + MAX_HOLD_NS, "max_hold_deadline_ns"),
        )
        self.protection = protection
        self._push_protective(protection.deadline, protection.sequence)
        for _, effective, _, _ in levels[1:]:
            self._push_protective(effective, protection.sequence)
        self._protective_step(time_ns)
        if self.protection is protection and protection.obligation is None:
            self._push_next_mark_check(time_ns, protection)

    def _stop_level(self, protection: _Protection, time_ns: int) -> tuple[int, int, Fraction, Fraction]:
        return [level for level in protection.levels if level[1] <= time_ns][-1]

    def _protective_event(self, time_ns: int, index: int) -> None:
        owner = self.event_owner.pop(index)
        protection = self.protection
        if protection is None or owner not in (_CURRENT_PROTECTION, protection.sequence):
            return
        self._protective_step(time_ns)
        if self.protection is protection and protection.obligation is None:
            self._push_next_mark_check(time_ns, protection)

    def _protective_step(self, time_ns: int) -> None:
        """Every protective rule at one instant: the 24 h deadline, the stop in force, then at most one attempt."""

        protection = self.protection
        if protection is None:
            return
        existing = protection.obligation
        triggers: list[HistoricalExecutionProtectiveTrigger] = []
        if time_ns >= protection.deadline and (
            existing is None
            or all(
                item.trigger_kind is not HistoricalExecutionProtectiveTriggerKind.MAX_HOLD for item in existing.triggers
            )
        ):
            triggers.append(
                HistoricalExecutionProtectiveTrigger(
                    HistoricalExecutionProtectiveTriggerKind.MAX_HOLD, protection.deadline, None, None, None, None
                )
            )
        if existing is None:
            milestone, _, _, level = self._stop_level(protection, time_ns)
            mark = self._fresh_mark(time_ns)
            if mark is not None and (mark.price <= level if protection.sign > 0 else mark.price >= level):
                triggers.append(
                    HistoricalExecutionProtectiveTrigger(
                        HistoricalExecutionProtectiveTriggerKind.STOP,
                        time_ns,
                        mark.record.record_digest,
                        _amount(mark.price, "mark_price"),
                        _amount(level, "stop_price"),
                        milestone,
                    )
                )
        for trigger in triggers:
            if protection.obligation is None:
                protection.obligation = _Obligation(
                    _derived_id("protective_obligation", self.run_digest, protection.protection_id),
                    trigger.trigger_time_ns,
                    [],
                    resume_at=trigger.trigger_time_ns,
                )
            protection.obligation.triggers.append(trigger)
        obligation = protection.obligation
        # A busy order re-evaluates the protection when it resolves: its fill, or the wake event at its window end.
        if (
            obligation is not None
            and obligation.resume_at is not None
            and obligation.resume_at <= time_ns
            and not self._busy(time_ns)
        ):
            self._issue_attempt(protection, obligation, time_ns)

    def _issue_attempt(self, protection: _Protection, obligation: _Obligation, time_ns: int) -> None:
        quantity = self.position.quantity
        if quantity == 0 or _sign(quantity) != protection.sign:
            raise _EconomicFailure("protective_state_inconsistent")
        long_position = quantity > 0
        sequence = obligation.next_sequence
        obligation.next_sequence += 1
        record = HistoricalExecutionProtectiveAttempt(
            attempt_id=_derived_id("protective_attempt", self.run_digest, obligation.obligation_id, sequence),
            obligation_id=obligation.obligation_id,
            attempt_sequence=sequence,
            attempt_time_ns=time_ns,
            position_quantity=_amount(quantity, "position_quantity"),
            requested_quantity=_amount(abs(quantity), "requested_quantity"),
            action=HistoricalExecutionIntentAction.CLOSE_LONG
            if long_position
            else HistoricalExecutionIntentAction.CLOSE_SHORT,
            side=HistoricalExecutionSide.SELL if long_position else HistoricalExecutionSide.BUY,
            earliest_execution_time_ns=_wire_int(time_ns + self.latency, "earliest_execution_time_ns"),
            attempt_digest="",
        )
        sealed: HistoricalExecutionProtectiveAttempt = _sealed(record, "attempt_digest")  # type: ignore[assignment]
        self.ledgers.attempts.append(sealed)
        obligation.attempt_ids.append(sealed.attempt_id)
        obligation.resume_at = None
        refused = self._protective_admission(time_ns)
        if refused is not None:
            self._fill_record(sealed, outcome=HistoricalExecutionFillOutcome.REJECTED, reason=refused)
            self._resume_after_refusal(protection, obligation, time_ns)
            return
        book, reason = self._select_protective_book(sealed)
        self.attempt_in_flight = True  # until its fill resolves, or, without a book before the end, to the end
        if book is None:
            self._unfilled(sealed, reason)
            self.ledgers.pending_attempt = sealed
            return
        index = self.fill_index
        self.fill_index += 1
        self.protective_fills[index] = (_Attempt(sealed, abs(quantity)), book)
        heapq.heappush(self.events, (book.visibility, _PRIORITY_FILL, index))

    def _resume_after_refusal(self, protection: _Protection, obligation: _Obligation, time_ns: int) -> None:
        start = self._next_protective_window_start(time_ns)
        if start is not None and start < self.end_ns:
            obligation.resume_at = start
            self._push_protective(start, protection.sequence)

    def _select_protective_book(self, attempt: HistoricalExecutionProtectiveAttempt) -> tuple[_Book | None, str]:
        """The first eligible book of a standing close-only attempt: no decision-staleness expiry applies to it."""

        index = bisect.bisect_left(self.book_visibilities, attempt.earliest_execution_time_ns)
        while index < len(self.books):
            book = self.books[index]
            index += 1
            if book.record.event_time_ns <= attempt.attempt_time_ns:
                continue
            if book.visibility >= self.end_ns:
                return None, "execution_window_closed"
            return book, ""
        return None, "no_eligible_book_observation"

    def _execute_protective(self, attempt: _Attempt, book: _Book) -> None:
        reason = self._fill_core(
            attempt.record,
            attempt.requested,
            book,
            admission=lambda price, filled, visibility: self._protective_fill_admission(visibility),
            close_only=True,
        )
        self.attempt_in_flight = False
        protection = self.protection
        if protection is None:  # the attempt left the position FLAT and discharged its obligation
            return
        obligation = protection.obligation
        if obligation is None:
            raise _EconomicFailure("protective_state_inconsistent")
        if reason.startswith(_GOVERNED_REASON_PREFIX):
            self._resume_after_refusal(protection, obligation, book.visibility)
            return
        obligation.resume_at = book.visibility
        self._protective_step(book.visibility)

    def _close_protection(self, fill: HistoricalExecutionFill, time_ns: int) -> None:
        protection = self.protection
        if protection is None:
            raise _EconomicFailure("protective_state_inconsistent")
        if protection.obligation is not None:
            self._finalize_obligation(
                protection, protection.obligation, discharged_at=time_ns, fill_digest=fill.fill_digest
            )
        self._finalize_protection(protection, closed_at=time_ns, fill_digest=fill.fill_digest)
        self.protection = None

    def _finalize_obligation(
        self, protection: _Protection, obligation: _Obligation, *, discharged_at: int | None, fill_digest: str | None
    ) -> None:
        ended = self.end_ns if discharged_at is None else discharged_at
        record = HistoricalExecutionProtectiveObligation(
            obligation_id=obligation.obligation_id,
            protection_id=protection.protection_id,
            status=HistoricalExecutionProtectiveObligationStatus.OUTSTANDING
            if discharged_at is None
            else HistoricalExecutionProtectiveObligationStatus.DISCHARGED,
            triggers=tuple(obligation.triggers),
            created_at_ns=obligation.created_at,
            attempt_ids=tuple(obligation.attempt_ids),
            discharged_at_ns=discharged_at,
            discharging_fill_digest=fill_digest,
            outstanding_quantity=_amount(
                self.position.quantity if discharged_at is None else Fraction(0), "outstanding_quantity"
            ),
            breach_duration_ns=_wire_int(ended - obligation.created_at, "breach_duration_ns"),
            obligation_digest="",
        )
        self.ledgers.obligations.append(_sealed(record, "obligation_digest"))  # type: ignore[arg-type]

    def _finalize_protection(self, protection: _Protection, *, closed_at: int | None, fill_digest: str | None) -> None:
        reading, pm = protection.reading, self.pm
        if pm is None or reading.value is None:
            raise _EconomicFailure("protective_state_inconsistent")
        record = HistoricalExecutionExcursionProtection(
            protection_id=protection.protection_id,
            trade_id=protection.trade_id,
            opening_intent_id=protection.opening_intent_id,
            opening_fill_digest=protection.opening_fill_digest,
            direction="LONG" if protection.sign > 0 else "SHORT",
            opened_at_ns=protection.opened_at,
            basis_price=_amount(protection.basis, "basis_price"),
            atr_method_id=reading.method_id,
            atr_interval_ns=reading.interval_ns,
            atr_at_ns=reading.at_ns,
            atr_value=_amount(reading.value, "atr_value"),
            atr_run_bar_count=reading.run_bar_count,
            atr_latest_bar_close_ns=reading.latest_bar_close_ns,  # type: ignore[arg-type]
            atr_window_digest=reading.window_digest,  # type: ignore[arg-type]
            stop_atr_multiple=_amount(STOP_ATR_MULTIPLE, "stop_atr_multiple"),
            stop_tightening_method_id=pm.policy.stop_tightening_method_id,
            stop_levels=tuple(
                HistoricalExecutionStopLevel(
                    milestone, effective, _amount(distance, "stop_distance"), _amount(price, "stop_price")
                )
                for milestone, effective, distance, price in protection.levels
            ),
            max_hold_deadline_ns=protection.deadline,
            closed_at_ns=closed_at,
            closing_fill_digest=fill_digest,
            obligation_id=None if protection.obligation is None else protection.obligation.obligation_id,
            protection_digest="",
        )
        self.ledgers.protections.append(_sealed(record, "protection_digest"))  # type: ignore[arg-type]

    def _execute(self, intent: _Intent, book: _Book) -> None:
        self._fill_core(
            intent.record,
            intent.requested,
            book,
            admission=lambda price, filled, visibility: (
                self._position_management_fill_admission(intent, price, filled)
                or self._fill_admission(intent, visibility, price, filled)
            ),
            close_only=False,
        )

    def _fill_core(
        self,
        order: HistoricalExecutionIntent | HistoricalExecutionProtectiveAttempt,
        requested: Fraction,
        book: _Book,
        *,
        admission: Callable[[Fraction, Fraction, int], str | None],
        close_only: bool,
    ) -> str:
        """The one fill model of every order; the rejection reason, or "" when the order executed."""

        book = self._observed_book(book)
        record = order
        observed = {
            "book_record_digest": book.record.record_digest,
            "book_event_time_ns": book.record.event_time_ns,
            "execution_time_ns": book.visibility,
        }

        def reject(reason: str, **extra: object) -> str:
            self._fill_record(
                record, outcome=HistoricalExecutionFillOutcome.REJECTED, reason=reason, **observed, **extra
            )
            return reason

        if book.bid <= 0 or book.ask <= 0 or book.bid_quantity < 0 or book.ask_quantity < 0:
            return reject("book_invalid")
        prices = {
            "best_bid_price": _amount(book.bid, "best_bid_price"),
            "best_ask_price": _amount(book.ask, "best_ask_price"),
        }
        if book.ask <= book.bid:
            return reject("book_crossed", **prices)
        mid = (book.bid + book.ask) / 2
        spread_bps = (book.ask - book.bid) / mid * _BPS
        half_spread_bps = spread_bps / 2
        quoted = {
            **prices,
            "mid_price": _amount(mid, "mid_price"),
            "spread_bps": _amount(spread_bps, "spread_bps"),
            "half_spread_bps": _amount(half_spread_bps, "half_spread_bps"),
        }
        if spread_bps > self.max_spread:
            return reject("spread_exceeds_max", **quoted)
        depth = book.ask_quantity if record.side is HistoricalExecutionSide.BUY else book.bid_quantity
        quoted["side_visible_quantity"] = _amount(depth, "side_visible_quantity")
        if depth <= 0:
            return reject("insufficient_depth", **quoted)
        maximum, maximum_text = _quantity_on_grid(self.depth_cap * depth, "max_executable_quantity")
        quoted["max_executable_quantity"] = maximum_text
        filled, filled_text = _quantity_on_grid(min(requested, maximum), "filled_quantity")
        if filled <= 0:
            return reject("insufficient_depth", **quoted)
        participation = filled / depth * _HUNDRED
        impact = self.impact * participation
        effective = self._effective_slippage(max(self.floor, half_spread_bps + impact), book)
        quoted.update(
            participation_pct=_amount(participation, "participation_pct"),
            impact_bps=_amount(impact, "impact_bps"),
            effective_slippage_bps=_amount(effective, "effective_slippage_bps"),
        )
        signed = filled if record.side is HistoricalExecutionSide.BUY else -filled
        raw_price = mid * (1 + effective / _BPS) if signed > 0 else mid * (1 - effective / _BPS)
        if raw_price <= 0:
            return reject("fill_price_non_positive", **quoted)
        price, price_text = _price_on_grid(raw_price, "fill_price")
        if price <= 0:
            return reject("fill_price_non_positive", **quoted)
        refused = admission(price, filled, book.visibility)
        if refused is not None:
            return reject(refused, **quoted)
        transition = _preview_transition(self.position, signed, price)
        if close_only and transition.kind not in (
            HistoricalExecutionTransitionKind.REDUCE,
            HistoricalExecutionTransitionKind.CLOSE,
        ):
            raise _EconomicFailure("protective_fill_not_close_only")
        fee_amount = price * filled * self.fee_bps / _BPS
        if abs(transition.post.quantity) > abs(self.position.quantity):
            mark = self.marks.at(book.visibility, "fill")
            # information time excludes every settlement whose final rate is not visible at the fill (otherwise none)
            candidate_equity = self._equity(
                transition.post.unrealized(mark.price),
                realized=self.realized + transition.realized_gross,
                fees=self.fees + fee_amount,
            ) - self._unpublished_funding(book.visibility)
            notional = abs(transition.post.quantity) * mark.price
            if candidate_equity <= 0 or notional > self.max_leverage * candidate_equity:
                return reject("risk_limit_exceeded", **quoted)
            refused = self._exposure_fill_admission(notional, candidate_equity)
            if refused is not None:
                return reject(refused, **quoted)
        outcome = (
            HistoricalExecutionFillOutcome.FILLED
            if filled == requested
            else HistoricalExecutionFillOutcome.PARTIALLY_FILLED
        )
        fill = self._fill_record(
            record,
            outcome=outcome,
            reason="filled" if filled == requested else "visible_depth_cap_partial_remainder_cancelled",
            filled_quantity=filled_text,
            cancelled_quantity=_amount(requested - filled, "cancelled_quantity"),
            fill_ratio=_amount(filled / requested, "fill_ratio"),
            fill_price=price_text,
            fill_notional=_amount(price * filled, "fill_notional"),
            **observed,
            **quoted,
        )
        fee: HistoricalExecutionFeeCashflow = _sealed(  # type: ignore[assignment]
            HistoricalExecutionFeeCashflow(
                fee_id=_derived_id("fee", fill.fill_digest),
                fill_digest=fill.fill_digest,
                time_ns=book.visibility,
                taker_fee_bps=self.policy.taker_fee_bps,
                fill_notional=fill.fill_notional,  # type: ignore[arg-type]
                fee_amount=_amount(fee_amount, "fee_amount"),
                fee_digest="",
            ),
            "fee_digest",
        )
        self.ledgers.fees.append(fee)
        self._apply(fill, fee, transition, fee_amount, book.visibility)
        return ""

    def _apply(
        self,
        fill: HistoricalExecutionFill,
        fee: HistoricalExecutionFeeCashflow,
        transition: _Transition,
        fee_amount: Fraction,
        time_ns: int,
    ) -> None:
        record: HistoricalExecutionPositionTransition = _sealed(  # type: ignore[assignment]
            HistoricalExecutionPositionTransition(
                transition_id=_derived_id("transition", fill.fill_digest),
                fill_digest=fill.fill_digest,
                transition_kind=transition.kind,
                time_ns=time_ns,
                prior_quantity=_amount(transition.prior.quantity, "prior_quantity"),
                prior_average_entry_price=_optional_amount(transition.prior.average, "average_entry_price"),
                delta_quantity=_amount(transition.signed, "delta_quantity"),
                post_quantity=_amount(transition.post.quantity, "post_quantity"),
                post_average_entry_price=_optional_amount(transition.post.average, "average_entry_price"),
                closed_quantity=_amount(transition.closed_quantity, "closed_quantity"),
                realized_gross_pnl=_amount(transition.realized_gross, "realized_gross_pnl"),
                transition_digest="",
            ),
            "transition_digest",
        )
        self.ledgers.transitions.append(record)
        self.position = transition.post
        self.realized += transition.realized_gross
        self.fees += fee_amount
        _amount(self.realized, "cumulative_realized_gross_pnl")
        _amount(self.fees, "cumulative_fees")
        if transition.kind is HistoricalExecutionTransitionKind.OPEN:
            self.trade = _Trade(
                _derived_id("trade", self.run_digest, fill.fill_digest),
                "LONG" if transition.signed > 0 else "SHORT",
                time_ns,
            )
        trade = self.trade
        if trade is None:
            raise _EconomicFailure("trade_state_inconsistent")
        if transition.kind in (HistoricalExecutionTransitionKind.OPEN, HistoricalExecutionTransitionKind.INCREASE):
            trade.entry_fills.append(fill.fill_digest)
        else:
            trade.exit_fills.append(fill.fill_digest)
        trade.fees.append(fee.fee_digest)
        trade.realized_gross += transition.realized_gross
        trade.total_fees += fee_amount
        trade.cash_flow += transition.cash_flow
        self.segments.append((time_ns, transition.post.quantity))
        self._valuation(HistoricalExecutionValuationKind.FILL, time_ns, fill.fill_digest)
        if transition.kind is HistoricalExecutionTransitionKind.CLOSE:
            self._close_trade(time_ns)
        if self.pm is not None:
            if transition.kind is HistoricalExecutionTransitionKind.OPEN:
                self._arm_protection(fill, transition, time_ns)
            elif transition.kind is HistoricalExecutionTransitionKind.CLOSE:
                self._close_protection(fill, time_ns)

    def _trade_record(
        self,
        trade: _Trade,
        status: HistoricalExecutionTradeStatus,
        end_time_ns: int | None,
        unrealized: str | None,
        terminal_valuation: str | None,
    ) -> HistoricalExecutionTrade:
        return _sealed(  # type: ignore[return-value]
            HistoricalExecutionTrade(
                trade_id=trade.trade_id,
                status=status,
                direction=trade.direction,
                start_time_ns=trade.start_time_ns,
                end_time_ns=end_time_ns,
                entry_fill_digests=tuple(trade.entry_fills),
                exit_fill_digests=tuple(trade.exit_fills),
                fee_digests=tuple(trade.fees),
                funding_cashflow_digests=tuple(trade.funding),
                realized_gross_pnl=_amount(trade.realized_gross, "trade_realized_gross_pnl"),
                total_fees=_amount(trade.total_fees, "trade_total_fees"),
                total_funding=_amount(trade.total_funding, "trade_total_funding"),
                realized_net_pnl=_amount(
                    trade.realized_gross - trade.total_fees + trade.total_funding, "trade_realized_net_pnl"
                ),
                unrealized_pnl=unrealized,
                terminal_valuation_digest=terminal_valuation,
                trade_digest="",
            ),
            "trade_digest",
        )

    def _close_trade(self, time_ns: int) -> None:
        trade = self.trade
        if trade is None:
            raise _EconomicFailure("trade_state_inconsistent")
        if trade.realized_gross != trade.cash_flow:
            raise _EconomicFailure("trade_cashflow_reconciliation_failed")
        self.ledgers.trades.append(
            self._trade_record(trade, HistoricalExecutionTradeStatus.CLOSED, time_ns, None, None)
        )
        self.trade_close_priorities.append(self.event_priority)
        self.trade = None

    def _liability(self, record: HistoricalPitRecord, interval: int) -> int:
        """Governed settlement instant of one funding window: event time + approved interval, inside the wire domain."""

        return _wire_int(record.event_time_ns + interval, "funding_liability_time_ns")

    def _check_funding_cycle_finality(self, interval: int) -> None:
        """A FINAL funding rate is authoritative only once its own cycle closes at the liability instant.

        The authenticated funding requirement declares ``event_time`` as the window open and finality as
        ``funding_cycle_closed``. A record claiming finality before that instant is a predicted rate wearing final
        semantics: the frozen P1 trace could act on it before the cycle closed and this layer would then book exactly
        that rate as settled economics. Fail closed for the whole result.
        """

        for record in self.funding:
            liability = self._liability(record, interval)
            if record.finalized_at_ns is not None and record.finalized_at_ns < liability:
                raise _EconomicFailure("funding_finalized_before_cycle_close")

    def _check_funding_grid(self, interval: int) -> None:
        """The approved interval must separate consecutive settlements of the authenticated series."""

        for earlier, later in zip(self.funding, self.funding[1:], strict=False):
            if later.event_time_ns - earlier.event_time_ns != interval:
                raise _EconomicFailure("funding_interval_inconsistent")

    def _check_funding_coverage(self, interval: int, start_ns: int, end_ns: int) -> None:
        """Every governed grid liability inside every liable interval must be an actual settlement.

        Coverage is decided against the GOVERNED GRID anchored on the retained settlements, never against the
        retained rows alone, so an omitted LEADING settlement (a position already funding-liable before the first
        retained record's liability) fails exactly like an omitted interior or trailing one. Counting is arithmetic,
        so a tiny interval over a long evaluation window cannot turn the check into an unbounded scan.
        """

        liabilities = [self._liability(record, interval) for record in self.funding]
        segments = [(start_ns, Fraction(0)), *self.segments]
        for index, (segment_start, quantity) in enumerate(segments):
            if quantity == 0:
                continue
            segment_end = segments[index + 1][0] if index + 1 < len(segments) else end_ns
            low, high = segment_start + 1, min(segment_end, end_ns - 1)
            if high < low:
                continue
            if not liabilities:
                raise _EconomicFailure("funding_coverage_incomplete")
            expected = _grid_instant_count(liabilities[0], interval, low, high)
            settled = bisect.bisect_right(liabilities, high) - bisect.bisect_left(liabilities, low)
            if expected != settled:
                raise _EconomicFailure("funding_coverage_incomplete")

    def run_all(self) -> _Ledgers:
        run = self.run
        start_ns, end_ns = run.evaluation_start_ns, run.evaluation_end_ns
        interval = self.policy.funding_interval_ns
        self._check_funding_grid(interval)
        self._check_funding_cycle_finality(interval)
        events = self.events
        for index, record in enumerate(self.funding):
            liability = self._liability(record, interval)
            if start_ns <= liability < end_ns:
                events.append((liability, _PRIORITY_FUNDING, index))
        decisions = run.decisions
        for index, decision in enumerate(decisions):
            events.append((decision.decision_time_ns, _PRIORITY_DECISION, index))
        boundary = (start_ns // _UTC_DAY_NS + 1) * _UTC_DAY_NS
        while boundary < end_ns:
            events.append((boundary, _PRIORITY_DAY_BOUNDARY, 0))
            boundary += _UTC_DAY_NS
        events.append((end_ns, _PRIORITY_END, 0))
        heapq.heapify(events)
        pending: dict[int, tuple[_Intent, _Book]] = {}
        self._valuation(HistoricalExecutionValuationKind.INITIAL, start_ns, None)
        while events:
            time_ns, priority, index = heapq.heappop(events)
            self.event_priority = priority
            if priority == _PRIORITY_FUNDING:
                self._settle(self.funding[index], time_ns)
            elif priority == _PRIORITY_PROTECTIVE:
                self._protective_event(time_ns, index)
            elif priority == _PRIORITY_DECISION:
                intent = self._intent(decisions[index])  # derived only: no state changes before its admission
                self._decision_snapshot(decisions[index], time_ns, intent)
                if intent is None:
                    continue
                refused = self._position_management_admission(intent)
                if refused is None:
                    refused = self._intent_admission(intent)
                if refused is not None:
                    self._fill_record(intent.record, outcome=HistoricalExecutionFillOutcome.REJECTED, reason=refused)
                    continue
                boundary_ns = decisions[index + 1].decision_time_ns if index + 1 < len(decisions) else end_ns
                book, reason = self._select_book(intent.record, boundary_ns)
                if book is None:
                    self._unfilled(intent.record, reason)
                    if self.pm is not None:  # the intent waits until its window ends: it defers protective attempts
                        resolution = min(intent.record.decision_time_ns + self.max_delay, boundary_ns)
                        self.decision_busy_until = resolution
                        self._push_protective(resolution, _CURRENT_PROTECTION)
                    continue
                pending[index] = (intent, book)
                self.decision_in_flight = True
                heapq.heappush(events, (book.visibility, _PRIORITY_FILL, index))
            elif priority == _PRIORITY_FILL:
                if index in pending:
                    intent, book = pending.pop(index)
                    self.decision_in_flight = False
                    self._execute(intent, book)
                    self._protective_step(time_ns)
                else:
                    attempt, book = self.protective_fills.pop(index)
                    self._execute_protective(attempt, book)
            elif priority == _PRIORITY_DAY_BOUNDARY:
                self._valuation(HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY, time_ns, None)
            else:
                self._valuation(HistoricalExecutionValuationKind.EVALUATION_END, time_ns, None)
        if self.protection is not None:  # an excursion still open at the evaluation end, its obligation outstanding
            if self.protection.obligation is not None:
                self._finalize_obligation(
                    self.protection, self.protection.obligation, discharged_at=None, fill_digest=None
                )
            self._finalize_protection(self.protection, closed_at=None, fill_digest=None)
        self._check_funding_coverage(interval, start_ns, end_ns)
        end = self.ledgers.valuations[-1]
        open_trade_id = None
        if self.trade is not None:
            open_trade_id = self.trade.trade_id
            self.ledgers.trades.append(
                self._trade_record(
                    self.trade,
                    HistoricalExecutionTradeStatus.OPEN,
                    None,
                    end.unrealized_pnl,
                    end.valuation_digest,
                )
            )
        self.ledgers.terminal = HistoricalExecutionTerminalState(
            position_quantity=end.position_quantity,
            average_entry_price=end.average_entry_price,
            open_trade_id=open_trade_id,
            end_valuation_digest=end.valuation_digest,
            cumulative_realized_gross_pnl=end.cumulative_realized_gross_pnl,
            cumulative_fees=end.cumulative_fees,
            cumulative_funding=end.cumulative_funding,
            unrealized_pnl=end.unrealized_pnl,
            equity=end.equity,
        )
        return self.ledgers


# --- Stage-3 synthetic stress (STRESS_PIT_TRANSFORM_V1) -------------------------------------------------------------


def _integer_sqrt(value: int) -> int:
    """``floor(sqrt(value))`` of a non-negative integer by exact integer Newton iteration (no float)."""

    if value < 2:
        return value
    root = 1 << ((value.bit_length() + 1) // 2)
    while True:
        candidate = (root + value // root) // 2
        if candidate >= root:
            return root
        root = candidate


def _scaled_sqrt(value: Fraction) -> Fraction:
    """``sqrt(value)`` rendered once at scale 18 by exact integer square root, ROUND_HALF_EVEN with an exact tie."""

    radicand = value.numerator * _STRESS_SCALE_FACTOR * _STRESS_SCALE_FACTOR
    root = _integer_sqrt(radicand // value.denominator)
    left = 4 * radicand
    right = value.denominator * (2 * root + 1) ** 2
    if left > right or (left == right and root % 2 == 1):
        root += 1
    return Fraction(root, _STRESS_SCALE_FACTOR)


def _scaled_depth(value: Fraction, multiplier: Fraction) -> Fraction:
    quantized = historical_execution_quantize_quantity(value * multiplier)
    if quantized is None:
        raise _EconomicFailure("economic_value_out_of_representation:stress_depth")
    return quantized[0]


class _ShockedMarks:
    """The mark observations of a FLASH_CRASH run: the authenticated cursor, gapped inside the shock window."""

    def __init__(self, inner: _MarkCursor, start: int, end: int, factor: Fraction) -> None:
        self._inner, self._start, self._end, self._factor = inner, start, end, factor

    def at(self, time_ns: int, purpose: str) -> _Mark:
        mark = self._inner.at(time_ns, purpose)
        if self._start <= time_ns < self._end:
            return _Mark(mark.visibility, mark.record, mark.price * self._factor)
        return mark


class _StressSimulation(_Simulation):
    """The historical simulation over one declared synthetic transformation of its authenticated observations."""

    def __init__(
        self,
        *,
        scenario: HistoricalExecutionStressScenario,
        anchor: Fraction | None,
        shock_time_ns: int | None,
        shock_factor: Fraction,
        **arguments: object,
    ) -> None:
        # The scenario is declared before the base construction, whose hooks below read it.
        kind = scenario.scenario_kind
        self.kind = kind
        self.anchor = anchor if anchor is not None and anchor > 0 else None
        self.slippage_multiplier = Fraction(scenario.slippage_multiplier)
        self.depth_multiplier = Fraction(scenario.depth_multiplier)
        self.maintenance_fraction = Fraction(scenario.maintenance_margin_fraction)
        self.shock_start = shock_time_ns
        self.shock_end = None if shock_time_ns is None else shock_time_ns + scenario.recovery_ns
        self.first_breach_ns: int | None = None
        self.shock_factor = shock_factor
        super().__init__(**arguments)  # type: ignore[arg-type]
        if kind is HistoricalExecutionStressScenarioKind.HIGH_VOLATILITY and self.anchor is None:
            raise _EconomicFailure("stress_anchor_mark_unavailable")

    def _transformed_marks(self, marks: _MarkCursor) -> _MarkCursor:
        if self.kind is HistoricalExecutionStressScenarioKind.HIGH_VOLATILITY:
            anchor = self.anchor
            if anchor is None:  # refused right after the base construction
                return marks
            return _MarkCursor(
                [
                    _Mark(mark.visibility, mark.record, mark.price * _scaled_sqrt(mark.price / anchor))
                    if mark.price > 0
                    else mark
                    for mark in marks._marks
                ],
                self.policy.max_mark_staleness_ns,
            )
        if self.kind is HistoricalExecutionStressScenarioKind.FLASH_CRASH and self.shock_start is not None:
            return _ShockedMarks(marks, self.shock_start, self.shock_end, self.shock_factor)  # type: ignore[return-value,arg-type]
        return marks

    def _transformed_books(self, books: list[_Book]) -> list[_Book]:
        if self.kind is HistoricalExecutionStressScenarioKind.HIGH_VOLATILITY:
            anchor = self.anchor
            if anchor is None:  # refused right after the base construction
                return books
            transformed = []
            for book in books:
                if book.bid <= 0 or book.ask <= 0:
                    transformed.append(book)
                    continue
                factor = _scaled_sqrt((book.bid + book.ask) / 2 / anchor)
                transformed.append(
                    _Book(
                        book.visibility,
                        book.record,
                        book.bid * factor,
                        book.ask * factor,
                        book.bid_quantity,
                        book.ask_quantity,
                    )
                )
            return transformed
        if self.kind is HistoricalExecutionStressScenarioKind.LOW_LIQUIDITY:
            return [
                _Book(
                    book.visibility,
                    book.record,
                    book.bid,
                    book.ask,
                    _scaled_depth(book.bid_quantity, self.depth_multiplier),
                    _scaled_depth(book.ask_quantity, self.depth_multiplier),
                )
                if book.bid_quantity >= 0 and book.ask_quantity >= 0
                else book
                for book in books
            ]
        return books

    def _in_shock(self, time_ns: int) -> bool:
        return self.shock_start is not None and self.shock_start <= time_ns < self.shock_end  # type: ignore[operator]

    def _effective_slippage(self, effective: Fraction, book: _Book) -> Fraction:
        if self.kind is HistoricalExecutionStressScenarioKind.FLASH_CRASH and not self._in_shock(book.visibility):
            return effective
        return effective * self.slippage_multiplier

    def _observed_book(self, book: _Book) -> _Book:
        if not self._in_shock(book.visibility) or book.bid_quantity < 0 or book.ask_quantity < 0:
            return book
        return _Book(
            book.visibility,
            book.record,
            book.bid * self.shock_factor,
            book.ask * self.shock_factor,
            _scaled_depth(book.bid_quantity, self.depth_multiplier),
            _scaled_depth(book.ask_quantity, self.depth_multiplier),
        )

    def _valuation(self, kind: HistoricalExecutionValuationKind, time_ns: int, trigger: str | None) -> None:
        super()._valuation(kind, time_ns, trigger)
        if self.position.quantity == 0 or not self._in_shock(time_ns):
            return
        mark = self.marks.at(time_ns, "stress_maintenance")
        equity = self._equity(self.position.unrealized(mark.price))
        if (
            equity < self.maintenance_fraction * abs(self.position.quantity) * mark.price
            and self.first_breach_ns is None
        ):
            self.first_breach_ns = time_ns


def canonical_historical_execution_stress_scenario(value: object) -> HistoricalExecutionStressScenario:
    """Validate one declared stress scenario exactly (kind, canonical decimals, neutral unused fields); raise otherwise."""

    if type(value) is not HistoricalExecutionStressScenario:
        raise _fail("stress_scenario_malformed")
    kind = value.scenario_kind
    if type(kind) is not HistoricalExecutionStressScenarioKind:
        raise _fail("stress_scenario_malformed:scenario_kind")
    names = (
        "return_multiplier",
        "slippage_multiplier",
        "depth_multiplier",
        "gap_fraction",
        "maintenance_margin_fraction",
    )
    for name in names:
        if not historical_execution_decimal_is_canonical(getattr(value, name)):
            raise _fail(f"stress_scenario_malformed:{name}")
    if not historical_execution_wire_int_is_valid(value.recovery_ns, minimum=0):
        raise _fail("stress_scenario_malformed:recovery_ns")
    returns, slippage, depth, gap, maintenance = (Fraction(getattr(value, name)) for name in names)
    high_volatility = kind is HistoricalExecutionStressScenarioKind.HIGH_VOLATILITY
    flash = kind is HistoricalExecutionStressScenarioKind.FLASH_CRASH
    checks = (
        ("return_multiplier", returns == (_HIGH_VOLATILITY_RETURN_MULTIPLIER if high_volatility else 1)),
        ("slippage_multiplier", slippage >= 1),
        ("depth_multiplier", 0 < depth <= 1 and (depth == 1 or not high_volatility)),
        ("gap_fraction", 0 < gap < 1 if flash else gap == 0),
        ("recovery_ns", value.recovery_ns > 0 if flash else value.recovery_ns == 0),
        ("maintenance_margin_fraction", 0 < maintenance < 1 if flash else maintenance == 0),
    )
    for name, holds in checks:
        if not holds:
            raise _fail(f"stress_scenario_invalid:{name}")
    return value


def historical_execution_stress_scenario_digest(scenario: HistoricalExecutionStressScenario) -> str:
    """The canonical digest of one validated stress scenario."""

    return edge_sha256_text(edge_canonical_json(_to_payload(canonical_historical_execution_stress_scenario(scenario))))


def _stress_anchor(
    dataset: HistoricalPitDataset,
    run: HistoricalDecisionRun,
    mark_series: str,
    policy: HistoricalExecutionEconomicsPolicy,
) -> Fraction | None:
    """The latest mark visible at the evaluation start (by event time, then sequence) within the staleness bound."""

    start = run.evaluation_start_ns
    best: HistoricalPitRecord | None = None
    for record in dataset.records:
        visible = (
            _visibility(record) if record.series_id == mark_series and record.instrument == run.instrument else None
        )
        if visible is None or visible > start:
            continue
        if best is None or (record.event_time_ns, record.sequence_id) > (best.event_time_ns, best.sequence_id):
            best = record
    if best is None or start - best.event_time_ns > policy.max_mark_staleness_ns:
        return None
    price = _value(best, policy.mark_value_name)
    return price if price > 0 else None


def _shock(result: HistoricalExecutionEconomicsResult) -> tuple[int | None, int]:
    """``(tau, position sign)``: the earliest UTC day boundary of maximal gross leverage, or ``(None, 0)`` when flat."""

    best: tuple[Fraction, int] | None = None
    sign = 0
    for valuation in result.valuations:
        if valuation.valuation_kind is not HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY:
            continue
        quantity = Fraction(valuation.position_quantity)
        if quantity == 0:
            continue
        equity = Fraction(valuation.equity)
        if valuation.mark_price is None or equity <= 0:
            raise _EconomicFailure("stress_baseline_exposure_unvaluable")
        leverage = abs(quantity) * Fraction(valuation.mark_price) / equity
        if best is None or leverage > best[0]:
            best, sign = (leverage, valuation.time_ns), _sign(quantity)
    return (None, 0) if best is None else (best[1], sign)


def _stress_outcome(
    result: HistoricalExecutionEconomicsResult,
    scenario: HistoricalExecutionStressScenario,
    *,
    simulated: bool,
    anchor: Fraction | None,
    shock_time_ns: int | None,
    shock_sign: int,
    ledgers: _Ledgers,
    first_breach_ns: int | None,
    reasons: Sequence[str],
) -> HistoricalExecutionStressOutcome:
    kinds = (
        HistoricalExecutionValuationKind.INITIAL,
        HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY,
        HistoricalExecutionValuationKind.EVALUATION_END,
    )
    endpoints = tuple(item.equity for item in ledgers.valuations if item.valuation_kind in kinds) if simulated else ()
    direction = {1: "PRICE_DOWN_AGAINST_LONG", -1: "PRICE_UP_AGAINST_SHORT"}.get(shock_sign, "NONE")
    seed = HistoricalExecutionStressOutcome(
        schema_version=_STRESS_SCHEMA_VERSION,
        stress_method_id=_STRESS_METHOD_ID,
        scenario=scenario,
        scenario_digest=historical_execution_stress_scenario_digest(scenario),
        baseline_result_id=result.result_id,
        baseline_result_digest=result.result_digest,
        evaluation_start_ns=result.evaluation_start_ns,
        evaluation_end_ns=result.evaluation_end_ns,
        simulated=simulated,
        anchor_mark_price=None if anchor is None else historical_execution_render_amount(anchor),
        shock_time_ns=shock_time_ns,
        shock_direction=direction,
        maintenance_breached=first_breach_ns is not None,
        first_breach_time_ns=first_breach_ns,
        closed_trade_count=sum(1 for item in ledgers.trades if item.status is HistoricalExecutionTradeStatus.CLOSED),
        rejected_fill_count=sum(1 for item in ledgers.fills if item.outcome is HistoricalExecutionFillOutcome.REJECTED),
        daily_endpoint_equities=endpoints,
        daily_endpoint_digest=edge_sha256_text(edge_canonical_json(list(endpoints))),
        reason_codes=_sorted_unique(reasons),
        outcome_digest="",
    )
    return replace(seed, outcome_digest=edge_payload_digest(_to_payload(seed), _STRESS_DIGEST_FIELD))


def simulate_historical_execution_stress(
    result: HistoricalExecutionEconomicsResult,
    *,
    expected_result_digest: str,
    scenario: HistoricalExecutionStressScenario,
) -> HistoricalExecutionStressOutcome:
    """Re-run this engine over one declared synthetic transformation of an authenticated READY + PASS result.

    The result is re-proven through ``verify_historical_execution_economics`` against the caller's anchor; its run,
    policy, approval, dataset and frozen decision trace are re-derived from its own bindings, never supplied. A
    malformed scenario or a non-authentic, non-computed result raises ``HistoricalExecutionEconomicsError``. A stressed
    run that cannot be computed (no anchor mark, an unrepresentable or stale value) is ``simulated=False`` with its
    reason; nothing is fabricated. Deterministic and pure.
    """

    scenario = canonical_historical_execution_stress_scenario(scenario)
    if type(result) is not HistoricalExecutionEconomicsResult:
        raise _fail("stress_baseline_malformed")
    verification = verify_historical_execution_economics(result)
    if not verification.intact or verification.recomputed_digest != expected_result_digest:
        raise _fail("stress_baseline_not_authentic")
    if result.schema_version != _SCHEMA_VERSION:
        raise _fail("stress_position_management_unsupported")
    if (
        result.status is not EdgeEvidenceStatus.READY
        or result.gate_verdict is not EdgeGateVerdict.PASS
        or result.simulated_economics_computed is not True
    ):
        raise _fail("stress_baseline_not_computed")
    codes, run = _run_authority(result.run_binding, correlation_id=result.correlation_id)
    policy_codes, policy = _policy_authority(result.policy_binding)
    context = None if run is None else _run_context(run)[1]
    unit_size = None if run is None else _unit_size(run)
    max_leverage = None if context is None else _max_leverage(context.spec)[0]
    if (
        codes
        or policy_codes
        or run is None
        or policy is None
        or context is None
        or unit_size is None
        or max_leverage is None
    ):
        raise _fail("stress_baseline_authority_unavailable")
    kind = scenario.scenario_kind
    anchor: Fraction | None = None
    shock_time_ns: int | None = None
    shock_sign = 0
    try:
        if kind is HistoricalExecutionStressScenarioKind.HIGH_VOLATILITY:
            anchor = _stress_anchor(context.dataset, run, result.mark_series_id, policy)
            if anchor is None:
                raise _EconomicFailure("stress_anchor_mark_unavailable")
        if kind is HistoricalExecutionStressScenarioKind.FLASH_CRASH:
            shock_time_ns, shock_sign = _shock(result)
        gap = Fraction(scenario.gap_fraction)
        simulation = _StressSimulation(
            scenario=scenario,
            anchor=anchor,
            shock_time_ns=shock_time_ns,
            shock_factor=1 - gap if shock_sign > 0 else 1 + gap,
            run=run,
            run_digest=result.run_digest,
            dataset=context.dataset,
            policy=policy,
            unit_size=unit_size,
            max_leverage=max_leverage,
            mark_series=result.mark_series_id,
            book_series=result.order_book_series_id,
        )
        ledgers = simulation.run_all()
    except _EconomicFailure as failure:
        return _stress_outcome(
            result,
            scenario,
            simulated=False,
            anchor=anchor,
            shock_time_ns=shock_time_ns,
            shock_sign=shock_sign,
            ledgers=_Ledgers(),
            first_breach_ns=None,
            reasons=(_reason(failure.code),),
        )
    return _stress_outcome(
        result,
        scenario,
        simulated=True,
        anchor=anchor,
        shock_time_ns=shock_time_ns,
        shock_sign=shock_sign,
        ledgers=ledgers,
        first_breach_ns=simulation.first_breach_ns,
        reasons=(),
    )


def historical_execution_stress_outcome_to_dict(outcome: HistoricalExecutionStressOutcome) -> dict[str, object]:
    """Canonical JSON-ready mapping of a stress outcome, including its self-digest."""

    return _to_payload(outcome)


def historical_execution_stress_outcome_digest(outcome: HistoricalExecutionStressOutcome) -> str:
    """Recompute the canonical stress outcome digest, excluding only ``outcome_digest``."""

    return edge_payload_digest(_to_payload(outcome), _STRESS_DIGEST_FIELD)


# --- governed paper admission (GOVERNED_PAPER_ADMISSION_HOOKS_V1) -----------------------------------------------------

HISTORICAL_EXECUTION_ADMISSION_SCHEDULE_SCHEMA_VERSION = "historical-execution-admission-schedule.v2"
_SCHEDULE_SCHEMA_VERSION = HISTORICAL_EXECUTION_ADMISSION_SCHEDULE_SCHEMA_VERSION
# Schedule v3 and outcome v3: the governed re-run of a position-managed (v2) baseline (PROTECTIVE_POSITION_LIFECYCLE_V1).
HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION = "historical-execution-admission-schedule.v3"
_PROTECTIVE_SCHEDULE_SCHEMA_VERSION = HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION
HISTORICAL_EXECUTION_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION = "historical-execution-governed-paper-outcome.v2"
_GOVERNED_SCHEMA_VERSION = HISTORICAL_EXECUTION_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION
HISTORICAL_EXECUTION_PROTECTIVE_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION = "historical-execution-governed-paper-outcome.v3"
_PROTECTIVE_GOVERNED_SCHEMA_VERSION = HISTORICAL_EXECUTION_PROTECTIVE_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION
# Schedule v4: the v3 schedule re-run on information time (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1, module docstring).
HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION = "historical-execution-admission-schedule.v4"
_INFORMATION_TIME_SCHEDULE_SCHEMA_VERSION = HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION
# PRDV4 §1.21 NT-R04 and §8.2: no single position strictly above 25% of NAV; schedule v4 enforces it at every fill.
HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP = Fraction(25, 100)
_GOVERNED_DIGEST_FIELD = "outcome_digest"
_PORTFOLIO_DIGEST_FIELD = "portfolio_digest"
_GOVERNED_REASON_PREFIX = "governed_paper_"
# The intent of the last decision is PENDING only when the evaluation end, not the market, left it unfilled.
_PENDING_REASONS = frozenset({"execution_window_closed", "no_eligible_book_observation"})


@dataclass(frozen=True)
class HistoricalExecutionAdmissionWindow:
    """One declared admission window ``[window_start_ns, window_end_ns)``; decimals are canonical scale-18 texts.

    The ceilings bound the post-fill position of an intent decided inside the window (long: ``max_long_quantity``,
    short: ``max_short_quantity``). ``reservation_price`` bounds ``filled × price`` by ``requested × reservation_price``
    for every fill of an intent this window decided, wherever that fill executes.
    """

    window_start_ns: int
    window_end_ns: int
    max_long_quantity: str
    max_short_quantity: str
    reservation_price: str


@dataclass(frozen=True)
class HistoricalExecutionProtectiveWindow:
    """One declared protective window ``[window_start_ns, window_end_ns)`` (DEC-1) and the authority that grants it.

    Inside it a close-only protective attempt and its fill are authorized. It never authorizes an entry, an increase or
    a decision intent of any kind.
    """

    window_start_ns: int
    window_end_ns: int
    authority_digest: str


@dataclass(frozen=True)
class HistoricalExecutionAdmissionSchedule:
    """One neutral declared admission schedule: ordered, disjoint windows and an optional invalidation instant.

    ``entry_refused_decision_sequences`` (strictly increasing) names the decisions whose entry is refused: an intent of
    such a decision that would increase the magnitude of the position is refused at its decision instant, while an
    exit or a reduction of an open position stays subject only to the other rules. ``protective_windows`` (schema v3
    and v4 only) are the ordered, disjoint DEC-1 protective windows of a position-managed baseline. Schema v4 carries
    exactly the v3 fields; its re-run admits on information time (see the module docstring).
    """

    schema_version: str
    schedule_id: str
    windows: tuple[HistoricalExecutionAdmissionWindow, ...]
    invalidated_from_ns: int | None
    entry_refused_decision_sequences: tuple[int, ...] = ()
    protective_windows: tuple[HistoricalExecutionProtectiveWindow, ...] = ()


HISTORICAL_EXECUTION_GOVERNED_PAPER_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("execution_authorized", False),
    ("venue_fill_truth_proven", False),
    ("venue_orders_created", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


@dataclass(frozen=True)
class HistoricalExecutionGovernedPaperOutcome:
    """This engine's re-run of one authenticated READY + PASS result under one declared admission schedule.

    ``simulated`` is False exactly when the governed run could not be computed (``reason_codes`` says why); its ledgers
    are then empty. ``governance_rejected_fill_digests`` are the fills the schedule refused, and
    ``pending_decision_sequence`` names the last decision when only the evaluation end left its intent unfilled. A
    deterministic simulation: never a venue fill, an execution permission or readiness.
    """

    schema_version: str
    schedule: HistoricalExecutionAdmissionSchedule
    schedule_digest: str
    baseline_result_id: str
    baseline_result_digest: str
    run_digest: str
    dataset_digest: str
    economics_policy_digest: str
    instrument: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    simulated: bool
    intents: tuple[HistoricalExecutionIntent, ...]
    fills: tuple[HistoricalExecutionFill, ...]
    position_transitions: tuple[HistoricalExecutionPositionTransition, ...]
    fee_cashflows: tuple[HistoricalExecutionFeeCashflow, ...]
    funding_cashflows: tuple[HistoricalExecutionFundingCashflow, ...]
    valuations: tuple[HistoricalExecutionValuation, ...]
    trades: tuple[HistoricalExecutionTrade, ...]
    terminal_state: HistoricalExecutionTerminalState | None
    intent_ledger_digest: str
    fill_ledger_digest: str
    position_transition_ledger_digest: str
    fee_ledger_digest: str
    funding_ledger_digest: str
    valuation_ledger_digest: str
    trade_ledger_digest: str
    governance_rejected_fill_digests: tuple[str, ...]
    pending_decision_sequence: int | None
    pending_intent_digest: str | None
    reason_codes: tuple[str, ...]
    outcome_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    venue_fill_truth_proven: bool = False
    venue_orders_created: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    # Schema v3 only (a position-managed baseline): a v2 payload carries none of these fields.
    excursion_protections: tuple[HistoricalExecutionExcursionProtection, ...] = ()
    protective_obligations: tuple[HistoricalExecutionProtectiveObligation, ...] = ()
    protective_attempts: tuple[HistoricalExecutionProtectiveAttempt, ...] = ()
    protection_ledger_digest: str = ""
    obligation_ledger_digest: str = ""
    attempt_ledger_digest: str = ""
    pending_protective_attempt_time_ns: int | None = None
    pending_protective_attempt_digest: str | None = None


HISTORICAL_EXECUTION_GOVERNED_PAPER_DECISION_PORTFOLIO_SCHEMA_VERSION = (
    "historical-execution-governed-paper-decision-portfolio.v1"
)


@dataclass(frozen=True)
class HistoricalExecutionDecisionPortfolioSnapshot:
    """The governed portfolio as known at one decision instant, before that decision is admitted.

    Every amount is rendered once from exact engine state. ``mark_*`` is the latest fresh visible mark of the instant
    (None when none is fresh and positive). ``nav`` and ``day_start_nav`` exclude the settlements whose final rate is not
    yet visible at the decision instant (``unpublished_settlement_count``; their amounts are unknown then and recorded
    nowhere here). ``nav`` is None with its ``nav_reason`` when an open position has no fresh visible mark or the exact
    NAV is outside the representation domain. ``day_start_nav`` is the NAV at ``day_start_ns``, the UTC midnight that
    starts the decision's day, and is None with its ``day_start_reason`` when the engine has not valued that instant
    before the decision or the amount is outside the representation domain. ``candidate_position_quantity`` is the
    position the decision's intent targets if admitted and filled in full; when it increases the magnitude of the
    position, ``candidate_nav`` is the NAV minus the candidate's own taker fee at the mark, or None with its
    ``candidate_nav_reason``. Without such a candidate both are absent (None, "").
    """

    decision_sequence: int
    decision_time_ns: int
    decision_digest: str
    position_quantity: str
    order_in_flight: bool
    mark_record_digest: str | None
    mark_price: str | None
    nav: str | None
    nav_reason: str
    day_start_ns: int
    day_start_nav: str | None
    day_start_reason: str
    unpublished_settlement_count: int
    candidate_position_quantity: str
    candidate_nav: str | None
    candidate_nav_reason: str
    snapshot_digest: str


@dataclass(frozen=True)
class HistoricalExecutionGovernedPaperDecisionPortfolio:
    """One snapshot per decision of the frozen trace, in order, from ONE governed re-run under one schedule v4.

    ``outcome_digest`` is that re-run's governed outcome, byte-identical to ``simulate_historical_execution_governed_paper``
    under the same schedule. ``simulated`` is False exactly when that re-run could not be computed, and then there is no
    snapshot. A deterministic paper record, never an account balance, a venue fact or an approved risk value.
    """

    schema_version: str
    schedule: HistoricalExecutionAdmissionSchedule
    schedule_digest: str
    baseline_result_id: str
    baseline_result_digest: str
    run_digest: str
    instrument: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    outcome_digest: str
    simulated: bool
    snapshots: tuple[HistoricalExecutionDecisionPortfolioSnapshot, ...]
    snapshot_ledger_digest: str
    reason_codes: tuple[str, ...]
    portfolio_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    venue_fill_truth_proven: bool = False
    venue_orders_created: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


@dataclass(frozen=True)
class HistoricalExecutionDecisionExactValues:
    """The exact amounts behind one decision snapshot's rendered ``nav`` and ``day_start_nav``, in memory only.

    Each is the exact engine value the snapshot renders once, and None exactly when the snapshot's is None. A rendered
    amount rounds half-even at scale 18, so a consumer comparing a strict threshold reads these, never the text. Never
    serialized, digested or an artifact.
    """

    decision_sequence: int
    nav: Fraction | None
    day_start_nav: Fraction | None


@dataclass(frozen=True)
class HistoricalExecutionGovernedPaperDerivation:
    """ONE governed re-run under one information-time schedule v4, in memory only: never serialized or digested.

    ``portfolio`` and ``outcome`` are byte-identical to ``simulate_historical_execution_governed_paper_decision_portfolio``
    and ``simulate_historical_execution_governed_paper`` under the same inputs. ``exact_values`` holds one entry per
    snapshot, in snapshot order. ``trade_close_phases`` holds one entry per CLOSED trade of the outcome, in the outcome's
    order (the order the engine closed them): the equal-instant phase (``HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES``) of
    the event that closed it. Both are empty when the re-run could not be computed.
    """

    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio
    outcome: HistoricalExecutionGovernedPaperOutcome
    exact_values: tuple[HistoricalExecutionDecisionExactValues, ...]
    trade_close_phases: tuple[str, ...]


_GOVERNED_V3_FIELDS = (
    "excursion_protections",
    "protective_obligations",
    "protective_attempts",
    "protection_ledger_digest",
    "obligation_ledger_digest",
    "attempt_ledger_digest",
    "pending_protective_attempt_time_ns",
    "pending_protective_attempt_digest",
)
# The legacy schema of each versioned artifact and the extension fields its legacy payload never carries.
_VERSIONED_PAYLOADS: dict[type, tuple[str, tuple[str, ...]]] = {
    HistoricalExecutionEconomicsResult: (_SCHEMA_VERSION, _RESULT_V2_FIELDS),
    HistoricalExecutionAdmissionSchedule: (_SCHEDULE_SCHEMA_VERSION, ("protective_windows",)),
    HistoricalExecutionGovernedPaperOutcome: (_GOVERNED_SCHEMA_VERSION, _GOVERNED_V3_FIELDS),
}


@dataclass(frozen=True)
class _Window:
    start: int
    end: int
    max_long: Fraction
    max_short: Fraction
    reservation_price: Fraction


class _GovernedPaperSimulation(_Simulation):
    """The historical simulation with one declared admission schedule applied at its two admission hooks."""

    def __init__(
        self,
        *,
        schedule: HistoricalExecutionAdmissionSchedule,
        record_decision_portfolio: bool = False,
        **arguments: object,
    ) -> None:
        self.windows = tuple(
            _Window(
                item.window_start_ns,
                item.window_end_ns,
                Fraction(item.max_long_quantity),
                Fraction(item.max_short_quantity),
                Fraction(item.reservation_price),
            )
            for item in schedule.windows
        )
        self.window_starts = [item.start for item in self.windows]
        self.invalidated_from = schedule.invalidated_from_ns
        self.entry_refusals = frozenset(schedule.entry_refused_decision_sequences)
        self.protective_windows = tuple(
            (item.window_start_ns, item.window_end_ns) for item in schedule.protective_windows
        )
        self.protective_starts = [start for start, _ in self.protective_windows]
        super().__init__(**arguments)  # type: ignore[arg-type]
        self.information_time = schedule.schema_version == _INFORMATION_TIME_SCHEDULE_SCHEMA_VERSION
        if record_decision_portfolio:
            self.decision_snapshots = []

    def _in_protective_window(self, time_ns: int) -> bool:
        index = bisect.bisect_right(self.protective_starts, time_ns) - 1
        return index >= 0 and time_ns < self.protective_windows[index][1]

    def _protective_admission(self, time_ns: int) -> str | None:
        """DEC-1: a protective close-only attempt needs a protective window, never a cycle, a ceiling or no invalidation."""

        return None if self._in_protective_window(time_ns) else "governed_paper_protective_authority_missing"

    def _protective_fill_admission(self, time_ns: int) -> str | None:
        return None if self._in_protective_window(time_ns) else "governed_paper_protective_authority_missing_at_fill"

    def _next_protective_window_start(self, time_ns: int) -> int | None:
        index = bisect.bisect_right(self.protective_starts, time_ns)
        return self.protective_starts[index] if index < len(self.protective_starts) else None

    def _window_index(self, time_ns: int) -> int | None:
        index = bisect.bisect_right(self.window_starts, time_ns) - 1
        if index < 0 or time_ns >= self.windows[index].end:
            return None
        return index

    def _invalidated(self, time_ns: int) -> bool:
        return self.invalidated_from is not None and self.invalidated_from <= time_ns

    def _intent_admission(self, intent: _Intent) -> str | None:
        decided = intent.record.decision_time_ns
        index = self._window_index(decided)
        if index is None:
            return "governed_paper_no_cycle_authority"
        if self._invalidated(decided):
            return "governed_paper_lifecycle_invalidated"
        window = self.windows[index]
        buying = intent.record.side is HistoricalExecutionSide.BUY
        if (window.max_long if buying else window.max_short) <= 0:
            return "governed_paper_direction_not_authorized"
        actual = self.position.quantity
        post = actual + intent.requested if buying else actual - intent.requested
        if actual != 0 and abs(post) > abs(actual):
            return "governed_paper_same_side_add_unsupported"
        if abs(post) > abs(actual) and intent.record.decision_sequence in self.entry_refusals:
            return "governed_paper_entry_safety_refused"
        if post > window.max_long or -post > window.max_short:
            return "governed_paper_unit_ceiling_exceeded"
        return None

    def _fill_admission(self, intent: _Intent, execution_time_ns: int, price: Fraction, filled: Fraction) -> str | None:
        index = self._window_index(execution_time_ns)
        if index is None:
            return "governed_paper_no_cycle_authority_at_fill"
        if self._invalidated(execution_time_ns):
            return "governed_paper_lifecycle_invalidated_before_fill"
        deciding = self._window_index(intent.record.decision_time_ns)
        if deciding is None or any(
            self.windows[item].end != self.windows[item + 1].start for item in range(deciding, index)
        ):
            return "governed_paper_cycle_authority_discontinuous"
        if filled * price > intent.requested * self.windows[deciding].reservation_price:
            return "governed_paper_price_ceiling_exceeded"
        return None

    def _exposure_fill_admission(self, notional: Fraction, equity: Fraction) -> str | None:
        """Schedule v4: the NT-R04 concentration bound on the exact post-fill position (strictly above 25% refuses)."""

        if self.information_time and notional > HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP * equity:
            return "governed_paper_position_concentration_exceeded_at_fill"
        return None


def canonical_historical_execution_admission_schedule(value: object) -> HistoricalExecutionAdmissionSchedule:
    """Validate one declared admission schedule exactly: types, canonical decimals and ordered disjoint windows."""

    if type(value) is not HistoricalExecutionAdmissionSchedule:
        raise _fail("admission_schedule_malformed")
    if type(value.schema_version) is not str or value.schema_version not in (
        _SCHEDULE_SCHEMA_VERSION,
        _PROTECTIVE_SCHEDULE_SCHEMA_VERSION,
        _INFORMATION_TIME_SCHEDULE_SCHEMA_VERSION,
    ):
        raise _fail("admission_schedule_malformed:schema_version")
    _canonical_protective_windows(value)
    _require_text(value.schedule_id, "schedule_id")
    if type(value.windows) is not tuple:
        raise _fail("admission_schedule_malformed:windows")
    previous_end: int | None = None
    for window in value.windows:
        if type(window) is not HistoricalExecutionAdmissionWindow:
            raise _fail("admission_schedule_malformed:window")
        for name in ("window_start_ns", "window_end_ns"):
            if not historical_execution_wire_int_is_valid(getattr(window, name), minimum=0):
                raise _fail(f"admission_schedule_malformed:{name}")
        for name in ("max_long_quantity", "max_short_quantity", "reservation_price"):
            if not historical_execution_decimal_is_canonical(getattr(window, name)):
                raise _fail(f"admission_schedule_malformed:{name}")
        if window.window_end_ns <= window.window_start_ns:
            raise _fail("admission_schedule_invalid:window_empty")
        if previous_end is not None and window.window_start_ns < previous_end:
            raise _fail("admission_schedule_invalid:windows_not_ordered_disjoint")
        if Fraction(window.max_long_quantity) < 0 or Fraction(window.max_short_quantity) < 0:
            raise _fail("admission_schedule_invalid:quantity_ceiling_negative")
        if Fraction(window.reservation_price) <= 0:
            raise _fail("admission_schedule_invalid:reservation_price_not_positive")
        previous_end = window.window_end_ns
    invalidated = value.invalidated_from_ns
    if invalidated is not None and not historical_execution_wire_int_is_valid(invalidated, minimum=0):
        raise _fail("admission_schedule_malformed:invalidated_from_ns")
    refused = value.entry_refused_decision_sequences
    if type(refused) is not tuple or any(
        not historical_execution_wire_int_is_valid(item, minimum=0) for item in refused
    ):
        raise _fail("admission_schedule_malformed:entry_refused_decision_sequences")
    if any(later <= earlier for earlier, later in zip(refused, refused[1:], strict=False)):
        raise _fail("admission_schedule_invalid:entry_refusals_not_strictly_increasing")
    return value


def _canonical_protective_windows(value: HistoricalExecutionAdmissionSchedule) -> None:
    windows = value.protective_windows
    if type(windows) is not tuple:
        raise _fail("admission_schedule_malformed:protective_windows")
    if value.schema_version == _SCHEDULE_SCHEMA_VERSION and windows:
        raise _fail("admission_schedule_malformed:protective_windows_need_schema_v3")
    previous_end: int | None = None
    for window in windows:
        if type(window) is not HistoricalExecutionProtectiveWindow:
            raise _fail("admission_schedule_malformed:protective_window")
        for name in ("window_start_ns", "window_end_ns"):
            if not historical_execution_wire_int_is_valid(getattr(window, name), minimum=0):
                raise _fail(f"admission_schedule_malformed:protective_{name}")
        if (
            type(window.authority_digest) is not str
            or len(window.authority_digest) != 64
            or not all(char in "0123456789abcdef" for char in window.authority_digest)
        ):
            raise _fail("admission_schedule_malformed:protective_authority_digest")
        if window.window_end_ns <= window.window_start_ns:
            raise _fail("admission_schedule_invalid:protective_window_empty")
        if previous_end is not None and window.window_start_ns < previous_end:
            raise _fail("admission_schedule_invalid:protective_windows_not_ordered_disjoint")
        previous_end = window.window_end_ns


def historical_execution_admission_schedule_to_dict(
    schedule: HistoricalExecutionAdmissionSchedule,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of a schedule (a v2 schedule carries exactly its v2 fields)."""

    return _to_payload(canonical_historical_execution_admission_schedule(schedule))


def historical_execution_admission_schedule_digest(schedule: HistoricalExecutionAdmissionSchedule) -> str:
    """The canonical digest of one validated admission schedule."""

    return edge_sha256_text(edge_canonical_json(historical_execution_admission_schedule_to_dict(schedule)))


@dataclass(frozen=True)
class _GovernedBaseline:
    """The authorities a governed re-run consumes, re-derived from the authenticated result's own bindings."""

    run: HistoricalDecisionRun
    policy: HistoricalExecutionEconomicsPolicy
    dataset: HistoricalPitDataset
    unit_size: Fraction
    max_leverage: Fraction
    position_management: _PositionManagement | None


def _governed_baseline(result: object, expected_result_digest: object) -> _GovernedBaseline:
    if type(result) is not HistoricalExecutionEconomicsResult:
        raise _fail("governed_paper_baseline_malformed")
    verification = verify_historical_execution_economics(result)
    if (
        not verification.intact
        or type(expected_result_digest) is not str
        or verification.recomputed_digest != expected_result_digest
    ):
        raise _fail("governed_paper_baseline_not_authentic")
    if (
        result.status is not EdgeEvidenceStatus.READY
        or result.gate_verdict is not EdgeGateVerdict.PASS
        or result.simulated_economics_computed is not True
    ):
        raise _fail("governed_paper_baseline_not_computed")
    codes, run = _run_authority(result.run_binding, correlation_id=result.correlation_id)
    policy_codes, policy = _policy_authority(result.policy_binding)
    context = None if run is None else _run_context(run)[1]
    unit_size = None if run is None else _unit_size(run)
    max_leverage = None if context is None else _max_leverage(context.spec)[0]
    position_management: _PositionManagement | None = None
    if result.position_management_policy_binding is not None:
        pm_codes, position_management = _position_management_authority(
            result.position_management_policy_binding, result.ohlc_archive_binding
        )
        codes = [*codes, *pm_codes]
    if (
        codes
        or policy_codes
        or run is None
        or policy is None
        or context is None
        or unit_size is None
        or max_leverage is None
        or (result.position_management_policy_binding is not None and position_management is None)
    ):
        raise _fail("governed_paper_baseline_authority_unavailable")
    return _GovernedBaseline(run, policy, context.dataset, unit_size, max_leverage, position_management)


def _pending_intent(run: HistoricalDecisionRun, ledgers: _Ledgers) -> HistoricalExecutionIntent | None:
    """The intent of the LAST decision when only the evaluation end left it unfilled; otherwise None."""

    if not run.decisions or not ledgers.intents:
        return None
    intent = ledgers.intents[-1]
    if intent.decision_sequence != run.decisions[-1].decision_sequence:
        return None
    outcomes = [item for item in ledgers.fills if item.intent_id == intent.intent_id]
    if (
        not outcomes
        or outcomes[-1].outcome is not HistoricalExecutionFillOutcome.UNFILLED
        or outcomes[-1].reason not in _PENDING_REASONS
    ):
        return None
    return intent


def _governed_outcome(
    result: HistoricalExecutionEconomicsResult,
    schedule: HistoricalExecutionAdmissionSchedule,
    *,
    simulated: bool,
    ledgers: _Ledgers,
    pending: HistoricalExecutionIntent | None,
    reasons: Sequence[str],
    protective: bool,
) -> HistoricalExecutionGovernedPaperOutcome:
    refused = tuple(
        item.fill_digest
        for item in ledgers.fills
        if item.outcome is HistoricalExecutionFillOutcome.REJECTED and item.reason.startswith(_GOVERNED_REASON_PREFIX)
    )
    attempt = ledgers.pending_attempt
    extension: dict[str, object] = {}
    if protective:
        extension = {
            "excursion_protections": tuple(ledgers.protections),
            "protective_obligations": tuple(ledgers.obligations),
            "protective_attempts": tuple(ledgers.attempts),
            "protection_ledger_digest": _ledger_digest(ledgers.protections),
            "obligation_ledger_digest": _ledger_digest(ledgers.obligations),
            "attempt_ledger_digest": _ledger_digest(ledgers.attempts),
            "pending_protective_attempt_time_ns": None if attempt is None else attempt.attempt_time_ns,
            "pending_protective_attempt_digest": None if attempt is None else attempt.attempt_digest,
        }
    seed = HistoricalExecutionGovernedPaperOutcome(
        schema_version=_PROTECTIVE_GOVERNED_SCHEMA_VERSION if protective else _GOVERNED_SCHEMA_VERSION,
        schedule=schedule,
        schedule_digest=historical_execution_admission_schedule_digest(schedule),
        baseline_result_id=result.result_id,
        baseline_result_digest=result.result_digest,
        run_digest=result.run_digest,
        dataset_digest=result.dataset_digest,
        economics_policy_digest=result.economics_policy_digest,
        instrument=result.instrument,
        evaluation_start_ns=result.evaluation_start_ns,
        evaluation_end_ns=result.evaluation_end_ns,
        simulated=simulated,
        intents=tuple(ledgers.intents),
        fills=tuple(ledgers.fills),
        position_transitions=tuple(ledgers.transitions),
        fee_cashflows=tuple(ledgers.fees),
        funding_cashflows=tuple(ledgers.funding),
        valuations=tuple(ledgers.valuations),
        trades=tuple(ledgers.trades),
        terminal_state=ledgers.terminal,
        intent_ledger_digest=_ledger_digest(ledgers.intents),
        fill_ledger_digest=_ledger_digest(ledgers.fills),
        position_transition_ledger_digest=_ledger_digest(ledgers.transitions),
        fee_ledger_digest=_ledger_digest(ledgers.fees),
        funding_ledger_digest=_ledger_digest(ledgers.funding),
        valuation_ledger_digest=_ledger_digest(ledgers.valuations),
        trade_ledger_digest=_ledger_digest(ledgers.trades),
        governance_rejected_fill_digests=refused,
        pending_decision_sequence=None if pending is None else pending.decision_sequence,
        pending_intent_digest=None if pending is None else pending.intent_digest,
        reason_codes=_sorted_unique(reasons),
        outcome_digest="",
        **extension,  # type: ignore[arg-type]
    )
    return replace(seed, outcome_digest=edge_payload_digest(_to_payload(seed), _GOVERNED_DIGEST_FIELD))


def simulate_historical_execution_governed_paper(
    result: HistoricalExecutionEconomicsResult,
    *,
    expected_result_digest: str,
    schedule: HistoricalExecutionAdmissionSchedule,
) -> HistoricalExecutionGovernedPaperOutcome:
    """Re-run this engine under one declared admission schedule over an authenticated READY + PASS result.

    The result is re-proven against the caller's anchor and its run, policy, dataset and frozen decision trace are
    re-derived from its own bindings, never supplied. A malformed schedule, a window outside the evaluation window or a
    non-authentic, non-computed result raises ``HistoricalExecutionEconomicsError``. A governed run that cannot be
    computed (an unrepresentable or stale value on its own path) is ``simulated=False`` with its reason. Pure.
    """

    return _governed_run(result, expected_result_digest, schedule, record_decision_portfolio=False)[0]


def _governed_run(
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    schedule: HistoricalExecutionAdmissionSchedule,
    *,
    record_decision_portfolio: bool,
) -> tuple[
    HistoricalExecutionGovernedPaperOutcome,
    tuple[HistoricalExecutionDecisionPortfolioSnapshot, ...],
    tuple[HistoricalExecutionDecisionExactValues, ...],
    tuple[str, ...],
]:
    """The one governed re-run: its outcome and, when asked to record them, its decision snapshots and the exact values
    behind them; with the equal-instant phase of every trade close (all empty when the re-run cannot be computed)."""

    schedule = canonical_historical_execution_admission_schedule(schedule)
    if record_decision_portfolio and schedule.schema_version != _INFORMATION_TIME_SCHEDULE_SCHEMA_VERSION:
        raise _fail("decision_portfolio_needs_the_information_time_schedule")
    baseline = _governed_baseline(result, expected_result_digest)
    protective = baseline.position_management is not None
    expected_schedules = (
        (_PROTECTIVE_SCHEDULE_SCHEMA_VERSION, _INFORMATION_TIME_SCHEDULE_SCHEMA_VERSION)
        if protective
        else (_SCHEDULE_SCHEMA_VERSION,)
    )
    if schedule.schema_version not in expected_schedules:
        raise _fail("admission_schedule_version_mismatch")
    if any(
        item.window_start_ns < result.evaluation_start_ns or item.window_end_ns > result.evaluation_end_ns
        for item in schedule.windows
    ):
        raise _fail("admission_schedule_outside_evaluation_window")
    try:
        simulation = _GovernedPaperSimulation(
            schedule=schedule,
            record_decision_portfolio=record_decision_portfolio,
            run=baseline.run,
            run_digest=result.run_digest,
            dataset=baseline.dataset,
            policy=baseline.policy,
            unit_size=baseline.unit_size,
            max_leverage=baseline.max_leverage,
            mark_series=result.mark_series_id,
            book_series=result.order_book_series_id,
            position_management=baseline.position_management,
        )
        ledgers = simulation.run_all()
    except _EconomicFailure as failure:
        failed = _governed_outcome(
            result,
            schedule,
            simulated=False,
            ledgers=_Ledgers(),
            pending=None,
            reasons=(_reason(failure.code),),
            protective=protective,
        )
        return failed, (), (), ()
    outcome = _governed_outcome(
        result,
        schedule,
        simulated=True,
        ledgers=ledgers,
        pending=_pending_intent(baseline.run, ledgers),
        reasons=(),
        protective=protective,
    )
    # a close outside every event (none occurs) has no phase: its absence misaligns the closes, which then prove nothing
    return (
        outcome,
        tuple(simulation.decision_snapshots or ()),
        tuple(simulation.decision_exact_values),
        tuple(
            HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES[item] for item in simulation.trade_close_priorities if item >= 0
        ),
    )


def simulate_historical_execution_governed_paper_decision_portfolio(
    result: HistoricalExecutionEconomicsResult,
    *,
    expected_result_digest: str,
    schedule: HistoricalExecutionAdmissionSchedule,
) -> HistoricalExecutionGovernedPaperDecisionPortfolio:
    """The governed re-run under ``schedule`` with its decision portfolio (see the module docstring).

    ``schedule`` must be the information-time schedule v4 (``decision_portfolio_needs_the_information_time_schedule``
    otherwise): a snapshot is information-time only where the admissions it conditions on are too. The authorities,
    refusals and failure modes are exactly those of ``simulate_historical_execution_governed_paper``, whose outcome under
    the same inputs is the one ``outcome_digest`` binds. Pure.
    """

    outcome, snapshots, _, _ = _governed_run(result, expected_result_digest, schedule, record_decision_portfolio=True)
    return _decision_portfolio(outcome, snapshots)


def simulate_historical_execution_governed_paper_derivation(
    result: HistoricalExecutionEconomicsResult,
    *,
    expected_result_digest: str,
    schedule: HistoricalExecutionAdmissionSchedule,
) -> HistoricalExecutionGovernedPaperDerivation:
    """The decision portfolio and the governed outcome of ONE re-run, with the exact values behind every snapshot's
    rendered NAVs and the equal-instant phase of every trade close (``HistoricalExecutionGovernedPaperDerivation``).

    The authorities, refusals and failure modes are exactly those of
    ``simulate_historical_execution_governed_paper_decision_portfolio``, and both artifacts are byte-identical to their
    own functions under the same inputs. A consumer comparing a strict threshold or ordering one nanosecond's events reads
    the exact values and phases, never the rendered text or the timestamp alone. Pure.
    """

    outcome, snapshots, exact, phases = _governed_run(
        result, expected_result_digest, schedule, record_decision_portfolio=True
    )
    return HistoricalExecutionGovernedPaperDerivation(_decision_portfolio(outcome, snapshots), outcome, exact, phases)


def _decision_portfolio(
    outcome: HistoricalExecutionGovernedPaperOutcome,
    snapshots: tuple[HistoricalExecutionDecisionPortfolioSnapshot, ...],
) -> HistoricalExecutionGovernedPaperDecisionPortfolio:
    seed = HistoricalExecutionGovernedPaperDecisionPortfolio(
        schema_version=HISTORICAL_EXECUTION_GOVERNED_PAPER_DECISION_PORTFOLIO_SCHEMA_VERSION,
        schedule=outcome.schedule,
        schedule_digest=outcome.schedule_digest,
        baseline_result_id=outcome.baseline_result_id,
        baseline_result_digest=outcome.baseline_result_digest,
        run_digest=outcome.run_digest,
        instrument=outcome.instrument,
        evaluation_start_ns=outcome.evaluation_start_ns,
        evaluation_end_ns=outcome.evaluation_end_ns,
        outcome_digest=outcome.outcome_digest,
        simulated=outcome.simulated,
        snapshots=snapshots,
        snapshot_ledger_digest=_ledger_digest(snapshots),
        reason_codes=outcome.reason_codes,
        portfolio_digest="",
    )
    return replace(seed, portfolio_digest=edge_payload_digest(_to_payload(seed), _PORTFOLIO_DIGEST_FIELD))


def historical_execution_governed_paper_decision_portfolio_to_dict(
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of a decision portfolio, including its self-digest."""

    return _to_payload(portfolio)


def historical_execution_governed_paper_decision_portfolio_digest(
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio,
) -> str:
    """Recompute the canonical decision-portfolio digest, excluding only ``portfolio_digest``.

    A consumer re-proves a supplied portfolio by recomputing this digest and re-running
    ``simulate_historical_execution_governed_paper_decision_portfolio`` over the same result and ``schedule``.
    """

    return edge_payload_digest(_to_payload(portfolio), _PORTFOLIO_DIGEST_FIELD)


def historical_execution_governed_paper_outcome_to_dict(
    outcome: HistoricalExecutionGovernedPaperOutcome,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of a governed outcome, including its self-digest."""

    return _to_payload(outcome)


def historical_execution_governed_paper_outcome_digest(outcome: HistoricalExecutionGovernedPaperOutcome) -> str:
    """Recompute the canonical governed outcome digest, excluding only ``outcome_digest``."""

    return edge_payload_digest(_to_payload(outcome), _GOVERNED_DIGEST_FIELD)


# Identifiers derived from the run digest: a longer replay is another run, so they differ by construction.
_RUN_DERIVED_FIELDS: dict[type, tuple[str, ...]] = {
    HistoricalExecutionIntent: ("intent_id", "intent_digest"),
    HistoricalExecutionFill: ("fill_id", "intent_id", "intent_digest", "fill_digest"),
    HistoricalExecutionPositionTransition: ("transition_id", "fill_digest", "transition_digest"),
    HistoricalExecutionFeeCashflow: ("fee_id", "fill_digest", "fee_digest"),
    HistoricalExecutionFundingCashflow: ("cashflow_id", "cashflow_digest"),
    HistoricalExecutionValuation: ("trigger_digest", "valuation_digest"),
    HistoricalExecutionTrade: ("trade_id", "terminal_valuation_digest", "trade_digest"),
    HistoricalExecutionExcursionProtection: (
        "protection_id",
        "trade_id",
        "opening_intent_id",
        "opening_fill_digest",
        "closing_fill_digest",
        "obligation_id",
        "protection_digest",
    ),
    HistoricalExecutionProtectiveObligation: (
        "obligation_id",
        "protection_id",
        "discharging_fill_digest",
        "obligation_digest",
    ),
    HistoricalExecutionProtectiveAttempt: ("attempt_id", "obligation_id", "attempt_digest"),
}
_TRADE_DIGEST_LISTS = ("entry_fill_digests", "exit_fill_digests", "fee_digests", "funding_cashflow_digests")


def _content(record: object, *, protective_fill: bool = False) -> dict[str, object]:
    """One economic record without its run-derived identifiers; a trade keeps only the counts of its digest lists.

    A protective fill also drops its ``decision_digest`` (the run-derived id of its obligation), and an obligation keeps
    only the count of its attempt ids.
    """

    payload = _to_payload(record)
    for name in _RUN_DERIVED_FIELDS[type(record)]:
        del payload[name]
    if protective_fill:
        del payload["decision_digest"]
    if type(record) is HistoricalExecutionTrade:
        for name in _TRADE_DIGEST_LISTS:
            payload[name] = len(getattr(record, name))
    if type(record) is HistoricalExecutionProtectiveObligation:
        payload["attempt_ids"] = len(record.attempt_ids)
    return payload


def historical_execution_governed_paper_prefix_digest(
    outcome: HistoricalExecutionGovernedPaperOutcome,
    *,
    before_ns: int,
    excluded_decision_sequences: tuple[int, ...] = (),
    excluded_protective_attempt_times: tuple[int, ...] = (),
) -> str:
    """The content identity of every governed economic event strictly before ``before_ns``.

    Intents decided, fill outcomes recorded (at their execution, else their decision instant), transitions, fees,
    funding settlements and valuations strictly before the instant, and the trades closed before it, each without its
    run-derived identifiers. Every fill outcome of an excluded decision is left out: that is the intent the shorter
    replay's end left pending. Open trades and the terminal state are never part of a prefix.

    Outcome v3 (a position-managed baseline) adds the protective attempts made before the instant. It also adds every
    protective fill outcome recorded before it (at its execution, else its attempt instant), except those of an excluded
    attempt, which the shorter replay's end left pending. It further adds the protections closed and the obligations
    discharged before the instant. An open protection and an outstanding obligation are never part of a prefix.
    """

    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome or outcome.simulated is not True:
        raise _fail("prefix_outcome_invalid")
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("prefix_instant_invalid")
    if type(excluded_decision_sequences) is not tuple or any(
        type(item) is not int for item in excluded_decision_sequences
    ):
        raise _fail("prefix_excluded_decisions_malformed")
    if type(excluded_protective_attempt_times) is not tuple or any(
        type(item) is not int for item in excluded_protective_attempt_times
    ):
        raise _fail("prefix_excluded_attempts_malformed")
    excluded = set(excluded_decision_sequences)
    excluded_attempts = set(excluded_protective_attempt_times)
    decided = {item.intent_id: item for item in outcome.intents}
    attempted = {item.attempt_id: item for item in outcome.protective_attempts}
    fills = []
    for item in outcome.fills:
        attempt = attempted.get(item.intent_id)
        if attempt is not None:
            instant = attempt.attempt_time_ns if item.execution_time_ns is None else item.execution_time_ns
            if attempt.attempt_time_ns not in excluded_attempts and instant < before_ns:
                fills.append(_content(item, protective_fill=True))
            continue
        intent = decided[item.intent_id]
        instant = intent.decision_time_ns if item.execution_time_ns is None else item.execution_time_ns
        if intent.decision_sequence not in excluded and instant < before_ns:
            fills.append(_content(item))
    prefix = {
        "intents": [_content(item) for item in outcome.intents if item.decision_time_ns < before_ns],
        "fills": fills,
        "position_transitions": [_content(item) for item in outcome.position_transitions if item.time_ns < before_ns],
        "fee_cashflows": [_content(item) for item in outcome.fee_cashflows if item.time_ns < before_ns],
        "funding_cashflows": [
            _content(item) for item in outcome.funding_cashflows if item.liability_time_ns < before_ns
        ],
        "valuations": [_content(item) for item in outcome.valuations if item.time_ns < before_ns],
        "closed_trades": [
            _content(item)
            for item in outcome.trades
            if item.status is HistoricalExecutionTradeStatus.CLOSED
            and item.end_time_ns is not None
            and item.end_time_ns < before_ns
        ],
    }
    if outcome.schema_version == _PROTECTIVE_GOVERNED_SCHEMA_VERSION:
        prefix["protective_attempts"] = [
            _content(item) for item in outcome.protective_attempts if item.attempt_time_ns < before_ns
        ]
        prefix["closed_protections"] = [
            _content(item)
            for item in outcome.excursion_protections
            if item.closed_at_ns is not None and item.closed_at_ns < before_ns
        ]
        prefix["discharged_obligations"] = [
            _content(item)
            for item in outcome.protective_obligations
            if item.discharged_at_ns is not None and item.discharged_at_ns < before_ns
        ]
    return edge_sha256_text(edge_canonical_json(prefix))


class _LatestVisible:
    """The latest record (by event time, then sequence; the earliest dataset position on a tie) visible at an instant.

    Built once over one series: records ordered by PIT visibility, with the running best of that key, so every query is
    a bisection. It selects exactly what a scan of the dataset in record order selects.
    """

    def __init__(self, dataset: HistoricalPitDataset, *, series: str, instrument: str) -> None:
        ranked: list[tuple[int, int, HistoricalPitRecord]] = []
        for position, record in enumerate(dataset.records):
            visible = _visibility(record) if record.series_id == series and record.instrument == instrument else None
            if visible is not None:
                ranked.append((visible, position, record))
        ranked.sort(key=lambda item: (item[0], item[1]))
        self._visibility = [item[0] for item in ranked]
        self._best: list[HistoricalPitRecord] = []
        best: tuple[int, int, int] | None = None
        record_of_best: HistoricalPitRecord | None = None
        for _, position, record in ranked:
            key = (record.event_time_ns, record.sequence_id, -position)
            if best is None or key > best:
                best, record_of_best = key, record
            self._best.append(record_of_best)  # type: ignore[arg-type]

    def at(self, at_ns: int) -> HistoricalPitRecord | None:
        index = bisect.bisect_right(self._visibility, at_ns)
        return self._best[index - 1] if index else None


class HistoricalExecutionVisibleObservations:
    """This engine's own point-in-time observation rules over one authentic dataset, policy and instrument.

    Built by ``historical_execution_visible_observations`` (which verifies its inputs once); every query is pure and
    reads only records visible at or before the queried instant.
    """

    def __init__(
        self,
        *,
        dataset: HistoricalPitDataset,
        policy: HistoricalExecutionEconomicsPolicy,
        instrument: str,
    ) -> None:
        self._policy = policy
        mark_codes, mark_series = _select_series(
            dataset, key=policy.mark_data_key, instrument=instrument, policy=policy
        )
        book_codes, book_series = _select_series(
            dataset, key=policy.order_book_data_key, instrument=instrument, policy=policy
        )
        self.mark_series_available = not mark_codes
        self.book_series_available = not book_codes
        self._marks = None if mark_codes else _LatestVisible(dataset, series=mark_series, instrument=instrument)
        self._books = None if book_codes else _LatestVisible(dataset, series=book_series, instrument=instrument)

    def latest_mark(self, at_ns: int) -> tuple[str, str] | None:
        """``(mark record digest, mark price)`` under the engine's valuation rule at ``at_ns``, or None.

        The latest visible mark (by event time, then sequence); None when there is none, it is older than
        ``max_mark_staleness_ns`` or its price is not positive.
        """

        if not historical_execution_wire_int_is_valid(at_ns, minimum=0):
            raise _fail("visible_mark_instant_invalid")
        best = None if self._marks is None else self._marks.at(at_ns)
        policy = self._policy
        if best is None or at_ns - best.event_time_ns > policy.max_mark_staleness_ns:
            return None
        values = [item.value for item in best.values if item.name == policy.mark_value_name]
        if len(values) != 1 or not historical_execution_decimal_is_canonical(values[0]):
            raise _fail("visible_mark_value_malformed")
        if Fraction(values[0]) <= 0:
            return None
        return best.record_digest, values[0]

    def latest_book_update(self, at_ns: int) -> tuple[str, int] | None:
        """``(book record digest, its native event time)`` of the latest order-book update visible at ``at_ns``."""

        if not historical_execution_wire_int_is_valid(at_ns, minimum=0):
            raise _fail("visible_book_instant_invalid")
        best = None if self._books is None else self._books.at(at_ns)
        return None if best is None else (best.record_digest, best.event_time_ns)


def historical_execution_visible_observations(
    dataset: HistoricalPitDataset,
    *,
    policy: HistoricalExecutionEconomicsPolicy,
    instrument: str,
) -> HistoricalExecutionVisibleObservations:
    """Verify one dataset and policy once and index this engine's visible mark and order-book observations.

    Malformed or non-authentic inputs raise ``HistoricalExecutionEconomicsError``; a missing or unusable mark or book
    series is reported by ``mark_series_available`` / ``book_series_available`` and every query of it returns None.
    """

    if type(dataset) is not HistoricalPitDataset or not verify_historical_pit_dataset(dataset).intact:
        raise _fail("visible_mark_input_malformed")
    if (
        type(policy) is not HistoricalExecutionEconomicsPolicy
        or not verify_historical_execution_economics_policy(policy).intact
    ):
        raise _fail("visible_mark_input_malformed")
    if type(instrument) is not str:
        raise _fail("visible_mark_instant_invalid")
    return HistoricalExecutionVisibleObservations(dataset=dataset, policy=policy, instrument=instrument)


def historical_execution_latest_visible_mark(
    dataset: HistoricalPitDataset,
    *,
    policy: HistoricalExecutionEconomicsPolicy,
    instrument: str,
    at_ns: int,
) -> tuple[str, str] | None:
    """``(mark record digest, mark price)`` under this engine's own valuation rule at ``at_ns``, or None.

    The latest mark of the dataset's one governed mark series visible at or before ``at_ns`` (by event time, then
    sequence); None when there is none, it is older than ``max_mark_staleness_ns`` or its price is not positive.
    Malformed or non-authentic inputs raise ``HistoricalExecutionEconomicsError``.
    """

    observations = historical_execution_visible_observations(dataset, policy=policy, instrument=instrument)
    if not historical_execution_wire_int_is_valid(at_ns, minimum=0):
        raise _fail("visible_mark_instant_invalid")
    if not observations.mark_series_available:
        raise _fail("visible_mark_series_unavailable")
    return observations.latest_mark(at_ns)


# --- result -------------------------------------------------------------------------------------------------------------


def _position_management_authority(
    policy_binding: EdgeAuthorityBinding | None, archive_binding: EdgeAuthorityBinding | None
) -> tuple[list[str], _PositionManagement | None]:
    """Re-derive the position-management policy and its OHLC archive from their bindings (re-proven, anchored)."""

    if policy_binding is None or archive_binding is None:
        return [_reason("position_management_context_unavailable")], None
    try:
        policy = historical_position_management_policy_from_payload(edge_authority_binding_snapshot(policy_binding))
        archive = historical_ohlc_bar_archive_from_payload(edge_authority_binding_snapshot(archive_binding))
    except Exception:  # noqa: BLE001 - an underivable context is an integrity failure, never a receipt
        return [_reason("position_management_context_unavailable")], None
    codes: list[str] = []
    verification = verify_historical_position_management_policy(policy)
    if not verification.intact:
        codes.extend(
            _reason(f"position_management_policy_integrity_failure:{code}") for code in verification.reason_codes
        )
    elif verification.recomputed_digest != policy_binding.expected_digest:
        codes.append(_reason("position_management_policy_digest_mismatch"))
    archive_verification = verify_historical_ohlc_bar_archive(archive)
    if not archive_verification.intact:
        codes.extend(_reason(f"ohlc_archive_integrity_failure:{code}") for code in archive_verification.reason_codes)
    elif archive_verification.recomputed_digest != archive_binding.expected_digest:
        codes.append(_reason("ohlc_archive_digest_mismatch"))
    if codes:
        return codes, None
    return [], _PositionManagement(policy, archive, historical_position_management_tightening_applied(policy))


def _position_management_reasons(
    pm: _PositionManagement,
    approval: HistoricalPositionManagementApproval | None,
    *,
    run: HistoricalDecisionRun,
) -> tuple[list[str], list[str]]:
    """The policy's economic incompatibilities (FAIL) and governance gaps (NEEDS_GOVERNANCE_APPROVAL) for one run."""

    fail: list[str] = []
    needs_governance: list[str] = []
    source = pm.archive.source
    if pm.policy.instrument != run.instrument:
        fail.append(_reason("position_management_policy_instrument_mismatch"))
    if source.instrument != run.instrument:
        fail.append(_reason("ohlc_archive_instrument_mismatch"))
    if pm.policy.atr_interval_ns not in source.bar_intervals_ns or (
        source.price_semantics is not pm.policy.atr_bar_price_semantics
    ):
        fail.append(_reason("ohlc_archive_not_of_the_position_management_policy"))
    if approval is None:
        needs_governance.append(_reason("position_management_approval_missing"))
        return fail, needs_governance
    needs_governance.extend(
        _reason(f"position_management_approval_{name}_mismatch")
        for name in historical_position_management_approval_mismatches(
            approval,
            policy=pm.policy,
            strategy_spec_digest=run.strategy_spec_digest,
            instrument=run.instrument,
            ohlc_source_digest=pm.archive.source_digest,
        )
    )
    if approval.approval_kind is HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE:
        needs_governance.extend(
            _reason(f"position_management_method_requires_human_approval:{method}")
            for method in historical_position_management_methods_requiring_human_approval(pm.policy)
        )
    return fail, needs_governance


def _assemble_result(
    *,
    run_binding: object,
    policy_binding: object,
    economics_approval: object,
    result_id: object,
    correlation_id: object,
    position_management_binding: object = None,
    position_management_approval: object = None,
    ohlc_archive_binding: object = None,
) -> HistoricalExecutionEconomicsResult:
    """The one result assembly path, shared by the builder and verifier re-derivation."""

    pm_ref = require_edge_authority_binding(
        position_management_binding,
        shape=historical_position_management_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("position_management_policy"),
        optional=True,
    )
    archive_ref = require_edge_authority_binding(
        ohlc_archive_binding,
        shape=historical_ohlc_bar_archive_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("ohlc_archive"),
        optional=True,
    )
    if (pm_ref is None) is not (archive_ref is None) or (pm_ref is None and position_management_approval is not None):
        raise _fail("position_management_inputs_incomplete")
    try:
        pm_approval = canonical_historical_position_management_approval(position_management_approval)
    except HistoricalPositionManagementPolicyError as exc:
        raise _fail("position_management_approval_malformed") from exc
    run_ref = require_edge_authority_binding(
        run_binding,
        shape=historical_decision_run_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("run"),
        optional=False,
    )
    policy_ref = require_edge_authority_binding(
        policy_binding,
        shape=historical_execution_economics_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("policy"),
        optional=False,
    )
    result_id = _require_text(result_id, "result_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    try:
        approval = canonical_historical_execution_economics_approval(economics_approval)
    except HistoricalExecutionEconomicsPolicyError as exc:
        raise _fail("economics_approval_malformed") from exc

    codes, run = _run_authority(run_ref, correlation_id=correlation_id)  # type: ignore[arg-type]
    policy_codes, policy = _policy_authority(policy_ref)  # type: ignore[arg-type]
    codes.extend(policy_codes)
    context: _RunContext | None = None
    if run is not None:
        context_codes, context = _run_context(run)
        codes.extend(context_codes)
    pm: _PositionManagement | None = None
    if pm_ref is not None:
        pm_codes, pm = _position_management_authority(pm_ref, archive_ref)
        codes.extend(pm_codes)
    integrity = _sorted_unique(codes)

    ledgers = _Ledgers()
    mark_series = book_series = ""
    if integrity or run is None or policy is None or context is None or (pm_ref is not None and pm is None):
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail: list[str] = []
        needs_external: list[str] = []
        needs_governance: list[str] = []
        buckets = (fail, needs_external, needs_governance)
        if run.advances is not True:
            _propagate("run", run.gate_verdict, buckets)
        if policy.advances is not True:
            _propagate("policy", policy.gate_verdict, buckets)
        spec = context.spec
        if spec.market_type.value != policy.market_type:
            fail.append(_reason("market_type_unsupported_for_economics_v1"))
        if policy.instrument != run.instrument:
            fail.append(_reason("economics_policy_instrument_mismatch"))
        if policy.satisfies_fee_model_requirement != spec.fee_model_requirement:
            fail.append(_reason("spec_fee_model_requirement_unsatisfied"))
        if policy.satisfies_slippage_model_requirement != spec.slippage_model_requirement:
            fail.append(_reason("spec_slippage_model_requirement_unsatisfied"))
        if policy.satisfies_latency_sensitivity != spec.latency_sensitivity:
            fail.append(_reason("spec_latency_sensitivity_unsatisfied"))
        max_leverage, leverage_code = _max_leverage(spec)
        if leverage_code is not None:
            fail.append(_reason(leverage_code))
        unit_size = _unit_size(run)
        if unit_size is None:
            fail.append(_reason("unit_size_parameter_unavailable"))
        series_codes, mark_series, book_series = _economic_series(context.dataset, run, policy)
        fail.extend(series_codes)
        if approval is None:
            needs_governance.append(_reason("economics_approval_missing"))
        else:
            needs_governance.extend(
                _reason(f"economics_approval_{name}_mismatch")
                for name in historical_execution_economics_approval_mismatches(
                    approval,
                    policy=policy,
                    strategy_spec_digest=run.strategy_spec_digest,
                    instrument=run.instrument,
                    market_type=spec.market_type.value,
                    data_requirement_registry_digest=context.data_requirement_registry_digest,
                )
            )
        if pm is not None:
            pm_fail, pm_governance = _position_management_reasons(pm, pm_approval, run=run)
            fail.extend(pm_fail)
            needs_governance.extend(pm_governance)
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        if verdict is EdgeGateVerdict.PASS:
            try:
                ledgers = _Simulation(
                    run=run,
                    run_digest=run_ref.expected_digest,  # type: ignore[union-attr]
                    dataset=context.dataset,
                    policy=policy,
                    unit_size=unit_size,  # type: ignore[arg-type]
                    max_leverage=max_leverage,  # type: ignore[arg-type]
                    mark_series=mark_series,
                    book_series=book_series,
                    position_management=pm,
                ).run_all()
            except _EconomicFailure as failure:
                fail.append(_reason(failure.code))
                ledgers = _Ledgers()
            verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        status = EdgeEvidenceStatus.READY
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    computed = status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS
    extension: dict[str, object] = {}
    if pm_ref is not None:
        extension = {
            "position_management_policy_binding": pm_ref,
            "position_management_approval": pm_approval,
            "ohlc_archive_binding": archive_ref,
            "position_management_policy_digest": pm_ref.expected_digest,
            "ohlc_archive_digest": archive_ref.expected_digest,  # type: ignore[union-attr]
            "synthetic_position_management_approval_used": pm_approval is not None
            and pm_approval.approval_kind is HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC,
            "stop_tightening_applied": pm is not None and pm.tightening,
            "excursion_protections": tuple(ledgers.protections),
            "protective_obligations": tuple(ledgers.obligations),
            "protective_attempts": tuple(ledgers.attempts),
            "protection_ledger_digest": _ledger_digest(ledgers.protections),
            "obligation_ledger_digest": _ledger_digest(ledgers.obligations),
            "attempt_ledger_digest": _ledger_digest(ledgers.attempts),
        }
    seed = HistoricalExecutionEconomicsResult(
        schema_version=_SCHEMA_VERSION if pm_ref is None else _POSITION_MANAGED_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=computed,
        result_id=result_id,
        correlation_id=correlation_id,
        run_binding=run_ref,  # type: ignore[arg-type]
        run_digest=run_ref.expected_digest,  # type: ignore[union-attr]
        dataset_digest="" if run is None else run.dataset_digest,
        source_manifest_digest="" if run is None else run.source_manifest_digest,
        data_requirement_registry_digest="" if context is None else context.data_requirement_registry_digest,
        executable_binding_digest="" if run is None else run.executable_binding_digest,
        strategy_spec_digest="" if run is None else run.strategy_spec_digest,
        profile_semantics_digest="" if run is None else run.profile_semantics_digest,
        parameter_assignment_digest="" if run is None else run.parameter_assignment_digest,
        parameter_approval=None if run is None else run.parameter_approval,
        instrument="" if run is None else run.instrument,
        market_type="" if context is None else context.spec.market_type.value,
        evaluation_start_ns=0 if run is None else run.evaluation_start_ns,
        evaluation_end_ns=0 if run is None else run.evaluation_end_ns,
        policy_binding=policy_ref,  # type: ignore[arg-type]
        economics_policy_digest=policy_ref.expected_digest,  # type: ignore[union-attr]
        economics_approval=approval,
        conformance=None if policy is None else policy.conformance,
        synthetic_test_facts_used=policy is not None and policy.synthetic_test_facts_used,
        synthetic_test_approval_used=approval is not None
        and approval.approval_kind is HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC,
        funding_series_id="" if run is None else run.funding_series_id,
        mark_series_id=mark_series,
        order_book_series_id=book_series,
        intents=tuple(ledgers.intents),
        fills=tuple(ledgers.fills),
        position_transitions=tuple(ledgers.transitions),
        fee_cashflows=tuple(ledgers.fees),
        funding_cashflows=tuple(ledgers.funding),
        valuations=tuple(ledgers.valuations),
        trades=tuple(ledgers.trades),
        terminal_state=ledgers.terminal,
        intent_ledger_digest=_ledger_digest(ledgers.intents),
        fill_ledger_digest=_ledger_digest(ledgers.fills),
        position_transition_ledger_digest=_ledger_digest(ledgers.transitions),
        fee_ledger_digest=_ledger_digest(ledgers.fees),
        funding_ledger_digest=_ledger_digest(ledgers.funding),
        valuation_ledger_digest=_ledger_digest(ledgers.valuations),
        trade_ledger_digest=_ledger_digest(ledgers.trades),
        simulated_economics_computed=computed,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        result_digest="",
        **extension,  # type: ignore[arg-type]
    )
    return replace(seed, result_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def _position_management_bindings(
    inputs: object,
) -> tuple[EdgeAuthorityBinding | None, HistoricalPositionManagementApproval | None, EdgeAuthorityBinding | None]:
    if inputs is None:
        return None, None, None
    if (
        type(inputs) is not HistoricalExecutionPositionManagementInputs
        or type(inputs.policy) is not HistoricalPositionManagementPolicy
        or type(inputs.ohlc_archive) is not HistoricalOhlcBarArchive
    ):
        raise _fail("position_management_inputs_malformed")
    try:
        policy_payload = historical_position_management_policy_to_dict(inputs.policy)
        archive_payload = historical_ohlc_bar_archive_to_dict(inputs.ohlc_archive)
    except Exception as exc:  # noqa: BLE001 - a hollow upstream object is a construction error, never a receipt
        raise _fail("position_management_not_serializable") from exc
    policy_ref = build_edge_authority_binding(
        snapshot_payload=policy_payload,
        expected_digest=inputs.expected_policy_digest,
        shape=historical_position_management_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("position_management_policy"),
    )
    archive_ref = build_edge_authority_binding(
        snapshot_payload=archive_payload,
        expected_digest=inputs.expected_ohlc_archive_digest,
        shape=historical_ohlc_bar_archive_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("ohlc_archive"),
    )
    return policy_ref, inputs.approval, archive_ref


def build_historical_execution_economics(
    run: HistoricalDecisionRun,
    *,
    expected_run_digest: str,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    expected_economics_policy_digest: str,
    economics_approval: HistoricalExecutionEconomicsApproval | None,
    result_id: str,
    correlation_id: str,
    position_management: HistoricalExecutionPositionManagementInputs | None = None,
) -> HistoricalExecutionEconomicsResult:
    """Build deterministic historical execution economics for an authenticated decision run.

    ``position_management`` (PROTECTIVE_POSITION_LIFECYCLE_V1) binds a position-management policy, its approval and its
    authenticated OHLC archive: the result is then schema v2 and the protective lifecycle applies (see the module
    docstring). Without it the result is exactly the accepted v1 result. Malformed caller input, a malformed approval or
    a non-serializable upstream object raises ``HistoricalExecutionEconomicsError``. A run or policy that fails
    re-proof yields ``REJECTED``/``NOT_EVALUATED``. Only ``READY`` + ``PASS`` carries economic ledgers.
    """

    if type(run) is not HistoricalDecisionRun:
        raise _fail("run_malformed")
    if type(economics_policy) is not HistoricalExecutionEconomicsPolicy:
        raise _fail("policy_malformed")
    pm_ref, pm_approval, archive_ref = _position_management_bindings(position_management)
    try:
        run_payload = historical_decision_run_to_dict(run)
    except Exception as exc:  # noqa: BLE001 - a hollow run object is a construction error, never a receipt
        raise _fail("run_not_serializable") from exc
    try:
        policy_payload = historical_execution_economics_policy_to_dict(economics_policy)
    except Exception as exc:  # noqa: BLE001 - a hollow policy object is a construction error, never a receipt
        raise _fail("policy_not_serializable") from exc
    run_ref = build_edge_authority_binding(
        snapshot_payload=run_payload,
        expected_digest=expected_run_digest,
        shape=historical_decision_run_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("run"),
    )
    policy_ref = build_edge_authority_binding(
        snapshot_payload=policy_payload,
        expected_digest=expected_economics_policy_digest,
        shape=historical_execution_economics_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("policy"),
    )
    return _assemble_result(
        run_binding=run_ref,
        policy_binding=policy_ref,
        economics_approval=economics_approval,
        result_id=result_id,
        correlation_id=correlation_id,
        position_management_binding=pm_ref,
        position_management_approval=pm_approval,
        ohlc_archive_binding=archive_ref,
    )


def historical_execution_economics_to_dict(result: HistoricalExecutionEconomicsResult) -> dict[str, object]:
    """Canonical JSON-ready mapping of a result, including its self-digest."""

    return _to_payload(result)


def historical_execution_economics_digest(result: HistoricalExecutionEconomicsResult) -> str:
    """Recompute the canonical result digest, excluding only ``result_digest``."""

    return edge_payload_digest(_to_payload(result), _SELF_DIGEST_FIELD)


# --- strict parsing -----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_decimal(value: object) -> str:
    if not historical_execution_decimal_is_canonical(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_optional_decimal(value: object) -> str | None:
    return None if value is None else _as_decimal(value)


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(
    cls: type,
    payload: object,
    converters: Mapping[str, Callable[[object], object]],
    names: list[str] | None = None,
) -> object:
    """``cls`` from exactly ``names`` (default: every field; an omitted field keeps its declared default)."""

    names = [item.name for item in fields(cls)] if names is None else names
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_optional(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _parse_run_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_decision_run_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("run"),
        optional=False,
    )


def _parse_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_execution_economics_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("policy"),
        optional=False,
    )


_INTENT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "decision_sequence": _as_int,
    "decision_time_ns": _as_int,
    "target_quantity": _as_decimal,
    "actual_quantity": _as_decimal,
    "delta_quantity": _as_decimal,
    "requested_quantity": _as_decimal,
    "action": _as_enum(HistoricalExecutionIntentAction),
    "side": _as_enum(HistoricalExecutionSide),
    "close_only_clamped": _as_bool,
    "earliest_execution_time_ns": _as_int,
}
_FILL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "outcome": _as_enum(HistoricalExecutionFillOutcome),
    "side": _as_enum(HistoricalExecutionSide),
    "requested_quantity": _as_decimal,
    "filled_quantity": _as_decimal,
    "cancelled_quantity": _as_decimal,
    "fill_ratio": _as_decimal,
    "book_record_digest": _as_optional_str,
    "book_event_time_ns": _as_optional_int,
    "execution_time_ns": _as_optional_int,
    **dict.fromkeys(
        (
            "best_bid_price",
            "best_ask_price",
            "mid_price",
            "spread_bps",
            "half_spread_bps",
            "side_visible_quantity",
            "max_executable_quantity",
            "participation_pct",
            "impact_bps",
            "effective_slippage_bps",
            "fill_price",
            "fill_notional",
        ),
        _as_optional_decimal,
    ),
}
_TRANSITION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "transition_kind": _as_enum(HistoricalExecutionTransitionKind),
    "time_ns": _as_int,
    "prior_quantity": _as_decimal,
    "prior_average_entry_price": _as_optional_decimal,
    "delta_quantity": _as_decimal,
    "post_quantity": _as_decimal,
    "post_average_entry_price": _as_optional_decimal,
    "closed_quantity": _as_decimal,
    "realized_gross_pnl": _as_decimal,
}
_FEE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "time_ns": _as_int,
    "taker_fee_bps": _as_decimal,
    "fill_notional": _as_decimal,
    "fee_amount": _as_decimal,
}
_FUNDING_CONVERTERS: dict[str, Callable[[object], object]] = {
    "funding_sequence_id": _as_int,
    "funding_event_time_ns": _as_int,
    "liability_time_ns": _as_int,
    "funding_rate": _as_decimal,
    "position_quantity": _as_decimal,
    "mark_price": _as_decimal,
    "funding_notional": _as_decimal,
    "cashflow_amount": _as_decimal,
}
_VALUATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "valuation_sequence": _as_int,
    "valuation_kind": _as_enum(HistoricalExecutionValuationKind),
    "time_ns": _as_int,
    "trigger_digest": _as_optional_str,
    "position_quantity": _as_decimal,
    "average_entry_price": _as_optional_decimal,
    "mark_record_digest": _as_optional_str,
    "mark_price": _as_optional_decimal,
    "unrealized_pnl": _as_decimal,
    "cumulative_realized_gross_pnl": _as_decimal,
    "cumulative_fees": _as_decimal,
    "cumulative_funding": _as_decimal,
    "equity": _as_decimal,
}
_TRADE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(HistoricalExecutionTradeStatus),
    "start_time_ns": _as_int,
    "end_time_ns": _as_optional_int,
    "entry_fill_digests": _as_str_tuple,
    "exit_fill_digests": _as_str_tuple,
    "fee_digests": _as_str_tuple,
    "funding_cashflow_digests": _as_str_tuple,
    "realized_gross_pnl": _as_decimal,
    "total_fees": _as_decimal,
    "total_funding": _as_decimal,
    "realized_net_pnl": _as_decimal,
    "unrealized_pnl": _as_optional_decimal,
    "terminal_valuation_digest": _as_optional_str,
}
_TERMINAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "position_quantity": _as_decimal,
    "average_entry_price": _as_optional_decimal,
    "open_trade_id": _as_optional_str,
    "cumulative_realized_gross_pnl": _as_decimal,
    "cumulative_fees": _as_decimal,
    "cumulative_funding": _as_decimal,
    "unrealized_pnl": _as_decimal,
    "equity": _as_decimal,
}
_CONFORMANCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    **{item.name: _as_bool for item in fields(HistoricalExecutionConformance) if item.type in ("bool", bool)},
    "prdv4_min_slippage_floor_bps": _as_decimal,
    "prdv4_max_visible_depth_cap_fraction": _as_decimal,
}
_RESULT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "run_binding": _parse_run_binding,
    "parameter_approval": _as_optional(StrategyExecutableParameterApproval, {}),
    "evaluation_start_ns": _as_int,
    "evaluation_end_ns": _as_int,
    "policy_binding": _parse_policy_binding,
    "economics_approval": _as_optional(
        HistoricalExecutionEconomicsApproval, {"approval_kind": _as_enum(HistoricalExecutionApprovalKind)}
    ),
    "conformance": _as_optional(HistoricalExecutionConformance, _CONFORMANCE_CONVERTERS),
    "synthetic_test_facts_used": _as_bool,
    "synthetic_test_approval_used": _as_bool,
    "intents": _as_records(HistoricalExecutionIntent, _INTENT_CONVERTERS),
    "fills": _as_records(HistoricalExecutionFill, _FILL_CONVERTERS),
    "position_transitions": _as_records(HistoricalExecutionPositionTransition, _TRANSITION_CONVERTERS),
    "fee_cashflows": _as_records(HistoricalExecutionFeeCashflow, _FEE_CONVERTERS),
    "funding_cashflows": _as_records(HistoricalExecutionFundingCashflow, _FUNDING_CONVERTERS),
    "valuations": _as_records(HistoricalExecutionValuation, _VALUATION_CONVERTERS),
    "trades": _as_records(HistoricalExecutionTrade, _TRADE_CONVERTERS),
    "terminal_state": _as_optional(HistoricalExecutionTerminalState, _TERMINAL_CONVERTERS),
    "simulated_economics_computed": _as_bool,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def _parse_position_management_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_position_management_policy_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("position_management_policy"),
        optional=True,
    )


def _parse_ohlc_archive_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_ohlc_bar_archive_payload_is_well_formed,
        error=HistoricalExecutionEconomicsError,
        code=_reason("ohlc_archive"),
        optional=True,
    )


def _as_position_management_approval(value: object) -> HistoricalPositionManagementApproval | None:
    if value is None:
        return None
    try:
        return historical_position_management_approval_from_payload(value)
    except HistoricalPositionManagementPolicyError as exc:
        raise _fail("payload_field_malformed") from exc


_STOP_LEVEL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "milestone": _as_int,
    "effective_from_ns": _as_int,
    "stop_distance": _as_decimal,
    "stop_price": _as_decimal,
}
_PROTECTION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "opened_at_ns": _as_int,
    "basis_price": _as_decimal,
    "atr_interval_ns": _as_int,
    "atr_at_ns": _as_int,
    "atr_value": _as_decimal,
    "atr_run_bar_count": _as_int,
    "atr_latest_bar_close_ns": _as_int,
    "stop_atr_multiple": _as_decimal,
    "stop_levels": _as_records(HistoricalExecutionStopLevel, _STOP_LEVEL_CONVERTERS),
    "max_hold_deadline_ns": _as_int,
    "closed_at_ns": _as_optional_int,
    "closing_fill_digest": _as_optional_str,
    "obligation_id": _as_optional_str,
}
_TRIGGER_CONVERTERS: dict[str, Callable[[object], object]] = {
    "trigger_kind": _as_enum(HistoricalExecutionProtectiveTriggerKind),
    "trigger_time_ns": _as_int,
    "mark_record_digest": _as_optional_str,
    "mark_price": _as_optional_decimal,
    "stop_price": _as_optional_decimal,
    "stop_milestone": _as_optional_int,
}
_OBLIGATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(HistoricalExecutionProtectiveObligationStatus),
    "triggers": _as_records(HistoricalExecutionProtectiveTrigger, _TRIGGER_CONVERTERS),
    "created_at_ns": _as_int,
    "attempt_ids": _as_str_tuple,
    "discharged_at_ns": _as_optional_int,
    "discharging_fill_digest": _as_optional_str,
    "outstanding_quantity": _as_decimal,
    "breach_duration_ns": _as_int,
}
_ATTEMPT_CONVERTERS: dict[str, Callable[[object], object]] = {
    "attempt_sequence": _as_int,
    "attempt_time_ns": _as_int,
    "position_quantity": _as_decimal,
    "requested_quantity": _as_decimal,
    "action": _as_enum(HistoricalExecutionIntentAction),
    "side": _as_enum(HistoricalExecutionSide),
    "earliest_execution_time_ns": _as_int,
}
_RESULT_CONVERTERS.update(
    {
        "position_management_policy_binding": _parse_position_management_binding,
        "position_management_approval": _as_position_management_approval,
        "ohlc_archive_binding": _parse_ohlc_archive_binding,
        "synthetic_position_management_approval_used": _as_bool,
        "stop_tightening_applied": _as_bool,
        "excursion_protections": _as_records(HistoricalExecutionExcursionProtection, _PROTECTION_CONVERTERS),
        "protective_obligations": _as_records(HistoricalExecutionProtectiveObligation, _OBLIGATION_CONVERTERS),
        "protective_attempts": _as_records(HistoricalExecutionProtectiveAttempt, _ATTEMPT_CONVERTERS),
    }
)


def historical_execution_economics_from_payload(payload: object) -> HistoricalExecutionEconomicsResult:
    """Strictly reconstruct a result from its serialized payload (exact fields, types and domains; no proof).

    A v1 payload carries exactly the v1 fields (the v2 fields take their neutral defaults); a v2 payload carries every
    field. Any other field set or schema version is refused.
    """

    if type(payload) is not dict:
        raise _fail("payload_fields_malformed")
    names = [item.name for item in fields(HistoricalExecutionEconomicsResult)]
    version = payload.get("schema_version")
    if version == _SCHEMA_VERSION:
        names = [name for name in names if name not in _RESULT_V2_FIELDS]
    elif version != _POSITION_MANAGED_SCHEMA_VERSION:
        raise _fail("payload_fields_malformed")
    return _parse_exact(HistoricalExecutionEconomicsResult, payload, _RESULT_CONVERTERS, names)  # type: ignore[return-value]


def historical_execution_economics_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a result snapshot."""

    try:
        historical_execution_economics_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_result(result: object) -> HistoricalExecutionEconomicsResult:
    return _assemble_result(
        run_binding=result.run_binding,  # type: ignore[attr-defined]
        policy_binding=result.policy_binding,  # type: ignore[attr-defined]
        economics_approval=result.economics_approval,  # type: ignore[attr-defined]
        result_id=result.result_id,  # type: ignore[attr-defined]
        correlation_id=result.correlation_id,  # type: ignore[attr-defined]
        position_management_binding=result.position_management_policy_binding,  # type: ignore[attr-defined]
        position_management_approval=result.position_management_approval,  # type: ignore[attr-defined]
        ohlc_archive_binding=result.ohlc_archive_binding,  # type: ignore[attr-defined]
    )


def verify_historical_execution_economics(result: object) -> EdgeEvidenceVerification:
    """Re-prove the run, policy and approval and re-derive every ledger from the frozen trace. Total: never raises."""

    return verify_edge_artifact_total(
        result,
        cls=HistoricalExecutionEconomicsResult,
        to_payload=_to_payload,
        parse_payload=historical_execution_economics_from_payload,
        reassemble=_reassemble_result,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "HISTORICAL_EXECUTION_ADMISSION_SCHEDULE_SCHEMA_VERSION",
    "HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES",
    "HISTORICAL_EXECUTION_GOVERNED_PAPER_DECISION_PORTFOLIO_SCHEMA_VERSION",
    "HISTORICAL_EXECUTION_GOVERNED_PAPER_NON_CLAIM_FLAGS",
    "HISTORICAL_EXECUTION_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION",
    "HISTORICAL_EXECUTION_INFORMATION_TIME_ADMISSION_SCHEDULE_SCHEMA_VERSION",
    "HISTORICAL_EXECUTION_NON_CLAIM_FLAGS",
    "HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP",
    "HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION",
    "HISTORICAL_EXECUTION_PROTECTIVE_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION",
    "HistoricalExecutionExcursionProtection",
    "HistoricalExecutionPositionManagementInputs",
    "HistoricalExecutionProtectiveAttempt",
    "HistoricalExecutionProtectiveObligation",
    "HistoricalExecutionProtectiveObligationStatus",
    "HistoricalExecutionProtectiveTrigger",
    "HistoricalExecutionProtectiveTriggerKind",
    "HistoricalExecutionProtectiveWindow",
    "HistoricalExecutionStopLevel",
    "historical_execution_admission_schedule_to_dict",
    "HistoricalExecutionAdmissionSchedule",
    "HistoricalExecutionAdmissionWindow",
    "HistoricalExecutionDecisionExactValues",
    "HistoricalExecutionDecisionPortfolioSnapshot",
    "HistoricalExecutionEconomicsError",
    "HistoricalExecutionEconomicsResult",
    "HistoricalExecutionFeeCashflow",
    "HistoricalExecutionFill",
    "HistoricalExecutionFillOutcome",
    "HistoricalExecutionFundingCashflow",
    "HistoricalExecutionGovernedPaperDecisionPortfolio",
    "HistoricalExecutionGovernedPaperDerivation",
    "HistoricalExecutionGovernedPaperOutcome",
    "HistoricalExecutionIntent",
    "HistoricalExecutionIntentAction",
    "HistoricalExecutionPositionTransition",
    "HistoricalExecutionSide",
    "HistoricalExecutionStressOutcome",
    "HistoricalExecutionStressScenario",
    "HistoricalExecutionStressScenarioKind",
    "HistoricalExecutionTerminalState",
    "HistoricalExecutionTrade",
    "HistoricalExecutionTradeStatus",
    "HistoricalExecutionTransitionKind",
    "HistoricalExecutionValuation",
    "HistoricalExecutionValuationKind",
    "build_historical_execution_economics",
    "canonical_historical_execution_admission_schedule",
    "canonical_historical_execution_stress_scenario",
    "historical_execution_admission_schedule_digest",
    "historical_execution_economics_digest",
    "historical_execution_economics_from_payload",
    "historical_execution_economics_payload_is_well_formed",
    "historical_execution_economics_to_dict",
    "historical_execution_governed_paper_decision_portfolio_digest",
    "historical_execution_governed_paper_decision_portfolio_to_dict",
    "historical_execution_governed_paper_outcome_digest",
    "historical_execution_governed_paper_outcome_to_dict",
    "historical_execution_governed_paper_prefix_digest",
    "historical_execution_latest_visible_mark",
    "historical_execution_stress_outcome_digest",
    "historical_execution_stress_outcome_to_dict",
    "historical_execution_stress_scenario_digest",
    "simulate_historical_execution_governed_paper",
    "simulate_historical_execution_governed_paper_decision_portfolio",
    "simulate_historical_execution_governed_paper_derivation",
    "simulate_historical_execution_stress",
    "verify_historical_execution_economics",
]
