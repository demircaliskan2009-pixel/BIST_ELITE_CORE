from __future__ import annotations

import pytest

from crypto_core import validation as validation_module
from crypto_core.validation import (
    RegimeGateEvidence,
    StressScenario,
    StressTrade,
    default_stress_scenarios,
    validate_stress_testing,
)


def _trade(
    trade_id: str,
    *,
    side: str = "long",
    entry_notional: float = 100.0,
    gross_pnl_before_costs: float = 25.0,
    realized_slippage_cost: float = 1.0,
    fixed_cost_ex_slippage: float = 1.0,
    depth_notional_at_execution: float | None = 1000.0,
    open_notional_during_event: float | None = 20.0,
) -> StressTrade:
    return StressTrade(
        trade_id=trade_id,
        side=side,
        entry_notional=entry_notional,
        gross_pnl_before_costs=gross_pnl_before_costs,
        realized_slippage_cost=realized_slippage_cost,
        fixed_cost_ex_slippage=fixed_cost_ex_slippage,
        depth_notional_at_execution=depth_notional_at_execution,
        open_notional_during_event=open_notional_during_event,
    )


def _gate(
    *,
    documented: bool = True,
    gate_id: str = "gate-1",
    evidence_ref: str = "audit://flash-crash",
    gate_action: str = "skip_regime",
) -> RegimeGateEvidence:
    return RegimeGateEvidence(
        scenario_id="flash_crash",
        documented=documented,
        gate_id=gate_id,
        evidence_ref=evidence_ref,
        gate_action=gate_action,
    )


def test_default_scenarios_are_deterministic_and_ordered():
    scenarios = default_stress_scenarios()
    assert scenarios == default_stress_scenarios()
    assert tuple(scenario.scenario_id for scenario in scenarios) == ("high_vol", "low_liquidity", "flash_crash")
    assert scenarios[0].return_scale == 1.5
    assert scenarios[1].depth_scale == 0.2
    assert scenarios[2].adverse_gap_pct == 0.10
    assert scenarios[2].recovery_minutes == 5


def test_all_three_default_scenarios_pass_with_robust_positive_expectancy():
    result = validate_stress_testing((_trade("t-1"), _trade("t-2", side="short"), _trade("t-3", entry_notional=150.0)))
    assert result.all_passed is True
    assert result.rejection_reasons == ()
    assert tuple(item.scenario_id for item in result.scenario_results) == ("high_vol", "low_liquidity", "flash_crash")
    assert all(item.passed for item in result.scenario_results)


def test_stressed_expectancy_zero_passes():
    result = validate_stress_testing(
        (
            _trade(
                "t-1",
                gross_pnl_before_costs=2.0,
                realized_slippage_cost=1.0,
                fixed_cost_ex_slippage=1.0,
            ),
        ),
        scenarios=(StressScenario("high_vol", return_scale=1.0, slippage_scale=1.0),),
    )
    assert result.all_passed is True
    assert result.scenario_results[0].stressed_expectancy == 0.0


