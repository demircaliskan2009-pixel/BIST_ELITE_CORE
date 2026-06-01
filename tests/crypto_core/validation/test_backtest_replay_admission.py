from __future__ import annotations

from dataclasses import replace

from crypto_core.audit import (
    DecisionEvidenceRef,
    DecisionLedgerRecord,
    DecisionLedgerStage,
    build_strategy_spec_decision_record,
    build_validation_decision_record,
    decision_ledger_digest,
    decision_ledger_record_to_dict,
)
from crypto_core.data.requirements import DataRequirementValidationResult, default_perp_data_requirement_registry
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, strategy_spec_to_dict, validate_strategy_spec
from crypto_core.validation import (
    BacktestReplayAdmissionInput,
    BacktestReplayAdmissionPolicy,
    BacktestReplayAdmissionStatus,
    BacktestReplayWindow,
    LeakageBiasRepaintStatus,
    backtest_replay_admission_digest,
    backtest_replay_admission_from_dict,
    backtest_replay_admission_to_dict,
    canonical_backtest_replay_admission_json,
    evaluate_backtest_replay_admission,
    validate_strategy_data_requirements,
)
from crypto_core.validation.leakage_bias_repaint import LeakageBiasRepaintResult


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "backtest-replay-s01",
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


def _lbr_result(
    *,
    status: LeakageBiasRepaintStatus = LeakageBiasRepaintStatus.PASS,
    rejection_reasons: tuple[str, ...] = (),
    needs_research_reasons: tuple[str, ...] = (),
) -> LeakageBiasRepaintResult:
    return LeakageBiasRepaintResult(
        accepted=status is LeakageBiasRepaintStatus.PASS and not rejection_reasons and not needs_research_reasons,
        status=status,
        rejection_reasons=rejection_reasons,
        needs_research_reasons=needs_research_reasons,
    )


def _pit_result() -> DataRequirementValidationResult:
    result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry())
    assert result.accepted is True
    return result


def _evidence_ref() -> DecisionEvidenceRef:
    return DecisionEvidenceRef(source_type="validation_result", digest="a" * 64, source_id="validation-result-v1")


def _records(
    spec: StrategySpec | None = None,
) -> tuple[DecisionLedgerRecord, DecisionLedgerRecord, DecisionLedgerRecord]:
    active_spec = _valid_spec() if spec is None else spec
    digest = strategy_spec_digest(active_spec)
    strategy_record = build_strategy_spec_decision_record(
        active_spec,
        input_digest="b" * 64,
        correlation_id="corr-backtest-replay-001",
    )
    lbr_record = build_validation_decision_record(
        DecisionLedgerStage.LEAKAGE_BIAS_REPAINT,
        _lbr_result(),
        strategy_id=active_spec.strategy_id,
        strategy_digest=digest,
        input_digest="c" * 64,
        correlation_id="corr-backtest-replay-001",
        evidence_refs=(_evidence_ref(),),
    )
    pit_record = build_validation_decision_record(
        DecisionLedgerStage.PIT_PARITY,
        _pit_result(),
        strategy_id=active_spec.strategy_id,
        strategy_digest=digest,
        input_digest="d" * 64,
        correlation_id="corr-backtest-replay-001",
        evidence_refs=(_evidence_ref(),),
    )
    assert strategy_record.accepted and strategy_record.record is not None
    assert lbr_record.accepted and lbr_record.record is not None
    assert pit_record.accepted and pit_record.record is not None
    return strategy_record.record, lbr_record.record, pit_record.record


def _policy(**overrides: object) -> BacktestReplayAdmissionPolicy:
    values = {
        "event_time_ns_policy": "event_time_ns",
        "available_at_ns_policy": "available_at_ns",
        "finalized_at_ns_policy": "finalized_at_ns",
        "fee_assumption": "maker_taker",
        "slippage_assumption": "book_impact_v1",
        "funding_assumption": "funding_curve_v1",
        "metadata": {"scope": "crypto_only"},
    }
    values.update(overrides)
    return BacktestReplayAdmissionPolicy(**values)


def _admission_input(**overrides: object) -> BacktestReplayAdmissionInput:
    values = {
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
    }
    values.update(overrides)
    return BacktestReplayAdmissionInput(**values)


def test_valid_fully_accepted_admission_passes() -> None:
    result = evaluate_backtest_replay_admission(_admission_input())

    assert result.accepted is True
    assert result.status is BacktestReplayAdmissionStatus.ACCEPTED
    assert result.rejection_reasons == ()
    assert result.needs_research_reasons == ()
    assert set(result.decision_ledger_digests) == {"STRATEGY_SPEC", "LEAKAGE_BIAS_REPAINT", "PIT_PARITY"}


def test_raw_strategy_spec_mapping_path_passes() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(strategy_spec=strategy_spec_to_dict(_valid_spec())))

    assert result.accepted is True


