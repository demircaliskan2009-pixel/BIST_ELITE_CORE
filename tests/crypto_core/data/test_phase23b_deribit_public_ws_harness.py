from __future__ import annotations

import ast
import json
from pathlib import Path

from crypto_core.data import deribit_public_ws_harness as harness
from crypto_core.data.deribit_public_ws_harness import (
    DERIBIT_DEFAULT_PUBLIC_CHANNEL,
    DERIBIT_OFFICIAL_PUBLIC_WS_URL,
    DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS,
    DERIBIT_PUBLIC_WS_MAX_SAMPLE_EVENTS,
    DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION,
    DeribitPublicWsSmokeConfig,
    deribit_public_ws_smoke_result_from_dict,
    deribit_public_ws_smoke_result_to_dict,
    run_deribit_public_ws_smoke_test,
    validate_deribit_public_ws_smoke_config,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import VenueId
from crypto_core.venue.operational_evidence_readiness import (
    OperationalEvidenceAcceptanceResult,
    operational_evidence_acceptance_ready,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, get_public_feed_dialect

MODULE_PATH = Path("src/crypto_core/data/deribit_public_ws_harness.py")
SCRIPT_PATH = Path("scripts/crypto_core/deribit_public_ws_smoke.py")
CHECKLIST_PATH = Path("docs/crypto_core/DERIBIT_OPERATIONAL_EVIDENCE_REVIEW_CHECKLIST.md")


def test_missing_operator_authorization_rejects():
    reasons = validate_deribit_public_ws_smoke_config(DeribitPublicWsSmokeConfig())

    assert "deribit_ws:authorization_missing" in reasons


def test_wrong_operator_authorization_rejects():
    reasons = validate_deribit_public_ws_smoke_config(DeribitPublicWsSmokeConfig(operator_authorization="LIVE_TRADING"))

    assert "deribit_ws:authorization_invalid" in reasons


def test_dry_run_false_rejects():
    reasons = validate_deribit_public_ws_smoke_config(_config(dry_run=False))

    assert "deribit_ws:dry_run_required" in reasons


def test_unknown_ws_url_rejects():
    reasons = validate_deribit_public_ws_smoke_config(_config(ws_url="wss://example.test/ws"))

    assert "deribit_ws:url_not_allowed" in reasons


def test_forbidden_raw_channel_rejects():
    reasons = validate_deribit_public_ws_smoke_config(_config(channels=("book.BTC-PERPETUAL.raw",)))

    assert "deribit_ws:channel_forbidden" in reasons


def test_forbidden_private_auth_account_order_channels_reject():
    for channel in (
        "user.orders.BTC-PERPETUAL.raw",
        "private.BTC-PERPETUAL.100ms",
        "auth.BTC-PERPETUAL.100ms",
        "account.BTC-PERPETUAL.100ms",
        "portfolio.BTC-PERPETUAL.100ms",
        "position.BTC-PERPETUAL.100ms",
    ):
        reasons = validate_deribit_public_ws_smoke_config(_config(channels=(channel,)))

        assert "deribit_ws:channel_forbidden" in reasons


def test_bounded_duration_required():
    assert "deribit_ws:duration_unbounded" in validate_deribit_public_ws_smoke_config(_config(duration_seconds=0))
    assert "deribit_ws:duration_unbounded" in validate_deribit_public_ws_smoke_config(_config(duration_seconds=31))


def test_bounded_max_messages_required():
    assert "deribit_ws:max_messages_unbounded" in validate_deribit_public_ws_smoke_config(_config(max_messages=0))
    assert "deribit_ws:max_messages_unbounded" in validate_deribit_public_ws_smoke_config(_config(max_messages=101))


def test_sample_limit_defaults_safe_and_allows_phase26d_capture_bound():
    default_config = DeribitPublicWsSmokeConfig()

    assert default_config.sample_limit == DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS
    assert DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS == 5
    assert DERIBIT_PUBLIC_WS_MAX_SAMPLE_EVENTS == 100
    assert "deribit_ws:sample_limit_invalid" in validate_deribit_public_ws_smoke_config(_config(sample_limit=0))
    assert "deribit_ws:sample_limit_invalid" in validate_deribit_public_ws_smoke_config(_config(sample_limit=101))
    assert validate_deribit_public_ws_smoke_config(_config(sample_limit=100)) == ()


def test_valid_public_aggregated_channel_accepted_by_config_validator():
    reasons = validate_deribit_public_ws_smoke_config(_config())

    assert reasons == ()


def test_mocked_valid_message_produces_accepted_quarantine_summary(monkeypatch):
    payload = _subscription_payload(change_id=10, event_time_ms=1_999)
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: ((payload, 2_000_000_000),),
    )

    result = run_deribit_public_ws_smoke_test(_config())

    assert result.accepted is True
    assert result.ws_url == DERIBIT_OFFICIAL_PUBLIC_WS_URL
    assert result.channels == (DERIBIT_DEFAULT_PUBLIC_CHANNEL,)
    assert result.message_count == 1
    assert result.rejection_reasons == ()
    assert result.sample_events[0].payload_sample["change_id"] == 10
    assert json.dumps(deribit_public_ws_smoke_result_to_dict(result), sort_keys=True)


def test_sample_limit_can_preserve_adjacent_raw_sequence_events(monkeypatch):
    payloads = tuple(
        (_subscription_payload(change_id=10 + offset, event_time_ms=1_999 + offset), 2_000_000_000 + offset)
        for offset in range(6)
    )
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: payloads,
    )

    result = run_deribit_public_ws_smoke_test(_config(sample_limit=6, max_messages=6))
    serialized = deribit_public_ws_smoke_result_to_dict(result)

    assert result.accepted is True
    assert result.message_count == 6
    assert len(result.sample_events) == 6
    assert len(serialized["sample_events"]) == 6
    assert [event.payload_sample["change_id"] for event in result.sample_events] == [10, 11, 12, 13, 14, 15]


