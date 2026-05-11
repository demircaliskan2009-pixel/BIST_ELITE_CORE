from __future__ import annotations

import json

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.authorization import (
    LIVE_AUTH_CREDENTIAL_ATTESTATION_MISSING,
    LIVE_AUTH_EXPIRED_OR_INVALID_WINDOW,
    LIVE_AUTH_INVALID_ALLOCATION_TIER,
    LIVE_AUTH_INVALID_NOTIONAL_LIMITS,
    LIVE_AUTH_KILL_SWITCH_NOT_CLEAR,
    LIVE_AUTH_NO_TRADE_GUARD_NOT_CLEAR,
    LIVE_AUTH_RISK_GOVERNANCE_NOT_CLEAR,
    LIVE_AUTH_STAGE4_HASH_MISSING,
    LIVE_AUTH_STAGE4_NOT_PASSED,
    LIVE_AUTH_STAGE5_HASH_MISSING,
    LIVE_AUTH_STAGE5_NOT_PASSED,
    LIVE_AUTH_SYMBOL_ALLOWLIST_MISSING,
    LIVE_AUTH_VALIDATION_NOT_READY,
    LIVE_AUTH_VENUE_ALLOWLIST_MISSING,
    LiveExecutionAuthorization,
    LiveExecutionAuthorizationCorruptError,
    build_live_execution_authorization,
    live_execution_authorization_from_dict,
    live_execution_authorization_ready,
    live_execution_authorization_rejection_reasons,
    live_execution_authorization_to_dict,
)
from crypto_core.execution.engine import ExecutionConfig, ExecutionEngine
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState

_AS_OF_NS = 1_000
_EXPIRES_AT_NS = 2_000


def _auth(**overrides: object) -> LiveExecutionAuthorization:
    values: dict[str, object] = {
        "authorization_id": "auth-20p",
        "sleeve_id": "sleeve-20p",
        "edge_id": "edge-20p",
        "as_of_ns": _AS_OF_NS,
        "expires_at_ns": _EXPIRES_AT_NS,
        "validation_ready": True,
        "validation_result_hash": "validation-hash-20p",
        "stage4_comparison_hash": "stage4-hash-20p",
        "stage4_passed": True,
        "stage5_gate_hash": "stage5-hash-20p",
        "stage5_passed": True,
        "stage5_runtime_evidence_record_id": "stage5-record-20p",
        "operator_approval_reference": "operator-approval-20p",
        "credential_attestation_reference": "credential-attestation-20p",
        "kill_switch_clear": True,
        "risk_governance_clear": True,
        "no_trade_guard_clear": True,
        "allocation_tier_pct": 10.0,
        "max_live_notional_usd": 500.0,
        "max_order_notional_usd": 50.0,
        "venue_allowlist": ("binance",),
        "symbol_allowlist": ("BTCUSDT",),
        "margin_mode": "isolated",
        "position_mode": "one_way",
        "decision_pack_hash": "decision-pack-hash-20p",
        "audit_id": "audit-20p",
    }
    values.update(overrides)
    return build_live_execution_authorization(**values)  # type: ignore[arg-type]


def _raw_default_auth() -> LiveExecutionAuthorization:
    return LiveExecutionAuthorization(
        authorization_id="auth-20p",
        sleeve_id="sleeve-20p",
        edge_id="edge-20p",
        as_of_ns=_AS_OF_NS,
        expires_at_ns=_EXPIRES_AT_NS,
        validation_ready=False,
        validation_result_hash=None,
        stage4_comparison_hash=None,
        stage4_passed=False,
        stage5_gate_hash=None,
        stage5_passed=False,
        stage5_runtime_evidence_record_id=None,
        operator_approval_reference=None,
        credential_attestation_reference=None,
        kill_switch_clear=False,
        risk_governance_clear=False,
        no_trade_guard_clear=False,
        allocation_tier_pct=0.0,
        max_live_notional_usd=0.0,
        max_order_notional_usd=0.0,
        venue_allowlist=(),
        symbol_allowlist=(),
        margin_mode=None,
        position_mode=None,
        decision_pack_hash=None,
        audit_id="audit-20p",
    )


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
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
    )
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
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )


def test_missing_authorization_is_not_ready():
    assert live_execution_authorization_ready(None) is False
    assert live_execution_authorization_ready(object()) is False  # type: ignore[arg-type]


def test_default_authorization_is_fail_closed():
    auth = _raw_default_auth()

    assert auth.passed is False
    assert live_execution_authorization_ready(auth) is False
    assert LIVE_AUTH_VALIDATION_NOT_READY in live_execution_authorization_rejection_reasons(auth)


def test_full_valid_authorization_is_ready():
    auth = _auth()

    assert auth.passed is True
    assert live_execution_authorization_rejection_reasons(auth) == ()
    assert live_execution_authorization_ready(auth, now_ns=_AS_OF_NS + 1) is True


def test_missing_validation_blocks():
    auth = _auth(validation_ready=False)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_VALIDATION_NOT_READY,)


