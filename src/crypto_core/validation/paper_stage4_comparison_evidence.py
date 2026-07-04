"""Deterministic paper Stage-4 comparison evidence (PRDV4 Stage 4, first authorized comparator run).

This validation artifact is the FIRST artifact allowed to call ``compare_stage4``. It consumes the merged
Stage-4 prerequisite chain at digest boundaries — ``PaperSharpeEvidence`` (PR #310),
``PaperVsBacktestMethodology`` (PR #311), ``PaperEdgeIdentityEvidence`` (PR #312),
``PaperStage4BacktestBaselineEvidence`` (PR #313) and ``PaperThirtyDayEvidenceGateDecision`` (PR #307) —
re-proves every self-digest via the public serializers, re-proves the caller-supplied
``Stage4BacktestBaseline`` by triple digest equality (recompute == caller anchor == the digest bound inside
the baseline evidence), cross-binds all artifacts into ONE chain (correlation / market / paper id / series
digests / edge id re-derivation), recomputes the Sharpe-retention verdict in ``Decimal``, and only then
invokes ``compare_stage4`` exactly once as an ADVISORY float reference.

Governance (user-approved for this slice):

* the Decimal recompute is the AUTHORITATIVE retention verdict
  (``decimal_retention_recompute_authoritative.v1``): full-precision ``paper / backtest`` under a local
  ``Decimal`` context (precision 80, ``ROUND_HALF_EVEN``) compared against the digest-bound methodology
  threshold with ``>=`` BEFORE output quantization; equality satisfies retention;
* the ``compare_stage4`` float output is an advisory echo only
  (``comparator_float_advisory_only=True``); if the Decimal verdict and the comparator verdict disagree the
  artifact fails closed (``REJECTED`` with
  ``paper_stage4_comparison_evidence:decimal_float_comparator_verdict_mismatch``);
* ``RETENTION_NOT_SATISFIED`` remains valid READY evidence — a failed retention is a real comparison
  outcome; only a later ``PaperStage4CompletionDecision`` may require ``sharpe_retention_satisfied=True``;
* the internally constructed ``Stage4PaperSummary`` uses ``paper_trade_count=0`` ONLY as a comparator-input
  placeholder (``paper_trade_count_source="not_carried_zero_placeholder.v1"``) — the consumed chain carries
  no trade count, so this is NOT actual paper trade-count evidence;
* the baseline Sharpe float is converted via ``Decimal(repr(...))``
  (``baseline_sharpe_conversion_policy="float_repr_decimal_conversion.v1"``) — the same shortest round-trip
  text canonical JSON binds into the baseline digest;
* comparability of the annualized paper Sharpe with the caller-supplied backtest Sharpe is DECLARED by the
  digest-bound methodology, not re-proven here (``sharpe_comparability_basis="policy_declared_not_reproven"``).

Status semantics: ``READY`` means only that trusted comparison evidence was constructed deterministically,
the comparator was invoked, and the Decimal and float verdicts agree — the verdict itself is the separate
digest-bound ``comparison_verdict`` (``RETENTION_SATISFIED`` | ``RETENTION_NOT_SATISFIED``). ``READY`` does
NOT mean PRDV4 Stage-4 completion. ``RETENTION_SATISFIED`` does NOT mean edge, profitability, live
readiness, shadow readiness, Deribit readiness, or operational readiness. Only a later
``PaperStage4CompletionDecision`` may decide Stage-4 completion; this artifact keeps
``prdv4_stage4_complete=False`` and ``stage4_completion_decided=False`` digest-bound.

It does NOT construct a ``Stage4BacktestBaseline``, does NOT set ``prdv4_stage4_complete``, does NOT decide
the operational-day gate, and does NOT prove edge, profitability, backtest validity, same-edge performance,
live readiness, shadow readiness, Deribit readiness, or operational readiness. It calls no wall-clock,
runtime, service, execution, venue, scheduler, filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields, replace
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
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
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    PaperVsBacktestMethodologyStatus,
    paper_vs_backtest_methodology_digest,
)
from crypto_core.validation.stage4_comparator import (
    Stage4BacktestBaseline,
    Stage4ComparisonResult,
    Stage4PaperSummary,
    compare_stage4,
    stage4_backtest_baseline_to_dict,
    stage4_paper_summary_to_dict,
)

_SCHEMA_VERSION = "paper-stage4-comparison-evidence.v1"
_EVIDENCE_VERSION = "paper-stage4-comparison-evidence.v1"
_REASON_PREFIX = "paper_stage4_comparison_evidence"

_EXPECTED_SHARPE_SCHEMA_VERSION = "paper-sharpe-evidence.v1"
_EXPECTED_METHODOLOGY_SCHEMA_VERSION = "paper-vs-backtest-methodology.v1"
_EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION = "paper-edge-identity-evidence.v1"
_EXPECTED_BASELINE_EVIDENCE_SCHEMA_VERSION = "paper-stage4-backtest-baseline-evidence.v1"
_EXPECTED_GATE_SCHEMA_VERSION = "paper-30day-evidence-gate-decision.v1"
_EXPECTED_COMPARISON_BASIS = "paper_vs_backtest_sharpe_retention.v1"
_EXPECTED_ENFORCED_GUARDRAIL_POLICY = "sharpe_retention_and_min_duration_only.v1"
# Consumer-boundary re-pin of the approved v1 comparison governance (mirrors the merged
# paper_vs_backtest_methodology builder constants): a resealed, digest-self-consistent methodology carrying a
# weakened threshold or duration must fail closed HERE — the verdict is never re-parameterized by a forgeable
# policy field alone.
_APPROVED_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_APPROVED_MIN_DURATION_DAYS = 30
_EDGE_ID_FORM = "hex64_sha256"
_EDGE_ID_DERIVATION_POLICY = "sha256_canonical_strategy_id_market_symbol.v1"

_RETENTION_VERDICT_POLICY_ID = "decimal_retention_recompute_authoritative.v1"
_BASELINE_SHARPE_CONVERSION_POLICY = "float_repr_decimal_conversion.v1"
_SHARPE_COMPARABILITY_BASIS = "policy_declared_not_reproven"
_PAPER_TRADE_COUNT_SOURCE = "not_carried_zero_placeholder.v1"
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
# could carry a canonical-but-pathologically-long value. The cap bounds the integer part to <= 41 digits
# (far above any real Sharpe), which together with the backtest-sharpe magnitude bounds below keeps every
# scale-18 quantization inside the precision-80 Decimal context, so an oversize value fails closed with a
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


class PaperStage4ComparisonEvidenceError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata / tokens)."""


