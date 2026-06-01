from __future__ import annotations

import json

from crypto_core.audit import (
    DecisionEvidenceRef,
    DecisionLedgerRecord,
    DecisionLedgerStage,
    DecisionLedgerStatus,
    build_strategy_spec_decision_record,
    build_validation_decision_record,
    canonical_decision_ledger_json,
    decision_ledger_digest,
    decision_ledger_record_from_dict,
    decision_ledger_record_to_dict,
    validate_decision_ledger_record,
)
from crypto_core.data.requirements import default_perp_data_requirement_registry
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import LeakageBiasRepaintStatus, validate_strategy_data_requirements
from crypto_core.validation.leakage_bias_repaint import LeakageBiasRepaintResult


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "decision-ledger-s01",
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


def _evidence_ref() -> DecisionEvidenceRef:
    return DecisionEvidenceRef(source_type="validation_result", digest="a" * 64, source_id="lbr-result-v1")


def _strategy_record() -> DecisionLedgerRecord:
    spec = _valid_spec()
    result = build_strategy_spec_decision_record(
        spec,
        input_digest="b" * 64,
        correlation_id="corr-001",
    )
    assert result.accepted is True
    assert result.record is not None
    return result.record


def test_valid_strategy_spec_decision_record_accepted() -> None:
    record = _strategy_record()

    assert record.stage is DecisionLedgerStage.STRATEGY_SPEC
    assert record.status is DecisionLedgerStatus.ACCEPTED
    assert record.accepted is True
    assert record.strategy_id == "decision-ledger-s01"
    assert record.strategy_digest == strategy_spec_digest(_valid_spec())


def test_valid_strategy_spec_decision_record_canonical_json_stable() -> None:
    record = _strategy_record()
    loaded = decision_ledger_record_from_dict(decision_ledger_record_to_dict(record))

    assert loaded.accepted is True
    assert loaded.record is not None
    assert canonical_decision_ledger_json(record) == canonical_decision_ledger_json(loaded.record)
    assert json.loads(canonical_decision_ledger_json(record)) == decision_ledger_record_to_dict(record)


def test_valid_strategy_spec_decision_digest_stable() -> None:
    record = _strategy_record()
    loaded = decision_ledger_record_from_dict(decision_ledger_record_to_dict(record))

    assert loaded.accepted is True
    assert loaded.record is not None
    assert decision_ledger_digest(record) == decision_ledger_digest(loaded.record)


def test_valid_lbr_decision_record_requires_evidence_refs() -> None:
    lbr_result = LeakageBiasRepaintResult(
        accepted=True,
        status=LeakageBiasRepaintStatus.PASS,
        rejection_reasons=(),
        needs_research_reasons=(),
    )
    valid = build_validation_decision_record(
        DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
        lbr_result,
        strategy_id="decision-ledger-s01",
        strategy_digest="c" * 64,
        input_digest="d" * 64,
        correlation_id="corr-001",
        evidence_refs=(_evidence_ref(),),
    )
    missing_ref = build_validation_decision_record(
        DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
        lbr_result,
        strategy_id="decision-ledger-s01",
        strategy_digest="c" * 64,
        input_digest="d" * 64,
        correlation_id="corr-001",
    )

    assert valid.accepted is True
    assert valid.record is not None
    assert missing_ref.accepted is False
    assert "decision_ledger:evidence_refs_missing" in missing_ref.rejection_reasons


def test_valid_pit_parity_decision_record_preserves_output_digest() -> None:
    pit_result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry())
    first = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        pit_result,
        strategy_id="decision-ledger-s01",
        strategy_digest="c" * 64,
        input_digest="d" * 64,
        correlation_id="corr-001",
        evidence_refs=(_evidence_ref(),),
    )
    second = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        pit_result,
        strategy_id="decision-ledger-s01",
        strategy_digest="c" * 64,
        input_digest="d" * 64,
        correlation_id="corr-001",
        evidence_refs=(_evidence_ref(),),
    )

    assert first.accepted is True
    assert second.accepted is True
    assert first.record is not None and second.record is not None
    assert first.record.output_digest == second.record.output_digest
    assert first.record.accepted is True


def test_accepted_true_with_rejection_reason_rejected() -> None:
    result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-001",
        accepted=True,
        rejection_reasons=("z_reason",),
    )

    assert result.accepted is False
    assert "decision_ledger:accepted_with_rejection_reasons" in result.rejection_reasons


def test_accepted_true_with_needs_research_rejected() -> None:
    result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-001",
        accepted=True,
        needs_research_reasons=("needs_calibration",),
    )

    assert result.accepted is False
    assert "decision_ledger:accepted_with_needs_research_reasons" in result.rejection_reasons


