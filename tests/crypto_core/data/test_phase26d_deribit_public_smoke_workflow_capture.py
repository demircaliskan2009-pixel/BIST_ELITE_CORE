from __future__ import annotations

from pathlib import Path

WORKFLOW_PATH = Path(".github/workflows/deribit-public-smoke.yml")


def test_phase26d_workflow_exposes_stronger_public_capture_inputs() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    for input_name in ("duration_seconds", "max_messages", "sample_limit", "max_receive_lag_ms"):
        assert f"{input_name}:" in workflow
    assert 'default: "30"' in workflow
    assert workflow.count('default: "100"') >= 2
    assert 'default: "60000"' in workflow
    assert "DERIBIT_SMOKE_DURATION_SECONDS: ${{ inputs.duration_seconds || '30' }}" in workflow
    assert "DERIBIT_SMOKE_MAX_MESSAGES: ${{ inputs.max_messages || '100' }}" in workflow
    assert "DERIBIT_SMOKE_SAMPLE_LIMIT: ${{ inputs.sample_limit || '100' }}" in workflow
    assert "DERIBIT_SMOKE_MAX_RECEIVE_LAG_MS: ${{ inputs.max_receive_lag_ms || '60000' }}" in workflow


def test_phase26d_workflow_passes_capture_inputs_to_smoke_script() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "--authorization PUBLIC_MARKET_DATA_ONLY" in workflow
    assert '--duration-seconds "$DERIBIT_SMOKE_DURATION_SECONDS"' in workflow
    assert '--max-messages "$DERIBIT_SMOKE_MAX_MESSAGES"' in workflow
    assert '--sample-limit "$DERIBIT_SMOKE_SAMPLE_LIMIT"' in workflow
    assert '--max-receive-lag-ms "$DERIBIT_SMOKE_MAX_RECEIVE_LAG_MS"' in workflow
    assert "name: deribit-public-smoke-proof" in workflow
    assert "path: smoke_result.json" in workflow


def test_phase26d_workflow_remains_manual_public_data_only() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    lowered = workflow.lower()

    assert "public market data only" in lowered
    assert "contents: read" in workflow
    assert "push:" not in workflow
    assert "pull_request:" not in workflow
    assert "${{ secrets." not in lowered
    for forbidden in ("private/", "private_", "api_key", "api_secret", "create_order", "send_order"):
        assert forbidden not in lowered
