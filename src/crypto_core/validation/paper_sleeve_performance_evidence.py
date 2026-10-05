"""RG-3 per-sleeve paper performance evidence (RG3_SLEEVE_PERFORMANCE_PROVENANCE_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-3). This artifact is the deterministic paper
performance snapshot of ONE sleeve. It reuses the accepted generic substrate: the daily-return series and the paper
Sharpe evidence, with day-index alignment preserved. It contains no sleeve label assertion and no self-sealed value.
It is paper-only, deterministic, digest-bound and fail-closed.

Binding, every element re-proven:

* RG-2: the ``PaperPortfolioRiskEnvelope`` is re-pinned through its total verifier, and must declare this sleeve and
  this market. The envelope's performance measure must be the paper Sharpe this artifact carries;
* valuation: the ``PaperSleeveDailyValuationEvidence`` is REBUILT from its exact inputs and must equal the supplied
  evidence. That re-proves the capacity-derived sleeve identity, every episode hop, every day close, the funding
  binding and the verified ``PaperSleeveEquityBasisPolicy``;
* methodology: the series' methodology must declare exactly the policy identifiers derived from that basis policy,
  so the generic series is bound to this exact basis;
* time window: the ``PaperDeterministicTimeWindowEvidence`` is REBUILT by its accepted producer from the supplied
  source ``PaperSessionMetricsSummary``, the producer input the window itself only references by digest. The summary
  anchor is that summary's recomputed public digest, never a digest the window carries. The injected window (bounds,
  ids, sample count) is re-validated by the producer against the summary, and the supplied window must equal the
  reconstruction canonically. Only that reconstruction reaches the series builder;
* series: the ``PaperDailyReturnSeriesEvidence`` is REBUILT by the accepted public builder over the exact buckets the
  valuation emits, and must equal the supplied series. Its correlation and market must equal the valuation's;
* Sharpe: the ``PaperSharpeEvidence`` is REBUILT by the accepted public builder over that series, and must equal the
  supplied evidence.

Status precedence:

* ``NEEDS_GOVERNANCE_APPROVAL`` when the envelope or the basis policy does not advance;
* otherwise ``NOT_COMPUTABLE`` when the valuation is blocked, the series inputs are not supplied, the series is
  rejected, or the Sharpe is not computed. The accepted sample semantics are retained, never overridden;
* otherwise ``READY``.

Performance values (the daily returns and both paper Sharpe ratios) are carried only when ``READY``. Every other state
carries the bound digests and statuses, but no value.

Any provenance or binding defect raises ``PaperSleevePerformanceEvidenceError``. Reasons are sorted and propagate
upstream codes unchanged. ``verify_paper_sleeve_performance_evidence`` re-proves an evidence by rebuilding it and is
total.

Non-overclaim. A READY snapshot decides NO promotion or demotion, NO allocation and NO portfolio stop. It selects no
governance threshold and claims no profitability, edge, statistical significance or readiness. The generic series'
time-window / metrics-summary session context is not claimed to be sleeve-scoped: only the values and the window are,
through the rebuilt buckets. That context must still be its accepted producer's exact output. Mark, instant and
funding origins and the completeness of the sleeve's episode set stay unproven, and no current lifecycle head is
consumed. Exact arithmetic, no float, no ``decimal`` context, and no IO, clock, randomness, network or environment
access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
)
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    build_paper_daily_return_series_evidence,
    paper_daily_return_series_evidence_to_dict,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    build_paper_deterministic_time_window_evidence,
    paper_deterministic_time_window_evidence_to_dict,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    paper_portfolio_risk_envelope_rule_set,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_return_series_methodology import PaperReturnSeriesMethodology
from crypto_core.validation.paper_session_metrics_summary import (
    PaperSessionMetricsSummary,
    paper_session_metrics_summary_digest,
)
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidence,
    PaperSharpeEvidenceStatus,
    build_paper_sharpe_evidence,
    paper_sharpe_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDailyValuationEvidence,
    PaperSleeveValuationInputs,
    PaperSleeveValuationStatus,
    build_paper_sleeve_daily_valuation_evidence,
    paper_sleeve_daily_return_buckets,
    paper_sleeve_daily_valuation_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    paper_sleeve_equity_basis_methodology_policy_ids,
    paper_sleeve_equity_basis_rule_set,
)

_SCHEMA_VERSION = "paper-sleeve-performance-evidence.v1"
_REASON_PREFIX = "paper_sleeve_performance_evidence"
_SELF_DIGEST_FIELD = "performance_evidence_digest"
# The wire bounds are read from the equity-basis rule set the bound valuation commits; none is defined here.
_RULES = paper_sleeve_equity_basis_rule_set()
_MAX_TEXT: int = _RULES["max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULES["max_wire_integer"]  # type: ignore[assignment]
PAPER_SLEEVE_PERFORMANCE_MEASURE_ID = "paper-sharpe-evidence.v1:paper_sharpe_annualized"
_T = TypeVar("_T")


class PaperSleevePerformanceEvidenceError(EdgeArtifactError):
    """Raised on malformed input or any provenance or binding defect: an invalid snapshot is never represented."""


class PaperSleevePerformanceStatus(str, Enum):
    """READY only when governed, computed and re-proven end to end; the other states are represented, never values."""

    READY = "READY"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


@dataclass(frozen=True)
class PaperSleevePerformanceInputs:
    """Everything RG-3 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    performance_evidence_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    valuation_inputs: PaperSleeveValuationInputs
    valuation: PaperSleeveDailyValuationEvidence
    methodology: PaperReturnSeriesMethodology | None
    metrics_summary: PaperSessionMetricsSummary | None
    time_window: PaperDeterministicTimeWindowEvidence | None
    daily_return_series: PaperDailyReturnSeriesEvidence | None
    sharpe_evidence: PaperSharpeEvidence | None


