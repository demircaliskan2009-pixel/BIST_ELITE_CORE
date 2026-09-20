"""Deterministic historical execution economics (DETERMINISTIC_HISTORICAL_EXECUTION_ECONOMICS_V1).

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

Outcomes. Integrity failure → ``REJECTED``/``NOT_EVALUATED``. A non-advancing run or policy propagates its verdict.
Missing external facts → ``NEEDS_EXTERNAL_FACTS``; missing/mismatched approval → ``NEEDS_GOVERNANCE_APPROVAL``; an
economic incompatibility or data insufficiency → ``FAIL``. Only ``READY`` + ``PASS`` carries economics; every other
outcome carries empty ledgers and no terminal state (nothing is fabricated).

Execution semantics (v1, linear USDT perpetual, base-asset quantity):

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
* price: mid × (1 ± max(slippage_floor_bps, half_spread_bps + coefficient × participation_pct) / 10 000);
* risk: an exposure-increasing fill is ``REJECTED`` (``risk_limit_exceeded``, never clipped) when its candidate
  post-fill equity — the exact equity the accepted FILL valuation would record, including this fill's own fee and its
  mark-to-market at the fill mark — is not positive, or when post-fill |q| × mark exceeds spec ``max_leverage`` ×
  that candidate equity; one shared transition preview serves the decision and the applied transition;
* fee: every fill is taker; fee = fill_price × filled × taker_fee_bps / 10 000, always a cost;
* funding: each final settlement at most once; liability time = event_time + funding_interval_ns; the liable position
  is the one before any fill at the same nanosecond; cashflow = −q × mark(liability) × rate (positive rate: LONG pays,
  SHORT receives); the funding grid must be consistent with the approved interval and cover every liable instant; a
  record whose ``finalized_at_ns`` precedes its own liability instant is ``FAIL``
  (``funding_finalized_before_cycle_close``), because under the authenticated ``funding_cycle_closed`` finality a
  final rate cannot exist before its own cycle closed; settlement itself stays at the governed liability instant even
  when the archive finalizes or publishes the record later (ex-post settlement accounting);
* valuation: latest visible mark (by event time) not older than ``max_mark_staleness_ns``; observations at the initial
  anchor, every fill, every settlement, every UTC day boundary (integer nanoseconds) and evaluation end;
  equity = initial_equity + realized gross − fees + funding + unrealized;
* terminal: no forced close; an open excursion is an OPEN trade with its unrealized MTM.

Canonical event order: time, then class (FUNDING_SETTLEMENT < DECISION < FILL < UTC_DAY_BOUNDARY < EVALUATION_END), then
sequence. Numeric values follow the committed v1 numeric policy (exact ``Fraction``; one ROUND_HALF_EVEN render per
monetary value; quantities truncated toward zero; <= 60 characters; int64 wire integers); an unrepresentable derived
value is ``FAIL`` (``economic_value_out_of_representation:<field>``). There is no ``decimal`` context and no float.

The result proves deterministic simulated historical economics under the approved policy only: not venue fill truth,
not edge, profitability, performance metrics or readiness. One assembly path serves the builder and verifier
reassembly; ``verify_historical_execution_economics`` re-proves every authority and re-derives every ledger. Total.
"""

from __future__ import annotations

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
    historical_execution_render_amount,
    historical_execution_render_quantity,
    historical_execution_wire_int_is_valid,
    verify_historical_execution_economics_policy,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    historical_pit_dataset_from_payload,
)
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableParameterApproval,
    strategy_executable_binding_from_payload,
)

_SCHEMA_VERSION = "historical-execution-economics.v1"
_REASON_PREFIX = "historical_execution_economics"
_SELF_DIGEST_FIELD = "result_digest"
_UTC_DAY_NS = 86_400_000_000_000
_BPS = Fraction(10_000)
_HUNDRED = Fraction(100)

_PRIORITY_FUNDING = 0
_PRIORITY_DECISION = 1
_PRIORITY_FILL = 2
_PRIORITY_DAY_BOUNDARY = 3
_PRIORITY_END = 4

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
    """Signed position change produced by one executed fill; realized gross PnL on the closed part."""

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
    """Mark-to-market equity observation at one canonical instant."""

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


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _sealed(record: object, digest_field: str) -> object:
    return replace(record, **{digest_field: edge_payload_digest(_to_payload(record), digest_field)})  # type: ignore[type-var]


