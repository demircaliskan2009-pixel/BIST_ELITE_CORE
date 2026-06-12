"""Paper replay result report — deterministic paper-only record of an offline replay outcome.

A small, deterministic, fail-closed contract that records *caller-supplied* offline paper replay outcome
evidence (a replay-trace digest, a metrics digest, a decision-trace digest, and an outcome status) for a
READY ``PaperReplayRunPlan``, re-proving the run-plan digest at the boundary. It is *only* a report
contract: it does not calculate PnL, run a replay, load events, simulate fills, open files, query venues,
schedule, or create storage — no DB/file/network IO, no persistence/repository adapter, no engine/runtime.

Design rules:
  - Boundary digest re-proof: the run-plan digest is recomputed via the public
    ``paper_replay_run_plan_to_dict`` serializer (excluding ``run_plan_digest``) and a mismatch is
    rejected before READY — a stale/forged/tampered run plan cannot report.
  - Record, don't compute: the outcome status and the three result digests are supplied by the caller;
    the report validates their shape, the run-plan paper-safety flags, and the chain digests, then
    propagates terminal status. No metric/PnL/fill is computed and no upstream validation is redone.
  - Fail closed: a wrong-typed run plan, empty correlation id, or malformed metadata raises; a hard
    run-plan rejection, a run-plan-digest mismatch, a malformed/unknown outcome status, a malformed chain/
    result digest, an unsafe run-plan flag, or a BIST/live/private/order/scheduler token in an identity/
    metadata value yields REJECTED; needs-research and insufficient-evidence propagate.
  - Deterministic: a canonical SHA-256 ``result_report_digest``; no wall-clock/random/IO. Frozen
    dataclass; ``paper_only=True`` and no order/route/venue/scheduler/runtime/persistence/store/engine field.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.validation.paper_replay_run_plan import (
    PaperReplayRunPlan,
    PaperReplayRunPlanStatus,
    paper_replay_run_plan_to_dict,
)

_SCHEMA_VERSION = "paper-replay-result-report.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")
_ALLOWED_REPLAY_MODES = frozenset({"offline_paper_replay", "deterministic_replay_dry_run"})

# Safely-detectable BIST markers and forbidden live/order/scheduler/private config tokens (word-bounded).
# A bare ``order``/``orders`` token is rejected while ``border``/``orderly``/``preorder`` are spared.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|auto_loop|shadow_live_execution|credentials|scheduler)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)


class PaperReplayResultReportError(RuntimeError):
    """Raised when report inputs are malformed at the call level (wrong type / bad id / bad metadata)."""


class PaperReplayResultReportStatus(str, Enum):
    """Terminal readiness of a paper replay result report. Never an order/live action."""

    READY = "READY"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PaperReplayOutcomeStatus(str, Enum):
    """Caller-supplied outcome of the offline paper replay run. Never an order/live action."""

    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    NEEDS_RESEARCH = "NEEDS_RESEARCH"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True)
class PaperReplayResultReport:
    """Deterministic, immutable record of an offline paper replay outcome over a run plan. PAPER ONLY."""

    schema_version: str
    status: PaperReplayResultReportStatus
    ready: bool
    result_report_id: str
    outcome_status: str
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
    run_plan_status: str
    replay_source_id: str
    historical_data_source_id: str
    replay_trace_digest: str
    metrics_digest: str
    decision_trace_digest: str
    metadata: tuple[tuple[str, str], ...]
    rejection_reasons: tuple[str, ...]
    needs_research_reasons: tuple[str, ...]
    correlation_id: str
    result_report_digest: str
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


def _safe_digest_value(value: object) -> str:
    return value if isinstance(value, str) else ""


def _safe_optional_digest_value(value: object) -> str | None:
    return value if isinstance(value, str) or value is None else None


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _scope_violations(*texts: str) -> tuple[str, ...]:
    reasons: list[str] = []
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            reasons.append("paper_replay_result_report:bist_scope_leakage")
        if _FORBIDDEN_PATTERN.search(text):
            reasons.append("paper_replay_result_report:forbidden_scope_token")
    return tuple(reasons)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperReplayResultReportError("paper_replay_result_report:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperReplayResultReportError("paper_replay_result_report:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _coerce_outcome(value: object) -> PaperReplayOutcomeStatus | None:
    if isinstance(value, PaperReplayOutcomeStatus):
        return value
    if isinstance(value, str):
        try:
            return PaperReplayOutcomeStatus(value)
        except ValueError:
            return None
    return None


def _expected_run_plan_digest(run_plan: PaperReplayRunPlan) -> str | None:
    try:
        payload = paper_replay_run_plan_to_dict(run_plan)
        payload.pop("run_plan_digest", None)
        return _canonical_digest(payload)
    except Exception:
        return None


def build_paper_replay_result_report(
    run_plan: PaperReplayRunPlan,
    *,
    result_report_id: str,
    outcome_status: PaperReplayOutcomeStatus | str,
    replay_trace_digest: str,
    metrics_digest: str,
    decision_trace_digest: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperReplayResultReport:
    """Record a caller-supplied offline paper replay outcome over a READY ``PaperReplayRunPlan``.

    ``run_plan`` must be a ``PaperReplayRunPlan``; a wrong-typed run plan, an empty ``correlation_id``, or
    non ``Mapping[str, str]`` metadata raises ``PaperReplayResultReportError``. The report is READY only
    when the run plan is READY + ready and paper-safe, its ``run_plan_digest`` re-proves via the public
    serializer, the chain and result digests are canonical 64-hex, the ids are non-empty, no forbidden/BIST
    token appears, and ``outcome_status`` is COMPLETED; every other outcome maps fail-closed to REJECTED /
    INSUFFICIENT_EVIDENCE / NEEDS_RESEARCH. Deterministic and immutable; records evidence, computes nothing.
    """
    if not isinstance(run_plan, PaperReplayRunPlan):
        raise PaperReplayResultReportError("paper_replay_result_report:run_plan_malformed")
    if not _is_non_empty_string(correlation_id):
        raise PaperReplayResultReportError("paper_replay_result_report:correlation_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)

    outcome = _coerce_outcome(outcome_status)
    outcome_value = (
        outcome.value if outcome is not None else (outcome_status if isinstance(outcome_status, str) else "")
    )

    hard: list[str] = []
    needs: list[str] = []
    insufficient: list[str] = []

    if not _is_non_empty_string(result_report_id):
        hard.append("paper_replay_result_report:result_report_id_invalid")
    if outcome is None:
        hard.append("paper_replay_result_report:outcome_status_unknown")
    if not _is_non_empty_string(run_plan.run_plan_id):
        hard.append("paper_replay_result_report:run_plan_id_invalid")
    if not _is_non_empty_string(run_plan.replay_mode):
        hard.append("paper_replay_result_report:run_plan_replay_mode_invalid")
    elif run_plan.replay_mode not in _ALLOWED_REPLAY_MODES:
        hard.append("paper_replay_result_report:run_plan_replay_mode_unknown")
    if not _is_non_empty_string(run_plan.requested_replay_id):
        hard.append("paper_replay_result_report:requested_replay_id_invalid")
    if not _is_non_empty_string(run_plan.operator_id):
        hard.append("paper_replay_result_report:operator_id_invalid")
    if not _is_non_empty_string(run_plan.replay_source_id):
        hard.append("paper_replay_result_report:replay_source_id_invalid")
    if not _is_non_empty_string(run_plan.historical_data_source_id):
        hard.append("paper_replay_result_report:historical_data_source_id_invalid")

    hard.extend(
        _scope_violations(
            result_report_id,
            correlation_id,
            run_plan.run_plan_id,
            run_plan.requested_replay_id,
            run_plan.operator_id,
            run_plan.replay_source_id,
            run_plan.historical_data_source_id,
            *(value for _, value in metadata_pairs),
        )
    )

    for name, digest in (
        ("bundle_digest", run_plan.bundle_digest),
        ("admission_digest", run_plan.admission_digest),
        ("bridge_digest", run_plan.bridge_digest),
        ("manifest_digest", run_plan.manifest_digest),
        ("intake_digest", run_plan.intake_digest),
        ("run_plan_digest", run_plan.run_plan_digest),
        ("replay_trace_digest", replay_trace_digest),
        ("metrics_digest", metrics_digest),
        ("decision_trace_digest", decision_trace_digest),
    ):
        if not _is_sha256_hex(digest):
            hard.append(f"paper_replay_result_report:{name}_invalid")

    if not run_plan.paper_only:
        hard.append("paper_replay_result_report:run_plan_non_paper")
    if run_plan.real_orders_enabled:
        hard.append("paper_replay_result_report:run_plan_real_orders_enabled")
    if run_plan.real_money_enabled:
        hard.append("paper_replay_result_report:run_plan_real_money_enabled")

    # Boundary digest re-proof: a stale/forged run plan must not report.
    if _is_sha256_hex(run_plan.run_plan_digest) and run_plan.run_plan_digest != _expected_run_plan_digest(run_plan):
        hard.append("paper_replay_result_report:run_plan_digest_mismatch")

    if run_plan.status is PaperReplayRunPlanStatus.REJECTED:
        hard.append("paper_replay_result_report:run_plan_rejected")
        hard.extend(run_plan.rejection_reasons)
    elif run_plan.status is PaperReplayRunPlanStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_result_report:run_plan_needs_research")
        needs.extend(run_plan.needs_research_reasons)
    elif run_plan.status is PaperReplayRunPlanStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_result_report:run_plan_insufficient_evidence")
    elif run_plan.status is PaperReplayRunPlanStatus.READY and not run_plan.ready:
        hard.append("paper_replay_result_report:run_plan_ready_mismatch")

    if outcome is PaperReplayOutcomeStatus.REJECTED:
        hard.append("paper_replay_result_report:outcome_rejected")
    elif outcome is PaperReplayOutcomeStatus.NEEDS_RESEARCH:
        needs.append("paper_replay_result_report:outcome_needs_research")
    elif outcome is PaperReplayOutcomeStatus.INSUFFICIENT_EVIDENCE:
        insufficient.append("paper_replay_result_report:outcome_insufficient_evidence")

    rejection_reasons = _sorted_unique(tuple(hard))
    needs_research_reasons = _sorted_unique(tuple(needs))
    insufficient_reasons = _sorted_unique(tuple(insufficient))

    if rejection_reasons:
        status = PaperReplayResultReportStatus.REJECTED
    elif insufficient_reasons:
        status = PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE
    elif needs_research_reasons:
        status = PaperReplayResultReportStatus.NEEDS_RESEARCH
    elif (
        run_plan.status is PaperReplayRunPlanStatus.READY
        and run_plan.ready
        and outcome is PaperReplayOutcomeStatus.COMPLETED
    ):
        status = PaperReplayResultReportStatus.READY
    else:
        status = PaperReplayResultReportStatus.INSUFFICIENT_EVIDENCE

    combined_rejections = rejection_reasons if rejection_reasons else insufficient_reasons
    return _assemble(
        status=status,
        run_plan=run_plan,
        result_report_id=result_report_id,
        outcome_value=outcome_value,
        replay_trace_digest=replay_trace_digest,
        metrics_digest=metrics_digest,
        decision_trace_digest=decision_trace_digest,
        metadata=metadata_pairs,
        rejection_reasons=combined_rejections,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
    )


def _assemble(
    *,
    status: PaperReplayResultReportStatus,
    run_plan: PaperReplayRunPlan,
    result_report_id: str,
    outcome_value: str,
    replay_trace_digest: str,
    metrics_digest: str,
    decision_trace_digest: str,
    metadata: tuple[tuple[str, str], ...],
    rejection_reasons: tuple[str, ...],
    needs_research_reasons: tuple[str, ...],
    correlation_id: str,
) -> PaperReplayResultReport:
    ready = status is PaperReplayResultReportStatus.READY
    strategy_digest = _safe_optional_digest_value(run_plan.strategy_digest)
    bundle_digest = _safe_digest_value(run_plan.bundle_digest)
    admission_digest = _safe_digest_value(run_plan.admission_digest)
    bridge_digest = _safe_digest_value(run_plan.bridge_digest)
    manifest_digest = _safe_digest_value(run_plan.manifest_digest)
    intake_digest = _safe_digest_value(run_plan.intake_digest)
    run_plan_digest = _safe_digest_value(run_plan.run_plan_digest)
    replay_trace_digest = _safe_digest_value(replay_trace_digest)
    metrics_digest = _safe_digest_value(metrics_digest)
    decision_trace_digest = _safe_digest_value(decision_trace_digest)
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "status": status.value,
        "ready": ready,
        "result_report_id": result_report_id,
        "outcome_status": outcome_value,
        "run_plan_id": run_plan.run_plan_id,
        "replay_mode": run_plan.replay_mode,
        "requested_replay_id": run_plan.requested_replay_id,
        "operator_id": run_plan.operator_id,
        "strategy_id": run_plan.strategy_id,
        "strategy_digest": strategy_digest,
        "bundle_digest": bundle_digest,
        "admission_digest": admission_digest,
        "bridge_digest": bridge_digest,
        "manifest_digest": manifest_digest,
        "intake_digest": intake_digest,
        "run_plan_digest": run_plan_digest,
        "run_plan_status": run_plan.status.value,
        "replay_source_id": run_plan.replay_source_id,
        "historical_data_source_id": run_plan.historical_data_source_id,
        "replay_trace_digest": replay_trace_digest,
        "metrics_digest": metrics_digest,
        "decision_trace_digest": decision_trace_digest,
        "metadata": [list(pair) for pair in metadata],
        "rejection_reasons": list(rejection_reasons),
        "needs_research_reasons": list(needs_research_reasons),
        "correlation_id": correlation_id,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return PaperReplayResultReport(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=ready,
        result_report_id=result_report_id,
        outcome_status=outcome_value,
        run_plan_id=run_plan.run_plan_id,
        replay_mode=run_plan.replay_mode,
        requested_replay_id=run_plan.requested_replay_id,
        operator_id=run_plan.operator_id,
        strategy_id=run_plan.strategy_id,
        strategy_digest=strategy_digest,
        bundle_digest=bundle_digest,
        admission_digest=admission_digest,
        bridge_digest=bridge_digest,
        manifest_digest=manifest_digest,
        intake_digest=intake_digest,
        run_plan_digest=run_plan_digest,
        run_plan_status=run_plan.status.value,
        replay_source_id=run_plan.replay_source_id,
        historical_data_source_id=run_plan.historical_data_source_id,
        replay_trace_digest=replay_trace_digest,
        metrics_digest=metrics_digest,
        decision_trace_digest=decision_trace_digest,
        metadata=metadata,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
        correlation_id=correlation_id,
        result_report_digest=_canonical_digest(payload),
    )


def paper_replay_result_report_to_dict(report: PaperReplayResultReport) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a paper replay result report (deterministic shape)."""
    return {
        "schema_version": report.schema_version,
        "status": report.status.value,
        "ready": report.ready,
        "result_report_id": report.result_report_id,
        "outcome_status": report.outcome_status,
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
        "run_plan_status": report.run_plan_status,
        "replay_source_id": report.replay_source_id,
        "historical_data_source_id": report.historical_data_source_id,
        "replay_trace_digest": report.replay_trace_digest,
        "metrics_digest": report.metrics_digest,
        "decision_trace_digest": report.decision_trace_digest,
        "metadata": [list(pair) for pair in report.metadata],
        "rejection_reasons": list(report.rejection_reasons),
        "needs_research_reasons": list(report.needs_research_reasons),
        "correlation_id": report.correlation_id,
        "result_report_digest": report.result_report_digest,
        "paper_only": report.paper_only,
        "real_orders_enabled": report.real_orders_enabled,
        "real_money_enabled": report.real_money_enabled,
    }


__all__ = [
    "PaperReplayOutcomeStatus",
    "PaperReplayResultReport",
    "PaperReplayResultReportError",
    "PaperReplayResultReportStatus",
    "build_paper_replay_result_report",
    "paper_replay_result_report_to_dict",
]