PAPER_SLEEVE_PERFORMANCE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("promotion_demotion_decided", False),
    ("portfolio_allocation_approved", False),
    ("portfolio_stop_evaluated", False),
    ("capital_allocated", False),
    ("execution_authorized", False),
    ("governance_threshold_selected", False),
    ("profitability_proven", False),
    ("edge_proven", False),
    ("statistical_significance_proven", False),
    ("account_equity_represented", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("prdv4_stage4_complete", False),
    ("series_session_context_sleeve_proven", False),
    ("episode_set_completeness_proven", False),
    ("mark_price_origin_proven", False),
    ("timestamp_origin_proven", False),
    ("funding_amount_origin_proven", False),
    ("current_lifecycle_head_proven", False),
    ("regime_evidence_available", False),
)


@dataclass(frozen=True)
class PaperSleevePerformanceEvidence:
    """Immutable, digest-bound RG-3 per-sleeve paper performance snapshot. Evidence only; decides nothing."""

    schema_version: str
    status: PaperSleevePerformanceStatus
    ready: bool
    performance_evidence_id: str
    correlation_id: str
    sleeve_id: str
    market_symbol: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    equity_basis_policy_digest: str
    equity_basis_digest: str
    equity_basis_policy_advances: bool
    valuation_digest: str
    valuation_status: str
    window_start_ns: int
    window_end_ns: int
    day_count: int
    methodology_digest: str
    time_window_digest: str
    daily_return_series_digest: str
    daily_return_series_status: str
    sharpe_evidence_digest: str
    sharpe_status: str
    sharpe_computed: bool
    performance_measure_id: str
    daily_returns: tuple[str, ...]
    paper_sharpe_daily: str
    paper_sharpe_annualized: str
    reason_codes: tuple[str, ...]
    performance_evidence_digest: str
    paper_only: bool = True
    promotion_demotion_decided: bool = False
    portfolio_allocation_approved: bool = False
    portfolio_stop_evaluated: bool = False
    capital_allocated: bool = False
    execution_authorized: bool = False
    governance_threshold_selected: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    statistical_significance_proven: bool = False
    account_equity_represented: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    prdv4_stage4_complete: bool = False
    series_session_context_sleeve_proven: bool = False
    episode_set_completeness_proven: bool = False
    mark_price_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    funding_amount_origin_proven: bool = False
    current_lifecycle_head_proven: bool = False
    regime_evidence_available: bool = False


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleevePerformanceEvidenceError:
    return PaperSleevePerformanceEvidenceError(_reason(code))


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


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed at this boundary
        raise _fail(f"{code}_reconstruction_failed") from exc


def _metadata(artifact: object, code: str) -> dict[str, str]:
    try:
        return dict(artifact.metadata)  # type: ignore[attr-defined]
    except Exception as exc:  # noqa: BLE001 - malformed carried metadata cannot be reconstructed
        raise _fail(f"{code}_metadata_malformed") from exc