def test_invalid_strategy_spec_rejects() -> None:
    payload = _strategy_payload()
    del payload["strategy_id"]

    result = evaluate_backtest_replay_admission(_admission_input(strategy_spec=payload))

    assert result.accepted is False
    assert "backtest_replay_admission:strategy_spec:strategy_spec:strategy_id_missing" in result.rejection_reasons


def test_lbr_rejected_rejects() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            leakage_bias_repaint_result=_lbr_result(
                status=LeakageBiasRepaintStatus.REJECT,
                rejection_reasons=("leakage_bias_repaint:test_rejection",),
            )
        )
    )

    assert result.accepted is False
    assert "backtest_replay_admission:lbr_not_accepted" in result.rejection_reasons


def test_lbr_needs_research_rejects() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            leakage_bias_repaint_result=_lbr_result(
                status=LeakageBiasRepaintStatus.NEEDS_RESEARCH,
                needs_research_reasons=("leakage_bias_repaint:needs_calibration",),
            )
        )
    )

    assert result.accepted is False
    assert result.status is BacktestReplayAdmissionStatus.NEEDS_RESEARCH
    assert result.needs_research_reasons


def test_lbr_insufficient_evidence_rejects() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            leakage_bias_repaint_result=_lbr_result(
                status=LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE,
                rejection_reasons=("leakage_bias_repaint:insufficient_evidence:missing_bars",),
            )
        )
    )

    assert result.accepted is False
    assert result.status is BacktestReplayAdmissionStatus.INSUFFICIENT_EVIDENCE


def test_pit_rejected_rejects() -> None:
    pit = DataRequirementValidationResult(
        accepted=False,
        registry=None,
        rejection_reasons=("pit_parity:test_rejection",),
        needs_research_reasons=(),
    )

    result = evaluate_backtest_replay_admission(_admission_input(pit_parity_result=pit))

    assert result.accepted is False
    assert "backtest_replay_admission:pit_parity:pit_parity:test_rejection" in result.rejection_reasons


def test_pit_needs_research_rejects() -> None:
    pit = DataRequirementValidationResult(
        accepted=False,
        registry=default_perp_data_requirement_registry(),
        rejection_reasons=(),
        needs_research_reasons=("pit_parity:needs_research:missing_source_review",),
    )

    result = evaluate_backtest_replay_admission(_admission_input(pit_parity_result=pit))

    assert result.accepted is False
    assert result.status is BacktestReplayAdmissionStatus.NEEDS_RESEARCH
    assert result.needs_research_reasons


def test_missing_strategy_spec_ledger_record_rejects() -> None:
    _, lbr_record, pit_record = _records()

    result = evaluate_backtest_replay_admission(_admission_input(decision_ledger_records=(lbr_record, pit_record)))

    assert "backtest_replay_admission:decision_ledger_missing_stage:STRATEGY_SPEC" in result.rejection_reasons


def test_missing_lbr_ledger_record_rejects() -> None:
    strategy_record, _, pit_record = _records()

    result = evaluate_backtest_replay_admission(_admission_input(decision_ledger_records=(strategy_record, pit_record)))

    assert "backtest_replay_admission:decision_ledger_missing_stage:LEAKAGE_BIAS_REPAINT" in result.rejection_reasons


def test_missing_pit_ledger_record_rejects() -> None:
    strategy_record, lbr_record, _ = _records()

    result = evaluate_backtest_replay_admission(_admission_input(decision_ledger_records=(strategy_record, lbr_record)))

    assert "backtest_replay_admission:decision_ledger_missing_stage:PIT_PARITY" in result.rejection_reasons


def test_ledger_stage_mismatch_rejects() -> None:
    strategy_record, lbr_record, _ = _records()

    result = evaluate_backtest_replay_admission(
        _admission_input(decision_ledger_records=(strategy_record, lbr_record, lbr_record))
    )

    assert "backtest_replay_admission:decision_ledger_stage_duplicate:LEAKAGE_BIAS_REPAINT" in result.rejection_reasons


def test_ledger_strategy_digest_mismatch_rejects() -> None:
    strategy_record, lbr_record, pit_record = _records()
    bad_lbr = replace(lbr_record, strategy_digest="0" * 64)

    result = evaluate_backtest_replay_admission(
        _admission_input(decision_ledger_records=(strategy_record, bad_lbr, pit_record))
    )

    assert "backtest_replay_admission:strategy_digest_mismatch:LEAKAGE_BIAS_REPAINT" in result.rejection_reasons


def test_invalid_ledger_record_rejects() -> None:
    strategy_record, lbr_record, pit_record = _records()
    invalid = replace(strategy_record, accepted=True, rejection_reasons=("bad",))

    result = evaluate_backtest_replay_admission(
        _admission_input(decision_ledger_records=(invalid, lbr_record, pit_record))
    )

    assert any("decision_ledger:accepted_with_rejection_reasons" in reason for reason in result.rejection_reasons)


def test_missing_replay_source_id_rejects() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(replay_source_id=""))

    assert "backtest_replay_admission:replay_source_id_missing" in result.rejection_reasons


def test_missing_historical_data_source_id_rejects() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(historical_data_source_id=""))

    assert "backtest_replay_admission:historical_data_source_id_missing" in result.rejection_reasons


