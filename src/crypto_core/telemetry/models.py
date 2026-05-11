"""Telemetry typed models — schema-aligned with telemetry_schema.json.

Every field name maps 1:1 to the JSON schema defined in
logs/telemetry/telemetry_schema.json.

PRD reference: §4.4 Telemetry Contract.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class TelemetryStage(str):
    """Valid pipeline stage identifiers (matches schema enum)."""

    pass


TelemetryStage.DATA = TelemetryStage("data")
TelemetryStage.EDGE = TelemetryStage("edge")
TelemetryStage.RISK = TelemetryStage("risk")
TelemetryStage.EXECUTION = TelemetryStage("execution")

#: All valid stage values.
VALID_STAGES: frozenset[str] = frozenset(
    {TelemetryStage.DATA, TelemetryStage.EDGE, TelemetryStage.RISK, TelemetryStage.EXECUTION}
)

#: Required metric keys per stage (validation contract).
REQUIRED_METRICS: dict[str, frozenset[str]] = {
    TelemetryStage.DATA: frozenset({"stage_latency_ms"}),
    TelemetryStage.EDGE: frozenset({"stage_latency_ms", "active_edges"}),
    TelemetryStage.RISK: frozenset({"stage_latency_ms", "shs_value", "kill_switch_level"}),
    TelemetryStage.EXECUTION: frozenset({"stage_latency_ms"}),
}


@dataclass(frozen=True)
class TelemetryAlert:
    """Single threshold-breach alert (matches schema alert item structure)."""

    metric: str
    value: float
    threshold: float
    severity: Literal["warning", "critical"]


@dataclass(frozen=True)
class TelemetryEnvelope:
    """One JSONL row emitted by a pipeline stage.

    Conforms exactly to telemetry_schema.json:
      required: [timestamp_ms, stage, metrics]
      additionalProperties: false
    """

    timestamp_ms: int
    stage: str  # TelemetryStage value
    metrics: dict[str, object]
    alerts: list[TelemetryAlert] = field(default_factory=list)

    def validate(self) -> list[str]:
        """Returns a list of validation errors. Empty list = valid."""
        errors: list[str] = []

        if self.stage not in VALID_STAGES:
            errors.append(f"invalid stage: {self.stage!r} not in {sorted(VALID_STAGES)}")

        if self.timestamp_ms <= 0:
            errors.append(f"invalid timestamp_ms: {self.timestamp_ms} must be > 0")

        required = REQUIRED_METRICS.get(self.stage, frozenset())
        for key in required:
            if key not in self.metrics:
                errors.append(f"missing required metric {key!r} for stage {self.stage!r}")

        for k, v in self.metrics.items():
            if v is None:
                errors.append(f"metric {k!r} is None — null values not allowed")

        for i, alert in enumerate(self.alerts):
            if alert.severity not in ("warning", "critical"):
                errors.append(f"alert[{i}] invalid severity: {alert.severity!r}")

        return errors