def _rebuild_time_window(
    summary: PaperSessionMetricsSummary, window: PaperDeterministicTimeWindowEvidence
) -> PaperDeterministicTimeWindowEvidence:
    """Re-run the accepted time-window producer over the supplied source summary and the window's injected values.

    The summary anchor is the recomputed public digest of that summary, never a digest the window carries. The
    injected values (bounds, ids, sample count, metadata) are re-validated by the producer against the summary.
    """

    metadata = _metadata(window, "time_window")
    try:
        expected_summary_digest = paper_session_metrics_summary_digest(summary)
    except Exception as exc:  # noqa: BLE001 - an unreadable producer input fails closed at this boundary
        raise _fail("time_window_reconstruction_failed") from exc
    return _rebuild(
        "time_window",
        build_paper_deterministic_time_window_evidence,
        summary,
        expected_metrics_summary_digest=expected_summary_digest,
        started_at_ns=window.started_at_ns,
        stopped_at_ns=window.stopped_at_ns,
        window_id=window.window_id,
        methodology_id=window.methodology_id,
        run_id=window.run_id,
        aggregate_id=window.aggregate_id,
        correlation_id=window.correlation_id,
        sample_observation_count=window.sample_observation_count,
        metadata=metadata,
    )


def _serialize(value: object) -> object:
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
    """Serialize exactly: ``status`` must hold the exact member and every other value an exact builtin or tuple."""

    payload: dict[str, object] = {}
    for field in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, field.name)
        if field.name != "status":
            payload[field.name] = _serialize(value)
        elif type(value) is PaperSleevePerformanceStatus:
            payload[field.name] = value.value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- assembly -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _SeriesBinding:
    methodology_digest: str
    time_window_digest: str
    series_digest: str
    series_status: str
    sharpe_digest: str
    sharpe_status: str
    sharpe_computed: bool
    daily_returns: tuple[str, ...]
    sharpe_daily: str
    sharpe_annualized: str
    reasons: tuple[str, ...]


def _bind_series(
    inputs: PaperSleevePerformanceInputs, valuation: PaperSleeveDailyValuationEvidence
) -> _SeriesBinding | None:
    """Rebuild the generic series and Sharpe over the valuation buckets; ``None`` when none is supplied."""

    supplied = (
        inputs.methodology,
        inputs.metrics_summary,
        inputs.time_window,
        inputs.daily_return_series,
        inputs.sharpe_evidence,
    )
    if all(item is None for item in supplied):
        return None
    if any(item is None for item in supplied):
        raise _fail("series_inputs_incomplete")
    _require_exact(inputs.methodology, PaperReturnSeriesMethodology, "methodology")
    _require_exact(inputs.metrics_summary, PaperSessionMetricsSummary, "metrics_summary")
    _require_exact(inputs.time_window, PaperDeterministicTimeWindowEvidence, "time_window")
    _require_exact(inputs.daily_return_series, PaperDailyReturnSeriesEvidence, "daily_return_series")
    _require_exact(inputs.sharpe_evidence, PaperSharpeEvidence, "sharpe_evidence")
    methodology = cast(PaperReturnSeriesMethodology, inputs.methodology)
    summary = cast(PaperSessionMetricsSummary, inputs.metrics_summary)
    supplied_window = cast(PaperDeterministicTimeWindowEvidence, inputs.time_window)
    series = cast(PaperDailyReturnSeriesEvidence, inputs.daily_return_series)
    sharpe = cast(PaperSharpeEvidence, inputs.sharpe_evidence)

    expected_ids = paper_sleeve_equity_basis_methodology_policy_ids(inputs.valuation_inputs.equity_basis_policy)
    for name, expected in expected_ids.items():
        if getattr(methodology, name) != expected:
            raise _fail("methodology_not_bound_to_equity_basis_policy")

    # Only the producer's reconstruction over the supplied metrics summary reaches the series builder.
    time_window = _rebuild_time_window(summary, supplied_window)
    if not _canonically_equal(supplied_window, time_window, paper_deterministic_time_window_evidence_to_dict):
        raise _fail("time_window_not_reconstructed")

    rebuilt_series = _rebuild(
        "daily_return_series",
        build_paper_daily_return_series_evidence,
        methodology,
        time_window,
        expected_methodology_digest=methodology.methodology_digest,
        expected_time_window_digest=time_window.time_window_digest,
        series_id=series.series_id,
        correlation_id=series.correlation_id,
        daily_buckets=paper_sleeve_daily_return_buckets(valuation),
        metadata=_metadata(series, "daily_return_series"),
    )
    if not _canonically_equal(series, rebuilt_series, paper_daily_return_series_evidence_to_dict):
        raise _fail("daily_return_series_not_reconstructed")
    if rebuilt_series.correlation_id != valuation.correlation_id:
        raise _fail("daily_return_series_correlation_mismatch")
    if rebuilt_series.market_symbol != valuation.market_symbol:
        raise _fail("daily_return_series_market_mismatch")

    rebuilt_sharpe = _rebuild(
        "sharpe_evidence",
        build_paper_sharpe_evidence,
        rebuilt_series,
        expected_daily_return_series_digest=rebuilt_series.series_digest,
        risk_free_policy_id=sharpe.risk_free_policy_id,
        sharpe_evidence_id=sharpe.sharpe_evidence_id,
        paper_id=sharpe.paper_id,
        correlation_id=sharpe.correlation_id,
        metadata=_metadata(sharpe, "sharpe_evidence"),
    )
    if not _canonically_equal(sharpe, rebuilt_sharpe, paper_sharpe_evidence_to_dict):
        raise _fail("sharpe_evidence_not_reconstructed")

    reasons: list[str] = []
    series_ready = rebuilt_series.status is PaperDailyReturnSeriesEvidenceStatus.READY
    if not series_ready:
        reasons.append(_reason("daily_return_series_not_ready"))
        reasons.extend(rebuilt_series.reason_codes)
    elif rebuilt_series.daily_returns != tuple(day.daily_return for day in valuation.days):
        raise _fail("daily_returns_not_valuation_returns")
    sharpe_computed = rebuilt_sharpe.status is PaperSharpeEvidenceStatus.READY and rebuilt_sharpe.sharpe_computed
    if not sharpe_computed:
        reasons.append(_reason("sharpe_not_computed"))
        reasons.extend(rebuilt_sharpe.reason_codes)
    return _SeriesBinding(
        methodology_digest=methodology.methodology_digest,
        time_window_digest=time_window.time_window_digest,
        series_digest=rebuilt_series.series_digest,
        series_status=rebuilt_series.status.value,
        sharpe_digest=rebuilt_sharpe.sharpe_evidence_digest,
        sharpe_status=rebuilt_sharpe.status.value,
        sharpe_computed=sharpe_computed,
        daily_returns=rebuilt_series.daily_returns if series_ready else (),
        sharpe_daily=rebuilt_sharpe.paper_sharpe_daily if sharpe_computed else "",
        sharpe_annualized=rebuilt_sharpe.paper_sharpe_annualized if sharpe_computed else "",
        reasons=tuple(reasons),
    )


