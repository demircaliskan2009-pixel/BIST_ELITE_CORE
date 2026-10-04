"""Deterministic paper sleeve daily valuation evidence (PAPER_SLEEVE_PERFORMANCE_PROVENANCE_CONSTRUCTION_V1).

This artifact values ONE sleeve's paper episodes, day by day, under one verified ``PaperSleeveEquityBasisPolicy``. It
emits the exact accepted ``PaperDailyReturnBucket`` form, so the generic daily-return and Sharpe substrate can be
reused without sleeve semantics leaking into it. It is paper-only, deterministic, digest-bound and fail-closed.

Provenance. Every episode hop is RECONSTRUCTED through its public builder, and the supplied artifact must equal the
reconstruction canonically; only the reconstructions are used afterwards. A digest alone is never authority, and a
self-sealed artifact never passes. The chain per episode is:

* sleeve authority: the capacity decision is rebuilt from its allocator draft and capacity policy, and must be
  ``ADMITTED``. ``sleeve_id`` is copied only from that decision;
* the order-intent request is rebuilt from its own fields and must bind that decision's digest. The admission is
  rebuilt from the decision and the request, and must be ``ADMITTED``;
* the order intent is rebuilt from the admission;
* the fill, the position transition, the new position state and the episode PnL report are rebuilt exactly as the
  runner builds them. The episode run is rebuilt, must be ``COMPUTED``, and must bind every child digest;
* the realized-PnL event is rebuilt, and the end-to-end episode is rebuilt over the signal bridge, the intent, the
  run and the event. It must be ``READY``, which binds bridge request lineage and capacity lineage.

Cross-episode rules:

* one sleeve and one market, equal to the policy's;
* a contiguous position chain from a FLAT genesis (each prior state is exactly the previous new state);
* strictly increasing fill instants inside the window;
* no economic action is used twice.

Time authority is the digest-bound ``PaperFillMarketSnapshot.observed_at_ns`` of each fill. UTC days are
start-inclusive and end-exclusive. Instants are injected evidence and their origin is not proven.

Daily close. For every UTC day of the window a day close must supply a ``PaperMarkSnapshot`` observed EXACTLY at the
bucket end, with no tolerance, no carry-forward, no interpolation and no future mark. It must also supply the PnL
report rebuilt by the public builder over the exact chain position after all fills strictly before the bucket end.
The day's equity basis is::

    reference notional + Σ gross realized - Σ fees + close unrealized + Σ funding

The sums run over fills (and funding settlements) strictly before the bucket end. Funding comes from verified
``PaperSleeveFundingEvidence``, whose every event is re-bound to the exact chain position it applies to; it is zero
only under the governed ``GOVERNED_NOT_APPLICABLE`` treatment, and never implicitly.

Index. The index starts at the accepted methodology convention ``1``, a dimensionless value and never a currency
unit. Each day's return ``E_d / E_(d-1) - 1`` is exact and is rendered ONCE at scale 18 with ROUND_HALF_EVEN. The
index is chain-linked, ``I_d = I_(d-1) * (1 + r_d)``. Every bucket return is therefore a terminating decimal, which
the accepted daily-return series requires, while the exact equity basis stays carried.

Blocking. ``NOT_COMPUTABLE`` is a represented state, never a fake value. It applies when:

* the policy does not advance;
* required funding evidence is absent;
* a day close is missing;
* an equity basis is not strictly positive;
* a rendered growth factor is not strictly positive;
* an index exceeds its committed representation bound.

Any provenance defect raises ``PaperSleeveDailyValuationError`` instead.
``verify_paper_sleeve_daily_valuation_evidence`` re-proves an evidence by rebuilding it from its inputs and is total.

Non-overclaim: the index is a synthetic paper-performance normalization, never account equity, capital, margin, a
balance or allocation authority. It claims no profitability, edge, readiness or venue truth. Marks, instants and
funding origins are not proven, the completeness of the supplied episode set is not proven, and the fee and slippage
rates of each episode's accepted fill policy are that episode's paper assumptions, not governed values. Exact
``Fraction`` arithmetic, no float, no ``decimal`` context, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.paper_allocator_intent_draft import PaperAllocatorIntentDraft
from crypto_core.validation.paper_capacity_gate import (
    PaperCapacityGateDecision,
    PaperCapacityGatePolicy,
    PaperCapacityGateStatus,
    evaluate_paper_capacity_gate,
    paper_capacity_gate_decision_to_dict,
)
from crypto_core.validation.paper_daily_return_series_evidence import PaperDailyReturnBucket
from crypto_core.validation.paper_end_to_end_episode import (
    PaperEndToEndEpisode,
    PaperEndToEndEpisodeStatus,
    build_paper_end_to_end_episode,
    paper_end_to_end_episode_to_dict,
)
from crypto_core.validation.paper_episode_runner import (
    PaperEpisodeRunResult,
    PaperEpisodeRunStatus,
    paper_episode_run_result_to_dict,
    run_paper_episode,
)
from crypto_core.validation.paper_fill_simulator import (
    PaperFillMarketSnapshot,
    PaperFillPolicy,
    PaperFillSimulationResult,
    paper_fill_simulation_result_digest,
    paper_fill_simulation_result_to_dict,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import (
    PaperOrderIntent,
    build_paper_order_intent,
    paper_order_intent_to_dict,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentAdmissionDecision,
    PaperOrderIntentAdmissionStatus,
    PaperOrderIntentRequest,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
    paper_order_intent_admission_decision_to_dict,
    paper_order_intent_request_to_dict,
)
from crypto_core.validation.paper_pnl_report import (
    PaperMarkSnapshot,
    PaperPnlReport,
    PaperPnlReportStatus,
    compute_paper_pnl_report,
    paper_pnl_report_digest,
    paper_pnl_report_to_dict,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    PaperPositionStateSide,
    PaperPositionTransitionResult,
    apply_paper_fill_to_position,
    paper_position_state_digest,
    paper_position_state_to_dict,
    paper_position_transition_result_digest,
    paper_position_transition_result_to_dict,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    PaperRealizedPnlStatus,
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_to_dict,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST,
    PaperSleeveEquityBasisPolicy,
    PaperSleeveFundingTreatment,
    paper_sleeve_equity_basis_rule_set,
    verify_paper_sleeve_equity_basis_policy,
)
from crypto_core.validation.paper_sleeve_funding_evidence import (
    PaperSleeveFundingEvidence,
    verify_paper_sleeve_funding_evidence,
)
from crypto_core.validation.strategy_signal_to_paper_intent import StrategySignalToPaperIntent

_SCHEMA_VERSION = "paper-sleeve-daily-valuation-evidence.v1"
_REASON_PREFIX = "paper_sleeve_daily_valuation_evidence"
_SELF_DIGEST_FIELD = "valuation_digest"
_BUCKET_ID_PREFIX = "sleeve-day"
_T = TypeVar("_T")

# Every numeric rule is read from the equity-basis rule set that the verified policy commits.
_RULES = paper_sleeve_equity_basis_rule_set()
_SCALE: int = _RULES["decimal_scale"]  # type: ignore[assignment]
_SCALE_FACTOR = 10**_SCALE
_MAX_CONSUMED_DECIMAL: int = _RULES["consumed_decimal_max_text_length"]  # type: ignore[assignment]
_MAX_INDEX_TEXT: int = _RULES["normalized_index_max_text_length"]  # type: ignore[assignment]
_DAY_NS: int = _RULES["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULES["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULES["max_text_length"]  # type: ignore[assignment]


class PaperSleeveDailyValuationError(EdgeArtifactError):
    """Raised on malformed input or any provenance defect: an invalid valuation is never represented."""


class PaperSleeveValuationStatus(str, Enum):
    """``COMPUTED`` only when every day is valued; ``NOT_COMPUTABLE`` is a represented blocked state, never a value."""

    COMPUTED = "COMPUTED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"


@dataclass(frozen=True)
class PaperSleeveEpisodeEvidence:
    """The exact accepted artifacts of one sleeve paper episode; every hop is re-proven by reconstruction."""

    capacity_policy: PaperCapacityGatePolicy
    allocator_draft: PaperAllocatorIntentDraft
    capacity_decision: PaperCapacityGateDecision
    order_intent_request: PaperOrderIntentRequest
    admission_decision: PaperOrderIntentAdmissionDecision
    order_intent: PaperOrderIntent
    signal_bridge: StrategySignalToPaperIntent
    prior_position_state: PaperPositionState
    fill_market_snapshot: PaperFillMarketSnapshot
    fill_policy: PaperFillPolicy
    episode_mark_snapshot: PaperMarkSnapshot
    fill_result: PaperFillSimulationResult
    position_transition: PaperPositionTransitionResult
    new_position_state: PaperPositionState
    episode_pnl_report: PaperPnlReport
    episode_run: PaperEpisodeRunResult
    realized_pnl_event: PaperRealizedPnlEvent
    end_to_end_episode: PaperEndToEndEpisode


@dataclass(frozen=True)
class PaperSleeveDayCloseValuation:
    """One UTC day close: a mark observed exactly at the bucket end and the PnL report over the close position."""

    close_mark_snapshot: PaperMarkSnapshot
    close_pnl_report: PaperPnlReport


@dataclass(frozen=True)
class PaperSleeveValuationInputs:
    """Everything the valuation consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    valuation_id: str
    correlation_id: str
    equity_basis_policy: PaperSleeveEquityBasisPolicy
    window_start_ns: int
    window_end_ns: int
    episodes: tuple[PaperSleeveEpisodeEvidence, ...]
    day_closes: tuple[PaperSleeveDayCloseValuation, ...]
    funding_evidence: PaperSleeveFundingEvidence | None


