from __future__ import annotations

from copy import deepcopy

from crypto_core.strategy.spec import (
    StrategySpec,
    StrategySpecValidationResult,
    canonical_strategy_spec_json,
    strategy_spec_digest,
    strategy_spec_from_dict,
    strategy_spec_to_dict,
    validate_strategy_spec,
)


def _valid_payload(*, market_type: str = "usdt_perp") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "s01",
        "strategy_version": "v1",
        "strategy_family": "microstructure",
        "edge_family": "order_flow_imbalance",
        "instrument_universe": ["BTCUSDT"],
        "market_type": market_type,
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


def test_valid_minimal_usdt_perp_spec_accepted() -> None:
    result = validate_strategy_spec(_valid_payload(market_type="usdt_perp"))

    assert result.accepted is True
    assert result.spec is not None
    assert result.rejection_reasons == ()
    assert result.needs_research_reasons == ()


def test_valid_inverse_perp_spec_accepted() -> None:
    payload = _valid_payload(market_type="inverse_perp")
    payload["instrument_universe"] = ["BTCUSD"]

    result = validate_strategy_spec(payload)

    assert result.accepted is True
    assert result.spec is not None


def test_missing_strategy_id_rejected() -> None:
    payload = _valid_payload()
    del payload["strategy_id"]

    result = validate_strategy_spec(payload)

    assert "strategy_spec:strategy_id_missing" in result.rejection_reasons


def test_missing_schema_version_rejected() -> None:
    payload = _valid_payload()
    del payload["schema_version"]

    result = validate_strategy_spec(payload)

    assert "strategy_spec:schema_version_missing" in result.rejection_reasons


def test_unknown_market_type_rejected() -> None:
    payload = _valid_payload(market_type="unknown_perp")

    result = validate_strategy_spec(payload)

    assert "strategy_spec:market_type_unknown" in result.rejection_reasons


def test_spot_margin_options_and_dated_futures_rejected_for_pr1() -> None:
    for unsupported in ("spot", "margin", "options", "dated_futures"):
        result = validate_strategy_spec(_valid_payload(market_type=unsupported))
        assert "strategy_spec:market_type_unsupported_pr1" in result.rejection_reasons


def test_empty_instrument_universe_rejected() -> None:
    payload = _valid_payload()
    payload["instrument_universe"] = []

    result = validate_strategy_spec(payload)

    assert "strategy_spec:instrument_universe_empty" in result.rejection_reasons


def test_unsupported_or_empty_venue_assumptions_rejected() -> None:
    payload = _valid_payload()
    payload["venue_assumptions"] = []

    result = validate_strategy_spec(payload)
    assert "strategy_spec:venue_assumptions_empty" in result.rejection_reasons

    payload = _valid_payload()
    payload["venue_assumptions"] = ["bist30"]
    result = validate_strategy_spec(payload)
    assert "strategy_spec:venue_assumptions_non_crypto" in result.rejection_reasons


def test_forbidden_live_private_order_scheduler_fields_rejected_recursively() -> None:
    payload = _valid_payload()
    payload["feature_requirements"] = {
        "nested": {
            "scheduler": "enabled",
            "private_api": "x",
            "order_router": "v1",
            "auto_loop": True,
            "shadow_live_execution": False,
            "credentials": "bad",
            "live": "bad",
        }
    }

    result = validate_strategy_spec(payload)
    assert any(reason.startswith("strategy_spec:forbidden_field_") for reason in result.rejection_reasons)


def test_bist_venue_scope_session_leakage_rejected_recursively() -> None:
    payload = _valid_payload()
    payload["feature_requirements"] = {"source": ["Matriks", {"scope": "Borsa"}]}

    result = validate_strategy_spec(payload)

    assert "strategy_spec:bist_scope_leakage" in result.rejection_reasons


