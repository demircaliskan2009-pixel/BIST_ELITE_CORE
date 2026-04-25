"""Run artifact export — Phase 8C.

Exportable, deterministic, serializable run artifacts for paper-live operations.

Provides:
  - RunArtifact: frozen composite artifact containing all run evidence.
  - build_run_artifact(): builder from current runtime state.
  - export_run_artifact(): write artifact to disk via EvidenceStore.

Artifacts include:
  - Run metadata (identity, counters).
  - Service summary (service, session, per-symbol).
  - Latest health/readiness snapshot.
  - Latest trading/operational metrics.
  - Recent audit summary.
  - Persistence health.

Design rules:
  - All artifact models are frozen dataclasses (deterministic, serializable).
  - Use only real runtime data — never fabricate.
  - Operator-friendly (JSON-serializable) and machine-friendly (typed).
  - Export via EvidenceStore for consistent bounded storage.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from crypto_core.service.evidence_store import EvidenceStore, WriteResult
from crypto_core.service.paper_shadow_session_controller import (
    FeedReplayPlan,
    FeedReplayResult,
    MarketEventBatch,
    MultiSourceRunEvidenceReport,
    PaperDataSourceBatchResult,
    PaperShadowRunEvidenceReport,
    PaperShadowSessionCorruptError,
    PaperShadowSessionSnapshot,
    feed_replay_plan_from_dict,
    feed_replay_plan_to_dict,
    feed_replay_result_from_dict,
    feed_replay_result_to_dict,
    market_event_batch_from_dict,
    market_event_batch_to_dict,
    multi_source_run_evidence_report_from_dict,
    multi_source_run_evidence_report_to_dict,
    paper_data_source_batch_result_from_dict,
    paper_data_source_batch_result_to_dict,
    paper_shadow_run_evidence_report_from_dict,
    paper_shadow_run_evidence_report_to_dict,
    paper_shadow_session_snapshot_from_dict,
    paper_shadow_session_snapshot_to_dict,
)
from crypto_core.service.sleeve_admission_controller import (
    ManagedSleeveSetManifest,
    PaperShadowActivationPlan,
    SleeveAdmissionCorruptError,
    SleeveAdmissionReleasePack,
    managed_sleeve_set_manifest_from_dict,
    managed_sleeve_set_manifest_to_dict,
    paper_shadow_activation_plan_from_dict,
    paper_shadow_activation_plan_to_dict,
    sleeve_admission_release_pack_from_dict,
    sleeve_admission_release_pack_to_dict,
)
from crypto_core.service.sleeve_portfolio import (
    SleevePortfolioCorruptError,
    SleevePortfolioSnapshot,
    sleeve_portfolio_snapshot_from_dict,
    sleeve_portfolio_snapshot_to_dict,
)

# ---------------------------------------------------------------------------
# Artifact model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunArtifact:
    """Frozen composite run artifact for paper-live operations.

    Fields:
      artifact_time_ns:      wall-clock ns when artifact was produced.
      run_id:                run identifier.
      run_metadata:          serialized RunMetadata dict.
      service_summary:       serialized ServiceRunSummary dict.
      session_summary:       serialized SessionSummary dict.
      symbol_summaries:      tuple of serialized SymbolSummary dicts.
      health_trend:          serialized HealthTrendSnapshot dict.
      readiness:             serialized ReadinessSnapshot dict.
      operational_metrics:   serialized OperationalMetrics dict.
      trading_metrics:       serialized TradingMetrics dict.
      audit_summary:         serialized audit summary dict.
      persistence_health:    serialized PersistenceHealthSnapshot dict.
    """

    artifact_time_ns: int
    run_id: str
    run_metadata: dict
    service_summary: dict
    session_summary: dict
    symbol_summaries: tuple[dict, ...] = field(default_factory=tuple)
    health_trend: dict = field(default_factory=dict)
    readiness: dict = field(default_factory=dict)
    operational_metrics: dict = field(default_factory=dict)
    trading_metrics: dict = field(default_factory=dict)
    audit_summary: dict = field(default_factory=dict)
    persistence_health: dict = field(default_factory=dict)


@dataclass(frozen=True)
class OperatorDecisionPack:
    """Frozen operator-facing promotion/readiness decision artifact."""

    artifact_time_ns: int
    review_id: str
    review_timestamp_ns: int
    review_status: str
    promotion_verdict: str
    operator_disposition: str
    decision_summary: str
    readiness_level: str
    readiness_is_supportive: bool
    criteria_summary: dict = field(default_factory=dict)
    pass_criteria: tuple[str, ...] = field(default_factory=tuple)
    warning_criteria: tuple[str, ...] = field(default_factory=tuple)
    fail_criteria: tuple[str, ...] = field(default_factory=tuple)
    insufficient_evidence: tuple[str, ...] = field(default_factory=tuple)
    insufficient_evidence_summary: dict = field(default_factory=dict)
    readiness_criteria: tuple[dict, ...] = field(default_factory=tuple)
    readiness_blockers: tuple[str, ...] = field(default_factory=tuple)
    external_regime_quality: str = "unavailable"
    external_regime_evidence_available: bool = False
    external_regime_evidence_sufficient: bool = False
    external_regime_concerns: tuple[str, ...] = field(default_factory=tuple)
    external_regime_governance: dict = field(default_factory=dict)
    external_regime_summary: str = ""
    campaign_coverage: dict = field(default_factory=dict)
    reason_codes: dict = field(default_factory=dict)
    why_not_promotable: tuple[str, ...] = field(default_factory=tuple)
    operator_next_inspection: tuple[str, ...] = field(default_factory=tuple)
    campaign_ids: tuple[str, ...] = field(default_factory=tuple)


class EscalationStage(str, Enum):
    """Deterministic crypto paper-live escalation gate outcomes."""

    PAPER_ONLY = "paper_only"
    CALIBRATED_PAPER = "calibrated_paper"
    SHADOW_LIVE_REVIEW_ELIGIBLE = "shadow_live_review_eligible"
    TINY_CAP_LIVE_REVIEW_ELIGIBLE = "tiny_cap_live_review_eligible"
    HOLD = "hold"
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class EscalationDecision:
    """Frozen operator-facing crypto live-readiness escalation artifact."""

    artifact_time_ns: int
    review_id: str
    review_timestamp_ns: int
    review_status: str
    promotion_verdict: str
    operator_disposition: str
    escalation_stage: EscalationStage
    decision_summary: str
    readiness_level: str
    readiness_is_supportive: bool
    external_regime_quality: str = "unavailable"
    blocking_reasons: tuple[str, ...] = field(default_factory=tuple)
    missing_evidence: tuple[str, ...] = field(default_factory=tuple)
    why_not_higher: tuple[str, ...] = field(default_factory=tuple)
    revalidation_required: tuple[str, ...] = field(default_factory=tuple)
    campaign_ids: tuple[str, ...] = field(default_factory=tuple)
    reason_codes: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _dataclass_to_dict(obj: object) -> dict:
    """Convert a frozen dataclass to a plain dict, handling nested enums."""
    from dataclasses import fields

    if not hasattr(obj, "__dataclass_fields__"):
        return {}
    result: dict = {}
    for f in fields(obj):  # type: ignore[arg-type]
        val = getattr(obj, f.name)
        if hasattr(val, "value"):
            # Enum-like: use .value
            result[f.name] = val.value
        elif isinstance(val, tuple):
            result[f.name] = [_dataclass_to_dict(v) if hasattr(v, "__dataclass_fields__") else v for v in val]
        elif hasattr(val, "__dataclass_fields__"):
            result[f.name] = _dataclass_to_dict(val)
        else:
            result[f.name] = val
    return result


def operator_disposition_from_verdict(verdict: str) -> str:
    """Map a promotion verdict to a compact operator disposition."""
    return {
        "promote": "promotable",
        "hold": "hold_only",
        "reject": "reject_worthy",
        "inconclusive": "inconclusive",
    }.get(verdict, "inconclusive")


def decision_pack_to_dict(pack: OperatorDecisionPack) -> dict:
    """Serialize OperatorDecisionPack to a plain dict."""
    return _dataclass_to_dict(pack)


def decision_pack_decision_summary(pack: OperatorDecisionPack) -> dict:
    """Compact decision summary for operator/reporting surfaces."""
    return {
        "review_id": pack.review_id,
        "review_status": pack.review_status,
        "promotion_verdict": pack.promotion_verdict,
        "operator_disposition": pack.operator_disposition,
        "summary": pack.decision_summary,
        "readiness_level": pack.readiness_level,
        "readiness_is_supportive": pack.readiness_is_supportive,
        "external_regime_quality": pack.external_regime_quality,
    }


def decision_pack_missing_evidence(pack: OperatorDecisionPack) -> dict:
    """Current evidence-gap summary from the decision pack."""
    return {
        "review_id": pack.review_id,
        "insufficient_evidence": list(pack.insufficient_evidence),
        "readiness_blockers": list(pack.readiness_blockers),
        "summary": pack.insufficient_evidence_summary.get("summary", ""),
        "details": pack.insufficient_evidence_summary,
    }


def decision_pack_why_not_promotable(pack: OperatorDecisionPack) -> dict:
    """Why promotion is not yet cleanly supported, if applicable."""
    return {
        "review_id": pack.review_id,
        "promotion_verdict": pack.promotion_verdict,
        "operator_disposition": pack.operator_disposition,
        "reasons": list(pack.why_not_promotable),
    }


def decision_pack_next_inspection(pack: OperatorDecisionPack) -> dict:
    """Ordered operator inspection checklist derived from current evidence."""
    return {
        "review_id": pack.review_id,
        "items": list(pack.operator_next_inspection),
    }


class OperatorDecisionPackCorruptError(RuntimeError):
    """Raised when persisted operator decision pack data is malformed."""


def _require_str(d: dict, field_name: str) -> str:
    value = d.get(field_name)
    if not isinstance(value, str) or not value:
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be a non-empty str")
    return value


def _require_int(d: dict, field_name: str) -> int:
    value = d.get(field_name)
    if not isinstance(value, int):
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be an int")
    return value


def _require_bool(d: dict, field_name: str) -> bool:
    value = d.get(field_name)
    if not isinstance(value, bool):
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be a bool")
    return value


def _require_dict(d: dict, field_name: str) -> dict:
    value = d.get(field_name)
    if not isinstance(value, dict):
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be a dict")
    return value


def _optional_tuple_of_strings(d: dict, field_name: str) -> tuple[str, ...]:
    value = d.get(field_name, ())
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be a list/tuple of str")
    return tuple(value)


def _optional_tuple_of_dicts(d: dict, field_name: str) -> tuple[dict, ...]:
    value = d.get(field_name, ())
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, dict) for item in value):
        raise OperatorDecisionPackCorruptError(f"Decision pack field {field_name!r} must be a list/tuple of dict")
    return tuple(value)


def decision_pack_from_dict(d: dict) -> OperatorDecisionPack:
    """Deserialize OperatorDecisionPack from a plain dict."""
    if not isinstance(d, dict):
        raise OperatorDecisionPackCorruptError(f"Decision pack payload must be a dict, got {type(d).__name__!r}")

    return OperatorDecisionPack(
        artifact_time_ns=_require_int(d, "artifact_time_ns"),
        review_id=_require_str(d, "review_id"),
        review_timestamp_ns=_require_int(d, "review_timestamp_ns"),
        review_status=_require_str(d, "review_status"),
        promotion_verdict=_require_str(d, "promotion_verdict"),
        operator_disposition=_require_str(d, "operator_disposition"),
        decision_summary=_require_str(d, "decision_summary"),
        readiness_level=_require_str(d, "readiness_level"),
        readiness_is_supportive=_require_bool(d, "readiness_is_supportive"),
        criteria_summary=_require_dict(d, "criteria_summary"),
        pass_criteria=_optional_tuple_of_strings(d, "pass_criteria"),
        warning_criteria=_optional_tuple_of_strings(d, "warning_criteria"),
        fail_criteria=_optional_tuple_of_strings(d, "fail_criteria"),
        insufficient_evidence=_optional_tuple_of_strings(d, "insufficient_evidence"),
        insufficient_evidence_summary=_require_dict(d, "insufficient_evidence_summary"),
        readiness_criteria=_optional_tuple_of_dicts(d, "readiness_criteria"),
        readiness_blockers=_optional_tuple_of_strings(d, "readiness_blockers"),
        external_regime_quality=_require_str(d, "external_regime_quality"),
        external_regime_evidence_available=_require_bool(d, "external_regime_evidence_available"),
        external_regime_evidence_sufficient=_require_bool(d, "external_regime_evidence_sufficient"),
        external_regime_concerns=_optional_tuple_of_strings(d, "external_regime_concerns"),
        external_regime_governance=_require_dict(d, "external_regime_governance"),
        external_regime_summary=_require_str(d, "external_regime_summary"),
        campaign_coverage=_require_dict(d, "campaign_coverage"),
        reason_codes=_require_dict(d, "reason_codes"),
        why_not_promotable=_optional_tuple_of_strings(d, "why_not_promotable"),
        operator_next_inspection=_optional_tuple_of_strings(d, "operator_next_inspection"),
        campaign_ids=_optional_tuple_of_strings(d, "campaign_ids"),
    )


def escalation_decision_to_dict(decision: EscalationDecision) -> dict:
    """Serialize EscalationDecision to a plain dict."""
    return _dataclass_to_dict(decision)


def escalation_decision_summary(decision: EscalationDecision) -> dict:
    """Compact escalation-go/no-go summary for operator surfaces."""
    return {
        "review_id": decision.review_id,
        "review_status": decision.review_status,
        "promotion_verdict": decision.promotion_verdict,
        "operator_disposition": decision.operator_disposition,
        "allowed_next_step": decision.escalation_stage.value,
        "summary": decision.decision_summary,
        "readiness_level": decision.readiness_level,
        "readiness_is_supportive": decision.readiness_is_supportive,
        "external_regime_quality": decision.external_regime_quality,
    }


def escalation_decision_blockers(decision: EscalationDecision) -> dict:
    """Current blocking reasons for escalation beyond the current gate."""
    return {
        "review_id": decision.review_id,
        "allowed_next_step": decision.escalation_stage.value,
        "blocking_reasons": list(decision.blocking_reasons),
    }


def escalation_decision_missing_evidence(decision: EscalationDecision) -> dict:
    """Current missing-evidence surface for escalation decisions."""
    return {
        "review_id": decision.review_id,
        "allowed_next_step": decision.escalation_stage.value,
        "missing_evidence": list(decision.missing_evidence),
    }


def escalation_decision_why_not_higher(decision: EscalationDecision) -> dict:
    """Why the current governance state is not eligible for a higher gate."""
    return {
        "review_id": decision.review_id,
        "allowed_next_step": decision.escalation_stage.value,
        "reasons": list(decision.why_not_higher),
    }


def escalation_decision_revalidation(decision: EscalationDecision) -> dict:
    """What must be revalidated before the next higher gate is considered."""
    return {
        "review_id": decision.review_id,
        "allowed_next_step": decision.escalation_stage.value,
        "items": list(decision.revalidation_required),
    }


def escalation_decision_from_dict(d: dict) -> EscalationDecision:
    """Deserialize EscalationDecision from a plain dict."""
    if not isinstance(d, dict):
        raise OperatorDecisionPackCorruptError(f"Escalation decision payload must be a dict, got {type(d).__name__!r}")

    return EscalationDecision(
        artifact_time_ns=_require_int(d, "artifact_time_ns"),
        review_id=_require_str(d, "review_id"),
        review_timestamp_ns=_require_int(d, "review_timestamp_ns"),
        review_status=_require_str(d, "review_status"),
        promotion_verdict=_require_str(d, "promotion_verdict"),
        operator_disposition=_require_str(d, "operator_disposition"),
        escalation_stage=EscalationStage(_require_str(d, "escalation_stage")),
        decision_summary=_require_str(d, "decision_summary"),
        readiness_level=_require_str(d, "readiness_level"),
        readiness_is_supportive=_require_bool(d, "readiness_is_supportive"),
        external_regime_quality=_require_str(d, "external_regime_quality"),
        blocking_reasons=_optional_tuple_of_strings(d, "blocking_reasons"),
        missing_evidence=_optional_tuple_of_strings(d, "missing_evidence"),
        why_not_higher=_optional_tuple_of_strings(d, "why_not_higher"),
        revalidation_required=_optional_tuple_of_strings(d, "revalidation_required"),
        campaign_ids=_optional_tuple_of_strings(d, "campaign_ids"),
        reason_codes=_require_dict(d, "reason_codes"),
    )


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_run_artifact(
    *,
    run_id: str,
    run_metadata: object | None = None,
    service_summary: object | None = None,
    health_trend: object | None = None,
    readiness: object | None = None,
    operational_metrics: object | None = None,
    trading_metrics: object | None = None,
    audit_snapshot: object | None = None,
    persistence_health: object | None = None,
) -> RunArtifact:
    """Build a RunArtifact from typed snapshot objects.

    All arguments are optional — missing data is represented as empty dicts.
    Uses _dataclass_to_dict for serialization of frozen dataclasses.

    Args:
        run_id: current run identifier.
        run_metadata: RunMetadata instance.
        service_summary: ServiceRunSummary instance.
        health_trend: HealthTrendSnapshot instance.
        readiness: ReadinessSnapshot instance.
        operational_metrics: OperationalMetrics instance.
        trading_metrics: TradingMetrics instance.
        audit_snapshot: AuditSnapshot instance.
        persistence_health: PersistenceHealthSnapshot instance.

    Returns:
        Frozen RunArtifact.
    """
    meta_dict = _dataclass_to_dict(run_metadata) if run_metadata else {}
    svc_dict = _dataclass_to_dict(service_summary) if service_summary else {}

    # Extract session and symbol summaries from service summary.
    session_dict: dict = {}
    symbol_dicts: tuple[dict, ...] = ()
    if service_summary is not None and hasattr(service_summary, "session"):
        session_dict = _dataclass_to_dict(service_summary.session)  # type: ignore[union-attr]
    if service_summary is not None and hasattr(service_summary, "symbols"):
        symbol_dicts = tuple(
            _dataclass_to_dict(s)
            for s in service_summary.symbols  # type: ignore[union-attr]
        )

    ht_dict = _dataclass_to_dict(health_trend) if health_trend else {}
    rd_dict = _dataclass_to_dict(readiness) if readiness else {}
    om_dict = _dataclass_to_dict(operational_metrics) if operational_metrics else {}
    tm_dict = _dataclass_to_dict(trading_metrics) if trading_metrics else {}
    ph_dict = _dataclass_to_dict(persistence_health) if persistence_health else {}

    # Audit summary: extract counts rather than full record dump.
    audit_dict: dict = {}
    if audit_snapshot is not None:
        audit_dict = {
            "total_records_logged": getattr(audit_snapshot, "total_records_logged", 0),
            "total_evicted": getattr(audit_snapshot, "total_evicted", 0),
            "blocked_cycle_count": getattr(audit_snapshot, "blocked_cycle_count", 0),
            "failed_cycle_count": getattr(audit_snapshot, "failed_cycle_count", 0),
            "service_error_count": getattr(audit_snapshot, "service_error_count", 0),
            "pressure_transition_count": getattr(audit_snapshot, "pressure_transition_count", 0),
            "recent_record_count": len(getattr(audit_snapshot, "records", ())),
        }

    return RunArtifact(
        artifact_time_ns=time.time_ns(),
        run_id=run_id,
        run_metadata=meta_dict,
        service_summary=svc_dict,
        session_summary=session_dict,
        symbol_summaries=symbol_dicts,
        health_trend=ht_dict,
        readiness=rd_dict,
        operational_metrics=om_dict,
        trading_metrics=tm_dict,
        audit_summary=audit_dict,
        persistence_health=ph_dict,
    )


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

_ARTIFACT_SNAPSHOT_NAME = "run_artifact"
_DECISION_PACK_SNAPSHOT_NAME = "operator_decision_pack"
_ESCALATION_DECISION_SNAPSHOT_NAME = "live_readiness_escalation"
_SLEEVE_PORTFOLIO_SNAPSHOT_NAME = "crypto_sleeve_portfolio"
_SLEEVE_ADMISSION_RELEASE_PACK_SNAPSHOT_NAME = "crypto_sleeve_admission_release_pack"
_MANAGED_SLEEVE_SET_MANIFEST_SNAPSHOT_NAME = "crypto_managed_sleeve_set_manifest"
_PAPER_SHADOW_ACTIVATION_PLAN_SNAPSHOT_NAME = "crypto_paper_shadow_activation_plan"
_PAPER_SHADOW_SESSION_SNAPSHOT_NAME = "crypto_paper_shadow_session"
_PAPER_SHADOW_MARKET_EVENT_BATCH_SNAPSHOT_NAME = "crypto_paper_shadow_market_event_batch"
_PAPER_SHADOW_FEED_REPLAY_PLAN_SNAPSHOT_NAME = "crypto_paper_shadow_feed_replay_plan"
_PAPER_SHADOW_FEED_REPLAY_RESULT_SNAPSHOT_NAME = "crypto_paper_shadow_feed_replay_result"
_PAPER_DATA_SOURCE_BATCH_RESULT_SNAPSHOT_NAME = "crypto_paper_data_source_batch_result"
_PAPER_SHADOW_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME = "crypto_paper_shadow_run_evidence_report"
_MULTI_SOURCE_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME = "crypto_multi_source_run_evidence_report"


def export_run_artifact(
    *,
    artifact: RunArtifact,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Export a RunArtifact to disk as an atomic JSON snapshot.

    Args:
        artifact: the RunArtifact to export.
        evidence_store: EvidenceStore instance for writing.

    Returns:
        WriteResult indicating success or failure.
    """
    data = _dataclass_to_dict(artifact)
    return evidence_store.save_snapshot(_ARTIFACT_SNAPSHOT_NAME, data)


