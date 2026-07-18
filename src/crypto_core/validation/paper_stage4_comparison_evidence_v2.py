"""Deterministic paper Stage-4 comparison evidence v2 (SM-6, real enforced secondary metrics).

This validation artifact is the SECOND authorized ``compare_stage4`` caller and the FIRST artifact allowed
to set ``secondary_metrics_enforced=True``. It supersedes the v1 comparison evidence's placeholder path
(``paper_hit_rate=None`` / ``paper_fill_rate=None`` / ``paper_slippage_bps=None`` / ``paper_trade_count=0``)
by consuming the REAL merged secondary-metrics chain at digest boundaries:

* the five v1-lineage anchors — ``PaperSharpeEvidence``, ``PaperEdgeIdentityEvidence``,
  ``PaperStage4BacktestBaselineEvidence``, ``PaperThirtyDayEvidenceGateDecision`` and the caller-supplied
  ``Stage4BacktestBaseline`` (triple digest equality: recompute == caller anchor == the digest bound inside
  the baseline evidence) — with ``PaperVsBacktestMethodologyV2`` REPLACING the v1 methodology anchor;
* the SM trust roots — the SAME ``PaperSecondaryMetricsEnforcementPrecondition`` the merged methodology-v2
  bound (``methodology_v2.verified_secondary_metrics_enforcement_precondition_digest`` must equal the
  precondition self-digest) and the direct real ``PaperSecondaryMetricsEvidence`` (SM-4), with the mandatory
  canonical equality ``precondition.metrics_evidence_digest == metrics_evidence.evidence_digest``.

Enforcement ownership: the approved hit-rate floor, BOTH fill-rate floors (by intended quantity AND by
episode — the SM-2 dual definition; the aggregate is their conjunction), the slippage ceiling, and the
minimum decided-episode count are REAPPLIED HERE in ``Decimal`` (precision 80, ROUND_HALF_EVEN) from the
direct SM-4 canonical scale-18 values against the methodology-v2 digest-bound approved thresholds. Carried
pass booleans are never trusted (recompute mismatch fails closed with ``threshold_pass_incoherent``);
``compare_stage4`` remains an advisory float echo that never enforces secondary-metric thresholds; any
required real secondary metric that is ``None`` or noncanonical is REJECTED (``missing_secondary_metric``)
— the SM-5 vacuous ``None``-slippage pass and the v1 zero placeholder are both structurally impossible on a
READY v2 artifact. ``secondary_metrics_enforced`` is True ONLY on a fully proven READY artifact.

Comparator echo transparency: the internally constructed ``Stage4PaperSummary`` feeds the REAL metrics —
``paper_trade_count`` is the SM-4 record count (``paper_trade_count_source="secondary_metrics_record_count.v2"``),
the single comparator fill-rate slot carries the conservative minimum of the two enforced fill rates
(``comparator_fill_rate_echo_policy``), and the signed SM-4 slippage is echoed as a float only when
non-negative (the comparator input contract accepts only non-negative-or-None slippage); a favorable signed
slippage is enforced and digest-bound here and echoed as ``None``
(``comparator_slippage_echo_policy``). The Decimal Sharpe-retention recompute remains the AUTHORITATIVE
verdict exactly as in v1; Decimal/float verdict disagreement fails closed.

It does NOT decide the >=30-day gate (consumed only; ``thirty_day_gate_decided=False``), does NOT decide
Stage-4 completion (only the future completion v3 may discharge
``secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1`` by consuming this artifact's
digest), does NOT prove machine-time or timestamp origin, edge, profitability, backtest validity, or
live/shadow/Deribit/operational readiness, and calls no wall-clock, runtime, service, execution, venue,
scheduler, filesystem, network, order, capital, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    PaperThirtyDayEvidenceGateDecisionStatus,
    paper_30day_evidence_gate_decision_digest,
)
from crypto_core.validation.paper_edge_identity_evidence import (
    PaperEdgeIdentityEvidence,
    PaperEdgeIdentityEvidenceStatus,
    paper_edge_identity_evidence_digest,
)
from crypto_core.validation.paper_secondary_metrics_enforcement_precondition import (
    PaperSecondaryMetricsEnforcementPrecondition,
    PaperSecondaryMetricsEnforcementPreconditionStatus,
    paper_secondary_metrics_enforcement_precondition_digest,
)
from crypto_core.validation.paper_secondary_metrics_evidence import (
    PaperSecondaryMetricsEvidence,
    PaperSecondaryMetricsEvidenceStatus,
    paper_secondary_metrics_evidence_digest,
)
from crypto_core.validation.paper_sharpe_evidence import (
    PaperSharpeEvidence,
    PaperSharpeEvidenceStatus,
    paper_sharpe_evidence_digest,
)
from crypto_core.validation.paper_stage4_backtest_baseline_evidence import (
    PaperStage4BacktestBaselineEvidence,
    PaperStage4BacktestBaselineEvidenceStatus,
    paper_stage4_backtest_baseline_evidence_digest,
)
from crypto_core.validation.paper_vs_backtest_methodology_v2 import (
    PaperVsBacktestMethodologyV2,
    PaperVsBacktestMethodologyV2Status,
    paper_vs_backtest_methodology_v2_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4ComparisonResult,
    Stage4PaperSummary,
    compare_stage4,
    stage4_backtest_baseline_to_dict,
    stage4_paper_summary_to_dict,
)

_SCHEMA_VERSION = "paper-stage4-comparison-evidence.v2"
_EVIDENCE_VERSION = "paper-stage4-comparison-evidence.v2"
_REASON_PREFIX = "paper_stage4_comparison_evidence_v2"

_EXPECTED_SHARPE_SCHEMA_VERSION = "paper-sharpe-evidence.v1"
_EXPECTED_METHODOLOGY_V2_SCHEMA_VERSION = "paper-vs-backtest-methodology.v2"
_EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION = "paper-edge-identity-evidence.v1"
_EXPECTED_BASELINE_EVIDENCE_SCHEMA_VERSION = "paper-stage4-backtest-baseline-evidence.v1"
_EXPECTED_GATE_SCHEMA_VERSION = "paper-30day-evidence-gate-decision.v1"
_EXPECTED_PRECONDITION_SCHEMA_VERSION = "paper-secondary-metrics-enforcement-precondition.v1"
_EXPECTED_METRICS_SCHEMA_VERSION = "paper-secondary-metrics-evidence.v1"
_EXPECTED_COMPARISON_BASIS = "paper_vs_backtest_sharpe_retention.v1"
_EXPECTED_ENFORCED_GUARDRAIL_POLICY = "sharpe_retention_and_min_duration_only.v1"
# Consumer-boundary re-pin of the approved comparison governance (mirrors the merged methodology-v2 builder
# constants): a resealed, digest-self-consistent methodology carrying a weakened threshold or duration must
# fail closed HERE — the verdict is never re-parameterized by a forgeable policy field alone.
_APPROVED_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_APPROVED_MIN_DURATION_DAYS = 30
_EDGE_ID_FORM = "hex64_sha256"
_EDGE_ID_DERIVATION_POLICY = "sha256_canonical_strategy_id_market_symbol.v1"

_RETENTION_VERDICT_POLICY_ID = "decimal_retention_recompute_authoritative.v1"
_BASELINE_SHARPE_CONVERSION_POLICY = "float_repr_decimal_conversion.v1"
_SHARPE_COMPARABILITY_BASIS = "policy_declared_not_reproven"
# v2 replaces the v1 ``not_carried_zero_placeholder.v1``: the comparator input trade count is the digest-
# proven SM-4 record count, and the enforced secondary metrics are the SM-4 canonical scale-18 values.
_PAPER_TRADE_COUNT_SOURCE = "secondary_metrics_record_count.v2"
_SECONDARY_METRICS_SOURCE = "direct_sm4_evidence_decimal_reapplied.v2"
_COMPARATOR_FILL_RATE_ECHO_POLICY = "min_of_quantity_and_episode_fill_rates.v1"
_COMPARATOR_SLIPPAGE_ECHO_POLICY = "non_negative_float_echo_or_none_signed_enforced_in_v2.v1"
_EXPECTED_SM_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
_EXPECTED_HIT_RATE_OPERATOR = ">="
_EXPECTED_FILL_RATE_OPERATOR = ">="
_EXPECTED_SLIPPAGE_OPERATOR = "<="
_RETENTION_COMPARISON_OPERATOR = ">="
_VERDICT_SATISFIED = "RETENTION_SATISFIED"
_VERDICT_NOT_SATISFIED = "RETENTION_NOT_SATISFIED"
_VERDICT_NOT_EVALUATED = ""

_COMPARATOR_STATUS_PASS = "PASS"  # noqa: S105 - status label, not a credential.
_COMPARATOR_STATUS_REJECT = "REJECT"  # noqa: S105 - status label, not a credential.
_COMPARATOR_BELOW_THRESHOLD_REASON = "stage4:paper_sharpe_below_backtest_threshold"

_DAY_NS = 86_400_000_000_000
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
_DECIMAL_QUANTUM = Decimal(1).scaleb(-_DECIMAL_SCALE)
_NEGATIVE_ZERO_SCALE18 = "-0.000000000000000000"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_SCALE18_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")
# Hard cap on the characters of a consumed scale-18 decimal string: a digest-valid but resealed artifact
# could carry a canonical-but-pathologically-long value. The cap bounds the integer part so every scale-18
# quantization stays inside the precision-80 Decimal context and oversize values fail closed with a
# deterministic reason instead of raising during quantization.
_MAX_SCALE18_DECIMAL_LENGTH = 60
# Magnitude bounds for the caller-supplied baseline Sharpe float (after finite/positive checks): outside
# [1e-18, 1e18] the scale-18 quantizations of the baseline and of the retention ratio could exceed the
# precision-80 context. Deterministic rejection, never a Decimal exception.
_MIN_BACKTEST_SHARPE_DECIMAL = Decimal("1E-18")
_MAX_BACKTEST_SHARPE_DECIMAL = Decimal("1E+18")
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"capital|margin|balance|reservation|real_account_equity|account_equity|real_equity)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
_CLOCK_TOKENS = (
    "wall_clock",
    "wall-clock",
    "wallclock",
    "datetime.now",
    "datetime.utcnow",
    "utcnow",
    "time.time_ns",
    "time.time",
    "perf_counter",
    "monotonic",
    "server_time",
    "exchange_time",
    "live_time",
    "real_time",
    "realtime",
    "system_time",
    "clock",
    "now()",
)


class PaperStage4ComparisonEvidenceV2Error(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata / tokens)."""


