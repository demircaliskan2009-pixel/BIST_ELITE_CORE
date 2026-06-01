from __future__ import annotations

from crypto_core.data.requirements import data_requirement_registry_to_dict, default_perp_data_requirement_registry
from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation import PitParityPolicy, validate_strategy_data_requirements


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "pit-s01",
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


def test_valid_minimal_perp_registry_and_strategy_data_requirements_passes() -> None:
    registry = default_perp_data_requirement_registry()
    result = validate_strategy_data_requirements(_valid_spec(), registry)

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert result.needs_research_reasons == ()


def test_raw_strategy_spec_mapping_path_passes() -> None:
    registry = default_perp_data_requirement_registry()
    result = validate_strategy_data_requirements(_strategy_payload(), registry)

    assert result.accepted is True


def test_invalid_strategy_spec_mapping_rejects_with_prefixed_reasons() -> None:
    payload = _strategy_payload()
    del payload["strategy_id"]

    result = validate_strategy_data_requirements(payload, default_perp_data_requirement_registry())

    assert result.accepted is False
    assert "pit_parity:strategy_spec:strategy_spec:strategy_id_missing" in result.rejection_reasons


def test_unknown_data_key_rejects() -> None:
    payload = _strategy_payload()
    payload["data_requirements"]["unknown_feed"] = {"required": True}

    result = validate_strategy_data_requirements(payload, default_perp_data_requirement_registry())
    assert "pit_parity:unknown_data_key:unknown_feed" in result.rejection_reasons


def test_missing_historical_source_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["order_book"]["historical_source"] = ""

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any(reason.startswith("pit_parity:registry:") for reason in result.rejection_reasons)


def test_missing_paper_parity_source_rejects_when_required() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["mark_price"]["paper_observation_source"] = None

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("paper_parity_source_missing" in reason for reason in result.rejection_reasons)


def test_missing_timestamp_semantics_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["order_book"]["event_time_policy"] = ""

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("event_time_policy" in reason for reason in result.rejection_reasons)


def test_ambiguous_generic_funding_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["funding_rate"]["funding_semantics"] = "generic"

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("funding_semantics_ambiguous" in reason for reason in result.rejection_reasons)


def test_mark_index_last_price_ambiguity_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["mark_price"]["price_semantics"] = "price"

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("price_semantics_ambiguous" in reason for reason in result.rejection_reasons)


def test_order_book_missing_level_depth_sequence_resync_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["order_book"]["order_book_level"] = None
    registry_payload["requirements"]["order_book"]["order_book_depth"] = 0
    registry_payload["requirements"]["order_book"]["sequence_policy"] = ""
    registry_payload["requirements"]["order_book"]["resync_policy"] = ""

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert "pit_parity:registry:data_requirement_registry:order_book_level_missing" in result.rejection_reasons


def test_liquidation_missing_source_or_finality_rejects() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["liquidation"]["liquidation_source"] = ""
    registry_payload["requirements"]["liquidation"]["finality_policy"] = ""

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("liquidation_source" in reason for reason in result.rejection_reasons)


def test_fee_slippage_latency_none_or_zero_defaults_reject() -> None:
    registry_payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    registry_payload["requirements"]["mark_price"]["fee_assumption"] = "0"
    registry_payload["requirements"]["mark_price"]["slippage_assumption"] = "none"
    registry_payload["requirements"]["mark_price"]["latency_assumption"] = ""

    result = validate_strategy_data_requirements(_valid_spec(), registry_payload)
    assert result.accepted is False
    assert any("fee_assumption" in reason for reason in result.rejection_reasons)


def test_bist_leakage_rejects_recursively() -> None:
    payload = _strategy_payload()
    payload["data_requirements"] = {"order_book": {"source": ["Matriks", {"scope": "Borsa"}]}}

    result = validate_strategy_data_requirements(payload, default_perp_data_requirement_registry())
    assert result.accepted is False
    assert any("bist_scope_leakage" in reason for reason in result.rejection_reasons)


def test_forbidden_live_private_order_scheduler_tokens_reject_recursively() -> None:
    payload = _strategy_payload()
    payload["data_requirements"] = {
        "order_book": {
            "scheduler": "enabled",
            "private_api": "x",
            "order_router": "v1",
            "auto_loop": True,
            "shadow_live_execution": False,
            "credentials": "bad",
            "live": "bad",
        }
    }

    result = validate_strategy_data_requirements(payload, default_perp_data_requirement_registry())
    assert result.accepted is False
    assert any("forbidden_field_scheduler" in reason for reason in result.rejection_reasons)


def test_needs_research_is_not_accepted() -> None:
    policy = PitParityPolicy(needs_research_reasons=("needs additional study",))
    result = validate_strategy_data_requirements(_valid_spec(), default_perp_data_requirement_registry(), policy)

    assert result.accepted is False
    assert result.needs_research_reasons


def test_rejection_reason_ordering_is_deterministic() -> None:
    payload = _strategy_payload()
    payload["data_requirements"] = {"price": {}, "funding": {}, "order_book": {"scheduler": "x", "b": "bist"}}

    result = validate_strategy_data_requirements(payload, default_perp_data_requirement_registry())
    assert result.rejection_reasons == tuple(sorted(set(result.rejection_reasons)))


def test_canonical_digest_stable() -> None:
    registry = default_perp_data_requirement_registry()
    result_a = validate_strategy_data_requirements(_valid_spec(), registry)
    result_b = validate_strategy_data_requirements(_valid_spec(), registry)

    assert result_a.accepted is True
    assert result_b.accepted is True
    assert result_a.rejection_reasons == result_b.rejection_reasons