def build_paper_sleeve_performance_evidence(inputs: PaperSleevePerformanceInputs) -> PaperSleevePerformanceEvidence:
    """Build the RG-3 per-sleeve performance snapshot from fully re-proven provenance; decides nothing.

    Malformed input and every provenance or binding defect raise ``PaperSleevePerformanceEvidenceError``. Missing
    governance yields ``NEEDS_GOVERNANCE_APPROVAL``; blocked or insufficient evidence yields ``NOT_COMPUTABLE``.
    """

    _require_exact(inputs, PaperSleevePerformanceInputs, "inputs")
    evidence_id = _require_text(inputs.performance_evidence_id, "performance_evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")

    envelope = inputs.portfolio_risk_envelope
    _require_exact(envelope, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(envelope).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    if paper_portfolio_risk_envelope_rule_set()["performance_measure_id"] != PAPER_SLEEVE_PERFORMANCE_MEASURE_ID:
        raise _fail("envelope_performance_measure_unsupported")

    _require_exact(inputs.valuation_inputs, PaperSleeveValuationInputs, "valuation_inputs")
    _require_exact(inputs.valuation, PaperSleeveDailyValuationEvidence, "valuation")
    try:
        rebuilt_valuation = build_paper_sleeve_daily_valuation_evidence(inputs.valuation_inputs)
    except Exception as exc:  # noqa: BLE001 - an unprovable valuation fails closed at this boundary
        raise _fail("valuation_reconstruction_failed") from exc
    if not _canonically_equal(inputs.valuation, rebuilt_valuation, paper_sleeve_daily_valuation_evidence_to_dict):
        raise _fail("valuation_not_reconstructed")
    valuation = rebuilt_valuation
    if valuation.correlation_id != correlation_id:
        raise _fail("valuation_correlation_mismatch")
    if valuation.sleeve_id not in {cap.sleeve_id for cap in envelope.sleeve_caps}:
        raise _fail("sleeve_not_declared_in_envelope")
    if valuation.market_symbol not in {cap.market_symbol for cap in envelope.market_caps}:
        raise _fail("market_not_declared_in_envelope")

    reasons: list[str] = []
    governance_missing = False
    if envelope.advances is not True:
        governance_missing = True
        reasons.append(_reason("portfolio_risk_envelope_not_governed"))
    if valuation.equity_basis_policy_advances is not True:
        governance_missing = True
        reasons.append(_reason("equity_basis_policy_not_governed"))
    computed = valuation.status is PaperSleeveValuationStatus.COMPUTED
    binding: _SeriesBinding | None = None
    if computed:
        binding = _bind_series(inputs, valuation)
        if binding is None:
            reasons.append(_reason("daily_return_series_not_supplied"))
        else:
            reasons.extend(binding.reasons)
    else:
        if any(
            item is not None
            for item in (
                inputs.methodology,
                inputs.metrics_summary,
                inputs.time_window,
                inputs.daily_return_series,
                inputs.sharpe_evidence,
            )
        ):
            raise _fail("series_inputs_supplied_for_uncomputed_valuation")
        reasons.append(_reason("valuation_not_computed"))
        reasons.extend(valuation.reason_codes)

    if governance_missing:
        status = PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    elif reasons:
        status = PaperSleevePerformanceStatus.NOT_COMPUTABLE
    else:
        status = PaperSleevePerformanceStatus.READY
    ready = status is PaperSleevePerformanceStatus.READY
    values = binding if ready else None
    seed = PaperSleevePerformanceEvidence(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        performance_evidence_id=evidence_id,
        correlation_id=correlation_id,
        sleeve_id=valuation.sleeve_id,
        market_symbol=valuation.market_symbol,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        equity_basis_policy_digest=valuation.equity_basis_policy_digest,
        equity_basis_digest=valuation.equity_basis_digest,
        equity_basis_policy_advances=valuation.equity_basis_policy_advances,
        valuation_digest=valuation.valuation_digest,
        valuation_status=valuation.status.value,
        window_start_ns=valuation.window_start_ns,
        window_end_ns=valuation.window_end_ns,
        day_count=valuation.day_count,
        methodology_digest="" if binding is None else binding.methodology_digest,
        time_window_digest="" if binding is None else binding.time_window_digest,
        daily_return_series_digest="" if binding is None else binding.series_digest,
        daily_return_series_status="" if binding is None else binding.series_status,
        sharpe_evidence_digest="" if binding is None else binding.sharpe_digest,
        sharpe_status="" if binding is None else binding.sharpe_status,
        sharpe_computed=False if binding is None else binding.sharpe_computed,
        performance_measure_id=PAPER_SLEEVE_PERFORMANCE_MEASURE_ID,
        daily_returns=() if values is None else values.daily_returns,
        paper_sharpe_daily="" if values is None else values.sharpe_daily,
        paper_sharpe_annualized="" if values is None else values.sharpe_annualized,
        reason_codes=tuple(sorted(set(reasons))),
        performance_evidence_digest="",
    )
    return replace(seed, performance_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def paper_sleeve_performance_evidence_to_dict(evidence: PaperSleevePerformanceEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the snapshot, including its self-digest."""

    return _to_payload(evidence)


def paper_sleeve_performance_evidence_digest(evidence: PaperSleevePerformanceEvidence) -> str:
    """Recompute the canonical snapshot digest, excluding only ``performance_evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def verify_paper_sleeve_performance_evidence(
    evidence: object, inputs: PaperSleevePerformanceInputs
) -> EdgeEvidenceVerification:
    """Re-prove a snapshot by rebuilding it from its exact inputs. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not PaperSleevePerformanceEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _to_payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _SELF_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _to_payload(build_paper_sleeve_performance_evidence(inputs))
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
    "PAPER_SLEEVE_PERFORMANCE_MEASURE_ID",
    "PAPER_SLEEVE_PERFORMANCE_NON_CLAIM_FLAGS",
    "PaperSleevePerformanceEvidence",
    "PaperSleevePerformanceEvidenceError",
    "PaperSleevePerformanceInputs",
    "PaperSleevePerformanceStatus",
    "build_paper_sleeve_performance_evidence",
    "paper_sleeve_performance_evidence_digest",
    "paper_sleeve_performance_evidence_to_dict",
    "verify_paper_sleeve_performance_evidence",
]