class PaperStage4ComparisonEvidenceStatus(str, Enum):
    """Comparison evidence status. READY is never Stage-4 completion — only a trusted comparison record."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperStage4ComparisonEvidence:
    """Immutable, digest-bound paper Stage-4 comparison evidence (Decimal verdict authoritative).

    ``status=READY`` only when every consumed artifact re-proves its digest, the chain cross-binds into ONE
    chain, the caller-supplied baseline re-proves by triple digest equality, the Decimal Sharpe-retention
    verdict is computed, ``compare_stage4`` was invoked exactly once, and the Decimal and float verdicts
    agree. ``comparison_verdict`` carries the outcome (``RETENTION_SATISFIED`` | ``RETENTION_NOT_SATISFIED``)
    and is meaningful only when READY. READY / RETENTION_SATISFIED do NOT mean Stage-4 completion, edge,
    profitability, backtest validity, live/shadow/Deribit/operational readiness, or execution of any kind;
    only a later ``PaperStage4CompletionDecision`` may decide Stage-4 completion. ``paper_trade_count=0`` in
    the internally constructed summary is a comparator-input placeholder only
    (``paper_trade_count_source``), never actual trade-count evidence.
    """

    schema_version: str
    evidence_version: str
    status: PaperStage4ComparisonEvidenceStatus
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
    expected_sharpe_evidence_digest: str
    verified_sharpe_evidence_digest: str
    expected_comparison_methodology_digest: str
    verified_comparison_methodology_digest: str
    expected_edge_identity_digest: str
    verified_edge_identity_digest: str
    expected_baseline_evidence_digest: str
    verified_baseline_evidence_digest: str
    expected_gate_decision_digest: str
    verified_gate_decision_digest: str
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
    risk_free_policy_id: str
    annualization_factor: int
    annualization_policy: str
    stddev_policy: str
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    retention_verdict_policy_id: str
    baseline_sharpe_conversion_policy: str
    sharpe_comparability_basis: str
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
    prdv4_stage4_complete: bool = False
    stage4_completion_decided: bool = False
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


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _safe_digest_value(value: object) -> str:
    return value if _is_hex64_string(value) else ""


def _safe_int_value(value: object) -> int:
    return value if _is_exact_int(value) else 0


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperStage4ComparisonEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperStage4ComparisonEvidenceError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4ComparisonEvidenceError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4ComparisonEvidenceError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperStage4ComparisonEvidenceError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperStage4ComparisonEvidenceError(_reason("metadata_malformed"))
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


def _derive_paper_edge_id(strategy_id: str, market_symbol: str) -> str:
    """Recompute the approved paper edge-id derivation. Mirrors ``paper_edge_identity_evidence`` exactly.

    ``sha256(canonical_json({"strategy_id": ..., "market_symbol": ...}))`` with ``ensure_ascii=False`` — the
    same representation the edge-identity module uses to mint ``paper_edge_id``. Re-deriving it here defeats
    a resealed edge identity whose digest/form/policy fields are self-consistent but whose ``paper_edge_id``
    was not actually produced by the approved derivation.
    """
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
    """AUTHORITATIVE Decimal Sharpe-retention verdict — no float arithmetic on this path.

    Full-precision ``paper / backtest`` under a local Decimal context (precision 80, ROUND_HALF_EVEN),
    compared against the digest-bound methodology threshold with ``>=`` BEFORE output quantization (equality
    satisfies retention). Returns ``(quantized_backtest_sharpe, quantized_retention_ratio, satisfied)``.
    """
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
_METHODOLOGY_TRUE_FLAGS = ("paper_only", "methodology_snapshot", "policy_declared")
_METHODOLOGY_FALSE_FLAGS = (
    "hit_rate_floor_enforced",
    "fill_rate_floor_enforced",
    "slippage_ceiling_enforced",
    "drawdown_ceiling_enforced",
    "comparison_ready",
    "paper_vs_backtest_comparison_ready",
    "comparison_performed",
    "stage4_comparator_invoked",
    "thirty_day_gate_satisfied",
    "thirty_day_gate_decided",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "profitability_proven",
    "edge_proven",
    "edge_identity_proven",
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


def _flag_failures(
    artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...], reason_code: str
) -> list[str]:
    if any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    ):
        return [_reason(reason_code)]
    return []


def _baseline_value_failures(baseline: Stage4BacktestBaseline) -> list[str]:
    """Re-prove caller-supplied baseline well-formedness. Mirrors ``stage4_comparator._validate_baseline`` ranges.

    Additionally bounds the positive baseline Sharpe magnitude to [1e-18, 1e18] so the Decimal retention
    quantizations stay inside the precision-80 context (deterministic rejection, never a Decimal exception).
    """

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
        _flag_failures(sharpe_evidence, _SHARPE_TRUE_FLAGS, _SHARPE_FALSE_FLAGS, "sharpe_evidence_unsafe_flags")
    )
    return hard


def _methodology_failures(methodology: PaperVsBacktestMethodology, sharpe_evidence: PaperSharpeEvidence) -> list[str]:
    hard: list[str] = []
    if methodology.schema_version != _EXPECTED_METHODOLOGY_SCHEMA_VERSION:
        hard.append(_reason("methodology_schema_invalid"))
    if (
        methodology.status is not PaperVsBacktestMethodologyStatus.READY
        or methodology.ready is not True
        or methodology.reason_codes != ()
    ):
        hard.append(_reason("methodology_not_ready"))
    if (
        methodology.comparison_basis != _EXPECTED_COMPARISON_BASIS
        or methodology.enforced_guardrail_policy != _EXPECTED_ENFORCED_GUARDRAIL_POLICY
        or methodology.risk_free_policy_id != sharpe_evidence.risk_free_policy_id
        or methodology.annualization_factor != sharpe_evidence.annualization_factor
        or methodology.annualization_policy != sharpe_evidence.annualization_policy
        or methodology.stddev_policy != sharpe_evidence.stddev_policy
        or methodology.decimal_policy != sharpe_evidence.decimal_policy
        or methodology.decimal_scale != sharpe_evidence.decimal_scale
        or methodology.decimal_rounding != sharpe_evidence.decimal_rounding
        or methodology.decimal_internal_precision != sharpe_evidence.decimal_internal_precision
    ):
        hard.append(_reason("methodology_policy_mismatch"))
    if (
        not _is_scale18_decimal_string(methodology.sharpe_retention_ratio)
        or Decimal(methodology.sharpe_retention_ratio) <= 0
    ):
        hard.append(_reason("methodology_retention_threshold_invalid"))
    elif methodology.sharpe_retention_ratio != _APPROVED_SHARPE_RETENTION_RATIO:
        hard.append(_reason("methodology_retention_threshold_unapproved"))
    if not _is_positive_int(methodology.min_duration_days):
        hard.append(_reason("methodology_min_duration_invalid"))
    elif methodology.min_duration_days != _APPROVED_MIN_DURATION_DAYS:
        hard.append(_reason("methodology_min_duration_unapproved"))
    hard.extend(
        _flag_failures(methodology, _METHODOLOGY_TRUE_FLAGS, _METHODOLOGY_FALSE_FLAGS, "methodology_unsafe_flags")
    )
    return hard


def _gate_decision_failures(
    gate_decision: PaperThirtyDayEvidenceGateDecision, methodology: PaperVsBacktestMethodology
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
    if gate_decision.risk_free_policy_id != methodology.risk_free_policy_id:
        hard.append(_reason("gate_risk_free_policy_mismatch"))
    if (
        not _is_exact_int(gate_decision.gate_minimum_consecutive_bucket_count)
        or not _is_exact_int(methodology.min_duration_days)
        or gate_decision.gate_minimum_consecutive_bucket_count != methodology.min_duration_days
    ):
        hard.append(_reason("min_duration_policy_mismatch"))
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
        _flag_failures(
            baseline_evidence,
            _BASELINE_EVIDENCE_TRUE_FLAGS,
            _BASELINE_EVIDENCE_FALSE_FLAGS,
            "baseline_evidence_unsafe_flags",
        )
    )
    return hard


def _cross_link_failures(
    *,
    correlation_id: str,
    sharpe_evidence: PaperSharpeEvidence,
    methodology: PaperVsBacktestMethodology,
    edge_identity: PaperEdgeIdentityEvidence,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
) -> list[str]:
    hard: list[str] = []
    if any(
        artifact.correlation_id != correlation_id
        for artifact in (sharpe_evidence, methodology, edge_identity, baseline_evidence, gate_decision)
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _is_plain_non_empty_string(sharpe_evidence.market_symbol) or any(
        artifact.market_symbol != sharpe_evidence.market_symbol
        for artifact in (gate_decision, edge_identity, baseline_evidence)
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


def _duration_failures(
    gate_decision: PaperThirtyDayEvidenceGateDecision, methodology: PaperVsBacktestMethodology
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
    if not _is_positive_int(methodology.min_duration_days):
        return hard, False
    duration_satisfied = bucket_count >= methodology.min_duration_days and duration >= (
        methodology.min_duration_days * _DAY_NS
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


def build_paper_stage4_comparison_evidence(
    backtest_baseline: Stage4BacktestBaseline,
    *,
    expected_baseline_digest: str,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    expected_baseline_evidence_digest: str,
    sharpe_evidence: PaperSharpeEvidence,
    expected_sharpe_evidence_digest: str,
    methodology: PaperVsBacktestMethodology,
    expected_methodology_digest: str,
    edge_identity: PaperEdgeIdentityEvidence,
    expected_edge_identity_digest: str,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    expected_gate_decision_digest: str,
    comparison_evidence_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4ComparisonEvidence:
    """Build the first authorized Stage-4 paper-vs-backtest comparison evidence (Decimal verdict authoritative).

    Every consumed artifact must be the exact merged type and re-prove its self-digest against the caller's
    independent anchor; the caller-supplied ``backtest_baseline`` must re-prove by TRIPLE digest equality
    (recompute == ``expected_baseline_digest`` == ``baseline_evidence.baseline_digest``). ``compare_stage4``
    is invoked exactly once, only after every precondition passes, and only as an advisory float echo — the
    authoritative retention verdict is the Decimal recompute. Wrong-typed inputs, malformed anchors,
    malformed metadata, or forbidden BIST/live/order/capital/readiness/clock tokens raise
    ``PaperStage4ComparisonEvidenceError``; every trust/value failure maps to ``status=REJECTED``.
    """
    if type(backtest_baseline) is not Stage4BacktestBaseline:
        raise PaperStage4ComparisonEvidenceError(_reason("backtest_baseline_malformed"))
    if type(baseline_evidence) is not PaperStage4BacktestBaselineEvidence:
        raise PaperStage4ComparisonEvidenceError(_reason("baseline_evidence_malformed"))
    if type(sharpe_evidence) is not PaperSharpeEvidence:
        raise PaperStage4ComparisonEvidenceError(_reason("sharpe_evidence_malformed"))
    if type(methodology) is not PaperVsBacktestMethodology:
        raise PaperStage4ComparisonEvidenceError(_reason("methodology_malformed"))
    if type(edge_identity) is not PaperEdgeIdentityEvidence:
        raise PaperStage4ComparisonEvidenceError(_reason("edge_identity_malformed"))
    if type(gate_decision) is not PaperThirtyDayEvidenceGateDecision:
        raise PaperStage4ComparisonEvidenceError(_reason("gate_decision_malformed"))
    expected_baseline_digest = _require_hex64(expected_baseline_digest, "expected_baseline_digest")
    expected_baseline_evidence_digest = _require_hex64(
        expected_baseline_evidence_digest, "expected_baseline_evidence_digest"
    )
    expected_sharpe_evidence_digest = _require_hex64(expected_sharpe_evidence_digest, "expected_sharpe_evidence_digest")
    expected_methodology_digest = _require_hex64(expected_methodology_digest, "expected_methodology_digest")
    expected_edge_identity_digest = _require_hex64(expected_edge_identity_digest, "expected_edge_identity_digest")
    expected_gate_decision_digest = _require_hex64(expected_gate_decision_digest, "expected_gate_decision_digest")
    comparison_evidence_id = _require_plain_non_empty_string(comparison_evidence_id, "comparison_evidence_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (comparison_evidence_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperStage4ComparisonEvidenceError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperStage4ComparisonEvidenceError(_reason("clock_token_forbidden"))

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
    methodology_failures, verified_methodology_digest = _digest_reproof_failures(
        artifact=methodology,
        carried_digest=methodology.methodology_digest,
        expected_digest=expected_methodology_digest,
        compute=paper_vs_backtest_methodology_digest,
        reason_code="methodology_digest_mismatch",
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

    hard.extend(_edge_identity_failures(edge_identity))
    hard.extend(_sharpe_evidence_failures(sharpe_evidence))
    hard.extend(_methodology_failures(methodology, sharpe_evidence))
    hard.extend(_gate_decision_failures(gate_decision, methodology))
    hard.extend(
        _baseline_evidence_failures(baseline_evidence, backtest_baseline, edge_identity, verified_edge_identity_digest)
    )
    hard.extend(
        _cross_link_failures(
            correlation_id=correlation_id,
            sharpe_evidence=sharpe_evidence,
            methodology=methodology,
            edge_identity=edge_identity,
            baseline_evidence=baseline_evidence,
            gate_decision=gate_decision,
        )
    )

    # Same-edge identity: the baseline edge id must equal the re-proven paper edge identity.
    baseline_edge_id = _plain_str_or_empty(backtest_baseline.edge_id)
    paper_edge_id = _plain_str_or_empty(edge_identity.paper_edge_id)
    if (
        not _is_hex64_string(baseline_edge_id)
        or not _is_hex64_string(paper_edge_id)
        or baseline_edge_id != paper_edge_id
    ):
        hard.append(_reason("baseline_edge_id_mismatch"))

    duration_hard, duration_satisfied = _duration_failures(gate_decision, methodology)
    hard.extend(duration_hard)

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

    decimal_satisfied = False
    if not hard:
        backtest_sharpe_repr = repr(backtest_baseline.backtest_sharpe)
        try:
            backtest_sharpe_decimal, sharpe_retention_ratio_decimal, decimal_satisfied = _decimal_retention_verdict(
                sharpe_evidence.paper_sharpe_annualized, backtest_sharpe_repr, methodology.sharpe_retention_ratio
            )
        except ArithmeticError:
            # Unreachable under the scale-18 length cap and baseline magnitude bounds above; belt-and-braces
            # so a Decimal edge case can only fail closed, never crash past the comparator gate.
            hard = [_reason("retention_verdict_not_computable")]

    if not hard:
        # Internally constructed comparator input. ``paper_trade_count=0`` is a placeholder only (the consumed
        # chain carries no trade count) and ``float(...)`` here feeds ONLY the advisory comparator echo.
        paper_summary = Stage4PaperSummary(
            paper_id=sharpe_evidence.paper_id,
            edge_id=paper_edge_id,
            started_at_ns=gate_decision.first_bucket_start_ns,
            stopped_at_ns=gate_decision.last_bucket_end_ns,
            paper_sharpe=float(sharpe_evidence.paper_sharpe_annualized),
            paper_hit_rate=None,
            paper_slippage_bps=None,
            paper_fill_rate=None,
            paper_trade_count=0,
        )
        paper_summary_digest = _canonical_digest(stage4_paper_summary_to_dict(paper_summary))

        comparator_result = compare_stage4(
            backtest_baseline,
            paper_summary,
            min_duration_days=float(methodology.min_duration_days),
            min_sharpe_retention_ratio=float(Decimal(methodology.sharpe_retention_ratio)),
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
            sharpe_retention_satisfied = decimal_satisfied
            comparison_verdict = _VERDICT_SATISFIED if decimal_satisfied else _VERDICT_NOT_SATISFIED

    if hard:
        status = PaperStage4ComparisonEvidenceStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
    else:
        status = PaperStage4ComparisonEvidenceStatus.READY
        ready = True
        reason_codes = ()

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
        "expected_sharpe_evidence_digest": expected_sharpe_evidence_digest,
        "verified_sharpe_evidence_digest": verified_sharpe_digest,
        "expected_comparison_methodology_digest": expected_methodology_digest,
        "verified_comparison_methodology_digest": verified_methodology_digest,
        "expected_edge_identity_digest": expected_edge_identity_digest,
        "verified_edge_identity_digest": verified_edge_identity_digest,
        "expected_baseline_evidence_digest": expected_baseline_evidence_digest,
        "verified_baseline_evidence_digest": verified_baseline_evidence_digest,
        "expected_gate_decision_digest": expected_gate_decision_digest,
        "verified_gate_decision_digest": verified_gate_decision_digest,
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
        "sharpe_retention_threshold": _plain_str_or_empty(methodology.sharpe_retention_ratio),
        "retention_comparison_operator": _RETENTION_COMPARISON_OPERATOR,
        "sharpe_retention_satisfied": sharpe_retention_satisfied,
        "min_duration_days": _safe_int_value(methodology.min_duration_days),
        "window_duration_ns": _safe_int_value(gate_decision.window_duration_ns),
        "bucket_count": _safe_int_value(gate_decision.bucket_count),
        "duration_satisfied": duration_satisfied,
        "comparison_verdict": comparison_verdict,
        "risk_free_policy_id": _plain_str_or_empty(methodology.risk_free_policy_id),
        "annualization_factor": _safe_int_value(methodology.annualization_factor),
        "annualization_policy": _plain_str_or_empty(methodology.annualization_policy),
        "stddev_policy": _plain_str_or_empty(methodology.stddev_policy),
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "retention_verdict_policy_id": _RETENTION_VERDICT_POLICY_ID,
        "baseline_sharpe_conversion_policy": _BASELINE_SHARPE_CONVERSION_POLICY,
        "sharpe_comparability_basis": _SHARPE_COMPARABILITY_BASIS,
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
    }
    seed = PaperStage4ComparisonEvidence(comparison_evidence_digest="", **evidence_fields)  # type: ignore[arg-type]
    return replace(seed, comparison_evidence_digest=paper_stage4_comparison_evidence_digest(seed))


def _evidence_payload_from(evidence: PaperStage4ComparisonEvidence) -> dict[str, object]:
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


def paper_stage4_comparison_evidence_to_dict(evidence: PaperStage4ComparisonEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for the comparison evidence, including its self-digest."""

    payload = _evidence_payload_from(evidence)
    payload["comparison_evidence_digest"] = evidence.comparison_evidence_digest
    return payload


def paper_stage4_comparison_evidence_digest(evidence: PaperStage4ComparisonEvidence) -> str:
    """Recompute the canonical comparison-evidence digest, excluding only the self-digest field."""

    return _canonical_digest(_evidence_payload_from(evidence))


__all__ = [
    "PaperStage4ComparisonEvidence",
    "PaperStage4ComparisonEvidenceError",
    "PaperStage4ComparisonEvidenceStatus",
    "build_paper_stage4_comparison_evidence",
    "paper_stage4_comparison_evidence_digest",
    "paper_stage4_comparison_evidence_to_dict",
]
