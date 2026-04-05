from __future__ import annotations

from bist_core.edge.registry import (
    EdgeCondition,
    EdgeDefinition,
    EdgeLogic,
    EdgeRegistry,
    EdgeRequiredData,
    EdgeRiskProfile,
    IMKBH_UNIVERSE,
    build_builtin_edge_registry,
)


def _valid_edge(edge_id: str = "test_edge") -> EdgeDefinition:
    return EdgeDefinition(
        edge_id=edge_id,
        hypothesis="IMKBH bull continuation hypothesis with explicit deterministic rules.",
        feature_set=("close", "sma_20", "sma_50", "momentum_20", "atr_14"),
        regime_applicability=("bull",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("bull",), "Bull regime must be active."),
                EdgeCondition("sma_20", ">", "sma_50", "Fast trend must lead slow trend."),
                EdgeCondition("momentum_20", ">", 0.0, "Momentum must be positive."),
            ),
        ),
        exit_logic=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("close", "<", "sma_20", "Exit when price loses SMA20 support."),
            ),
        ),
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "not_in", ("bull",), "Fail closed outside bull regime."),
                EdgeCondition("atr_14", "<=", 0.0, "ATR14 must remain defined."),
            ),
        ),
        risk_profile=EdgeRiskProfile(
            volatility_bucket="medium",
            max_expected_drawdown_pct=0.06,
            max_holding_bars=8,
        ),
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d",
            bar_fields=("open", "high", "low", "close", "volume", "timestamp"),
            min_history_bars=60,
        ),
    )


def test_builtin_edge_registry_loads_examples() -> None:
    registry = build_builtin_edge_registry()
    active = registry.list_active_edges()
    assert len(active) == 2
    assert tuple(edge.edge_id for edge in active) == (
        "bist_bull_pullback_sma20",
        "bist_sideways_rsi_reversion",
    )


def test_add_edge_rejects_duplicate_edge_id() -> None:
    registry = EdgeRegistry()
    first = _valid_edge("dup_edge")
    assert registry.add_edge(first).valid is True
    duplicate = registry.add_edge(first)
    assert duplicate.valid is False
    assert duplicate.errors == ("duplicate edge_id 'dup_edge'",)


def test_validate_edge_rejects_undefined_feature() -> None:
    registry = EdgeRegistry()
    invalid = EdgeDefinition(
        edge_id="bad_feature_edge",
        hypothesis="Invalid edge with missing feature definition.",
        feature_set=("close", "undefined_feature"),
        regime_applicability=("bull",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("undefined_feature", ">", 0.0, "Undefined feature should fail validation."),
            ),
        ),
        exit_logic=EdgeLogic(
            match="any",
            conditions=(EdgeCondition("close", "<", 0.0, "Never true test exit."),),
        ),
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(EdgeCondition("regime", "not_in", ("bull",), "Fail outside bull."),),
        ),
        risk_profile=EdgeRiskProfile("low", 0.03, 5),
        required_data=EdgeRequiredData(IMKBH_UNIVERSE, "1d", ("open", "high", "low", "close", "volume", "timestamp"), 50),
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert "feature_set contains undefined feature 'undefined_feature'" in result.errors


def test_validate_edge_rejects_ambiguous_operator() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("ambiguous_operator_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis=invalid.hypothesis,
        feature_set=invalid.feature_set,
        regime_applicability=invalid.regime_applicability,
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("sma_20", "approx", "sma_50", "Approximate comparisons are not allowed."),
            ),
        ),
        exit_logic=invalid.exit_logic,
        invalidation_conditions=invalid.invalidation_conditions,
        risk_profile=invalid.risk_profile,
        required_data=invalid.required_data,
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert "entry_logic: ambiguous operator 'approx'" in result.errors


def test_validate_edge_rejects_non_deterministic_description() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("nondeterministic_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis=invalid.hypothesis,
        feature_set=invalid.feature_set,
        regime_applicability=invalid.regime_applicability,
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("momentum_20", ">", 0.0, "Use random discretion when momentum looks good."),
            ),
        ),
        exit_logic=invalid.exit_logic,
        invalidation_conditions=invalid.invalidation_conditions,
        risk_profile=invalid.risk_profile,
        required_data=invalid.required_data,
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert (
        "entry_logic: non-deterministic language in description 'Use random discretion when momentum looks good.'"
        in result.errors
    )