def load_run_artifact(
    *,
    evidence_store: EvidenceStore,
) -> dict:
    """Load the most recent exported run artifact from disk.

    Returns:
        The artifact data dict from the snapshot envelope.

    Raises:
        EvidenceStoreCorruptError: if snapshot missing or malformed.
    """
    envelope = evidence_store.load_snapshot(_ARTIFACT_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        from crypto_core.service.evidence_store import EvidenceStoreCorruptError

        raise EvidenceStoreCorruptError(f"Run artifact snapshot 'data' must be a dict, got {type(data).__name__!r}")
    return data


def export_operator_decision_pack(
    *,
    pack: OperatorDecisionPack,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest operator decision pack via EvidenceStore."""
    data = decision_pack_to_dict(pack)
    result = evidence_store.save_snapshot(_DECISION_PACK_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_DECISION_PACK_SNAPSHOT_NAME, data)
    return result


def load_operator_decision_pack(*, evidence_store: EvidenceStore) -> OperatorDecisionPack:
    """Load the latest persisted operator decision pack."""
    envelope = evidence_store.load_snapshot(_DECISION_PACK_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise OperatorDecisionPackCorruptError(f"Decision pack 'data' must be a dict, got {type(data).__name__!r}")
    return decision_pack_from_dict(data)


def export_escalation_decision(
    *,
    decision: EscalationDecision,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest live-readiness escalation decision."""
    data = escalation_decision_to_dict(decision)
    result = evidence_store.save_snapshot(_ESCALATION_DECISION_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_ESCALATION_DECISION_SNAPSHOT_NAME, data)
    return result


def load_escalation_decision(*, evidence_store: EvidenceStore) -> EscalationDecision:
    """Load the latest persisted live-readiness escalation decision."""
    envelope = evidence_store.load_snapshot(_ESCALATION_DECISION_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise OperatorDecisionPackCorruptError(
            f"Escalation decision 'data' must be a dict, got {type(data).__name__!r}"
        )
    return escalation_decision_from_dict(data)


def export_sleeve_portfolio_snapshot(
    *,
    snapshot: SleevePortfolioSnapshot,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest crypto sleeve portfolio snapshot."""
    data = sleeve_portfolio_snapshot_to_dict(snapshot)
    result = evidence_store.save_snapshot(_SLEEVE_PORTFOLIO_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_SLEEVE_PORTFOLIO_SNAPSHOT_NAME, data)
    return result


def load_sleeve_portfolio_snapshot(*, evidence_store: EvidenceStore) -> SleevePortfolioSnapshot:
    """Load the latest persisted crypto sleeve portfolio snapshot."""
    envelope = evidence_store.load_snapshot(_SLEEVE_PORTFOLIO_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise SleevePortfolioCorruptError(
            f"Sleeve portfolio snapshot 'data' must be a dict, got {type(data).__name__!r}"
        )
    return sleeve_portfolio_snapshot_from_dict(data)


def export_sleeve_admission_release_pack(
    *,
    pack: SleeveAdmissionReleasePack,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest operator-facing sleeve admission release pack."""
    data = sleeve_admission_release_pack_to_dict(pack)
    result = evidence_store.save_snapshot(_SLEEVE_ADMISSION_RELEASE_PACK_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_SLEEVE_ADMISSION_RELEASE_PACK_SNAPSHOT_NAME, data)
    return result


def load_sleeve_admission_release_pack(*, evidence_store: EvidenceStore) -> SleeveAdmissionReleasePack:
    """Load the latest persisted operator-facing sleeve admission release pack."""
    envelope = evidence_store.load_snapshot(_SLEEVE_ADMISSION_RELEASE_PACK_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Sleeve admission release pack 'data' must be a dict, got {type(data).__name__!r}"
        )
    return sleeve_admission_release_pack_from_dict(data)


def export_managed_sleeve_set_manifest(
    *,
    manifest: ManagedSleeveSetManifest,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest paper-only managed sleeve set manifest."""
    data = managed_sleeve_set_manifest_to_dict(manifest)
    result = evidence_store.save_snapshot(_MANAGED_SLEEVE_SET_MANIFEST_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_MANAGED_SLEEVE_SET_MANIFEST_SNAPSHOT_NAME, data)
    return result


def load_managed_sleeve_set_manifest(*, evidence_store: EvidenceStore) -> ManagedSleeveSetManifest:
    """Load the latest persisted paper-only managed sleeve set manifest."""
    envelope = evidence_store.load_snapshot(_MANAGED_SLEEVE_SET_MANIFEST_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Managed sleeve set manifest 'data' must be a dict, got {type(data).__name__!r}"
        )
    return managed_sleeve_set_manifest_from_dict(data)


def export_paper_shadow_activation_plan(
    *,
    plan: PaperShadowActivationPlan,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest paper/shadow-only activation plan."""
    data = paper_shadow_activation_plan_to_dict(plan)
    result = evidence_store.save_snapshot(_PAPER_SHADOW_ACTIVATION_PLAN_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_PAPER_SHADOW_ACTIVATION_PLAN_SNAPSHOT_NAME, data)
    return result


def load_paper_shadow_activation_plan(*, evidence_store: EvidenceStore) -> PaperShadowActivationPlan:
    """Load the latest persisted paper/shadow-only activation plan."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_ACTIVATION_PLAN_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise SleeveAdmissionCorruptError(
            f"Paper/shadow activation plan 'data' must be a dict, got {type(data).__name__!r}"
        )
    return paper_shadow_activation_plan_from_dict(data)


def export_paper_shadow_session_snapshot(
    *,
    snapshot: PaperShadowSessionSnapshot,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist the latest paper/shadow session lifecycle snapshot."""
    data = paper_shadow_session_snapshot_to_dict(snapshot)
    result = evidence_store.save_snapshot(_PAPER_SHADOW_SESSION_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_PAPER_SHADOW_SESSION_SNAPSHOT_NAME, data)
    return result


def load_paper_shadow_session_snapshot(*, evidence_store: EvidenceStore) -> PaperShadowSessionSnapshot:
    """Load the latest persisted paper/shadow session lifecycle snapshot."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_SESSION_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow session snapshot 'data' must be a dict, got {type(data).__name__!r}"
        )
    return paper_shadow_session_snapshot_from_dict(data)


def export_paper_shadow_market_event_batch(
    *,
    batch: MarketEventBatch,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic read-only paper/shadow market event batch."""
    data = market_event_batch_to_dict(batch)
    result = evidence_store.save_snapshot(_PAPER_SHADOW_MARKET_EVENT_BATCH_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_PAPER_SHADOW_MARKET_EVENT_BATCH_SNAPSHOT_NAME, data)
    return result


def load_paper_shadow_market_event_batch(*, evidence_store: EvidenceStore) -> MarketEventBatch:
    """Load the latest deterministic read-only paper/shadow market event batch."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_MARKET_EVENT_BATCH_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow market event batch 'data' must be a dict, got {type(data).__name__!r}"
        )
    return market_event_batch_from_dict(data)


def export_paper_shadow_feed_replay_plan(
    *,
    plan: FeedReplayPlan,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic local paper/shadow feed replay plan."""
    data = feed_replay_plan_to_dict(plan)
    result = evidence_store.save_snapshot(_PAPER_SHADOW_FEED_REPLAY_PLAN_SNAPSHOT_NAME, data)
    if not result.success:
        return result
    evidence_store.append_evidence(_PAPER_SHADOW_FEED_REPLAY_PLAN_SNAPSHOT_NAME, data)
    return result


def load_paper_shadow_feed_replay_plan(*, evidence_store: EvidenceStore) -> FeedReplayPlan:
    """Load the latest deterministic local paper/shadow feed replay plan."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_FEED_REPLAY_PLAN_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow feed replay plan 'data' must be a dict, got {type(data).__name__!r}"
        )
    return feed_replay_plan_from_dict(data)


def export_paper_shadow_feed_replay_result(
    *,
    result: FeedReplayResult,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic local paper/shadow feed replay result."""
    data = feed_replay_result_to_dict(result)
    write_result = evidence_store.save_snapshot(_PAPER_SHADOW_FEED_REPLAY_RESULT_SNAPSHOT_NAME, data)
    if not write_result.success:
        return write_result
    evidence_store.append_evidence(_PAPER_SHADOW_FEED_REPLAY_RESULT_SNAPSHOT_NAME, data)
    return write_result


def load_paper_shadow_feed_replay_result(*, evidence_store: EvidenceStore) -> FeedReplayResult:
    """Load the latest deterministic local paper/shadow feed replay result."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_FEED_REPLAY_RESULT_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow feed replay result 'data' must be a dict, got {type(data).__name__!r}"
        )
    return feed_replay_result_from_dict(data)


def export_paper_data_source_batch_result(
    *,
    result: PaperDataSourceBatchResult,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic local paper data-source conversion result."""
    data = paper_data_source_batch_result_to_dict(result)
    write_result = evidence_store.save_snapshot(_PAPER_DATA_SOURCE_BATCH_RESULT_SNAPSHOT_NAME, data)
    if not write_result.success:
        return write_result
    evidence_store.append_evidence(_PAPER_DATA_SOURCE_BATCH_RESULT_SNAPSHOT_NAME, data)
    return write_result


def load_paper_data_source_batch_result(*, evidence_store: EvidenceStore) -> PaperDataSourceBatchResult:
    """Load the latest deterministic local paper data-source conversion result."""
    envelope = evidence_store.load_snapshot(_PAPER_DATA_SOURCE_BATCH_RESULT_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper data source batch result 'data' must be a dict, got {type(data).__name__!r}"
        )
    return paper_data_source_batch_result_from_dict(data)


def export_paper_shadow_run_evidence_report(
    *,
    report: PaperShadowRunEvidenceReport,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic paper/shadow run-level evidence report."""
    data = paper_shadow_run_evidence_report_to_dict(report)
    write_result = evidence_store.save_snapshot(_PAPER_SHADOW_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME, data)
    if not write_result.success:
        return write_result
    evidence_store.append_evidence(_PAPER_SHADOW_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME, data)
    return write_result


def load_paper_shadow_run_evidence_report(*, evidence_store: EvidenceStore) -> PaperShadowRunEvidenceReport:
    """Load the latest deterministic paper/shadow run-level evidence report."""
    envelope = evidence_store.load_snapshot(_PAPER_SHADOW_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow run evidence report 'data' must be a dict, got {type(data).__name__!r}"
        )
    return paper_shadow_run_evidence_report_from_dict(data)


def export_multi_source_run_evidence_report(
    *,
    report: MultiSourceRunEvidenceReport,
    evidence_store: EvidenceStore,
) -> WriteResult:
    """Persist a deterministic multi-source paper/shadow run evidence report."""
    data = multi_source_run_evidence_report_to_dict(report)
    write_result = evidence_store.save_snapshot(_MULTI_SOURCE_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME, data)
    if not write_result.success:
        return write_result
    evidence_store.append_evidence(_MULTI_SOURCE_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME, data)
    return write_result


def load_multi_source_run_evidence_report(*, evidence_store: EvidenceStore) -> MultiSourceRunEvidenceReport:
    """Load the latest deterministic multi-source paper/shadow run evidence report."""
    envelope = evidence_store.load_snapshot(_MULTI_SOURCE_RUN_EVIDENCE_REPORT_SNAPSHOT_NAME)
    data = envelope.get("data")
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Multi-source run evidence report 'data' must be a dict, got {type(data).__name__!r}"
        )
    return multi_source_run_evidence_report_from_dict(data)