@dataclass(frozen=True)
class PaperSleeveEpisodeValuation:
    """The re-proven economics and lineage of one episode, in position-chain order."""

    episode_digest: str
    capacity_decision_digest: str
    order_intent_digest: str
    episode_run_digest: str
    fill_simulation_result_digest: str
    realized_pnl_event_digest: str
    prior_position_state_digest: str
    new_position_state_digest: str
    fill_observed_at_ns: int
    day_index: int
    realized_amount: str
    fee_amount: str


@dataclass(frozen=True)
class PaperSleeveDayValuation:
    """One UTC day's exact close valuation and the accepted bucket it emits."""

    day_index: int
    bucket_start_ns: int
    bucket_end_ns: int
    close_position_state_digest: str
    close_mark_snapshot_digest: str
    close_pnl_report_digest: str
    cumulative_realized: str
    cumulative_fees: str
    cumulative_funding: str
    close_unrealized: str
    equity_basis: str
    daily_return: str
    normalized_index_start: str
    normalized_index_end: str
    bucket_id: str
    bucket_digest: str


PAPER_SLEEVE_DAILY_VALUATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("synthetic_paper_performance_index", True),
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("margin_modeled", False),
    ("balance_represented", False),
    ("risk_budget_used_as_denominator", False),
    ("historical_economics_consumed", False),
    ("allocation_performed", False),
    ("execution_authorized", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("profitability_proven", False),
    ("edge_proven", False),
    ("prdv4_stage4_complete", False),
    ("mark_price_origin_proven", False),
    ("timestamp_origin_proven", False),
    ("funding_amount_origin_proven", False),
    ("episode_set_completeness_proven", False),
    ("fill_policy_values_governed", False),
    ("interpolation_used", False),
    ("carry_forward_used", False),
    ("sharpe_computed", False),
)


