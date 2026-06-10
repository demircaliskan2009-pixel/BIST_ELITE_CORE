"""Paper replay promotion readiness gate over a completed paper-only result report.

A deterministic, fail-closed governance record that consumes a READY ``PaperReplayResultReport`` and
answers whether the completed offline paper replay report is eligible for a later human/governance review
step. It does not promote anything, admit a sleeve, write storage, run a replay, schedule work, load
events, route orders, or create runtime/controller wiring.

Design rules:
  - Boundary digest re-proof: the result-report digest is recomputed via the public
    ``paper_replay_result_report_to_dict`` serializer (excluding ``result_report_digest``) and a mismatch
    is rejected before READY.
  - Consume, don't re-run: terminal result-report status and outcome are propagated; this gate adds only
    governance-target whitelisting, id/source/digest-shape checks, paper-safety checks, and a canonical
    readiness digest.
  - Fail closed: malformed ids, forbidden BIST/live/private/order/scheduler tokens, unsafe paper flags,
    malformed chain/result digests, unknown targets/outcomes, or a stale/forged report reject.
  - Deterministic: no wall-clock/random/IO/network. Frozen dataclass; paper-only flags remain locked.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_result_report import (
    PaperReplayOutcomeStatus,
    PaperReplayResultReport,
    PaperReplayResultReportStatus,
    paper_replay_result_report_to_dict,
)

_SCHEMA_VERSION = "paper-replay-promotion-readiness.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
# A bare ``order``/``orders`` token is rejected while ``border``/``orderly``/``preorder`` are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperReplayPromotionReadinessError(RuntimeError):
    """Raised when promotion-readiness inputs are malformed at the call level."""


class PaperReplayPromotionReadinessStatus(str, Enum):
    """Governance readiness verdict for later paper-only human review. Never an execution action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PaperReplayPromotionTarget(str, Enum):
    """Whitelisted paper-only governance review labels. They do not trigger runtime behavior."""

    PAPER_CANDIDATE_REVIEW = "PAPER_CANDIDATE_REVIEW"
    PAPER_SLEEVE_ADMISSION_REVIEW = "PAPER_SLEEVE_ADMISSION_REVIEW"


