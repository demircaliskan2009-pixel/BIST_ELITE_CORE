"""Tests for the backtest replay bridge (admitted decision -> existing replay-admission evaluator)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

from crypto_core.audit import (
    DecisionEvidenceRef,
    DecisionLedgerRecord,
    DecisionLedgerStage,
    build_strategy_spec_decision_record,
    build_validation_decision_record,
)
from crypto_core.data.requirements import DataRequirementValidationResult, default_perp_data_requirement_registry
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.backtest_admission import (
    BacktestAdmissionDecision,
    BacktestAdmissionStatus,
    backtest_admission_decision_to_dict,
)
from crypto_core.validation.backtest_replay_admission import (
    BacktestReplayAdmissionPolicy,
    BacktestReplayAdmissionStatus,
    BacktestReplayWindow,
)
from crypto_core.validation.backtest_replay_bridge import (
    BacktestReplayBridgeError,
    BacktestReplayBridgeResult,
    backtest_replay_bridge_result_to_dict,
    build_backtest_replay_bridge,
)
from crypto_core.validation.leakage_bias_repaint import LeakageBiasRepaintResult, LeakageBiasRepaintStatus
from crypto_core.validation.pit_parity import validate_strategy_data_requirements

_CORR = "corr:backtest-replay-bridge-001"
_LEDGER_CORR = "corr-backtest-replay-bridge-ledger"


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "bridge-s01",
        "strategy_version": "v1",
        "strategy_family": "microstructure",
        "edge_family": "order_flow_imbalance",
        "instrument_universe": ["BTCUSDT"],
        "market_type": "usdt_perp",
        "venue_assumptions": ["binance_usdm", "bybit_usdt_perp"],
        "timeframe": "1m",
        "bar_definition": "ohlcv",
        "entry_conditions": ["ofi > 0.5"],
        "exit_conditions": ["ofi < 0.1"],
        "invalidation_conditions": ["spread > 20bps"],
        "risk_caps": {"max_leverage": 3.0, "max_notional": 1000},
        "data_requirements": {
            "order_book": {"required": True},
            "funding_rate": {"required": True},
            "mark_price": {"required": True},
            "liquidation": {"required": True},
        },
        "feature_requirements": {"ofi_window": 20},
        "latency_sensitivity": "high",
        "funding_sensitivity": "medium",
        "fee_model_requirement": "maker_taker",
        "slippage_model_requirement": "book_impact_v1",
        "expected_regime": "volatile",
        "failure_modes": ["feed_drop"],
        "kill_switch_triggers": ["dtl_breach"],
        "telemetry_fields": ["edge_score", "risk_state"],
        "promotion_requirements": ["wf_pass", "pbo_pass"],
    }


def _valid_spec() -> StrategySpec:
    result = validate_strategy_spec(_strategy_payload())
    assert result.accepted is True
    assert result.spec is not None
    return result.spec


def _lbr_result() -> LeakageBiasRepaintResult:
    return LeakageBiasRepaintResult(
        accepted=True, status=LeakageBiasRepaintStatus.PASS, rejection_reasons=(), needs_research_reasons=()
    )


def _pit_result() -> DataRequirementValidationResult:
    result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry())
    assert result.accepted is True
    return result


def _records() -> tuple[DecisionLedgerRecord, DecisionLedgerRecord, DecisionLedgerRecord]:
    spec = _valid_spec()
    digest = strategy_spec_digest(spec)
    ref = (DecisionEvidenceRef(source_type="validation_result", digest="a" * 64, source_id="vr-1"),)
    strategy_record = build_strategy_spec_decision_record(spec, input_digest="b" * 64, correlation_id=_LEDGER_CORR)
    lbr_record = build_validation_decision_record(
        DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
        _lbr_result(),
        strategy_id=spec.strategy_id,
        strategy_digest=digest,
        input_digest="c" * 64,
        correlation_id=_LEDGER_CORR,
        evidence_refs=ref,
    )
    pit_record = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        _pit_result(),
        strategy_id=spec.strategy_id,
        strategy_digest=digest,
        input_digest="d" * 64,
        correlation_id=_LEDGER_CORR,
        evidence_refs=ref,
    )
    assert strategy_record.record is not None and lbr_record.record is not None and pit_record.record is not None
    return strategy_record.record, lbr_record.record, pit_record.record


def _policy() -> BacktestReplayAdmissionPolicy:
    return BacktestReplayAdmissionPolicy(
        event_time_ns_policy="event_time_ns",
        available_at_ns_policy="available_at_ns",
        finalized_at_ns_policy="finalized_at_ns",
        fee_assumption="maker_taker",
        slippage_assumption="book_impact_v1",
        funding_assumption="funding_curve_v1",
        metadata={"scope": "crypto_only"},
    )


def _admission(**overrides) -> BacktestAdmissionDecision:
    spec = _valid_spec()
    kwargs = {
        "schema_version": "backtest-admission.v1",
        "status": BacktestAdmissionStatus.ADMITTED,
        "admitted": True,
        "strategy_id": spec.strategy_id,
        "strategy_digest": strategy_spec_digest(spec),
        "bundle_status": "ACCEPTED",
        "bundle_digest": "f" * 64,
        "source_packet_digest": None,
        "decision_record_count": 3,
        "min_decision_records": 3,
        "require_source_packet": False,
        "require_accepted_bundle": True,
        "rejection_reasons": (),
        "needs_research_reasons": (),
        "correlation_id": "corr:admission-001",
        "admission_digest": "1" * 64,
    }
    kwargs.update(overrides)
    decision = BacktestAdmissionDecision(**kwargs)
    if "admission_digest" in overrides:
        return decision
    payload = backtest_admission_decision_to_dict(decision)
    payload.pop("admission_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(decision, admission_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _bridge(admission=None, **overrides):
    admission = _admission() if admission is None else admission
    kwargs = {
        "strategy_spec": _valid_spec(),
        "leakage_bias_repaint_result": _lbr_result(),
        "pit_parity_result": _pit_result(),
        "decision_ledger_records": _records(),
        "replay_source_id": "offline-replay-v1",
        "historical_data_source_id": "historical-perp-journal-v1",
        "replay_window": BacktestReplayWindow(start_ns=1_000, end_ns=2_000),
        "admission_policy": _policy(),
        "evidence_digest_by_stage": None,
        "metadata": {"scope": "crypto_only"},
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_backtest_replay_bridge(admission, **kwargs)


def test_admitted_decision_with_matching_evidence_accepted():
    admission = _admission()
    result = _bridge(admission)
    assert isinstance(result, BacktestReplayBridgeResult)
    assert result.status is BacktestReplayAdmissionStatus.ACCEPTED
    assert result.accepted is True
    assert result.admission_digest == admission.admission_digest
    assert result.replay_admission_result is not None
    assert result.replay_admission_result.accepted is True
    assert result.replay_admission_status == "ACCEPTED"
    assert set(result.replay_admission_result.decision_ledger_digests) == {
        "STRATEGY_SPEC",
        "LEAKAGE_BIAS_REPAINT",
        "PIT_PARITY",
    }
    assert len(result.bridge_digest) == 64
    assert result.paper_only is True


def test_stale_admission_digest_rejected_before_evaluator():
    admission = _admission()
    forged = replace(admission, bundle_digest="0" * 64)
    result = _bridge(forged)
    assert result.status is BacktestReplayAdmissionStatus.REJECTED
    assert result.accepted is False
    assert result.replay_admission_result is None
    assert "backtest_replay_bridge:admission_digest_mismatch" in result.rejection_reasons


def test_non_admitted_decision_rejects_before_evaluator():
    for admission in (
        _admission(status=BacktestAdmissionStatus.REJECTED, admitted=False),
        _admission(admitted=False),
    ):
        result = _bridge(admission)
        assert result.status is BacktestReplayAdmissionStatus.REJECTED
        assert result.replay_admission_result is None  # evaluator not reached
        assert "backtest_replay_bridge:admission_not_admitted" in result.rejection_reasons


def test_strategy_digest_mismatch_rejects():
    result = _bridge(_admission(strategy_digest="0" * 64))
    assert result.status is BacktestReplayAdmissionStatus.REJECTED
    assert result.replay_admission_result is None
    assert "backtest_replay_bridge:strategy_digest_mismatch" in result.rejection_reasons


def test_insufficient_ledger_evidence_blocks_before_evaluator():
    result = _bridge(decision_ledger_records=())
    assert result.status is BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE
    assert result.replay_admission_result is None
    assert "backtest_replay_bridge:ledger_evidence_insufficient" in result.rejection_reasons


def test_wrong_type_and_bad_inputs_raise():
    with pytest.raises(BacktestReplayBridgeError):
        build_backtest_replay_bridge(
            {"status": "ADMITTED"},  # type: ignore[arg-type]
            strategy_spec=_valid_spec(),
            leakage_bias_repaint_result=_lbr_result(),
            pit_parity_result=_pit_result(),
            decision_ledger_records=_records(),
            replay_source_id="offline-replay-v1",
            historical_data_source_id="historical-perp-journal-v1",
            replay_window=BacktestReplayWindow(start_ns=1_000, end_ns=2_000),
            admission_policy=_policy(),
            correlation_id=_CORR,
        )
    with pytest.raises(BacktestReplayBridgeError):
        _bridge(correlation_id="")


def test_replay_window_failure_delegated_to_evaluator():
    # Bridge gates pass; the invalid window is rejected by the existing evaluator (delegation proof).
    result = _bridge(replay_window=BacktestReplayWindow(start_ns=2_000, end_ns=1_000))
    assert result.status is BacktestReplayAdmissionStatus.REJECTED
    assert result.replay_admission_result is not None  # evaluator WAS reached
    assert any(reason.startswith("backtest_replay_admission:") for reason in result.rejection_reasons)


def test_forbidden_scope_in_raw_metadata_delegated_and_rejected():
    result = _bridge(replay_source_id="live_execution_feed")
    assert result.status is BacktestReplayAdmissionStatus.REJECTED
    assert result.replay_admission_result is not None
    assert any(reason.startswith("backtest_replay_admission:") for reason in result.rejection_reasons)


def test_deterministic_and_material_change_digest():
    first = _bridge()
    second = _bridge()
    assert first.bridge_digest == second.bridge_digest
    assert backtest_replay_bridge_result_to_dict(first) == backtest_replay_bridge_result_to_dict(second)
    changed = _bridge(_admission(admission_digest="2" * 64))
    assert changed.bridge_digest != first.bridge_digest


def test_immutable_and_no_plan_runtime_persistence_fields():
    result = _bridge()
    with pytest.raises(FrozenInstanceError):
        result.status = BacktestReplayAdmissionStatus.REJECTED  # type: ignore[misc]
    forbidden = {
        "order",
        "route",
        "venue",
        "exchange",
        "scheduler",
        "live",
        "plan",
        "runtime",
        "persistence",
        "store",
        "engine",
    }
    assert {field.name for field in fields(result)}.isdisjoint(forbidden)
    payload = backtest_replay_bridge_result_to_dict(result)
    assert payload["schema_version"] == "backtest-replay-bridge.v1"
    assert set(payload).isdisjoint(forbidden)