def test_fee_requirement_missing_or_zero_default_rejected() -> None:
    payload = _valid_payload()
    payload["fee_model_requirement"] = "0"

    result = validate_strategy_spec(payload)
    assert "strategy_spec:fee_model_requirement_invalid" in result.rejection_reasons

    payload = _valid_payload()
    del payload["fee_model_requirement"]
    result = validate_strategy_spec(payload)
    assert "strategy_spec:fee_model_requirement_missing" in result.rejection_reasons


def test_slippage_requirement_missing_or_zero_default_rejected() -> None:
    payload = _valid_payload()
    payload["slippage_model_requirement"] = "zero"

    result = validate_strategy_spec(payload)
    assert "strategy_spec:slippage_model_requirement_invalid" in result.rejection_reasons

    payload = _valid_payload()
    del payload["slippage_model_requirement"]
    result = validate_strategy_spec(payload)
    assert "strategy_spec:slippage_model_requirement_missing" in result.rejection_reasons


def test_perp_funding_sensitivity_missing_or_unknown_needs_research() -> None:
    payload = _valid_payload()
    payload["funding_sensitivity"] = "unknown"

    result = validate_strategy_spec(payload)
    assert result.accepted is False
    assert "strategy_spec:funding_sensitivity_needs_research" in result.needs_research_reasons

    payload = _valid_payload()
    del payload["funding_sensitivity"]
    result = validate_strategy_spec(payload)
    assert "strategy_spec:funding_sensitivity_missing" in result.rejection_reasons


def test_max_leverage_missing_or_above_three_rejected() -> None:
    payload = _valid_payload()
    payload["risk_caps"] = {"max_notional": 1000}

    result = validate_strategy_spec(payload)
    assert "strategy_spec:max_leverage_missing" in result.rejection_reasons

    payload = _valid_payload()
    payload["risk_caps"] = {"max_leverage": 4}
    result = validate_strategy_spec(payload)
    assert "strategy_spec:max_leverage_exceeds_cap" in result.rejection_reasons


def test_deterministic_canonical_json_stable_across_key_order() -> None:
    payload_a = _valid_payload()
    payload_b = {}
    for key in reversed(list(payload_a.keys())):
        payload_b[key] = payload_a[key]

    result_a = validate_strategy_spec(payload_a)
    result_b = validate_strategy_spec(payload_b)

    assert result_a.accepted and result_b.accepted
    assert result_a.spec is not None and result_b.spec is not None
    assert canonical_strategy_spec_json(result_a.spec) == canonical_strategy_spec_json(result_b.spec)


def test_deterministic_sha256_digest_stable_across_key_order() -> None:
    payload_a = _valid_payload()
    payload_b = deepcopy(payload_a)
    payload_b["risk_caps"] = {"max_notional": 1000, "max_leverage": 3.0}

    result_a = validate_strategy_spec(payload_a)
    result_b = validate_strategy_spec(payload_b)

    assert result_a.accepted and result_b.accepted
    assert result_a.spec is not None and result_b.spec is not None
    assert strategy_spec_digest(result_a.spec) == strategy_spec_digest(result_b.spec)


def test_malformed_from_dict_payload_fails_closed() -> None:
    result = strategy_spec_from_dict({"not": "a_full_payload"})

    assert result.accepted is False
    assert result.spec is None
    assert "strategy_spec:schema_version_missing" in result.rejection_reasons


def test_to_dict_from_dict_round_trip_is_deterministic_for_valid_spec() -> None:
    initial_result = validate_strategy_spec(_valid_payload())

    assert initial_result.accepted is True
    assert initial_result.spec is not None

    payload = strategy_spec_to_dict(initial_result.spec)
    second_result = strategy_spec_from_dict(payload)

    assert second_result.accepted is True
    assert second_result.spec is not None
    assert canonical_strategy_spec_json(initial_result.spec) == canonical_strategy_spec_json(second_result.spec)
    assert strategy_spec_digest(initial_result.spec) == strategy_spec_digest(second_result.spec)


def test_public_api_types_present() -> None:
    result = validate_strategy_spec(_valid_payload())

    assert isinstance(result, StrategySpecValidationResult)
    assert isinstance(result.spec, StrategySpec)
