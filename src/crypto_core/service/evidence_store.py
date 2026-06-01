"""Persistent operator evidence store — Phase 8C.

Append-safe JSONL evidence log + atomic JSON snapshot for the managed
paper-live service.

Persists bounded operator evidence to disk:
  - readiness snapshots
  - health trend snapshots
  - queue pressure transitions
  - service-level failures
  - cycle summary / audit records

Design rules:
  - JSONL for append-style evidence (one JSON object per line).
  - Atomic JSON for current-state snapshots (temp-file + rename).
  - Fail-closed on malformed persisted data (raise, never skip).
  - Bounded: configurable max lines for JSONL, oldest truncated on compact.
  - Write failures are explicit — returned as error results and tracked.
  - Deterministic: same inputs → same outputs.
  - Thread-safe for write operations (single lock).

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crypto_core.audit import (
    DecisionLedgerRecord,
    decision_ledger_digest,
    decision_ledger_record_to_dict,
    validate_decision_ledger_record,
)

logger = logging.getLogger(__name__)

_EVIDENCE_SCHEMA_VERSION = "1"
_SNAPSHOT_SCHEMA_VERSION = "1"
_DECISION_LEDGER_EVIDENCE_TYPE = "audit_record"
_DECISION_LEDGER_PAYLOAD_SCHEMA_VERSION = "1"
_DECISION_LEDGER_PAYLOAD_TYPE = "decision_ledger_record"


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EvidenceStoreCorruptError(RuntimeError):
    """Raised when persisted evidence data is malformed.

    Fail-closed: any corruption → STOP restore.
    """


class EvidenceWriteError(RuntimeError):
    """Raised when a write to the evidence store fails."""


# ---------------------------------------------------------------------------
# Evidence record types
# ---------------------------------------------------------------------------


EVIDENCE_TYPES = frozenset(
    {
        "readiness_snapshot",
        "health_trend_snapshot",
        "pressure_transition",
        "service_failure",
        "audit_record",
        "cycle_summary",
        "service_transition",
    }
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceStoreConfig:
    """Configuration for the persistent evidence store.

    max_evidence_lines:  maximum JSONL lines before compaction.
    compaction_keep:     lines to keep after compaction (most recent).
    snapshot_indent:     JSON indent for atomic snapshot files.
    """

    max_evidence_lines: int = 5000
    compaction_keep: int = 2000
    snapshot_indent: int = 2


# ---------------------------------------------------------------------------
# Write result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WriteResult:
    """Result of a write operation.

    success:  True if the write succeeded.
    error:    error message if failed; None if success.
    path:     file path that was written.
    """

    success: bool
    error: str | None = None
    path: str = ""


# ---------------------------------------------------------------------------
# Evidence store
# ---------------------------------------------------------------------------


class EvidenceStore:
    """Persistent operator evidence store for paper-live operations.

    Provides:
      - append_evidence(): JSONL append of typed evidence records.
      - save_snapshot(): atomic JSON write of current-state snapshots.
      - load_evidence(): read + validate JSONL evidence log.
      - load_snapshot(): read + validate atomic JSON snapshot.
      - compact(): truncate JSONL to bounded retention.

    Thread-safe: all writes are serialized by an internal lock.

    Usage::

        store = EvidenceStore(
            evidence_dir=Path("runtime/evidence"),
            config=EvidenceStoreConfig(),
        )
        result = store.append_evidence("readiness_snapshot", {"level": "ready"})
        result = store.save_snapshot("run_state", {"run_id": "abc"})
        records = store.load_evidence()
        snapshot = store.load_snapshot("run_state")
    """

    def __init__(
        self,
        *,
        evidence_dir: Path,
        config: EvidenceStoreConfig | None = None,
    ) -> None:
        self._dir = evidence_dir
        self._config = config or EvidenceStoreConfig()
        self._lock = threading.Lock()
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def evidence_dir(self) -> Path:
        """Root directory for evidence files."""
        return self._dir

    @property
    def evidence_log_path(self) -> Path:
        """Path to the JSONL evidence log."""
        return self._dir / "evidence.jsonl"

    def snapshot_path(self, name: str) -> Path:
        """Path to an atomic JSON snapshot file."""
        return self._dir / f"{name}.json"

    # ------------------------------------------------------------------
    # JSONL evidence append
    # ------------------------------------------------------------------

    def append_evidence(
        self,
        evidence_type: str,
        data: dict,
    ) -> WriteResult:
        """Append one evidence record to the JSONL log.

        Args:
            evidence_type: one of EVIDENCE_TYPES (validated).
            data: arbitrary dict payload for this evidence record.

        Returns:
            WriteResult indicating success or failure.
        """
        if evidence_type not in EVIDENCE_TYPES:
            return WriteResult(
                success=False,
                error=f"Unknown evidence_type={evidence_type!r}",
                path=str(self.evidence_log_path),
            )

        record = {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "evidence_type": evidence_type,
            "timestamp_ns": time.time_ns(),
            "data": data,
        }

        with self._lock:
            try:
                line = json.dumps(record, default=str) + "\n"
                with self.evidence_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                return WriteResult(success=True, path=str(self.evidence_log_path))
            except Exception as exc:
                msg = f"Evidence append failed: {exc}"
                logger.error(msg)
                return WriteResult(success=False, error=msg, path=str(self.evidence_log_path))

    def append_evidence_batch(
        self,
        records: list[tuple[str, dict]],
    ) -> WriteResult:
        """Append multiple evidence records atomically.

        Args:
            records: list of (evidence_type, data) tuples.

        Returns:
            WriteResult for the batch.
        """
        lines: list[str] = []
        now_ns = time.time_ns()
        for evidence_type, data in records:
            if evidence_type not in EVIDENCE_TYPES:
                return WriteResult(
                    success=False,
                    error=f"Unknown evidence_type={evidence_type!r}",
                    path=str(self.evidence_log_path),
                )
            record = {
                "schema_version": _EVIDENCE_SCHEMA_VERSION,
                "evidence_type": evidence_type,
                "timestamp_ns": now_ns,
                "data": data,
            }
            lines.append(json.dumps(record, default=str) + "\n")

        with self._lock:
            try:
                with self.evidence_log_path.open("a", encoding="utf-8") as fh:
                    fh.writelines(lines)
                return WriteResult(success=True, path=str(self.evidence_log_path))
            except Exception as exc:
                msg = f"Evidence batch append failed: {exc}"
                logger.error(msg)
                return WriteResult(success=False, error=msg, path=str(self.evidence_log_path))

    def append_decision_ledger_record(
        self,
        record_or_payload: DecisionLedgerRecord | Mapping[str, Any],
    ) -> WriteResult:
        """Append a deterministic DecisionLedgerRecord evidence payload.

        This adapter validates the decision ledger contract first and rejects
        duplicate ledger digests. It writes the existing evidence JSONL envelope
        with a deterministic timestamp sentinel instead of generating wall-clock
        time.
        """
        try:
            payload = decision_ledger_record_to_evidence_payload(record_or_payload)
        except ValueError as exc:
            return WriteResult(
                success=False,
                error=f"Decision ledger evidence rejected: {exc}",
                path=str(self.evidence_log_path),
            )

        evidence_digest = payload["evidence_digest"]
        try:
            if self._decision_ledger_digest_exists(evidence_digest):
                return WriteResult(
                    success=False,
                    error=f"Duplicate decision ledger evidence digest: {evidence_digest}",
                    path=str(self.evidence_log_path),
                )
        except EvidenceStoreCorruptError as exc:
            return WriteResult(
                success=False,
                error=f"Decision ledger evidence state invalid: {exc}",
                path=str(self.evidence_log_path),
            )

        envelope = {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "evidence_type": _DECISION_LEDGER_EVIDENCE_TYPE,
            "timestamp_ns": 0,
            "data": payload,
        }

        with self._lock:
            try:
                line = json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
                with self.evidence_log_path.open("a", encoding="utf-8") as fh:
                    fh.write(line)
                return WriteResult(success=True, path=str(self.evidence_log_path))
            except Exception as exc:
                msg = f"Decision ledger evidence append failed: {exc}"
                logger.error(msg)
                return WriteResult(success=False, error=msg, path=str(self.evidence_log_path))

    def _decision_ledger_digest_exists(self, evidence_digest: object) -> bool:
        if not isinstance(evidence_digest, str) or not evidence_digest:
            raise EvidenceStoreCorruptError("Decision ledger evidence digest is malformed")

        for record in self.load_evidence():
            if record.get("evidence_type") != _DECISION_LEDGER_EVIDENCE_TYPE:
                continue
            data = record.get("data")
            if not isinstance(data, Mapping):
                continue
            if (
                data.get("payload_type") == _DECISION_LEDGER_PAYLOAD_TYPE
                and data.get("evidence_digest") == evidence_digest
            ):
                return True
        return False

    # ------------------------------------------------------------------
    # JSONL evidence load
    # ------------------------------------------------------------------

    def load_evidence(self) -> list[dict]:
        """Load and validate all evidence records from the JSONL log.

        Returns:
            List of validated evidence dicts (oldest first).

        Raises:
            EvidenceStoreCorruptError: if any line is malformed (fail-closed).
        """
        path = self.evidence_log_path
        if not path.exists():
            return []

        records: list[dict] = []
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    record = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise EvidenceStoreCorruptError(f"Evidence JSONL line {line_no} is malformed: {exc}") from exc

                _validate_evidence_record(record, line_no)
                records.append(record)

        return records

    def evidence_line_count(self) -> int:
        """Count lines in the evidence log without loading all records."""
        path = self.evidence_log_path
        if not path.exists():
            return 0
        count = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    count += 1
        return count

    # ------------------------------------------------------------------
    # Atomic JSON snapshot
    # ------------------------------------------------------------------

    def save_snapshot(self, name: str, data: dict) -> WriteResult:
        """Atomically write a JSON snapshot.

        Args:
            name: snapshot identifier (used as filename stem).
            data: dict payload to serialize.

        Returns:
            WriteResult indicating success or failure.

        The write is atomic: data goes to a .tmp file first, then renamed.
        """
        path = self.snapshot_path(name)
        envelope = {
            "schema_version": _SNAPSHOT_SCHEMA_VERSION,
            "snapshot_name": name,
            "timestamp_ns": time.time_ns(),
            "data": data,
        }

        with self._lock:
            try:
                tmp_path = path.with_suffix(".tmp")
                content = json.dumps(envelope, indent=self._config.snapshot_indent, default=str)
                with tmp_path.open("w", encoding="utf-8") as fh:
                    fh.write(content)
                os.replace(tmp_path, path)
                return WriteResult(success=True, path=str(path))
            except Exception as exc:
                msg = f"Snapshot write failed for {name!r}: {exc}"
                logger.error(msg)
                return WriteResult(success=False, error=msg, path=str(path))

    def load_snapshot(self, name: str) -> dict:
        """Load and validate an atomic JSON snapshot.

        Args:
            name: snapshot identifier (filename stem).

        Returns:
            The validated snapshot envelope dict.

        Raises:
            EvidenceStoreCorruptError: if file missing, malformed, or invalid.
        """
        path = self.snapshot_path(name)
        if not path.exists():
            raise EvidenceStoreCorruptError(f"Snapshot {name!r} not found at {path}")

        try:
            with path.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise EvidenceStoreCorruptError(f"Snapshot {name!r} JSON decode error: {exc}") from exc

        _validate_snapshot_envelope(raw, name)
        return raw

    def snapshot_exists(self, name: str) -> bool:
        """True if a snapshot file exists for the given name."""
        return self.snapshot_path(name).exists()

    # ------------------------------------------------------------------
    # Compaction (bounded retention)
    # ------------------------------------------------------------------

    def compact(self) -> WriteResult:
        """Compact the JSONL evidence log to bounded retention.

        Keeps the most recent ``compaction_keep`` lines. Atomic:
        writes to a temp file, then replaces the original.

        Returns:
            WriteResult indicating success or failure.
        """
        path = self.evidence_log_path
        if not path.exists():
            return WriteResult(success=True, path=str(path))

        with self._lock:
            try:
                with path.open("r", encoding="utf-8") as fh:
                    all_lines = fh.readlines()

                non_empty = [line for line in all_lines if line.strip()]
                if len(non_empty) <= self._config.compaction_keep:
                    return WriteResult(success=True, path=str(path))

                keep = non_empty[-self._config.compaction_keep :]
                tmp_path = path.with_suffix(".compact.tmp")
                with tmp_path.open("w", encoding="utf-8") as fh:
                    fh.writelines(keep)
                os.replace(tmp_path, path)
                return WriteResult(success=True, path=str(path))
            except Exception as exc:
                msg = f"Evidence compaction failed: {exc}"
                logger.error(msg)
                return WriteResult(success=False, error=msg, path=str(path))

    def needs_compaction(self) -> bool:
        """True if the evidence log exceeds max_evidence_lines."""
        return self.evidence_line_count() > self._config.max_evidence_lines

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Remove all evidence files. Used for testing."""
        with self._lock:
            for f in self._dir.iterdir():
                if f.is_file():
                    f.unlink()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def _validate_evidence_record(record: object, line_no: int) -> None:
    """Fail-closed validation for one JSONL evidence record."""
    if not isinstance(record, dict):
        raise EvidenceStoreCorruptError(f"Evidence line {line_no}: expected dict, got {type(record).__name__!r}")
    required = {"schema_version", "evidence_type", "timestamp_ns", "data"}
    missing = required - set(record)
    if missing:
        raise EvidenceStoreCorruptError(f"Evidence line {line_no}: missing fields {sorted(missing)!r}")
    if record["schema_version"] != _EVIDENCE_SCHEMA_VERSION:
        raise EvidenceStoreCorruptError(f"Evidence line {line_no}: unknown schema_version={record['schema_version']!r}")
    if record["evidence_type"] not in EVIDENCE_TYPES:
        raise EvidenceStoreCorruptError(f"Evidence line {line_no}: unknown evidence_type={record['evidence_type']!r}")