def test_disable_edge_removes_it_from_active_list() -> None:
    registry = EdgeRegistry()
    assert registry.add_edge(_valid_edge("disable_me")).valid is True
    assert registry.disable_edge("disable_me", "walk-forward degradation") is True
    assert registry.list_active_edges() == ()
    all_edges = registry.list_all_edges()
    assert len(all_edges) == 1
    assert all_edges[0].enabled is False
    assert all_edges[0].disabled_reason == "walk-forward degradation"


def test_validate_edge_rejects_leakage_hypothesis_language() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("leakage_hypothesis_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis="Use future return information from the next_bar close to pick IMKBH winners.",
        feature_set=invalid.feature_set,
        regime_applicability=invalid.regime_applicability,
        entry_logic=invalid.entry_logic,
        exit_logic=invalid.exit_logic,
        invalidation_conditions=invalid.invalidation_conditions,
        risk_profile=invalid.risk_profile,
        required_data=invalid.required_data,
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert "hypothesis contains leakage-prone language" in result.errors


def test_validate_edge_rejects_mixed_timeframes() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("mixed_timeframe_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis=invalid.hypothesis,
        feature_set=invalid.feature_set,
        regime_applicability=invalid.regime_applicability,
        entry_logic=invalid.entry_logic,
        exit_logic=invalid.exit_logic,
        invalidation_conditions=invalid.invalidation_conditions,
        risk_profile=invalid.risk_profile,
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d+60",
            bar_fields=invalid.required_data.bar_fields,
            min_history_bars=invalid.required_data.min_history_bars,
        ),
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert "required_data.timeframe must describe a single timeframe, got '1d+60'" in result.errors


def test_validate_edge_rejects_missing_feature_dependencies() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("dependency_gap_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis=invalid.hypothesis,
        feature_set=("atr_14",),
        regime_applicability=invalid.regime_applicability,
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("bull",), "Bull regime must be active."),
                EdgeCondition("atr_14", ">", 0.0, "ATR14 must be positive."),
            ),
        ),
        exit_logic=invalid.exit_logic,
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "not_in", ("bull",), "Fail closed outside bull regime."),
            ),
        ),
        risk_profile=invalid.risk_profile,
        required_data=EdgeRequiredData(
            universe=IMKBH_UNIVERSE,
            timeframe="1d",
            bar_fields=("close", "timestamp"),
            min_history_bars=60,
        ),
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert (
        "feature_set feature 'atr_14' requires bar_fields ('high', 'low', 'close'); missing ('high', 'low')"
        in result.errors
    )


def test_validate_edge_rejects_invalid_regime_transition_guard() -> None:
    registry = EdgeRegistry()
    invalid = _valid_edge("bad_regime_guard_edge")
    invalid = EdgeDefinition(
        edge_id=invalid.edge_id,
        hypothesis=invalid.hypothesis,
        feature_set=invalid.feature_set,
        regime_applicability=("bull",),
        entry_logic=EdgeLogic(
            match="all",
            conditions=(
                EdgeCondition("regime", "in", ("sideways",), "Wrong regime entry guard."),
                EdgeCondition("momentum_20", ">", 0.0, "Momentum must be positive."),
            ),
        ),
        exit_logic=invalid.exit_logic,
        invalidation_conditions=EdgeLogic(
            match="any",
            conditions=(
                EdgeCondition("regime", "in", ("bull",), "This does not guard transitions correctly."),
            ),
        ),
        risk_profile=invalid.risk_profile,
        required_data=invalid.required_data,
    )
    result = registry.validate_edge_structure(invalid)
    assert result.valid is False
    assert "entry_logic regime guard must be a subset of regime_applicability" in result.errors
    assert "invalidation_conditions regime guard must use 'not_in' or '!='" in result.errors