@dataclass(frozen=True)
class PaperReplayPromotionReadiness:
    """Deterministic paper-only gate result for later governance review of a replay report."""

    schema_version: str
    status: PaperReplayPromotionReadinessStatus
    ready: bool
    readiness_id: str
    promotion_target: str
    reviewer_id: str
    result_report_id: str
    outcome_status: str
    report_status: str
    run_plan_id: str
    replay_mode: str
    requested_replay_id: str
    operator_id: str
    strategy_id: str | None
    strategy_digest: str | None
    bundle_digest: str
    admission_digest: str
    bridge_digest: str
    manifest_digest: str
    intake_digest: str
    run_plan_digest: str
    result_report_digest: str
    replay_source_id: str
    historical_data_source_id: str
    replay_trace_digest: str
    metrics_digest: str
    decision_trace_digest: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    readiness_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_sha256_hex(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _string_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_replay_promotion_readiness:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_replay_promotion_readiness:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReplayPromotionReadinessError("paper_replay_promotion_readiness:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperReplayPromotionReadinessError("paper_replay_promotion_readiness:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _coerce_report_status(value: object) -> PaperReplayResultReportStatus | None:
    if isinstance(value, PaperReplayResultReportStatus):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayResultReportStatus(value)
        except ValueError:
            return None
    return None


def _coerce_outcome(value: object) -> PaperReplayOutcomeStatus | None:
    if isinstance(value, PaperReplayOutcomeStatus):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayOutcomeStatus(value)
        except ValueError:
            return None
    return None


def _coerce_target(value: object) -> PaperReplayPromotionTarget | None:
    if isinstance(value, PaperReplayPromotionTarget):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayPromotionTarget(value)
        except ValueError:
            return None
    return None


def _expected_result_report_digest(report: PaperReplayResultReport) -> str | None:
    try:
        payload = paper_replay_result_report_to_dict(report)
    except (AttributeError, TypeError, ValueError):
        return None
    payload.pop("result_report_digest", None)
    return _canonical_digest(payload)


def build_paper_replay_promotion_readiness(
    report: PaperReplayResultReport,
    *,
    readiness_id: str,
    promotion_target: PaperReplayPromotionTarget | str,
    reviewer_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayPromotionReadiness:
    """Build a deterministic paper-only promotion-readiness record from a result report.

    READY means only that the report is eligible for later human/governance review under the whitelisted
    paper-only target label. It never admits a sleeve, promotes runtime behavior, stores evidence, loads
    events, schedules work, or routes orders.
    """
    if not isinstance(report, PaperReplayResultReport):
        raise PaperReplayPromotionReadinessError("paper_replay_promotion_readiness:report_malformed")
    metadata_pairs = _normalize_metadata(metadata)

    target = _coerce_target(promotion_target)
    target_value = target.value if target is not None else _string_value(promotion_target)
    report_status = _coerce_report_status(report.status)
    outcome = _coerce_outcome(report.outcome_status)
    report_status_value = report_status.value if report_status is not None else _string_value(report.status)
    outcome_value = outcome.value if outcome is not None else _string_value(report.outcome_status)

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(readiness_id):
        hard.append("paper_replay_promotion_readiness:readiness_id_invalid")
    if not _is_non_empty_string(reviewer_id):
        hard.append("paper_replay_promotion_readiness:reviewer_id_invalid")
    if not _is_non_empty_string(correlation_id):
        hard.append("paper_replay_promotion_readiness:correlation_id_invalid")
    if not _is_non_empty_string(target_value):
        hard.append("paper_replay_promotion_readiness:promotion_target_invalid")
    elif target is None:
        hard.append("paper_replay_promotion_readiness:promotion_target_unknown")

    if not _is_non_empty_string(report.result_report_id):
        hard.append("paper_replay_promotion_readiness:result_report_id_invalid")
    if not _is_non_empty_string(report.run_plan_id):
        hard.append("paper_replay_promotion_readiness:run_plan_id_invalid")
    if not _is_non_empty_string(report.replay_mode):
        hard.append("paper_replay_promotion_readiness:replay_mode_invalid")
    if not _is_non_empty_string(report.requested_replay_id):
        hard.append("paper_replay_promotion_readiness:requested_replay_id_invalid")
    if not _is_non_empty_string(report.operator_id):
        hard.append("paper_replay_promotion_readiness:operator_id_invalid")
    if not _is_non_empty_string(report.replay_source_id):
        hard.append("paper_replay_promotion_readiness:replay_source_id_invalid")
    if not _is_non_empty_string(report.historical_data_source_id):
        hard.append("paper_replay_promotion_readiness:historical_data_source_id_invalid")
    if report_status is None:
        hard.append("paper_replay_promotion_readiness:report_status_unknown")
    if outcome is None:
        hard.append("paper_replay_promotion_readiness:outcome_status_unknown")

    hard.extend(
        _scope_violations(
            readiness_id,
            reviewer_id,
            correlation_id,
            target_value,
            report.result_report_id,
            report.run_plan_id,
            report.replay_mode,
            report.requested_replay_id,
            report.operator_id,
            report.replay_source_id,
            report.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", report.bundle_digest),
        ("admission_digest", report.admission_digest),
        ("bridge_digest", report.bridge_digest),
        ("manifest_digest", report.manifest_digest),
        ("intake_digest", report.intake_digest),
        ("run_plan_digest", report.run_plan_digest),
        ("result_report_digest", report.result_report_digest),
        ("replay_trace_digest", report.replay_trace_digest),
        ("metrics_digest", report.metrics_digest),
        ("decision_trace_digest", report.decision_trace_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_replay_promotion_readiness:{name}_invalid")

    if report.paper_only is not True:
        hard.append("paper_replay_promotion_readiness:report_non_paper")
    if report.real_orders_enabled is not False:
        hard.append("paper_replay_promotion_readiness:report_real_orders_enabled")
    if report.real_money_enabled is not False:
        hard.append("paper_replay_promotion_readiness:report_real_money_enabled")

    expected_report_digest = (
        _expected_result_report_digest(report) if _is_sha256_hex(report.result_report_digest) else None
    )
    if _is_sha256_hex(report.result_report_digest) and report.result_report_digest != expected_report_digest:
        hard.append("paper_replay_promotion_readiness:result_report_digest_mismatch")

    if report_status is PaperReplayResultReportStatus.REJECTED:
        hard.append("paper_replay_promotion_readiness:report_rejected")
        hard.extend(report.rejection_reasons)
    elif report_status is PaperReplayResultReportStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_promotion_readiness:report_needs_research")
        needs.extend(report.needs_research_reasons)
    elif report_status is PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_promotion_readiness:report_insufficient_evidence")
    elif report_status is PaperReplayResultReportStatus.READY and report.ready is not True:
        hard.append("paper_replay_promotion_readiness:report_ready_mismatch")

    if outcome is PaperReplayOutcomeStatus.REJECTED:
        hard.append("paper_replay_promotion_readiness:outcome_rejected")
    elif outcome is PaperReplayOutcomeStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_promotion_readiness:outcome_needs_research")
    elif outcome is PaperReplayOutcomeStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_promotion_readiness:outcome_insufficient_evidence")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperReplayPromotionReadinessStatus.REJECTED
    elif insufficient_reasons:
        status = PaperReplayPromotionReadinessStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperReplayPromotionReadinessStatus.NEEDS_RESEARCH
    elif (
        report_status is PaperReplayResultReportStatus.READY
        and report.ready is True
        and outcome is PaperReplayOutcomeStatus.COMPLETED
        and target is not None
    ):
        status = PaperReplayPromotionReadinessStatus.READY
    else:
        status = PaperReplayPromotionReadinessStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        report=report,
        readiness_id=_string_value(readiness_id),
        promotion_target=target_value,
        reviewer_id=_string_value(reviewer_id),
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=_string_value(correlation_id),
        report_status_value=report_status_value,
        outcome_value=outcome_value,
    )


def _assemble(
    *,
    status: PaperReplayPromotionReadinessStatus,
    report: PaperReplayResultReport,
    readiness_id: str,
    promotion_target: str,
    reviewer_id: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
    report_status_value: str,
    outcome_value: str,
) -> PaperReplayPromotionReadiness:
    ready = status is PaperReplayPromotionReadinessStatus.READY
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "readiness_id": readiness_id,
        "promotion_target": promotion_target,
        "reviewer_id": reviewer_id,
        "result_report_id": report.result_report_id,
        "outcome_status": outcome_value,
        "report_status": report_status_value,
        "run_plan_id": report.run_plan_id,
        "replay_mode": report.replay_mode,
        "requested_replay_id": report.requested_replay_id,
        "operator_id": report.operator_id,
        "strategy_id": report.strategy_id,
        "strategy_digest": report.strategy_digest,
        "bundle_digest": report.bundle_digest,
        "admission_digest": report.admission_digest,
        "bridge_digest": report.bridge_digest,
        "manifest_digest": report.manifest_digest,
        "intake_digest": report.intake_digest,
        "run_plan_digest": report.run_plan_digest,
        "result_report_digest": report.result_report_digest,
        "replay_source_id": report.replay_source_id,
        "historical_data_source_id": report.historical_data_source_id,
        "replay_trace_digest": report.replay_trace_digest,
        "metrics_digest": report.metrics_digest,
        "decision_trace_digest": report.decision_trace_digest,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return PaperReplayPromotionReadiness(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        readiness_id=readiness_id,
        promotion_target=promotion_target,
        reviewer_id=reviewer_id,
        result_report_id=report.result_report_id,
        outcome_status=outcome_value,
        report_status=report_status_value,
        run_plan_id=report.run_plan_id,
        replay_mode=report.replay_mode,
        requested_replay_id=report.requested_replay_id,
        operator_id=report.operator_id,
        strategy_id=report.strategy_id,
        strategy_digest=report.strategy_digest,
        bundle_digest=report.bundle_digest,
        admission_digest=report.admission_digest,
        bridge_digest=report.bridge_digest,
        manifest_digest=report.manifest_digest,
        intake_digest=report.intake_digest,
        run_plan_digest=report.run_plan_digest,
        result_report_digest=report.result_report_digest,
        replay_source_id=report.replay_source_id,
        historical_data_source_id=report.historical_data_source_id,
        replay_trace_digest=report.replay_trace_digest,
        metrics_digest=report.metrics_digest,
        decision_trace_digest=report.decision_trace_digest,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        readiness_digest=_canonical_digest(payload),
    )


def paper_replay_promotion_readiness_to_dict(readiness: PaperReplayPromotionReadiness) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper replay promotion-readiness record."""
    return {
        "schema_version": readiness.schema_version,
        "status": readiness.status.value,
        "ready": readiness.ready,
        "readiness_id": readiness.readiness_id,
        "promotion_target": readiness.promotion_target,
        "reviewer_id": readiness.reviewer_id,
        "result_report_id": readiness.result_report_id,
        "outcome_status": readiness.outcome_status,
        "report_status": readiness.report_status,
        "run_plan_id": readiness.run_plan_id,
        "replay_mode": readiness.replay_mode,
        "requested_replay_id": readiness.requested_replay_id,
        "operator_id": readiness.operator_id,
        "strategy_id": readiness.strategy_id,
        "strategy_digest": readiness.strategy_digest,
        "bundle_digest": readiness.bundle_digest,
        "admission_digest": readiness.admission_digest,
        "bridge_digest": readiness.bridge_digest,
        "manifest_digest": readiness.manifest_digest,
        "intake_digest": readiness.intake_digest,
        "run_plan_digest": readiness.run_plan_digest,
        "result_report_digest": readiness.result_report_digest,
        "replay_source_id": readiness.replay_source_id,
        "historical_data_source_id": readiness.historical_data_source_id,
        "replay_trace_digest": readiness.replay_trace_digest,
        "metrics_digest": readiness.metrics_digest,
        "decision_trace_digest": readiness.decision_trace_digest,
        "metadata": [list(pair) for pair in readiness.metadata],
        "rejection_reasons": list(readiness.rejection_reasons),
        "needs_research_reasons": list(readiness.needs_research_reasons),
        "correlation_id": readiness.correlation_id,
        "readiness_digest": readiness.readiness_digest,
        "paper_only": readiness.paper_only,
        "real_orders_enabled": readiness.real_orders_enabled,
        "real_money_enabled": readiness.real_money_enabled,
    }


__all__ = [
    "PaperReplayPromotionReadiness",
    "PaperReplayPromotionReadinessError",
    "PaperReplayPromotionReadinessStatus",
    "PaperReplayPromotionTarget",
    "build_paper_replay_promotion_readiness",
    "paper_replay_promotion_readiness_to_dict",
]
