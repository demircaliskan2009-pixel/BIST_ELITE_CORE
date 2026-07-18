"""SM-5 paper-vs-backtest methodology-v2 snapshot (PRDV4 Stage 4, digest-bound, paper-only).

This validation artifact is a deterministic, paper-only, fail-closed, digest-bound snapshot that BINDS three
already-merged upstream anchors into a single methodology-v2 snapshot for a later SM-6 consumer:

1. ``PaperVsBacktestMethodology`` v1 — the approved Sharpe-retention comparison-policy snapshot;
2. ``SecondaryMetricsPolicy`` — the approved hit-rate / fill-rate / slippage threshold contracts;
3. ``PaperSecondaryMetricsEnforcementPrecondition`` — the merged bridge that already re-proved the SM-4
   computed metrics clear those approved thresholds under the verified policy over a reconciled record set.

It re-proves each anchor's public self-digest (recompute == carried == caller-supplied expected), re-pins
the predecessor's frozen v1 governance literals, re-pins the policy's approved definitions / decimal /
Fraction contract, re-pins the precondition's nested digest formats, cross-binds policy id/digest,
correlations, market symbol and every policy-to-precondition threshold echo, and independently recomputes
every threshold pass from the precondition's carried computed values against the policy's approved
thresholds. It carries the approved threshold contracts plus the three metric-specific
``*_floor_enforced`` / ``*_ceiling_enforced`` flags — which are legal ONLY here and mean only that the bound
precondition proved those approved thresholds, NOT aggregate Stage-4 secondary-metrics enforcement.

It does NOT execute or import the Stage-4 comparator, does NOT consume SM-4 evidence or the #327
reconciliation directly, does NOT claim aggregate secondary-metrics enforcement, does NOT decide comparison,
the >=30-day gate, Stage-4 completion or readiness, does NOT claim edge or profitability, does NOT touch
Deribit connector readiness, and does NOT implement SM-6. ``secondary_metrics_enforced`` is structurally
False on every path. It calls no wall-clock, runtime, service, execution, venue, scheduler, filesystem,
network, order, capital, or random surface.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.validation.paper_secondary_metrics_enforcement_precondition import (
    PaperSecondaryMetricsEnforcementPrecondition,
    PaperSecondaryMetricsEnforcementPreconditionStatus,
    paper_secondary_metrics_enforcement_precondition_digest,
)
from crypto_core.validation.paper_vs_backtest_methodology import (
    PaperVsBacktestMethodology,
    PaperVsBacktestMethodologyStatus,
    paper_vs_backtest_methodology_digest,
)
from crypto_core.validation.secondary_metrics_policy import (
    SecondaryMetricsPolicy,
    SecondaryMetricsPolicyStatus,
    secondary_metrics_policy_digest,
)

_SCHEMA_VERSION = "paper-vs-backtest-methodology.v2"
_METHODOLOGY_VERSION = "paper-vs-backtest-methodology.v2"
_REASON_PREFIX = "paper_vs_backtest_methodology_v2"

_EXPECTED_PREDECESSOR_SCHEMA_VERSION = "paper-vs-backtest-methodology.v1"
_EXPECTED_PREDECESSOR_METHODOLOGY_VERSION = "paper-vs-backtest-methodology.v1"

_EXPECTED_POLICY_SCHEMA_VERSION = "secondary-metrics-policy.v1"
_EXPECTED_POLICY_VERSION = "secondary-metrics-policy.v1"

_EXPECTED_PRECONDITION_SCHEMA_VERSION = "paper-secondary-metrics-enforcement-precondition.v1"
_EXPECTED_PRECONDITION_VERSION = "paper-secondary-metrics-enforcement-precondition.v1"

_COMPARISON_BASIS = "paper_vs_backtest_sharpe_retention.v1"
_ENFORCED_GUARDRAIL_POLICY = "sharpe_retention_and_min_duration_only.v1"

_SECONDARY_GUARDRAIL_POLICY = "approved_hit_rate_fill_rate_slippage_threshold_contracts_bound_comparison_pending.v2"
_HIT_RATE_GUARDRAIL_POLICY = "approved_hit_rate_floor_contract_bound_comparison_pending.v2"
_FILL_RATE_GUARDRAIL_POLICY = "approved_fill_rate_floor_contract_bound_comparison_pending.v2"
_SLIPPAGE_GUARDRAIL_POLICY = "approved_slippage_ceiling_contract_bound_comparison_pending.v2"
_DRAWDOWN_GUARDRAIL_POLICY = "declared_not_enforced_review_only.v1"

# The predecessor v1 snapshot declares its secondary guardrails as review-only, never enforced.
_V1_DECLARED_NOT_ENFORCED = "declared_not_enforced_review_only.v1"

_HIT_RATE_OPERATOR = ">="
_FILL_RATE_OPERATOR = ">="
_SLIPPAGE_OPERATOR = "<="

_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_MIN_DURATION_DAYS = 30
_RISK_FREE_POLICY_ID = "constant_zero_daily_review_only.v1"
_ANNUALIZATION_FACTOR = 365
_ANNUALIZATION_POLICY = "daily_utc_365_review_only"
_STDDEV_POLICY = "sample_stddev_n_minus_1.v1"
_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
_DECIMAL_SCALE = 18
_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_DECIMAL_INTERNAL_PRECISION = 80

_HIT_RATE_DEFINITION = "realized_pnl_positive_episode_over_decided_episodes.v1"
_FILL_RATE_DEFINITION = "filled_quantity_over_intended_quantity_and_filled_episode_ratio.v1"
_SLIPPAGE_DEFINITION = "signed_bps_vs_expected_fill_reference_price.v1"

_EXPECTED_FILL_MODEL_REFERENCE = "crypto_core.execution.fill_pricer.FillPricer.mid_plus_half_spread_plus_size_impact.v1"

_SECONDARY_METRICS_DECIMAL_POLICY = "decimal_quantized_scale_18_round_half_even_fraction_intermediates.v1"
_SECONDARY_METRICS_DECIMAL_SCALE = 18
_SECONDARY_METRICS_DECIMAL_ROUNDING = "ROUND_HALF_EVEN"
_FRACTION_INTERMEDIATES_REQUIRED = True

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_SCALE18_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)\.[0-9]{18}$")
_NEGATIVE_ZERO_SCALE18 = "-0.000000000000000000"
_MAX_SCALE18_LENGTH = 60

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

_PREDECESSOR_TRUE_FLAGS = ("paper_only", "methodology_snapshot", "policy_declared")
_PREDECESSOR_FALSE_FLAGS = (
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
_POLICY_TRUE_FLAGS = ("paper_only", "policy_only")
_POLICY_FALSE_FLAGS = (
    "secondary_metrics_enforced",
    "trade_records_consumed",
    "episodes_consumed",
    "fills_consumed",
    "pnl_consumed",
    "comparator_invoked",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "scheduler_enabled",
    "auto_loop_enabled",
    "edge_proven",
    "profitability_proven",
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


class PaperVsBacktestMethodologyV2Error(RuntimeError):
    """Raised on malformed caller input, forbidden caller scope/BIST/clock tokens, or wrong anchor types."""


class PaperVsBacktestMethodologyV2Status(str, Enum):
    """Methodology-v2 snapshot status. READY binds approved threshold contracts; it is never a comparison."""

    METHODOLOGY_READY = "METHODOLOGY_READY"
    METHODOLOGY_REJECTED = "METHODOLOGY_REJECTED"


@dataclass(frozen=True)
class PaperVsBacktestMethodologyV2:
    """Immutable, digest-bound SM-5 methodology-v2 snapshot binding the three approved upstream anchors."""

    schema_version: str
    methodology_version: str
    status: PaperVsBacktestMethodologyV2Status
    ready: bool
    methodology_id: str
    correlation_id: str
    predecessor_methodology_id: str
    secondary_metrics_policy_id: str
    secondary_metrics_enforcement_precondition_id: str
    market_symbol: str
    expected_predecessor_methodology_digest: str
    verified_predecessor_methodology_digest: str
    expected_secondary_metrics_policy_digest: str
    verified_secondary_metrics_policy_digest: str
    expected_secondary_metrics_enforcement_precondition_digest: str
    verified_secondary_metrics_enforcement_precondition_digest: str
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
    hit_rate_definition: str
    fill_rate_definition: str
    slippage_definition: str
    hit_rate_operator: str
    fill_rate_operator: str
    slippage_operator: str
    expected_fill_model_reference: str
    expected_fill_model_parameters_digest: str | None
    secondary_metrics_decimal_policy: str
    secondary_metrics_decimal_scale: int
    secondary_metrics_decimal_rounding: str
    fraction_intermediates_required: bool
    approved_hit_rate_floor: str | None
    approved_fill_rate_floor: str | None
    approved_slippage_ceiling_bps: str | None
    approved_min_decided_episode_count: int | None
    approval_reference: str | None
    approval_digest: str | None
    thresholds_approved: bool
    hit_rate_floor_enforced: bool
    fill_rate_floor_enforced: bool
    slippage_ceiling_enforced: bool
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    methodology_digest: str
    paper_only: bool = True
    methodology_snapshot: bool = True
    policy_declared: bool = True
    predecessor_methodology_consumed: bool = False
    secondary_metrics_policy_consumed: bool = False
    secondary_metrics_enforcement_precondition_consumed: bool = False
    secondary_metrics_enforced: bool = False
    drawdown_ceiling_enforced: bool = False
    comparison_ready: bool = False
    paper_vs_backtest_comparison_ready: bool = False
    comparison_performed: bool = False
    stage4_comparator_invoked: bool = False
    thirty_day_gate_satisfied: bool = False
    thirty_day_gate_decided: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    edge_identity_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_fills_used: bool = False
    authoritative_pnl: bool = False
    capital_mutation_enabled: bool = False
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


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


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


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _plain_strings_equal(left: object, right: object) -> bool:
    return _is_plain_non_empty_string(left) and _is_plain_non_empty_string(right) and left == right


def _exact_ints_equal(left: object, right: object) -> bool:
    return _is_exact_int(left) and _is_exact_int(right) and left == right


def _is_exact_empty_tuple(value: object) -> bool:
    return type(value) is tuple and len(value) == 0


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise PaperVsBacktestMethodologyV2Error(_reason(f"{field_name}_malformed"))
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not _is_hex64_string(value):
        raise PaperVsBacktestMethodologyV2Error(_reason(f"{field_name}_malformed"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperVsBacktestMethodologyV2Error(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperVsBacktestMethodologyV2Error(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperVsBacktestMethodologyV2Error(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperVsBacktestMethodologyV2Error(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _has_bist_token(*texts: object) -> bool:
    return any(type(text) is str and text != "" and _BIST_PATTERN.search(text) for text in texts)


def _has_forbidden_scope(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
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


def _has_any_scope_violation(*texts: object) -> bool:
    return _has_bist_token(*texts) or _has_forbidden_scope(*texts) or _has_clock_token(*texts)


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _parse_scale18(value: object) -> Decimal | None:
    if (
        type(value) is not str
        or len(value) > _MAX_SCALE18_LENGTH
        or value == _NEGATIVE_ZERO_SCALE18
        or not _SCALE18_PATTERN.fullmatch(value)
    ):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _scale18_in_range(value: object, lower: Decimal, upper: Decimal | None) -> bool:
    parsed = _parse_scale18(value)
    if parsed is None or parsed < lower:
        return False
    return not (upper is not None and parsed > upper)


def _recomputed_digest_or_none(compute: object, artifact: object) -> str | None:
    try:
        return compute(artifact)  # type: ignore[operator]
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection
        return None


def _digest_reproof_ok(*, artifact: object, carried_digest: object, expected_digest: str, compute: object) -> bool:
    recomputed = _recomputed_digest_or_none(compute, artifact)
    return (
        _is_hex64_string(recomputed)
        and _is_hex64_string(carried_digest)
        and _is_hex64_string(expected_digest)
        and recomputed == carried_digest
        and carried_digest == expected_digest
    )


def _flag_failure(artifact: object, true_flags: tuple[str, ...], false_flags: tuple[str, ...]) -> bool:
    return any(getattr(artifact, flag) is not True for flag in true_flags) or any(
        getattr(artifact, flag) is not False for flag in false_flags
    )


def _is_canonical_anchor_metadata(metadata: object) -> bool:
    """Exact canonical-representation check for anchor-carried metadata (validates, never repairs).

    Canonical means: the outer container is exactly ``tuple``; every entry is exactly a two-element
    ``tuple``; every key and value is an exact, non-empty, stripped ``str`` containing no ASCII control or
    DEL character; the tuple is exactly sorted; keys are unique. Anything else — list containers or pairs,
    wrong pair arity, non-string or nested values, duplicate keys, unsorted order, padding, control
    characters — is noncanonical and fails closed at the consuming anchor's contract check. It is never
    normalized, repaired, or silently skipped.
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