def test_high_vol_negative_expectancy_rejects():
    result = validate_stress_testing(
        (_trade("t-1", gross_pnl_before_costs=1.0, realized_slippage_cost=1.0, fixed_cost_ex_slippage=1.0),),
        scenarios=(StressScenario("high_vol", return_scale=1.5, slippage_scale=2.0),),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == ("high_vol:negative_expectancy",)
    assert result.scenario_results[0].passed is False


def test_low_liquidity_negative_expectancy_rejects():
    result = validate_stress_testing(
        (_trade("t-1", gross_pnl_before_costs=2.0, realized_slippage_cost=1.0, fixed_cost_ex_slippage=1.0),),
        scenarios=(StressScenario("low_liquidity", return_scale=1.0, slippage_scale=3.0, depth_scale=0.2),),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == ("low_liquidity:negative_expectancy",)
    assert result.scenario_results[0].passed is False


def test_flash_crash_negative_expectancy_rejects_without_regime_gate():
    result = validate_stress_testing(
        (
            _trade(
                "t-1",
                gross_pnl_before_costs=5.0,
                realized_slippage_cost=1.0,
                fixed_cost_ex_slippage=1.0,
                open_notional_during_event=50.0,
            ),
        ),
        scenarios=(
            StressScenario(
                "flash_crash",
                return_scale=1.0,
                slippage_scale=3.0,
                adverse_gap_pct=0.10,
                recovery_minutes=5,
                allows_regime_gate=True,
            ),
        ),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == ("flash_crash:negative_expectancy",)
    assert result.scenario_results[0].regime_gate_used is False


def test_flash_crash_negative_expectancy_passes_with_valid_regime_gate():
    result = validate_stress_testing(
        (
            _trade(
                "t-1",
                gross_pnl_before_costs=5.0,
                realized_slippage_cost=1.0,
                fixed_cost_ex_slippage=1.0,
                open_notional_during_event=50.0,
            ),
        ),
        scenarios=(
            StressScenario(
                "flash_crash",
                return_scale=1.0,
                slippage_scale=3.0,
                adverse_gap_pct=0.10,
                recovery_minutes=5,
                allows_regime_gate=True,
            ),
        ),
        regime_gates=(_gate(),),
    )
    assert result.all_passed is True
    assert result.rejection_reasons == ()
    assert result.scenario_results[0].passed_with_regime_gate is True
    assert result.scenario_results[0].regime_gate_used is True


def test_invalid_regime_gate_fails_closed():
    result = validate_stress_testing((_trade("t-1"),), regime_gates=(_gate(documented=False),))
    assert result.all_passed is False
    assert result.rejection_reasons == ("regime_gate[0]:undocumented",)
    assert all(item.passed for item in result.scenario_results)


def test_empty_trades_fail_closed():
    result = validate_stress_testing(())
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("trades_empty",)


def test_duplicate_trade_id_fails_closed():
    result = validate_stress_testing((_trade("dup"), _trade("dup")))
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("trade[1]:duplicate_trade_id",)


def test_malformed_entry_notional_fails_closed():
    result = validate_stress_testing((_trade("t-1", entry_notional=0.0),))
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("trade[0]:malformed_entry_notional",)


def test_negative_slippage_fails_closed():
    result = validate_stress_testing((_trade("t-1", realized_slippage_cost=-0.1),))
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("trade[0]:malformed_realized_slippage_cost",)


def test_negative_fixed_cost_fails_closed():
    result = validate_stress_testing((_trade("t-1", fixed_cost_ex_slippage=-0.1),))
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("trade[0]:malformed_fixed_cost_ex_slippage",)


def test_missing_depth_for_low_liquidity_fails_closed():
    result = validate_stress_testing(
        (_trade("t-1", depth_notional_at_execution=None),),
        scenarios=(StressScenario("low_liquidity", return_scale=1.0, slippage_scale=3.0, depth_scale=0.2),),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == ("low_liquidity:missing_depth_notional_at_execution",)
    assert result.scenario_results[0].passed is False


def test_missing_open_notional_for_flash_crash_fails_closed():
    result = validate_stress_testing(
        (_trade("t-1", open_notional_during_event=None),),
        scenarios=(
            StressScenario(
                "flash_crash",
                return_scale=1.0,
                slippage_scale=3.0,
                adverse_gap_pct=0.10,
                recovery_minutes=5,
                allows_regime_gate=True,
            ),
        ),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == ("flash_crash:missing_open_notional_during_event",)
    assert result.scenario_results[0].passed is False


def test_unknown_scenario_fails_closed():
    result = validate_stress_testing((_trade("t-1"),), scenarios=(StressScenario("unknown", 1.0, 1.0),))
    assert result.all_passed is False
    assert result.scenario_results == ()
    assert result.rejection_reasons == ("scenario[0]:unknown_scenario_id",)


def test_low_liquidity_max_depth_usage_ratio_is_computed_deterministically():
    result = validate_stress_testing(
        (
            _trade("t-1", entry_notional=100.0, depth_notional_at_execution=1000.0),
            _trade("t-2", entry_notional=120.0, gross_pnl_before_costs=40.0, depth_notional_at_execution=150.0),
        ),
        scenarios=(StressScenario("low_liquidity", return_scale=1.0, slippage_scale=3.0, depth_scale=0.2),),
    )
    assert result.all_passed is True
    assert result.scenario_results[0].max_depth_usage_ratio == pytest.approx(4.0)


def test_repeated_output_is_deterministic():
    payload = (_trade("t-1"), _trade("t-2", side="short"))
    assert validate_stress_testing(payload) == validate_stress_testing(payload)


def test_rejection_reasons_are_stable_and_ordered():
    result = validate_stress_testing(
        (
            _trade(
                "t-1",
                gross_pnl_before_costs=1.0,
                realized_slippage_cost=1.0,
                fixed_cost_ex_slippage=1.0,
                depth_notional_at_execution=None,
                open_notional_during_event=None,
            ),
        ),
        regime_gates=(_gate(documented=False),),
    )
    assert result.all_passed is False
    assert result.rejection_reasons == (
        "high_vol:negative_expectancy",
        "low_liquidity:missing_depth_notional_at_execution",
        "flash_crash:missing_open_notional_during_event",
        "regime_gate[0]:undocumented",
    )


def test_validation_exports_import_correctly():
    assert validation_module.StressTrade is StressTrade
    assert validation_module.StressScenario is StressScenario
    assert validation_module.RegimeGateEvidence is RegimeGateEvidence
    assert validation_module.default_stress_scenarios is default_stress_scenarios
    assert validation_module.validate_stress_testing is validate_stress_testing
