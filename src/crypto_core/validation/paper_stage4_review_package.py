"""Paper Stage-4 review package — deterministic, paper-only, fail-closed, digest-bound, operator-reviewable
evidence dossier (phase-map slice §10.4.5, the terminal §10.4 product slice).

This artifact assembles and RE-PROVES the already-merged deterministic §10.4 paper-metrics evidence chain into
one operator-reviewable dossier. It COMPUTES NOTHING NEW: it consumes six already-built, digest-bound artifacts,
re-proves each self-digest via its PUBLIC serializer against an independent caller anchor, re-checks each
artifact's safety / non-overclaim posture, proves they describe ONE same evidence chain (cross-bound through the
shared metrics-summary / time-window / methodology / series digests each downstream artifact already carries),
requires the ≥30-day evidence gate to be SATISFIED, and emits one frozen, digest-bound
``PaperStage4ReviewPackage``.

Consumed chain (all merged to ``main``):
``PaperSessionMetricsSummary`` (§10.4.1) → ``PaperDeterministicTimeWindowEvidence`` (§10.4.2) →
``PaperVsBacktestComparatorBridgeEvidence`` (§10.4.3, fail-closed BLOCKED bridge) +
``PaperReturnSeriesMethodology`` (§10.3) → ``PaperDailyReturnSeriesEvidence`` (§10.3) →
``PaperThirtyDayEvidenceGateDecision`` (§10.4.4).

It is REVIEW-ONLY: ``status=READY`` (== ``ready``) means ONLY that a deterministic, same-chain, operator-reviewable
dossier was assembled. It does NOT mean the evidence was approved, NOT that operator review is complete, NOT
PRDV4 Stage-4 completion, NOT that the paper-vs-backtest comparison is ready (the consumed bridge is a fail-closed
BLOCKED bridge — the comparator is never run), NOT live / shadow / Deribit / operational readiness, and NOT a
profitability / edge proof. ``operator_review_required=True`` while ``operator_review_complete`` /
``approval_granted`` / ``comparison_ready`` / ``prdv4_stage4_complete`` and every live/shadow/Deribit/readiness/
profitability/edge/execution/order/capital flag are explicit ``False``, serializer-visible and digest-bound.

It computes NO Sharpe, NO annualized Sharpe, NO return series (it references the already-merged daily evidence),
runs NO comparator, constructs / imports NO ``Stage4PaperSummary``, and imports neither ``stage4_comparator`` nor
any ``crypto_core.service`` / ``execution`` / ``venue`` / ``runtime`` surface, no Deribit, no BIST. Deterministic
and immutable; no wall-clock/random/IO; inputs unmutated. The optional §7.7 ``PaperStage4ReadinessDecision`` is an
ORTHOGONAL chain (replay/governor, not the §10.4 metrics chain) and is intentionally NOT consumed in v1
(``paper_stage4_readiness_decision_consumed=False``).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_30day_evidence_gate_decision import (
    PaperThirtyDayEvidenceGateDecision,
    PaperThirtyDayEvidenceGateDecisionStatus,
    paper_30day_evidence_gate_decision_digest,
)
from crypto_core.validation.paper_daily_return_series_evidence import (
    PaperDailyReturnSeriesEvidence,
    PaperDailyReturnSeriesEvidenceStatus,
    paper_daily_return_series_evidence_digest,
)
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    PaperDeterministicTimeWindowEvidence,
    PaperDeterministicTimeWindowEvidenceStatus,
    paper_deterministic_time_window_evidence_digest,
)
from crypto_core.validation.paper_return_series_methodology import (
    PaperReturnSeriesMethodology,
    PaperReturnSeriesMethodologyStatus,
    paper_return_series_methodology_digest,
)
from crypto_core.validation.paper_session_metrics_summary import (
    PaperSessionMetricsSummary,
    PaperSessionMetricsSummaryStatus,
    paper_session_metrics_summary_digest,
)
from crypto_core.validation.paper_vs_backtest_comparator_bridge import (
    PaperVsBacktestComparatorBridgeEvidence,
    PaperVsBacktestComparatorBridgeStatus,
    paper_vs_backtest_comparator_bridge_digest,
)

_SCHEMA_VERSION = "paper-stage4-review-package.v1"
_PACKAGE_VERSION = "paper-stage4-review-package.v1"

_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# Review-package posture notes recorded only when the dossier assembles READY (deterministic, sorted).
_READY_FINDINGS = (
    "paper_stage4_review_package:comparison_not_ready_paper_inputs_missing",
    "paper_stage4_review_package:deterministic_paper_evidence_chain_complete",
    "paper_stage4_review_package:not_prdv4_stage4_complete",
    "paper_stage4_review_package:operator_review_required",
    "paper_stage4_review_package:thirty_day_gate_satisfied",
)

# Scope guard mirrors the sibling validation modules and additionally rejects approval/trade/production/execution
# tokens (a review package must never carry approval or execution identifiers). Market-data terms scrubbed first.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"stage4_comparator|compare_stage4|Stage4PaperSummary|capital|margin|balance|reservation|"
    r"real_account_equity|account_equity|real_equity|approv|trade|production)\w*"
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


class PaperStage4ReviewPackageError(RuntimeError):
    """Raised on call-level malformed input (wrong-typed artifacts / ids / digests / metadata / tokens)."""


class PaperStage4ReviewPackageStatus(str, Enum):
    """Whether a deterministic, same-chain, operator-reviewable dossier could be assembled. READY is assembly
    only — never approval, Stage-4 completion, comparison readiness, or live/shadow/Deribit readiness."""

    READY = "READY"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperStage4ReviewPackage:
    """Deterministic, immutable, digest-bound paper Stage-4 review-only evidence dossier.

    ``status`` READY only when all six consumed §10.4 artifacts re-prove, cross-bind to one chain, are paper-safe /
    non-over-claiming, and the ≥30-day gate is satisfied. ``ready`` mirrors ``status == READY`` (dossier assembled).
    Review-only: ``operator_review_required`` True; ``operator_review_complete`` / ``approval_granted`` /
    ``comparison_ready`` / ``prdv4_stage4_complete`` and every live/shadow/Deribit/readiness/profitability/edge/
    execution/order/capital flag are ``False``, digest-bound. NOT PRDV4 Stage 4, NOT live/shadow readiness, NOT an
    actual comparison, NOT a Sharpe/profitability/edge proof.
    """

    schema_version: str
    package_version: str
    status: PaperStage4ReviewPackageStatus
    ready: bool
    review_package_id: str
    paper_id: str
    correlation_id: str
    market_symbol: str
    # consumed-artifact expected (caller) anchors + verified (stored==recomputed) digests
    expected_metrics_summary_digest: str
    metrics_summary_digest: str
    expected_time_window_digest: str
    time_window_digest: str
    expected_comparator_bridge_digest: str
    comparator_bridge_digest: str
    expected_return_series_methodology_digest: str
    return_series_methodology_digest: str
    expected_daily_return_series_digest: str
    daily_return_series_digest: str
    expected_thirty_day_gate_decision_digest: str
    thirty_day_gate_decision_digest: str
    # consumed-artifact statuses (string values)
    metrics_summary_status: str
    time_window_status: str
    comparator_bridge_status: str
    return_series_methodology_status: str
    daily_return_series_status: str
    thirty_day_gate_decision_status: str
    # carried review-dossier facts (no recomputation — copied from the re-proven artifacts)
    thirty_day_gate_satisfied: bool
    thirty_day_gate_minimum_bucket_count: int
    thirty_day_gate_bucket_count: int
    thirty_day_gate_daily_return_count: int
    thirty_day_gate_used_bucket_count: int
    thirty_day_gate_used_first_bucket_id: str
    thirty_day_gate_used_last_bucket_id: str
    thirty_day_gate_used_first_bucket_start_ns: int
    thirty_day_gate_used_last_bucket_end_ns: int
    comparator_comparison_ready: bool
    comparator_stage4_comparator_invoked: bool
    comparator_missing_inputs: tuple[str, ...]
    daily_return_series_bucket_count: int
    daily_return_series_return_count: int
    # evidence-chain consumption flags (True only when every required artifact verified)
    metrics_summary_consumed: bool
    time_window_evidence_consumed: bool
    comparator_bridge_consumed: bool
    return_series_methodology_consumed: bool
    daily_return_series_evidence_consumed: bool
    thirty_day_gate_consumed: bool
    evidence_chain_consumed: bool
    review_findings: tuple[str, ...]
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    review_package_digest: str
    paper_only: bool = True
    stage4_review_package: bool = True
    review_only: bool = True
    operator_review_required: bool = True
    paper_stage4_readiness_decision_consumed: bool = False
    operator_review_complete: bool = False
    approval_granted: bool = False
    comparison_ready: bool = False
    stage4_comparator_invoked: bool = False
    prdv4_stage4_complete: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    production_execution: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    real_wall_clock_used: bool = False
    real_account_equity_used: bool = False
    real_capital_used: bool = False
    sharpe_computed: bool = False
    paper_sharpe_computed: bool = False
    annualized_sharpe_computed: bool = False
    return_series_constructed: bool = False


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


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _str_or_empty(value: object) -> str:
    return value if type(value) is str else ""


def _int_or_zero(value: object) -> int:
    return value if _is_exact_int(value) else 0


def _bool_or_false(value: object) -> bool:
    return value if type(value) is bool else False


def _str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not tuple:
        return ()
    return tuple(item for item in value if type(item) is str)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperStage4ReviewPackageError("paper_stage4_review_package:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise PaperStage4ReviewPackageError("paper_stage4_review_package:metadata_malformed")
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise PaperStage4ReviewPackageError("paper_stage4_review_package:metadata_malformed")
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise PaperStage4ReviewPackageError("paper_stage4_review_package:metadata_malformed")
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


def _reprove_digest(artifact: object, recompute, stored: object, expected: str, label: str) -> str | None:
    """Re-prove a consumed artifact self-digest via its PUBLIC serializer AND the caller anchor. Reason or None."""
    try:
        recomputed = recompute(artifact)
    except Exception:  # noqa: BLE001 - any recompute failure is a fail-closed rejection, not a crash
        return f"paper_stage4_review_package:{label}_malformed"
    if not _is_hex64_string(stored) or stored != recomputed or stored != expected:
        return f"paper_stage4_review_package:{label}_digest_mismatch"
    return None


def _metrics_summary_safe(summary: PaperSessionMetricsSummary) -> bool:
    return (
        summary.status is PaperSessionMetricsSummaryStatus.READY
        and summary.paper_only is True
        and summary.prdv4_stage4_complete is False
        and summary.live_ready is False
        and summary.shadow_ready is False
        and summary.profitability_proven is False
        and summary.edge_proven is False
        and summary.production_execution is False
        and summary.real_orders_enabled is False
        and summary.real_money_enabled is False
        and summary.real_capital_reserved is False
        and summary.live_api_called is False
        and summary.scheduler_enabled is False
        and summary.auto_loop_enabled is False
        and summary.connector_invoked is False
        and summary.deribit_ready is False
        and summary.operational_readiness is False
        and summary.sharpe_computed is False
        and summary.return_series_computed is False
        and summary.thirty_day_gate_satisfied is False
    )


def _time_window_safe(window: PaperDeterministicTimeWindowEvidence) -> bool:
    return (
        window.status is PaperDeterministicTimeWindowEvidenceStatus.READY
        and window.ready is True
        and window.paper_only is True
        and window.injected_deterministic_time_window is True
        and window.prdv4_stage4_complete is False
        and window.live_ready is False
        and window.shadow_ready is False
        and window.profitability_proven is False
        and window.edge_proven is False
        and window.production_execution is False
        and window.real_orders_enabled is False
        and window.real_money_enabled is False
        and window.real_capital_reserved is False
        and window.live_api_called is False
        and window.scheduler_enabled is False
        and window.auto_loop_enabled is False
        and window.connector_invoked is False
        and window.deribit_ready is False
        and window.operational_readiness is False
        and window.sharpe_computed is False
        and window.return_series_computed is False
        and window.thirty_day_gate_satisfied is False
        and window.stage4_comparator_invoked is False
        and window.real_wall_clock_used is False
        and window.timestamp_origin_proven is False
    )


def _comparator_bridge_safe(bridge: PaperVsBacktestComparatorBridgeEvidence) -> bool:
    return (
        bridge.status is PaperVsBacktestComparatorBridgeStatus.READY
        and bridge.ready is True
        and bridge.paper_only is True
        and bridge.comparison_ready is False
        and bridge.stage4_comparator_invoked is False
        and bridge.paper_vs_backtest_comparison_ready is False
        and bridge.prdv4_stage4_complete is False
        and bridge.live_ready is False
        and bridge.shadow_ready is False
        and bridge.profitability_proven is False
        and bridge.edge_proven is False
        and bridge.production_execution is False
        and bridge.real_orders_enabled is False
        and bridge.real_money_enabled is False
        and bridge.real_capital_reserved is False
        and bridge.live_api_called is False
        and bridge.scheduler_enabled is False
        and bridge.auto_loop_enabled is False
        and bridge.connector_invoked is False
        and bridge.deribit_ready is False
        and bridge.operational_readiness is False
        and bridge.sharpe_computed is False
        and bridge.return_series_computed is False
        and bridge.thirty_day_gate_satisfied is False
        and bridge.real_wall_clock_used is False
        and bridge.timestamp_origin_proven is False
    )


def _methodology_safe(methodology: PaperReturnSeriesMethodology) -> bool:
    return (
        methodology.status is PaperReturnSeriesMethodologyStatus.READY
        and methodology.ready is True
        and methodology.paper_only is True
        and methodology.methodology_snapshot is True
        and methodology.daily_utc_only is True
        and methodology.normalized_paper_equity_index is True
        and methodology.real_account_equity_used is False
        and methodology.real_capital_used is False
        and methodology.return_series_computed is False
        and methodology.daily_returns_computed is False
        and methodology.sharpe_computed is False
        and methodology.paper_sharpe_computed is False
        and methodology.thirty_day_gate_satisfied is False
        and methodology.comparison_ready is False
        and methodology.stage4_comparator_invoked is False
        and methodology.prdv4_stage4_complete is False
        and methodology.live_ready is False
        and methodology.shadow_ready is False
        and methodology.operational_readiness is False
        and methodology.deribit_ready is False
        and methodology.profitability_proven is False
        and methodology.edge_proven is False
        and methodology.production_execution is False
        and methodology.real_orders_enabled is False
        and methodology.real_money_enabled is False
        and methodology.real_capital_reserved is False
        and methodology.live_api_called is False
        and methodology.scheduler_enabled is False
        and methodology.auto_loop_enabled is False
        and methodology.connector_invoked is False
        and methodology.real_wall_clock_used is False
    )


def _daily_return_series_safe(series: PaperDailyReturnSeriesEvidence) -> bool:
    return (
        series.status is PaperDailyReturnSeriesEvidenceStatus.READY
        and series.ready is True
        and series.paper_only is True
        and series.daily_return_series_evidence is True
        and series.methodology_snapshot_consumed is True
        and series.injected_deterministic_time_window_consumed is True
        and series.daily_utc_only is True
        and series.normalized_paper_equity_index is True
        and series.mark_to_market_required is True
        and series.realized_only_primary_series is False
        and series.return_series_computed is True
        and series.daily_returns_computed is True
        and series.sample_eligible is True
        and series.sharpe_computed is False
        and series.paper_sharpe_computed is False
        and series.thirty_day_gate_satisfied is False
        and series.thirty_day_gate_decided is False
        and series.comparison_ready is False
        and series.stage4_comparator_invoked is False
        and series.prdv4_stage4_complete is False
        and series.live_ready is False
        and series.shadow_ready is False
        and series.operational_readiness is False
        and series.deribit_ready is False
        and series.profitability_proven is False
        and series.edge_proven is False
        and series.production_execution is False
        and series.real_orders_enabled is False
        and series.real_money_enabled is False
        and series.real_capital_reserved is False
        and series.live_api_called is False
        and series.scheduler_enabled is False
        and series.auto_loop_enabled is False
        and series.connector_invoked is False
        and series.real_wall_clock_used is False
        and series.real_account_equity_used is False
        and series.real_capital_used is False
    )


def _thirty_day_gate_safe(gate: PaperThirtyDayEvidenceGateDecision) -> bool:
    return (
        gate.status is PaperThirtyDayEvidenceGateDecisionStatus.READY
        and gate.ready is True
        and gate.thirty_day_gate_decided is True
        and gate.thirty_day_evidence_gate_decision is True
        and gate.daily_return_series_evidence_consumed is True
        and gate.paper_only is True
        and gate.sharpe_computed is False
        and gate.paper_sharpe_computed is False
        and gate.comparison_ready is False
        and gate.stage4_comparator_invoked is False
        and gate.prdv4_stage4_complete is False
        and gate.live_ready is False
        and gate.shadow_ready is False
        and gate.operational_readiness is False
        and gate.deribit_ready is False
        and gate.profitability_proven is False
        and gate.edge_proven is False
        and gate.production_execution is False
        and gate.real_orders_enabled is False
        and gate.real_money_enabled is False
        and gate.real_capital_reserved is False
        and gate.live_api_called is False
        and gate.scheduler_enabled is False
        and gate.auto_loop_enabled is False
        and gate.connector_invoked is False
        and gate.real_wall_clock_used is False
        and gate.real_account_equity_used is False
        and gate.real_capital_used is False
    )


def build_paper_stage4_review_package(
    metrics_summary: PaperSessionMetricsSummary,
    time_window_evidence: PaperDeterministicTimeWindowEvidence,
    comparator_bridge_evidence: PaperVsBacktestComparatorBridgeEvidence,
    return_series_methodology: PaperReturnSeriesMethodology,
    daily_return_series_evidence: PaperDailyReturnSeriesEvidence,
    thirty_day_gate_decision: PaperThirtyDayEvidenceGateDecision,
    *,
    expected_metrics_summary_digest: str,
    expected_time_window_digest: str,
    expected_comparator_bridge_digest: str,
    expected_return_series_methodology_digest: str,
    expected_daily_return_series_digest: str,
    expected_thirty_day_gate_decision_digest: str,
    review_package_id: str,
    paper_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperStage4ReviewPackage:
    """Assemble a deterministic, same-chain, review-only Stage-4 evidence dossier from six merged §10.4 artifacts.

    Each artifact must be its exact type; each ``expected_*_digest`` an exact plain 64-lowercase-hex ``str`` (the
    caller's INDEPENDENT anchor); ``review_package_id`` / ``paper_id`` / ``correlation_id`` exact plain non-empty
    ``str``; ``metadata`` ``Mapping[str, str]`` or ``None``. A wrong type, malformed digest, empty id, a forbidden
    BIST/live/order/capital/service/readiness/approval/trade token, a clock-suggesting token, or malformed metadata
    raises ``PaperStage4ReviewPackageError`` before any work.

    Each consumed self-digest is re-proven via its PUBLIC serializer (== stored == expected anchor); each artifact
    must be paper-safe + non-over-claiming with its expected status; the six must cross-bind to ONE chain (each
    downstream artifact's carried metrics-summary / time-window / methodology / series digests must equal the
    upstream artifact's self-digest) and agree on ``correlation_id`` / ``market_symbol``; the consumed
    comparator bridge must be a fail-closed BLOCKED bridge (``comparison_ready`` False, comparator not invoked); and
    the ≥30-day gate must be SATISFIED. ``status=READY`` over a fully trusted same-chain set; any trust / chain /
    safety / gate failure maps to ``status=REJECTED``. Review-only: assembling the dossier is never approval, never
    Stage-4 completion, never comparison/live/shadow/Deribit readiness. Deterministic and immutable; no
    wall-clock/random/IO; inputs unmutated; computes nothing new.
    """
    artifacts = (
        ("metrics_summary", metrics_summary, PaperSessionMetricsSummary),
        ("time_window_evidence", time_window_evidence, PaperDeterministicTimeWindowEvidence),
        ("comparator_bridge_evidence", comparator_bridge_evidence, PaperVsBacktestComparatorBridgeEvidence),
        ("return_series_methodology", return_series_methodology, PaperReturnSeriesMethodology),
        ("daily_return_series_evidence", daily_return_series_evidence, PaperDailyReturnSeriesEvidence),
        ("thirty_day_gate_decision", thirty_day_gate_decision, PaperThirtyDayEvidenceGateDecision),
    )
    for label, artifact, expected_type in artifacts:
        if type(artifact) is not expected_type:
            raise PaperStage4ReviewPackageError(f"paper_stage4_review_package:{label}_malformed")
    for label, digest in (
        ("expected_metrics_summary_digest", expected_metrics_summary_digest),
        ("expected_time_window_digest", expected_time_window_digest),
        ("expected_comparator_bridge_digest", expected_comparator_bridge_digest),
        ("expected_return_series_methodology_digest", expected_return_series_methodology_digest),
        ("expected_daily_return_series_digest", expected_daily_return_series_digest),
        ("expected_thirty_day_gate_decision_digest", expected_thirty_day_gate_decision_digest),
    ):
        if not _is_hex64_string(digest):
            raise PaperStage4ReviewPackageError(f"paper_stage4_review_package:{label}_invalid")
    for name, value in (
        ("review_package_id", review_package_id),
        ("paper_id", paper_id),
        ("correlation_id", correlation_id),
    ):
        if not _is_plain_non_empty_string(value):
            raise PaperStage4ReviewPackageError(f"paper_stage4_review_package:{name}_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    scope_texts = (review_package_id, paper_id, correlation_id, *_metadata_texts(metadata_pairs))
    if _has_scope_violation(*scope_texts):
        raise PaperStage4ReviewPackageError("paper_stage4_review_package:scope_violation")
    if _has_clock_token(*scope_texts):
        raise PaperStage4ReviewPackageError("paper_stage4_review_package:clock_token_forbidden")

    hard: list[str] = []

    # 1) Trust boundary: re-prove each consumed self-digest via its PUBLIC serializer AND the caller anchor.
    for reason in (
        _reprove_digest(
            metrics_summary,
            paper_session_metrics_summary_digest,
            metrics_summary.summary_digest,
            expected_metrics_summary_digest,
            "metrics_summary",
        ),
        _reprove_digest(
            time_window_evidence,
            paper_deterministic_time_window_evidence_digest,
            time_window_evidence.time_window_digest,
            expected_time_window_digest,
            "time_window",
        ),
        _reprove_digest(
            comparator_bridge_evidence,
            paper_vs_backtest_comparator_bridge_digest,
            comparator_bridge_evidence.bridge_digest,
            expected_comparator_bridge_digest,
            "comparator_bridge",
        ),
        _reprove_digest(
            return_series_methodology,
            paper_return_series_methodology_digest,
            return_series_methodology.methodology_digest,
            expected_return_series_methodology_digest,
            "return_series_methodology",
        ),
        _reprove_digest(
            daily_return_series_evidence,
            paper_daily_return_series_evidence_digest,
            daily_return_series_evidence.series_digest,
            expected_daily_return_series_digest,
            "daily_return_series",
        ),
        _reprove_digest(
            thirty_day_gate_decision,
            paper_30day_evidence_gate_decision_digest,
            thirty_day_gate_decision.decision_digest,
            expected_thirty_day_gate_decision_digest,
            "thirty_day_gate_decision",
        ),
    ):
        if reason is not None:
            hard.append(reason)

    # 2) Per-artifact safety / non-overclaim re-check (do not trust bytes after digest re-proof alone).
    if not _metrics_summary_safe(metrics_summary):
        hard.append("paper_stage4_review_package:metrics_summary_unsafe_flags")
    if not _time_window_safe(time_window_evidence):
        hard.append("paper_stage4_review_package:time_window_unsafe_flags")
    if not _comparator_bridge_safe(comparator_bridge_evidence):
        hard.append("paper_stage4_review_package:comparator_bridge_unsafe_flags")
    if not _methodology_safe(return_series_methodology):
        hard.append("paper_stage4_review_package:return_series_methodology_unsafe_flags")
    if not _daily_return_series_safe(daily_return_series_evidence):
        hard.append("paper_stage4_review_package:daily_return_series_unsafe_flags")
    if not _thirty_day_gate_safe(thirty_day_gate_decision):
        hard.append("paper_stage4_review_package:thirty_day_gate_unsafe_flags")

    # 3) Same-chain cross-binding: each downstream artifact must carry the upstream self-digests (one chain).
    summary_digest = _str_or_empty(metrics_summary.summary_digest)
    window_digest = _str_or_empty(time_window_evidence.time_window_digest)
    methodology_digest = _str_or_empty(return_series_methodology.methodology_digest)
    series_digest = _str_or_empty(daily_return_series_evidence.series_digest)
    if _str_or_empty(time_window_evidence.metrics_summary_digest) != summary_digest:
        hard.append("paper_stage4_review_package:time_window_summary_chain_mismatch")
    if _str_or_empty(comparator_bridge_evidence.time_window_digest) != window_digest:
        hard.append("paper_stage4_review_package:comparator_bridge_window_chain_mismatch")
    if _str_or_empty(comparator_bridge_evidence.metrics_summary_digest) != summary_digest:
        hard.append("paper_stage4_review_package:comparator_bridge_summary_chain_mismatch")
    if _str_or_empty(daily_return_series_evidence.methodology_digest) != methodology_digest:
        hard.append("paper_stage4_review_package:daily_series_methodology_chain_mismatch")
    if _str_or_empty(daily_return_series_evidence.time_window_digest) != window_digest:
        hard.append("paper_stage4_review_package:daily_series_window_chain_mismatch")
    if _str_or_empty(daily_return_series_evidence.metrics_summary_digest) != summary_digest:
        hard.append("paper_stage4_review_package:daily_series_summary_chain_mismatch")
    if _str_or_empty(thirty_day_gate_decision.series_digest) != series_digest:
        hard.append("paper_stage4_review_package:gate_series_chain_mismatch")
    if _str_or_empty(thirty_day_gate_decision.methodology_digest) != methodology_digest:
        hard.append("paper_stage4_review_package:gate_methodology_chain_mismatch")
    if _str_or_empty(thirty_day_gate_decision.time_window_digest) != window_digest:
        hard.append("paper_stage4_review_package:gate_window_chain_mismatch")
    if _str_or_empty(thirty_day_gate_decision.metrics_summary_digest) != summary_digest:
        hard.append("paper_stage4_review_package:gate_summary_chain_mismatch")

    # 4) Shared correlation + market symbol across the chain (methodology carries no market symbol).
    if not (
        _str_or_empty(metrics_summary.correlation_id)
        == _str_or_empty(time_window_evidence.correlation_id)
        == _str_or_empty(comparator_bridge_evidence.correlation_id)
        == _str_or_empty(return_series_methodology.correlation_id)
        == _str_or_empty(daily_return_series_evidence.correlation_id)
        == _str_or_empty(thirty_day_gate_decision.correlation_id)
        == correlation_id
    ):
        hard.append("paper_stage4_review_package:correlation_id_mismatch")
    market_symbol = _str_or_empty(metrics_summary.market_symbol)
    if market_symbol == "" or not (
        market_symbol
        == _str_or_empty(time_window_evidence.market_symbol)
        == _str_or_empty(comparator_bridge_evidence.market_symbol)
        == _str_or_empty(daily_return_series_evidence.market_symbol)
        == _str_or_empty(thirty_day_gate_decision.market_symbol)
    ):
        hard.append("paper_stage4_review_package:market_symbol_mismatch")

    # 5) Terminal §10.4 gate requirement: the >=30-day evidence gate must be SATISFIED.
    if thirty_day_gate_decision.thirty_day_gate_satisfied is not True:
        hard.append("paper_stage4_review_package:thirty_day_gate_not_satisfied")

    if hard:
        status = PaperStage4ReviewPackageStatus.REJECTED
        ready = False
        consumed = False
        reason_codes = tuple(sorted(set(hard)))
        review_findings: tuple[str, ...] = ()
    else:
        status = PaperStage4ReviewPackageStatus.READY
        ready = True
        consumed = True
        reason_codes = ()
        review_findings = _READY_FINDINGS

    return _finalize_package(
        status=status,
        ready=ready,
        consumed=consumed,
        review_package_id=review_package_id,
        paper_id=paper_id,
        correlation_id=correlation_id,
        market_symbol=market_symbol,
        metrics_summary=metrics_summary,
        time_window_evidence=time_window_evidence,
        comparator_bridge_evidence=comparator_bridge_evidence,
        return_series_methodology=return_series_methodology,
        daily_return_series_evidence=daily_return_series_evidence,
        thirty_day_gate_decision=thirty_day_gate_decision,
        expected_metrics_summary_digest=expected_metrics_summary_digest,
        expected_time_window_digest=expected_time_window_digest,
        expected_comparator_bridge_digest=expected_comparator_bridge_digest,
        expected_return_series_methodology_digest=expected_return_series_methodology_digest,
        expected_daily_return_series_digest=expected_daily_return_series_digest,
        expected_thirty_day_gate_decision_digest=expected_thirty_day_gate_decision_digest,
        review_findings=review_findings,
        reason_codes=reason_codes,
        metadata=metadata_pairs,
    )


def _finalize_package(
    *,
    status: PaperStage4ReviewPackageStatus,
    ready: bool,
    consumed: bool,
    review_package_id: str,
    paper_id: str,
    correlation_id: str,
    market_symbol: str,
    metrics_summary: PaperSessionMetricsSummary,
    time_window_evidence: PaperDeterministicTimeWindowEvidence,
    comparator_bridge_evidence: PaperVsBacktestComparatorBridgeEvidence,
    return_series_methodology: PaperReturnSeriesMethodology,
    daily_return_series_evidence: PaperDailyReturnSeriesEvidence,
    thirty_day_gate_decision: PaperThirtyDayEvidenceGateDecision,
    expected_metrics_summary_digest: str,
    expected_time_window_digest: str,
    expected_comparator_bridge_digest: str,
    expected_return_series_methodology_digest: str,
    expected_daily_return_series_digest: str,
    expected_thirty_day_gate_decision_digest: str,
    review_findings: tuple[str, ...],
    reason_codes: tuple[str, ...],
    metadata: tuple[tuple[str, str], ...],
) -> PaperStage4ReviewPackage:
    fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "package_version": _PACKAGE_VERSION,
        "status": status,
        "ready": ready,
        "review_package_id": review_package_id,
        "paper_id": paper_id,
        "correlation_id": correlation_id,
        "market_symbol": market_symbol,
        "expected_metrics_summary_digest": expected_metrics_summary_digest,
        "metrics_summary_digest": _str_or_empty(metrics_summary.summary_digest),
        "expected_time_window_digest": expected_time_window_digest,
        "time_window_digest": _str_or_empty(time_window_evidence.time_window_digest),
        "expected_comparator_bridge_digest": expected_comparator_bridge_digest,
        "comparator_bridge_digest": _str_or_empty(comparator_bridge_evidence.bridge_digest),
        "expected_return_series_methodology_digest": expected_return_series_methodology_digest,
        "return_series_methodology_digest": _str_or_empty(return_series_methodology.methodology_digest),
        "expected_daily_return_series_digest": expected_daily_return_series_digest,
        "daily_return_series_digest": _str_or_empty(daily_return_series_evidence.series_digest),
        "expected_thirty_day_gate_decision_digest": expected_thirty_day_gate_decision_digest,
        "thirty_day_gate_decision_digest": _str_or_empty(thirty_day_gate_decision.decision_digest),
        "metrics_summary_status": _status_value(metrics_summary.status),
        "time_window_status": _status_value(time_window_evidence.status),
        "comparator_bridge_status": _status_value(comparator_bridge_evidence.status),
        "return_series_methodology_status": _status_value(return_series_methodology.status),
        "daily_return_series_status": _status_value(daily_return_series_evidence.status),
        "thirty_day_gate_decision_status": _status_value(thirty_day_gate_decision.status),
        "thirty_day_gate_satisfied": _bool_or_false(thirty_day_gate_decision.thirty_day_gate_satisfied),
        "thirty_day_gate_minimum_bucket_count": _int_or_zero(
            thirty_day_gate_decision.gate_minimum_consecutive_bucket_count
        ),
        "thirty_day_gate_bucket_count": _int_or_zero(thirty_day_gate_decision.bucket_count),
        "thirty_day_gate_daily_return_count": _int_or_zero(thirty_day_gate_decision.daily_return_count),
        "thirty_day_gate_used_bucket_count": _int_or_zero(thirty_day_gate_decision.gate_bucket_count_used),
        "thirty_day_gate_used_first_bucket_id": _str_or_empty(thirty_day_gate_decision.gate_used_first_bucket_id),
        "thirty_day_gate_used_last_bucket_id": _str_or_empty(thirty_day_gate_decision.gate_used_last_bucket_id),
        "thirty_day_gate_used_first_bucket_start_ns": _int_or_zero(
            thirty_day_gate_decision.gate_used_first_bucket_start_ns
        ),
        "thirty_day_gate_used_last_bucket_end_ns": _int_or_zero(thirty_day_gate_decision.gate_used_last_bucket_end_ns),
        "comparator_comparison_ready": _bool_or_false(comparator_bridge_evidence.comparison_ready),
        "comparator_stage4_comparator_invoked": _bool_or_false(comparator_bridge_evidence.stage4_comparator_invoked),
        "comparator_missing_inputs": _str_tuple(comparator_bridge_evidence.missing_comparator_inputs),
        "daily_return_series_bucket_count": _int_or_zero(daily_return_series_evidence.bucket_count),
        "daily_return_series_return_count": _int_or_zero(daily_return_series_evidence.return_count),
        "metrics_summary_consumed": consumed,
        "time_window_evidence_consumed": consumed,
        "comparator_bridge_consumed": consumed,
        "return_series_methodology_consumed": consumed,
        "daily_return_series_evidence_consumed": consumed,
        "thirty_day_gate_consumed": consumed,
        "evidence_chain_consumed": consumed,
        "review_findings": review_findings,
        "reason_codes": reason_codes,
        "metadata": metadata,
    }
    seed = PaperStage4ReviewPackage(review_package_digest="", **fields)  # type: ignore[arg-type]
    return _replace_package_digest(seed, paper_stage4_review_package_digest(seed))


def _status_value(status: object) -> str:
    return status.value if isinstance(status, Enum) and type(status.value) is str else ""


def _replace_package_digest(package: PaperStage4ReviewPackage, digest: str) -> PaperStage4ReviewPackage:
    fields = _package_fields(package)
    fields["review_package_digest"] = digest
    return PaperStage4ReviewPackage(**fields)  # type: ignore[arg-type]


def _package_fields(package: PaperStage4ReviewPackage) -> dict[str, object]:
    return {
        "schema_version": package.schema_version,
        "package_version": package.package_version,
        "status": package.status,
        "ready": package.ready,
        "review_package_id": package.review_package_id,
        "paper_id": package.paper_id,
        "correlation_id": package.correlation_id,
        "market_symbol": package.market_symbol,
        "expected_metrics_summary_digest": package.expected_metrics_summary_digest,
        "metrics_summary_digest": package.metrics_summary_digest,
        "expected_time_window_digest": package.expected_time_window_digest,
        "time_window_digest": package.time_window_digest,
        "expected_comparator_bridge_digest": package.expected_comparator_bridge_digest,
        "comparator_bridge_digest": package.comparator_bridge_digest,
        "expected_return_series_methodology_digest": package.expected_return_series_methodology_digest,
        "return_series_methodology_digest": package.return_series_methodology_digest,
        "expected_daily_return_series_digest": package.expected_daily_return_series_digest,
        "daily_return_series_digest": package.daily_return_series_digest,
        "expected_thirty_day_gate_decision_digest": package.expected_thirty_day_gate_decision_digest,
        "thirty_day_gate_decision_digest": package.thirty_day_gate_decision_digest,
        "metrics_summary_status": package.metrics_summary_status,
        "time_window_status": package.time_window_status,
        "comparator_bridge_status": package.comparator_bridge_status,
        "return_series_methodology_status": package.return_series_methodology_status,
        "daily_return_series_status": package.daily_return_series_status,
        "thirty_day_gate_decision_status": package.thirty_day_gate_decision_status,
        "thirty_day_gate_satisfied": package.thirty_day_gate_satisfied,
        "thirty_day_gate_minimum_bucket_count": package.thirty_day_gate_minimum_bucket_count,
        "thirty_day_gate_bucket_count": package.thirty_day_gate_bucket_count,
        "thirty_day_gate_daily_return_count": package.thirty_day_gate_daily_return_count,
        "thirty_day_gate_used_bucket_count": package.thirty_day_gate_used_bucket_count,
        "thirty_day_gate_used_first_bucket_id": package.thirty_day_gate_used_first_bucket_id,
        "thirty_day_gate_used_last_bucket_id": package.thirty_day_gate_used_last_bucket_id,
        "thirty_day_gate_used_first_bucket_start_ns": package.thirty_day_gate_used_first_bucket_start_ns,
        "thirty_day_gate_used_last_bucket_end_ns": package.thirty_day_gate_used_last_bucket_end_ns,
        "comparator_comparison_ready": package.comparator_comparison_ready,
        "comparator_stage4_comparator_invoked": package.comparator_stage4_comparator_invoked,
        "comparator_missing_inputs": package.comparator_missing_inputs,
        "daily_return_series_bucket_count": package.daily_return_series_bucket_count,
        "daily_return_series_return_count": package.daily_return_series_return_count,
        "metrics_summary_consumed": package.metrics_summary_consumed,
        "time_window_evidence_consumed": package.time_window_evidence_consumed,
        "comparator_bridge_consumed": package.comparator_bridge_consumed,
        "return_series_methodology_consumed": package.return_series_methodology_consumed,
        "daily_return_series_evidence_consumed": package.daily_return_series_evidence_consumed,
        "thirty_day_gate_consumed": package.thirty_day_gate_consumed,
        "evidence_chain_consumed": package.evidence_chain_consumed,
        "review_findings": package.review_findings,
        "reason_codes": package.reason_codes,
        "metadata": package.metadata,
    }


def _package_payload_from(package: PaperStage4ReviewPackage) -> dict[str, object]:
    payload = dict(_package_fields(package))
    payload["status"] = package.status.value
    payload["comparator_missing_inputs"] = list(package.comparator_missing_inputs)
    payload["review_findings"] = list(package.review_findings)
    payload["reason_codes"] = list(package.reason_codes)
    payload["metadata"] = _serialize_metadata(package.metadata)
    payload.update(
        {
            "paper_only": package.paper_only,
            "stage4_review_package": package.stage4_review_package,
            "review_only": package.review_only,
            "operator_review_required": package.operator_review_required,
            "paper_stage4_readiness_decision_consumed": package.paper_stage4_readiness_decision_consumed,
            "operator_review_complete": package.operator_review_complete,
            "approval_granted": package.approval_granted,
            "comparison_ready": package.comparison_ready,
            "stage4_comparator_invoked": package.stage4_comparator_invoked,
            "prdv4_stage4_complete": package.prdv4_stage4_complete,
            "live_ready": package.live_ready,
            "shadow_ready": package.shadow_ready,
            "operational_readiness": package.operational_readiness,
            "deribit_ready": package.deribit_ready,
            "profitability_proven": package.profitability_proven,
            "edge_proven": package.edge_proven,
            "production_execution": package.production_execution,
            "real_orders_enabled": package.real_orders_enabled,
            "real_money_enabled": package.real_money_enabled,
            "real_capital_reserved": package.real_capital_reserved,
            "live_api_called": package.live_api_called,
            "scheduler_enabled": package.scheduler_enabled,
            "auto_loop_enabled": package.auto_loop_enabled,
            "connector_invoked": package.connector_invoked,
            "real_wall_clock_used": package.real_wall_clock_used,
            "real_account_equity_used": package.real_account_equity_used,
            "real_capital_used": package.real_capital_used,
            "sharpe_computed": package.sharpe_computed,
            "paper_sharpe_computed": package.paper_sharpe_computed,
            "annualized_sharpe_computed": package.annualized_sharpe_computed,
            "return_series_constructed": package.return_series_constructed,
        }
    )
    return payload


def paper_stage4_review_package_to_dict(package: PaperStage4ReviewPackage) -> dict[str, object]:
    """Canonical, JSON-ready, operator-readable mapping for the review package (includes its self-digest)."""
    payload = _package_payload_from(package)
    payload["review_package_digest"] = package.review_package_digest
    return payload


def paper_stage4_review_package_digest(package: PaperStage4ReviewPackage) -> str:
    """Recompute the canonical review-package digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_package_payload_from(package))


__all__ = [
    "PaperStage4ReviewPackage",
    "PaperStage4ReviewPackageError",
    "PaperStage4ReviewPackageStatus",
    "build_paper_stage4_review_package",
    "paper_stage4_review_package_digest",
    "paper_stage4_review_package_to_dict",
]
