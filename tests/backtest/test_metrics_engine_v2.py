from __future__ import annotations

import json

import pytest

from bist_core.backtest.metrics_engine_v2 import MetricsEngineV2, export_metrics_to_json
from bist_core.providers.base import FailClosedError


def _trades() -> list[dict[str, float]]:
    return [
        {"pnl": 10.0},
        {"pnl": -5.0},
    ]


def _equity_curve() -> list[dict[str, float | int]]:
    return [
        {"timestamp": 1, "equity": 100.0},
        {"timestamp": 2, "equity": 110.0},
        {"timestamp": 3, "equity": 99.0},
    ]


def test_compute_metrics_returns_expected_values() -> None:
    engine = MetricsEngineV2()

    metrics = engine.compute_metrics(_trades(), _equity_curve())

    assert metrics == {
        "total_return": -0.01,
        "max_drawdown": 0.1,
        "sharpe_ratio": 0.0,
        "expectancy": 2.5,
        "win_rate": 0.5,
        "avg_win": 10.0,
        "avg_loss": 5.0,
        "profit_factor": 2.0,
        "trade_count": 2,
    }


def test_fail_on_empty_trades() -> None:
    engine = MetricsEngineV2()

    with pytest.raises(FailClosedError, match="invalid_trades:empty"):
        engine.compute_metrics([], _equity_curve())


def test_fail_on_invalid_equity_curve() -> None:
    engine = MetricsEngineV2()

    with pytest.raises(FailClosedError, match="invalid_equity_curve:non_monotonic_timestamp"):
        engine.compute_metrics(
            _trades(),
            [
                {"timestamp": 2, "equity": 100.0},
                {"timestamp": 2, "equity": 101.0},
            ],
        )


def test_export_metrics_to_json_writes_file(tmp_path) -> None:
    engine = MetricsEngineV2()
    metrics = engine.compute_metrics(_trades(), _equity_curve())

    output_path = export_metrics_to_json(metrics, output_path=tmp_path / "backtest_metrics_test.json")
    payload = json.loads(output_path.read_text(encoding="utf-8"))

    assert output_path.name == "backtest_metrics_test.json"
    assert payload == {
        "avg_loss": 5.0,
        "avg_win": 10.0,
        "expectancy": 2.5,
        "max_drawdown": 0.1,
        "profit_factor": 2.0,
        "sharpe_ratio": 0.0,
        "total_return": -0.01,
        "trade_count": 2,
        "win_rate": 0.5,
    }


def test_deterministic_output() -> None:
    first_engine = MetricsEngineV2()
    second_engine = MetricsEngineV2()

    first = first_engine.compute_metrics(_trades(), _equity_curve())
    second = second_engine.compute_metrics(_trades(), _equity_curve())

    assert first == second