def test_missing_stage4_blocks():
    auth = _auth(stage4_passed=False, stage4_comparison_hash=None)

    assert auth.passed is False
    assert LIVE_AUTH_STAGE4_NOT_PASSED in auth.rejection_reasons
    assert LIVE_AUTH_STAGE4_HASH_MISSING in auth.rejection_reasons


def test_missing_stage5_blocks():
    auth = _auth(stage5_passed=False, stage5_gate_hash=None)

    assert auth.passed is False
    assert LIVE_AUTH_STAGE5_NOT_PASSED in auth.rejection_reasons
    assert LIVE_AUTH_STAGE5_HASH_MISSING in auth.rejection_reasons


def test_missing_operator_approval_blocks():
    auth = _auth(operator_approval_reference=None)

    assert auth.passed is False
    assert auth.rejection_reasons == ("live_auth:operator_approval_missing",)


def test_missing_credential_attestation_blocks_without_env_reads(monkeypatch):
    monkeypatch.setenv("CRYPTO_CORE_FAKE_API_KEY", "must-not-be-read")
    before = dict(__import__("os").environ)

    auth = _auth(credential_attestation_reference=None)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_CREDENTIAL_ATTESTATION_MISSING,)
    assert dict(__import__("os").environ) == before


def test_kill_switch_not_clear_blocks():
    auth = _auth(kill_switch_clear=False)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_KILL_SWITCH_NOT_CLEAR,)


def test_risk_governance_not_clear_blocks():
    auth = _auth(risk_governance_clear=False)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_RISK_GOVERNANCE_NOT_CLEAR,)


def test_no_trade_guard_not_clear_blocks():
    auth = _auth(no_trade_guard_clear=False)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_NO_TRADE_GUARD_NOT_CLEAR,)


def test_invalid_allocation_tier_blocks():
    auth = _auth(allocation_tier_pct=5.0)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_INVALID_ALLOCATION_TIER,)


def test_invalid_notional_limits_block():
    auth = _auth(max_live_notional_usd=100.0, max_order_notional_usd=200.0)

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_INVALID_NOTIONAL_LIMITS,)


def test_empty_venue_allowlist_blocks():
    auth = _auth(venue_allowlist=())

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_VENUE_ALLOWLIST_MISSING,)


def test_empty_symbol_allowlist_blocks():
    auth = _auth(symbol_allowlist=())

    assert auth.passed is False
    assert auth.rejection_reasons == (LIVE_AUTH_SYMBOL_ALLOWLIST_MISSING,)


def test_expired_authorization_not_ready():
    auth = _auth()

    assert live_execution_authorization_ready(auth, now_ns=_EXPIRES_AT_NS + 1) is False

    invalid_window = _auth(expires_at_ns=_AS_OF_NS)
    assert invalid_window.passed is False
    assert invalid_window.rejection_reasons == (LIVE_AUTH_EXPIRED_OR_INVALID_WINDOW,)


def test_to_dict_from_dict_roundtrip_json_safe():
    auth = _auth()
    payload = live_execution_authorization_to_dict(auth)

    json.dumps(payload)
    assert payload["venue_allowlist"] == ["binance"]
    assert payload["symbol_allowlist"] == ["BTCUSDT"]

    restored = live_execution_authorization_from_dict(payload)
    assert restored == auth


def test_from_dict_rejects_non_dict():
    with pytest.raises(LiveExecutionAuthorizationCorruptError, match="payload must be a dict"):
        live_execution_authorization_from_dict(("not", "a", "dict"))


def test_from_dict_rejects_missing_required_fields():
    payload = live_execution_authorization_to_dict(_auth())
    payload.pop("audit_id")

    with pytest.raises(LiveExecutionAuthorizationCorruptError, match="audit_id"):
        live_execution_authorization_from_dict(payload)


def test_from_dict_rejects_optimistic_passed_with_missing_evidence():
    payload = live_execution_authorization_to_dict(_auth())
    payload["stage4_comparison_hash"] = None
    payload["passed"] = True

    with pytest.raises(LiveExecutionAuthorizationCorruptError, match="claims passed=True"):
        live_execution_authorization_from_dict(payload)


def test_no_env_or_credential_reads(monkeypatch):
    monkeypatch.setenv("CRYPTO_CORE_FAKE_SECRET", "must-not-be-read")
    before = dict(__import__("os").environ)

    auth = _auth(credential_attestation_reference="credential-reference-only")
    payload = live_execution_authorization_to_dict(auth)

    assert "api_key" not in payload
    assert "secret" not in payload
    assert "token" not in payload
    assert dict(__import__("os").environ) == before


def test_live_execution_lifecycle_still_rejects_live_mode():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED
    assert result.final_state == "REJECTED"


def test_paper_or_dry_run_behavior_unchanged_if_authorization_module_exists():
    decision = ExecutionEngine(ExecutionConfig(mode=ExecutionMode.DRY_RUN)).execute(_execution_request())

    assert decision.allowed is True
    assert decision.mode == ExecutionMode.DRY_RUN
    assert decision.rejection_reason is None


def test_deterministic_replay_same_input_same_output():
    first = live_execution_authorization_to_dict(_auth())
    second = live_execution_authorization_to_dict(_auth())

    assert first == second