@dataclass(frozen=True)
class PaperSleeveDailyValuationEvidence:
    """Immutable, digest-bound daily valuation of one sleeve. Synthetic paper performance only; never account value."""

    schema_version: str
    status: PaperSleeveValuationStatus
    computed: bool
    valuation_id: str
    correlation_id: str
    sleeve_id: str
    market_symbol: str
    equity_basis_policy_id: str
    equity_basis_policy_version: str
    equity_basis_policy_digest: str
    equity_basis_digest: str
    equity_basis_rule_set_digest: str
    equity_basis_policy_advances: bool
    paper_performance_reference_notional: str
    funding_treatment: PaperSleeveFundingTreatment
    funding_evidence_digest: str
    funding_event_count: int
    window_start_ns: int
    window_end_ns: int
    day_count: int
    capacity_decision_digests: tuple[str, ...]
    episode_count: int
    episodes: tuple[PaperSleeveEpisodeValuation, ...]
    day_close_count: int
    lineage_digest: str
    days: tuple[PaperSleeveDayValuation, ...]
    reason_codes: tuple[str, ...]
    valuation_digest: str
    paper_only: bool = True
    synthetic_paper_performance_index: bool = True
    account_equity_represented: bool = False
    capital_represented: bool = False
    margin_modeled: bool = False
    balance_represented: bool = False
    risk_budget_used_as_denominator: bool = False
    historical_economics_consumed: bool = False
    allocation_performed: bool = False
    execution_authorized: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    prdv4_stage4_complete: bool = False
    mark_price_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    funding_amount_origin_proven: bool = False
    episode_set_completeness_proven: bool = False
    fill_policy_values_governed: bool = False
    interpolation_used: bool = False
    carry_forward_used: bool = False
    sharpe_computed: bool = False


_RECORD_TYPES = frozenset({PaperSleeveEpisodeValuation, PaperSleeveDayValuation})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveDailyValuationEvidence: {
        "status": PaperSleeveValuationStatus,
        "funding_treatment": PaperSleeveFundingTreatment,
    },
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveDailyValuationError:
    return PaperSleeveDailyValuationError(_reason(code))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


def _consumed_decimal(value: object, code: str) -> Fraction:
    """Exact value of plain decimal text emitted by an accepted paper artifact; anything else fails closed."""

    if type(value) is not str or value == "" or len(value) > _MAX_CONSUMED_DECIMAL or not value.isascii():
        raise _fail(code)
    integer, dot, fraction = (value[1:] if value.startswith("-") else value).partition(".")
    if not _ascii_digits(integer) or (integer != "0" and integer.startswith("0")):
        raise _fail(code)
    if dot == "." and not _ascii_digits(fraction):
        raise _fail(code)
    return Fraction(value)


def _factor_out(value: int, prime: int) -> tuple[int, int]:
    """``(rest, count)`` with ``value == rest * prime**count`` and ``rest`` not divisible by ``prime``.

    Dividing by repeatedly squared prime powers keeps the number of big-integer divisions logarithmic in ``count``.
    """

    count = 0
    while value % prime == 0:
        power, exponent = prime, 1
        while value % (power * power) == 0:
            power *= power
            exponent *= 2
        value //= power
        count += exponent
    return value, count


def _render(value: Fraction, max_length: int) -> str | None:
    """Canonical plain decimal text (no exponent, no trailing zero, no negative zero) of a terminating value.

    ``None`` when the value does not terminate in decimal or its text would exceed ``max_length``; the length is
    bounded before any integer-to-text conversion.
    """

    rest, twos = _factor_out(value.denominator, 2)
    rest, fives = _factor_out(rest, 5)
    if rest != 1:
        return None
    scale = max(twos, fives)
    if scale >= max_length:
        return None
    units = abs(value.numerator) * (2 ** (scale - twos)) * (5 ** (scale - fives))
    if units >= 10**max_length:
        return None
    digits = str(units).rjust(scale + 1, "0")
    rendered = f"{digits[:-scale]}.{digits[-scale:]}" if scale else digits
    if scale:
        rendered = rendered.rstrip("0").rstrip(".")
    if value < 0 and rendered != "0":
        rendered = f"-{rendered}"
    return rendered if len(rendered) <= max_length else None


def _render_half_even(value: Fraction) -> Fraction:
    """The value rounded ONCE to the scale-18 grid with exact integer ROUND_HALF_EVEN (sign-symmetric)."""

    magnitude = abs(value)
    quotient, remainder = divmod(magnitude.numerator * _SCALE_FACTOR, magnitude.denominator)
    twice = 2 * remainder
    if twice > magnitude.denominator or (twice == magnitude.denominator and quotient % 2 == 1):
        quotient += 1
    return Fraction(-quotient if value < 0 else quotient, _SCALE_FACTOR)


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """Call one accepted public builder; any failure is a provenance defect of this valuation."""

    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed at this boundary
        raise _fail(f"{code}_reconstruction_failed") from exc


def _metadata(artifact: object, code: str) -> dict[str, str]:
    try:
        return dict(artifact.metadata)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - malformed carried metadata cannot be reconstructed
        raise _fail(f"{code}_metadata_malformed") from exc


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _bucket_digest(bucket_id: str, start_ns: int, end_ns: int, index_start: str, index_end: str) -> str:
    """The accepted daily-return bucket digest contract, replayed exactly over its five committed fields."""

    return edge_sha256_text(
        edge_canonical_json(
            {
                "bucket_id": bucket_id,
                "bucket_start_ns": start_ns,
                "bucket_end_ns": end_ns,
                "normalized_index_start": index_start,
                "normalized_index_end": index_end,
            }
        )
    )


# --- episode reconstruction ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProvenEpisode:
    sleeve_id: str
    market_symbol: str
    fill_observed_at_ns: int
    prior_state: PaperPositionState
    new_state: PaperPositionState
    realized: Fraction
    fee: Fraction
    record: PaperSleeveEpisodeValuation
    identities: tuple[str, ...]


