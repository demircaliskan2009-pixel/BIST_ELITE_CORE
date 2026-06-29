"""Paper-vs-backtest comparison methodology snapshot (PRDV4 Stage 4, policy-only).

This validation artifact is a deterministic, paper-only, fail-closed, digest-bound snapshot of the approved
Stage-4 paper-vs-backtest comparison POLICY. It consumes no evidence, computes no Sharpe, runs no comparator,
binds no edge identity, and decides no gate. It exists so a later comparison-evidence artifact can fail closed
when the comparison policy is missing, mismatched, or unapproved.

Governance (user-approved for this slice):

* enforced guardrails in v1: Sharpe-retention ratio (``0.500000000000000000``) and minimum duration (``30``
  days) only;
* secondary guardrails (hit-rate / fill-rate / slippage / drawdown) are DECLARED-NOT-ENFORCED review-only
  policy strings in v1 — no numeric thresholds are invented;
* the risk-free / annualization / sample-stddev / decimal policy constants are pinned to the SAME values the
  merged ``paper_sharpe_evidence`` artifact computes under, so a later comparison can prove the paper Sharpe was
  produced under the methodology the comparison expects.

It does NOT consume ``PaperSharpeEvidence`` or any paper evidence, does NOT bind a backtest baseline, does NOT
derive a paper edge identity, does NOT decide the operational or ≥30-day gate, does NOT invoke the Stage-4
comparator, does NOT construct ``Stage4PaperSummary``/``Stage4BacktestBaseline``, does NOT set
``prdv4_stage4_complete``, and does NOT claim comparison readiness, profitability, edge, live readiness, shadow
readiness, Deribit readiness, or operational readiness. It calls no wall-clock, runtime, service, execution,
venue, scheduler, filesystem, network, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

_SCHEMA_VERSION = "paper-vs-backtest-methodology.v1"
_METHODOLOGY_VERSION = "paper-vs-backtest-methodology.v1"
_COMPARISON_BASIS = "paper_vs_backtest_sharpe_retention.v1"
_ENFORCED_GUARDRAIL_POLICY = "sharpe_retention_and_min_duration_only.v1"
_SECONDARY_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"
_HIT_RATE_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"
_FILL_RATE_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"
_SLIPPAGE_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"
_DRAWDOWN_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"

# Consistency anchor with the merged ``paper_sharpe_evidence`` artifact (pinned, not caller-configurable).
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_ANNUALIZATION_FACTOR = 365
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_STDDEV_POLICY = "sample_stddev_n_minus_1.v1"
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80

# Approved governance values for this slice.
_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_MIN_DURATION_DAYS = 30
# A canonical fixed-scale-18 decimal string (sign optional so out-of-range values reach a deterministic REJECTED
# rather than a raw format raise).
_SCALE18_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")

_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"stage4_comparator|compare_stage4|Stage4PaperSummary|Stage4BacktestBaseline|capital|margin|balance|"
    r"reservation|real_account_equity|account_equity|real_equity)\w*"
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


class PaperVsBacktestMethodologyError(RuntimeError):
    """Raised on malformed inputs, forbidden scope/clock tokens, or an unapproved risk-free policy."""


class PaperVsBacktestMethodologyStatus(str, Enum):
    """Methodology snapshot status. READY is a policy declaration only, never a comparison verdict."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperVsBacktestMethodology:
    """Immutable, digest-bound paper-vs-backtest comparison-policy snapshot (policy-only)."""

    schema_version: str
    methodology_version: str
    status: PaperVsBacktestMethodologyStatus
    ready: bool
    methodology_id: str
    correlation_id: str
    comparison_basis: str
    enforced_guardrail_policy: str
    secondary_guardrail_policy: str
    sharpe_retention_ratio: str
    min_duration_days: int
    risk_free_policy_id: str
    annualization_factor: int
    annualization_policy: str
    stddev_policy: str
    decimal_policy: str
    decimal_scale: int
    decimal_rounding: str
    decimal_internal_precision: int
    hit_rate_guardrail_policy: str
    fill_rate_guardrail_policy: str
    slippage_guardrail_policy: str
    drawdown_guardrail_policy: str
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    methodology_digest: str
    paper_only: bool = True
    methodology_snapshot: bool = True
    policy_declared: bool = True
    hit_rate_floor_enforced: bool = False
    fill_rate_floor_enforced: bool = False
    slippage_ceiling_enforced: bool = False
    drawdown_ceiling_enforced: bool = False
    comparison_ready: bool = False
    paper_vs_backtest_comparison_ready: bool = False
    comparison_performed: bool = False
    stage4_comparator_invoked: bool = False
    thirty_day_gate_satisfied: bool = False
    thirty_day_gate_decided: bool = False
    prdv4_stage4_complete: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    edge_identity_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    private_api_ready: bool = False
    real_wall_clock_used: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperVsBacktestMethodologyError(f"paper_vs_backtest_methodology:{field_name}_invalid")
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


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