def _validate_snapshot_envelope(raw: object, name: str) -> None:
    """Fail-closed validation for an atomic snapshot envelope."""
    if not isinstance(raw, dict):
        raise EvidenceStoreCorruptError(f"Snapshot {name!r}: expected dict, got {type(raw).__name__!r}")
    required = {"schema_version", "snapshot_name", "timestamp_ns", "data"}
    missing = required - set(raw)
    if missing:
        raise EvidenceStoreCorruptError(f"Snapshot {name!r}: missing fields {sorted(missing)!r}")
    if raw["schema_version"] != _SNAPSHOT_SCHEMA_VERSION:
        raise EvidenceStoreCorruptError(f"Snapshot {name!r}: unknown schema_version={raw['schema_version']!r}")


def decision_ledger_record_to_evidence_payload(
    record_or_payload: DecisionLedgerRecord | Mapping[str, Any],
) -> dict[str, Any]:
    """Convert a valid DecisionLedgerRecord into a canonical evidence payload."""
    validation = validate_decision_ledger_record(record_or_payload)
    if not validation.accepted or validation.record is None:
        reasons = ",".join(validation.rejection_reasons) or "decision_ledger:invalid"
        raise ValueError(reasons)

    record_payload = decision_ledger_record_to_dict(validation.record)
    evidence_digest = decision_ledger_digest(validation.record)
    return {
        "schema_version": _DECISION_LEDGER_PAYLOAD_SCHEMA_VERSION,
        "payload_type": _DECISION_LEDGER_PAYLOAD_TYPE,
        "evidence_digest": evidence_digest,
        "decision_ledger_record": record_payload,
        "stage": record_payload["stage"],
        "status": record_payload["status"],
        "strategy_id": record_payload["strategy_id"],
        "strategy_digest": record_payload["strategy_digest"],
        "input_digest": record_payload["input_digest"],
        "output_digest": record_payload["output_digest"],
        "accepted": record_payload["accepted"],
        "rejection_reasons": list(record_payload["rejection_reasons"]),
        "needs_research_reasons": list(record_payload["needs_research_reasons"]),
        "evidence_refs": list(record_payload["evidence_refs"]),
        "correlation_id": record_payload["correlation_id"],
        "previous_record_digest": record_payload["previous_record_digest"],
    }