_EPISODE_PART_TYPES: tuple[tuple[str, type], ...] = (
    ("capacity_policy", PaperCapacityGatePolicy),
    ("allocator_draft", PaperAllocatorIntentDraft),
    ("capacity_decision", PaperCapacityGateDecision),
    ("order_intent_request", PaperOrderIntentRequest),
    ("admission_decision", PaperOrderIntentAdmissionDecision),
    ("order_intent", PaperOrderIntent),
    ("signal_bridge", StrategySignalToPaperIntent),
    ("prior_position_state", PaperPositionState),
    ("fill_market_snapshot", PaperFillMarketSnapshot),
    ("fill_policy", PaperFillPolicy),
    ("episode_mark_snapshot", PaperMarkSnapshot),
    ("fill_result", PaperFillSimulationResult),
    ("position_transition", PaperPositionTransitionResult),
    ("new_position_state", PaperPositionState),
    ("episode_pnl_report", PaperPnlReport),
    ("episode_run", PaperEpisodeRunResult),
    ("realized_pnl_event", PaperRealizedPnlEvent),
    ("end_to_end_episode", PaperEndToEndEpisode),
)


def _prove_episode(evidence: object, *, window_start_ns: int, window_end_ns: int) -> _ProvenEpisode:
    _require_exact(evidence, PaperSleeveEpisodeEvidence, "episode")
    episode = cast(PaperSleeveEpisodeEvidence, evidence)
    for name, cls in _EPISODE_PART_TYPES:
        _require_exact(getattr(episode, name, None), cls, name)

    # Sleeve authority: the capacity decision must be exactly what the accepted gate emits for its draft + policy.
    decision = episode.capacity_decision
    rebuilt_decision = _rebuild(
        "capacity_decision",
        evaluate_paper_capacity_gate,
        episode.allocator_draft,
        episode.capacity_policy,
        requested_notional=decision.requested_notional,
        requested_units=decision.requested_units,
        correlation_id=decision.correlation_id,
        metadata=_metadata(decision, "capacity_decision"),
    )
    if not _canonically_equal(decision, rebuilt_decision, paper_capacity_gate_decision_to_dict):
        raise _fail("capacity_decision_not_reconstructed")
    if rebuilt_decision.status is not PaperCapacityGateStatus.ADMITTED:
        raise _fail("capacity_decision_not_admitted")

    request = episode.order_intent_request
    rebuilt_request = _rebuild(
        "order_intent_request",
        build_paper_order_intent_request,
        request_id=request.request_id,
        capacity_decision_digest=request.capacity_decision_digest,
        market_symbol=request.market_symbol,
        side=request.side,
        intent_type=request.intent_type,
        requested_notional=request.requested_notional,
        requested_units=request.requested_units,
        limit_price=request.limit_price,
        correlation_id=request.correlation_id,
        metadata=_metadata(request, "order_intent_request"),
    )
    if not _canonically_equal(request, rebuilt_request, paper_order_intent_request_to_dict):
        raise _fail("order_intent_request_not_reconstructed")
    if rebuilt_request.capacity_decision_digest != rebuilt_decision.decision_digest:
        raise _fail("request_capacity_lineage_mismatch")

    admission = episode.admission_decision
    rebuilt_admission = _rebuild(
        "admission_decision",
        evaluate_paper_order_intent_admission,
        rebuilt_decision,
        rebuilt_request,
        correlation_id=admission.correlation_id,
        metadata=_metadata(admission, "admission_decision"),
    )
    if not _canonically_equal(admission, rebuilt_admission, paper_order_intent_admission_decision_to_dict):
        raise _fail("admission_decision_not_reconstructed")
    if rebuilt_admission.status is not PaperOrderIntentAdmissionStatus.ADMITTED:
        raise _fail("admission_decision_not_admitted")

    intent = episode.order_intent
    rebuilt_intent = _rebuild(
        "order_intent",
        build_paper_order_intent,
        rebuilt_admission,
        intent_id=intent.intent_id,
        correlation_id=intent.correlation_id,
        metadata=_metadata(intent, "order_intent"),
    )
    if not _canonically_equal(intent, rebuilt_intent, paper_order_intent_to_dict):
        raise _fail("order_intent_not_reconstructed")

    # Execution: rebuild the children exactly as the runner builds them, then the run itself.
    run = episode.episode_run
    correlation = run.correlation_id
    prior = episode.prior_position_state
    snapshot = episode.fill_market_snapshot
    rebuilt_fill = _rebuild(
        "fill_result",
        simulate_paper_fill,
        rebuilt_intent,
        snapshot,
        episode.fill_policy,
        fill_simulation_id=episode.fill_result.fill_simulation_id,
        correlation_id=correlation,
    )
    if not _canonically_equal(episode.fill_result, rebuilt_fill, paper_fill_simulation_result_to_dict):
        raise _fail("fill_result_not_reconstructed")
    rebuilt_transition, rebuilt_new_state = _rebuild(
        "position_transition",
        apply_paper_fill_to_position,
        prior,
        rebuilt_fill,
        transition_id=episode.position_transition.transition_id,
        new_position_state_id=episode.new_position_state.position_state_id,
        correlation_id=correlation,
    )
    if not _canonically_equal(
        episode.position_transition, rebuilt_transition, paper_position_transition_result_to_dict
    ):
        raise _fail("position_transition_not_reconstructed")
    if rebuilt_new_state is None or not _canonically_equal(
        episode.new_position_state, rebuilt_new_state, paper_position_state_to_dict
    ):
        raise _fail("new_position_state_not_reconstructed")
    rebuilt_report = _rebuild(
        "episode_pnl_report",
        compute_paper_pnl_report,
        rebuilt_new_state,
        episode.episode_mark_snapshot,
        pnl_report_id=episode.episode_pnl_report.pnl_report_id,
        correlation_id=correlation,
    )
    if not _canonically_equal(episode.episode_pnl_report, rebuilt_report, paper_pnl_report_to_dict):
        raise _fail("episode_pnl_report_not_reconstructed")
    rebuilt_run = _rebuild(
        "episode_run",
        run_paper_episode,
        rebuilt_intent,
        prior,
        snapshot,
        episode.fill_policy,
        episode.episode_mark_snapshot,
        fill_simulation_id=rebuilt_fill.fill_simulation_id,
        position_transition_id=rebuilt_transition.transition_id,
        new_position_state_id=rebuilt_new_state.position_state_id,
        pnl_report_id=rebuilt_report.pnl_report_id,
        episode_run_id=run.episode_run_id,
        correlation_id=correlation,
        metadata=_metadata(run, "episode_run"),
    )
    if not _canonically_equal(run, rebuilt_run, paper_episode_run_result_to_dict):
        raise _fail("episode_run_not_reconstructed")
    if rebuilt_run.status is not PaperEpisodeRunStatus.COMPUTED:
        raise _fail("episode_run_not_computed")
    child_bindings = (
        (rebuilt_run.fill_simulation_result_digest, paper_fill_simulation_result_digest(rebuilt_fill)),
        (rebuilt_run.position_transition_digest, paper_position_transition_result_digest(rebuilt_transition)),
        (rebuilt_run.new_position_state_digest, paper_position_state_digest(rebuilt_new_state)),
        (rebuilt_run.pnl_report_digest, paper_pnl_report_digest(rebuilt_report)),
        (rebuilt_run.prior_position_state_digest, paper_position_state_digest(prior)),
    )
    if any(left != right for left, right in child_bindings):
        raise _fail("episode_run_child_binding_mismatch")

    event = episode.realized_pnl_event
    rebuilt_event = _rebuild(
        "realized_pnl_event",
        compute_paper_realized_pnl_event,
        prior,
        rebuilt_fill,
        rebuilt_transition,
        rebuilt_new_state,
        realized_pnl_event_id=event.realized_pnl_event_id,
        correlation_id=event.correlation_id,
        metadata=_metadata(event, "realized_pnl_event"),
    )
    if not _canonically_equal(event, rebuilt_event, paper_realized_pnl_event_to_dict):
        raise _fail("realized_pnl_event_not_reconstructed")
    if rebuilt_event.status not in (PaperRealizedPnlStatus.COMPUTED, PaperRealizedPnlStatus.NO_REALIZED_PNL):
        raise _fail("realized_pnl_event_not_computed")

    end_to_end = episode.end_to_end_episode
    bridge = episode.signal_bridge
    rebuilt_end_to_end = _rebuild(
        "end_to_end_episode",
        build_paper_end_to_end_episode,
        bridge,
        rebuilt_intent,
        rebuilt_run,
        rebuilt_event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=rebuilt_intent.intent_digest,
        expected_episode_run_digest=rebuilt_run.episode_run_digest,
        expected_realized_pnl_event_digest=rebuilt_event.realized_pnl_event_digest,
        episode_id=end_to_end.episode_id,
        run_id=end_to_end.run_id,
        correlation_id=end_to_end.correlation_id,
        metadata=_metadata(end_to_end, "end_to_end_episode"),
    )
    if not _canonically_equal(end_to_end, rebuilt_end_to_end, paper_end_to_end_episode_to_dict):
        raise _fail("end_to_end_episode_not_reconstructed")
    if rebuilt_end_to_end.status is not PaperEndToEndEpisodeStatus.READY:
        raise _fail("end_to_end_episode_not_ready")

    instant = snapshot.observed_at_ns
    if type(instant) is not int or instant < window_start_ns or instant >= window_end_ns:
        raise _fail("fill_instant_outside_window")
    realized = _consumed_decimal(rebuilt_event.realized_pnl, "realized_amount_invalid")
    fee = _consumed_decimal(rebuilt_fill.fee_amount, "fee_amount_invalid")
    if fee < 0:
        raise _fail("fee_amount_negative")
    realized_text = _render(realized, _MAX_CONSUMED_DECIMAL)
    fee_text = _render(fee, _MAX_CONSUMED_DECIMAL)
    if realized_text is None or fee_text is None:
        raise _fail("episode_amount_not_representable")
    record = PaperSleeveEpisodeValuation(
        episode_digest=rebuilt_end_to_end.episode_digest,
        capacity_decision_digest=rebuilt_decision.decision_digest,
        order_intent_digest=rebuilt_intent.intent_digest,
        episode_run_digest=rebuilt_run.episode_run_digest,
        fill_simulation_result_digest=rebuilt_run.fill_simulation_result_digest,
        realized_pnl_event_digest=rebuilt_event.realized_pnl_event_digest,
        prior_position_state_digest=rebuilt_run.prior_position_state_digest,
        new_position_state_digest=paper_position_state_digest(rebuilt_new_state),
        fill_observed_at_ns=instant,
        day_index=(instant - window_start_ns) // _DAY_NS,
        realized_amount=realized_text,
        fee_amount=fee_text,
    )
    identities = (
        rebuilt_decision.decision_digest,
        rebuilt_request.request_digest,
        rebuilt_admission.decision_digest,
        rebuilt_intent.intent_digest,
        bridge.bridge_digest,
        rebuilt_run.episode_run_digest,
        rebuilt_run.fill_simulation_result_digest,
        rebuilt_run.position_transition_digest,
        rebuilt_event.realized_pnl_event_digest,
        rebuilt_end_to_end.episode_digest,
    )
    return _ProvenEpisode(
        sleeve_id=rebuilt_decision.sleeve_id,
        market_symbol=rebuilt_intent.market_symbol,
        fill_observed_at_ns=instant,
        prior_state=prior,
        new_state=rebuilt_new_state,
        realized=realized,
        fee=fee,
        record=record,
        identities=identities,
    )