def test_malformed_payload_rejects(monkeypatch):
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: (({"jsonrpc": "2.0", "method": "unexpected"}, 2_000_000_000),),
    )

    result = run_deribit_public_ws_smoke_test(_config())

    assert result.accepted is False
    assert "deribit_ws:message_malformed" in result.rejection_reasons


def test_stale_receive_lag_rejects(monkeypatch):
    payload = _subscription_payload(change_id=10, event_time_ms=1_000)
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: ((payload, 2_000_000_000),),
    )

    result = run_deribit_public_ws_smoke_test(_config(max_receive_lag_ms=5))

    assert result.accepted is False
    assert "deribit_ws:receive_lag_stale" in result.rejection_reasons


def test_sequence_gap_rejects_when_sequence_fields_exist(monkeypatch):
    first = _subscription_payload(change_id=10, event_time_ms=1_999)
    second = _subscription_payload(change_id=12, prev_change_id=9, event_time_ms=2_000)
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: ((first, 2_000_000_000), (second, 2_001_000_000)),
    )

    result = run_deribit_public_ws_smoke_test(_config())

    assert result.accepted is False
    assert "deribit_ws:sequence_gap" in result.rejection_reasons


def test_result_serializer_roundtrip(monkeypatch):
    payload = _subscription_payload(change_id=10, event_time_ms=1_999)
    monkeypatch.setattr(
        harness,
        "_receive_deribit_public_ws_messages",
        lambda config: ((payload, 2_000_000_000),),
    )
    result = run_deribit_public_ws_smoke_test(_config())

    restored = deribit_public_ws_smoke_result_from_dict(deribit_public_ws_smoke_result_to_dict(result))

    assert restored == result


def test_no_env_or_api_key_reads():
    for path in (MODULE_PATH, SCRIPT_PATH):
        text = path.read_text(encoding="utf-8").lower()
        assert "os.environ" not in text
        assert "getenv" not in text
        assert "api_key" not in text


def test_smoke_script_exposes_sample_limit_without_credentials_or_orders():
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "--sample-limit" in text
    assert "DERIBIT_PUBLIC_WS_DEFAULT_SAMPLE_EVENTS" in text
    assert "sample_limit=args.sample_limit" in text
    assert "DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION" in text
    assert "NO CREDENTIALS" in text
    lowered = text.lower()
    for forbidden in ("private/", "private_", "api_key", "api_secret", "create_order", "send_order"):
        assert forbidden not in lowered


def test_no_service_orchestrator_trading_or_risk_imports():
    forbidden_modules = {
        "crypto_core.service",
        "crypto_core.service.service_orchestrator",
        "crypto_core.risk",
        "crypto_core.execution",
        "crypto_core.strategy",
    }
    for path in (MODULE_PATH, SCRIPT_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        imports.update(
            node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        assert forbidden_modules.isdisjoint(imports)


def test_connector_ready_dialects_remains_empty():
    assert connector_ready_dialects() == ()


def test_registry_remains_unverified():
    spec = get_public_feed_dialect("deribit:l2_orderbook:placeholder")

    assert spec.verification_status.value == "unverified"
    assert spec.enabled_for_connector is False
    assert connector_ready_dialects() == ()


def test_operational_evidence_ready_remains_false_current_deribit_blocked():
    checklist = CHECKLIST_PATH.read_text(encoding="utf-8")
    result = OperationalEvidenceAcceptanceResult(
        accepted=False,
        venue_id=VenueId.DERIBIT,
        rejection_reasons=("operational_evidence:claim_review_rejected",),
    )

    assert "- `operational_status`: `BLOCKED`" in checklist
    assert "`connector_ready_dialects_expected`: `[]`" in checklist
    assert operational_evidence_acceptance_ready(result) is False


def test_lifecycle_and_session_live_remain_rejected():
    lifecycle = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(
        _execution_request()
    )
    execution = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.LIVE)).execute(_execution_request())

    assert lifecycle.approved is False
    assert lifecycle.rejection_reason == RejectionReason.LIVE_NOT_ENABLED
    assert execution.allowed is False
    assert execution.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _config(**overrides):
    values = {
        "operator_authorization": DERIBIT_PUBLIC_WS_OPERATOR_AUTHORIZATION,
    }
    values.update(overrides)
    return DeribitPublicWsSmokeConfig(**values)


def _subscription_payload(
    *,
    change_id: int,
    event_time_ms: int,
    prev_change_id: int | None = None,
) -> dict:
    data = {
        "type": "snapshot",
        "instrument_name": "BTC-PERPETUAL",
        "timestamp": event_time_ms,
        "change_id": change_id,
        "bids": [[50_000.0, 1.0]],
        "asks": [[50_010.0, 1.0]],
    }
    if prev_change_id is not None:
        data["prev_change_id"] = prev_change_id
    return {
        "jsonrpc": "2.0",
        "method": "subscription",
        "params": {
            "channel": DERIBIT_DEFAULT_PUBLIC_CHANNEL,
            "data": data,
        },
    }


def _execution_request() -> ExecutionRequest:
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=EdgeSignal(
                family=EdgeFamily.ORDER_FLOW_IMBALANCE,
                symbol="BTCUSDT",
                exchange="binance",
                direction=SignalDirection.BUY,
                confidence=0.5,
                score=0.5,
                evidence={"ofi": 0.5},
                timestamp_ns=100,
                is_valid=True,
                block_reason=None,
            ),
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
