"""Deterministic paper Stage-4 completion decision (PRDV4 Stage 4, v1 = BLOCKED completion).

This validation artifact is the terminal governance consumer of the merged Stage-4 paper-methodology chain.
It consumes the merged ``PaperStage4ComparisonEvidence`` (PR #316) together with the five upstream artifacts
that comparison evidence bound — ``PaperSharpeEvidence`` (PR #310), ``PaperVsBacktestMethodology`` (PR #311),
``PaperEdgeIdentityEvidence`` (PR #312), ``PaperStage4BacktestBaselineEvidence`` (PR #313) and
``PaperThirtyDayEvidenceGateDecision`` (PR #307) — re-proves every self-digest via the public serializers,
re-proves that the comparison evidence consumed EXACTLY the upstream artifacts supplied to this builder
(reseal defense: each ``verified_*`` digest carried by the comparison evidence must equal the digest this
builder recomputes from the artifact it was handed), re-derives the paper edge id, re-pins the approved v1
comparison governance, independently recomputes the quantized Decimal Sharpe-retention ratio from the carried
inputs, and renders ONE deterministic completion decision.

Governance (user-approved Option B for this slice):

* ``prdv4_stage4_complete`` is STRUCTURALLY FALSE in v1 — no code path may set it True. PRDV4 §"Stage 4:
  Paper Trading" requires "Minimum 30 days live paper trading" and a four-metric paper-vs-backtest
  comparison (Sharpe, hit rate, slippage, fill rate). The merged chain proves the Sharpe-retention gate over
  a >=30-consecutive-UTC-daily-bucket deterministic return series under INJECTED deterministic time
  (``timestamp_origin_proven=False``) — it does NOT prove 30 days of live paper trading, and methodology v1
  declares hit/fill/slippage as review-only (not enforced). Completion is therefore BLOCKED, digest-bound;
* READY decisions carry ``completion_verdict="STAGE4_COMPLETION_BLOCKED"`` plus the exact deterministic
  ``stage4_completion_blockers`` tuple naming why full PRDV4 Stage-4 completion cannot be set yet;
* the paper-METHODOLOGY outcome is decided separately and honestly:
  ``paper_methodology_verdict="STAGE4_PAPER_METHOD_COMPLETE"`` (with the narrow
  ``paper_methodology_complete=True`` flag) when the trusted comparison evidence proved
  ``RETENTION_SATISFIED``, or ``"STAGE4_PAPER_METHOD_NOT_COMPLETE"`` when it proved
  ``RETENTION_NOT_SATISFIED``. ``paper_methodology_complete=True`` does NOT mean PRDV4 Stage-4 completion;
* true Stage-4 completion requires a FUTURE schema/version consuming a multi-session per-UTC-day
  operational-day evidence chain, under separate explicit authorization
  (``completion_policy_id="stage4_completion_blocked_pending_operational_day_source.v1"``).

Status semantics: ``READY`` means only that a trusted, digest-proven completion decision was rendered — it
does NOT mean Stage-4 completion. ``STAGE4_PAPER_METHOD_COMPLETE`` does NOT mean edge, profitability, live
readiness, shadow readiness, Deribit readiness, or operational readiness. Any digest / binding / schema /
status / policy / coherence failure maps to ``status=REJECTED`` (fail-closed); wrong-typed or malformed
caller input raises ``PaperStage4CompletionDecisionError``.

This module re-runs NO comparator: it imports nothing from the comparator module, constructs no comparator
input objects, and consumes only already-proven evidence. It does NOT implement an operational-day source or
gate, does NOT prove edge, profitability, backtest validity, or same-edge performance, and calls no
wall-clock, runtime, service, execution, venue, scheduler, filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
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
from crypto_core.validation.paper_stage4_comparison_evidence import (
    PaperStage4ComparisonEvidence,
    PaperStage4ComparisonEvidenceStatus,
    paper_stage4_comparison_evidence_digest,
)
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    PaperVsBacktestMethodologyStatus,
    paper_vs_backtest_methodology_digest,
)

_SCHEMA_VERSION = "paper-stage4-completion-decision.v1"
_DECISION_VERSION = "paper-stage4-completion-decision.v1"
_REASON_PREFIX = "paper_stage4_completion_decision"

_EXPECTED_COMPARISON_SCHEMA_VERSION = "paper-stage4-comparison-evidence.v1"
_EXPECTED_SHARPE_SCHEMA_VERSION = "paper-sharpe-evidence.v1"
_EXPECTED_METHODOLOGY_SCHEMA_VERSION = "paper-vs-backtest-methodology.v1"
_EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION = "paper-edge-identity-evidence.v1"
_EXPECTED_BASELINE_EVIDENCE_SCHEMA_VERSION = "paper-stage4-backtest-baseline-evidence.v1"
_EXPECTED_GATE_SCHEMA_VERSION = "paper-30day-evidence-gate-decision.v1"
_EXPECTED_COMPARISON_BASIS = "paper_vs_backtest_sharpe_retention.v1"
_EXPECTED_ENFORCED_GUARDRAIL_POLICY = "sharpe_retention_and_min_duration_only.v1"
_EDGE_ID_FORM = "hex64_sha256"
_EDGE_ID_DERIVATION_POLICY = "sha256_canonical_strategy_id_market_symbol.v1"

# Consumer-boundary re-pin of the approved v1 comparison governance (mirrors the merged methodology and
# comparison-evidence constants): a resealed, digest-self-consistent input carrying weakened governance must
# fail closed HERE — the completion decision never trusts forgeable policy fields alone.
_APPROVED_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_APPROVED_MIN_DURATION_DAYS = 30
_APPROVED_RETENTION_OPERATOR = ">="
_APPROVED_RETENTION_VERDICT_POLICY_ID = "decimal_retention_recompute_authoritative.v1"
_APPROVED_BASELINE_SHARPE_CONVERSION_POLICY = "float_repr_decimal_conversion.v1"
_APPROVED_SHARPE_COMPARABILITY_BASIS = "policy_declared_not_reproven"
_APPROVED_PAPER_TRADE_COUNT_SOURCE = "not_carried_zero_placeholder.v1"
_APPROVED_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"

_VERDICT_SATISFIED = "RETENTION_SATISFIED"
_VERDICT_NOT_SATISFIED = "RETENTION_NOT_SATISFIED"
_COMPARATOR_STATUS_PASS = "PASS"  # noqa: S105 - status label, not a credential.
_COMPARATOR_STATUS_REJECT = "REJECT"  # noqa: S105 - status label, not a credential.
_COMPARATOR_BELOW_THRESHOLD_REASON = "stage4:paper_sharpe_below_backtest_threshold"

_METHOD_VERDICT_COMPLETE = "STAGE4_PAPER_METHOD_COMPLETE"
_METHOD_VERDICT_NOT_COMPLETE = "STAGE4_PAPER_METHOD_NOT_COMPLETE"
_METHOD_VERDICT_NOT_DECIDED = ""
_COMPLETION_VERDICT_BLOCKED = "STAGE4_COMPLETION_BLOCKED"
_COMPLETION_VERDICT_NOT_DECIDED = ""
_COMPLETION_SCOPE = "prdv4_stage4_full_definition.v1"
_COMPLETION_POLICY_ID = "stage4_completion_blocked_pending_operational_day_source.v1"
# Deterministic, digest-bound blockers naming why full PRDV4 Stage-4 completion cannot be set in v1
# (PRDV4 §"Stage 4: Paper Trading": "Minimum 30 days live paper trading" + four-metric comparison).
_STAGE4_COMPLETION_BLOCKERS = (
    "prdv4_minimum_30_day_live_paper_trading_unproven",
    "operational_day_evidence_source_unavailable",
    "timestamp_origin_not_proven_injected_deterministic_time_only",
    "secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1",
)

_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
_DECIMAL_QUANTUM = Decimal(1).scaleb(-_DECIMAL_SCALE)

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
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


class PaperStage4CompletionDecisionError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata / tokens)."""


