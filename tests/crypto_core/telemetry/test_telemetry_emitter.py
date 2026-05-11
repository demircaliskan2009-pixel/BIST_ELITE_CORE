"""Tests for TelemetryEmitter and schema-validated stage payloads (PRD §4.4)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from crypto_core.telemetry.emitter import TelemetryEmitter, TelemetryValidationError
from crypto_core.telemetry.models import TelemetryAlert, TelemetryEnvelope, TelemetryStage

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS_MS = 1_700_000_000_000  # 2023-11-14 epoch ms


def _emitter(tmp_path: Path) -> TelemetryEmitter:
    fixed_now = datetime(2024, 1, 15, tzinfo=timezone.utc)
    return TelemetryEmitter(log_dir=tmp_path, now_utc=lambda: fixed_now)


def _good_data_envelope() -> TelemetryEnvelope:
    return TelemetryEnvelope(
        timestamp_ms=_TS_MS,
        stage=TelemetryStage.DATA,
        metrics={"stage_latency_ms": 42.0},
    )


def _good_edge_envelope() -> TelemetryEnvelope:
    return TelemetryEnvelope(
        timestamp_ms=_TS_MS,
        stage=TelemetryStage.EDGE,
        metrics={"stage_latency_ms": 15.0, "active_edges": 3},
    )


def _good_risk_envelope() -> TelemetryEnvelope:
    return TelemetryEnvelope(
        timestamp_ms=_TS_MS,
        stage=TelemetryStage.RISK,
        metrics={"stage_latency_ms": 8.0, "shs_value": 0.95, "kill_switch_level": 0},
    )


def _good_exec_envelope() -> TelemetryEnvelope:
    return TelemetryEnvelope(
        timestamp_ms=_TS_MS,
        stage=TelemetryStage.EXECUTION,
        metrics={"stage_latency_ms": 12.0},
    )


# ---------------------------------------------------------------------------
# TelemetryEnvelope.validate()
# ---------------------------------------------------------------------------


class TestEnvelopeValidate:
    def test_valid_data_envelope(self) -> None:
        assert _good_data_envelope().validate() == []

    def test_valid_edge_envelope(self) -> None:
        assert _good_edge_envelope().validate() == []

    def test_valid_risk_envelope(self) -> None:
        assert _good_risk_envelope().validate() == []

    def test_valid_execution_envelope(self) -> None:
        assert _good_exec_envelope().validate() == []

    def test_invalid_stage(self) -> None:
        env = TelemetryEnvelope(timestamp_ms=_TS_MS, stage="unknown_stage", metrics={"stage_latency_ms": 1})
        errors = env.validate()
        assert any("invalid stage" in e for e in errors)

    def test_zero_timestamp_fails(self) -> None:
        env = TelemetryEnvelope(timestamp_ms=0, stage=TelemetryStage.DATA, metrics={"stage_latency_ms": 1})
        errors = env.validate()
        assert any("timestamp_ms" in e for e in errors)

    def test_missing_required_metric_fails(self) -> None:
        env = TelemetryEnvelope(
            timestamp_ms=_TS_MS,
            stage=TelemetryStage.RISK,
            metrics={"stage_latency_ms": 1.0},  # missing shs_value, kill_switch_level
        )
        errors = env.validate()
        assert len(errors) == 2

    def test_null_metric_value_fails(self) -> None:
        env = TelemetryEnvelope(
            timestamp_ms=_TS_MS,
            stage=TelemetryStage.DATA,
            metrics={"stage_latency_ms": None},  # type: ignore[dict-item]
        )
        errors = env.validate()
        assert any("None" in e for e in errors)

    def test_invalid_alert_severity_fails(self) -> None:
        alert = TelemetryAlert(metric="shs_value", value=0.3, threshold=0.5, severity="low")  # type: ignore[arg-type]
        env = TelemetryEnvelope(
            timestamp_ms=_TS_MS,
            stage=TelemetryStage.DATA,
            metrics={"stage_latency_ms": 1.0},
            alerts=[alert],
        )
        errors = env.validate()
        assert any("severity" in e for e in errors)

    def test_valid_alert_passes(self) -> None:
        alert = TelemetryAlert(metric="shs_value", value=0.3, threshold=0.5, severity="critical")
        env = TelemetryEnvelope(
            timestamp_ms=_TS_MS,
            stage=TelemetryStage.RISK,
            metrics={"stage_latency_ms": 1.0, "shs_value": 0.3, "kill_switch_level": 1},
            alerts=[alert],
        )
        assert env.validate() == []


# ---------------------------------------------------------------------------
# TelemetryEmitter.emit()
# ---------------------------------------------------------------------------


class TestEmitterEmit:
    def test_valid_emit_writes_jsonl(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        emitter.emit(_good_data_envelope())

        out_file = tmp_path / "telemetry_2024-01-15.jsonl"
        assert out_file.exists()
        line = out_file.read_text(encoding="utf-8").strip()
        data = json.loads(line)
        assert data["stage"] == "data"
        assert data["timestamp_ms"] == _TS_MS
        assert "stage_latency_ms" in data["metrics"]

    def test_invalid_payload_raises(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        bad = TelemetryEnvelope(timestamp_ms=0, stage="bad_stage", metrics={})
        with pytest.raises(TelemetryValidationError) as exc_info:
            emitter.emit(bad)
        assert "invalid" in str(exc_info.value).lower()

    def test_invalid_payload_does_not_write(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        bad = TelemetryEnvelope(timestamp_ms=0, stage="bad_stage", metrics={})
        with pytest.raises(TelemetryValidationError):
            emitter.emit(bad)
        # No file should be written
        assert not list(tmp_path.glob("*.jsonl"))

    def test_multiple_emits_append(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        emitter.emit(_good_data_envelope())
        emitter.emit(_good_edge_envelope())
        emitter.emit(_good_risk_envelope())

        out_file = tmp_path / "telemetry_2024-01-15.jsonl"
        lines = [l for l in out_file.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(lines) == 3
        stages = [json.loads(l)["stage"] for l in lines]
        assert stages == ["data", "edge", "risk"]

    def test_emit_result_success(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        result = emitter.emit(_good_data_envelope())
        assert result.success is True
        assert "2024-01-15" in result.path
        assert result.errors == []

    def test_emit_safe_does_not_raise_on_invalid(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        bad = TelemetryEnvelope(timestamp_ms=0, stage="bad", metrics={})
        result = emitter.emit_safe(bad)
        assert result.success is False
        assert len(result.errors) > 0


# ---------------------------------------------------------------------------
# Stage-specific builder methods
# ---------------------------------------------------------------------------


class TestStageBuilders:
    def test_build_data_envelope(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        env = emitter.build_data_envelope(
            _TS_MS,
            stage_latency_ms=25.0,
            ws_reconnect_count=1,
            book_crc32_fail_rate=0.001,
        )
        assert env.stage == TelemetryStage.DATA
        assert env.validate() == []

    def test_build_edge_envelope(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        env = emitter.build_edge_envelope(_TS_MS, 12.0, active_edges=2, edge_hit_rate=0.45)
        assert env.stage == TelemetryStage.EDGE
        assert env.validate() == []

    def test_build_risk_envelope(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        env = emitter.build_risk_envelope(_TS_MS, 8.0, shs_value=0.90, kill_switch_level=0, cvar99_pct=0.02)
        assert env.stage == TelemetryStage.RISK
        assert env.validate() == []

    def test_build_execution_envelope(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        env = emitter.build_execution_envelope(_TS_MS, 5.0, execution_slippage_bps=3.0, fill_rate_pct=99.5)
        assert env.stage == TelemetryStage.EXECUTION
        assert env.validate() == []


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestSerialization:
    def test_no_alerts_key_if_empty(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        emitter.emit(_good_data_envelope())
        out_file = tmp_path / "telemetry_2024-01-15.jsonl"
        data = json.loads(out_file.read_text(encoding="utf-8").strip())
        # alerts key should NOT appear if empty (schema allows omission)
        assert "alerts" not in data

    def test_alerts_serialized_correctly(self, tmp_path: Path) -> None:
        emitter = _emitter(tmp_path)
        alert = TelemetryAlert(metric="shs_value", value=0.3, threshold=0.5, severity="critical")
        env = TelemetryEnvelope(
            timestamp_ms=_TS_MS,
            stage=TelemetryStage.RISK,
            metrics={"stage_latency_ms": 1.0, "shs_value": 0.3, "kill_switch_level": 0},
            alerts=[alert],
        )
        emitter.emit(env)
        out_file = tmp_path / "telemetry_2024-01-15.jsonl"
        data = json.loads(out_file.read_text(encoding="utf-8").strip())
        assert data["alerts"][0]["severity"] == "critical"
