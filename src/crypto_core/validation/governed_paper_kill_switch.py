"""Governed paper kill-switch proven escalation (S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1): a PRDV4 §1.19 lower bound.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.19 (the black swan kill-switch ladder), read with §1.16
(latency tiers), §1.21 (NT-R01 and NT-T02), §1.26 (the DTL input of KS-2) and §1.29 (the ladder level is one input of
the system state, never the system state); the governed paper path of
``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7. Paper-only, deterministic, point-in-time and
fail-closed. It creates no order, closes no position, authorizes no recovery and proves no venue fact.

What it proves. Only a LOWER BOUND of the §1.19 level of one governed paper evaluation. Every reading recorded here is a
trigger proven TRUE on authenticated records and on the one economics engine (``historical_execution_economics``);
every trigger it cannot prove TRUE is UNPROVEN, never FALSE. An unproven trigger may be active, so neither KS-0 nor KS-1
is ever proven: there is no upper bound, no cooldown state and no recovery authority here. A consumer may refuse on a
proven level and on nothing else (NT-R01 of ``governed_paper_entry_safety`` rule set v5); nothing here admits an entry.

Readings (proven TRUE only; each threshold is PRDV4 §1.19's, strict, and equality never triggers):

* T1 intraday drawdown: at each decision snapshot of the governed decision portfolio (publication-visible, the engine's
  own valuation) whose NAV and UTC day-start NAV are available, ``(nav - day_start) / day_start < -5%``. "Intraday" and
  its session start are read exactly as NT-R02 reads its intraday base on this path: the UTC midnight that starts the
  decision's day, valued as known at the decision. A partial first day has no day start and proves nothing;
* T2 and T11 drawdown from peak: the peak is the running maximum of the publication-visible NAV observed since the
  lineage start G, the engine's initial equity at G included (the governed lineage's inception, as RG-4 runs its peak
  from the window start). ``(nav - peak) / peak < -10%`` (T2, standard) and ``< -15%`` (T11, critical). Observing only
  at decisions yields a peak no higher and a drawdown no deeper than the continuous one, so a reading is sound;
* T5 loss streak: the CLOSED trades of the governed outcome in close order. A trade is losing once its realized gross
  and net PnL are both strictly negative (losing under every reading of "losing") and every funding record it settled
  is visible; T5 holds from the instant the latest five closed trades are all known losing until the next trade closes;
* T6 funding spike: the economics' own final funding series. Only an approved funding interval of exactly 8 h reads
  "per 8 h" (no normalization is invented); the engine proves the series an exact grid. T6 holds while the four latest
  consecutive final rates visible are all strictly above 0.1% in absolute value, from the visibility of the fourth;
* T7 latency: the governed simulated latency, the only latency of the paper path (NT-X01's reading, tier T1 100 ms),
  strictly above ten times the tier budget holds from G on, so T7 holds strictly more than 60 s after G.

A drawdown reading is a point ``[t, t + 1)`` at its decision instant: between samples a breach is unproven, never
absent. T4 is proven not applicable on the one-sleeve, one-instrument paper portfolio (NT-M04's proof). UNMEASURED, so
never TRUE here: T3 (no §1.18 CVaR methodology or governed producer), T8 (no §1.17 liquidity methodology or history
coverage), T9 (no authenticated exchange-API health reading on the paper path), T10 (the data contract authenticates no
BTC price identity; a symbol string is no identity), T12 (PRDV4 defines no critical-feed membership), KS4 (no §1.19
trigger defines a system-integrity threat) and DTL (§1.26 needs a margin and liquidation-distance model); T1, T2, T5,
T11 without a simulated governed re-run, T6 without an 8 h interval and T7 without a known tier budget are unmeasured
too.

Bound. At each instant the triggers proven TRUE then give their §1.19 level: KS-3 for any critical or three standard
triggers, KS-2 for two simultaneous standard triggers, KS-1 for one. Escalation is immediate, so under every reading of
§1.19 the true level is at least that level at that instant (and may skip levels to reach it). A proven KS-3 holds from
then on: KS-3 is left only through a governed human recovery approval, and none exists or is accepted here. Below KS-3
the bound claims no persistence. §1.19 keeps a level up during an event and leaves it once its triggers have cleared and
its cool-down has elapsed, but the clause reads that cool-down either from the clearing or from the level's entry; under
the latter an event that an unproven trigger opened earlier may already have run out its cool-down, so no persistence
after the proven triggers end holds under every reading. The bound therefore falls back to the triggers proven at each
instant: a fall records that a proof ended, never a de-escalation, and no cool-down is ever claimed or denied. The bound
is monotone in the proven readings and never exceeds the true level under any of those readings, so it stays a lower
bound whatever reading a human later adopts. KS-4 is never entered.

Every change of the bound is a transition recorded with its instant, the triggers proven at it and the identities of
their readings. A reading's evidence names the snapshots and trades of its own engine re-run, whose digests derive from
that run, so ``governed_paper_kill_switch_prefix_digest`` projects the bound before an instant onto its run-independent
content (each reading's trigger, start, end clipped there and observed value; each transition's instant, levels and
proven triggers): a causal replay over a later archive yields the same prefix, and consecutive day seals bind it.

The ladder binds the economics, its policy, the archive, the decision portfolio and the governed outcome it reads, each
re-proven by its public digest. Exact arithmetic, no float, no ``decimal`` context, and no IO, clock or randomness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionGovernedPaperDecisionPortfolio,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionTradeStatus,
    historical_execution_economics_digest,
    historical_execution_governed_paper_decision_portfolio_digest,
    historical_execution_governed_paper_outcome_digest,
)
from crypto_core.validation.historical_execution_economics_policy import (
    LATENCY_TIER_PRDV4_T1,
    HistoricalExecutionEconomicsPolicy,
    historical_execution_decimal_is_canonical,
    historical_execution_economics_policy_digest,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    historical_pit_dataset_digest,
)

GOVERNED_PAPER_KILL_SWITCH_RULE_ID = "governed-paper-kill-switch-proven-escalation.v1"
_SCHEMA_VERSION = "governed-paper-kill-switch-ladder.v1"
_PREFIX = "governed_paper_kill_switch"
_DIGEST_FIELD = "ladder_digest"
_NS_PER_SECOND = 1_000_000_000
_HOUR_NS = 3_600 * _NS_PER_SECOND
_FUNDING_PERIOD_NS = 8 * _HOUR_NS  # §1.19 trigger 6 quotes the funding rate "per 8h"
_INTRADAY_DRAWDOWN = Fraction(-5, 100)  # trigger 1
_PEAK_DRAWDOWN = Fraction(-10, 100)  # trigger 2
_CRITICAL_PEAK_DRAWDOWN = Fraction(-15, 100)  # trigger 11
_LOSS_STREAK = 5  # trigger 5: at least five consecutive losing trades
_FUNDING_SPIKE = Fraction(1, 1_000)  # trigger 6: |FR| > 0.1% per 8 h
_FUNDING_SPIKE_PERIODS = 4  # trigger 6: for more than three consecutive periods
_LATENCY_MULTIPLE = 10  # trigger 7: L > 10 x L_tier
_LATENCY_PERSISTENCE_NS = 60 * _NS_PER_SECOND  # trigger 7: for more than 60 seconds

# §1.16 latency budget per tier: tier T1 Critical (< 100 ms) is the Funding (B) tier, the one NT-X01 reads.
GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS: Mapping[str, int] = {LATENCY_TIER_PRDV4_T1: 100_000_000}

_STANDARD = "STANDARD"
_CRITICAL = "CRITICAL"
# Every §1.19 trigger in PRDV4 order, then the two further level inputs; (id, severity, condition).
GOVERNED_PAPER_KILL_SWITCH_TRIGGERS: tuple[tuple[str, str, str], ...] = (
    ("T1", _STANDARD, "portfolio_drawdown_intraday_lt_minus_5pct"),
    ("T2", _STANDARD, "portfolio_drawdown_from_peak_lt_minus_10pct"),
    ("T3", _STANDARD, "realized_loss_gt_2x_the_cvar99_estimate"),
    ("T4", _STANDARD, "average_pairwise_correlation_gt_0.85"),
    ("T5", _STANDARD, "at_least_5_consecutive_losing_trades"),
    ("T6", _STANDARD, "abs_funding_rate_gt_0.1pct_per_8h_for_gt_3_consecutive_periods"),
    ("T7", _STANDARD, "latency_gt_10x_the_tier_budget_for_gt_60s"),
    ("T8", _STANDARD, "liquidity_regime_crisis_for_gt_30min"),
    ("T9", _CRITICAL, "exchange_api_unresponsive_gt_120s"),
    ("T10", _CRITICAL, "btc_abs_move_gt_15pct_in_5min"),
    ("T11", _CRITICAL, "portfolio_drawdown_from_peak_gt_15pct"),
    ("T12", _CRITICAL, "data_integrity_gap_gt_60s_in_a_critical_feed"),
    ("KS4", "KS4_INPUT", "system_integrity_threat"),
    ("DTL", "KS2_INPUT", "distance_to_liquidation_lt_3pct_section_1_26"),
)
GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS: tuple[str, ...] = tuple(item[0] for item in GOVERNED_PAPER_KILL_SWITCH_TRIGGERS)
_SEVERITY = {item[0]: item[1] for item in GOVERNED_PAPER_KILL_SWITCH_TRIGGERS}
_ORDER = {name: index for index, name in enumerate(GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS)}
_LADDER_IDS = frozenset(
    name for name, severity, _ in GOVERNED_PAPER_KILL_SWITCH_TRIGGERS if severity in (_STANDARD, _CRITICAL)
)
# Why a trigger is never read TRUE on the governed paper path (a fixed vocabulary, never caller text).
_UNMEASURED: Mapping[str, str] = {
    "T3": "cvar99_methodology_and_governed_producer_absent",
    "T8": "liquidity_regime_methodology_and_history_coverage_absent",
    "T9": "no_authenticated_exchange_api_health_reading_on_the_paper_path",
    "T10": "btc_price_identity_not_authenticated_by_the_data_contract",
    "T12": "critical_feed_membership_not_defined",
    "KS4": "no_section_1_19_trigger_defines_a_system_integrity_threat",
    "DTL": "margin_and_liquidation_distance_model_absent",
}
_NOT_SIMULATED = "governed_portfolio_not_simulated"
_INTERVAL_NOT_8H = "approved_funding_interval_is_not_8h_and_no_normalization_exists"
_TIER_UNKNOWN = "latency_tier_budget_unknown"
_SINGLE_INSTRUMENT = "single_instrument_paper_portfolio_has_no_pairwise_correlation"
_CORRELATION_UNMEASURED = "cross_asset_correlation_not_measured"


class GovernedPaperKillSwitchError(EdgeArtifactError):
    """Malformed input or a binding defect: a ladder is never represented over it."""


class GovernedPaperKillSwitchMeasurement(str, Enum):
    MEASURED = "MEASURED"  # TRUE readings are derived; absence is still never proven
    NOT_APPLICABLE = "NOT_APPLICABLE"  # proven inapplicable on the selected path
    UNMEASURED = "UNMEASURED"  # never read TRUE here, never FALSE


@dataclass(frozen=True)
class GovernedPaperKillSwitchTriggerState:
    """How one trigger is read by this evaluation, with the fixed reason of an unmeasured or inapplicable one."""

    trigger_id: str
    severity: str
    measurement: GovernedPaperKillSwitchMeasurement
    reason: str


@dataclass(frozen=True)
class GovernedPaperKillSwitchReading:
    """One proven TRUE interval ``[start_ns, end_ns)`` of one trigger; ``end_ns`` is None while TRUE at the horizon.

    ``reading_id`` digests every other field but ``end_ns``; the transitions of the ladder name their readings by it.
    """

    trigger_id: str
    start_ns: int
    end_ns: int | None
    observed: str
    evidence_digests: tuple[str, ...]
    reading_id: str


@dataclass(frozen=True)
class GovernedPaperKillSwitchTransition:
    """One level change of the lower-bound ladder, with the triggers proven at its instant and their readings."""

    time_ns: int
    from_level: int
    to_level: int
    proven_trigger_ids: tuple[str, ...]
    reading_ids: tuple[str, ...]
    transition_digest: str


@dataclass(frozen=True)
class GovernedPaperKillSwitchLadder:
    """The proven lower-bound §1.19 ladder of one governed evaluation over ``[start_ns, horizon_ns)``."""

    schema_version: str
    rule_id: str
    rule_digest: str
    instrument: str
    economics_result_digest: str
    economics_policy_digest: str
    dataset_digest: str
    decision_portfolio_digest: str
    governed_outcome_digest: str
    schedule_digest: str
    start_ns: int
    horizon_ns: int
    triggers: tuple[GovernedPaperKillSwitchTriggerState, ...]
    readings: tuple[GovernedPaperKillSwitchReading, ...]
    transitions: tuple[GovernedPaperKillSwitchTransition, ...]
    ladder_digest: str
    paper_only: bool = True
    level_upper_bound_proven: bool = False
    cooldown_state_proven: bool = False
    recovery_authorized: bool = False
    venue_health_proven: bool = False
    entry_authorized: bool = False


GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("level_upper_bound_proven", False),
    ("cooldown_state_proven", False),
    ("recovery_authorized", False),
    ("venue_health_proven", False),
    ("entry_authorized", False),
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperKillSwitchError:
    return GovernedPaperKillSwitchError(_reason(code))


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
    if rendered is None:  # pragma: no cover - the PRDV4 thresholds are representable
        raise _fail("threshold_unrepresentable")
    return rendered


def _ordered(ids: object) -> tuple[str, ...]:
    return tuple(sorted(set(ids), key=_ORDER.__getitem__))  # type: ignore[call-overload]


def governed_paper_kill_switch_rule() -> dict[str, object]:
    """The rule this module evaluates: every trigger, its severity and reading, the ladder and its non-claims."""

    return {
        "rule_id": GOVERNED_PAPER_KILL_SWITCH_RULE_ID,
        "contract_id": "S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1",
        "authorities": ["PRDV4 §1.19", "PRDV4 §1.16", "PRDV4 §1.21", "PRDV4 §1.26", "PRDV4 §1.29"],
        "bound": "lower_bound_only_every_reading_proven_true_every_other_trigger_unproven_never_false",
        "triggers": [
            {"trigger_id": name, "severity": severity, "condition": condition}
            for name, severity, condition in GOVERNED_PAPER_KILL_SWITCH_TRIGGERS
        ],
        "levels": {
            "KS-1": "any_1_proven_standard_trigger",
            "KS-2": "any_2_simultaneous_proven_standard_triggers",
            "KS-3": "any_3_proven_standard_triggers_or_any_proven_critical_trigger",
        },
        "escalation": "immediate_at_each_instant_the_level_of_the_simultaneous_proven_triggers",
        "persistence": "none_below_ks3_the_de_escalation_clause_reads_the_cooldown_from_the_clearing_or_from_the_"
        "level_entry_and_an_earlier_unproven_entry_may_have_run_it_out_a_fall_is_a_proof_ending_never_a_de_escalation",
        "cooldown": "never_claimed_nor_denied",
        "ks3": "absorbing_recovery_needs_a_governed_human_approval_and_none_is_accepted",
        "ks4": "never_entered_no_trigger_defines_it",
        "T1": "decision_snapshot_nav_against_the_utc_day_start_nav_as_known_at_the_decision_the_nt_r02_intraday_base",
        "T2_T11": "decision_snapshot_nav_against_the_running_peak_of_the_publication_visible_nav_since_g_"
        "initial_equity_included",
        "T5": "the_latest_five_closed_trades_known_losing_gross_and_net_strictly_negative_with_every_settled_funding_"
        "record_visible_until_the_next_close",
        "T6": "the_four_latest_consecutive_visible_final_rates_of_the_economics_funding_series_on_an_approved_8h_"
        "interval_all_strictly_above_in_absolute_value",
        "T7": "the_governed_simulated_latency_strictly_above_ten_times_the_tier_budget_strictly_more_than_60s_after_g",
        "sampling": "a_drawdown_reading_is_a_point_at_its_decision_instant_a_breach_between_samples_is_unproven",
        "thresholds": {
            "T1": _render(_INTRADAY_DRAWDOWN),
            "T2": _render(_PEAK_DRAWDOWN),
            "T11": _render(_CRITICAL_PEAK_DRAWDOWN),
            "T5": _LOSS_STREAK,
            "T6": _render(_FUNDING_SPIKE),
            "T6_periods": _FUNDING_SPIKE_PERIODS,
            "T6_period_ns": _FUNDING_PERIOD_NS,
            "T7_multiple": _LATENCY_MULTIPLE,
            "T7_persistence_ns": _LATENCY_PERSISTENCE_NS,
            "tier_latency_budget_ns": dict(GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS),
        },
        "not_applicable": {"T4": _SINGLE_INSTRUMENT},
        "unmeasured": dict(_UNMEASURED),
    }


GOVERNED_PAPER_KILL_SWITCH_RULE = governed_paper_kill_switch_rule()
GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST = edge_sha256_text(edge_canonical_json(GOVERNED_PAPER_KILL_SWITCH_RULE))


# --- the lower-bound ladder ------------------------------------------------------------------------------------------------


def _reading(
    trigger_id: str, start: int, end: int | None, observed: str, evidence: Sequence[str]
) -> GovernedPaperKillSwitchReading:
    identity = {
        "trigger_id": trigger_id,
        "start_ns": start,
        "observed": observed,
        "evidence_digests": list(evidence),
    }
    return GovernedPaperKillSwitchReading(
        trigger_id=trigger_id,
        start_ns=start,
        end_ns=end,
        observed=observed,
        evidence_digests=tuple(evidence),
        reading_id=edge_sha256_text(edge_canonical_json(identity)),
    )


def _target(ids: Sequence[str]) -> int:
    """The §1.19 level of a set of simultaneously proven triggers."""

    critical = sum(1 for name in ids if _SEVERITY[name] == _CRITICAL)
    standard = sum(1 for name in ids if _SEVERITY[name] == _STANDARD)
    if critical or standard >= 3:
        return 3
    return standard


def _canonical_readings(
    readings: object, *, start_ns: int, horizon_ns: int
) -> tuple[GovernedPaperKillSwitchReading, ...]:
    if type(readings) is not tuple:
        raise _fail("readings_malformed")
    for item in readings:
        if type(item) is not GovernedPaperKillSwitchReading or item.trigger_id not in _LADDER_IDS:
            raise _fail("reading_malformed")
        if not historical_execution_wire_int_is_valid(item.start_ns, minimum=0) or not (
            start_ns <= item.start_ns < horizon_ns
        ):
            raise _fail("reading_outside_the_evaluation")
        if item.end_ns is not None and (
            not historical_execution_wire_int_is_valid(item.end_ns, minimum=0) or item.end_ns <= item.start_ns
        ):
            raise _fail("reading_interval_malformed")
    return readings  # type: ignore[return-value]


def governed_paper_kill_switch_transitions(
    readings: tuple[GovernedPaperKillSwitchReading, ...], *, start_ns: int, horizon_ns: int
) -> tuple[GovernedPaperKillSwitchTransition, ...]:
    """Every change of the proven lower bound over proven readings on ``[start_ns, horizon_ns)`` (see the module
    docstring). Pure.

    The bound starts at 0 at ``start_ns`` (a lower bound, never a proven KS-0). At each instant it is the level of the
    triggers proven then, and 3 from the first proven KS-3 on. Readings are half-open: one that starts at an instant
    counts there, one that ends there does not.
    """

    if not historical_execution_wire_int_is_valid(start_ns, minimum=0) or not historical_execution_wire_int_is_valid(
        horizon_ns, minimum=0
    ):
        raise _fail("evaluation_window_malformed")
    if horizon_ns <= start_ns:
        raise _fail("evaluation_window_malformed")
    readings = _canonical_readings(readings, start_ns=start_ns, horizon_ns=horizon_ns)
    instants = sorted(
        {start_ns}
        | {item.start_ns for item in readings}
        | {item.end_ns for item in readings if item.end_ns is not None and item.end_ns < horizon_ns}
    )
    transitions: list[GovernedPaperKillSwitchTransition] = []
    bound = 0
    for at in instants:
        covering = [item for item in readings if item.start_ns <= at and (item.end_ns is None or at < item.end_ns)]
        # immediate escalation to the proven level; a proven KS-3 is absorbing; below it no persistence is claimed
        following = 3 if bound == 3 else _target([item.trigger_id for item in covering])
        if following == bound:
            continue
        body = {
            "time_ns": at,
            "from_level": bound,
            "to_level": following,
            "proven_trigger_ids": list(_ordered(item.trigger_id for item in covering)),
            "reading_ids": sorted(item.reading_id for item in covering),
            "transition_digest": "",
        }
        transitions.append(
            GovernedPaperKillSwitchTransition(
                time_ns=at,
                from_level=bound,
                to_level=following,
                proven_trigger_ids=tuple(body["proven_trigger_ids"]),  # type: ignore[arg-type]
                reading_ids=tuple(body["reading_ids"]),  # type: ignore[arg-type]
                transition_digest=edge_payload_digest(body, "transition_digest"),
            )
        )
        bound = following
    return tuple(transitions)


# --- the native readers ------------------------------------------------------------------------------------------------


def _visibility(record: HistoricalPitRecord) -> int | None:
    if record.finalized_at_ns is None:
        return None
    return max(record.available_at_ns, record.finalized_at_ns)


def _value(record: HistoricalPitRecord, name: str) -> Fraction | None:
    values = [item.value for item in record.values if item.name == name]
    if len(values) != 1 or not historical_execution_decimal_is_canonical(values[0]):
        return None
    return Fraction(values[0])


def _drawdown_readings(
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio,
    *,
    initial_equity: Fraction,
    initial_digest: str,
    start_ns: int,
    horizon_ns: int,
) -> list[GovernedPaperKillSwitchReading]:
    """T1, T2 and T11 at each decision snapshot (a point reading each); see the module docstring."""

    readings: list[GovernedPaperKillSwitchReading] = []
    peak, peak_digest = initial_equity, initial_digest
    for snapshot in sorted(portfolio.snapshots, key=lambda item: (item.decision_time_ns, item.decision_sequence)):
        at = snapshot.decision_time_ns
        if snapshot.nav is None or not start_ns <= at < horizon_ns:
            continue
        nav = Fraction(snapshot.nav)
        if nav > peak:
            peak, peak_digest = nav, snapshot.snapshot_digest
        change = (nav - peak) / peak
        rendered = historical_execution_render_amount(change)
        if rendered is not None:
            evidence = (snapshot.snapshot_digest, peak_digest)
            if change < _PEAK_DRAWDOWN:
                readings.append(_reading("T2", at, at + 1, rendered, evidence))
            if change < _CRITICAL_PEAK_DRAWDOWN:
                readings.append(_reading("T11", at, at + 1, rendered, evidence))
        if snapshot.day_start_nav is not None and Fraction(snapshot.day_start_nav) > 0:
            start = Fraction(snapshot.day_start_nav)
            intraday = (nav - start) / start
            rendered = historical_execution_render_amount(intraday)
            if rendered is not None and intraday < _INTRADAY_DRAWDOWN:
                readings.append(_reading("T1", at, at + 1, rendered, (snapshot.snapshot_digest,)))
    return readings


def _loss_streak_readings(
    outcome: HistoricalExecutionGovernedPaperOutcome,
    visibility: Mapping[str, int | None],
    *,
    start_ns: int,
    horizon_ns: int,
) -> list[GovernedPaperKillSwitchReading]:
    """T5: from the instant the latest five closed trades are all known losing until the next trade closes."""

    cashflows = {item.cashflow_digest: item.funding_record_digest for item in outcome.funding_cashflows}
    closed = sorted(
        (item for item in outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED),
        key=lambda item: (item.end_time_ns, item.trade_digest),
    )
    known: list[int | None] = []  # the instant each closed trade is known losing, None when not proven losing
    evidence: list[tuple[str, ...]] = []
    for trade in closed:
        records = tuple(sorted(cashflows.get(name, "") for name in trade.funding_cashflow_digests))
        published = [visibility.get(name) for name in records]
        losing = Fraction(trade.realized_gross_pnl) < 0 and Fraction(trade.realized_net_pnl) < 0
        if not losing or trade.end_time_ns is None or any(item is None for item in published):
            known.append(None)
        else:
            known.append(max([trade.end_time_ns, *published]))  # type: ignore[list-item]
        evidence.append((trade.trade_digest, *records))
    readings: list[GovernedPaperKillSwitchReading] = []
    for last in range(_LOSS_STREAK - 1, len(closed)):
        window = known[last - _LOSS_STREAK + 1 : last + 1]
        if any(item is None for item in window):
            continue
        start = max(start_ns, *window)  # type: ignore[arg-type]
        end = closed[last + 1].end_time_ns if last + 1 < len(closed) else None
        if (end is not None and start >= end) or start >= horizon_ns:
            continue
        digests = sorted({name for item in evidence[last - _LOSS_STREAK + 1 : last + 1] for name in item})
        readings.append(_reading("T5", start, end, str(_LOSS_STREAK), digests))
    return readings


@dataclass(frozen=True)
class _Rate:
    event_ns: int
    rate: Fraction | None
    visible_ns: int | None
    digest: str


def _funding_spike_readings(
    rates: list[_Rate], *, interval_ns: int, start_ns: int, horizon_ns: int
) -> list[GovernedPaperKillSwitchReading]:
    """T6 over the series' final rates in sequence order (see the module docstring).

    At each instant the latest visible rate and the three before it must all be visible, consecutive on the exact grid
    and strictly beyond the threshold; anything less proves nothing.
    """

    instants = sorted(
        {start_ns}
        | {item.visible_ns for item in rates if item.visible_ns is not None and start_ns < item.visible_ns < horizon_ns}
    )
    segments: list[tuple[int, int, tuple[int, ...]]] = []
    for index, at in enumerate(instants):
        following = instants[index + 1] if index + 1 < len(instants) else horizon_ns
        seen = {
            position for position, item in enumerate(rates) if item.visible_ns is not None and item.visible_ns <= at
        }
        if not seen:
            continue
        latest = max(seen)
        window = tuple(range(latest - _FUNDING_SPIKE_PERIODS + 1, latest + 1))
        if window[0] < 0 or not seen.issuperset(window):
            continue
        if any(
            rates[later].event_ns - rates[earlier].event_ns != interval_ns for earlier, later in zip(window, window[1:])
        ):
            continue
        if any(rates[position].rate is None or abs(rates[position].rate) <= _FUNDING_SPIKE for position in window):  # type: ignore[arg-type]
            continue
        segments.append((at, following, window))
    readings: list[GovernedPaperKillSwitchReading] = []
    for index, (at, following, window) in enumerate(segments):
        if index and segments[index - 1][2] == window and segments[index - 1][1] == at:
            continue  # the same window continues: one reading
        end = following
        for later in segments[index + 1 :]:
            if later[2] != window or later[0] != end:
                break
            end = later[1]
        observed = historical_execution_render_amount(min(abs(rates[position].rate) for position in window))  # type: ignore[arg-type,type-var]
        digests = [rates[position].digest for position in window]
        readings.append(_reading("T6", at, None if end >= horizon_ns else end, observed or "", digests))
    return readings


# --- the ladder of one governed evaluation -------------------------------------------------------------------------------


def _states(
    *, simulated: bool, interval_8h: bool, tier_known: bool, single_instrument_portfolio: bool
) -> tuple[GovernedPaperKillSwitchTriggerState, ...]:
    measured = GovernedPaperKillSwitchMeasurement.MEASURED
    unmeasured = GovernedPaperKillSwitchMeasurement.UNMEASURED
    reasons: dict[str, tuple[GovernedPaperKillSwitchMeasurement, str]] = {
        name: (unmeasured, reason) for name, reason in _UNMEASURED.items()
    }
    for name in ("T1", "T2", "T5", "T11"):
        reasons[name] = (measured, "") if simulated else (unmeasured, _NOT_SIMULATED)
    reasons["T6"] = (measured, "") if interval_8h else (unmeasured, _INTERVAL_NOT_8H)
    reasons["T7"] = (measured, "") if tier_known else (unmeasured, _TIER_UNKNOWN)
    reasons["T4"] = (
        (GovernedPaperKillSwitchMeasurement.NOT_APPLICABLE, _SINGLE_INSTRUMENT)
        if single_instrument_portfolio
        else (unmeasured, _CORRELATION_UNMEASURED)
    )
    return tuple(
        GovernedPaperKillSwitchTriggerState(name, _SEVERITY[name], reasons[name][0], reasons[name][1])
        for name in GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS
    )


def build_governed_paper_kill_switch_ladder(
    *,
    policy: HistoricalExecutionEconomicsPolicy,
    dataset: HistoricalPitDataset,
    economics: HistoricalExecutionEconomicsResult,
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    single_instrument_portfolio: bool,
) -> GovernedPaperKillSwitchLadder:
    """The proven lower-bound ladder of one governed evaluation (see the module docstring). Pure.

    ``portfolio`` and ``outcome`` are the decision portfolio and the governed outcome of ONE engine re-run of
    ``economics`` under one schedule (``simulate_historical_execution_governed_paper_decision_portfolio_and_outcome``);
    ``single_instrument_portfolio`` is the genesis envelope's fact the entry gate derives (NT-M04's proof). Every input
    is re-proven by its public digest and must bind the others; a malformed or foreign input raises
    ``GovernedPaperKillSwitchError``.
    """

    if (
        type(policy) is not HistoricalExecutionEconomicsPolicy
        or type(dataset) is not HistoricalPitDataset
        or type(economics) is not HistoricalExecutionEconomicsResult
        or type(portfolio) is not HistoricalExecutionGovernedPaperDecisionPortfolio
        or type(outcome) is not HistoricalExecutionGovernedPaperOutcome
        or type(single_instrument_portfolio) is not bool
    ):
        raise _fail("input_malformed")
    if (
        historical_execution_economics_policy_digest(policy) != policy.policy_digest
        or historical_pit_dataset_digest(dataset) != dataset.dataset_digest
        or historical_execution_economics_digest(economics) != economics.result_digest
        or historical_execution_governed_paper_decision_portfolio_digest(portfolio) != portfolio.portfolio_digest
        or historical_execution_governed_paper_outcome_digest(outcome) != outcome.outcome_digest
    ):
        raise _fail("input_digest_mismatch")
    if (
        economics.economics_policy_digest != policy.policy_digest
        or economics.instrument != policy.instrument
        or economics.dataset_digest != dataset.dataset_digest
        or outcome.dataset_digest != dataset.dataset_digest
        or portfolio.baseline_result_digest != economics.result_digest
        or outcome.baseline_result_digest != economics.result_digest
        or outcome.run_digest != economics.run_digest
        or portfolio.run_digest != economics.run_digest
        or portfolio.outcome_digest != outcome.outcome_digest
        or portfolio.schedule_digest != outcome.schedule_digest
        or portfolio.simulated is not outcome.simulated
    ):
        raise _fail("inputs_not_of_one_governed_re_run")
    start, horizon = economics.evaluation_start_ns, economics.evaluation_end_ns
    simulated = outcome.simulated is True
    visibility = {item.record_digest: _visibility(item) for item in dataset.records}
    readings: list[GovernedPaperKillSwitchReading] = []
    if simulated:
        readings += _drawdown_readings(
            portfolio,
            initial_equity=Fraction(policy.initial_equity),
            initial_digest=policy.policy_digest,
            start_ns=start,
            horizon_ns=horizon,
        )
        readings += _loss_streak_readings(outcome, visibility, start_ns=start, horizon_ns=horizon)
    interval_8h = policy.funding_interval_ns == _FUNDING_PERIOD_NS
    if interval_8h:
        series = sorted(
            (
                item
                for item in dataset.records
                if item.series_id == economics.funding_series_id and item.instrument == economics.instrument
            ),
            key=lambda item: item.sequence_id,
        )
        rates = [
            _Rate(item.event_time_ns, _value(item, policy.funding_value_name), _visibility(item), item.record_digest)
            for item in series
        ]
        readings += _funding_spike_readings(
            rates, interval_ns=policy.funding_interval_ns, start_ns=start, horizon_ns=horizon
        )
    budget = GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS.get(policy.latency_tier_id)
    persisted = start + _LATENCY_PERSISTENCE_NS + 1
    if budget is not None and policy.latency_ns > _LATENCY_MULTIPLE * budget and persisted < horizon:
        readings.append(_reading("T7", persisted, None, str(policy.latency_ns), (policy.policy_digest,)))
    ordered = tuple(
        sorted(
            readings,
            key=lambda item: (
                item.start_ns,
                _ORDER[item.trigger_id],
                horizon if item.end_ns is None else item.end_ns,
                item.reading_id,
            ),
        )
    )
    seed = GovernedPaperKillSwitchLadder(
        schema_version=_SCHEMA_VERSION,
        rule_id=GOVERNED_PAPER_KILL_SWITCH_RULE_ID,
        rule_digest=GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
        instrument=economics.instrument,
        economics_result_digest=economics.result_digest,
        economics_policy_digest=policy.policy_digest,
        dataset_digest=dataset.dataset_digest,
        decision_portfolio_digest=portfolio.portfolio_digest,
        governed_outcome_digest=outcome.outcome_digest,
        schedule_digest=outcome.schedule_digest,
        start_ns=start,
        horizon_ns=horizon,
        triggers=_states(
            simulated=simulated,
            interval_8h=interval_8h,
            tier_known=budget is not None,
            single_instrument_portfolio=single_instrument_portfolio,
        ),
        readings=ordered,
        transitions=governed_paper_kill_switch_transitions(ordered, start_ns=start, horizon_ns=horizon),
        ladder_digest="",
    )
    return replace(seed, ladder_digest=edge_payload_digest(_to_payload(seed), _DIGEST_FIELD))


# --- reading a ladder ------------------------------------------------------------------------------------------------------


def _ladder(ladder: object) -> GovernedPaperKillSwitchLadder:
    if type(ladder) is not GovernedPaperKillSwitchLadder:
        raise _fail("ladder_malformed")
    return ladder


def governed_paper_kill_switch_level_at(
    ladder: GovernedPaperKillSwitchLadder, time_ns: int
) -> tuple[int, GovernedPaperKillSwitchTransition | None]:
    """The proven lower bound of the level after every instant at or before ``time_ns``, and the transition that set it."""

    ladder = _ladder(ladder)
    if not historical_execution_wire_int_is_valid(time_ns, minimum=0):
        raise _fail("instant_malformed")
    level, setting = 0, None
    for item in ladder.transitions:
        if item.time_ns > time_ns:
            break
        level, setting = item.to_level, item
    return level, setting


def governed_paper_kill_switch_proven_at(ladder: GovernedPaperKillSwitchLadder, time_ns: int) -> tuple[str, ...]:
    """The triggers proven TRUE at ``time_ns``, in PRDV4 order."""

    ladder = _ladder(ladder)
    return _ordered(
        item.trigger_id
        for item in ladder.readings
        if item.start_ns <= time_ns and (item.end_ns is None or time_ns < item.end_ns)
    )


def governed_paper_kill_switch_unmeasured(ladder: GovernedPaperKillSwitchLadder) -> tuple[str, ...]:
    """The triggers this evaluation never reads TRUE, in PRDV4 order."""

    return tuple(
        item.trigger_id
        for item in _ladder(ladder).triggers
        if item.measurement is GovernedPaperKillSwitchMeasurement.UNMEASURED
    )


def governed_paper_kill_switch_unproven_at(ladder: GovernedPaperKillSwitchLadder, time_ns: int) -> tuple[str, ...]:
    """Every trigger neither proven TRUE at ``time_ns`` nor proven not applicable, in PRDV4 order."""

    proven = set(governed_paper_kill_switch_proven_at(ladder, time_ns))
    return tuple(
        item.trigger_id
        for item in ladder.triggers
        if item.trigger_id not in proven and item.measurement is not GovernedPaperKillSwitchMeasurement.NOT_APPLICABLE
    )


def governed_paper_kill_switch_prefix_digest(ladder: GovernedPaperKillSwitchLadder, *, before_ns: int) -> str:
    """The digest of the ladder strictly before ``before_ns``, projected onto its run-independent content.

    Each reading keeps its trigger, its start, its end clipped at ``before_ns`` and its observed value, and each earlier
    transition its instant, levels and proven triggers. Evidence digests and reading identities name the records of one
    engine re-run, whose digests derive from that run, and are left out. A causal replay over a later archive yields the
    same prefix, so consecutive day seals bind it (X1 for the ladder).
    """

    ladder = _ladder(ladder)
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("instant_malformed")
    readings = sorted(
        (
            {
                "trigger_id": item.trigger_id,
                "start_ns": item.start_ns,
                "end_ns": before_ns if item.end_ns is None or item.end_ns > before_ns else item.end_ns,
                "observed": item.observed,
            }
            for item in ladder.readings
            if item.start_ns < before_ns
        ),
        key=lambda item: (item["start_ns"], _ORDER[item["trigger_id"]], item["end_ns"], item["observed"]),  # type: ignore[index]
    )
    transitions = [
        {
            "time_ns": item.time_ns,
            "from_level": item.from_level,
            "to_level": item.to_level,
            "proven_trigger_ids": list(item.proven_trigger_ids),
        }
        for item in ladder.transitions
        if item.time_ns < before_ns
    ]
    return edge_sha256_text(
        edge_canonical_json(
            {
                "rule_digest": ladder.rule_digest,
                "start_ns": ladder.start_ns,
                "readings": readings,
                "transitions": transitions,
            }
        )
    )


def governed_paper_kill_switch_ladder_to_dict(ladder: GovernedPaperKillSwitchLadder) -> dict[str, object]:
    """Canonical JSON-ready mapping of the ladder, including its self-digest."""

    return _to_payload(_ladder(ladder))


def governed_paper_kill_switch_ladder_digest(ladder: GovernedPaperKillSwitchLadder) -> str:
    """Recompute the canonical ladder digest, excluding only ``ladder_digest``."""

    return edge_payload_digest(_to_payload(_ladder(ladder)), _DIGEST_FIELD)


__all__ = [
    "GOVERNED_PAPER_KILL_SWITCH_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_KILL_SWITCH_RULE",
    "GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST",
    "GOVERNED_PAPER_KILL_SWITCH_RULE_ID",
    "GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS",
    "GOVERNED_PAPER_KILL_SWITCH_TRIGGERS",
    "GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS",
    "GovernedPaperKillSwitchError",
    "GovernedPaperKillSwitchLadder",
    "GovernedPaperKillSwitchMeasurement",
    "GovernedPaperKillSwitchReading",
    "GovernedPaperKillSwitchTransition",
    "GovernedPaperKillSwitchTriggerState",
    "build_governed_paper_kill_switch_ladder",
    "governed_paper_kill_switch_ladder_digest",
    "governed_paper_kill_switch_ladder_to_dict",
    "governed_paper_kill_switch_level_at",
    "governed_paper_kill_switch_prefix_digest",
    "governed_paper_kill_switch_proven_at",
    "governed_paper_kill_switch_rule",
    "governed_paper_kill_switch_transitions",
    "governed_paper_kill_switch_unmeasured",
    "governed_paper_kill_switch_unproven_at",
]
