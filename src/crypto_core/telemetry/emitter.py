"""Telemetry Emitter — schema-validated JSONL emission (PRD §4.4).

Writes one record per emit() call to:
  logs/telemetry/telemetry_YYYY-MM-DD.jsonl

Rules:
  - Validates every envelope before writing.
  - Raises TelemetryValidationError on invalid payload (fail-closed).
  - Atomic line append (no partial lines).
  - Reusable by any pipeline stage.
  - No async complexity — synchronous file writes.

PRD reference: §4.4 Telemetry Contract.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from crypto_core.telemetry.models import TelemetryEnvelope

logger = logging.getLogger(__name__)

#: Default telemetry log directory.
DEFAULT_LOG_DIR = Path("logs/telemetry")


class TelemetryValidationError(ValueError):
    """Raised when a telemetry envelope fails schema validation."""


@dataclass
class EmitResult:
    """Result of one emit() call."""

    success: bool
    path: str
    errors: list[str]


class TelemetryEmitter:
    """Writes schema-validated TelemetryEnvelope records to JSONL files.

    File rotation: one file per UTC calendar day.
    File path: <log_dir>/telemetry_YYYY-MM-DD.jsonl

    Fail-closed: invalid envelope → TelemetryValidationError raised.
    The caller must catch this and handle (typically: block downstream).

    Usage::

        emitter = TelemetryEmitter(log_dir=Path("logs/telemetry"))
        emitter.emit(envelope)
    """

    def __init__(
        self,
        log_dir: Path | None = None,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self._log_dir = log_dir or DEFAULT_LOG_DIR
        self._now_utc = now_utc or (lambda: datetime.now(tz=timezone.utc))
        self._log_dir.mkdir(parents=True, exist_ok=True)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def emit(self, envelope: TelemetryEnvelope) -> EmitResult:
        """Validate and write envelope to today's JSONL file.

        Raises:
            TelemetryValidationError: if envelope.validate() returns errors.
        """
        errors = envelope.validate()
        if errors:
            error_str = "; ".join(errors)
            raise TelemetryValidationError(f"Telemetry payload invalid ({len(errors)} error(s)): {error_str}")

        path = self._file_path()
        line = self._serialize(envelope)
        self._write_line(path, line)

        return EmitResult(success=True, path=str(path), errors=[])

    def emit_safe(self, envelope: TelemetryEnvelope) -> EmitResult:
        """Like emit() but catches all exceptions and returns EmitResult.

        Use when telemetry failure must NOT block the calling stage.
        """
        try:
            return self.emit(envelope)
        except TelemetryValidationError as exc:
            logger.error("Telemetry validation failed: %s", exc)
            return EmitResult(success=False, path="", errors=[str(exc)])
        except Exception as exc:
            logger.exception("Telemetry emit raised unexpectedly")
            return EmitResult(success=False, path="", errors=[f"unexpected: {exc}"])

    # -----------------------------------------------------------------------
    # Stage-specific builders (convenience factory methods)
    # -----------------------------------------------------------------------

    def build_data_envelope(
        self,
        timestamp_ms: int,
        stage_latency_ms: float,
        *,
        ws_reconnect_count: int = 0,
        book_crc32_fail_rate: float = 0.0,
        data_drift_psi: float | None = None,
        data_drift_ks: float | None = None,
        alerts: list | None = None,
    ) -> TelemetryEnvelope:
        metrics: dict[str, object] = {
            "stage_latency_ms": stage_latency_ms,
            "ws_reconnect_count": ws_reconnect_count,
            "book_crc32_fail_rate": book_crc32_fail_rate,
        }
        if data_drift_psi is not None:
            metrics["data_drift_psi"] = data_drift_psi
        if data_drift_ks is not None:
            metrics["data_drift_ks"] = data_drift_ks
        return TelemetryEnvelope(timestamp_ms=timestamp_ms, stage="data", metrics=metrics, alerts=alerts or [])

    def build_edge_envelope(
        self,
        timestamp_ms: int,
        stage_latency_ms: float,
        active_edges: int,
        *,
        edge_hit_rate: float | None = None,
        alerts: list | None = None,
    ) -> TelemetryEnvelope:
        metrics: dict[str, object] = {
            "stage_latency_ms": stage_latency_ms,
            "active_edges": active_edges,
        }
        if edge_hit_rate is not None:
            metrics["edge_hit_rate"] = edge_hit_rate
        return TelemetryEnvelope(timestamp_ms=timestamp_ms, stage="edge", metrics=metrics, alerts=alerts or [])

    def build_risk_envelope(
        self,
        timestamp_ms: int,
        stage_latency_ms: float,
        shs_value: float,
        kill_switch_level: int,
        *,
        cvar99_pct: float | None = None,
        margin_utilization_pct: float | None = None,
        alerts: list | None = None,
    ) -> TelemetryEnvelope:
        metrics: dict[str, object] = {
            "stage_latency_ms": stage_latency_ms,
            "shs_value": shs_value,
            "kill_switch_level": kill_switch_level,
        }
        if cvar99_pct is not None:
            metrics["cvar99_pct"] = cvar99_pct
        if margin_utilization_pct is not None:
            metrics["margin_utilization_pct"] = margin_utilization_pct
        return TelemetryEnvelope(timestamp_ms=timestamp_ms, stage="risk", metrics=metrics, alerts=alerts or [])

    def build_execution_envelope(
        self,
        timestamp_ms: int,
        stage_latency_ms: float,
        *,
        execution_slippage_bps: float | None = None,
        fill_rate_pct: float | None = None,
        alerts: list | None = None,
    ) -> TelemetryEnvelope:
        metrics: dict[str, object] = {"stage_latency_ms": stage_latency_ms}
        if execution_slippage_bps is not None:
            metrics["execution_slippage_bps"] = execution_slippage_bps
        if fill_rate_pct is not None:
            metrics["fill_rate_pct"] = fill_rate_pct
        return TelemetryEnvelope(timestamp_ms=timestamp_ms, stage="execution", metrics=metrics, alerts=alerts or [])

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _file_path(self) -> Path:
        date_str = self._now_utc().strftime("%Y-%m-%d")
        return self._log_dir / f"telemetry_{date_str}.jsonl"

    @staticmethod
    def _serialize(envelope: TelemetryEnvelope) -> str:
        """Serialize envelope to compact JSON line."""
        data: dict[str, object] = {
            "timestamp_ms": envelope.timestamp_ms,
            "stage": envelope.stage,
            "metrics": envelope.metrics,
        }
        if envelope.alerts:
            data["alerts"] = [
                {
                    "metric": a.metric,
                    "value": a.value,
                    "threshold": a.threshold,
                    "severity": a.severity,
                }
                for a in envelope.alerts
            ]
        return json.dumps(data, separators=(",", ":"))

    @staticmethod
    def _write_line(path: Path, line: str) -> None:
        """Append one line atomically using line-buffered write."""
        with open(path, "a", encoding="utf-8", buffering=1) as fh:  # noqa: WPS515
            fh.write(line + os.linesep)