def _prove_chain(episodes: tuple[_ProvenEpisode, ...]) -> None:
    """One sleeve, one market, a contiguous chain from a FLAT genesis, strictly increasing fills, no reused action."""

    first = episodes[0]
    if first.prior_state.side is not PaperPositionStateSide.FLAT:
        raise _fail("genesis_position_not_flat")
    seen: set[str] = set()
    for index, episode in enumerate(episodes):
        if episode.sleeve_id != first.sleeve_id:
            raise _fail("cross_sleeve_episode")
        if episode.market_symbol != first.market_symbol:
            raise _fail("cross_market_episode")
        if index > 0:
            previous = episodes[index - 1]
            if episode.record.prior_position_state_digest != previous.record.new_position_state_digest:
                raise _fail("position_chain_discontinuous")
            if episode.fill_observed_at_ns <= previous.fill_observed_at_ns:
                raise _fail("fill_instants_not_strictly_increasing")
        for identity in episode.identities:
            if identity in seen:
                raise _fail("economic_action_reused")
            seen.add(identity)


def _position_before(
    instant: int, genesis: PaperPositionState, episodes: tuple[_ProvenEpisode, ...]
) -> PaperPositionState:
    """The chain position after every fill strictly before ``instant``."""

    state = genesis
    for episode in episodes:
        if episode.fill_observed_at_ns < instant:
            state = episode.new_state
    return state