class PaperStage4ComparisonEvidenceV2Status(str, Enum):
    """Comparison evidence v2 status. READY is never Stage-4 completion — only a trusted comparison record."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperStage4ComparisonEvidenceV2:
    """Immutable, digest-bound paper Stage-4 comparison evidence v2 (real enforced secondary metrics).

    ``status=READY`` only when every consumed artifact re-proves its digest, the chain cross-binds into ONE
    chain (including ``precondition.metrics_evidence_digest == metrics_evidence.evidence_digest`` and the
    methodology-v2 precondition binding), every required real secondary metric is present and canonical, the
    approved thresholds are independently re-cleared in Decimal, the Decimal Sharpe-retention verdict is
    computed, ``compare_stage4`` was invoked exactly once as an advisory echo, and the Decimal and float
    verdicts agree. ``secondary_metrics_enforced`` is True ONLY on that fully proven READY path.
    ``comparison_verdict`` carries the retention outcome (``RETENTION_SATISFIED`` |
    ``RETENTION_NOT_SATISFIED``) and is meaningful only when READY. READY / RETENTION_SATISFIED do NOT mean
    Stage-4 completion, gate decision, machine-time proof, edge, profitability, backtest validity,
    live/shadow/Deribit/operational readiness, or execution of any kind; only the future completion v3 may
    decide Stage-4 completion by consuming this artifact's digest.
    """

    schema_version: str
    evidence_version: str
    status: PaperStage4ComparisonEvidenceV2Status
    ready: bool
    comparison_evidence_id: str
    correlation_id: str
    paper_id: str
    series_id: str
    window_id: str
    market_symbol: str
    paper_edge_id: str
    baseline_id: str
    strategy_id: str
    strategy_version: str
    strategy_family: str
    edge_family: str
    market_type: str
    secondary_metrics_policy_id: str
    metrics_evidence_id: str
    enforcement_precondition_id: str
    methodology_v2_id: str
    expected_sharpe_evidence_digest: str
    verified_sharpe_evidence_digest: str
    expected_methodology_v2_digest: str
    verified_methodology_v2_digest: str
    expected_edge_identity_digest: str
    verified_edge_identity_digest: str
    expected_baseline_evidence_digest: str
    verified_baseline_evidence_digest: str
    expected_gate_decision_digest: str
    verified_gate_decision_digest: str
    expected_enforcement_precondition_digest: str
    verified_enforcement_precondition_digest: str
    expected_metrics_evidence_digest: str
    verified_metrics_evidence_digest: str
    verified_secondary_metrics_policy_digest: str
    expected_baseline_digest: str
    baseline_digest: str
    paper_summary_digest: str
    series_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    series_methodology_digest: str
    paper_sharpe_annualized: str
    backtest_sharpe_repr: str
    backtest_sharpe_decimal: str
    sharpe_retention_ratio_decimal: str
    sharpe_retention_threshold: str
    retention_comparison_operator: str
    sharpe_retention_satisfied: bool
    min_duration_days: int
    window_duration_ns: int
    bucket_count: int
    duration_satisfied: bool
    comparison_verdict: str
    paper_hit_rate: str | None
    paper_fill_rate_by_quantity: str | None
    paper_fill_rate_by_episode: str | None
    paper_slippage_bps: str | None
    decided_episode_count: int
    record_count: int
    approved_hit_rate_floor: str | None
    approved_fill_rate_floor: str | None
    approved_slippage_ceiling_bps: str | None
    approved_min_decided_episode_count: int | None
    hit_rate_operator: str
    fill_rate_operator: str
    slippage_operator: str
    hit_rate_floor_satisfied: bool
    fill_rate_by_quantity_floor_satisfied: bool
    fill_rate_by_episode_floor_satisfied: bool
    fill_rate_floor_satisfied: bool
    slippage_ceiling_satisfied: bool
    min_decided_episode_count_satisfied: bool
    secondary_thresholds_cleared: bool
    secondary_metrics_source: str
    comparator_fill_rate_echo_policy: str
    comparator_slippage_echo_policy: str
    risk_free_policy_id: str
    annualization_factor: int
    annualization_policy: str
    stddev_policy: str
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    secondary_metrics_decimal_policy: str
    retention_verdict_policy_id: str
    baseline_sharpe_conversion_policy: str
    sharpe_comparability_basis: str
    paper_trade_count: int
    paper_trade_count_source: str
    stage4_comparator_invoked: bool
    comparison_performed: bool
    comparator_status_echo: str
    comparator_evaluated_echo: bool
    comparator_passed_echo: bool
    comparator_sharpe_retention_ratio_echo: str
    comparator_required_min_paper_sharpe_echo: str
    comparator_rejection_reasons_echo: tuple[str, ...]
    comparator_float_advisory_only: bool
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    comparison_evidence_digest: str
    paper_only: bool = True
    thresholds_reapplied_here_not_by_comparator: bool = True
    secondary_metrics_enforced: bool = False
    methodology_v2_consumed: bool = False
    enforcement_precondition_consumed: bool = False
    metrics_evidence_consumed: bool = False
    prdv4_stage4_complete: bool = False
    stage4_completion_decided: bool = False
    thirty_day_gate_decided: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    drawdown_ceiling_enforced: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    same_edge_as_backtest_proven: bool = False
    backtest_validity_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    operational_readiness: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_fills_used: bool = False
    authoritative_pnl: bool = False
    capital_mutation_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_wall_clock_used: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_positive_int(value: object) -> bool:
    return _is_exact_int(value) and value > 0


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and not isinstance(value, bool) and math.isfinite(value)


def _is_rate(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= float(value) <= 1.0


def _is_non_negative_optional_number(value: object) -> bool:
    return value is None or (_is_finite_number(value) and float(value) >= 0.0)


def _is_optional_rate(value: object) -> bool:
    return value is None or _is_rate(value)


def _is_scale18_decimal_string(value: object) -> bool:
    return (
        type(value) is str
        and len(value) <= _MAX_SCALE18_DECIMAL_LENGTH
        and bool(_SCALE18_DECIMAL_PATTERN.fullmatch(value))
        and value != _NEGATIVE_ZERO_SCALE18
    )


def _parse_scale18(value: object) -> Decimal | None:
    if not _is_scale18_decimal_string(value):
        return None
    try:
        parsed = Decimal(value)  # type: ignore[arg-type]
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _scale18_or_none(value: object) -> str | None:
    return value if _is_scale18_decimal_string(value) else None  # type: ignore[return-value]


def _safe_digest_value(value: object) -> str:
    return value if _is_hex64_string(value) else ""


def _safe_int_value(value: object) -> int:
    return value if _is_exact_int(value) else 0


def _safe_optional_int(value: object) -> int | None:
    return value if _is_exact_int(value) else None


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperStage4ComparisonEvidenceV2Error(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperStage4ComparisonEvidenceV2Error(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4ComparisonEvidenceV2Error(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4ComparisonEvidenceV2Error(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperStage4ComparisonEvidenceV2Error(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperStage4ComparisonEvidenceV2Error(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _is_canonical_anchor_metadata(metadata: object) -> bool:
    """Exact canonical-representation check for anchor-carried metadata (validates, never repairs).

    Canonical means: the outer container is exactly ``tuple``; every entry is exactly a two-element
    ``tuple``; every key and value is an exact, non-empty, stripped ``str`` containing no ASCII control or
    DEL character; the tuple is exactly sorted; keys are unique. Anything else fails closed at the consuming
    anchor's canonicality check and is never normalized, repaired, or silently skipped.
    """

    if type(metadata) is not tuple:
        return False
    keys: list[str] = []
    for pair in metadata:
        if type(pair) is not tuple or len(pair) != 2:
            return False
        key, value = pair
        if not _is_plain_non_empty_string(key) or not _is_plain_non_empty_string(value):
            return False
        keys.append(key)
    if len(set(keys)) != len(keys):
        return False
    return list(metadata) == sorted(metadata)


def _derive_paper_edge_id(strategy_id: str, market_symbol: str) -> str:
    """Recompute the approved paper edge-id derivation. Mirrors ``paper_edge_identity_evidence`` exactly."""

    canonical = json.dumps(
        {"strategy_id": strategy_id, "market_symbol": market_symbol},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _format_public_decimal(value: Decimal) -> str:
    """Quantize to exactly ``_DECIMAL_SCALE`` fractional digits with ROUND_HALF_EVEN; normalize signed zero."""

    quantized = value.quantize(_DECIMAL_QUANTUM, rounding=ROUND_HALF_EVEN)
    if quantized == 0:
        quantized = Decimal(0).quantize(_DECIMAL_QUANTUM)
    return format(quantized, "f")


def _decimal_retention_verdict(
    paper_sharpe_annualized: str, backtest_sharpe_repr: str, retention_threshold: str
) -> tuple[str, str, bool]:
    """AUTHORITATIVE Decimal Sharpe-retention verdict — no float arithmetic on this path."""

    with localcontext() as context:
        context.prec = _DECIMAL_INTERNAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        paper_decimal = Decimal(paper_sharpe_annualized)
        backtest_decimal = Decimal(backtest_sharpe_repr)
        threshold_decimal = Decimal(retention_threshold)
        retention_ratio = paper_decimal / backtest_decimal
        satisfied = retention_ratio >= threshold_decimal
        return _format_public_decimal(backtest_decimal), _format_public_decimal(retention_ratio), satisfied


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return None


def _digest_reproof_failures(
    *,
    artifact: object,
    carried_digest: object,
    expected_digest: str,
    compute: object,
    reason_code: str,
) -> tuple[list[str], str]:
    """Recompute the artifact self-digest via its public digest function; require recompute == carried == expected."""

    recomputed = _recomputed_digest_or_none(compute, artifact)
    if (
        recomputed is None
        or not _is_hex64_string(carried_digest)
        or carried_digest != recomputed
        or carried_digest != expected_digest
    ):
        return [_reason(reason_code)], ""
    return [], recomputed


_SHARPE_TRUE_FLAGS = ("paper_only", "daily_return_series_evidence_consumed", "paper_sharpe_evidence")
_SHARPE_FALSE_FLAGS = (
    "return_series_constructed",
    "statistical_significance_proven",
    "sharpe_stable",
    "paper_vs_backtest_comparison_ready",
    "comparison_ready",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "prdv4_stage4_complete",
    "live_ready",
    "shadow_ready",
    "operational_readiness",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)
# Methodology-v2 anchor: the three metric-specific enforced flags, the approval flag, and the consumed
# echoes must be True on the consumed READY snapshot; aggregate enforcement and every completion /
# readiness / execution claim must remain False (the SM-5 boundary keeps ``secondary_metrics_enforced``
# structurally False — only THIS artifact may set its own aggregate flag).
_METHODOLOGY_V2_TRUE_FLAGS = (
    "paper_only",
    "methodology_snapshot",
    "policy_declared",
    "thresholds_approved",
    "hit_rate_floor_enforced",
    "fill_rate_floor_enforced",
    "slippage_ceiling_enforced",
    "predecessor_methodology_consumed",
    "secondary_metrics_policy_consumed",
    "secondary_metrics_enforcement_precondition_consumed",
)
_METHODOLOGY_V2_FALSE_FLAGS = (
    "secondary_metrics_enforced",
    "drawdown_ceiling_enforced",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "comparison_performed",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "edge_identity_proven",
    "production_execution",
    "real_orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)
_EDGE_IDENTITY_TRUE_FLAGS = ("paper_only",)
_EDGE_IDENTITY_FALSE_FLAGS = (
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "same_edge_comparison_ready",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
    "paper_chain_link_cryptographic",
    "paper_chain_spec_digest_carried",
)
_BASELINE_EVIDENCE_TRUE_FLAGS = ("paper_only",)
_BASELINE_EVIDENCE_FALSE_FLAGS = (
    "baseline_constructed",
    "same_edge_as_backtest_proven",
    "backtest_validity_proven",
    "baseline_profitability_proven",
    "edge_proven",
    "profitability_proven",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
    "paper_chain_link_cryptographic",
    "paper_chain_spec_digest_carried",
)
_GATE_TRUE_FLAGS = (
    "paper_only",
    "daily_return_series_evidence_consumed",
    "thirty_day_evidence_gate_decision",
    "thirty_day_gate_decided",
)
_GATE_FALSE_FLAGS = (
    "sharpe_computed",
    "paper_sharpe_computed",
    "comparison_ready",
    "stage4_comparator_invoked",
    "prdv4_stage4_complete",
    "live_ready",
    "shadow_ready",
    "operational_readiness",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "real_wall_clock_used",
    "real_account_equity_used",
    "real_capital_used",
)
_PRECONDITION_TRUE_FLAGS = ("paper_only", "validation_only")
_PRECONDITION_FALSE_FLAGS = (
    "live_ready",
    "shadow_ready",
    "connector_ready",
    "orders_enabled",
    "real_fills_used",
    "authoritative_pnl",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "stage4_complete",
    "sm5_enabled",
    "sm6_enabled",
)
_METRICS_TRUE_FLAGS = ("paper_only", "evidence_only", "thresholds_enforced_here_not_by_comparator")
_METRICS_FALSE_FLAGS = (
    "comparator_invoked",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "pnl_authoritative",
    "edge_proven",
    "profitability_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "production_execution",
)


def _flag_failures(
    artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...], reason_code: str
) -> list[str]:
    if any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    ):
        return [_reason(reason_code)]
    return []


def _anchor_canonicality_failures(
    *,
    identity_values: tuple[object, ...],
    metadata: object,
    reason_code: str,
) -> list[str]:
    """Canonical identity + exact canonical metadata representation for one anchor (SM-5 round-2 lessons).

    Digest validity is never accepted as evidence of canonical representation: every anchor-carried trust
    identity must be an exact plain non-empty ``str`` and the anchor metadata must be in the exact canonical
    sorted-tuple form BEFORE any equality, scan, or projection consumes it.
    """

    if any(not _is_plain_non_empty_string(value) for value in identity_values) or not _is_canonical_anchor_metadata(
        metadata
    ):
        return [_reason(reason_code)]
    return []


def _baseline_value_failures(baseline: Stage4BacktestBaseline) -> list[str]:
    """Re-prove caller-supplied baseline well-formedness. Mirrors ``stage4_comparator._validate_baseline`` ranges."""

    hard: list[str] = []
    if not _is_plain_non_empty_string(baseline.baseline_id):
        hard.append(_reason("baseline_id_invalid"))
    if not _is_hex64_string(baseline.edge_id):
        hard.append(_reason("baseline_edge_id_invalid"))
    if not _is_positive_int(baseline.as_of_ns):
        hard.append(_reason("baseline_as_of_ns_invalid"))
    if not _is_finite_number(baseline.backtest_sharpe) or float(baseline.backtest_sharpe) <= 0.0:
        hard.append(_reason("backtest_sharpe_non_positive"))
    elif not (_MIN_BACKTEST_SHARPE_DECIMAL <= Decimal(repr(baseline.backtest_sharpe)) <= _MAX_BACKTEST_SHARPE_DECIMAL):
        hard.append(_reason("backtest_sharpe_out_of_bounds"))
    if not _is_rate(baseline.backtest_hit_rate):
        hard.append(_reason("backtest_hit_rate_invalid"))
    if not _is_non_negative_optional_number(baseline.backtest_slippage_bps):
        hard.append(_reason("backtest_slippage_invalid"))
    if not _is_optional_rate(baseline.backtest_fill_rate):
        hard.append(_reason("backtest_fill_rate_invalid"))
    if type(baseline.source_window_ids) is not tuple or not all(
        _is_plain_non_empty_string(item) for item in baseline.source_window_ids
    ):
        hard.append(_reason("source_window_ids_invalid"))
    return hard


def _baseline_string_fields(baseline: Stage4BacktestBaseline) -> tuple[str, ...]:
    texts: list[str] = []
    if type(baseline.baseline_id) is str:
        texts.append(baseline.baseline_id)
    if type(baseline.edge_id) is str:
        texts.append(baseline.edge_id)
    if type(baseline.source_window_ids) is tuple:
        texts.extend(item for item in baseline.source_window_ids if type(item) is str)
    return tuple(texts)


def _edge_identity_failures(edge_identity: PaperEdgeIdentityEvidence) -> list[str]:
    """Trust boundary for the merged edge identity (schema / status / resolution / policy / re-derivation / flags)."""

    hard: list[str] = []
    if edge_identity.schema_version != _EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION:
        hard.append(_reason("edge_identity_schema_invalid"))
    if (
        edge_identity.status is not PaperEdgeIdentityEvidenceStatus.READY
        or edge_identity.ready is not True
        or edge_identity.reason_codes != ()
    ):
        hard.append(_reason("edge_identity_not_ready"))
    if edge_identity.edge_identity_resolved is not True or edge_identity.strategy_spec_identity_proven is not True:
        hard.append(_reason("edge_identity_not_resolved"))
    if not _is_hex64_string(edge_identity.paper_edge_id):
        hard.append(_reason("edge_identity_paper_edge_id_invalid"))
    if edge_identity.edge_id_form != _EDGE_ID_FORM:
        hard.append(_reason("edge_identity_edge_id_form_invalid"))
    if edge_identity.edge_id_derivation_policy != _EDGE_ID_DERIVATION_POLICY:
        hard.append(_reason("edge_identity_derivation_policy_mismatch"))
    if (
        not _is_plain_non_empty_string(edge_identity.strategy_id)
        or not _is_plain_non_empty_string(edge_identity.market_symbol)
        or not _is_hex64_string(edge_identity.paper_edge_id)
        or _derive_paper_edge_id(edge_identity.strategy_id, edge_identity.market_symbol) != edge_identity.paper_edge_id
    ):
        hard.append(_reason("edge_id_derivation_mismatch"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                edge_identity.edge_identity_id,
                edge_identity.paper_id,
                edge_identity.correlation_id,
                edge_identity.strategy_id,
                edge_identity.market_symbol,
            ),
            metadata=edge_identity.metadata,
            reason_code="edge_identity_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(
            edge_identity, _EDGE_IDENTITY_TRUE_FLAGS, _EDGE_IDENTITY_FALSE_FLAGS, "edge_identity_unsafe_flags"
        )
    )
    return hard


def _sharpe_evidence_failures(sharpe_evidence: PaperSharpeEvidence) -> list[str]:
    hard: list[str] = []
    if sharpe_evidence.schema_version != _EXPECTED_SHARPE_SCHEMA_VERSION:
        hard.append(_reason("sharpe_evidence_schema_invalid"))
    if (
        sharpe_evidence.status is not PaperSharpeEvidenceStatus.READY
        or sharpe_evidence.ready is not True
        or sharpe_evidence.reason_codes != ()
    ):
        hard.append(_reason("sharpe_evidence_not_ready"))
    if sharpe_evidence.sharpe_computed is not True:
        hard.append(_reason("sharpe_not_computed"))
    if not _is_scale18_decimal_string(sharpe_evidence.paper_sharpe_annualized):
        hard.append(_reason("paper_sharpe_annualized_invalid"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                sharpe_evidence.sharpe_evidence_id,
                sharpe_evidence.paper_id,
                sharpe_evidence.series_id,
                sharpe_evidence.window_id,
                sharpe_evidence.correlation_id,
                sharpe_evidence.market_symbol,
            ),
            metadata=sharpe_evidence.metadata,
            reason_code="sharpe_evidence_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(sharpe_evidence, _SHARPE_TRUE_FLAGS, _SHARPE_FALSE_FLAGS, "sharpe_evidence_unsafe_flags")
    )
    return hard


def _methodology_v2_failures(
    methodology_v2: PaperVsBacktestMethodologyV2, sharpe_evidence: PaperSharpeEvidence
) -> list[str]:
    """Trust boundary for the merged SM-5 methodology-v2 snapshot (the SAME checks v1 ran, plus SM-5 gates).

    The consumed snapshot must be READY with the exact v2 schema, carry the exact approved comparison
    governance the Sharpe evidence used, and carry the three metric-specific enforced flags True while its
    aggregate ``secondary_metrics_enforced`` stays False (the SM-5 boundary). The approved secondary
    thresholds it carries must be canonical scale-18 / exact-int values in range.
    """

    hard: list[str] = []
    if (
        methodology_v2.schema_version != _EXPECTED_METHODOLOGY_V2_SCHEMA_VERSION
        or methodology_v2.methodology_version != _EXPECTED_METHODOLOGY_V2_SCHEMA_VERSION
    ):
        hard.append(_reason("methodology_v2_schema_invalid"))
    if (
        methodology_v2.status is not PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY
        or methodology_v2.ready is not True
        or methodology_v2.reason_codes != ()
    ):
        hard.append(_reason("methodology_v2_not_ready"))
    if (
        methodology_v2.comparison_basis != _EXPECTED_COMPARISON_BASIS
        or methodology_v2.enforced_guardrail_policy != _EXPECTED_ENFORCED_GUARDRAIL_POLICY
        or methodology_v2.risk_free_policy_id != sharpe_evidence.risk_free_policy_id
        or methodology_v2.annualization_factor != sharpe_evidence.annualization_factor
        or methodology_v2.annualization_policy != sharpe_evidence.annualization_policy
        or methodology_v2.stddev_policy != sharpe_evidence.stddev_policy
        or methodology_v2.decimal_policy != sharpe_evidence.decimal_policy
        or methodology_v2.decimal_scale != sharpe_evidence.decimal_scale
        or methodology_v2.decimal_rounding != sharpe_evidence.decimal_rounding
        or methodology_v2.decimal_internal_precision != sharpe_evidence.decimal_internal_precision
    ):
        hard.append(_reason("methodology_v2_policy_mismatch"))
    if (
        not _is_scale18_decimal_string(methodology_v2.sharpe_retention_ratio)
        or Decimal(methodology_v2.sharpe_retention_ratio) <= 0
    ):
        hard.append(_reason("methodology_v2_retention_threshold_invalid"))
    elif methodology_v2.sharpe_retention_ratio != _APPROVED_SHARPE_RETENTION_RATIO:
        hard.append(_reason("methodology_v2_retention_threshold_unapproved"))
    if not _is_positive_int(methodology_v2.min_duration_days):
        hard.append(_reason("methodology_v2_min_duration_invalid"))
    elif methodology_v2.min_duration_days != _APPROVED_MIN_DURATION_DAYS:
        hard.append(_reason("methodology_v2_min_duration_unapproved"))
    if (
        methodology_v2.secondary_metrics_decimal_policy != _EXPECTED_SM_DECIMAL_POLICY
        or methodology_v2.secondary_metrics_decimal_scale != _DECIMAL_SCALE
        or methodology_v2.secondary_metrics_decimal_rounding != _DECIMAL_ROUNDING
        or methodology_v2.fraction_intermediates_required is not True
        or methodology_v2.hit_rate_operator != _EXPECTED_HIT_RATE_OPERATOR
        or methodology_v2.fill_rate_operator != _EXPECTED_FILL_RATE_OPERATOR
        or methodology_v2.slippage_operator != _EXPECTED_SLIPPAGE_OPERATOR
    ):
        hard.append(_reason("methodology_v2_secondary_policy_mismatch"))
    hit_floor = _parse_scale18(methodology_v2.approved_hit_rate_floor)
    fill_floor = _parse_scale18(methodology_v2.approved_fill_rate_floor)
    slippage_ceiling = _parse_scale18(methodology_v2.approved_slippage_ceiling_bps)
    if (
        hit_floor is None
        or hit_floor < 0
        or hit_floor > 1
        or fill_floor is None
        or fill_floor < 0
        or fill_floor > 1
        or slippage_ceiling is None
        or slippage_ceiling < 0
        or not _is_exact_int(methodology_v2.approved_min_decided_episode_count)
        or methodology_v2.approved_min_decided_episode_count < 1
    ):
        hard.append(_reason("methodology_v2_thresholds_invalid"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                methodology_v2.methodology_id,
                methodology_v2.correlation_id,
                methodology_v2.predecessor_methodology_id,
                methodology_v2.secondary_metrics_policy_id,
                methodology_v2.secondary_metrics_enforcement_precondition_id,
                methodology_v2.market_symbol,
            ),
            metadata=methodology_v2.metadata,
            reason_code="methodology_v2_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(
            methodology_v2, _METHODOLOGY_V2_TRUE_FLAGS, _METHODOLOGY_V2_FALSE_FLAGS, "methodology_v2_unsafe_flags"
        )
    )
    return hard


def _gate_decision_failures(
    gate_decision: PaperThirtyDayEvidenceGateDecision, methodology_v2: PaperVsBacktestMethodologyV2
) -> list[str]:
    hard: list[str] = []
    if (
        gate_decision.schema_version != _EXPECTED_GATE_SCHEMA_VERSION
        or gate_decision.decision_version != _EXPECTED_GATE_SCHEMA_VERSION
    ):
        hard.append(_reason("gate_decision_schema_invalid"))
    if (
        gate_decision.status is not PaperThirtyDayEvidenceGateDecisionStatus.READY
        or gate_decision.ready is not True
        or gate_decision.reason_codes != ()
    ):
        hard.append(_reason("gate_decision_not_ready"))
    if gate_decision.thirty_day_gate_satisfied is not True:
        hard.append(_reason("thirty_day_gate_not_satisfied"))
    if gate_decision.risk_free_policy_id != methodology_v2.risk_free_policy_id:
        hard.append(_reason("gate_risk_free_policy_mismatch"))
    if (
        not _is_exact_int(gate_decision.gate_minimum_consecutive_bucket_count)
        or not _is_exact_int(methodology_v2.min_duration_days)
        or gate_decision.gate_minimum_consecutive_bucket_count != methodology_v2.min_duration_days
    ):
        hard.append(_reason("min_duration_policy_mismatch"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                gate_decision.gate_id,
                gate_decision.series_id,
                gate_decision.window_id,
                gate_decision.correlation_id,
                gate_decision.market_symbol,
            ),
            metadata=gate_decision.metadata,
            reason_code="gate_decision_noncanonical",
        )
    )
    hard.extend(_flag_failures(gate_decision, _GATE_TRUE_FLAGS, _GATE_FALSE_FLAGS, "gate_decision_unsafe_flags"))
    return hard


def _baseline_evidence_failures(
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    backtest_baseline: Stage4BacktestBaseline,
    edge_identity: PaperEdgeIdentityEvidence,
    verified_edge_identity_digest: str,
) -> list[str]:
    hard: list[str] = []
    if (
        baseline_evidence.schema_id != _EXPECTED_BASELINE_EVIDENCE_SCHEMA_VERSION
        or baseline_evidence.schema_version != _EXPECTED_BASELINE_EVIDENCE_SCHEMA_VERSION
    ):
        hard.append(_reason("baseline_evidence_schema_invalid"))
    if (
        baseline_evidence.status is not PaperStage4BacktestBaselineEvidenceStatus.READY
        or baseline_evidence.ready is not True
        or baseline_evidence.reason_codes != ()
    ):
        hard.append(_reason("baseline_evidence_not_ready"))
    if baseline_evidence.baseline_bound is not True or baseline_evidence.same_edge_identity_equal is not True:
        hard.append(_reason("baseline_evidence_not_bound"))
    if verified_edge_identity_digest == "" or baseline_evidence.edge_identity_digest != verified_edge_identity_digest:
        hard.append(_reason("edge_identity_cross_digest_mismatch"))
    if (
        baseline_evidence.baseline_id != backtest_baseline.baseline_id
        or baseline_evidence.edge_id != backtest_baseline.edge_id
        or baseline_evidence.baseline_as_of_ns != backtest_baseline.as_of_ns
        or baseline_evidence.baseline_source_window_ids != backtest_baseline.source_window_ids
        or baseline_evidence.paper_edge_id != edge_identity.paper_edge_id
        or baseline_evidence.paper_id != edge_identity.paper_id
        or baseline_evidence.market_symbol != edge_identity.market_symbol
        or baseline_evidence.strategy_id != edge_identity.strategy_id
    ):
        hard.append(_reason("baseline_evidence_binding_mismatch"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                baseline_evidence.baseline_evidence_id,
                baseline_evidence.baseline_id,
                baseline_evidence.paper_id,
                baseline_evidence.correlation_id,
                baseline_evidence.market_symbol,
                baseline_evidence.strategy_id,
            ),
            metadata=baseline_evidence.metadata,
            reason_code="baseline_evidence_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(
            baseline_evidence,
            _BASELINE_EVIDENCE_TRUE_FLAGS,
            _BASELINE_EVIDENCE_FALSE_FLAGS,
            "baseline_evidence_unsafe_flags",
        )
    )
    return hard


def _precondition_failures(precondition: PaperSecondaryMetricsEnforcementPrecondition) -> list[str]:
    """Trust boundary for the SAME enforcement precondition the merged methodology-v2 bound."""

    hard: list[str] = []
    if (
        precondition.schema_version != _EXPECTED_PRECONDITION_SCHEMA_VERSION
        or precondition.precondition_version != _EXPECTED_PRECONDITION_SCHEMA_VERSION
    ):
        hard.append(_reason("enforcement_precondition_schema_invalid"))
    if (
        precondition.status is not PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
        or precondition.ready is not True
        or precondition.reason_codes != ()
    ):
        hard.append(_reason("enforcement_precondition_not_ready"))
    if (
        not _is_hex64_string(precondition.policy_digest)
        or not _is_hex64_string(precondition.metrics_evidence_digest)
        or not _is_hex64_string(precondition.reconciliation_digest)
    ):
        hard.append(_reason("enforcement_precondition_contract_invalid"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                precondition.precondition_id,
                precondition.correlation_id,
                precondition.policy_id,
                precondition.market_symbol,
            ),
            metadata=precondition.metadata,
            reason_code="enforcement_precondition_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(
            precondition, _PRECONDITION_TRUE_FLAGS, _PRECONDITION_FALSE_FLAGS, "enforcement_precondition_unsafe_flags"
        )
    )
    return hard


def _metrics_evidence_failures(metrics_evidence: PaperSecondaryMetricsEvidence) -> list[str]:
    """Trust boundary for the direct real SM-4 evidence (never replaced by carried copies elsewhere)."""

    hard: list[str] = []
    if (
        metrics_evidence.schema_version != _EXPECTED_METRICS_SCHEMA_VERSION
        or metrics_evidence.evidence_version != _EXPECTED_METRICS_SCHEMA_VERSION
    ):
        hard.append(_reason("metrics_evidence_schema_invalid"))
    if (
        metrics_evidence.status is not PaperSecondaryMetricsEvidenceStatus.METRICS_READY
        or metrics_evidence.ready is not True
        or metrics_evidence.reason_codes != ()
        or metrics_evidence.thresholds_cleared is not True
        or metrics_evidence.sufficient_evidence is not True
    ):
        hard.append(_reason("metrics_evidence_not_ready"))
    if (
        metrics_evidence.decimal_policy != _EXPECTED_SM_DECIMAL_POLICY
        or metrics_evidence.decimal_scale != _DECIMAL_SCALE
        or metrics_evidence.decimal_rounding != _DECIMAL_ROUNDING
        or metrics_evidence.decimal_internal_precision != _DECIMAL_INTERNAL_PRECISION
        or metrics_evidence.hit_rate_operator != _EXPECTED_HIT_RATE_OPERATOR
        or metrics_evidence.fill_rate_operator != _EXPECTED_FILL_RATE_OPERATOR
        or metrics_evidence.slippage_operator != _EXPECTED_SLIPPAGE_OPERATOR
        or not _is_hex64_string(metrics_evidence.verified_policy_digest)
    ):
        hard.append(_reason("metrics_evidence_contract_invalid"))
    hard.extend(
        _anchor_canonicality_failures(
            identity_values=(
                metrics_evidence.evidence_id,
                metrics_evidence.correlation_id,
                metrics_evidence.policy_id,
            ),
            metadata=metrics_evidence.metadata,
            reason_code="metrics_evidence_noncanonical",
        )
    )
    hard.extend(
        _flag_failures(metrics_evidence, _METRICS_TRUE_FLAGS, _METRICS_FALSE_FLAGS, "metrics_evidence_unsafe_flags")
    )
    return hard


def _plain_strings_equal(*values: object) -> bool:
    return all(_is_plain_non_empty_string(value) for value in values) and len({*values}) == 1


def _hex64_strings_equal(*values: object) -> bool:
    return all(_is_hex64_string(value) for value in values) and len({*values}) == 1


def _optional_scale18_equal(left: object, right: object) -> bool:
    if left is None and right is None:
        return True
    return _is_scale18_decimal_string(left) and _is_scale18_decimal_string(right) and left == right


def _sm_binding_failures(
    *,
    methodology_v2: PaperVsBacktestMethodologyV2,
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
    metrics_evidence: PaperSecondaryMetricsEvidence,
) -> list[str]:
    """Cross-bind the SM trust roots into ONE chain (digest, policy, computed values, record set)."""

    hard: list[str] = []
    # MANDATORY: the precondition must be bound to exactly the direct SM-4 artifact supplied here.
    if not _hex64_strings_equal(precondition.metrics_evidence_digest, metrics_evidence.evidence_digest):
        hard.append(_reason("precondition_metrics_evidence_binding_mismatch"))
    # The methodology-v2 snapshot must have bound the SAME precondition (the SM-5-recorded handoff).
    if not _hex64_strings_equal(
        methodology_v2.verified_secondary_metrics_enforcement_precondition_digest, precondition.precondition_digest
    ):
        hard.append(_reason("methodology_v2_precondition_binding_mismatch"))
    # Policy identity quadruple: id and digest must agree across methodology-v2, precondition, and SM-4.
    if not _plain_strings_equal(
        methodology_v2.secondary_metrics_policy_id, precondition.policy_id, metrics_evidence.policy_id
    ) or not _hex64_strings_equal(
        methodology_v2.verified_secondary_metrics_policy_digest,
        precondition.policy_digest,
        metrics_evidence.verified_policy_digest,
    ):
        hard.append(_reason("policy_binding_mismatch"))
    # The precondition-carried computed values must equal the direct SM-4 canonical values exactly.
    if (
        not _optional_scale18_equal(precondition.computed_hit_rate, metrics_evidence.hit_rate)
        or not _optional_scale18_equal(
            precondition.computed_fill_rate_by_quantity, metrics_evidence.fill_rate_by_quantity
        )
        or not _optional_scale18_equal(
            precondition.computed_fill_rate_by_episode, metrics_evidence.fill_rate_by_episode
        )
        or not (
            (precondition.computed_slippage_bps is None and metrics_evidence.average_slippage_bps is None)
            or _optional_scale18_equal(precondition.computed_slippage_bps, metrics_evidence.average_slippage_bps)
        )
        or not _is_exact_int(precondition.computed_decided_episode_count)
        or not _is_exact_int(metrics_evidence.decided_episode_count)
        or precondition.computed_decided_episode_count != metrics_evidence.decided_episode_count
    ):
        hard.append(_reason("computed_metrics_binding_mismatch"))
    # Approved threshold snapshot triple equality across methodology-v2, precondition, and SM-4.
    if (
        not _optional_scale18_equal(methodology_v2.approved_hit_rate_floor, precondition.approved_hit_rate_floor)
        or not _optional_scale18_equal(methodology_v2.approved_hit_rate_floor, metrics_evidence.approved_hit_rate_floor)
        or not _optional_scale18_equal(methodology_v2.approved_fill_rate_floor, precondition.approved_fill_rate_floor)
        or not _optional_scale18_equal(
            methodology_v2.approved_fill_rate_floor, metrics_evidence.approved_fill_rate_floor
        )
        or not _optional_scale18_equal(
            methodology_v2.approved_slippage_ceiling_bps, precondition.approved_slippage_ceiling_bps
        )
        or not _optional_scale18_equal(
            methodology_v2.approved_slippage_ceiling_bps, metrics_evidence.approved_slippage_ceiling_bps
        )
        or not _is_exact_int(methodology_v2.approved_min_decided_episode_count)
        or methodology_v2.approved_min_decided_episode_count != precondition.approved_min_decided_episode_count
        or methodology_v2.approved_min_decided_episode_count != metrics_evidence.approved_min_decided_episode_count
    ):
        hard.append(_reason("threshold_snapshot_mismatch"))
    # Record-set / denominator coherence: the SM-4 record digests are the single lineage authority.
    metrics_digests = metrics_evidence.record_digests if type(metrics_evidence.record_digests) is tuple else None
    precondition_digests = precondition.record_digests if type(precondition.record_digests) is tuple else None
    record_set_ok = (
        metrics_digests is not None
        and precondition_digests is not None
        and all(_is_hex64_string(digest) for digest in metrics_digests)
        and list(metrics_digests) == sorted(metrics_digests)
        and len(set(metrics_digests)) == len(metrics_digests)
        and metrics_digests == precondition_digests
        and _is_exact_int(metrics_evidence.record_count)
        and len(metrics_digests) == metrics_evidence.record_count
        and _is_exact_int(precondition.metrics_record_count)
        and precondition.metrics_record_count == metrics_evidence.record_count
        and _is_exact_int(precondition.reconciled_record_count)
        and precondition.reconciled_record_count == metrics_evidence.record_count
        and _is_exact_int(precondition.reconciled_episode_count)
        and precondition.reconciled_episode_count == metrics_evidence.record_count
        and _is_exact_int(metrics_evidence.decided_episode_count)
        and 0 <= metrics_evidence.decided_episode_count <= metrics_evidence.record_count
        and metrics_evidence.record_count >= 1
    )
    if not record_set_ok:
        hard.append(_reason("record_set_incoherent"))
    return hard


@dataclass(frozen=True)
class _SecondaryEnforcement:
    hit_pass: bool
    fill_quantity_pass: bool
    fill_episode_pass: bool
    fill_pass: bool
    slippage_pass: bool
    min_decided_pass: bool
    all_present: bool
    all_cleared: bool
    hit_rate: Decimal | None
    fill_quantity: Decimal | None
    fill_episode: Decimal | None
    slippage: Decimal | None


def _secondary_enforcement_failures(
    *,
    methodology_v2: PaperVsBacktestMethodologyV2,
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
    metrics_evidence: PaperSecondaryMetricsEvidence,
) -> tuple[list[str], _SecondaryEnforcement]:
    """Independent Decimal reapplication of the approved secondary thresholds (SM-6 enforcement authority).

    Every required real metric must be present and canonical (``missing_secondary_metric`` otherwise — the
    SM-5 vacuous ``None``-slippage pass is structurally impossible here), every threshold comparison is
    recomputed from the direct SM-4 canonical values against the methodology-v2 digest-bound approved
    thresholds, and every carried pass boolean on SM-4 and on the precondition must equal the recompute
    (``threshold_pass_incoherent``) — carried booleans are never trusted as enforcement.
    """

    hard: list[str] = []
    hit_floor = _parse_scale18(methodology_v2.approved_hit_rate_floor)
    fill_floor = _parse_scale18(methodology_v2.approved_fill_rate_floor)
    slippage_ceiling = _parse_scale18(methodology_v2.approved_slippage_ceiling_bps)
    hit_rate = _parse_scale18(metrics_evidence.hit_rate)
    fill_quantity = _parse_scale18(metrics_evidence.fill_rate_by_quantity)
    fill_episode = _parse_scale18(metrics_evidence.fill_rate_by_episode)
    slippage = _parse_scale18(metrics_evidence.average_slippage_bps)

    all_present = (
        hit_rate is not None and fill_quantity is not None and fill_episode is not None and slippage is not None
    )
    if not all_present:
        hard.append(_reason("missing_secondary_metric"))

    with localcontext() as context:
        context.prec = _DECIMAL_INTERNAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        hit_pass = hit_floor is not None and hit_rate is not None and hit_rate >= hit_floor
        fill_quantity_pass = fill_floor is not None and fill_quantity is not None and fill_quantity >= fill_floor
        fill_episode_pass = fill_floor is not None and fill_episode is not None and fill_episode >= fill_floor
        fill_pass = fill_quantity_pass and fill_episode_pass
        slippage_pass = slippage_ceiling is not None and slippage is not None and slippage <= slippage_ceiling
        # The upstream SM-4 / precondition echo semantics treat a ``None`` slippage as a vacuous pass; the
        # coherence recompute below must use THAT formula so an honest upstream chain is not flagged
        # incoherent, while SM-6's own enforcement above requires the metric to be present.
        slippage_vacuous_pass = slippage_ceiling is not None and (
            metrics_evidence.average_slippage_bps is None or (slippage is not None and slippage <= slippage_ceiling)
        )
    min_decided_pass = (
        _is_exact_int(methodology_v2.approved_min_decided_episode_count)
        and _is_exact_int(metrics_evidence.decided_episode_count)
        and metrics_evidence.decided_episode_count >= methodology_v2.approved_min_decided_episode_count
    )

    if hit_floor is not None and hit_rate is not None and not hit_pass:
        hard.append(_reason("hit_rate_floor_not_met"))
    if fill_floor is not None and fill_quantity is not None and fill_episode is not None and not fill_pass:
        hard.append(_reason("fill_rate_floor_not_met"))
    if slippage_ceiling is not None and slippage is not None and not slippage_pass:
        hard.append(_reason("slippage_ceiling_exceeded"))
    if not min_decided_pass:
        hard.append(_reason("min_decided_episode_count_not_met"))

    vacuous_cleared = hit_pass and fill_pass and slippage_vacuous_pass and min_decided_pass
    echo_coherent = (
        metrics_evidence.hit_rate_satisfied is hit_pass
        and metrics_evidence.fill_rate_satisfied is fill_pass
        and metrics_evidence.slippage_satisfied is slippage_vacuous_pass
        and metrics_evidence.sufficient_evidence is min_decided_pass
        and metrics_evidence.thresholds_cleared is vacuous_cleared
        and precondition.hit_rate_passed is hit_pass
        and precondition.fill_rate_by_quantity_passed is fill_quantity_pass
        and precondition.fill_rate_by_episode_passed is fill_episode_pass
        and precondition.fill_rate_passed is fill_pass
        and precondition.slippage_passed is slippage_vacuous_pass
        and precondition.min_decided_episode_count_passed is min_decided_pass
    )
    if not echo_coherent:
        hard.append(_reason("threshold_pass_incoherent"))

    all_cleared = all_present and hit_pass and fill_pass and slippage_pass and min_decided_pass
    return hard, _SecondaryEnforcement(
        hit_pass=hit_pass,
        fill_quantity_pass=fill_quantity_pass,
        fill_episode_pass=fill_episode_pass,
        fill_pass=fill_pass,
        slippage_pass=slippage_pass,
        min_decided_pass=min_decided_pass,
        all_present=all_present,
        all_cleared=all_cleared,
        hit_rate=hit_rate,
        fill_quantity=fill_quantity,
        fill_episode=fill_episode,
        slippage=slippage,
    )


def _cross_link_failures(
    *,
    correlation_id: str,
    sharpe_evidence: PaperSharpeEvidence,
    methodology_v2: PaperVsBacktestMethodologyV2,
    edge_identity: PaperEdgeIdentityEvidence,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
    metrics_evidence: PaperSecondaryMetricsEvidence,
) -> list[str]:
    hard: list[str] = []
    if any(
        artifact.correlation_id != correlation_id
        for artifact in (
            sharpe_evidence,
            methodology_v2,
            edge_identity,
            baseline_evidence,
            gate_decision,
            precondition,
            metrics_evidence,
        )
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _is_plain_non_empty_string(sharpe_evidence.market_symbol) or any(
        artifact.market_symbol != sharpe_evidence.market_symbol
        for artifact in (gate_decision, edge_identity, baseline_evidence, methodology_v2, precondition)
    ):
        hard.append(_reason("market_symbol_mismatch"))
    if not _is_plain_non_empty_string(sharpe_evidence.paper_id) or any(
        artifact.paper_id != sharpe_evidence.paper_id for artifact in (edge_identity, baseline_evidence)
    ):
        hard.append(_reason("paper_id_mismatch"))
    if (
        not _is_hex64_string(sharpe_evidence.verified_daily_return_series_digest)
        or sharpe_evidence.verified_daily_return_series_digest != gate_decision.series_digest
    ):
        hard.append(_reason("series_digest_mismatch"))
    if (
        sharpe_evidence.series_id != gate_decision.series_id
        or sharpe_evidence.window_id != gate_decision.window_id
        or sharpe_evidence.time_window_digest != gate_decision.time_window_digest
        or sharpe_evidence.metrics_summary_digest != gate_decision.metrics_summary_digest
        or sharpe_evidence.methodology_digest != gate_decision.methodology_digest
        or sharpe_evidence.bucket_count != gate_decision.bucket_count
        or sharpe_evidence.required_consecutive_bucket_count != gate_decision.required_consecutive_bucket_count
    ):
        hard.append(_reason("series_binding_mismatch"))
    return hard


def _anchor_scope_failures(
    *,
    sharpe_evidence: PaperSharpeEvidence,
    methodology_v2: PaperVsBacktestMethodologyV2,
    edge_identity: PaperEdgeIdentityEvidence,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    precondition: PaperSecondaryMetricsEnforcementPrecondition,
    metrics_evidence: PaperSecondaryMetricsEvidence,
) -> list[str]:
    """Anchor-carried identity/metadata scope scan (REJECTED, never a caller-input RAISE).

    A coherent resealed anchor must not smuggle BIST/scope/clock text through its ids or metadata. Metadata
    texts are extracted only from metadata that already passed the exact canonical-representation check (a
    noncanonical representation is REJECTED by that anchor's canonicality gate and never silently skipped,
    so this scan can never crash); identity texts are scanned only when they are plain strings.
    """

    texts: list[str] = []
    for artifact, identity_names in (
        (sharpe_evidence, ("sharpe_evidence_id", "paper_id", "series_id", "window_id", "correlation_id")),
        (
            methodology_v2,
            (
                "methodology_id",
                "correlation_id",
                "predecessor_methodology_id",
                "secondary_metrics_policy_id",
                "secondary_metrics_enforcement_precondition_id",
            ),
        ),
        (edge_identity, ("edge_identity_id", "paper_id", "correlation_id", "strategy_id")),
        (baseline_evidence, ("baseline_evidence_id", "baseline_id", "paper_id", "correlation_id", "strategy_id")),
        (gate_decision, ("gate_id", "series_id", "window_id", "correlation_id")),
        (precondition, ("precondition_id", "correlation_id", "policy_id")),
        (metrics_evidence, ("evidence_id", "correlation_id", "policy_id")),
    ):
        for name in identity_names:
            value = getattr(artifact, name)
            if _is_plain_non_empty_string(value):
                texts.append(value)
        metadata = artifact.metadata
        if _is_canonical_anchor_metadata(metadata):
            texts.extend(_metadata_texts(metadata))
    if _has_scope_violation(*texts) or _has_clock_token(*texts):
        return [_reason("anchor_scope_violation")]
    return []


def _duration_failures(
    gate_decision: PaperThirtyDayEvidenceGateDecision, methodology_v2: PaperVsBacktestMethodologyV2
) -> tuple[list[str], bool]:
    """Integer-arithmetic duration precheck — the comparator must never see a below-minimum window."""

    hard: list[str] = []
    first_start = gate_decision.first_bucket_start_ns
    last_end = gate_decision.last_bucket_end_ns
    duration = gate_decision.window_duration_ns
    bucket_count = gate_decision.bucket_count
    if (
        not _is_positive_int(first_start)
        or not _is_positive_int(last_end)
        or not _is_positive_int(duration)
        or not _is_positive_int(bucket_count)
        or last_end <= first_start
    ):
        hard.append(_reason("gate_window_timestamps_invalid"))
        return hard, False
    if duration != last_end - first_start or duration != bucket_count * _DAY_NS:
        hard.append(_reason("window_duration_incoherent"))
        return hard, False
    if not _is_positive_int(methodology_v2.min_duration_days):
        return hard, False
    duration_satisfied = bucket_count >= methodology_v2.min_duration_days and duration >= (
        methodology_v2.min_duration_days * _DAY_NS
    )
    if not duration_satisfied:
        hard.append(_reason("duration_below_minimum_precheck"))
    return hard, duration_satisfied


def _echo_float_repr(value: object) -> str:
    return repr(value) if type(value) is float and math.isfinite(value) else ""


def _echo_reasons(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        return ()
    return tuple(item for item in value if type(item) is str)


def _comparator_coherence_failures(result: Stage4ComparisonResult, decimal_satisfied: bool) -> list[str]:
    """Fail closed when the advisory float comparator disagrees with the authoritative Decimal verdict."""

    hard: list[str] = []
    status = _plain_str_or_empty(result.status)
    reasons = _echo_reasons(result.rejection_reasons)
    if result.evaluated is not True or status not in (_COMPARATOR_STATUS_PASS, _COMPARATOR_STATUS_REJECT):
        hard.append(_reason("comparator_unexpected_rejection"))
        return hard
    if decimal_satisfied:
        if status != _COMPARATOR_STATUS_PASS or result.passed is not True or reasons != ():
            hard.append(_reason("decimal_float_comparator_verdict_mismatch"))
        return hard
    if status == _COMPARATOR_STATUS_PASS:
        hard.append(_reason("decimal_float_comparator_verdict_mismatch"))
        return hard
    if result.passed is not False or reasons != (_COMPARATOR_BELOW_THRESHOLD_REASON,):
        hard.append(_reason("comparator_unexpected_rejection"))
    return hard


def build_paper_stage4_comparison_evidence_v2(
    backtest_baseline: Stage4BacktestBaseline,
    *,
    expected_baseline_digest: str,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    expected_baseline_evidence_digest: str,
    sharpe_evidence: PaperSharpeEvidence,
    expected_sharpe_evidence_digest: str,
    methodology_v2: PaperVsBacktestMethodologyV2,
    expected_methodology_v2_digest: str,
    edge_identity: PaperEdgeIdentityEvidence,
    expected_edge_identity_digest: str,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    expected_gate_decision_digest: str,
    enforcement_precondition: PaperSecondaryMetricsEnforcementPrecondition,
    expected_enforcement_precondition_digest: str,
    metrics_evidence: PaperSecondaryMetricsEvidence,
    expected_metrics_evidence_digest: str,
    comparison_evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4ComparisonEvidenceV2:
    """Build Stage-4 comparison evidence v2 with real enforced secondary metrics (Decimal authoritative).

    Every consumed artifact must be the exact merged type and re-prove its self-digest against the caller's
    independent anchor; the caller-supplied ``backtest_baseline`` must re-prove by TRIPLE digest equality
    (recompute == ``expected_baseline_digest`` == ``baseline_evidence.baseline_digest``); the enforcement
    precondition must be bound to exactly the direct SM-4 evidence and be the SAME precondition the merged
    methodology-v2 bound. The approved secondary thresholds are reapplied here in Decimal; ``None`` or
    noncanonical real metrics are REJECTED; ``compare_stage4`` is invoked exactly once, only after every
    precondition passes, and only as an advisory float echo. Wrong-typed inputs, malformed anchors, malformed
    metadata, or forbidden BIST/live/order/capital/readiness/clock tokens raise
    ``PaperStage4ComparisonEvidenceV2Error``; every trust/value failure maps to ``status=REJECTED``.
    """
    if type(backtest_baseline) is not Stage4BacktestBaseline:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("backtest_baseline_malformed"))
    if type(baseline_evidence) is not PaperStage4BacktestBaselineEvidence:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("baseline_evidence_malformed"))
    if type(sharpe_evidence) is not PaperSharpeEvidence:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("sharpe_evidence_malformed"))
    if type(methodology_v2) is not PaperVsBacktestMethodologyV2:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("methodology_v2_malformed"))
    if type(edge_identity) is not PaperEdgeIdentityEvidence:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("edge_identity_malformed"))
    if type(gate_decision) is not PaperThirtyDayEvidenceGateDecision:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("gate_decision_malformed"))
    if type(enforcement_precondition) is not PaperSecondaryMetricsEnforcementPrecondition:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("enforcement_precondition_malformed"))
    if type(metrics_evidence) is not PaperSecondaryMetricsEvidence:
        raise PaperStage4ComparisonEvidenceV2Error(_reason("metrics_evidence_malformed"))
    expected_baseline_digest = _require_hex64(expected_baseline_digest, "expected_baseline_digest")
    expected_baseline_evidence_digest = _require_hex64(
        expected_baseline_evidence_digest, "expected_baseline_evidence_digest"
    )
    expected_sharpe_evidence_digest = _require_hex64(expected_sharpe_evidence_digest, "expected_sharpe_evidence_digest")
    expected_methodology_v2_digest = _require_hex64(expected_methodology_v2_digest, "expected_methodology_v2_digest")
    expected_edge_identity_digest = _require_hex64(expected_edge_identity_digest, "expected_edge_identity_digest")
    expected_gate_decision_digest = _require_hex64(expected_gate_decision_digest, "expected_gate_decision_digest")
    expected_enforcement_precondition_digest = _require_hex64(
        expected_enforcement_precondition_digest, "expected_enforcement_precondition_digest"
    )
    expected_metrics_evidence_digest = _require_hex64(
        expected_metrics_evidence_digest, "expected_metrics_evidence_digest"
    )
    comparison_evidence_id = _require_plain_non_empty_string(comparison_evidence_id, "comparison_evidence_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (comparison_evidence_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperStage4ComparisonEvidenceV2Error(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperStage4ComparisonEvidenceV2Error(_reason("clock_token_forbidden"))

    precondition = enforcement_precondition
    hard: list[str] = []

    # Trust boundary: re-prove every consumed artifact self-digest (recompute == carried == caller anchor).
    sharpe_failures, verified_sharpe_digest = _digest_reproof_failures(
        artifact=sharpe_evidence,
        carried_digest=sharpe_evidence.sharpe_evidence_digest,
        expected_digest=expected_sharpe_evidence_digest,
        compute=paper_sharpe_evidence_digest,
        reason_code="sharpe_evidence_digest_mismatch",
    )
    hard.extend(sharpe_failures)
    methodology_failures, verified_methodology_v2_digest = _digest_reproof_failures(
        artifact=methodology_v2,
        carried_digest=methodology_v2.methodology_digest,
        expected_digest=expected_methodology_v2_digest,
        compute=paper_vs_backtest_methodology_v2_digest,
        reason_code="methodology_v2_digest_mismatch",
    )
    hard.extend(methodology_failures)
    edge_failures, verified_edge_identity_digest = _digest_reproof_failures(
        artifact=edge_identity,
        carried_digest=edge_identity.edge_identity_digest,
        expected_digest=expected_edge_identity_digest,
        compute=paper_edge_identity_evidence_digest,
        reason_code="edge_identity_digest_mismatch",
    )
    hard.extend(edge_failures)
    baseline_evidence_failures, verified_baseline_evidence_digest = _digest_reproof_failures(
        artifact=baseline_evidence,
        carried_digest=baseline_evidence.baseline_evidence_digest,
        expected_digest=expected_baseline_evidence_digest,
        compute=paper_stage4_backtest_baseline_evidence_digest,
        reason_code="baseline_evidence_digest_mismatch",
    )
    hard.extend(baseline_evidence_failures)
    gate_failures, verified_gate_decision_digest = _digest_reproof_failures(
        artifact=gate_decision,
        carried_digest=gate_decision.decision_digest,
        expected_digest=expected_gate_decision_digest,
        compute=paper_30day_evidence_gate_decision_digest,
        reason_code="gate_decision_digest_mismatch",
    )
    hard.extend(gate_failures)
    precondition_digest_failures, verified_precondition_digest = _digest_reproof_failures(
        artifact=precondition,
        carried_digest=precondition.precondition_digest,
        expected_digest=expected_enforcement_precondition_digest,
        compute=paper_secondary_metrics_enforcement_precondition_digest,
        reason_code="enforcement_precondition_digest_mismatch",
    )
    hard.extend(precondition_digest_failures)
    metrics_digest_failures, verified_metrics_evidence_digest = _digest_reproof_failures(
        artifact=metrics_evidence,
        carried_digest=metrics_evidence.evidence_digest,
        expected_digest=expected_metrics_evidence_digest,
        compute=paper_secondary_metrics_evidence_digest,
        reason_code="metrics_evidence_digest_mismatch",
    )
    hard.extend(metrics_digest_failures)

    # Caller-supplied baseline: TRIPLE digest equality (recompute == caller anchor == bound-in-#313 digest).
    try:
        recomputed_baseline_digest = _canonical_digest(stage4_backtest_baseline_to_dict(backtest_baseline))
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        recomputed_baseline_digest = None
    if recomputed_baseline_digest is None or recomputed_baseline_digest != expected_baseline_digest:
        hard.append(_reason("baseline_digest_mismatch"))
        baseline_digest = ""
    else:
        baseline_digest = recomputed_baseline_digest
    if baseline_digest == "" or baseline_evidence.baseline_digest != baseline_digest:
        hard.append(_reason("baseline_evidence_baseline_digest_mismatch"))

    hard.extend(_baseline_value_failures(backtest_baseline))
    if _has_scope_violation(*_baseline_string_fields(backtest_baseline)):
        hard.append(_reason("baseline_scope_violation"))
    if _has_clock_token(*_baseline_string_fields(backtest_baseline)):
        hard.append(_reason("baseline_clock_token"))

    edge_contract_failures = _edge_identity_failures(edge_identity)
    hard.extend(edge_contract_failures)
    sharpe_contract_failures = _sharpe_evidence_failures(sharpe_evidence)
    hard.extend(sharpe_contract_failures)
    methodology_contract_failures = _methodology_v2_failures(methodology_v2, sharpe_evidence)
    hard.extend(methodology_contract_failures)
    gate_contract_failures = _gate_decision_failures(gate_decision, methodology_v2)
    hard.extend(gate_contract_failures)
    baseline_evidence_contract_failures = _baseline_evidence_failures(
        baseline_evidence, backtest_baseline, edge_identity, verified_edge_identity_digest
    )
    hard.extend(baseline_evidence_contract_failures)
    precondition_contract_failures = _precondition_failures(precondition)
    hard.extend(precondition_contract_failures)
    metrics_contract_failures = _metrics_evidence_failures(metrics_evidence)
    hard.extend(metrics_contract_failures)
    sm_binding_failures = _sm_binding_failures(
        methodology_v2=methodology_v2, precondition=precondition, metrics_evidence=metrics_evidence
    )
    hard.extend(sm_binding_failures)
    cross_link_failures = _cross_link_failures(
        correlation_id=correlation_id,
        sharpe_evidence=sharpe_evidence,
        methodology_v2=methodology_v2,
        edge_identity=edge_identity,
        baseline_evidence=baseline_evidence,
        gate_decision=gate_decision,
        precondition=precondition,
        metrics_evidence=metrics_evidence,
    )
    hard.extend(cross_link_failures)
    anchor_scope_failures = _anchor_scope_failures(
        sharpe_evidence=sharpe_evidence,
        methodology_v2=methodology_v2,
        edge_identity=edge_identity,
        baseline_evidence=baseline_evidence,
        gate_decision=gate_decision,
        precondition=precondition,
        metrics_evidence=metrics_evidence,
    )
    hard.extend(anchor_scope_failures)

    # Same-edge identity: the baseline edge id must equal the re-proven paper edge identity.
    baseline_edge_id = _plain_str_or_empty(backtest_baseline.edge_id)
    paper_edge_id = _plain_str_or_empty(edge_identity.paper_edge_id)
    if (
        not _is_hex64_string(baseline_edge_id)
        or not _is_hex64_string(paper_edge_id)
        or baseline_edge_id != paper_edge_id
    ):
        hard.append(_reason("baseline_edge_id_mismatch"))

    duration_hard, duration_satisfied = _duration_failures(gate_decision, methodology_v2)
    hard.extend(duration_hard)

    enforcement_hard, enforcement = _secondary_enforcement_failures(
        methodology_v2=methodology_v2, precondition=precondition, metrics_evidence=metrics_evidence
    )
    hard.extend(enforcement_hard)

    hard = sorted(set(hard))

    # Decimal verdict + advisory comparator run only on a fully proven chain.
    backtest_sharpe_repr = ""
    backtest_sharpe_decimal = ""
    sharpe_retention_ratio_decimal = ""
    sharpe_retention_satisfied = False
    comparison_verdict = _VERDICT_NOT_EVALUATED
    stage4_comparator_invoked = False
    comparison_performed = False
    comparator_status_echo = ""
    comparator_evaluated_echo = False
    comparator_passed_echo = False
    comparator_ratio_echo = ""
    comparator_required_min_echo = ""
    comparator_rejection_reasons_echo: tuple[str, ...] = ()
    paper_summary_digest = ""
    comparator_coherent = False

    decimal_satisfied = False
    if not hard:
        backtest_sharpe_repr = repr(backtest_baseline.backtest_sharpe)
        try:
            backtest_sharpe_decimal, sharpe_retention_ratio_decimal, decimal_satisfied = _decimal_retention_verdict(
                sharpe_evidence.paper_sharpe_annualized, backtest_sharpe_repr, methodology_v2.sharpe_retention_ratio
            )
        except ArithmeticError:
            # Unreachable under the scale-18 length cap and baseline magnitude bounds above; belt-and-braces
            # so a Decimal edge case can only fail closed, never crash past the comparator gate.
            hard = [_reason("retention_verdict_not_computable")]

    if not hard:
        # Internally constructed comparator input carrying the REAL digest-proven SM-4 metrics. The floats
        # here feed ONLY the advisory comparator echo — the authoritative enforcement above ran in Decimal
        # on the canonical scale-18 values. The single comparator fill-rate slot carries the conservative
        # minimum of the two enforced fill rates; a signed negative (favorable) slippage cannot be
        # represented by the comparator input contract and is echoed as ``None`` while remaining enforced
        # and digest-bound in this artifact's own ``paper_slippage_bps``.
        echo_fill_rate = min(enforcement.fill_quantity, enforcement.fill_episode)  # type: ignore[type-var]
        echo_slippage = (
            float(enforcement.slippage) if enforcement.slippage is not None and enforcement.slippage >= 0 else None
        )
        paper_summary = Stage4PaperSummary(
            paper_id=sharpe_evidence.paper_id,
            edge_id=paper_edge_id,
            started_at_ns=gate_decision.first_bucket_start_ns,
            stopped_at_ns=gate_decision.last_bucket_end_ns,
            paper_sharpe=float(sharpe_evidence.paper_sharpe_annualized),
            paper_hit_rate=float(enforcement.hit_rate),  # type: ignore[arg-type]
            paper_slippage_bps=echo_slippage,
            paper_fill_rate=float(echo_fill_rate),
            paper_trade_count=metrics_evidence.record_count,
        )
        paper_summary_digest = _canonical_digest(stage4_paper_summary_to_dict(paper_summary))

        comparator_result = compare_stage4(
            backtest_baseline,
            paper_summary,
            min_duration_days=float(methodology_v2.min_duration_days),
            min_sharpe_retention_ratio=float(Decimal(methodology_v2.sharpe_retention_ratio)),
        )
        stage4_comparator_invoked = True
        comparison_performed = True
        comparator_status_echo = _plain_str_or_empty(comparator_result.status)
        comparator_evaluated_echo = comparator_result.evaluated is True
        comparator_passed_echo = comparator_result.passed is True
        comparator_ratio_echo = _echo_float_repr(comparator_result.sharpe_retention_ratio)
        comparator_required_min_echo = _echo_float_repr(comparator_result.required_min_paper_sharpe)
        comparator_rejection_reasons_echo = _echo_reasons(comparator_result.rejection_reasons)

        coherence_hard = _comparator_coherence_failures(comparator_result, decimal_satisfied)
        if coherence_hard:
            hard = sorted(set(coherence_hard))
        else:
            comparator_coherent = True
            sharpe_retention_satisfied = decimal_satisfied
            comparison_verdict = _VERDICT_SATISFIED if decimal_satisfied else _VERDICT_NOT_SATISFIED

    ready = not hard
    reason_codes = tuple(hard)

    # Final READY invariant guard — READY is impossible unless every named gate independently re-proves:
    # all seven anchor digest triples, the baseline triple, every anchor contract, the SM bindings, the
    # cross-links, anchor scope, edge identity equality, the duration precheck, full real-metric presence,
    # the independently re-cleared thresholds, echo coherence, and one coherent comparator invocation.
    if ready and not (
        verified_sharpe_digest != ""
        and verified_methodology_v2_digest != ""
        and verified_edge_identity_digest != ""
        and verified_baseline_evidence_digest != ""
        and verified_gate_decision_digest != ""
        and verified_precondition_digest != ""
        and verified_metrics_evidence_digest != ""
        and baseline_digest != ""
        and baseline_evidence.baseline_digest == baseline_digest
        and not edge_contract_failures
        and not sharpe_contract_failures
        and not methodology_contract_failures
        and not gate_contract_failures
        and not baseline_evidence_contract_failures
        and not precondition_contract_failures
        and not metrics_contract_failures
        and not sm_binding_failures
        and not cross_link_failures
        and not anchor_scope_failures
        and baseline_edge_id == paper_edge_id
        and duration_satisfied
        and enforcement.all_present
        and enforcement.all_cleared
        and stage4_comparator_invoked
        and comparison_performed
        and comparator_coherent
        and comparison_verdict in (_VERDICT_SATISFIED, _VERDICT_NOT_SATISFIED)
    ):
        ready = False
        reason_codes = (_reason("ready_invariant_failed"),)
        comparison_verdict = _VERDICT_NOT_EVALUATED
        sharpe_retention_satisfied = False

    status = PaperStage4ComparisonEvidenceV2Status.READY if ready else PaperStage4ComparisonEvidenceV2Status.REJECTED
    secondary_metrics_enforced = ready and enforcement.all_present and enforcement.all_cleared

    evidence_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "evidence_version": _EVIDENCE_VERSION,
        "status": status,
        "ready": ready,
        "comparison_evidence_id": comparison_evidence_id,
        "correlation_id": correlation_id,
        "paper_id": _plain_str_or_empty(sharpe_evidence.paper_id),
        "series_id": _plain_str_or_empty(sharpe_evidence.series_id),
        "window_id": _plain_str_or_empty(sharpe_evidence.window_id),
        "market_symbol": _plain_str_or_empty(sharpe_evidence.market_symbol),
        "paper_edge_id": paper_edge_id,
        "baseline_id": _plain_str_or_empty(backtest_baseline.baseline_id),
        "strategy_id": _plain_str_or_empty(edge_identity.strategy_id),
        "strategy_version": _plain_str_or_empty(edge_identity.strategy_version),
        "strategy_family": _plain_str_or_empty(edge_identity.strategy_family),
        "edge_family": _plain_str_or_empty(edge_identity.edge_family),
        "market_type": _plain_str_or_empty(edge_identity.market_type),
        "secondary_metrics_policy_id": _plain_str_or_empty(methodology_v2.secondary_metrics_policy_id),
        "metrics_evidence_id": _plain_str_or_empty(metrics_evidence.evidence_id),
        "enforcement_precondition_id": _plain_str_or_empty(precondition.precondition_id),
        "methodology_v2_id": _plain_str_or_empty(methodology_v2.methodology_id),
        "expected_sharpe_evidence_digest": expected_sharpe_evidence_digest,
        "verified_sharpe_evidence_digest": verified_sharpe_digest,
        "expected_methodology_v2_digest": expected_methodology_v2_digest,
        "verified_methodology_v2_digest": verified_methodology_v2_digest,
        "expected_edge_identity_digest": expected_edge_identity_digest,
        "verified_edge_identity_digest": verified_edge_identity_digest,
        "expected_baseline_evidence_digest": expected_baseline_evidence_digest,
        "verified_baseline_evidence_digest": verified_baseline_evidence_digest,
        "expected_gate_decision_digest": expected_gate_decision_digest,
        "verified_gate_decision_digest": verified_gate_decision_digest,
        "expected_enforcement_precondition_digest": expected_enforcement_precondition_digest,
        "verified_enforcement_precondition_digest": verified_precondition_digest,
        "expected_metrics_evidence_digest": expected_metrics_evidence_digest,
        "verified_metrics_evidence_digest": verified_metrics_evidence_digest,
        "verified_secondary_metrics_policy_digest": (
            _safe_digest_value(precondition.policy_digest) if not sm_binding_failures else ""
        ),
        "expected_baseline_digest": expected_baseline_digest,
        "baseline_digest": baseline_digest,
        "paper_summary_digest": paper_summary_digest,
        "series_digest": _safe_digest_value(gate_decision.series_digest),
        "time_window_digest": _safe_digest_value(sharpe_evidence.time_window_digest),
        "metrics_summary_digest": _safe_digest_value(sharpe_evidence.metrics_summary_digest),
        "series_methodology_digest": _safe_digest_value(sharpe_evidence.methodology_digest),
        "paper_sharpe_annualized": _plain_str_or_empty(sharpe_evidence.paper_sharpe_annualized),
        "backtest_sharpe_repr": backtest_sharpe_repr,
        "backtest_sharpe_decimal": backtest_sharpe_decimal,
        "sharpe_retention_ratio_decimal": sharpe_retention_ratio_decimal,
        "sharpe_retention_threshold": _plain_str_or_empty(methodology_v2.sharpe_retention_ratio),
        "retention_comparison_operator": _RETENTION_COMPARISON_OPERATOR,
        "sharpe_retention_satisfied": sharpe_retention_satisfied,
        "min_duration_days": _safe_int_value(methodology_v2.min_duration_days),
        "window_duration_ns": _safe_int_value(gate_decision.window_duration_ns),
        "bucket_count": _safe_int_value(gate_decision.bucket_count),
        "duration_satisfied": duration_satisfied,
        "comparison_verdict": comparison_verdict,
        "paper_hit_rate": _scale18_or_none(metrics_evidence.hit_rate),
        "paper_fill_rate_by_quantity": _scale18_or_none(metrics_evidence.fill_rate_by_quantity),
        "paper_fill_rate_by_episode": _scale18_or_none(metrics_evidence.fill_rate_by_episode),
        "paper_slippage_bps": _scale18_or_none(metrics_evidence.average_slippage_bps),
        "decided_episode_count": _safe_int_value(metrics_evidence.decided_episode_count),
        "record_count": _safe_int_value(metrics_evidence.record_count),
        "approved_hit_rate_floor": _scale18_or_none(methodology_v2.approved_hit_rate_floor),
        "approved_fill_rate_floor": _scale18_or_none(methodology_v2.approved_fill_rate_floor),
        "approved_slippage_ceiling_bps": _scale18_or_none(methodology_v2.approved_slippage_ceiling_bps),
        "approved_min_decided_episode_count": _safe_optional_int(methodology_v2.approved_min_decided_episode_count),
        "hit_rate_operator": _EXPECTED_HIT_RATE_OPERATOR,
        "fill_rate_operator": _EXPECTED_FILL_RATE_OPERATOR,
        "slippage_operator": _EXPECTED_SLIPPAGE_OPERATOR,
        "hit_rate_floor_satisfied": enforcement.hit_pass,
        "fill_rate_by_quantity_floor_satisfied": enforcement.fill_quantity_pass,
        "fill_rate_by_episode_floor_satisfied": enforcement.fill_episode_pass,
        "fill_rate_floor_satisfied": enforcement.fill_pass,
        "slippage_ceiling_satisfied": enforcement.slippage_pass,
        "min_decided_episode_count_satisfied": enforcement.min_decided_pass,
        "secondary_thresholds_cleared": enforcement.all_cleared,
        "secondary_metrics_source": _SECONDARY_METRICS_SOURCE,
        "comparator_fill_rate_echo_policy": _COMPARATOR_FILL_RATE_ECHO_POLICY,
        "comparator_slippage_echo_policy": _COMPARATOR_SLIPPAGE_ECHO_POLICY,
        "risk_free_policy_id": _plain_str_or_empty(methodology_v2.risk_free_policy_id),
        "annualization_factor": _safe_int_value(methodology_v2.annualization_factor),
        "annualization_policy": _plain_str_or_empty(methodology_v2.annualization_policy),
        "stddev_policy": _plain_str_or_empty(methodology_v2.stddev_policy),
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "secondary_metrics_decimal_policy": _EXPECTED_SM_DECIMAL_POLICY,
        "retention_verdict_policy_id": _RETENTION_VERDICT_POLICY_ID,
        "baseline_sharpe_conversion_policy": _BASELINE_SHARPE_CONVERSION_POLICY,
        "sharpe_comparability_basis": _SHARPE_COMPARABILITY_BASIS,
        "paper_trade_count": _safe_int_value(metrics_evidence.record_count),
        "paper_trade_count_source": _PAPER_TRADE_COUNT_SOURCE,
        "stage4_comparator_invoked": stage4_comparator_invoked,
        "comparison_performed": comparison_performed,
        "comparator_status_echo": comparator_status_echo,
        "comparator_evaluated_echo": comparator_evaluated_echo,
        "comparator_passed_echo": comparator_passed_echo,
        "comparator_sharpe_retention_ratio_echo": comparator_ratio_echo,
        "comparator_required_min_paper_sharpe_echo": comparator_required_min_echo,
        "comparator_rejection_reasons_echo": comparator_rejection_reasons_echo,
        "comparator_float_advisory_only": True,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
        "secondary_metrics_enforced": secondary_metrics_enforced,
        "methodology_v2_consumed": ready,
        "enforcement_precondition_consumed": ready,
        "metrics_evidence_consumed": ready,
    }
    seed = PaperStage4ComparisonEvidenceV2(comparison_evidence_digest="", **evidence_fields)  # type: ignore[arg-type]
    return replace(seed, comparison_evidence_digest=paper_stage4_comparison_evidence_v2_digest(seed))


def _evidence_payload_from(evidence: PaperStage4ComparisonEvidenceV2) -> dict[str, object]:
    """Canonical payload over EVERY public field except the self-digest (complete by construction)."""

    payload: dict[str, object] = {}
    for field in fields(evidence):
        if field.name == "comparison_evidence_digest":
            continue
        value = getattr(evidence, field.name)
        if field.name == "status":
            payload[field.name] = evidence.status.value
        elif field.name == "metadata":
            payload[field.name] = [[key, item] for key, item in evidence.metadata]
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def paper_stage4_comparison_evidence_v2_to_dict(evidence: PaperStage4ComparisonEvidenceV2) -> dict[str, object]:
    """Canonical JSON-ready mapping for the comparison evidence v2, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["comparison_evidence_digest"] = evidence.comparison_evidence_digest
    return payload


def paper_stage4_comparison_evidence_v2_digest(evidence: PaperStage4ComparisonEvidenceV2) -> str:
    """Recompute the canonical comparison-evidence-v2 digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperStage4ComparisonEvidenceV2",
    "PaperStage4ComparisonEvidenceV2Error",
    "PaperStage4ComparisonEvidenceV2Status",
    "build_paper_stage4_comparison_evidence_v2",
    "paper_stage4_comparison_evidence_v2_digest",
    "paper_stage4_comparison_evidence_v2_to_dict",
]