def _ledger_digest(records: Sequence[object]) -> str:
    return edge_sha256_text(edge_canonical_json([_to_payload(record) for record in records]))


def _derived_id(kind: str, *parts: object) -> str:
    return edge_sha256_text(edge_canonical_json([kind, *parts]))


def _amount(value: Fraction, field_name: str) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return rendered


def _quantity(value: Fraction, field_name: str) -> str:
    rendered = historical_execution_render_quantity(value)
    if rendered is None:
        raise _EconomicFailure(f"economic_value_out_of_representation:{field_name}")
    return rendered


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


def _max_leverage(spec: StrategySpec) -> Fraction | None:
    """Exact value of the digest-bound spec leverage cap (a float is read through its canonical JSON text)."""

    value = spec.risk_caps.get("max_leverage") if isinstance(spec.risk_caps, Mapping) else None
    if type(value) is int and value > 0:
        return Fraction(value)
    if type(value) is float:
        exact = Fraction(repr(value))
        return exact if exact > 0 else None
    return None


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


@dataclass(frozen=True)
class _Transition:
    """Candidate position change of one priced fill; the leverage decision and the applied transition share it."""

    kind: HistoricalExecutionTransitionKind
    prior_quantity: Fraction
    prior_average: Fraction | None
    signed: Fraction
    post_quantity: Fraction
    post_average: Fraction | None
    closed_quantity: Fraction
    realized_gross: Fraction


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
    ) -> None:
        self.run = run
        self.run_digest = run_digest
        self.policy = policy
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
        funding = sorted(
            (r for r in dataset.records if r.series_id == run.funding_series_id and r.instrument == instrument),
            key=lambda record: record.sequence_id,
        )
        self.funding = funding
        marks = [
            _Mark(visible, record, _value(record, policy.mark_value_name))
            for record in dataset.records
            if record.series_id == mark_series and record.instrument == instrument
            for visible in (_visibility(record),)
            if visible is not None
        ]
        marks.sort(key=lambda mark: (mark.visibility, mark.record.event_time_ns, mark.record.sequence_id))
        self.marks = _MarkCursor(marks, policy.max_mark_staleness_ns)
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
        self.books = books
        self.quantity = Fraction(0)
        self.average: Fraction | None = None
        self.realized = Fraction(0)
        self.fees = Fraction(0)
        self.funding_total = Fraction(0)
        self.trade: _Trade | None = None
        self.segments: list[tuple[int, Fraction]] = []
        self.settled: set[tuple[str, str, int]] = set()
        self.ledgers = _Ledgers()

    # -- rendering helpers --

    def _unrealized_of(self, quantity: Fraction, average: Fraction | None, mark: _Mark | None) -> Fraction:
        if quantity == 0 or mark is None or average is None:
            return Fraction(0)
        return Fraction(_amount(quantity * (mark.price - average), "unrealized_pnl"))

    def _unrealized(self, mark: _Mark | None) -> Fraction:
        return self._unrealized_of(self.quantity, self.average, mark)

    def _equity(
        self, unrealized: Fraction, *, realized: Fraction | None = None, fees: Fraction | None = None
    ) -> Fraction:
        """The one equity identity; a candidate state passes its own realized/fees totals."""

        realized = self.realized if realized is None else realized
        fees = self.fees if fees is None else fees
        return self.initial_equity + realized - fees + self.funding_total + unrealized

    # -- events --

    def _valuation(self, kind: HistoricalExecutionValuationKind, time_ns: int, trigger: str | None) -> None:
        mark = self.marks.at(time_ns, kind.value.lower()) if self.quantity != 0 else None
        unrealized = self._unrealized(mark)
        record = HistoricalExecutionValuation(
            valuation_sequence=len(self.ledgers.valuations),
            valuation_kind=kind,
            time_ns=time_ns,
            trigger_digest=trigger,
            position_quantity=_amount(self.quantity, "position_quantity"),
            average_entry_price=None if self.average is None else _amount(self.average, "average_entry_price"),
            mark_record_digest=None if mark is None else mark.record.record_digest,
            mark_price=None if mark is None else _amount(mark.price, "mark_price"),
            unrealized_pnl=_amount(unrealized, "unrealized_pnl"),
            cumulative_realized_gross_pnl=_amount(self.realized, "cumulative_realized_gross_pnl"),
            cumulative_fees=_amount(self.fees, "cumulative_fees"),
            cumulative_funding=_amount(self.funding_total, "cumulative_funding"),
            equity=_amount(self._equity(unrealized), "equity"),
            valuation_digest="",
        )
        self.ledgers.valuations.append(_sealed(record, "valuation_digest"))  # type: ignore[arg-type]

    def _settle(self, record: HistoricalPitRecord, liability_ns: int) -> None:
        key = (record.series_id, record.instrument, record.sequence_id)
        if key in self.settled:
            raise _EconomicFailure("funding_settlement_duplicate")
        self.settled.add(key)
        if self.quantity == 0:
            return
        if record.finalized_at_ns is None:
            raise _EconomicFailure("funding_coverage_incomplete")
        mark = self.marks.at(liability_ns, "funding_settlement")
        rate = _value(record, self.policy.funding_value_name)
        notional = Fraction(_amount(abs(self.quantity) * mark.price, "funding_notional"))
        amount = Fraction(_amount(-self.quantity * mark.price * rate, "funding_cashflow_amount"))
        cashflow = HistoricalExecutionFundingCashflow(
            cashflow_id=_derived_id("funding", self.run_digest, record.record_digest),
            funding_record_digest=record.record_digest,
            funding_series_id=record.series_id,
            funding_sequence_id=record.sequence_id,
            funding_event_time_ns=record.event_time_ns,
            liability_time_ns=liability_ns,
            funding_rate=_amount(rate, "funding_rate"),
            position_quantity=_amount(self.quantity, "position_quantity"),
            mark_record_digest=mark.record.record_digest,
            mark_price=_amount(mark.price, "mark_price"),
            funding_notional=_amount(notional, "funding_notional"),
            cashflow_amount=_amount(amount, "funding_cashflow_amount"),
            cashflow_digest="",
        )
        sealed: HistoricalExecutionFundingCashflow = _sealed(cashflow, "cashflow_digest")  # type: ignore[assignment]
        self.ledgers.funding.append(sealed)
        self.funding_total += amount
        _amount(self.funding_total, "cumulative_funding")
        if self.trade is not None:
            self.trade.funding.append(sealed.cashflow_digest)
            self.trade.total_funding += amount
        self._valuation(HistoricalExecutionValuationKind.FUNDING_SETTLEMENT, liability_ns, sealed.cashflow_digest)

    def _intent(self, decision: HistoricalDecisionRecord) -> HistoricalExecutionIntent | None:
        direction = {"LONG": 1, "SHORT": -1, "FLAT": 0}.get(decision.resulting_direction)
        if direction is None:
            raise _EconomicFailure("decision_direction_unsupported")
        target = self.unit_size * direction
        actual = self.quantity
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
        return sealed

    def _select_book(self, intent: HistoricalExecutionIntent, boundary_ns: int) -> tuple[_Book | None, str]:
        earliest = intent.earliest_execution_time_ns
        low, high = 0, len(self.books)
        while low < high:
            middle = (low + high) // 2
            if self.books[middle].visibility < earliest:
                low = middle + 1
            else:
                high = middle
        for book in self.books[low:]:
            if book.record.event_time_ns <= intent.decision_time_ns:
                continue
            if book.visibility - intent.decision_time_ns > self.max_delay:
                return None, "execution_delay_expired"
            if book.visibility >= boundary_ns:
                return None, "execution_window_closed"
            return book, ""
        return None, "no_eligible_book_observation"

    def _fill_record(self, intent: HistoricalExecutionIntent, **values: object) -> HistoricalExecutionFill:
        base: dict[str, object] = {
            "fill_id": _derived_id("fill", intent.intent_id),
            "intent_id": intent.intent_id,
            "intent_digest": intent.intent_digest,
            "decision_digest": intent.decision_digest,
            "side": intent.side,
            "requested_quantity": intent.requested_quantity,
            "filled_quantity": _amount(Fraction(0), "filled_quantity"),
            "cancelled_quantity": intent.requested_quantity,
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

    def _unfilled(self, intent: HistoricalExecutionIntent, reason: str) -> None:
        self._fill_record(intent, outcome=HistoricalExecutionFillOutcome.UNFILLED, reason=reason)

    def _execute(self, intent: HistoricalExecutionIntent, book: _Book) -> None:
        observed = {
            "book_record_digest": book.record.record_digest,
            "book_event_time_ns": book.record.event_time_ns,
            "execution_time_ns": book.visibility,
        }

        def reject(reason: str, **extra: object) -> None:
            self._fill_record(
                intent, outcome=HistoricalExecutionFillOutcome.REJECTED, reason=reason, **observed, **extra
            )

        if book.bid <= 0 or book.ask <= 0 or book.bid_quantity < 0 or book.ask_quantity < 0:
            reject("book_invalid")
            return
        prices = {
            "best_bid_price": _amount(book.bid, "best_bid_price"),
            "best_ask_price": _amount(book.ask, "best_ask_price"),
        }
        if book.ask <= book.bid:
            reject("book_crossed", **prices)
            return
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
            reject("spread_exceeds_max", **quoted)
            return
        depth = book.ask_quantity if intent.side is HistoricalExecutionSide.BUY else book.bid_quantity
        quoted["side_visible_quantity"] = _amount(depth, "side_visible_quantity")
        if depth <= 0:
            reject("insufficient_depth", **quoted)
            return
        requested = Fraction(intent.requested_quantity)
        maximum = self.depth_cap * depth
        quoted["max_executable_quantity"] = _quantity(maximum, "max_executable_quantity")
        filled = Fraction(_quantity(min(requested, maximum), "filled_quantity"))
        if filled <= 0:
            reject("insufficient_depth", **quoted)
            return
        participation = filled / depth * _HUNDRED
        impact = self.impact * participation
        effective = max(self.floor, half_spread_bps + impact)
        quoted.update(
            participation_pct=_amount(participation, "participation_pct"),
            impact_bps=_amount(impact, "impact_bps"),
            effective_slippage_bps=_amount(effective, "effective_slippage_bps"),
        )
        signed = filled if intent.side is HistoricalExecutionSide.BUY else -filled
        raw_price = mid * (1 + effective / _BPS) if signed > 0 else mid * (1 - effective / _BPS)
        price = Fraction(_amount(raw_price, "fill_price")) if raw_price > 0 else Fraction(0)
        if price <= 0:
            reject("fill_price_non_positive", **quoted)
            return
        transition = self._preview(signed, price)
        fee_amount = Fraction(_amount(price * filled * self.fee_bps / _BPS, "fee_amount"))
        if abs(transition.post_quantity) > abs(self.quantity):
            mark = self.marks.at(book.visibility, "fill")
            post_equity = Fraction(
                _amount(
                    self._equity(
                        self._unrealized_of(transition.post_quantity, transition.post_average, mark),
                        realized=self.realized + transition.realized_gross,
                        fees=self.fees + fee_amount,
                    ),
                    "equity",
                )
            )
            if post_equity <= 0 or abs(transition.post_quantity) * mark.price > self.max_leverage * post_equity:
                reject("risk_limit_exceeded", **quoted)
                return
        notional = Fraction(_amount(price * filled, "fill_notional"))
        outcome = (
            HistoricalExecutionFillOutcome.FILLED
            if filled == requested
            else HistoricalExecutionFillOutcome.PARTIALLY_FILLED
        )
        fill = self._fill_record(
            intent,
            outcome=outcome,
            reason="filled" if filled == requested else "visible_depth_cap_partial_remainder_cancelled",
            filled_quantity=_amount(filled, "filled_quantity"),
            cancelled_quantity=_amount(requested - filled, "cancelled_quantity"),
            fill_ratio=_amount(filled / requested, "fill_ratio"),
            fill_price=_amount(price, "fill_price"),
            fill_notional=_amount(notional, "fill_notional"),
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

    def _preview(self, signed: Fraction, price: Fraction) -> _Transition:
        """Pure candidate transition arithmetic. No state mutation: a rejected fill leaves the position untouched."""

        prior_quantity, prior_average = self.quantity, self.average
        post = prior_quantity + signed
        closed = Fraction(0)
        realized = Fraction(0)
        if prior_quantity == 0:
            kind, average = HistoricalExecutionTransitionKind.OPEN, price
        elif _sign(signed) == _sign(prior_quantity):
            kind = HistoricalExecutionTransitionKind.INCREASE
            average = Fraction(
                _amount((abs(prior_quantity) * prior_average + abs(signed) * price) / abs(post), "average_entry_price")  # type: ignore[operator]
            )
        else:
            closed = abs(signed)
            direction = _sign(prior_quantity)
            realized = Fraction(_amount(closed * (price - prior_average) * direction, "realized_gross_pnl"))  # type: ignore[operator]
            if post == 0:
                kind, average = HistoricalExecutionTransitionKind.CLOSE, None
            else:
                kind, average = HistoricalExecutionTransitionKind.REDUCE, prior_average
        return _Transition(kind, prior_quantity, prior_average, signed, post, average, closed, realized)

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
                prior_quantity=_amount(transition.prior_quantity, "prior_quantity"),
                prior_average_entry_price=None
                if transition.prior_average is None
                else _amount(transition.prior_average, "average_entry_price"),
                delta_quantity=_amount(transition.signed, "delta_quantity"),
                post_quantity=_amount(transition.post_quantity, "post_quantity"),
                post_average_entry_price=None
                if transition.post_average is None
                else _amount(transition.post_average, "average_entry_price"),
                closed_quantity=_amount(transition.closed_quantity, "closed_quantity"),
                realized_gross_pnl=_amount(transition.realized_gross, "realized_gross_pnl"),
                transition_digest="",
            ),
            "transition_digest",
        )
        self.ledgers.transitions.append(record)
        self.quantity, self.average = transition.post_quantity, transition.post_average
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
        self.segments.append((time_ns, transition.post_quantity))
        self._valuation(HistoricalExecutionValuationKind.FILL, time_ns, fill.fill_digest)
        if transition.kind is HistoricalExecutionTransitionKind.CLOSE:
            self._close_trade(time_ns)

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
        if self.trade is None:
            raise _EconomicFailure("trade_state_inconsistent")
        self.ledgers.trades.append(
            self._trade_record(self.trade, HistoricalExecutionTradeStatus.CLOSED, time_ns, None, None)
        )
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

    def _check_funding_grid(self, interval: int) -> int | None:
        """The approved interval must separate consecutive settlements; returns the last liability time."""

        for earlier, later in zip(self.funding, self.funding[1:], strict=False):
            if later.event_time_ns - earlier.event_time_ns != interval:
                raise _EconomicFailure("funding_interval_inconsistent")
        if not self.funding:
            return None
        return self._liability(self.funding[-1], interval)

    def _check_tail_coverage(self, last_liability: int | None, interval: int, end_ns: int) -> None:
        """Fail when a liable instant lies after the last available settlement (no silent interpolation)."""

        expected = interval if last_liability is None else last_liability + interval
        for index, (start_ns, quantity) in enumerate(self.segments):
            if quantity == 0:
                continue
            stop_ns = self.segments[index + 1][0] if index + 1 < len(self.segments) else end_ns - 1
            if last_liability is None:
                raise _EconomicFailure("funding_coverage_incomplete")
            first = expected if start_ns < expected else expected + ((start_ns - expected) // interval + 1) * interval
            if first <= stop_ns and first < end_ns:
                raise _EconomicFailure("funding_coverage_incomplete")

    def run_all(self) -> _Ledgers:
        run = self.run
        start_ns, end_ns = run.evaluation_start_ns, run.evaluation_end_ns
        interval = self.policy.funding_interval_ns
        self._check_funding_cycle_finality(interval)
        last_liability = self._check_funding_grid(interval)
        events: list[tuple[int, int, int]] = []
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
        pending: dict[int, tuple[HistoricalExecutionIntent, _Book]] = {}
        self._valuation(HistoricalExecutionValuationKind.INITIAL, start_ns, None)
        while events:
            time_ns, priority, index = heapq.heappop(events)
            if priority == _PRIORITY_FUNDING:
                self._settle(self.funding[index], time_ns)
            elif priority == _PRIORITY_DECISION:
                intent = self._intent(decisions[index])
                if intent is None:
                    continue
                boundary_ns = decisions[index + 1].decision_time_ns if index + 1 < len(decisions) else end_ns
                book, reason = self._select_book(intent, boundary_ns)
                if book is None:
                    self._unfilled(intent, reason)
                    continue
                pending[index] = (intent, book)
                heapq.heappush(events, (book.visibility, _PRIORITY_FILL, index))
            elif priority == _PRIORITY_FILL:
                intent, book = pending.pop(index)
                self._execute(intent, book)
            elif priority == _PRIORITY_DAY_BOUNDARY:
                self._valuation(HistoricalExecutionValuationKind.UTC_DAY_BOUNDARY, time_ns, None)
            else:
                self._valuation(HistoricalExecutionValuationKind.EVALUATION_END, time_ns, None)
        self._check_tail_coverage(last_liability, interval, end_ns)
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


# --- result -------------------------------------------------------------------------------------------------------------


def _assemble_result(
    *,
    run_binding: object,
    policy_binding: object,
    economics_approval: object,
    result_id: object,
    correlation_id: object,
) -> HistoricalExecutionEconomicsResult:
    """The one result assembly path, shared by the builder and verifier re-derivation."""

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
    integrity = _sorted_unique(codes)

    ledgers = _Ledgers()
    mark_series = book_series = ""
    if integrity or run is None or policy is None or context is None:
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
        max_leverage = _max_leverage(spec)
        if max_leverage is None:
            fail.append(_reason("strategy_max_leverage_unavailable"))
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
                ).run_all()
            except _EconomicFailure as failure:
                fail.append(_reason(failure.code))
                ledgers = _Ledgers()
            verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        status = EdgeEvidenceStatus.READY
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    computed = status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS
    seed = HistoricalExecutionEconomicsResult(
        schema_version=_SCHEMA_VERSION,
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
    )
    return replace(seed, result_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_historical_execution_economics(
    run: HistoricalDecisionRun,
    *,
    expected_run_digest: str,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    expected_economics_policy_digest: str,
    economics_approval: HistoricalExecutionEconomicsApproval | None,
    result_id: str,
    correlation_id: str,
) -> HistoricalExecutionEconomicsResult:
    """Build deterministic historical execution economics for an authenticated decision run.

    Malformed caller input, a malformed approval or a non-serializable upstream object raises
    ``HistoricalExecutionEconomicsError``. A run or policy that fails re-proof yields ``REJECTED``/``NOT_EVALUATED``.
    Only ``READY`` + ``PASS`` carries economic ledgers.
    """

    if type(run) is not HistoricalDecisionRun:
        raise _fail("run_malformed")
    if type(economics_policy) is not HistoricalExecutionEconomicsPolicy:
        raise _fail("policy_malformed")
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


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
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


def historical_execution_economics_from_payload(payload: object) -> HistoricalExecutionEconomicsResult:
    """Strictly reconstruct a result from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(HistoricalExecutionEconomicsResult, payload, _RESULT_CONVERTERS)  # type: ignore[return-value]


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
    "HISTORICAL_EXECUTION_NON_CLAIM_FLAGS",
    "HistoricalExecutionEconomicsError",
    "HistoricalExecutionEconomicsResult",
    "HistoricalExecutionFeeCashflow",
    "HistoricalExecutionFill",
    "HistoricalExecutionFillOutcome",
    "HistoricalExecutionFundingCashflow",
    "HistoricalExecutionIntent",
    "HistoricalExecutionIntentAction",
    "HistoricalExecutionPositionTransition",
    "HistoricalExecutionSide",
    "HistoricalExecutionTerminalState",
    "HistoricalExecutionTrade",
    "HistoricalExecutionTradeStatus",
    "HistoricalExecutionTransitionKind",
    "HistoricalExecutionValuation",
    "HistoricalExecutionValuationKind",
    "build_historical_execution_economics",
    "historical_execution_economics_digest",
    "historical_execution_economics_from_payload",
    "historical_execution_economics_payload_is_well_formed",
    "historical_execution_economics_to_dict",
    "verify_historical_execution_economics",
]
