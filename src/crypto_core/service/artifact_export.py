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

from crypto_core.service.evidence_store import EvidenceStore, WriteResult

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
