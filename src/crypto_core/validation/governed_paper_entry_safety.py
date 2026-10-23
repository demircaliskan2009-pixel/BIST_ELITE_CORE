"""Governed paper entry safety (S1_PAPER_ENTRY_SAFETY_CLOSURE_V1): the PRDV4 §1.21 NO-TRADE and §1.9 Family B gate.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.21 (explicit NO-TRADE conditions) and §1.9 (funding edge
safety), applied to the governed paper path of ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7.
Paper-only, deterministic, point-in-time and fail-closed. It creates no order and proves no venue fact.

Entry. A decision of the authenticated decision run whose resulting direction is LONG or SHORT can produce an intent
that increases the magnitude of the position; every such decision is evaluated here at its own decision instant ``t``.
A decision whose resulting direction is FLAT can only exit or hold, so it is never an entry. The day seal lists the
decision sequences this gate refuses in the engine's admission schedule, and the engine refuses their entries only: an
exit or a reduction of an open position is never refused by this gate.

Evaluation. The 26 NO-TRADE ids that PRDV4 §1.21 enumerates (its heading declares 23; every enumerated id is evaluated
and none is dropped), in the published order Data → Risk → Regime → Edge → Execution → Temporal, then the seven §1.9
Family B gates. Every check is exactly one of:

* ``PASS`` or ``FAIL``: the published rule evaluated on inputs derived here at ``t``, with the observed value and the
  threshold recorded;
* ``BLOCKED_ON_MISSING_INPUT``: a required measurement the selected path does not produce, never read as a pass;
* ``BLOCKED_PROTECTION_UNREPRESENTABLE``: a mandatory §1.9 position-management protection the selected path cannot
  represent, so no entry may rely on it;
* ``PROVEN_NOT_APPLICABLE``: the rule cannot apply on the selected path, for the exact reason recorded.

The first check, in that order, that is neither ``PASS`` nor ``PROVEN_NOT_APPLICABLE`` refuses the entry with its id,
reason, observed value, threshold, instrument and PIT instant. There is no override.

Derived inputs (none is supplied by a caller): the latest order-book update visible at ``t`` and the marks visible at
``t`` and at ``t − 4h`` under the economics engine's own rules (``historical_execution_visible_observations``), the
genesis instant G, the governed simulation latency and its tier, the RG-2 envelope's declared sleeves and markets, the
EF-8 invalidation instant and the registered profile of the run. The rules evaluated on them:

* NT-D02: the age ``t − event_time`` of the latest visible book update FAILs when strictly above 10 s;
* NT-E02: an EF-8 DISABLED or QUARANTINE successor effective at or before ``t`` FAILs. Otherwise the check is BLOCKED:
  the PRDV4 edge state machine (§1.6, §1.22) is driven by the edge health score, which is not produced, and an ACTIVE
  EF-8 receipt is not that state machine;
* NT-M04: PROVEN_NOT_APPLICABLE when the paper portfolio (the RG-2 envelope) declares exactly one sleeve, the genesis
  sleeve, whose admitted universe the genesis proves to be the one genesis instrument: a single instrument has no
  pairwise correlation. Market caps are budget bounds, never positions. Otherwise BLOCKED;
* NT-X01: the governed simulated latency ``latency_ns``, the only latency of the paper path, FAILs when strictly above
  five times the §1.16 tier budget (tier T1, Funding (B): 100 ms);
* NT-T01: FAILs while ``t`` lies in the first five minutes after the paper engine start G;
* FB-ANTITREND: ``r_4h = m(t) / m(t − 4h) − 1`` over the engine's visible marks; a SHORT entry FAILs when
  ``r_4h > +2%`` and a LONG entry when ``r_4h < −2%``. The §1.9 override needs the composite microstructure signal
  (§1.2) and the cascade state (§1.3); neither is produced, so an anti-trend block is never overridden.

Every other check is BLOCKED with the missing measurement or protection named. Family B applies to the registered
``passive_funding_carry.v1``: it enters SHORT on a positive and LONG on a negative trailing mean of final funding
rates, the §1.1 Family B funding mean-reversion entry. Any other profile leaves every Family B check BLOCKED.

The evidence is digest-bound and paper-only. It proves no venue fact, edge, profitability, readiness or Stage-4
completion. Exact arithmetic, no float, no ``decimal`` context, and no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperGenesisAuthority
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun
from crypto_core.validation.historical_execution_economics import historical_execution_visible_observations
from crypto_core.validation.historical_execution_economics_policy import (
    LATENCY_TIER_PRDV4_T1,
    historical_execution_decimal_is_canonical,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    get_strategy_executable_profile,
)

_SCHEMA_VERSION = "governed-paper-entry-safety-evidence.v1"
_PREFIX = "governed_paper_entry_safety"
_DIGEST_FIELD = "evidence_digest"
_NS_PER_SECOND = 1_000_000_000

# PRDV4 doctrine values: published thresholds, never governed parameters.
_BOOK_STALE_AFTER_NS = 10 * _NS_PER_SECOND  # NT-D02 (§1.21, §4.2)
_TIER_LATENCY_BUDGET_NS = {LATENCY_TIER_PRDV4_T1: 100_000_000}  # §1.16 T1 Critical, < 100 ms: Funding (B)
_LATENCY_BREACH_MULTIPLE = 5  # NT-X01
_STARTUP_WARMUP_NS = 5 * 60 * _NS_PER_SECOND  # NT-T01
_RETURN_LOOKBACK_NS = 4 * 3600 * _NS_PER_SECOND  # §1.9 r_4h
_ANTI_TREND_BOUND = Fraction(2, 100)  # §1.9 anti-trend protection, ±2%
_ENTRY_DIRECTIONS = ("LONG", "SHORT")

GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID = "governed-paper-entry-safety.v1"

GOVERNED_PAPER_ENTRY_SAFETY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("execution_authorized", False),
    ("venue_orders_created", False),
    ("real_market_source_qualified", False),
    ("venue_facts_proven", False),
    ("timestamp_origin_proven", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("stage4_complete", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


class GovernedPaperEntrySafetyError(EdgeArtifactError):
    """Malformed input or a binding defect: an entry-safety evaluation is never represented over it."""


class GovernedPaperEntrySafetyStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED_ON_MISSING_INPUT = "BLOCKED_ON_MISSING_INPUT"
    BLOCKED_PROTECTION_UNREPRESENTABLE = "BLOCKED_PROTECTION_UNREPRESENTABLE"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"


class GovernedPaperEntrySafetyFamily(str, Enum):
    """The PRDV4 §1.21 evaluation families in their published order, then the §1.9 Family B gates."""

    DATA = "DATA"
    RISK = "RISK"
    REGIME = "REGIME"
    EDGE = "EDGE"
    EXECUTION = "EXECUTION"
    TEMPORAL = "TEMPORAL"
    FAMILY_B = "FAMILY_B"


_ADMITTING = (GovernedPaperEntrySafetyStatus.PASS, GovernedPaperEntrySafetyStatus.PROVEN_NOT_APPLICABLE)


@dataclass(frozen=True)
class GovernedPaperEntrySafetyObservation:
    """The point-in-time facts one decision is evaluated on (derived by this module, never caller authority)."""

    decision_sequence: int
    decision_time_ns: int
    decision_digest: str
    instrument: str
    target_direction: str
    family_b_applicable: bool
    genesis_start_ns: int
    latency_tier_id: str
    latency_ns: int
    single_instrument_portfolio: bool
    lifecycle_invalidated: bool
    book_update_record_digest: str | None
    book_update_event_time_ns: int | None
    mark_record_digest: str | None
    mark_price: str | None
    lookback_mark_record_digest: str | None
    lookback_mark_price: str | None


@dataclass(frozen=True)
class GovernedPaperEntrySafetyCheck:
    """One evaluated check: its status, the observed value (empty when unavailable), the published threshold."""

    check_id: str
    family: GovernedPaperEntrySafetyFamily
    status: GovernedPaperEntrySafetyStatus
    observed: str
    threshold: str
    reason: str
    evidence_record_digests: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperEntrySafetyDecision:
    """Every check of one entry decision, in evaluation order, and the first one that refuses the entry."""

    decision_sequence: int
    decision_time_ns: int
    decision_digest: str
    instrument: str
    target_direction: str
    checks: tuple[GovernedPaperEntrySafetyCheck, ...]
    entry_permitted: bool
    first_failure_check_id: str
    first_failure_reason: str


@dataclass(frozen=True)
class GovernedPaperEntrySafetyEvidence:
    """The entry-safety evaluation of every entry decision of one decision run; ``evidence_digest`` covers the rest."""

    schema_version: str
    rule_set_id: str
    rule_set_digest: str
    genesis_id: str
    genesis_digest: str
    run_digest: str
    dataset_digest: str
    economics_policy_digest: str
    instrument: str
    profile_id: str
    family_b_applicable: bool
    invalidated_from_ns: int | None
    decisions: tuple[GovernedPaperEntrySafetyDecision, ...]
    refused_decision_sequences: tuple[int, ...]
    evidence_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    venue_orders_created: bool = False
    real_market_source_qualified: bool = False
    venue_facts_proven: bool = False
    timestamp_origin_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    stage4_complete: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperEntrySafetyError:
    return GovernedPaperEntrySafetyError(_reason(code))


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


# --- the checks --------------------------------------------------------------------------------------------------------

_Status = GovernedPaperEntrySafetyStatus
_Family = GovernedPaperEntrySafetyFamily
_Observation = GovernedPaperEntrySafetyObservation


@dataclass(frozen=True)
class _Outcome:
    status: GovernedPaperEntrySafetyStatus
    observed: str
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Check:
    check_id: str
    family: GovernedPaperEntrySafetyFamily
    clause: str
    threshold: str
    evaluate: Callable[[GovernedPaperEntrySafetyObservation], _Outcome]


def _missing(reason: str) -> Callable[[_Observation], _Outcome]:
    def evaluate(observation: _Observation) -> _Outcome:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason)

    return evaluate


def _unrepresentable(reason: str) -> Callable[[_Observation], _Outcome]:
    def evaluate(observation: _Observation) -> _Outcome:
        return _Outcome(_Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", reason)

    return evaluate


def _family_b(evaluate: Callable[[_Observation], _Outcome]) -> Callable[[_Observation], _Outcome]:
    def gated(observation: _Observation) -> _Outcome:
        if not observation.family_b_applicable:
            return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "family_b_applicability_undetermined")
        return evaluate(observation)

    return gated


def _book_staleness(observation: _Observation) -> _Outcome:
    if observation.book_update_event_time_ns is None or observation.book_update_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "no_order_book_update_visible_at_the_decision_instant")
    evidence = (observation.book_update_record_digest,)
    age = observation.decision_time_ns - observation.book_update_event_time_ns
    if age < 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, str(age), "order_book_update_after_the_decision", evidence)
    if age > _BOOK_STALE_AFTER_NS:
        return _Outcome(_Status.FAIL, str(age), "last_l2_update_older_than_10s", evidence)
    return _Outcome(_Status.PASS, str(age), "last_l2_update_within_10s", evidence)


def _edge_state(observation: _Observation) -> _Outcome:
    if observation.lifecycle_invalidated:
        return _Outcome(_Status.FAIL, "EF8_DISABLED_OR_QUARANTINE", "edge_lifecycle_disabled_at_or_before_the_decision")
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "prdv4_edge_state_machine_not_produced")


def _correlation(observation: _Observation) -> _Outcome:
    if observation.single_instrument_portfolio:
        return _Outcome(
            _Status.PROVEN_NOT_APPLICABLE, "", "single_instrument_paper_portfolio_has_no_pairwise_correlation"
        )
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "cross_asset_correlation_not_measured")


def _latency(observation: _Observation) -> _Outcome:
    budget = _TIER_LATENCY_BUDGET_NS.get(observation.latency_tier_id)
    if budget is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "latency_tier_budget_unknown")
    observed = str(observation.latency_ns)
    if observation.latency_ns > _LATENCY_BREACH_MULTIPLE * budget:
        return _Outcome(_Status.FAIL, observed, "simulated_latency_above_five_times_the_tier_budget")
    return _Outcome(_Status.PASS, observed, "simulated_latency_within_five_times_the_tier_budget")


def _startup(observation: _Observation) -> _Outcome:
    elapsed = observation.decision_time_ns - observation.genesis_start_ns
    if elapsed < 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, str(elapsed), "decision_before_the_paper_engine_start")
    if elapsed < _STARTUP_WARMUP_NS:
        return _Outcome(_Status.FAIL, str(elapsed), "inside_the_first_5_minutes_after_the_paper_engine_start")
    return _Outcome(_Status.PASS, str(elapsed), "after_the_startup_warmup")


def _anti_trend(observation: _Observation) -> _Outcome:
    if observation.mark_price is None or observation.mark_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "mark_unavailable_at_the_decision_instant")
    if observation.lookback_mark_price is None or observation.lookback_mark_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "mark_unavailable_4h_before_the_decision_instant")
    evidence = (observation.lookback_mark_record_digest, observation.mark_record_digest)
    move = Fraction(observation.mark_price) / Fraction(observation.lookback_mark_price) - 1
    observed = historical_execution_render_amount(move)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "r_4h_unrepresentable", evidence)
    if observation.target_direction == "SHORT":
        triggered = move > _ANTI_TREND_BOUND
    else:
        triggered = move < -_ANTI_TREND_BOUND
    if triggered:
        return _Outcome(_Status.FAIL, observed, "anti_trend_entry_blocked_and_override_unprovable", evidence)
    return _Outcome(_Status.PASS, observed, "anti_trend_bound_not_crossed", evidence)


_D, _R, _M, _E, _X, _T, _B = (
    _Family.DATA,
    _Family.RISK,
    _Family.REGIME,
    _Family.EDGE,
    _Family.EXECUTION,
    _Family.TEMPORAL,
    _Family.FAMILY_B,
)
_CHECKS: tuple[_Check, ...] = (
    _Check(
        "NT-D01",
        _D,
        "PRDV4 §1.21 NT-D01 OHLCV feed gap",
        "trade_stream_gap_gt_60s_or_kline_gap_gt_5min",
        _missing("trade_and_kline_feeds_not_in_the_selected_data_contract"),
    ),
    _Check("NT-D02", _D, "PRDV4 §1.21 NT-D02 order book stale", "last_l2_update_age_gt_10s", _book_staleness),
    _Check(
        "NT-D03",
        _D,
        "PRDV4 §1.21 NT-D03 trade/book timestamp divergence",
        "abs_trade_book_timestamp_divergence_gt_5s",
        _missing("trade_stream_not_in_the_selected_data_contract"),
    ),
    _Check(
        "NT-D04",
        _D,
        "PRDV4 §1.21 NT-D04 price vs index deviation",
        "abs_price_minus_index_over_index_gt_2pct",
        _missing("index_price_series_not_in_the_selected_data_contract"),
    ),
    _Check(
        "NT-D05",
        _D,
        "PRDV4 §1.21 NT-D05 volume anomaly",
        "volume_5min_lt_5pct_of_the_30d_mean_5min_volume",
        _missing("volume_series_not_in_the_selected_data_contract"),
    ),
    _Check(
        "NT-R01",
        _R,
        "PRDV4 §1.21 NT-R01 kill-switch active (§1.19)",
        "kill_switch_level_ge_2",
        _missing("kill_switch_ladder_level_not_produced"),
    ),
    _Check(
        "NT-R02",
        _R,
        "PRDV4 §1.21 NT-R02 daily loss limit",
        "intraday_pnl_over_nav_lt_minus_2pct",
        _missing("intraday_portfolio_pnl_and_nav_not_measured_at_the_decision_instant"),
    ),
    _Check(
        "NT-R03",
        _R,
        "PRDV4 §1.21 NT-R03 open risk cap",
        "sum_position_risk_over_equity_gt_4pct",
        _missing("portfolio_position_risk_not_measured_at_the_decision_instant"),
    ),
    _Check(
        "NT-R04",
        _R,
        "PRDV4 §1.21 NT-R04 position concentration",
        "any_position_gt_25pct_of_nav",
        _missing("portfolio_position_concentration_not_measured_at_the_decision_instant"),
    ),
    _Check(
        "NT-R05",
        _R,
        "PRDV4 §1.21 NT-R05 CVaR budget exhausted (§1.18)",
        "portfolio_cvar99_ge_5pct_of_nav",
        _missing("portfolio_cvar99_not_produced"),
    ),
    _Check(
        "NT-R06",
        _R,
        "PRDV4 §1.21 NT-R06 margin utilization",
        "used_margin_gt_80pct_of_available",
        _missing("margin_utilization_not_modeled"),
    ),
    _Check(
        "NT-M01",
        _M,
        "PRDV4 §1.21 NT-M01 liquidity regime CRISIS (§1.17)",
        "liq_lt_0.15_sustained_gt_30min",
        _missing("liquidity_regime_not_produced"),
    ),
    _Check(
        "NT-M02",
        _M,
        "PRDV4 §1.21 NT-M02 leverage regime EXTREME (§1.17)",
        "open_interest_over_market_cap_gt_0.10",
        _missing("open_interest_and_market_cap_not_in_the_selected_data_contract"),
    ),
    _Check(
        "NT-M03",
        _M,
        "PRDV4 §1.21 NT-M03 regime transition in progress",
        "any_regime_dimension_in_its_hysteresis_window",
        _missing("regime_hysteresis_state_not_produced"),
    ),
    _Check(
        "NT-M04",
        _M,
        "PRDV4 §1.21 NT-M04 correlation breakdown",
        "mean_pairwise_correlation_gt_0.85",
        _correlation,
    ),
    _Check(
        "NT-E01",
        _E,
        "PRDV4 §1.21 NT-E01 edge health score (§1.6)",
        "edge_health_score_lt_0.30",
        _missing("edge_health_score_not_produced"),
    ),
    _Check("NT-E02", _E, "PRDV4 §1.21 NT-E02 edge in DISABLED state", "edge_state_machine_disabled", _edge_state),
    _Check(
        "NT-E03",
        _E,
        "PRDV4 §1.21 NT-E03 edge capacity RED (§1.15)",
        "utilization_ge_80pct_of_kmax",
        _missing("edge_capacity_kmax_and_utilization_not_produced"),
    ),
    _Check(
        "NT-E04",
        _E,
        "PRDV4 §1.21 NT-E04 no valid edge for asset",
        "zero_edges_with_edge_health_score_gt_0.50",
        _missing("edge_health_score_not_produced"),
    ),
    _Check(
        "NT-X01",
        _X,
        "PRDV4 §1.21 NT-X01 latency breach (§1.16)",
        "latency_gt_5x_the_tier_budget_t1_100ms",
        _latency,
    ),
    _Check(
        "NT-X02",
        _X,
        "PRDV4 §1.21 NT-X02 fill rate degradation",
        "last_10_orders_fill_rate_lt_50pct",
        _missing("exchange_order_fill_rate_not_observable_on_the_paper_path"),
    ),
    _Check(
        "NT-X03",
        _X,
        "PRDV4 §1.21 NT-X03 spread anomaly",
        "spread_gt_3x_the_30d_median",
        _missing("thirty_day_median_spread_needs_proven_complete_book_coverage"),
    ),
    _Check(
        "NT-X04",
        _X,
        "PRDV4 §1.21 NT-X04 exchange maintenance",
        "scheduled_or_detected_maintenance_window",
        _missing("exchange_maintenance_schedule_not_produced"),
    ),
    _Check("NT-T01", _T, "PRDV4 §1.21 NT-T01 system startup", "first_5min_after_the_engine_start", _startup),
    _Check(
        "NT-T02",
        _T,
        "PRDV4 §1.21 NT-T02 post-kill-switch cool-down (§1.19)",
        "inside_the_kill_switch_cooldown",
        _missing("kill_switch_cooldown_state_not_produced"),
    ),
    _Check(
        "NT-T03",
        _T,
        "PRDV4 §1.21 NT-T03 high-impact event window",
        "within_15min_of_a_known_macro_event",
        _missing("macro_event_calendar_not_produced"),
    ),
    _Check(
        "FB-TREND",
        _B,
        "PRDV4 §1.9 trend filter",
        "funding_extreme_and_trend_strength_aligned_ts_gt_1.5",
        _family_b(_missing("trend_strength_ema_atr_construction_not_defined_or_produced")),
    ),
    _Check(
        "FB-REGIME",
        _B,
        "PRDV4 §1.9 regime filter",
        "regime_not_range_or_high_vol_or_crisis",
        _family_b(_missing("regime_state_not_produced")),
    ),
    _Check(
        "FB-REGIME-COOLDOWN",
        _B,
        "PRDV4 §1.9 regime filter transition cooldown",
        "trending_within_the_last_4h_suppresses_4h",
        _family_b(_missing("trending_regime_history_not_produced")),
    ),
    _Check(
        "FB-ANTITREND",
        _B,
        "PRDV4 §1.9 anti-trend protection",
        "short_with_r4h_gt_plus_2pct_or_long_with_r4h_lt_minus_2pct",
        _family_b(_anti_trend),
    ),
    _Check(
        "FB-MAX-HOLD",
        _B,
        "PRDV4 §1.9 position management maximum holding period",
        "maximum_holding_period_24h",
        _family_b(_unrepresentable("holding_period_exit_not_representable_on_the_selected_path")),
    ),
    _Check(
        "FB-STOP",
        _B,
        "PRDV4 §1.9 position management mandatory stop",
        "stop_at_1.5x_atr4h_from_entry",
        _family_b(_unrepresentable("atr_4h_stop_exit_not_representable_on_the_selected_path")),
    ),
    _Check(
        "FB-STOP-TIGHTENING",
        _B,
        "PRDV4 §1.9 position management time-decay stop",
        "stop_tightened_by_20pct_every_8h",
        _family_b(_unrepresentable("stop_tightening_not_representable_on_the_selected_path")),
    ),
)


def governed_paper_entry_safety_rule_set() -> dict[str, object]:
    """The rule set this module evaluates: every check, in order, with its PRDV4 clause and published threshold."""

    return {
        "rule_set_id": GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
        "contract_id": "S1_PAPER_ENTRY_SAFETY_CLOSURE_V1",
        "authorities": ["PRDV4 §1.21", "PRDV4 §1.9", "PRDV4 §1.16", "PRDV4 §1.1 Family B"],
        "entry_rule": "decisions_with_a_LONG_or_SHORT_resulting_direction_are_evaluated_and_only_a_magnitude_increasing_intent_is_refused",
        "first_failure_rule": "the_first_check_in_order_that_is_neither_PASS_nor_PROVEN_NOT_APPLICABLE_refuses_the_entry",
        "override_rule": "none",
        "prdv4_no_trade_count": "heading_declares_23_tables_enumerate_26_ids_every_enumerated_id_is_evaluated",
        "family_b_profiles": [PASSIVE_FUNDING_CARRY_V1],
        "visible_observation_rule": "historical_execution_visible_observations",
        "checks": [
            {"check_id": item.check_id, "family": item.family.value, "clause": item.clause, "threshold": item.threshold}
            for item in _CHECKS
        ],
    }


def governed_paper_entry_safety_rule_set_digest() -> str:
    return edge_sha256_text(edge_canonical_json(governed_paper_entry_safety_rule_set()))


GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET = governed_paper_entry_safety_rule_set()
GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest()


# --- one decision ------------------------------------------------------------------------------------------------------


def _optional_text(value: object, name: str) -> None:
    if value is not None and (type(value) is not str or value == ""):
        raise _fail(f"observation_malformed:{name}")


def _canonical_observation(observation: object) -> GovernedPaperEntrySafetyObservation:
    if type(observation) is not GovernedPaperEntrySafetyObservation:
        raise _fail("observation_malformed")
    for name in ("decision_sequence", "decision_time_ns", "genesis_start_ns", "latency_ns"):
        if not historical_execution_wire_int_is_valid(getattr(observation, name), minimum=0):
            raise _fail(f"observation_malformed:{name}")
    if not edge_is_hex64(observation.decision_digest):
        raise _fail("observation_malformed:decision_digest")
    for name in ("instrument", "latency_tier_id"):
        value = getattr(observation, name)
        if type(value) is not str or value == "":
            raise _fail(f"observation_malformed:{name}")
    if type(observation.target_direction) is not str or observation.target_direction not in _ENTRY_DIRECTIONS:
        raise _fail("observation_malformed:target_direction")
    for name in ("family_b_applicable", "single_instrument_portfolio", "lifecycle_invalidated"):
        if type(getattr(observation, name)) is not bool:
            raise _fail(f"observation_malformed:{name}")
    event = observation.book_update_event_time_ns
    if event is not None and not historical_execution_wire_int_is_valid(event, minimum=0):
        raise _fail("observation_malformed:book_update_event_time_ns")
    for name in ("book_update_record_digest", "mark_record_digest", "lookback_mark_record_digest"):
        value = getattr(observation, name)
        if value is not None and not edge_is_hex64(value):
            raise _fail(f"observation_malformed:{name}")
    for name in ("mark_price", "lookback_mark_price"):
        value = getattr(observation, name)
        _optional_text(value, name)
        if value is not None and (not historical_execution_decimal_is_canonical(value) or Fraction(value) <= 0):
            raise _fail(f"observation_malformed:{name}")
    return observation


def evaluate_governed_paper_entry_safety(
    observation: GovernedPaperEntrySafetyObservation,
) -> GovernedPaperEntrySafetyDecision:
    """Evaluate every check of one entry decision in order (pure); the first non-admitting check refuses the entry."""

    observation = _canonical_observation(observation)
    checks: list[GovernedPaperEntrySafetyCheck] = []
    first: GovernedPaperEntrySafetyCheck | None = None
    for item in _CHECKS:
        outcome = item.evaluate(observation)
        check = GovernedPaperEntrySafetyCheck(
            check_id=item.check_id,
            family=item.family,
            status=outcome.status,
            observed=outcome.observed,
            threshold=item.threshold,
            reason=_reason(f"{item.check_id}:{outcome.reason}"),
            evidence_record_digests=outcome.evidence,
        )
        checks.append(check)
        if first is None and outcome.status not in _ADMITTING:
            first = check
    return GovernedPaperEntrySafetyDecision(
        decision_sequence=observation.decision_sequence,
        decision_time_ns=observation.decision_time_ns,
        decision_digest=observation.decision_digest,
        instrument=observation.instrument,
        target_direction=observation.target_direction,
        checks=tuple(checks),
        entry_permitted=first is None,
        first_failure_check_id="" if first is None else first.check_id,
        first_failure_reason="" if first is None else first.reason,
    )


# --- the evidence of one decision run ----------------------------------------------------------------------------------


def _single_instrument_portfolio(authority: GovernedPaperGenesisAuthority) -> bool:
    """The paper portfolio is exactly the genesis sleeve (its universe is the one genesis instrument)."""

    genesis, envelope = authority.genesis, authority.portfolio_risk_envelope
    return len(envelope.sleeve_caps) == 1 and envelope.sleeve_caps[0].sleeve_id == genesis.sleeve_id


def build_governed_paper_entry_safety_evidence(
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    invalidated_from_ns: int | None,
) -> GovernedPaperEntrySafetyEvidence:
    """Evaluate every entry decision of ``run`` over the archive ``dataset`` it was built from (see the module docstring).

    The run must be the genesis's own READY + PASS run over this archive and the archive the genesis's; the visible
    observations re-verify the archive and the economics policy. A malformed or foreign input raises
    ``GovernedPaperEntrySafetyError``. Pure.
    """

    if type(authority) is not GovernedPaperGenesisAuthority:
        raise _fail("genesis_authority_malformed")
    if type(run) is not HistoricalDecisionRun or type(dataset) is not HistoricalPitDataset:
        raise _fail("decision_run_or_archive_malformed")
    if invalidated_from_ns is not None and not historical_execution_wire_int_is_valid(invalidated_from_ns, minimum=0):
        raise _fail("invalidated_from_ns_invalid")
    genesis = authority.genesis
    if run.status is not EdgeEvidenceStatus.READY or run.gate_verdict is not EdgeGateVerdict.PASS:
        raise _fail("decision_run_not_ready")
    if (
        run.dataset_digest != dataset.dataset_digest
        or run.executable_binding_digest != genesis.executable_binding_digest
        or run.instrument != genesis.instrument
        or run.evaluation_start_ns != genesis.genesis_start_ns
        or dataset.source_manifest_digest != genesis.source_manifest_digest
        or dataset.data_requirement_registry_digest != genesis.data_requirement_registry_digest
    ):
        raise _fail("decision_run_or_archive_not_of_the_genesis")
    policy = authority.economics_policy
    observations = historical_execution_visible_observations(dataset, policy=policy, instrument=genesis.instrument)
    registered = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    family_b = (
        run.profile_id == registered.profile_id and run.profile_semantics_digest == registered.profile_semantics_digest
    )
    single = _single_instrument_portfolio(authority)
    decisions: list[GovernedPaperEntrySafetyDecision] = []
    for decision in run.decisions:
        if decision.resulting_direction not in _ENTRY_DIRECTIONS:
            continue
        instant = decision.decision_time_ns
        book = observations.latest_book_update(instant)
        mark = observations.latest_mark(instant)
        lookback = observations.latest_mark(instant - _RETURN_LOOKBACK_NS) if instant >= _RETURN_LOOKBACK_NS else None
        observation = GovernedPaperEntrySafetyObservation(
            decision_sequence=decision.decision_sequence,
            decision_time_ns=instant,
            decision_digest=decision.decision_digest,
            instrument=genesis.instrument,
            target_direction=decision.resulting_direction,
            family_b_applicable=family_b,
            genesis_start_ns=genesis.genesis_start_ns,
            latency_tier_id=policy.latency_tier_id,
            latency_ns=policy.latency_ns,
            single_instrument_portfolio=single,
            lifecycle_invalidated=invalidated_from_ns is not None and invalidated_from_ns <= instant,
            book_update_record_digest=None if book is None else book[0],
            book_update_event_time_ns=None if book is None else book[1],
            mark_record_digest=None if mark is None else mark[0],
            mark_price=None if mark is None else mark[1],
            lookback_mark_record_digest=None if lookback is None else lookback[0],
            lookback_mark_price=None if lookback is None else lookback[1],
        )
        decisions.append(evaluate_governed_paper_entry_safety(observation))
    seed = GovernedPaperEntrySafetyEvidence(
        schema_version=_SCHEMA_VERSION,
        rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
        rule_set_digest=governed_paper_entry_safety_rule_set_digest(),
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        run_digest=run.run_digest,
        dataset_digest=dataset.dataset_digest,
        economics_policy_digest=genesis.economics_policy_digest,
        instrument=genesis.instrument,
        profile_id=run.profile_id,
        family_b_applicable=family_b,
        invalidated_from_ns=invalidated_from_ns,
        decisions=tuple(decisions),
        refused_decision_sequences=tuple(
            sorted(item.decision_sequence for item in decisions if not item.entry_permitted)
        ),
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), _DIGEST_FIELD))


def governed_paper_entry_safety_evidence_to_dict(evidence: GovernedPaperEntrySafetyEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_entry_safety_evidence_digest(evidence: GovernedPaperEntrySafetyEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _DIGEST_FIELD)