def test_invalid_replay_window_rejects() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(replay_window=BacktestReplayWindow(2_000, 1_000)))

    assert "backtest_replay_admission:replay_window_end_not_after_start" in result.rejection_reasons


def test_missing_timestamp_policy_rejects() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(admission_policy=_policy(event_time_ns_policy="")))

    assert "backtest_replay_admission:event_time_ns_policy_missing" in result.rejection_reasons


def test_missing_fee_slippage_funding_assumptions_rejects() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            admission_policy=_policy(fee_assumption="", slippage_assumption="none", funding_assumption="0")
        )
    )

    assert "backtest_replay_admission:fee_assumption_missing" in result.rejection_reasons
    assert "backtest_replay_admission:slippage_assumption_missing" in result.rejection_reasons
    assert "backtest_replay_admission:funding_assumption_missing" in result.rejection_reasons


def test_optional_evidence_digest_mismatch_rejects() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(evidence_digest_by_stage={DecisionLedgerStage.STRATEGY_SPEC: "0" * 64})
    )

    assert "backtest_replay_admission:evidence_digest_mismatch:STRATEGY_SPEC" in result.rejection_reasons


def test_optional_evidence_digest_match_passes() -> None:
    strategy_record, _, _ = _records()

    result = evaluate_backtest_replay_admission(
        _admission_input(
            decision_ledger_records=_records(),
            evidence_digest_by_stage={DecisionLedgerStage.STRATEGY_SPEC: decision_ledger_digest(strategy_record)},
        )
    )

    assert result.accepted is True
    assert result.evidence_digest_by_stage["STRATEGY_SPEC"] == decision_ledger_digest(strategy_record)


def test_bist_leakage_rejects_recursively() -> None:
    result = evaluate_backtest_replay_admission(_admission_input(metadata={"nested": ["Matriks", {"scope": "Borsa"}]}))

    assert "backtest_replay_admission:bist_scope_leakage" in result.rejection_reasons


def test_forbidden_live_private_order_scheduler_keys_reject_recursively() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            metadata={
                "scheduler": "enabled",
                "private_api": "x",
                "order_router": "v1",
                "auto_loop": True,
                "shadow_live_execution": False,
                "credentials": "bad",
                "live": "bad",
            }
        )
    )

    assert "backtest_replay_admission:forbidden_field_scheduler" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_private_api" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_order_router" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_auto_loop" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_shadow_live_execution" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_credentials" in result.rejection_reasons
    assert "backtest_replay_admission:forbidden_field_live" in result.rejection_reasons


def test_malformed_from_dict_payload_fails_closed() -> None:
    result = backtest_replay_admission_from_dict(object())  # type: ignore[arg-type]

    assert result.accepted is False
    assert result.status is BacktestReplayAdmissionStatus.REJECTED
    assert "backtest_replay_admission:payload_malformed" in result.rejection_reasons


def test_rejection_ordering_deterministic() -> None:
    result = evaluate_backtest_replay_admission(
        _admission_input(
            replay_source_id="",
            historical_data_source_id="",
            admission_policy=_policy(event_time_ns_policy="", fee_assumption=""),
            metadata={"z": "scheduler", "a": "bist"},
        )
    )

    assert result.rejection_reasons == tuple(sorted(set(result.rejection_reasons)))


def test_canonical_json_stable() -> None:
    first = evaluate_backtest_replay_admission(_admission_input())
    second = evaluate_backtest_replay_admission(_admission_input())

    assert canonical_backtest_replay_admission_json(first) == canonical_backtest_replay_admission_json(second)
    assert backtest_replay_admission_to_dict(first) == backtest_replay_admission_to_dict(second)


def test_digest_stable() -> None:
    first = evaluate_backtest_replay_admission(_admission_input())
    second = evaluate_backtest_replay_admission(_admission_input())

    assert backtest_replay_admission_digest(first) == backtest_replay_admission_digest(second)


def test_result_from_dict_round_trip() -> None:
    result = evaluate_backtest_replay_admission(_admission_input())
    payload = backtest_replay_admission_to_dict(result)
    loaded = backtest_replay_admission_from_dict(payload)

    assert loaded == result


def test_raw_lbr_dict_path_passes() -> None:
    lbr_payload = {
        "accepted": True,
        "status": LeakageBiasRepaintStatus.PASS.value,
        "rejection_reasons": [],
        "needs_research_reasons": [],
    }

    result = evaluate_backtest_replay_admission(_admission_input(leakage_bias_repaint_result=lbr_payload))

    assert result.accepted is True


def test_invalid_ledger_mapping_rejects() -> None:
    strategy_record, lbr_record, pit_record = _records()
    payload = decision_ledger_record_to_dict(strategy_record)
    payload["stage"] = "UNKNOWN"

    result = evaluate_backtest_replay_admission(
        _admission_input(decision_ledger_records=(payload, lbr_record, pit_record))
    )

    assert any("decision_ledger:stage_unknown" in reason for reason in result.rejection_reasons)
