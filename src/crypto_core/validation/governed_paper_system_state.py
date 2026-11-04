"""Governed paper system state (S1_INTEGRATED_RISK_AND_SYSTEM_SAFETY_CLOSURE_V1): a PRDV4 §1.29 proven lower bound.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.29 (the global system state engine), read with §1.19 (the
kill-switch level, signal S1), §8.2 and §1.19 trigger 11 (the 15% drawdown from peak, signal S2), §1.21 (the NT-D and
NT-X triggers, signals S4 and S5) and §1.16 (the latency tiers, signal S10); and the human-approved R29 structure of
``S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1`` r2 (CL2-7): Family B is a T1 edge, so an S1 entry needs a proven SS-0.
Paper-only, deterministic, point-in-time and fail-closed. It creates no order, closes no position, cancels nothing,
disables no engine and authorizes no entry.

What it proves. This module is the ONE system-state authority of the governed paper path. At each entry decision of a
governed evaluation it derives only a LOWER BOUND of the §1.29 state: a state the true state is at least, under every
reading of the signals it does not measure. It never proves SS-0. The PRDV4 weights, thresholds and override rules are
doctrine values, never governed parameters, and no signal reading here is a new methodology:

* S1 kill-switch level (``s1 = KS / 4``): the proven lower bound of the §1.19 ladder at the decision
  (``governed_paper_kill_switch``). KS-4 is never proven, so S1 never reaches 1 here.
* S2 drawdown severity (``s2 = min(1, DD / 0.15)``): DD is the §8.2 drawdown from peak, whose 15% limit (§1.19 trigger
  11) is S2's normalizer. Only the ladder's proofs at the decision are read: trigger 11 (drawdown strictly beyond 15%)
  gives 1 and trigger 2 (strictly beyond 10%) gives 2/3; nothing deeper is ever claimed between them.
* S4 data feed health: the fraction of the five NT-D01..NT-D05 conditions the decision's own evaluation proves active
  (FAIL). A BLOCKED condition is unknown, never inactive and never active.
* S5 execution health: the fraction of the four NT-X01..NT-X04 conditions proven active likewise.
* S10 latency health (``max over tiers of min(1, L / (5 x L_tier))``): the governed latency is the only latency of the
  paper path and Family B is tier T1 (100 ms), so ``min(1, L / (5 x 100 ms))`` is a lower bound of the maximum.
* S3 (§1.18 CVaR), S6 (§1.17 LIQ), S7 (§1.23 feature drift) and S9 (§1.26 margin utilization, which needs a paper
  wallet model and D1 margin facts) have no reading at all. S8 (correlation spike) is proven not applicable on the
  single-instrument paper portfolio (NT-M04's proof). An unmeasured signal adds nothing to the lower bound and is never
  read as healthy.

The bound. The stress lower bound is ``sum(w_i x s_i)`` over the measured lower bounds, exactly (``Fraction``), and the
SHS upper bound is ``1`` minus it. Escalation is immediate (§1.29 State Transition Protocol), so the state is at least
the state whose entry threshold the SHS upper bound meets: HALT at or below 0.15, CRISIS at or below 0.35, DEFENSIVE at
or below 0.60, DEGRADED at or below 0.80. The critical overrides read only proven severities, and every §1.29 rule is a
cumulative minimum: the most severe applicable one binds and none lowers another. Any proven ``s_i = 1``, S4's complete
data loss included, raises the bound to at least CRISIS regardless of the SHS. S4's own rule (complete data loss,
DEFENSIVE minimum) is cumulative with that CRISIS and always met by it; it never weakens it.

Instants and persistence. The bound is read at the entry decision's own instant, at its DECISION phase, exactly where the
gate reads every other fact. No state between decisions is claimed. No persistence is claimed either: a de-escalation
needs an exit threshold sustained for a minimum duration over the TRUE SHS, and an unmeasured signal may already have
held the state since an earlier, unknown instant, so the bound falls back to the signals proven at each instant. The
bound never exceeds the true state under any reading of the unmeasured signals, and it stays a lower bound whatever
reading a human later adopts.

Obligations. For a bound above SS-0 the §1.29 per-state rules that act on entries, positions or orders are recorded with
their representation on the paper path: a rule that refuses entries is enforced by the entry refusal itself, a reduced
allocation is refused through SCALE-1 (no smaller entry is representable), and every position, order or engine action
(stop tightening, TWAP reduction or exit, cancellation, flattening, engine disable) is BLOCKED_UNREPRESENTABLE: no
mechanics for them are defined, and none is ever executed here.

Exact arithmetic, no float, no ``decimal`` context, and no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.historical_execution_economics_policy import (
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)

GOVERNED_PAPER_SYSTEM_STATE_CONTRACT_ID = "S1_INTEGRATED_RISK_AND_SYSTEM_SAFETY_CLOSURE_V1"
GOVERNED_PAPER_SYSTEM_STATE_RULE_ID = "governed-paper-system-state-proven-lower-bound.v1"
_SCHEMA_VERSION = "governed-paper-system-state-evidence.v1"
_PREFIX = "governed_paper_system_state"
_DIGEST_FIELD = "evidence_digest"
_READING_DIGEST_FIELD = "reading_digest"

# PRDV4 §1.29 doctrine values: published, never governed parameters.
GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS: tuple[str, ...] = tuple(f"S{index}" for index in range(1, 11))
_WEIGHTS: dict[str, Fraction] = {
    "S1": Fraction(20, 100),
    "S2": Fraction(15, 100),
    "S3": Fraction(15, 100),
    "S4": Fraction(10, 100),
    "S5": Fraction(10, 100),
    "S6": Fraction(8, 100),
    "S7": Fraction(7, 100),
    "S8": Fraction(5, 100),
    "S9": Fraction(5, 100),
    "S10": Fraction(5, 100),
}
_SOURCES: dict[str, str] = {
    "S1": "PRDV4 §1.19 kill-switch level: s1 = KS_level / 4",
    "S2": "PRDV4 §1.29 drawdown severity: s2 = min(1, DD / 0.15)",
    "S3": "PRDV4 §1.18 CVaR breach ratio: s3 = min(1, CVaR99 / (0.05 x NAV))",
    "S4": "PRDV4 §1.21 NT-D01..D05: s4 = fraction of active NT-D triggers",
    "S5": "PRDV4 §1.21 NT-X01..X04: s5 = fraction of active NT-X triggers",
    "S6": "PRDV4 §1.17 liquidity regime: s6 = 1 - LIQ",
    "S7": "PRDV4 §1.23 feature drift: s7 = min(1, CSI / 0.50)",
    "S8": "PRDV4 §1.19 trigger 4 correlation spike: s8 = min(1, mean pairwise correlation / 0.85)",
    "S9": "PRDV4 §1.26 leverage exposure: s9 = min(1, MU / 0.85)",
    "S10": "PRDV4 §1.16 latency health: s10 = max over tiers of min(1, L / (5 x L_tier))",
}
_STATE_IDS: tuple[str, ...] = ("SS-0", "SS-1", "SS-2", "SS-3", "SS-4")
_STATE_NAMES: tuple[str, ...] = ("NORMAL", "DEGRADED", "DEFENSIVE", "CRISIS", "HALT")
# The entry threshold of each state above SS-0: the state is entered when SHS is AT OR BELOW its bound (§1.29).
_STATE_ENTRY: tuple[tuple[int, Fraction], ...] = (
    (4, Fraction(15, 100)),
    (3, Fraction(35, 100)),
    (2, Fraction(60, 100)),
    (1, Fraction(80, 100)),
)
_CRISIS = 3  # §1.29: any single proven severity of 1 is at least CRISIS, regardless of the SHS
_KILL_SWITCH_LEVELS = 4  # s1 = KS_level / 4; the ladder proves at most KS-3
_DRAWDOWN_NORMALIZER = Fraction(15, 100)  # s2 = min(1, DD / 0.15)
_T2_DRAWDOWN = Fraction(10, 100)  # §1.19 trigger 2: a drawdown from peak strictly beyond 10%
_DATA_IDS: tuple[str, ...] = tuple(f"NT-D0{index}" for index in range(1, 6))
_EXECUTION_IDS: tuple[str, ...] = tuple(f"NT-X0{index}" for index in range(1, 5))
_LATENCY_MULTIPLE = 5  # s10 = min(1, L / (5 x L_tier))
_ACTIVE = "FAIL"  # an NT condition is active exactly when the evaluation proves it (FAIL)
_SCALE = 10**18  # the numeric policy's scale of a rendered amount
_GATE_STATUSES = frozenset(
    {"PASS", "FAIL", "BLOCKED_ON_MISSING_INPUT", "BLOCKED_PROTECTION_UNREPRESENTABLE", "PROVEN_NOT_APPLICABLE"}
)


class GovernedPaperSystemStateError(EdgeArtifactError):
    """Malformed input: a system-state reading is never represented over it."""


class GovernedPaperSystemStateMeasurement(str, Enum):
    LOWER_BOUND = "LOWER_BOUND"  # a proven lower bound of the severity; the signal may be higher
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"  # the signal cannot apply on the selected path
    UNMEASURED = "UNMEASURED"  # no reading at all: it adds nothing to the lower bound and is never read as healthy


class GovernedPaperSystemStateObligationStatus(str, Enum):
    ENFORCED_BY_ENTRY_REFUSAL = "ENFORCED_BY_ENTRY_REFUSAL"
    FAIL_CLOSED_BY_SCALE_1 = "FAIL_CLOSED_BY_SCALE_1"
    BLOCKED_UNREPRESENTABLE = "BLOCKED_UNREPRESENTABLE"


_Status = GovernedPaperSystemStateObligationStatus
# The §1.29 per-state rules that act on entries, positions or orders, and how the paper path represents each.
_OBLIGATIONS: dict[int, tuple[tuple[str, GovernedPaperSystemStateObligationStatus, str], ...]] = {
    1: (
        (
            "t0_and_t1_edges_suspended",
            _Status.ENFORCED_BY_ENTRY_REFUSAL,
            "family_b_is_a_t1_edge_so_the_system_state_check_refuses_its_entry",
        ),
        (
            "remaining_allocation_reduced_by_30pct",
            _Status.FAIL_CLOSED_BY_SCALE_1,
            "no_reduced_allocation_is_representable_so_scale_1_refuses_the_entry",
        ),
    ),
    2: (
        ("no_new_entries_across_all_horizons", _Status.ENFORCED_BY_ENTRY_REFUSAL, "the_entry_is_refused"),
        (
            "trailing_stops_tightened_to_50pct_of_normal_width",
            _Status.BLOCKED_UNREPRESENTABLE,
            "no_trailing_stop_width_or_state_tightening_reading_is_defined",
        ),
        (
            "micro_and_intraday_positions_reduced_by_twap",
            _Status.BLOCKED_UNREPRESENTABLE,
            "twap_reduction_mechanics_are_undefined",
        ),
    ),
    3: (
        ("no_new_entries", _Status.ENFORCED_BY_ENTRY_REFUSAL, "the_entry_is_refused"),
        (
            "intraday_positions_exited_by_15min_twap",
            _Status.BLOCKED_UNREPRESENTABLE,
            "twap_exit_mechanics_are_undefined",
        ),
        (
            "all_pending_orders_cancelled",
            _Status.BLOCKED_UNREPRESENTABLE,
            "the_paper_engine_has_no_order_cancellation",
        ),
    ),
    4: (
        ("no_new_entries", _Status.ENFORCED_BY_ENTRY_REFUSAL, "the_entry_is_refused"),
        (
            "all_positions_flattened_by_market_orders",
            _Status.BLOCKED_UNREPRESENTABLE,
            "flattening_mechanics_are_undefined",
        ),
        (
            "all_orders_cancelled",
            _Status.BLOCKED_UNREPRESENTABLE,
            "the_paper_engine_has_no_order_cancellation",
        ),
        (
            "all_engines_disabled_until_a_manual_restart",
            _Status.BLOCKED_UNREPRESENTABLE,
            "no_engine_disable_or_restart_authority_exists_on_the_paper_path",
        ),
    ),
}


@dataclass(frozen=True)
class GovernedPaperSystemStateSignal:
    """One §1.29 signal at one decision: its weight, how it is read, its proven severity lower bound and why."""

    signal_id: str
    weight: str
    measurement: GovernedPaperSystemStateMeasurement
    lower_bound: str
    reason: str


@dataclass(frozen=True)
class GovernedPaperSystemStateObligation:
    """One §1.29 per-state rule of the bound state and its representation on the paper path (never executed here)."""

    state_id: str
    rule: str
    status: GovernedPaperSystemStateObligationStatus
    reason: str


@dataclass(frozen=True)
class GovernedPaperSystemStateReading:
    """The proven lower bound of the §1.29 state at one entry decision; ``reading_digest`` covers every other field.

    ``state_lower_bound`` is an index of ``SS-0``..``SS-4``: the true state is at least that state. A bound of 0 means
    that no state above SS-0 is proven, never that SS-0 is. The state is decided on exact values; each rendering keeps
    its bound's direction at scale 18: a severity and the stress lower bound are rounded down, the SHS upper bound up.
    """

    decision_sequence: int
    decision_time_ns: int
    signals: tuple[GovernedPaperSystemStateSignal, ...]
    stress_lower_bound: str
    shs_upper_bound: str
    state_lower_bound: int
    state_reason: str
    unmeasured_signal_ids: tuple[str, ...]
    obligations: tuple[GovernedPaperSystemStateObligation, ...]
    reading_digest: str


@dataclass(frozen=True)
class GovernedPaperSystemStateEvidence:
    """The system-state readings of every entry decision of one governed evaluation; ``evidence_digest`` covers the
    rest."""

    schema_version: str
    rule_id: str
    rule_digest: str
    instrument: str
    readings: tuple[GovernedPaperSystemStateReading, ...]
    evidence_digest: str
    paper_only: bool = True
    ss0_proven: bool = False
    state_upper_bound_proven: bool = False
    persistence_claimed: bool = False
    actions_executed: bool = False
    entry_authorized: bool = False


GOVERNED_PAPER_SYSTEM_STATE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("ss0_proven", False),
    ("state_upper_bound_proven", False),
    ("persistence_claimed", False),
    ("actions_executed", False),
    ("entry_authorized", False),
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperSystemStateError:
    return GovernedPaperSystemStateError(_reason(code))


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _render(value: Fraction) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:  # pragma: no cover - every severity, weight and bound lies in [0, 1]
        raise _fail("amount_unrepresentable")
    return rendered


def _render_down(value: Fraction) -> str:
    """A lower bound at scale 18, rounded down so its rendering never exceeds it (exact integer floor)."""

    return _render(Fraction(value.numerator * _SCALE // value.denominator, _SCALE))


def _render_up(value: Fraction) -> str:
    """An upper bound at scale 18, rounded up so its rendering is never below it (exact integer ceiling)."""

    return _render(Fraction(-(-value.numerator * _SCALE // value.denominator), _SCALE))


def governed_paper_system_state_rule() -> dict[str, object]:
    """The code-defined rule of the proven lower bound: every PRDV4 §1.29 value and every reading of this module."""

    return {
        "rule_id": GOVERNED_PAPER_SYSTEM_STATE_RULE_ID,
        "contract_id": GOVERNED_PAPER_SYSTEM_STATE_CONTRACT_ID,
        "authorities": [
            "PRDV4 §1.29",
            "PRDV4 §1.19",
            "PRDV4 §8.2",
            "PRDV4 §1.21",
            "PRDV4 §1.16",
            "CL2-7 S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1 r2: Family B is T1 and an entry needs a proven SS-0",
        ],
        "states": [f"{state}:{name}" for state, name in zip(_STATE_IDS, _STATE_NAMES, strict=True)],
        "weights": {name: _render(value) for name, value in _WEIGHTS.items()},
        "sources": dict(_SOURCES),
        "state_entry_shs_at_or_below": {_STATE_IDS[state]: _render(bound) for state, bound in _STATE_ENTRY},
        "critical_override": "any_proven_severity_of_1_s4_included_raises_the_bound_to_at_least_crisis",
        "s4_complete_data_loss": "its_defensive_minimum_is_cumulative_with_the_crisis_override_and_always_met_by_it",
        "precedence": "every_rule_is_a_cumulative_minimum_the_most_severe_binds_and_none_lowers_the_shs_entry_state",
        "kill_switch_halt": "ks4_is_never_proven_so_halt_is_never_reached_through_it",
        "instant": "the_entry_decision_instant_at_its_decision_phase_no_state_between_decisions_is_claimed",
        "persistence": "none_claimed_the_bound_reads_only_the_signals_proven_at_its_instant",
        "S1": "the_proven_lower_bound_of_the_kill_switch_ladder_at_the_decision_over_4",
        "S2": "1_on_a_proven_trigger_11_drawdown_beyond_15pct_2_3_on_a_proven_trigger_2_beyond_10pct_else_0",
        "S4": "the_proven_active_nt_d_conditions_of_the_decision_over_5",
        "S5": "the_proven_active_nt_x_conditions_of_the_decision_over_4",
        "S8": "proven_not_applicable_on_the_single_instrument_paper_portfolio_otherwise_unmeasured",
        "S10": "min_1_governed_latency_over_5_times_the_t1_budget_a_lower_bound_of_the_tier_maximum",
        "unmeasured": ["S3", "S6", "S7", "S9"],
        "ss0": "never_proven_no_signal_has_an_upper_bound_and_s3_s6_s7_s9_have_no_reading",
        "obligations": {
            _STATE_IDS[state]: [f"{rule}:{status.value}" for rule, status, _ in items]
            for state, items in sorted(_OBLIGATIONS.items())
        },
    }


GOVERNED_PAPER_SYSTEM_STATE_RULE = governed_paper_system_state_rule()
GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST = edge_sha256_text(edge_canonical_json(GOVERNED_PAPER_SYSTEM_STATE_RULE))


# --- one decision ------------------------------------------------------------------------------------------------------


def _signal(
    signal_id: str, measurement: GovernedPaperSystemStateMeasurement, value: Fraction, reason: str
) -> tuple[GovernedPaperSystemStateSignal, Fraction]:
    """One signal record and its exact severity lower bound."""

    weight = _render(_WEIGHTS[signal_id])  # every PRDV4 weight is exact at scale 18
    record = GovernedPaperSystemStateSignal(signal_id, weight, measurement, _render_down(value), reason)
    return record, value


def _state_lower_bound(shs: Fraction, critical_ids: tuple[str, ...]) -> tuple[int, str]:
    """The §1.29 state that a proven SHS upper bound and the proven critical severities give together (pure).

    Every rule is a minimum and the rules are cumulative, so the most severe one binds and none lowers another: the SHS
    entry state, and CRISIS for any proven severity of 1 (``critical_ids``, in signal order; the first one names the
    reason). S4's own DEFENSIVE minimum for a complete data loss is always met by the CRISIS that its severity of 1
    already imposes, and KS-4's HALT is never proven here.
    """

    state, reason = 0, "no_state_above_ss0_proven"
    for candidate, threshold in _STATE_ENTRY:
        if shs <= threshold:
            state, reason = candidate, f"shs_upper_bound_at_or_below_the_{_STATE_NAMES[candidate].lower()}_entry"
            break
    if critical_ids and state < _CRISIS:
        state, reason = _CRISIS, f"critical_override_{critical_ids[0].lower()}_severity_1"
    return state, reason


def _active_count(statuses: object, ids: tuple[str, ...], name: str) -> int:
    if (
        type(statuses) is not tuple
        or len(statuses) != len(ids)
        or any(type(item) is not tuple or len(item) != 2 for item in statuses)  # noqa: PLR2004 - (check id, status)
        or tuple(item[0] for item in statuses) != ids
        or any(type(item[1]) is not str or item[1] not in _GATE_STATUSES for item in statuses)
    ):
        raise _fail(f"inputs_malformed:{name}")
    return sum(1 for _, status in statuses if status == _ACTIVE)


def derive_governed_paper_system_state_reading(  # noqa: PLR0913
    *,
    decision_sequence: int,
    decision_time_ns: int,
    kill_switch_level: int,
    drawdown_beyond_10pct_proven: bool,
    drawdown_beyond_15pct_proven: bool,
    data_statuses: tuple[tuple[str, str], ...],
    execution_statuses: tuple[tuple[str, str], ...],
    latency_ns: int,
    latency_budget_ns: int | None,
    single_instrument_portfolio: bool,
) -> GovernedPaperSystemStateReading:
    """The proven lower bound of the §1.29 state at one entry decision (pure; see the module docstring).

    The inputs are the decision's own facts, derived by its governed evaluation: the ladder's proven level and drawdown
    proofs at the decision, the statuses of its NT-D01..NT-D05 and NT-X01..NT-X04 checks in that order, the governed
    latency with its tier budget (None when unknown) and the single-instrument fact. A malformed input raises
    ``GovernedPaperSystemStateError``.
    """

    for name, value in (("decision_sequence", decision_sequence), ("decision_time_ns", decision_time_ns)):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"inputs_malformed:{name}")
    if type(kill_switch_level) is not int or not 0 <= kill_switch_level < _KILL_SWITCH_LEVELS:
        raise _fail("inputs_malformed:kill_switch_level")
    for name, flag in (
        ("drawdown_beyond_10pct_proven", drawdown_beyond_10pct_proven),
        ("drawdown_beyond_15pct_proven", drawdown_beyond_15pct_proven),
        ("single_instrument_portfolio", single_instrument_portfolio),
    ):
        if type(flag) is not bool:
            raise _fail(f"inputs_malformed:{name}")
    if drawdown_beyond_15pct_proven and not drawdown_beyond_10pct_proven:
        raise _fail("inputs_malformed:drawdown_beyond_15pct_without_beyond_10pct")
    data_active = _active_count(data_statuses, _DATA_IDS, "data_statuses")
    execution_active = _active_count(execution_statuses, _EXECUTION_IDS, "execution_statuses")
    if not historical_execution_wire_int_is_valid(latency_ns, minimum=0):
        raise _fail("inputs_malformed:latency_ns")
    if latency_budget_ns is not None and not historical_execution_wire_int_is_valid(latency_budget_ns, minimum=1):
        raise _fail("inputs_malformed:latency_budget_ns")

    bound, unmeasured = GovernedPaperSystemStateMeasurement.LOWER_BOUND, GovernedPaperSystemStateMeasurement.UNMEASURED
    zero = Fraction(0)
    if drawdown_beyond_15pct_proven:
        drawdown = (Fraction(1), "trigger_11_drawdown_from_peak_beyond_15pct_proven")
    elif drawdown_beyond_10pct_proven:
        drawdown = (_T2_DRAWDOWN / _DRAWDOWN_NORMALIZER, "trigger_2_drawdown_from_peak_beyond_10pct_proven")
    else:
        drawdown = (zero, "no_drawdown_from_peak_beyond_10pct_proven_at_the_decision")
    if latency_budget_ns is None:
        latency = _signal("S10", unmeasured, zero, "latency_tier_budget_unknown")
    else:
        severity = min(Fraction(1), Fraction(latency_ns, _LATENCY_MULTIPLE * latency_budget_ns))
        latency = _signal(
            "S10", bound, severity, "governed_latency_over_5x_the_t1_budget_lower_bound_of_the_tier_maximum"
        )
    pairs = (
        _signal(
            "S1",
            bound,
            Fraction(kill_switch_level, _KILL_SWITCH_LEVELS),
            f"kill_switch_lower_bound_ks_{kill_switch_level}_at_the_decision",
        ),
        _signal("S2", bound, *drawdown),
        _signal("S3", unmeasured, zero, "portfolio_cvar99_methodology_undefined"),
        _signal(
            "S4",
            bound,
            Fraction(data_active, len(_DATA_IDS)),
            f"{data_active}_of_5_data_integrity_conditions_proven_active",
        ),
        _signal(
            "S5",
            bound,
            Fraction(execution_active, len(_EXECUTION_IDS)),
            f"{execution_active}_of_4_execution_conditions_proven_active",
        ),
        _signal("S6", unmeasured, zero, "liquidity_regime_methodology_undefined"),
        _signal("S7", unmeasured, zero, "feature_drift_index_not_produced"),
        _signal(
            "S8",
            GovernedPaperSystemStateMeasurement.PROVEN_NOT_APPLICABLE,
            zero,
            "single_instrument_paper_portfolio_has_no_pairwise_correlation",
        )
        if single_instrument_portfolio
        else _signal("S8", unmeasured, zero, "cross_asset_correlation_not_measured"),
        _signal("S9", unmeasured, zero, "margin_utilization_needs_a_paper_wallet_model_and_d1_margin_facts"),
        latency,
    )
    signals = tuple(item[0] for item in pairs)
    severities = {item[0].signal_id: item[1] for item in pairs}
    stress = sum((_WEIGHTS[name] * severities[name] for name in GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS), zero)
    shs = 1 - stress
    critical = tuple(
        item.signal_id for item in signals if item.measurement is bound and severities[item.signal_id] == 1
    )
    state, reason = _state_lower_bound(shs, critical)
    seed = GovernedPaperSystemStateReading(
        decision_sequence=decision_sequence,
        decision_time_ns=decision_time_ns,
        signals=signals,
        stress_lower_bound=_render_down(stress),
        shs_upper_bound=_render_up(shs),
        state_lower_bound=state,
        state_reason=reason,
        unmeasured_signal_ids=tuple(item.signal_id for item in signals if item.measurement is unmeasured),
        obligations=tuple(
            GovernedPaperSystemStateObligation(_STATE_IDS[state], rule, status, why)
            for rule, status, why in _OBLIGATIONS.get(state, ())
        ),
        reading_digest="",
    )
    return replace(seed, reading_digest=edge_payload_digest(_to_payload(seed), _READING_DIGEST_FIELD))


def governed_paper_system_state_id(reading: GovernedPaperSystemStateReading) -> str:
    """The id (``SS-0``..``SS-4``) of a reading's lower bound; ``SS-0`` means no higher state is proven."""

    return _STATE_IDS[reading.state_lower_bound]


