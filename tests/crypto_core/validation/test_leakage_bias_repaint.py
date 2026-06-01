from __future__ import annotations

import json

from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation import (
    LeakageBiasRepaintInput,
    LeakageBiasRepaintStatus,
    ValidationFeatureTimestamp,
    ValidationFundingObservation,
    ValidationIndicatorPolicy,
    evaluate_leakage_bias_repaint,
    leakage_bias_repaint_result_from_dict,
    leakage_bias_repaint_result_to_dict,
)


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "validator-s01",
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
        "data_requirements": {"book_depth": 10},
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


def _base_input(*, strategy_spec: StrategySpec | dict[str, object] | None = None) -> LeakageBiasRepaintInput:
    return LeakageBiasRepaintInput(
        strategy_spec=_valid_spec() if strategy_spec is None else strategy_spec,
        decision_timestamp_ns=1_000,
        pit_policy={"mode": "strict", "point_in_time": True},
        feature_timestamps=(
            ValidationFeatureTimestamp(
                feature_name="ofi_20",
                event_time_ns=990,
                available_at_ns=995,
                finalized_at_ns=995,
                is_candle_or_bar_derived=True,
                uses_current_bar=False,
            ),
        ),
        funding_observations=(
            ValidationFundingObservation(
                venue="binance_usdm",
                event_time_ns=980,
                available_at_ns=985,
                finalized_at_ns=990,
                final_rate=0.0001,
            ),
        ),
        indicator_policies=(
            ValidationIndicatorPolicy(
                indicator_name="ema_cross",
                repaint_risk=False,
                confirmation_rule=None,
            ),
        ),
        payload={"source": "crypto"},
        metadata={"scope": "crypto_only"},
        fee_assumption="maker_taker",
        slippage_assumption="book_impact_v1",
        funding_assumption="funding_curve_v1",
    )


def test_valid_finalized_pit_payload_passes() -> None:
    result = evaluate_leakage_bias_repaint(_base_input())

    assert result.accepted is True
    assert result.status is LeakageBiasRepaintStatus.PASS
    assert result.rejection_reasons == ()
    assert result.needs_research_reasons == ()


def test_valid_raw_strategy_spec_mapping_path_passes() -> None:
    result = evaluate_leakage_bias_repaint(_base_input(strategy_spec=_strategy_payload()))

    assert result.status is LeakageBiasRepaintStatus.PASS
    assert result.accepted is True


def test_invalid_strategy_spec_mapping_rejects_with_prefixed_reasons() -> None:
    bad_spec = _strategy_payload()
    del bad_spec["strategy_id"]

    result = evaluate_leakage_bias_repaint(_base_input(strategy_spec=bad_spec))

    assert result.accepted is False
    assert result.status is LeakageBiasRepaintStatus.REJECT
    assert "leakage_bias_repaint:strategy_spec:strategy_spec:strategy_id_missing" in result.rejection_reasons


def test_feature_event_time_after_decision_rejects() -> None:
    input_ = _base_input()
    input_ = LeakageBiasRepaintInput(
        **{**input_.__dict__, "feature_timestamps": (ValidationFeatureTimestamp("ofi", 1001, 999, 999, True),)}
    )

    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:feature_event_time_after_decision" in result.rejection_reasons


def test_feature_available_at_after_decision_rejects() -> None:
    input_ = _base_input()
    input_ = LeakageBiasRepaintInput(
        **{**input_.__dict__, "feature_timestamps": (ValidationFeatureTimestamp("ofi", 995, 1001, 995, True),)}
    )

    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:feature_available_at_after_decision" in result.rejection_reasons


def test_unfinalized_candle_or_bar_feature_rejects() -> None:
    input_ = _base_input()
    input_ = LeakageBiasRepaintInput(
        **{**input_.__dict__, "feature_timestamps": (ValidationFeatureTimestamp("bar_close", 995, 999, None, True),)}
    )

    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:feature_finalized_at_missing" in result.rejection_reasons


def test_current_bar_usage_rejects() -> None:
    input_ = _base_input()
    input_ = LeakageBiasRepaintInput(
        **{
            **input_.__dict__,
            "feature_timestamps": (ValidationFeatureTimestamp("bar_close", 995, 999, 999, True, True),),
        }
    )

    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:current_bar_usage_forbidden" in result.rejection_reasons


