from __future__ import annotations

import json

from crypto_core.venue.deribit_campaign_telemetry_audit import run_deribit_campaign_telemetry_audit
from tests.crypto_core.venue.test_phase49b_campaign_telemetry_audit_artifact import (
    _artifact,
    _phase47_approval,
    _phase48_artifact,
)


def test_phase49g_validation_is_deterministic() -> None:
    phase48 = _phase48_artifact()
    approval = _phase47_approval()

    first = run_deribit_campaign_telemetry_audit(phase48, approval)
    second = run_deribit_campaign_telemetry_audit(phase48, approval)

    assert first == second


def test_phase49g_artifact_json_round_trip_is_deterministic() -> None:
    artifact = _artifact()

    first = json.dumps(artifact, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