# --- day closes and funding -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProvenClose:
    day_index: int
    position_digest: str
    mark_digest: str
    report_digest: str
    unrealized: Fraction


def _prove_day_closes(
    values: object,
    *,
    window_start_ns: int,
    day_count: int,
    market_symbol: str,
    genesis: PaperPositionState,
    episodes: tuple[_ProvenEpisode, ...],
) -> dict[int, _ProvenClose]:
    proven: dict[int, _ProvenClose] = {}
    for item in _snapshot(values, "day_closes"):
        _require_exact(item, PaperSleeveDayCloseValuation, "day_close")
        _require_exact(getattr(item, "close_mark_snapshot", None), PaperMarkSnapshot, "close_mark_snapshot")
        _require_exact(getattr(item, "close_pnl_report", None), PaperPnlReport, "close_pnl_report")
        close = cast(PaperSleeveDayCloseValuation, item)
        mark = close.close_mark_snapshot
        report = close.close_pnl_report
        instant = mark.observed_at_ns
        if type(instant) is not int or instant <= window_start_ns or (instant - window_start_ns) % _DAY_NS != 0:
            raise _fail("close_mark_not_at_a_bucket_end")
        day_index = (instant - window_start_ns) // _DAY_NS - 1
        if day_index >= day_count:
            raise _fail("close_mark_not_at_a_bucket_end")
        if day_index in proven:
            raise _fail("day_close_duplicate")
        if mark.market_symbol != market_symbol:
            raise _fail("close_mark_market_mismatch")
        position = _position_before(instant, genesis, episodes)
        rebuilt = _rebuild(
            "close_pnl_report",
            compute_paper_pnl_report,
            position,
            mark,
            pnl_report_id=report.pnl_report_id,
            correlation_id=report.correlation_id,
            metadata=_metadata(report, "close_pnl_report"),
        )
        if not _canonically_equal(report, rebuilt, paper_pnl_report_to_dict):
            raise _fail("close_pnl_report_not_reconstructed")
        if rebuilt.status is not PaperPnlReportStatus.COMPUTED:
            raise _fail("close_pnl_report_not_computed")
        proven[day_index] = _ProvenClose(
            day_index=day_index,
            position_digest=paper_position_state_digest(position),
            mark_digest=rebuilt.mark_snapshot_digest,
            report_digest=rebuilt.pnl_report_digest,
            unrealized=_consumed_decimal(rebuilt.unrealized_pnl, "close_unrealized_invalid"),
        )
    return proven


def _prove_funding(
    evidence: object,
    *,
    sleeve_id: str,
    market_symbol: str,
    window_start_ns: int,
    window_end_ns: int,
    genesis: PaperPositionState,
    episodes: tuple[_ProvenEpisode, ...],
) -> tuple[tuple[tuple[int, Fraction], ...], str, int]:
    _require_exact(evidence, PaperSleeveFundingEvidence, "funding_evidence")
    if not verify_paper_sleeve_funding_evidence(evidence).intact:
        raise _fail("funding_evidence_not_intact")
    funding = cast(PaperSleeveFundingEvidence, evidence)
    if funding.sleeve_id != sleeve_id:
        raise _fail("funding_evidence_sleeve_mismatch")
    if funding.market_symbol != market_symbol:
        raise _fail("funding_evidence_market_mismatch")
    if funding.window_start_ns != window_start_ns or funding.window_end_ns != window_end_ns:
        raise _fail("funding_evidence_window_mismatch")
    settlements: list[tuple[int, Fraction]] = []
    for event in funding.events:
        position = _position_before(event.settlement_at_ns, genesis, episodes)
        if event.position_state_digest != paper_position_state_digest(position):
            raise _fail("funding_event_position_mismatch")
        if position.side is PaperPositionStateSide.FLAT:
            raise _fail("funding_event_position_flat")
        settlements.append((event.settlement_at_ns, Fraction(event.funding_amount)))
    return tuple(settlements), funding.funding_evidence_digest, len(settlements)