def test_future_or_unfinalized_funding_observation_rejects() -> None:
    input_ = _base_input()
    input_ = LeakageBiasRepaintInput(
        **{
            **input_.__dict__,
            "funding_observations": (
                ValidationFundingObservation(
                    venue="binance_usdm",
                    event_time_ns=980,
                    available_at_ns=1001,
                    finalized_at_ns=None,
                    final_rate=None,
                ),
            ),
        }
    )

    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:funding_available_at_after_decision" in result.rejection_reasons
    assert "leakage_bias_repaint:funding_unfinalized_at_decision" in result.rejection_reasons
    assert "leakage_bias_repaint:funding_final_rate_unavailable" in result.rejection_reasons


def test_missing_pit_policy_rejects() -> None:
    result = evaluate_leakage_bias_repaint(LeakageBiasRepaintInput(**{**_base_input().__dict__, "pit_policy": None}))
    assert "leakage_bias_repaint:pit_policy_missing" in result.rejection_reasons


def test_repaint_risk_indicator_without_confirmation_rule_rejects() -> None:
    input_ = LeakageBiasRepaintInput(
        **{
            **_base_input().__dict__,
            "indicator_policies": (ValidationIndicatorPolicy("zigzag", repaint_risk=True, confirmation_rule=None),),
        }
    )
    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:repaint_confirmation_rule_missing" in result.rejection_reasons


def test_bist_metadata_leakage_rejects_recursively() -> None:
    input_ = LeakageBiasRepaintInput(**{**_base_input().__dict__, "metadata": {"nested": ["Matriks", {"x": "Borsa"}]}})
    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:bist_scope_leakage" in result.rejection_reasons


def test_forbidden_live_private_order_scheduler_tokens_reject_recursively() -> None:
    input_ = LeakageBiasRepaintInput(
        **{
            **_base_input().__dict__,
            "payload": {
                "nested": {
                    "scheduler": "enabled",
                    "private_api": "x",
                    "order_router": "v1",
                    "auto_loop": True,
                    "shadow_live_execution": False,
                    "credentials": "bad",
                    "live": "bad",
                }
            },
        }
    )
    result = evaluate_leakage_bias_repaint(input_)
    assert "leakage_bias_repaint:forbidden_field_scheduler" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_private_api" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_order_router" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_auto_loop" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_shadow_live_execution" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_credentials" in result.rejection_reasons
    assert "leakage_bias_repaint:forbidden_field_live" in result.rejection_reasons


def test_needs_research_is_not_accepted() -> None:
    input_ = LeakageBiasRepaintInput(
        **{**_base_input().__dict__, "needs_research_reasons": ("indicator calibration missing",)}
    )
    result = evaluate_leakage_bias_repaint(input_)
    assert result.accepted is False
    assert result.status is LeakageBiasRepaintStatus.NEEDS_RESEARCH


def test_insufficient_evidence_is_not_accepted() -> None:
    input_ = LeakageBiasRepaintInput(**{**_base_input().__dict__, "insufficient_evidence_reasons": ("missing bars",)})
    result = evaluate_leakage_bias_repaint(input_)
    assert result.accepted is False
    assert result.status is LeakageBiasRepaintStatus.INSUFFICIENT_EVIDENCE


def test_rejection_reason_ordering_is_deterministic() -> None:
    input_ = LeakageBiasRepaintInput(
        **{
            **_base_input().__dict__,
            "pit_policy": None,
            "payload": {"z": "scheduler", "a": "bist"},
            "feature_timestamps": (ValidationFeatureTimestamp("x", 1001, 1001, None, True, True),),
        }
    )
    result = evaluate_leakage_bias_repaint(input_)
    assert result.rejection_reasons == tuple(sorted(set(result.rejection_reasons)))


def test_to_dict_serialization_is_deterministic_and_audit_safe() -> None:
    result = evaluate_leakage_bias_repaint(_base_input())
    payload_a = leakage_bias_repaint_result_to_dict(result)
    payload_b = leakage_bias_repaint_result_to_dict(result)

    assert payload_a == payload_b
    assert json.loads(json.dumps(payload_a)) == payload_a


def test_from_dict_round_trip() -> None:
    result = evaluate_leakage_bias_repaint(_base_input())
    payload = leakage_bias_repaint_result_to_dict(result)
    loaded = leakage_bias_repaint_result_from_dict(payload)
    assert loaded == result