def _governance_failures(sharpe_retention_ratio: str, min_duration_days: int) -> list[str]:
    """Deterministic REJECTED reasons for well-formed-but-governance-inconsistent values (never a raise)."""
    hard: list[str] = []
    retention_value = Decimal(sharpe_retention_ratio)
    if retention_value < 0 or retention_value > 1:
        hard.append("paper_vs_backtest_methodology:sharpe_retention_ratio_out_of_range")
    if sharpe_retention_ratio != _SHARPE_RETENTION_RATIO:
        hard.append("paper_vs_backtest_methodology:sharpe_retention_ratio_not_approved")
    if min_duration_days != _MIN_DURATION_DAYS:
        hard.append("paper_vs_backtest_methodology:min_duration_days_not_approved")
    return sorted(set(hard))


def build_paper_vs_backtest_methodology(
    *,
    methodology_id: str,
    correlation_id: str,
    sharpe_retention_ratio: str,
    min_duration_days: int,
    risk_free_policy_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperVsBacktestMethodology:
    """Build a deterministic, governance-consistent paper-vs-backtest comparison-policy snapshot."""

    methodology_id = _require_plain_non_empty_string(methodology_id, "methodology_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    risk_free_policy_id = _require_plain_non_empty_string(risk_free_policy_id, "risk_free_policy_id")
    if type(sharpe_retention_ratio) is not str or not _SCALE18_DECIMAL_PATTERN.fullmatch(sharpe_retention_ratio):
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:sharpe_retention_ratio_invalid")
    if not _is_exact_int(min_duration_days):
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:min_duration_days_invalid")

    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (
        methodology_id,
        correlation_id,
        risk_free_policy_id,
        sharpe_retention_ratio,
        *_metadata_texts(metadata_pairs),
    )
    if _has_scope_violation(*scope_texts):
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:scope_violation")
    if _has_clock_token(*scope_texts):
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:clock_token_forbidden")
    if risk_free_policy_id != _RISK_FREE_POLICY_ID:
        raise PaperVsBacktestMethodologyError("paper_vs_backtest_methodology:risk_free_policy_unapproved")

    hard = _governance_failures(sharpe_retention_ratio, min_duration_days)
    if hard:
        status = PaperVsBacktestMethodologyStatus.REJECTED
        ready = False
        reason_codes = tuple(hard)
    else:
        status = PaperVsBacktestMethodologyStatus.READY
        ready = True
        reason_codes = ()

    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "methodology_version": _METHODOLOGY_VERSION,
        "status": status,
        "ready": ready,
        "methodology_id": methodology_id,
        "correlation_id": correlation_id,
        "comparison_basis": _COMPARISON_BASIS,
        "enforced_guardrail_policy": _ENFORCED_GUARDRAIL_POLICY,
        "secondary_guardrail_policy": _SECONDARY_GUARDRAIL_POLICY,
        "sharpe_retention_ratio": sharpe_retention_ratio,
        "min_duration_days": min_duration_days,
        "risk_free_policy_id": risk_free_policy_id,
        "annualization_factor": _ANNUALIZATION_FACTOR,
        "annualization_policy": _ANNUALIZATION_POLICY,
        "stddev_policy": _STDDEV_POLICY,
        "decimal_policy": _DECIMAL_POLICY,
        "decimal_scale": _DECIMAL_SCALE,
        "decimal_rounding": _DECIMAL_ROUNDING,
        "decimal_internal_precision": _DECIMAL_INTERNAL_PRECISION,
        "hit_rate_guardrail_policy": _HIT_RATE_GUARDRAIL_POLICY,
        "fill_rate_guardrail_policy": _FILL_RATE_GUARDRAIL_POLICY,
        "slippage_guardrail_policy": _SLIPPAGE_GUARDRAIL_POLICY,
        "drawdown_guardrail_policy": _DRAWDOWN_GUARDRAIL_POLICY,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = PaperVsBacktestMethodology(methodology_digest="", **fields)  # type: ignore[arg-type]
    return _replace_methodology_digest(seed, paper_vs_backtest_methodology_digest(seed))


def _replace_methodology_digest(methodology: PaperVsBacktestMethodology, digest: str) -> PaperVsBacktestMethodology:
    fields = _methodology_fields(methodology)
    fields["methodology_digest"] = digest
    return PaperVsBacktestMethodology(**fields)  # type: ignore[arg-type]


def _methodology_fields(methodology: PaperVsBacktestMethodology) -> dict[str, object]:
    return {
        "schema_version": methodology.schema_version,
        "methodology_version": methodology.methodology_version,
        "status": methodology.status,
        "ready": methodology.ready,
        "methodology_id": methodology.methodology_id,
        "correlation_id": methodology.correlation_id,
        "comparison_basis": methodology.comparison_basis,
        "enforced_guardrail_policy": methodology.enforced_guardrail_policy,
        "secondary_guardrail_policy": methodology.secondary_guardrail_policy,
        "sharpe_retention_ratio": methodology.sharpe_retention_ratio,
        "min_duration_days": methodology.min_duration_days,
        "risk_free_policy_id": methodology.risk_free_policy_id,
        "annualization_factor": methodology.annualization_factor,
        "annualization_policy": methodology.annualization_policy,
        "stddev_policy": methodology.stddev_policy,
        "decimal_policy": methodology.decimal_policy,
        "decimal_scale": methodology.decimal_scale,
        "decimal_rounding": methodology.decimal_rounding,
        "decimal_internal_precision": methodology.decimal_internal_precision,
        "hit_rate_guardrail_policy": methodology.hit_rate_guardrail_policy,
        "fill_rate_guardrail_policy": methodology.fill_rate_guardrail_policy,
        "slippage_guardrail_policy": methodology.slippage_guardrail_policy,
        "drawdown_guardrail_policy": methodology.drawdown_guardrail_policy,
        "reason_codes": methodology.reason_codes,
        "metadata": methodology.metadata,
    }


def _methodology_payload_from(methodology: PaperVsBacktestMethodology) -> dict[str, object]:
    return {
        "schema_version": methodology.schema_version,
        "methodology_version": methodology.methodology_version,
        "status": methodology.status.value,
        "ready": methodology.ready,
        "methodology_id": methodology.methodology_id,
        "correlation_id": methodology.correlation_id,
        "comparison_basis": methodology.comparison_basis,
        "enforced_guardrail_policy": methodology.enforced_guardrail_policy,
        "secondary_guardrail_policy": methodology.secondary_guardrail_policy,
        "sharpe_retention_ratio": methodology.sharpe_retention_ratio,
        "min_duration_days": methodology.min_duration_days,
        "risk_free_policy_id": methodology.risk_free_policy_id,
        "annualization_factor": methodology.annualization_factor,
        "annualization_policy": methodology.annualization_policy,
        "stddev_policy": methodology.stddev_policy,
        "decimal_policy": methodology.decimal_policy,
        "decimal_scale": methodology.decimal_scale,
        "decimal_rounding": methodology.decimal_rounding,
        "decimal_internal_precision": methodology.decimal_internal_precision,
        "hit_rate_guardrail_policy": methodology.hit_rate_guardrail_policy,
        "fill_rate_guardrail_policy": methodology.fill_rate_guardrail_policy,
        "slippage_guardrail_policy": methodology.slippage_guardrail_policy,
        "drawdown_guardrail_policy": methodology.drawdown_guardrail_policy,
        "reason_codes": list(methodology.reason_codes),
        "metadata": _serialize_metadata(methodology.metadata),
        "paper_only": methodology.paper_only,
        "methodology_snapshot": methodology.methodology_snapshot,
        "policy_declared": methodology.policy_declared,
        "hit_rate_floor_enforced": methodology.hit_rate_floor_enforced,
        "fill_rate_floor_enforced": methodology.fill_rate_floor_enforced,
        "slippage_ceiling_enforced": methodology.slippage_ceiling_enforced,
        "drawdown_ceiling_enforced": methodology.drawdown_ceiling_enforced,
        "comparison_ready": methodology.comparison_ready,
        "paper_vs_backtest_comparison_ready": methodology.paper_vs_backtest_comparison_ready,
        "comparison_performed": methodology.comparison_performed,
        "stage4_comparator_invoked": methodology.stage4_comparator_invoked,
        "thirty_day_gate_satisfied": methodology.thirty_day_gate_satisfied,
        "thirty_day_gate_decided": methodology.thirty_day_gate_decided,
        "prdv4_stage4_complete": methodology.prdv4_stage4_complete,
        "operational_readiness": methodology.operational_readiness,
        "live_ready": methodology.live_ready,
        "shadow_ready": methodology.shadow_ready,
        "deribit_ready": methodology.deribit_ready,
        "profitability_proven": methodology.profitability_proven,
        "edge_proven": methodology.edge_proven,
        "edge_identity_proven": methodology.edge_identity_proven,
        "production_execution": methodology.production_execution,
        "real_orders_enabled": methodology.real_orders_enabled,
        "real_money_enabled": methodology.real_money_enabled,
        "real_capital_reserved": methodology.real_capital_reserved,
        "live_api_called": methodology.live_api_called,
        "scheduler_enabled": methodology.scheduler_enabled,
        "auto_loop_enabled": methodology.auto_loop_enabled,
        "connector_invoked": methodology.connector_invoked,
        "private_api_ready": methodology.private_api_ready,
        "real_wall_clock_used": methodology.real_wall_clock_used,
        "real_account_equity_used": methodology.real_account_equity_used,
        "real_capital_used": methodology.real_capital_used,
    }


def paper_vs_backtest_methodology_to_dict(methodology: PaperVsBacktestMethodology) -> dict[str, object]:
    """Canonical JSON-ready mapping for the methodology snapshot, including its self-digest."""

    payload = _methodology_payload_from(methodology)
    payload["methodology_digest"] = methodology.methodology_digest
    return payload


def paper_vs_backtest_methodology_digest(methodology: PaperVsBacktestMethodology) -> str:
    """Recompute the canonical methodology digest, excluding only the self-digest field."""

    return _canonical_digest(_methodology_payload_from(methodology))


__all__ = [
    "PaperVsBacktestMethodology",
    "PaperVsBacktestMethodologyError",
    "PaperVsBacktestMethodologyStatus",
    "build_paper_vs_backtest_methodology",
    "paper_vs_backtest_methodology_digest",
    "paper_vs_backtest_methodology_to_dict",
]