# --- serialization --------------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in value]
    if type(value) is int:
        if value < 0 or value > _MAX_WIRE_INT:
            raise _fail("payload_integer_out_of_range")
        return value
    if type(value) in (str, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize exactly: an enum field must hold the exact member and every other value an exact builtin or record."""

    enum_fields = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for field in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, field.name)
        enum_cls = enum_fields.get(field.name)
        if enum_cls is None:
            payload[field.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[field.name] = value.value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- valuation ------------------------------------------------------------------------------------------------------


def _value_days(
    *,
    reference: Fraction,
    window_start_ns: int,
    day_count: int,
    episodes: tuple[_ProvenEpisode, ...],
    closes: dict[int, _ProvenClose],
    settlements: tuple[tuple[int, Fraction], ...],
    lineage_digest: str,
) -> tuple[tuple[PaperSleeveDayValuation, ...], list[str]]:
    days: list[PaperSleeveDayValuation] = []
    previous_equity = reference
    index_start = Fraction(1)
    index_start_text = "1"
    for day_index in range(day_count):
        bucket_start = window_start_ns + day_index * _DAY_NS
        bucket_end = bucket_start + _DAY_NS
        close = closes[day_index]
        realized = sum(
            (episode.realized for episode in episodes if episode.fill_observed_at_ns < bucket_end), Fraction(0)
        )
        fees = sum((episode.fee for episode in episodes if episode.fill_observed_at_ns < bucket_end), Fraction(0))
        funding = sum((amount for instant, amount in settlements if instant < bucket_end), Fraction(0))
        equity = reference + realized - fees + close.unrealized + funding
        if equity <= 0:
            return (), [_reason(f"paper_performance_basis_not_positive:{day_index}")]
        daily_return = _render_half_even(equity / previous_equity - 1)
        growth = 1 + daily_return
        if growth <= 0:
            return (), [_reason(f"rendered_growth_not_positive:{day_index}")]
        index_end = index_start * growth
        rendered = [
            _render(value, _MAX_INDEX_TEXT)
            for value in (realized, fees, funding, close.unrealized, equity, daily_return, index_end)
        ]
        if any(text is None for text in rendered):
            return (), [_reason(f"normalized_index_representation_bound_exceeded:{day_index}")]
        texts = cast(list[str], rendered)
        realized_text, fees_text, funding_text, unrealized_text, equity_text, return_text, index_end_text = texts
        bucket_id = f"{_BUCKET_ID_PREFIX}-{day_index}-{lineage_digest}"
        days.append(
            PaperSleeveDayValuation(
                day_index=day_index,
                bucket_start_ns=bucket_start,
                bucket_end_ns=bucket_end,
                close_position_state_digest=close.position_digest,
                close_mark_snapshot_digest=close.mark_digest,
                close_pnl_report_digest=close.report_digest,
                cumulative_realized=realized_text,
                cumulative_fees=fees_text,
                cumulative_funding=funding_text,
                close_unrealized=unrealized_text,
                equity_basis=equity_text,
                daily_return=return_text,
                normalized_index_start=index_start_text,
                normalized_index_end=index_end_text,
                bucket_id=bucket_id,
                bucket_digest=_bucket_digest(bucket_id, bucket_start, bucket_end, index_start_text, index_end_text),
            )
        )
        previous_equity = equity
        index_start = index_end
        index_start_text = index_end_text
    return tuple(days), []


def build_paper_sleeve_daily_valuation_evidence(
    inputs: PaperSleeveValuationInputs,
) -> PaperSleeveDailyValuationEvidence:
    """Value one sleeve's re-proven paper episodes per UTC day under its verified equity-basis policy.

    Malformed input and every provenance defect raise ``PaperSleeveDailyValuationError``. Missing governance or
    evidence yields ``NOT_COMPUTABLE`` with sorted reasons and no day valuations; nothing is fabricated or defaulted.
    Inputs are read once and never mutated.
    """

    _require_exact(inputs, PaperSleeveValuationInputs, "inputs")
    valuation_id = _require_text(inputs.valuation_id, "valuation_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    window_start = _require_int(inputs.window_start_ns, "window_start_ns", minimum=0)
    window_end = _require_int(inputs.window_end_ns, "window_end_ns", minimum=0)
    if window_start % _DAY_NS != 0 or window_end % _DAY_NS != 0 or window_end <= window_start:
        raise _fail("window_not_utc_day_aligned")
    day_count = (window_end - window_start) // _DAY_NS

    policy = inputs.equity_basis_policy
    _require_exact(policy, PaperSleeveEquityBasisPolicy, "equity_basis_policy")
    if not verify_paper_sleeve_equity_basis_policy(policy).intact:
        raise _fail("equity_basis_policy_not_intact")
    if policy.rule_set_digest != PAPER_SLEEVE_EQUITY_BASIS_RULE_SET_DIGEST:
        raise _fail("equity_basis_rule_set_unsupported")

    episode_items = _snapshot(inputs.episodes, "episodes")
    if not episode_items:
        raise _fail("episodes_missing")
    proven = tuple(
        _prove_episode(item, window_start_ns=window_start, window_end_ns=window_end) for item in episode_items
    )
    _prove_chain(proven)
    sleeve_id = proven[0].sleeve_id
    market_symbol = proven[0].market_symbol
    if policy.sleeve_id != sleeve_id:
        raise _fail("equity_basis_policy_sleeve_mismatch")
    if policy.market_symbol != market_symbol:
        raise _fail("equity_basis_policy_market_mismatch")
    genesis = proven[0].prior_state

    closes = _prove_day_closes(
        inputs.day_closes,
        window_start_ns=window_start,
        day_count=day_count,
        market_symbol=market_symbol,
        genesis=genesis,
        episodes=proven,
    )

    blocking: list[str] = []
    settlements: tuple[tuple[int, Fraction], ...] = ()
    funding_digest = ""
    funding_count = 0
    funding_evidence = inputs.funding_evidence
    if policy.funding_treatment is PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED:
        if funding_evidence is None:
            blocking.append(_reason("funding_evidence_missing"))
        else:
            settlements, funding_digest, funding_count = _prove_funding(
                funding_evidence,
                sleeve_id=sleeve_id,
                market_symbol=market_symbol,
                window_start_ns=window_start,
                window_end_ns=window_end,
                genesis=genesis,
                episodes=proven,
            )
    elif funding_evidence is not None:
        raise _fail("funding_evidence_supplied_under_governed_not_applicable")
    if policy.advances is not True:
        blocking.append(_reason("equity_basis_policy_not_governed"))
    blocking.extend(_reason(f"day_close_missing:{day}") for day in range(day_count) if day not in closes)

    lineage_digest = edge_sha256_text(
        edge_canonical_json(
            {
                "sleeve_id": sleeve_id,
                "market_symbol": market_symbol,
                "equity_basis_policy_digest": policy.policy_digest,
                "equity_basis_rule_set_digest": policy.rule_set_digest,
                "window_start_ns": window_start,
                "window_end_ns": window_end,
                "episode_digests": [episode.record.episode_digest for episode in proven],
                "funding_evidence_digest": funding_digest,
            }
        )
    )
    days: tuple[PaperSleeveDayValuation, ...] = ()
    if not blocking:
        days, blocking = _value_days(
            reference=Fraction(policy.paper_performance_reference_notional),
            window_start_ns=window_start,
            day_count=day_count,
            episodes=proven,
            closes=closes,
            settlements=settlements,
            lineage_digest=lineage_digest,
        )
    reasons = tuple(sorted(set(blocking)))
    status = PaperSleeveValuationStatus.NOT_COMPUTABLE if reasons else PaperSleeveValuationStatus.COMPUTED
    seed = PaperSleeveDailyValuationEvidence(
        schema_version=_SCHEMA_VERSION,
        status=status,
        computed=status is PaperSleeveValuationStatus.COMPUTED,
        valuation_id=valuation_id,
        correlation_id=correlation_id,
        sleeve_id=sleeve_id,
        market_symbol=market_symbol,
        equity_basis_policy_id=policy.policy_id,
        equity_basis_policy_version=policy.policy_version,
        equity_basis_policy_digest=policy.policy_digest,
        equity_basis_digest=policy.equity_basis_digest,
        equity_basis_rule_set_digest=policy.rule_set_digest,
        equity_basis_policy_advances=policy.advances,
        paper_performance_reference_notional=policy.paper_performance_reference_notional,
        funding_treatment=policy.funding_treatment,
        funding_evidence_digest=funding_digest,
        funding_event_count=funding_count,
        window_start_ns=window_start,
        window_end_ns=window_end,
        day_count=day_count,
        capacity_decision_digests=tuple(sorted({episode.record.capacity_decision_digest for episode in proven})),
        episode_count=len(proven),
        episodes=tuple(episode.record for episode in proven),
        day_close_count=len(closes),
        lineage_digest=lineage_digest,
        days=days,
        reason_codes=reasons,
        valuation_digest="",
    )
    return replace(seed, valuation_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def paper_sleeve_daily_valuation_evidence_to_dict(evidence: PaperSleeveDailyValuationEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the valuation evidence, including its self-digest."""

    return _to_payload(evidence)


def paper_sleeve_daily_valuation_evidence_digest(evidence: PaperSleeveDailyValuationEvidence) -> str:
    """Recompute the canonical valuation digest, excluding only ``valuation_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def paper_sleeve_daily_return_buckets(
    evidence: PaperSleeveDailyValuationEvidence,
) -> tuple[PaperDailyReturnBucket, ...]:
    """Adapter: the exact accepted daily-return buckets of a COMPUTED valuation, after re-proving its digest."""

    if type(evidence) is not PaperSleeveDailyValuationEvidence:
        raise _fail("evidence_malformed")
    try:
        recomputed = paper_sleeve_daily_valuation_evidence_digest(evidence)
    except Exception as exc:  # noqa: BLE001 - an evidence that cannot serialize canonically emits nothing
        raise _fail("evidence_not_canonical") from exc
    if recomputed != evidence.valuation_digest:
        raise _fail("valuation_digest_mismatch")
    if evidence.status is not PaperSleeveValuationStatus.COMPUTED or not evidence.days:
        raise _fail("valuation_not_computed")
    buckets: list[PaperDailyReturnBucket] = []
    for day in evidence.days:
        digest = _bucket_digest(
            day.bucket_id, day.bucket_start_ns, day.bucket_end_ns, day.normalized_index_start, day.normalized_index_end
        )
        if digest != day.bucket_digest:
            raise _fail("bucket_digest_mismatch")
        buckets.append(
            PaperDailyReturnBucket(
                bucket_id=day.bucket_id,
                bucket_start_ns=day.bucket_start_ns,
                bucket_end_ns=day.bucket_end_ns,
                normalized_index_start=day.normalized_index_start,
                normalized_index_end=day.normalized_index_end,
                bucket_digest=day.bucket_digest,
            )
        )
    return tuple(buckets)


def verify_paper_sleeve_daily_valuation_evidence(
    evidence: object, inputs: PaperSleeveValuationInputs
) -> EdgeEvidenceVerification:
    """Re-prove a valuation evidence by rebuilding it from its exact inputs. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not PaperSleeveDailyValuationEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _to_payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _SELF_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _to_payload(build_paper_sleeve_daily_valuation_evidence(inputs))
        codes: set[str] = set()
        if carried[_SELF_DIGEST_FIELD] != recomputed:
            codes.add(_reason("self_digest_mismatch"))
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
    "PAPER_SLEEVE_DAILY_VALUATION_NON_CLAIM_FLAGS",
    "PaperSleeveDailyValuationError",
    "PaperSleeveDailyValuationEvidence",
    "PaperSleeveDayCloseValuation",
    "PaperSleeveDayValuation",
    "PaperSleeveEpisodeEvidence",
    "PaperSleeveEpisodeValuation",
    "PaperSleeveValuationInputs",
    "PaperSleeveValuationStatus",
    "build_paper_sleeve_daily_valuation_evidence",
    "paper_sleeve_daily_return_buckets",
    "paper_sleeve_daily_valuation_evidence_digest",
    "paper_sleeve_daily_valuation_evidence_to_dict",
    "verify_paper_sleeve_daily_valuation_evidence",
]