def build_paper_vs_backtest_methodology_v2(
    predecessor_methodology: PaperVsBacktestMethodology,
    secondary_metrics_policy: SecondaryMetricsPolicy,
    enforcement_precondition: PaperSecondaryMetricsEnforcementPrecondition,
    *,
    expected_predecessor_methodology_digest: str,
    expected_secondary_metrics_policy_digest: str,
    expected_secondary_metrics_enforcement_precondition_digest: str,
    methodology_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperVsBacktestMethodologyV2:
    """Bind three approved upstream anchors into a deterministic, digest-bound SM-5 methodology-v2 snapshot.

    Malformed caller input and forbidden caller scope/BIST/clock tokens RAISE. Stale, tampered, resealed,
    not-ready, contract-inconsistent, cross-inconsistent, or anchor-carried-unsafe inputs fail closed to
    ``METHODOLOGY_REJECTED``. ``METHODOLOGY_READY`` binds the approved threshold contracts only; it never
    claims aggregate enforcement, comparison, completion, readiness, edge, or profitability.
    """

    # 1. Exact anchor types (RAISE).
    if type(predecessor_methodology) is not PaperVsBacktestMethodology:
        raise PaperVsBacktestMethodologyV2Error(_reason("predecessor_methodology_malformed"))
    if type(secondary_metrics_policy) is not SecondaryMetricsPolicy:
        raise PaperVsBacktestMethodologyV2Error(_reason("secondary_metrics_policy_malformed"))
    if type(enforcement_precondition) is not PaperSecondaryMetricsEnforcementPrecondition:
        raise PaperVsBacktestMethodologyV2Error(_reason("enforcement_precondition_malformed"))

    predecessor = predecessor_methodology
    policy = secondary_metrics_policy
    precondition = enforcement_precondition

    # 2. Caller-owned identifiers, expected digests and metadata (RAISE).
    methodology_id = _require_plain_non_empty_string(methodology_id, "methodology_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    expected_predecessor_methodology_digest = _require_hex64(
        expected_predecessor_methodology_digest, "expected_predecessor_methodology_digest"
    )
    expected_secondary_metrics_policy_digest = _require_hex64(
        expected_secondary_metrics_policy_digest, "expected_secondary_metrics_policy_digest"
    )
    expected_secondary_metrics_enforcement_precondition_digest = _require_hex64(
        expected_secondary_metrics_enforcement_precondition_digest,
        "expected_secondary_metrics_enforcement_precondition_digest",
    )
    # 3. Normalize metadata to a sorted tuple.
    metadata_pairs = _normalize_metadata(metadata)

    # 4. Caller-owned BIST / scope / clock text (RAISE).
    caller_texts = (methodology_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_bist_token(*caller_texts):
        raise PaperVsBacktestMethodologyV2Error(_reason("bist_token_forbidden"))
    if _has_forbidden_scope(*caller_texts):
        raise PaperVsBacktestMethodologyV2Error(_reason("scope_violation"))
    if _has_clock_token(*caller_texts):
        raise PaperVsBacktestMethodologyV2Error(_reason("clock_token_forbidden"))

    hard: list[str] = []

    # 5-6. Independent self-digest reproof for each anchor (recompute == carried == expected).
    predecessor_digest_ok = _digest_reproof_ok(
        artifact=predecessor,
        carried_digest=predecessor.methodology_digest,
        expected_digest=expected_predecessor_methodology_digest,
        compute=paper_vs_backtest_methodology_digest,
    )
    policy_digest_ok = _digest_reproof_ok(
        artifact=policy,
        carried_digest=policy.policy_digest,
        expected_digest=expected_secondary_metrics_policy_digest,
        compute=secondary_metrics_policy_digest,
    )
    precondition_digest_ok = _digest_reproof_ok(
        artifact=precondition,
        carried_digest=precondition.precondition_digest,
        expected_digest=expected_secondary_metrics_enforcement_precondition_digest,
        compute=paper_secondary_metrics_enforcement_precondition_digest,
    )
    if not predecessor_digest_ok:
        hard.append(_reason("predecessor_methodology_digest_mismatch"))
    if not policy_digest_ok:
        hard.append(_reason("secondary_metrics_policy_digest_mismatch"))
    if not precondition_digest_ok:
        hard.append(_reason("secondary_metrics_enforcement_precondition_digest_mismatch"))

    # Canonical-representation gates: anchor metadata and anchor identities are validated exactly before
    # READY selection; digest validity is never accepted as evidence of canonical representation.
    predecessor_metadata_canonical = _is_canonical_anchor_metadata(predecessor.metadata)
    policy_metadata_canonical = _is_canonical_anchor_metadata(policy.metadata)
    precondition_metadata_canonical = _is_canonical_anchor_metadata(precondition.metadata)

    # Canonical identity/reference gates are computed before any comparison or rejected-output projection.
    predecessor_methodology_id_canonical = _is_plain_non_empty_string(predecessor.methodology_id)
    predecessor_correlation_id_canonical = _is_plain_non_empty_string(predecessor.correlation_id)

    policy_id_canonical = _is_plain_non_empty_string(policy.policy_id)
    policy_correlation_id_canonical = _is_plain_non_empty_string(policy.correlation_id)
    policy_approval_reference_canonical = _is_plain_non_empty_string(policy.approval_reference)
    policy_digest_canonical = _is_hex64_string(policy.policy_digest)
    policy_expected_fill_parameters_digest_canonical = _is_hex64_string(policy.expected_fill_model_parameters_digest)
    policy_approval_digest_canonical = _is_hex64_string(policy.approval_digest)
    policy_hit_rate_floor_canonical = _scale18_in_range(policy.approved_hit_rate_floor, Decimal(0), Decimal(1))
    policy_fill_rate_floor_canonical = _scale18_in_range(policy.approved_fill_rate_floor, Decimal(0), Decimal(1))
    policy_slippage_ceiling_canonical = _scale18_in_range(policy.approved_slippage_ceiling_bps, Decimal(0), None)
    policy_min_decided_count_canonical = (
        _is_exact_int(policy.approved_min_decided_episode_count) and policy.approved_min_decided_episode_count >= 1
    )
    policy_thresholds_approved = policy.thresholds_approved is True

    precondition_id_canonical = _is_plain_non_empty_string(precondition.precondition_id)
    precondition_correlation_id_canonical = _is_plain_non_empty_string(precondition.correlation_id)
    precondition_policy_id_canonical = _is_plain_non_empty_string(precondition.policy_id)
    precondition_policy_digest_canonical = _is_hex64_string(precondition.policy_digest)
    precondition_market_symbol_canonical = _is_plain_non_empty_string(precondition.market_symbol)
    precondition_hit_rate_floor_canonical = _scale18_in_range(
        precondition.approved_hit_rate_floor, Decimal(0), Decimal(1)
    )
    precondition_fill_rate_floor_canonical = _scale18_in_range(
        precondition.approved_fill_rate_floor, Decimal(0), Decimal(1)
    )
    precondition_slippage_ceiling_canonical = _scale18_in_range(
        precondition.approved_slippage_ceiling_bps, Decimal(0), None
    )
    precondition_min_decided_count_canonical = (
        _is_exact_int(precondition.approved_min_decided_episode_count)
        and precondition.approved_min_decided_episode_count >= 1
    )

    # 7-9. Predecessor v1 readiness, frozen governance literals, and correlation continuity.
    predecessor_ready_ok = (
        predecessor.status is PaperVsBacktestMethodologyStatus.READY
        and predecessor.ready is True
        and _is_exact_empty_tuple(predecessor.reason_codes)
    )
    if not predecessor_ready_ok:
        hard.append(_reason("predecessor_methodology_not_ready"))
    predecessor_contract_ok = (
        _plain_strings_equal(predecessor.schema_version, _EXPECTED_PREDECESSOR_SCHEMA_VERSION)
        and _plain_strings_equal(predecessor.methodology_version, _EXPECTED_PREDECESSOR_METHODOLOGY_VERSION)
        and _plain_strings_equal(predecessor.comparison_basis, _COMPARISON_BASIS)
        and _plain_strings_equal(predecessor.enforced_guardrail_policy, _ENFORCED_GUARDRAIL_POLICY)
        and _plain_strings_equal(predecessor.secondary_guardrail_policy, _V1_DECLARED_NOT_ENFORCED)
        and _plain_strings_equal(predecessor.hit_rate_guardrail_policy, _V1_DECLARED_NOT_ENFORCED)
        and _plain_strings_equal(predecessor.fill_rate_guardrail_policy, _V1_DECLARED_NOT_ENFORCED)
        and _plain_strings_equal(predecessor.slippage_guardrail_policy, _V1_DECLARED_NOT_ENFORCED)
        and _plain_strings_equal(predecessor.drawdown_guardrail_policy, _V1_DECLARED_NOT_ENFORCED)
        and _plain_strings_equal(predecessor.sharpe_retention_ratio, _SHARPE_RETENTION_RATIO)
        and _exact_ints_equal(predecessor.min_duration_days, _MIN_DURATION_DAYS)
        and _plain_strings_equal(predecessor.risk_free_policy_id, _RISK_FREE_POLICY_ID)
        and _exact_ints_equal(predecessor.annualization_factor, _ANNUALIZATION_FACTOR)
        and _plain_strings_equal(predecessor.annualization_policy, _ANNUALIZATION_POLICY)
        and _plain_strings_equal(predecessor.stddev_policy, _STDDEV_POLICY)
        and _plain_strings_equal(predecessor.decimal_policy, _DECIMAL_POLICY)
        and _exact_ints_equal(predecessor.decimal_scale, _DECIMAL_SCALE)
        and _plain_strings_equal(predecessor.decimal_rounding, _DECIMAL_ROUNDING)
        and _exact_ints_equal(predecessor.decimal_internal_precision, _DECIMAL_INTERNAL_PRECISION)
        and predecessor_methodology_id_canonical
        and predecessor_correlation_id_canonical
        and predecessor_metadata_canonical
    )
    if not predecessor_contract_ok:
        hard.append(_reason("predecessor_methodology_contract_mismatch"))

    # 10-11. Policy readiness (including the ready echo), definitions, fill-model reference,
    # decimal/Fraction and approval contract. A digest-valid policy with any incoherent
    # status/ready/secondary_metrics_policy_ready/reason combination is REJECTED.
    policy_ready_ok = (
        policy.status is SecondaryMetricsPolicyStatus.POLICY_READY
        and policy.ready is True
        and policy.secondary_metrics_policy_ready is True
        and _is_exact_empty_tuple(policy.reason_codes)
    )
    if not policy_ready_ok:
        hard.append(_reason("secondary_metrics_policy_not_ready"))
    policy_contract_ok = (
        _plain_strings_equal(policy.schema_version, _EXPECTED_POLICY_SCHEMA_VERSION)
        and _plain_strings_equal(policy.policy_version, _EXPECTED_POLICY_VERSION)
        and _plain_strings_equal(policy.hit_rate_definition, _HIT_RATE_DEFINITION)
        and _plain_strings_equal(policy.fill_rate_definition, _FILL_RATE_DEFINITION)
        and _plain_strings_equal(policy.slippage_definition, _SLIPPAGE_DEFINITION)
        and _plain_strings_equal(policy.expected_fill_model_reference, _EXPECTED_FILL_MODEL_REFERENCE)
        and policy_expected_fill_parameters_digest_canonical
        and _plain_strings_equal(policy.decimal_policy, _SECONDARY_METRICS_DECIMAL_POLICY)
        and _exact_ints_equal(policy.decimal_scale, _SECONDARY_METRICS_DECIMAL_SCALE)
        and _plain_strings_equal(policy.decimal_rounding, _SECONDARY_METRICS_DECIMAL_ROUNDING)
        and policy.fraction_intermediates_required is True
        and policy_approval_reference_canonical
        and policy_approval_digest_canonical
        and policy_thresholds_approved
        and policy_hit_rate_floor_canonical
        and policy_fill_rate_floor_canonical
        and policy_slippage_ceiling_canonical
        and policy_min_decided_count_canonical
        and policy_id_canonical
        and policy_correlation_id_canonical
        and policy_digest_canonical
        and policy_metadata_canonical
    )
    if not policy_contract_ok:
        hard.append(_reason("secondary_metrics_policy_contract_mismatch"))

    # 12. Precondition readiness, nested digest formats, and identity/metadata canonicality.
    precondition_ready_ok = (
        precondition.status is PaperSecondaryMetricsEnforcementPreconditionStatus.PRECONDITION_READY
        and precondition.ready is True
        and _is_exact_empty_tuple(precondition.reason_codes)
    )
    if not precondition_ready_ok:
        hard.append(_reason("secondary_metrics_enforcement_precondition_not_ready"))
    precondition_contract_ok = (
        _plain_strings_equal(precondition.schema_version, _EXPECTED_PRECONDITION_SCHEMA_VERSION)
        and _plain_strings_equal(precondition.precondition_version, _EXPECTED_PRECONDITION_VERSION)
        and precondition_policy_digest_canonical
        and _is_hex64_string(precondition.metrics_evidence_digest)
        and _is_hex64_string(precondition.reconciliation_digest)
        and precondition_id_canonical
        and precondition_correlation_id_canonical
        and precondition_policy_id_canonical
        and precondition_market_symbol_canonical
        and precondition_metadata_canonical
    )
    if not precondition_contract_ok:
        hard.append(_reason("secondary_metrics_enforcement_precondition_contract_mismatch"))

    # Structural safety / claim flags across all three anchors.
    if (
        _flag_failure(predecessor, _PREDECESSOR_TRUE_FLAGS, _PREDECESSOR_FALSE_FLAGS)
        or _flag_failure(policy, _POLICY_TRUE_FLAGS, _POLICY_FALSE_FLAGS)
        or _flag_failure(precondition, _PRECONDITION_TRUE_FLAGS, _PRECONDITION_FALSE_FLAGS)
    ):
        hard.append(_reason("unsafe_flags"))

    # 13. Cross-binding: policy id/digest, correlations, market symbol, threshold echoes.
    policy_id_binding_ok = (
        precondition_policy_id_canonical and policy_id_canonical and precondition.policy_id == policy.policy_id
    )
    policy_digest_binding_ok = (
        precondition_policy_digest_canonical
        and policy_digest_canonical
        and precondition.policy_digest == policy.policy_digest
    )
    policy_binding_ok = policy_id_binding_ok and policy_digest_binding_ok
    if not policy_binding_ok:
        hard.append(_reason("policy_binding_mismatch"))
    correlation_ok = (
        predecessor_correlation_id_canonical
        and predecessor.correlation_id == correlation_id
        and policy_correlation_id_canonical
        and policy.correlation_id == correlation_id
        and precondition_correlation_id_canonical
        and precondition.correlation_id == correlation_id
    )
    if not correlation_ok:
        hard.append(_reason("correlation_id_mismatch"))
    market_symbol_valid = precondition_market_symbol_canonical and not _has_any_scope_violation(
        precondition.market_symbol
    )
    if not market_symbol_valid:
        hard.append(_reason("market_symbol_invalid"))
    threshold_snapshot_ok = (
        precondition_hit_rate_floor_canonical
        and policy_hit_rate_floor_canonical
        and precondition.approved_hit_rate_floor == policy.approved_hit_rate_floor
        and precondition_fill_rate_floor_canonical
        and policy_fill_rate_floor_canonical
        and precondition.approved_fill_rate_floor == policy.approved_fill_rate_floor
        and precondition_slippage_ceiling_canonical
        and policy_slippage_ceiling_canonical
        and precondition.approved_slippage_ceiling_bps == policy.approved_slippage_ceiling_bps
        and precondition_min_decided_count_canonical
        and policy_min_decided_count_canonical
        and precondition.approved_min_decided_episode_count == policy.approved_min_decided_episode_count
    )
    if not threshold_snapshot_ok:
        hard.append(_reason("threshold_snapshot_mismatch"))

    # 14-15. Independently recompute every threshold pass from precondition-carried computed values.
    hit_floor = _parse_scale18(policy.approved_hit_rate_floor)
    fill_floor = _parse_scale18(policy.approved_fill_rate_floor)
    slippage_ceiling = _parse_scale18(policy.approved_slippage_ceiling_bps)
    hit_rate = _parse_scale18(precondition.computed_hit_rate)
    fill_quantity = _parse_scale18(precondition.computed_fill_rate_by_quantity)
    fill_episode = _parse_scale18(precondition.computed_fill_rate_by_episode)
    slippage = _parse_scale18(precondition.computed_slippage_bps)

    hit_pass = hit_floor is not None and hit_rate is not None and hit_rate >= hit_floor
    fill_quantity_pass = fill_floor is not None and fill_quantity is not None and fill_quantity >= fill_floor
    fill_episode_pass = fill_floor is not None and fill_episode is not None and fill_episode >= fill_floor
    fill_pass = fill_quantity_pass and fill_episode_pass
    # SM-5 boundary: a ``None`` computed slippage passes vacuously when a ceiling exists; SM-6 rejects None.
    slippage_pass = slippage_ceiling is not None and (
        precondition.computed_slippage_bps is None or (slippage is not None and slippage <= slippage_ceiling)
    )
    min_decided_pass = (
        _is_exact_int(policy.approved_min_decided_episode_count)
        and _is_exact_int(precondition.computed_decided_episode_count)
        and precondition.computed_decided_episode_count >= policy.approved_min_decided_episode_count
    )
    all_thresholds_cleared = hit_pass and fill_pass and slippage_pass and min_decided_pass

    threshold_pass_coherent = (
        precondition.hit_rate_passed is hit_pass
        and precondition.fill_rate_by_quantity_passed is fill_quantity_pass
        and precondition.fill_rate_by_episode_passed is fill_episode_pass
        and precondition.fill_rate_passed is fill_pass
        and precondition.slippage_passed is slippage_pass
        and precondition.min_decided_episode_count_passed is min_decided_pass
    )
    if not threshold_pass_coherent:
        hard.append(_reason("threshold_pass_incoherent"))

    # 16-18. Record-set / count coherence (decided count may be below records but never exceed them).
    record_digests = precondition.record_digests if type(precondition.record_digests) is tuple else ()
    record_digests_ok = (
        type(precondition.record_digests) is tuple
        and all(_is_hex64_string(digest) for digest in record_digests)
        and list(record_digests) == sorted(record_digests)
        and len(set(record_digests)) == len(record_digests)
    )
    counts_ok = (
        _is_exact_int(precondition.metrics_record_count)
        and _is_exact_int(precondition.reconciled_record_count)
        and _is_exact_int(precondition.reconciled_episode_count)
        and _is_exact_int(precondition.computed_decided_episode_count)
        and len(record_digests) == precondition.metrics_record_count
        and precondition.metrics_record_count == precondition.reconciled_record_count
        and precondition.reconciled_record_count == precondition.reconciled_episode_count
        and 0 <= precondition.computed_decided_episode_count <= precondition.metrics_record_count
    )
    record_set_ok = record_digests_ok and counts_ok
    if not record_set_ok:
        hard.append(_reason("record_set_incoherent"))

    # 19. Anchor-carried identity/scope text (REJECTED, never a caller-input RAISE). Metadata keys and
    # values carried by all three anchors are scanned too — a coherent resealed anchor must not smuggle
    # BIST/scope/clock text through metadata. Texts are extracted only from metadata that already passed
    # the exact canonical-representation validation above; a noncanonical representation is REJECTED by
    # its anchor's contract check and is never silently skipped, so the scan itself can never crash.
    anchor_metadata_texts = (
        *(_metadata_texts(predecessor.metadata) if predecessor_metadata_canonical else ()),
        *(_metadata_texts(policy.metadata) if policy_metadata_canonical else ()),
        *(_metadata_texts(precondition.metadata) if precondition_metadata_canonical else ()),
    )
    anchor_texts = (
        *((predecessor.methodology_id,) if predecessor_methodology_id_canonical else ()),
        *((predecessor.correlation_id,) if predecessor_correlation_id_canonical else ()),
        *((policy.policy_id,) if policy_id_canonical else ()),
        *((policy.correlation_id,) if policy_correlation_id_canonical else ()),
        *((policy.approval_reference,) if policy_approval_reference_canonical else ()),
        *((precondition.precondition_id,) if precondition_id_canonical else ()),
        *((precondition.correlation_id,) if precondition_correlation_id_canonical else ()),
        *((precondition.policy_id,) if precondition_policy_id_canonical else ()),
        *anchor_metadata_texts,
    )
    anchor_scope_ok = not _has_any_scope_violation(*anchor_texts)
    if not anchor_scope_ok:
        hard.append(_reason("anchor_scope_violation"))

    # 20-21. Sorted, unique reasons select the status.
    reason_codes = _sorted_unique(hard)
    ready = not reason_codes

    # 24-25. Final READY invariant guard — READY is impossible unless every named gate independently
    # re-proves: digest triples, canonical metadata, canonical identities, ready echoes, anchor contracts,
    # cross-bindings, threshold passes, record/count coherence, and scope safety.
    if ready and not (
        predecessor_digest_ok
        and policy_digest_ok
        and precondition_digest_ok
        and predecessor_metadata_canonical
        and policy_metadata_canonical
        and precondition_metadata_canonical
        and predecessor_methodology_id_canonical
        and predecessor_correlation_id_canonical
        and policy_id_canonical
        and policy_correlation_id_canonical
        and policy_approval_reference_canonical
        and policy_digest_canonical
        and precondition_id_canonical
        and precondition_correlation_id_canonical
        and precondition_policy_id_canonical
        and precondition_policy_digest_canonical
        and precondition_market_symbol_canonical
        and predecessor_ready_ok
        and predecessor_contract_ok
        and policy_ready_ok
        and policy_contract_ok
        and precondition_ready_ok
        and precondition_contract_ok
        and policy_binding_ok
        and correlation_ok
        and market_symbol_valid
        and threshold_snapshot_ok
        and threshold_pass_coherent
        and record_set_ok
        and anchor_scope_ok
        and all_thresholds_cleared
        and policy.thresholds_approved is True
    ):
        reason_codes = (_reason("ready_invariant_failed"),)
        ready = False

    status = (
        PaperVsBacktestMethodologyV2Status.METHODOLOGY_READY
        if ready
        else PaperVsBacktestMethodologyV2Status.METHODOLOGY_REJECTED
    )

    # 22-23. Verified digests populated only per passing triple; consumed / enforced flags equal final READY.
    field_values: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "methodology_version": _METHODOLOGY_VERSION,
        "status": status,
        "ready": ready,
        "methodology_id": methodology_id,
        "correlation_id": correlation_id,
        "predecessor_methodology_id": predecessor.methodology_id if predecessor_methodology_id_canonical else "",
        "secondary_metrics_policy_id": policy.policy_id if policy_id_canonical else "",
        "secondary_metrics_enforcement_precondition_id": (
            precondition.precondition_id if precondition_id_canonical else ""
        ),
        "market_symbol": precondition.market_symbol if precondition_market_symbol_canonical else "",
        "expected_predecessor_methodology_digest": expected_predecessor_methodology_digest,
        "verified_predecessor_methodology_digest": predecessor.methodology_digest if predecessor_digest_ok else "",
        "expected_secondary_metrics_policy_digest": expected_secondary_metrics_policy_digest,
        "verified_secondary_metrics_policy_digest": policy.policy_digest if policy_digest_ok else "",
        "expected_secondary_metrics_enforcement_precondition_digest": (
            expected_secondary_metrics_enforcement_precondition_digest
        ),
        "verified_secondary_metrics_enforcement_precondition_digest": (
            precondition.precondition_digest if precondition_digest_ok else ""
        ),
        "comparison_basis": _COMPARISON_BASIS,
        "enforced_guardrail_policy": _ENFORCED_GUARDRAIL_POLICY,
        "secondary_guardrail_policy": _SECONDARY_GUARDRAIL_POLICY,
        "sharpe_retention_ratio": _SHARPE_RETENTION_RATIO,
        "min_duration_days": _MIN_DURATION_DAYS,
        "risk_free_policy_id": _RISK_FREE_POLICY_ID,
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
        "hit_rate_definition": _HIT_RATE_DEFINITION,
        "fill_rate_definition": _FILL_RATE_DEFINITION,
        "slippage_definition": _SLIPPAGE_DEFINITION,
        "hit_rate_operator": _HIT_RATE_OPERATOR,
        "fill_rate_operator": _FILL_RATE_OPERATOR,
        "slippage_operator": _SLIPPAGE_OPERATOR,
        "expected_fill_model_reference": _EXPECTED_FILL_MODEL_REFERENCE,
        "expected_fill_model_parameters_digest": (
            policy.expected_fill_model_parameters_digest if policy_expected_fill_parameters_digest_canonical else None
        ),
        "secondary_metrics_decimal_policy": _SECONDARY_METRICS_DECIMAL_POLICY,
        "secondary_metrics_decimal_scale": _SECONDARY_METRICS_DECIMAL_SCALE,
        "secondary_metrics_decimal_rounding": _SECONDARY_METRICS_DECIMAL_ROUNDING,
        "fraction_intermediates_required": _FRACTION_INTERMEDIATES_REQUIRED,
        "approved_hit_rate_floor": policy.approved_hit_rate_floor if policy_hit_rate_floor_canonical else None,
        "approved_fill_rate_floor": policy.approved_fill_rate_floor if policy_fill_rate_floor_canonical else None,
        "approved_slippage_ceiling_bps": (
            policy.approved_slippage_ceiling_bps if policy_slippage_ceiling_canonical else None
        ),
        "approved_min_decided_episode_count": (
            policy.approved_min_decided_episode_count if policy_min_decided_count_canonical else None
        ),
        "approval_reference": policy.approval_reference if policy_approval_reference_canonical else None,
        "approval_digest": policy.approval_digest if policy_approval_digest_canonical else None,
        "thresholds_approved": policy_thresholds_approved,
        "hit_rate_floor_enforced": ready,
        "fill_rate_floor_enforced": ready,
        "slippage_ceiling_enforced": ready,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
        "predecessor_methodology_consumed": ready,
        "secondary_metrics_policy_consumed": ready,
        "secondary_metrics_enforcement_precondition_consumed": ready,
    }
    seed = PaperVsBacktestMethodologyV2(methodology_digest="", **field_values)  # type: ignore[arg-type]
    return _replace_methodology_digest(seed, paper_vs_backtest_methodology_v2_digest(seed))


def _replace_methodology_digest(methodology: PaperVsBacktestMethodologyV2, digest: str) -> PaperVsBacktestMethodologyV2:
    values = {
        field.name: getattr(methodology, field.name)
        for field in fields(methodology)
        if field.name != "methodology_digest"
    }
    values["methodology_digest"] = digest
    return PaperVsBacktestMethodologyV2(**values)  # type: ignore[arg-type]


def _methodology_payload_from(methodology: PaperVsBacktestMethodologyV2) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(methodology):
        if field.name == "methodology_digest":
            continue
        value = getattr(methodology, field.name)
        if field.name == "status":
            payload[field.name] = value.value if isinstance(value, PaperVsBacktestMethodologyV2Status) else value
        elif field.name == "reason_codes":
            payload[field.name] = list(methodology.reason_codes)
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(methodology.metadata)
        else:
            payload[field.name] = value
    return payload


def paper_vs_backtest_methodology_v2_to_dict(methodology: PaperVsBacktestMethodologyV2) -> dict[str, object]:
    """Canonical JSON-ready mapping for the methodology-v2 snapshot, including its self-digest."""

    payload = _methodology_payload_from(methodology)
    payload["methodology_digest"] = methodology.methodology_digest
    return payload


def paper_vs_backtest_methodology_v2_digest(methodology: PaperVsBacktestMethodologyV2) -> str:
    """Recompute the canonical methodology-v2 digest, excluding only the self-digest field."""

    return _canonical_digest(_methodology_payload_from(methodology))


__all__ = [
    "PaperVsBacktestMethodologyV2",
    "PaperVsBacktestMethodologyV2Error",
    "PaperVsBacktestMethodologyV2Status",
    "build_paper_vs_backtest_methodology_v2",
    "paper_vs_backtest_methodology_v2_digest",
    "paper_vs_backtest_methodology_v2_to_dict",
]
