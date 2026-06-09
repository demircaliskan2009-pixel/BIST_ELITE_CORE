"""Tests for the strategy validation bundle (deterministic paper-only pipeline consumer)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from crypto_core.data.requirements import default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import (
    SourcePacketRightsStatus,
    SourcePacketSourceType,
    build_source_packet,
)
from crypto_core.strategy.spec import StrategySpec, validate_strategy_spec
from crypto_core.validation.leakage_bias_repaint import (
    LeakageBiasRepaintInput,
    ValidationFeatureTimestamp,
    ValidationFundingObservation,
    ValidationIndicatorPolicy,
)
from crypto_core.validation.strategy_validation_bundle import (
    StrategyValidationBundle,
    StrategyValidationBundleError,
    StrategyValidationBundleStatus,
    build_strategy_validation_bundle,
    strategy_validation_bundle_to_dict,
)

_CORR = "corr:strategy-validation-bundle-001"
_HEX64 = "a" * 64


def _strategy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "strategy_id": "svb-s01",
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


def _leakage_input(spec, **overrides) -> LeakageBiasRepaintInput:
    kwargs = {
        "strategy_spec": spec,
        "decision_timestamp_ns": 1_000,
        "pit_policy": {"mode": "strict", "point_in_time": True},
        "feature_timestamps": (
            ValidationFeatureTimestamp(
                feature_name="ofi_20",
                event_time_ns=990,
                available_at_ns=995,
                finalized_at_ns=995,
                is_candle_or_bar_derived=True,
                uses_current_bar=False,
            ),
        ),
        "funding_observations": (
            ValidationFundingObservation(
                venue="binance_usdm",
                event_time_ns=980,
                available_at_ns=985,
                finalized_at_ns=990,
                final_rate=0.0001,
            ),
        ),
        "indicator_policies": (ValidationIndicatorPolicy(indicator_name="ema_cross", repaint_risk=False),),
        "payload": {"source": "crypto"},
        "metadata": {"scope": "crypto_only"},
        "fee_assumption": "maker_taker",
        "slippage_assumption": "book_impact_v1",
        "funding_assumption": "funding_curve_v1",
    }
    kwargs.update(overrides)
    return LeakageBiasRepaintInput(**kwargs)


def _usable_packet():
    return build_source_packet(
        packet_id="src:svb-001",
        source_type=SourcePacketSourceType.ACADEMIC_PAPER,
        source_reference="https://example.org/ofi",
        source_title="Order flow imbalance edge",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        edge_hypothesis="Order flow imbalance predicts short-horizon perpetual returns",
        content_digest=_HEX64,
        market_scope_tags=("btc-perp",),
    )


def _bundle(**overrides):
    spec = overrides.pop("strategy_spec", None)
    spec = _valid_spec() if spec is None else spec
    kwargs = {
        "registry": default_perp_data_requirement_registry(),
        "leakage_input": _leakage_input(spec),
        "correlation_id": _CORR,
    }
    kwargs.update(overrides)
    return build_strategy_validation_bundle(spec, **kwargs)


def test_valid_minimal_accepted_bundle():
    bundle = _bundle()
    assert isinstance(bundle, StrategyValidationBundle)
    assert bundle.status is StrategyValidationBundleStatus.ACCEPTED
    assert bundle.accepted is True
    assert bundle.strategy_id == "svb-s01"
    assert len(bundle.strategy_digest) == 64
    assert bundle.data_registry_digest is not None and len(bundle.data_registry_digest) == 64
    assert bundle.pit_status == "ACCEPTED"
    assert bundle.leakage_status == "PASS"
    assert bundle.terminal_rejection_reasons == ()
    assert bundle.terminal_needs_research_reasons == ()
    assert len(bundle.decision_record_digests) == 3
    assert all(len(digest) == 64 for digest in bundle.decision_record_digests)
    assert len(bundle.bundle_digest) == 64
    assert bundle.paper_only is True
    assert bundle.real_orders_enabled is False
    assert bundle.real_money_enabled is False


def test_invalid_strategy_spec_rejects():
    payload = _strategy_payload()
    del payload["strategy_id"]
    bundle = _bundle(strategy_spec=payload)
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.accepted is False
    assert bundle.terminal_rejection_reasons != ()
    assert bundle.decision_record_digests == ()
    assert bundle.strategy_digest == ""


def test_malformed_registry_rejects():
    bundle = _bundle(registry={"schema_version": "1.0", "requirements": {}})
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.pit_status == "REJECTED"
    assert any("registry" in reason for reason in bundle.terminal_rejection_reasons)


def test_pit_rejection_propagates():
    payload = _strategy_payload()
    payload["data_requirements"]["unknown_feed"] = {"required": True}
    bundle = _bundle(strategy_spec=payload)
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.pit_status == "REJECTED"
    assert "pit_parity:unknown_data_key:unknown_feed" in bundle.terminal_rejection_reasons


def test_leakage_current_bar_rejection_propagates():
    spec = _valid_spec()
    leakage = _leakage_input(
        spec,
        feature_timestamps=(
            ValidationFeatureTimestamp(
                feature_name="ofi_20",
                event_time_ns=990,
                available_at_ns=995,
                finalized_at_ns=995,
                is_candle_or_bar_derived=True,
                uses_current_bar=True,
            ),
        ),
    )
    bundle = build_strategy_validation_bundle(
        spec, registry=default_perp_data_requirement_registry(), leakage_input=leakage, correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.leakage_status == "REJECT"
    assert "leakage_bias_repaint:current_bar_usage_forbidden" in bundle.terminal_rejection_reasons


def test_leakage_needs_research_propagates():
    spec = _valid_spec()
    leakage = _leakage_input(spec, needs_research_reasons=("funding_regime_uncertain",))
    bundle = build_strategy_validation_bundle(
        spec, registry=default_perp_data_requirement_registry(), leakage_input=leakage, correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.NEEDS_RESEARCH
    assert bundle.accepted is False
    assert bundle.leakage_status == "NEEDS_RESEARCH"
    assert bundle.terminal_needs_research_reasons != ()


def test_restricted_source_packet_blocks_acceptance():
    packet = build_source_packet(
        packet_id="src:svb-restricted",
        source_type=SourcePacketSourceType.CODE_REPOSITORY,
        source_reference="https://example.org/private-repo",
        source_title="Restricted strategy code",
        rights_status=SourcePacketRightsStatus.RESTRICTED,
        edge_hypothesis="Restricted source funding carry edge",
        content_digest=_HEX64,
        market_scope_tags=("btc-perp",),
    )
    bundle = _bundle(source_packet=packet)
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.accepted is False
    assert "strategy_validation_bundle:source_packet_not_usable" in bundle.terminal_rejection_reasons
    assert bundle.source_packet_digest == packet.packet_digest


def test_usable_source_packet_evidence_included():
    packet = _usable_packet()
    bundle = _bundle(source_packet=packet)
    assert bundle.status is StrategyValidationBundleStatus.ACCEPTED
    assert bundle.source_packet_digest == packet.packet_digest
    assert len(bundle.decision_record_digests) == 3


def test_decision_record_digests_deterministic_and_non_empty():
    first = _bundle().decision_record_digests
    second = _bundle().decision_record_digests
    assert first == second
    assert len(first) == 3
    assert all(len(digest) == 64 for digest in first)


def test_material_change_changes_bundle_digest():
    base = _bundle()
    changed = _bundle(correlation_id="corr:strategy-validation-bundle-002")
    assert changed.bundle_digest != base.bundle_digest


def test_identical_input_identical_dict_and_digest():
    first = _bundle()
    second = _bundle()
    assert strategy_validation_bundle_to_dict(first) == strategy_validation_bundle_to_dict(second)
    assert first.bundle_digest == second.bundle_digest
    assert strategy_validation_bundle_to_dict(first)["bundle_digest"] == first.bundle_digest


def test_bist_and_forbidden_leakage_rejects():
    # BIST in the strategy spec -> spec invalid -> rejected bundle.
    bist_payload = _strategy_payload()
    bist_payload["venue_assumptions"] = ["borsa_istanbul"]
    assert (
        build_strategy_validation_bundle(
            bist_payload,
            registry=default_perp_data_requirement_registry(),
            leakage_input=None,
            correlation_id=_CORR,
        ).status
        is StrategyValidationBundleStatus.REJECTED
    )

    # Forbidden token inside the leakage payload -> leakage REJECT -> rejected bundle.
    spec = _valid_spec()
    leakage = _leakage_input(spec, payload={"note": "order_router wiring"})
    bundle = build_strategy_validation_bundle(
        spec, registry=default_perp_data_requirement_registry(), leakage_input=leakage, correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert any("order_router" in reason for reason in bundle.terminal_rejection_reasons)


def test_leakage_input_for_different_strategy_rejected():
    # Regression (Codex P1): a leakage proof built for strategy B must not certify strategy A.
    spec_a = _valid_spec()
    payload_b = _strategy_payload()
    payload_b["strategy_id"] = "svb-other"
    result_b = validate_strategy_spec(payload_b)
    assert result_b.spec is not None
    leakage_b = _leakage_input(result_b.spec)
    bundle = build_strategy_validation_bundle(
        spec_a, registry=default_perp_data_requirement_registry(), leakage_input=leakage_b, correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.REJECTED
    assert bundle.accepted is False
    assert "strategy_validation_bundle:leakage_strategy_mismatch" in bundle.terminal_rejection_reasons
    # The foreign leakage proof must not enter the ledger chain (spec + PIT records only).
    assert len(bundle.decision_record_digests) == 2


def test_missing_leakage_input_is_insufficient_evidence():
    bundle = build_strategy_validation_bundle(
        _valid_spec(), registry=default_perp_data_requirement_registry(), leakage_input=None, correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.INSUFFICIENT_EVIDENCE
    assert bundle.accepted is False
    assert bundle.leakage_status == "INSUFFICIENT_EVIDENCE"


def test_immutable_and_no_leakage_fields():
    bundle = _bundle()
    with pytest.raises(FrozenInstanceError):
        bundle.status = StrategyValidationBundleStatus.REJECTED  # type: ignore[misc]
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert {field.name for field in fields(bundle)}.isdisjoint(forbidden)
    payload = strategy_validation_bundle_to_dict(bundle)
    assert payload["schema_version"] == "strategy-validation-bundle.v1"
    assert set(payload).isdisjoint(forbidden)


def test_call_level_malformed_inputs_raise():
    spec = _valid_spec()
    with pytest.raises(StrategyValidationBundleError):
        build_strategy_validation_bundle(spec, correlation_id="")
    with pytest.raises(StrategyValidationBundleError):
        build_strategy_validation_bundle(spec, correlation_id=_CORR, previous_record_digest="not-a-digest")
    with pytest.raises(StrategyValidationBundleError):
        build_strategy_validation_bundle(123, correlation_id=_CORR)
    with pytest.raises(StrategyValidationBundleError):
        build_strategy_validation_bundle(spec, correlation_id=_CORR, leakage_input={"not": "typed"})
    with pytest.raises(StrategyValidationBundleError):
        build_strategy_validation_bundle(spec, correlation_id=_CORR, source_packet={"not": "typed"})


def test_valid_previous_record_digest_accepted():
    bundle = _bundle(previous_record_digest=_HEX64)
    assert bundle.status is StrategyValidationBundleStatus.ACCEPTED
    assert len(bundle.decision_record_digests) == 3


def test_registry_default_used_when_none():
    spec = _valid_spec()
    bundle = build_strategy_validation_bundle(
        spec, registry=None, leakage_input=_leakage_input(spec), correlation_id=_CORR
    )
    assert bundle.status is StrategyValidationBundleStatus.ACCEPTED
    assert bundle.data_registry_digest is not None