def test_missing_strategy_digest_rejected() -> None:
    result = build_strategy_spec_decision_record(
        None,
        input_digest="b" * 64,
        correlation_id="corr-001",
        strategy_id="decision-ledger-s01",
        output_digest="c" * 64,
        accepted=False,
    )

    assert result.accepted is False
    assert "decision_ledger:strategy_digest_missing" in result.rejection_reasons


def test_unknown_stage_rejected() -> None:
    payload = decision_ledger_record_to_dict(_strategy_record())
    payload["stage"] = "UNKNOWN"

    result = decision_ledger_record_from_dict(payload)

    assert result.accepted is False
    assert "decision_ledger:stage_unknown" in result.rejection_reasons


def test_unknown_status_rejected() -> None:
    payload = decision_ledger_record_to_dict(_strategy_record())
    payload["status"] = "UNKNOWN"

    result = decision_ledger_record_from_dict(payload)

    assert result.accepted is False
    assert "decision_ledger:status_unknown" in result.rejection_reasons


def test_missing_evidence_refs_for_lbr_and_pit_rejected() -> None:
    lbr_result = LeakageBiasRepaintResult(
        accepted=True,
        status=LeakageBiasRepaintStatus.PASS,
        rejection_reasons=(),
        needs_research_reasons=(),
    )
    pit_result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry())

    for stage, validation_result in (
        (DecisionLedgerStage.LEAKAGE_BIAS_REPAINT, lbr_result),
        (DecisionLedgerStage.PIT_PARITY, pit_result),
    ):
        ledger_result = build_validation_decision_record(
            stage,
            validation_result,
            strategy_id="decision-ledger-s01",
            strategy_digest="c" * 64,
            input_digest="d" * 64,
            correlation_id="corr-001",
        )
        assert ledger_result.accepted is False
        assert "decision_ledger:evidence_refs_missing" in ledger_result.rejection_reasons


def test_bist_metadata_leakage_rejected() -> None:
    result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-001",
        metadata={"source": {"system": "Matriks"}},
    )

    assert result.accepted is False
    assert "decision_ledger:bist_scope_leakage" in result.rejection_reasons


def test_forbidden_live_private_order_scheduler_keys_rejected() -> None:
    result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-001",
        metadata={
            "scheduler": "enabled",
            "private_api": "x",
            "order_router": "v1",
            "auto_loop": True,
            "shadow_live_execution": False,
            "credentials": "bad",
            "live": "bad",
        },
    )

    assert result.accepted is False
    assert "decision_ledger:forbidden_field_scheduler" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_private_api" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_order_router" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_auto_loop" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_shadow_live_execution" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_credentials" in result.rejection_reasons
    assert "decision_ledger:forbidden_field_live" in result.rejection_reasons


def test_runtime_timestamp_policy_rejected() -> None:
    for metadata in (
        {"timestamp_policy": "now"},
        {"timestamp_policy": "wall_clock"},
        {"timestamp_policy": "datetime.now"},
        {"timestamp_policy": "utcnow"},
    ):
        result = build_strategy_spec_decision_record(
            _valid_spec(),
            input_digest="b" * 64,
            correlation_id="corr-001",
            metadata=metadata,
        )
        assert result.accepted is False
        assert "decision_ledger:metadata_runtime_timestamp_forbidden" in result.rejection_reasons


def test_digest_changes_when_previous_record_digest_changes() -> None:
    first = _strategy_record()
    second_result = build_strategy_spec_decision_record(
        _valid_spec(),
        input_digest="b" * 64,
        correlation_id="corr-001",
        previous_record_digest="0" * 64,
    )

    assert second_result.accepted is True
    assert second_result.record is not None
    assert decision_ledger_digest(first) != decision_ledger_digest(second_result.record)


def test_from_dict_malformed_payload_fails_closed() -> None:
    result = decision_ledger_record_from_dict({"not": "a ledger"})

    assert result.accepted is False
    assert result.record is None
    assert result.rejection_reasons


def test_reason_ordering_deterministic() -> None:
    result = build_strategy_spec_decision_record(
        None,
        input_digest="b" * 64,
        correlation_id="corr-001",
        strategy_id="decision-ledger-s01",
        strategy_digest="c" * 64,
        output_digest="d" * 64,
        rejection_reasons=("z_reason", "a_reason", "z_reason"),
    )

    assert result.accepted is True
    assert result.record is not None
    assert result.record.rejection_reasons == ("a_reason", "z_reason")


def test_to_dict_from_dict_round_trip_deterministic() -> None:
    record = _strategy_record()
    payload = decision_ledger_record_to_dict(record)
    loaded = decision_ledger_record_from_dict(payload)

    assert loaded.accepted is True
    assert loaded.record is not None
    assert decision_ledger_record_to_dict(loaded.record) == payload
    assert canonical_decision_ledger_json(loaded.record) == canonical_decision_ledger_json(record)


def test_validate_direct_record_contract() -> None:
    record = _strategy_record()

    result = validate_decision_ledger_record(record)

    assert result.accepted is True
    assert result.record == record