class PaperStage4CompletionDecisionStatus(str, Enum):
    """Completion decision status. READY is never Stage-4 completion — only a trusted, blocked decision."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperStage4CompletionDecision:
    """Immutable, digest-bound paper Stage-4 completion decision (v1 = BLOCKED completion).

    ``status=READY`` only when every consumed artifact re-proves its digest, the comparison evidence is
    proven to have consumed EXACTLY the upstream artifacts supplied to this builder, the approved v1
    governance re-pins hold, and the carried retention verdict is internally coherent (verdict <-> bool <->
    comparator echo <-> independent Decimal recompute). ``paper_methodology_verdict`` carries the honest
    methodology outcome; ``completion_verdict`` is always ``STAGE4_COMPLETION_BLOCKED`` on READY in v1 and
    ``prdv4_stage4_complete`` is structurally False on every path. ``paper_methodology_complete=True`` does
    NOT mean PRDV4 Stage-4 completion, edge, profitability, backtest validity, live/shadow/Deribit/
    operational readiness, or execution of any kind. True Stage-4 completion requires a future
    schema/version with operational-day evidence and separate authorization.
    """

    schema_version: str
    decision_version: str
    status: PaperStage4CompletionDecisionStatus
    ready: bool
    completion_decision_id: str
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
    expected_comparison_evidence_digest: str
    verified_comparison_evidence_digest: str
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
    baseline_digest: str
    paper_summary_digest: str
    series_digest: str
    time_window_digest: str
    metrics_summary_digest: str
    series_methodology_digest: str
    paper_methodology_verdict: str
    paper_methodology_complete: bool
    comparison_verdict_echo: str
    sharpe_retention_satisfied_echo: bool
    sharpe_retention_ratio_decimal: str
    sharpe_retention_threshold: str
    retention_comparison_operator: str
    min_duration_days: int
    bucket_count: int
    window_duration_ns: int
    completion_verdict: str
    stage4_completion_decided: bool
    stage4_completion_blockers: tuple[str, ...]
    completion_scope: str
    completion_policy_id: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    completion_decision_digest: str
    paper_only: bool = True
    comparison_evidence_consumed: bool = True
    operational_day_gate_deferred: bool = True
    operational_day_evidence_consumed: bool = False
    timestamp_origin_proven: bool = False
    real_time_paper_operation_proven: bool = False
    prdv4_stage4_complete: bool = False
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


def _plain_str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _safe_digest_value(value: object) -> str:
    return value if _is_hex64_string(value) else ""


def _safe_int_value(value: object) -> int:
    return value if _is_exact_int(value) else 0


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperStage4CompletionDecisionError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperStage4CompletionDecisionError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4CompletionDecisionError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4CompletionDecisionError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperStage4CompletionDecisionError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperStage4CompletionDecisionError(_reason("metadata_malformed"))
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


def _recompute_retention_verdict(
    paper_sharpe_annualized: str, backtest_sharpe_repr: str, retention_threshold: str
) -> tuple[str, bool]:
    """Independently recompute the quantized retention ratio and verdict — no float arithmetic on this path.

    Reproduces the merged comparison-evidence Decimal policy exactly (local context precision 80,
    ROUND_HALF_EVEN, full-precision ``paper / backtest`` compared ``>=`` threshold BEFORE quantization) from
    the SAME digest-bound input strings, so a resealed verdict that does not follow from its own carried
    inputs fails closed here.
    """
    with localcontext() as context:
        context.prec = _DECIMAL_INTERNAL_PRECISION
        context.rounding = ROUND_HALF_EVEN
        paper_decimal = Decimal(paper_sharpe_annualized)
        backtest_decimal = Decimal(backtest_sharpe_repr)
        threshold_decimal = Decimal(retention_threshold)
        retention_ratio = paper_decimal / backtest_decimal
        satisfied = retention_ratio >= threshold_decimal
        return _format_public_decimal(retention_ratio), satisfied


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
_COMPARISON_TRUE_FLAGS = ("paper_only", "comparator_float_advisory_only")
_COMPARISON_FALSE_FLAGS = (
    "prdv4_stage4_complete",
    "stage4_completion_decided",
    "edge_proven",
    "profitability_proven",
    "same_edge_as_backtest_proven",
    "backtest_validity_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "operational_readiness",
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
)


def _flag_failures(
    artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...], reason_code: str
) -> list[str]:
    if any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    ):
        return [_reason(reason_code)]
    return []


def _sharpe_evidence_failures(sharpe_evidence: PaperSharpeEvidence) -> list[str]:
    hard: list[str] = []
    if sharpe_evidence.schema_version != _EXPECTED_SHARPE_SCHEMA_VERSION:
        hard.append(_reason("sharpe_evidence_schema_invalid"))
    if (
        sharpe_evidence.status is not PaperSharpeEvidenceStatus.READY
        or sharpe_evidence.ready is not True
        or sharpe_evidence.reason_codes != ()
        or sharpe_evidence.sharpe_computed is not True
    ):
        hard.append(_reason("sharpe_evidence_not_ready"))
    hard.extend(
        _flag_failures(sharpe_evidence, _SHARPE_TRUE_FLAGS, _SHARPE_FALSE_FLAGS, "sharpe_evidence_unsafe_flags")
    )
    return hard


def _methodology_failures(methodology: PaperVsBacktestMethodology) -> list[str]:
    hard: list[str] = []
    if methodology.schema_version != _EXPECTED_METHODOLOGY_SCHEMA_VERSION:
        hard.append(_reason("methodology_schema_invalid"))
    if (
        methodology.status is not PaperVsBacktestMethodologyStatus.READY
        or methodology.ready is not True
        or methodology.reason_codes != ()
    ):
        hard.append(_reason("methodology_not_ready"))
    hard.extend(
        _flag_failures(methodology, _METHODOLOGY_TRUE_FLAGS, _METHODOLOGY_FALSE_FLAGS, "methodology_unsafe_flags")
    )
    return hard


def _edge_identity_failures(edge_identity: PaperEdgeIdentityEvidence) -> list[str]:
    hard: list[str] = []
    if edge_identity.schema_version != _EXPECTED_EDGE_IDENTITY_SCHEMA_VERSION:
        hard.append(_reason("edge_identity_schema_invalid"))
    if (
        edge_identity.status is not PaperEdgeIdentityEvidenceStatus.READY
        or edge_identity.ready is not True
        or edge_identity.reason_codes != ()
        or edge_identity.edge_identity_resolved is not True
        or edge_identity.strategy_spec_identity_proven is not True
    ):
        hard.append(_reason("edge_identity_not_ready"))
    if (
        not _is_hex64_string(edge_identity.paper_edge_id)
        or edge_identity.edge_id_form != _EDGE_ID_FORM
        or edge_identity.edge_id_derivation_policy != _EDGE_ID_DERIVATION_POLICY
        or not _is_plain_non_empty_string(edge_identity.strategy_id)
        or not _is_plain_non_empty_string(edge_identity.market_symbol)
        or _derive_paper_edge_id(edge_identity.strategy_id, edge_identity.market_symbol) != edge_identity.paper_edge_id
    ):
        hard.append(_reason("edge_id_derivation_mismatch"))
    hard.extend(
        _flag_failures(
            edge_identity, _EDGE_IDENTITY_TRUE_FLAGS, _EDGE_IDENTITY_FALSE_FLAGS, "edge_identity_unsafe_flags"
        )
    )
    return hard


def _baseline_evidence_failures(baseline_evidence: PaperStage4BacktestBaselineEvidence) -> list[str]:
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
    hard.extend(
        _flag_failures(
            baseline_evidence,
            _BASELINE_EVIDENCE_TRUE_FLAGS,
            _BASELINE_EVIDENCE_FALSE_FLAGS,
            "baseline_evidence_unsafe_flags",
        )
    )
    return hard


def _gate_decision_failures(gate_decision: PaperThirtyDayEvidenceGateDecision) -> list[str]:
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
        or gate_decision.thirty_day_gate_satisfied is not True
    ):
        hard.append(_reason("gate_decision_not_ready"))
    hard.extend(_flag_failures(gate_decision, _GATE_TRUE_FLAGS, _GATE_FALSE_FLAGS, "gate_decision_unsafe_flags"))
    return hard


def _comparison_evidence_failures(comparison_evidence: PaperStage4ComparisonEvidence) -> list[str]:
    hard: list[str] = []
    if (
        comparison_evidence.schema_version != _EXPECTED_COMPARISON_SCHEMA_VERSION
        or comparison_evidence.evidence_version != _EXPECTED_COMPARISON_SCHEMA_VERSION
    ):
        hard.append(_reason("comparison_evidence_schema_invalid"))
    if (
        comparison_evidence.status is not PaperStage4ComparisonEvidenceStatus.READY
        or comparison_evidence.ready is not True
        or comparison_evidence.reason_codes != ()
    ):
        hard.append(_reason("comparison_evidence_not_ready"))
    if comparison_evidence.stage4_comparator_invoked is not True:
        hard.append(_reason("comparator_not_invoked_upstream"))
    if comparison_evidence.comparison_performed is not True:
        hard.append(_reason("comparison_not_performed"))
    hard.extend(
        _flag_failures(
            comparison_evidence, _COMPARISON_TRUE_FLAGS, _COMPARISON_FALSE_FLAGS, "comparison_evidence_unsafe_flags"
        )
    )
    return hard


def _governance_repin_failures(
    comparison_evidence: PaperStage4ComparisonEvidence,
    methodology: PaperVsBacktestMethodology,
    sharpe_evidence: PaperSharpeEvidence,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
) -> list[str]:
    """Re-pin the approved v1 governance at the completion boundary — never trust forgeable policy fields."""

    hard: list[str] = []
    if (
        comparison_evidence.sharpe_retention_threshold != _APPROVED_SHARPE_RETENTION_RATIO
        or methodology.sharpe_retention_ratio != _APPROVED_SHARPE_RETENTION_RATIO
    ):
        hard.append(_reason("retention_threshold_unapproved"))
    if (
        comparison_evidence.min_duration_days != _APPROVED_MIN_DURATION_DAYS
        or methodology.min_duration_days != _APPROVED_MIN_DURATION_DAYS
        or gate_decision.gate_minimum_consecutive_bucket_count != _APPROVED_MIN_DURATION_DAYS
    ):
        hard.append(_reason("min_duration_unapproved"))
    if (
        comparison_evidence.retention_comparison_operator != _APPROVED_RETENTION_OPERATOR
        or comparison_evidence.retention_verdict_policy_id != _APPROVED_RETENTION_VERDICT_POLICY_ID
        or comparison_evidence.baseline_sharpe_conversion_policy != _APPROVED_BASELINE_SHARPE_CONVERSION_POLICY
        or comparison_evidence.sharpe_comparability_basis != _APPROVED_SHARPE_COMPARABILITY_BASIS
        or comparison_evidence.paper_trade_count_source != _APPROVED_PAPER_TRADE_COUNT_SOURCE
        or comparison_evidence.decimal_policy != _DECIMAL_POLICY
        or comparison_evidence.decimal_scale != _DECIMAL_SCALE
        or comparison_evidence.decimal_rounding != _DECIMAL_ROUNDING
        or comparison_evidence.decimal_internal_precision != _DECIMAL_INTERNAL_PRECISION
        or comparison_evidence.risk_free_policy_id != _APPROVED_RISK_FREE_POLICY_ID
        or methodology.comparison_basis != _EXPECTED_COMPARISON_BASIS
        or methodology.enforced_guardrail_policy != _EXPECTED_ENFORCED_GUARDRAIL_POLICY
        or methodology.risk_free_policy_id != _APPROVED_RISK_FREE_POLICY_ID
        or methodology.decimal_policy != _DECIMAL_POLICY
        or methodology.decimal_scale != _DECIMAL_SCALE
        or methodology.decimal_rounding != _DECIMAL_ROUNDING
        or methodology.decimal_internal_precision != _DECIMAL_INTERNAL_PRECISION
        or sharpe_evidence.risk_free_policy_id != _APPROVED_RISK_FREE_POLICY_ID
        or sharpe_evidence.decimal_policy != _DECIMAL_POLICY
        or sharpe_evidence.decimal_scale != _DECIMAL_SCALE
        or sharpe_evidence.decimal_rounding != _DECIMAL_ROUNDING
        or sharpe_evidence.decimal_internal_precision != _DECIMAL_INTERNAL_PRECISION
        or gate_decision.risk_free_policy_id != _APPROVED_RISK_FREE_POLICY_ID
    ):
        hard.append(_reason("governance_repin_mismatch"))
    return hard


def _comparison_binding_failures(
    comparison_evidence: PaperStage4ComparisonEvidence,
    *,
    verified_sharpe_digest: str,
    verified_methodology_digest: str,
    verified_edge_identity_digest: str,
    verified_baseline_evidence_digest: str,
    verified_gate_decision_digest: str,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    sharpe_evidence: PaperSharpeEvidence,
) -> list[str]:
    """Reseal defense: the comparison evidence must have consumed EXACTLY the artifacts supplied now."""

    hard: list[str] = []
    pairs = (
        (comparison_evidence.expected_sharpe_evidence_digest, comparison_evidence.verified_sharpe_evidence_digest),
        (
            comparison_evidence.expected_comparison_methodology_digest,
            comparison_evidence.verified_comparison_methodology_digest,
        ),
        (comparison_evidence.expected_edge_identity_digest, comparison_evidence.verified_edge_identity_digest),
        (
            comparison_evidence.expected_baseline_evidence_digest,
            comparison_evidence.verified_baseline_evidence_digest,
        ),
        (comparison_evidence.expected_gate_decision_digest, comparison_evidence.verified_gate_decision_digest),
    )
    if any(expected != verified or not _is_hex64_string(verified) for expected, verified in pairs):
        hard.append(_reason("comparison_binding_mismatch"))
    elif (
        comparison_evidence.verified_sharpe_evidence_digest != verified_sharpe_digest
        or comparison_evidence.verified_comparison_methodology_digest != verified_methodology_digest
        or comparison_evidence.verified_edge_identity_digest != verified_edge_identity_digest
        or comparison_evidence.verified_baseline_evidence_digest != verified_baseline_evidence_digest
        or comparison_evidence.verified_gate_decision_digest != verified_gate_decision_digest
    ):
        hard.append(_reason("comparison_binding_mismatch"))
    if (
        not _is_hex64_string(comparison_evidence.baseline_digest)
        or comparison_evidence.baseline_digest != baseline_evidence.baseline_digest
    ):
        hard.append(_reason("baseline_digest_binding_mismatch"))
    if not _is_hex64_string(comparison_evidence.paper_summary_digest) or any(
        not _is_hex64_string(value)
        for value in (
            comparison_evidence.series_digest,
            comparison_evidence.time_window_digest,
            comparison_evidence.metrics_summary_digest,
            comparison_evidence.series_methodology_digest,
        )
    ):
        hard.append(_reason("comparison_binding_mismatch"))
    if comparison_evidence.paper_sharpe_annualized != sharpe_evidence.paper_sharpe_annualized:
        hard.append(_reason("comparison_binding_mismatch"))
    return hard


def _cross_link_failures(
    *,
    correlation_id: str,
    comparison_evidence: PaperStage4ComparisonEvidence,
    sharpe_evidence: PaperSharpeEvidence,
    methodology: PaperVsBacktestMethodology,
    edge_identity: PaperEdgeIdentityEvidence,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
) -> list[str]:
    hard: list[str] = []
    if any(
        artifact.correlation_id != correlation_id
        for artifact in (
            comparison_evidence,
            sharpe_evidence,
            methodology,
            edge_identity,
            baseline_evidence,
            gate_decision,
        )
    ):
        hard.append(_reason("correlation_id_mismatch"))
    if not _is_plain_non_empty_string(comparison_evidence.market_symbol) or any(
        artifact.market_symbol != comparison_evidence.market_symbol
        for artifact in (sharpe_evidence, gate_decision, edge_identity, baseline_evidence)
    ):
        hard.append(_reason("market_symbol_mismatch"))
    if not _is_plain_non_empty_string(comparison_evidence.paper_id) or any(
        artifact.paper_id != comparison_evidence.paper_id
        for artifact in (sharpe_evidence, edge_identity, baseline_evidence)
    ):
        hard.append(_reason("paper_id_mismatch"))
    if (
        comparison_evidence.series_id != sharpe_evidence.series_id
        or comparison_evidence.series_id != gate_decision.series_id
        or comparison_evidence.window_id != sharpe_evidence.window_id
        or comparison_evidence.window_id != gate_decision.window_id
        or comparison_evidence.series_digest != gate_decision.series_digest
        or comparison_evidence.series_digest != sharpe_evidence.verified_daily_return_series_digest
        or comparison_evidence.time_window_digest != sharpe_evidence.time_window_digest
        or comparison_evidence.time_window_digest != gate_decision.time_window_digest
        or comparison_evidence.metrics_summary_digest != sharpe_evidence.metrics_summary_digest
        or comparison_evidence.metrics_summary_digest != gate_decision.metrics_summary_digest
        or comparison_evidence.series_methodology_digest != sharpe_evidence.methodology_digest
        or comparison_evidence.series_methodology_digest != gate_decision.methodology_digest
        or comparison_evidence.bucket_count != gate_decision.bucket_count
        or comparison_evidence.bucket_count != sharpe_evidence.bucket_count
        or comparison_evidence.window_duration_ns != gate_decision.window_duration_ns
        or comparison_evidence.duration_satisfied is not True
    ):
        hard.append(_reason("series_binding_mismatch"))
    if (
        comparison_evidence.paper_edge_id != edge_identity.paper_edge_id
        or comparison_evidence.paper_edge_id != baseline_evidence.paper_edge_id
        or baseline_evidence.edge_id != edge_identity.paper_edge_id
        or comparison_evidence.baseline_id != baseline_evidence.baseline_id
        or comparison_evidence.strategy_id != edge_identity.strategy_id
    ):
        hard.append(_reason("comparison_binding_mismatch"))
    return hard


def _verdict_coherence_failures(
    comparison_evidence: PaperStage4ComparisonEvidence,
    sharpe_evidence: PaperSharpeEvidence,
    methodology: PaperVsBacktestMethodology,
) -> list[str]:
    """Verdict <-> bool <-> comparator echo <-> independent Decimal recompute must all agree (fail-closed)."""

    hard: list[str] = []
    verdict = _plain_str_or_empty(comparison_evidence.comparison_verdict)
    satisfied = comparison_evidence.sharpe_retention_satisfied
    if (verdict, satisfied) not in ((_VERDICT_SATISFIED, True), (_VERDICT_NOT_SATISFIED, False)):
        hard.append(_reason("comparison_verdict_incoherent"))
        return hard
    echo_status = _plain_str_or_empty(comparison_evidence.comparator_status_echo)
    echo_reasons = comparison_evidence.comparator_rejection_reasons_echo
    if satisfied:
        if (
            echo_status != _COMPARATOR_STATUS_PASS
            or comparison_evidence.comparator_passed_echo is not True
            or comparison_evidence.comparator_evaluated_echo is not True
            or echo_reasons != ()
        ):
            hard.append(_reason("comparison_verdict_incoherent"))
    elif (
        echo_status != _COMPARATOR_STATUS_REJECT
        or comparison_evidence.comparator_passed_echo is not False
        or comparison_evidence.comparator_evaluated_echo is not True
        or echo_reasons != (_COMPARATOR_BELOW_THRESHOLD_REASON,)
    ):
        hard.append(_reason("comparison_verdict_incoherent"))

    # A corrupted exact-typed artifact (already digest-mismatched above) must never crash this recompute:
    # every Decimal input is proven a plain non-empty string FIRST, and any conversion/arithmetic failure is
    # caught broadly — the decision can only fail closed, never raise past the completion boundary.
    backtest_repr = comparison_evidence.backtest_sharpe_repr
    paper_value = sharpe_evidence.paper_sharpe_annualized
    threshold_value = methodology.sharpe_retention_ratio
    if (
        not _is_plain_non_empty_string(backtest_repr)
        or not _is_plain_non_empty_string(paper_value)
        or not _is_plain_non_empty_string(threshold_value)
    ):
        hard.append(_reason("retention_recompute_mismatch"))
        return hard
    try:
        recomputed_ratio, recomputed_satisfied = _recompute_retention_verdict(
            paper_value, backtest_repr, threshold_value
        )
    except (ArithmeticError, TypeError, ValueError):
        hard.append(_reason("retention_recompute_mismatch"))
        return hard
    if recomputed_ratio != comparison_evidence.sharpe_retention_ratio_decimal:
        hard.append(_reason("retention_recompute_mismatch"))
    if recomputed_satisfied is not satisfied:
        hard.append(_reason("comparison_verdict_incoherent"))
    return hard


def build_paper_stage4_completion_decision(
    comparison_evidence: PaperStage4ComparisonEvidence,
    *,
    expected_comparison_evidence_digest: str,
    sharpe_evidence: PaperSharpeEvidence,
    expected_sharpe_evidence_digest: str,
    methodology: PaperVsBacktestMethodology,
    expected_methodology_digest: str,
    edge_identity: PaperEdgeIdentityEvidence,
    expected_edge_identity_digest: str,
    baseline_evidence: PaperStage4BacktestBaselineEvidence,
    expected_baseline_evidence_digest: str,
    gate_decision: PaperThirtyDayEvidenceGateDecision,
    expected_gate_decision_digest: str,
    completion_decision_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4CompletionDecision:
    """Render the terminal (v1 = BLOCKED) paper Stage-4 completion decision over the proven methodology chain.

    Every consumed artifact must be the exact merged type and re-prove its self-digest against the caller's
    independent anchor; the comparison evidence must be proven to have consumed EXACTLY the upstream
    artifacts supplied here (reseal defense over its ``verified_*`` digests); the approved v1 governance is
    re-pinned; the carried retention verdict is re-verified by an independent Decimal recompute. On success
    the decision is READY with the honest ``paper_methodology_verdict`` and an always-BLOCKED
    ``completion_verdict`` — ``prdv4_stage4_complete`` stays False on every path. Wrong-typed inputs,
    malformed anchors, malformed metadata, or forbidden BIST/live/order/capital/readiness/clock tokens raise
    ``PaperStage4CompletionDecisionError``; every trust/value failure maps to ``status=REJECTED``.
    """
    if type(comparison_evidence) is not PaperStage4ComparisonEvidence:
        raise PaperStage4CompletionDecisionError(_reason("comparison_evidence_malformed"))
    if type(sharpe_evidence) is not PaperSharpeEvidence:
        raise PaperStage4CompletionDecisionError(_reason("sharpe_evidence_malformed"))
    if type(methodology) is not PaperVsBacktestMethodology:
        raise PaperStage4CompletionDecisionError(_reason("methodology_malformed"))
    if type(edge_identity) is not PaperEdgeIdentityEvidence:
        raise PaperStage4CompletionDecisionError(_reason("edge_identity_malformed"))
    if type(baseline_evidence) is not PaperStage4BacktestBaselineEvidence:
        raise PaperStage4CompletionDecisionError(_reason("baseline_evidence_malformed"))
    if type(gate_decision) is not PaperThirtyDayEvidenceGateDecision:
        raise PaperStage4CompletionDecisionError(_reason("gate_decision_malformed"))
    expected_comparison_evidence_digest = _require_hex64(
        expected_comparison_evidence_digest, "expected_comparison_evidence_digest"
    )
    expected_sharpe_evidence_digest = _require_hex64(expected_sharpe_evidence_digest, "expected_sharpe_evidence_digest")
    expected_methodology_digest = _require_hex64(expected_methodology_digest, "expected_methodology_digest")
    expected_edge_identity_digest = _require_hex64(expected_edge_identity_digest, "expected_edge_identity_digest")
    expected_baseline_evidence_digest = _require_hex64(
        expected_baseline_evidence_digest, "expected_baseline_evidence_digest"
    )
    expected_gate_decision_digest = _require_hex64(expected_gate_decision_digest, "expected_gate_decision_digest")
    completion_decision_id = _require_plain_non_empty_string(completion_decision_id, "completion_decision_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (completion_decision_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperStage4CompletionDecisionError(_reason("scope_violation"))
    if _has_clock_token(*scope_texts):
        raise PaperStage4CompletionDecisionError(_reason("clock_token_forbidden"))

    hard: list[str] = []

    # Trust boundary: re-prove every consumed artifact self-digest (recompute == carried == caller anchor).
    comparison_failures, verified_comparison_digest = _digest_reproof_failures(
        artifact=comparison_evidence,
        carried_digest=comparison_evidence.comparison_evidence_digest,
        expected_digest=expected_comparison_evidence_digest,
        compute=paper_stage4_comparison_evidence_digest,
        reason_code="comparison_evidence_digest_mismatch",
    )
    hard.extend(comparison_failures)
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

    # Reseal defense: the comparison evidence must be bound to EXACTLY the artifacts supplied now.
    hard.extend(
        _comparison_binding_failures(
            comparison_evidence,
            verified_sharpe_digest=verified_sharpe_digest,
            verified_methodology_digest=verified_methodology_digest,
            verified_edge_identity_digest=verified_edge_identity_digest,
            verified_baseline_evidence_digest=verified_baseline_evidence_digest,
            verified_gate_decision_digest=verified_gate_decision_digest,
            baseline_evidence=baseline_evidence,
            sharpe_evidence=sharpe_evidence,
        )
    )

    hard.extend(_comparison_evidence_failures(comparison_evidence))
    hard.extend(_sharpe_evidence_failures(sharpe_evidence))
    hard.extend(_methodology_failures(methodology))
    hard.extend(_edge_identity_failures(edge_identity))
    hard.extend(_baseline_evidence_failures(baseline_evidence))
    hard.extend(_gate_decision_failures(gate_decision))
    hard.extend(_governance_repin_failures(comparison_evidence, methodology, sharpe_evidence, gate_decision))
    hard.extend(
        _cross_link_failures(
            correlation_id=correlation_id,
            comparison_evidence=comparison_evidence,
            sharpe_evidence=sharpe_evidence,
            methodology=methodology,
            edge_identity=edge_identity,
            baseline_evidence=baseline_evidence,
            gate_decision=gate_decision,
        )
    )
    hard.extend(_verdict_coherence_failures(comparison_evidence, sharpe_evidence, methodology))

    hard = sorted(set(hard))
    if hard:
        status = PaperStage4CompletionDecisionStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
        paper_methodology_verdict = _METHOD_VERDICT_NOT_DECIDED
        paper_methodology_complete = False
        completion_verdict = _COMPLETION_VERDICT_NOT_DECIDED
        stage4_completion_decided = False
        stage4_completion_blockers: tuple[str, ...] = ()
    else:
        status = PaperStage4CompletionDecisionStatus.READY
        ready = True
        reason_codes = ()
        if comparison_evidence.sharpe_retention_satisfied is True:
            paper_methodology_verdict = _METHOD_VERDICT_COMPLETE
            paper_methodology_complete = True
        else:
            paper_methodology_verdict = _METHOD_VERDICT_NOT_COMPLETE
            paper_methodology_complete = False
        completion_verdict = _COMPLETION_VERDICT_BLOCKED
        stage4_completion_decided = True
        stage4_completion_blockers = _STAGE4_COMPLETION_BLOCKERS

    decision_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "decision_version": _DECISION_VERSION,
        "status": status,
        "ready": ready,
        "completion_decision_id": completion_decision_id,
        "correlation_id": correlation_id,
        "paper_id": _plain_str_or_empty(comparison_evidence.paper_id),
        "series_id": _plain_str_or_empty(comparison_evidence.series_id),
        "window_id": _plain_str_or_empty(comparison_evidence.window_id),
        "market_symbol": _plain_str_or_empty(comparison_evidence.market_symbol),
        "paper_edge_id": _safe_digest_value(comparison_evidence.paper_edge_id),
        "baseline_id": _plain_str_or_empty(comparison_evidence.baseline_id),
        "strategy_id": _plain_str_or_empty(edge_identity.strategy_id),
        "strategy_version": _plain_str_or_empty(edge_identity.strategy_version),
        "strategy_family": _plain_str_or_empty(edge_identity.strategy_family),
        "edge_family": _plain_str_or_empty(edge_identity.edge_family),
        "market_type": _plain_str_or_empty(edge_identity.market_type),
        "expected_comparison_evidence_digest": expected_comparison_evidence_digest,
        "verified_comparison_evidence_digest": verified_comparison_digest,
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
        "baseline_digest": _safe_digest_value(comparison_evidence.baseline_digest),
        "paper_summary_digest": _safe_digest_value(comparison_evidence.paper_summary_digest),
        "series_digest": _safe_digest_value(comparison_evidence.series_digest),
        "time_window_digest": _safe_digest_value(comparison_evidence.time_window_digest),
        "metrics_summary_digest": _safe_digest_value(comparison_evidence.metrics_summary_digest),
        "series_methodology_digest": _safe_digest_value(comparison_evidence.series_methodology_digest),
        "paper_methodology_verdict": paper_methodology_verdict,
        "paper_methodology_complete": paper_methodology_complete,
        "comparison_verdict_echo": _plain_str_or_empty(comparison_evidence.comparison_verdict),
        "sharpe_retention_satisfied_echo": comparison_evidence.sharpe_retention_satisfied is True,
        "sharpe_retention_ratio_decimal": _plain_str_or_empty(comparison_evidence.sharpe_retention_ratio_decimal),
        "sharpe_retention_threshold": _plain_str_or_empty(comparison_evidence.sharpe_retention_threshold),
        "retention_comparison_operator": _APPROVED_RETENTION_OPERATOR,
        "min_duration_days": _safe_int_value(comparison_evidence.min_duration_days),
        "bucket_count": _safe_int_value(comparison_evidence.bucket_count),
        "window_duration_ns": _safe_int_value(comparison_evidence.window_duration_ns),
        "completion_verdict": completion_verdict,
        "stage4_completion_decided": stage4_completion_decided,
        "stage4_completion_blockers": stage4_completion_blockers,
        "completion_scope": _COMPLETION_SCOPE,
        "completion_policy_id": _COMPLETION_POLICY_ID,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperStage4CompletionDecision(completion_decision_digest="", **decision_fields)  # type: ignore[arg-type]
    return replace(seed, completion_decision_digest=paper_stage4_completion_decision_digest(seed))


def _decision_payload_from(decision: PaperStage4CompletionDecision) -> dict[str, object]:
    """Canonical payload over EVERY public field except the self-digest (complete by construction)."""

    payload: dict[str, object] = {}
    for field in fields(decision):
        if field.name == "completion_decision_digest":
            continue
        value = getattr(decision, field.name)
        if field.name == "status":
            payload[field.name] = decision.status.value
        elif field.name == "metadata":
            payload[field.name] = [[key, item] for key, item in decision.metadata]
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def paper_stage4_completion_decision_to_dict(decision: PaperStage4CompletionDecision) -> dict[str, object]:
    """Canonical JSON-ready mapping for the completion decision, including its self-digest."""

    payload = _decision_payload_from(decision)
    payload["completion_decision_digest"] = decision.completion_decision_digest
    return payload


def paper_stage4_completion_decision_digest(decision: PaperStage4CompletionDecision) -> str:
    """Recompute the canonical completion-decision digest, excluding only the self-digest field."""

    return _canonical_digest(_decision_payload_from(decision))


__all__ = [
    "PaperStage4CompletionDecision",
    "PaperStage4CompletionDecisionError",
    "PaperStage4CompletionDecisionStatus",
    "build_paper_stage4_completion_decision",
    "paper_stage4_completion_decision_digest",
    "paper_stage4_completion_decision_to_dict",
]