# --- the evidence of one evaluation ------------------------------------------------------------------------------------


def build_governed_paper_system_state_evidence(
    *, instrument: str, readings: Sequence[GovernedPaperSystemStateReading]
) -> GovernedPaperSystemStateEvidence:
    """Bind the readings of every entry decision of one evaluation, in decision order (pure)."""

    if type(instrument) is not str or instrument == "":
        raise _fail("instrument_malformed")
    items = tuple(readings)
    if any(type(item) is not GovernedPaperSystemStateReading for item in items):
        raise _fail("readings_malformed")
    order = [(item.decision_time_ns, item.decision_sequence) for item in items]
    if order != sorted(set(order)):
        raise _fail("readings_malformed")
    for item in items:
        if edge_payload_digest(_to_payload(item), _READING_DIGEST_FIELD) != item.reading_digest:
            raise _fail("reading_digest_mismatch")
    seed = GovernedPaperSystemStateEvidence(
        schema_version=_SCHEMA_VERSION,
        rule_id=GOVERNED_PAPER_SYSTEM_STATE_RULE_ID,
        rule_digest=GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST,
        instrument=instrument,
        readings=items,
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), _DIGEST_FIELD))


def governed_paper_system_state_evidence_to_dict(evidence: GovernedPaperSystemStateEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_system_state_evidence_digest(evidence: GovernedPaperSystemStateEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _DIGEST_FIELD)


def governed_paper_system_state_reading_digest(reading: GovernedPaperSystemStateReading) -> str:
    """Recompute the canonical reading digest, excluding only ``reading_digest``."""

    return edge_payload_digest(_to_payload(reading), _READING_DIGEST_FIELD)


__all__ = [
    "GOVERNED_PAPER_SYSTEM_STATE_CONTRACT_ID",
    "GOVERNED_PAPER_SYSTEM_STATE_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_SYSTEM_STATE_RULE",
    "GOVERNED_PAPER_SYSTEM_STATE_RULE_DIGEST",
    "GOVERNED_PAPER_SYSTEM_STATE_RULE_ID",
    "GOVERNED_PAPER_SYSTEM_STATE_SIGNAL_IDS",
    "GovernedPaperSystemStateError",
    "GovernedPaperSystemStateEvidence",
    "GovernedPaperSystemStateMeasurement",
    "GovernedPaperSystemStateObligation",
    "GovernedPaperSystemStateObligationStatus",
    "GovernedPaperSystemStateReading",
    "GovernedPaperSystemStateSignal",
    "build_governed_paper_system_state_evidence",
    "derive_governed_paper_system_state_reading",
    "governed_paper_system_state_evidence_digest",
    "governed_paper_system_state_evidence_to_dict",
    "governed_paper_system_state_id",
    "governed_paper_system_state_reading_digest",
    "governed_paper_system_state_rule",
]
