from __future__ import annotations

import pytest

from crypto_core.validation import WalkForwardWindow, validate_walk_forward


def _window(
    window_id: str,
    *,
    in_sample_sharpe: float = 2.0,
    out_of_sample_sharpe: float = 1.2,
    oos_expectancy: float = 1.0,
    in_sample_hit_rate: float = 60.0,
    out_of_sample_hit_rate: float = 55.0,
    trade_count: int = 25,
    evidence_count: int = 25,
    in_sample_max_drawdown: float = 0.10,
    oos_max_drawdown: float = 0.15,
    oos_profit_factor: float = 1.2,
) -> WalkForwardWindow:
    return WalkForwardWindow(
        window_id=window_id,
        in_sample_sharpe=in_sample_sharpe,
        out_of_sample_sharpe=out_of_sample_sharpe,
        oos_expectancy=oos_expectancy,
        in_sample_hit_rate=in_sample_hit_rate,
        out_of_sample_hit_rate=out_of_sample_hit_rate,
        trade_count=trade_count,
        evidence_count=evidence_count,
        in_sample_max_drawdown=in_sample_max_drawdown,
        oos_max_drawdown=oos_max_drawdown,
        oos_profit_factor=oos_profit_factor,
    )


def test_validate_walk_forward_supportive_three_window_pass():
    result = validate_walk_forward(
        (
            _window("wf-1"),
            _window("wf-2", in_sample_sharpe=1.8, out_of_sample_sharpe=1.0),
            _window("wf-3", in_sample_hit_rate=58.0, out_of_sample_hit_rate=49.0),
        )
    )
    assert result.supportive is True
    assert result.valid_oos_window_count == 3
    assert result.supportive_window_count == 3
    assert result.positive_expectancy_window_count == 3
    assert result.required_positive_expectancy_window_count == 2
    assert result.rejection_reasons == ()


def test_validate_walk_forward_two_of_three_positive_expectancy_passes():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_expectancy=1.0),
            _window("wf-2", oos_expectancy=-0.1),
            _window("wf-3", oos_expectancy=0.4),
        )
    )
    assert result.supportive is True
    assert result.positive_expectancy_window_count == 2
    assert result.required_positive_expectancy_window_count == 2
    assert result.window_results[1].expectancy_supportive is False
    assert result.rejection_reasons == ()


def test_validate_walk_forward_one_of_three_positive_expectancy_fails():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_expectancy=1.0),
            _window("wf-2", oos_expectancy=-0.1),
            _window("wf-3", oos_expectancy=-0.2),
        )
    )
    assert result.supportive is False
    assert result.positive_expectancy_window_count == 1
    assert result.required_positive_expectancy_window_count == 2
    assert result.rejection_reasons == ("insufficient_positive_expectancy_windows",)


def test_validate_walk_forward_three_of_four_requires_three_positive_windows():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_expectancy=1.0),
            _window("wf-2", oos_expectancy=0.7),
            _window("wf-3", oos_expectancy=0.0),
            _window("wf-4", oos_expectancy=-0.1),
        )
    )
    assert result.supportive is False
    assert result.valid_oos_window_count == 4
    assert result.positive_expectancy_window_count == 2
    assert result.required_positive_expectancy_window_count == 3
    assert result.rejection_reasons == ("insufficient_positive_expectancy_windows",)


def test_validate_walk_forward_zero_expectancy_counts_as_non_positive():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_expectancy=1.0),
            _window("wf-2", oos_expectancy=0.0),
            _window("wf-3", oos_expectancy=0.5),
        )
    )
    assert result.supportive is True
    assert result.positive_expectancy_window_count == 2
    assert result.required_positive_expectancy_window_count == 2
    assert result.window_results[1].expectancy_supportive is False


def test_validate_walk_forward_fewer_than_three_windows_fails_closed():
    result = validate_walk_forward((_window("wf-1"), _window("wf-2")))
    assert result.supportive is False
    assert result.valid_oos_window_count == 2
    assert result.rejection_reasons == ("insufficient_valid_oos_windows",)


@pytest.mark.parametrize(
    ("windows", "expected_reasons", "expected_valid_count"),
    [
        (
            (
                _window("wf-1"),
                _window("wf-2", in_sample_sharpe=2.0, out_of_sample_sharpe=0.99),
                _window("wf-3"),
            ),
            ("window[1]:oos_sharpe_below_ratio",),
            3,
        ),
        (
            (
                _window("wf-1"),
                _window("wf-2", in_sample_hit_rate=60.0, out_of_sample_hit_rate=49.9),
                _window("wf-3"),
            ),
            ("window[1]:oos_hit_rate_below_delta",),
            3,
        ),
        (
            (
                _window("wf-1"),
                _window("wf-2", trade_count=0, evidence_count=0),
                _window("wf-3"),
            ),
            (
                "window[1]:non_positive_trade_count",
                "window[1]:non_positive_evidence_count",
                "insufficient_valid_oos_windows",
            ),
            2,
        ),
        (
            (
                _window("wf-1"),
                None,
                _window("wf-3"),
                _window("wf-4"),
            ),
            ("window[1]:malformed",),
            3,
        ),
    ],
    ids=["sharpe", "hit-rate", "evidence", "malformed"],
)
def test_validate_walk_forward_rejects_expected_window_failures(
    windows: tuple[WalkForwardWindow | None, ...],
    expected_reasons: tuple[str, ...],
    expected_valid_count: int,
):
    result = validate_walk_forward(windows)
    assert result.supportive is False
    assert result.valid_oos_window_count == expected_valid_count
    assert result.rejection_reasons == expected_reasons


def test_validate_walk_forward_repeated_output_is_deterministic():
    windows = (_window("wf-1"), _window("wf-2"), _window("wf-3"))
    assert validate_walk_forward(windows) == validate_walk_forward(windows)


def test_validate_walk_forward_rejection_reasons_are_stable_and_ordered():
    result = validate_walk_forward(
        (
            _window("wf-1", trade_count=0, evidence_count=0, oos_expectancy=1.0),
            _window("wf-2", in_sample_sharpe=2.0, out_of_sample_sharpe=0.8, oos_expectancy=-0.1),
            _window("wf-3", in_sample_hit_rate=65.0, out_of_sample_hit_rate=54.0, oos_expectancy=-0.2),
        )
    )
    assert result.supportive is False
    assert result.rejection_reasons == (
        "window[0]:non_positive_trade_count",
        "window[0]:non_positive_evidence_count",
        "window[1]:oos_sharpe_below_ratio",
        "window[2]:oos_hit_rate_below_delta",
        "insufficient_valid_oos_windows",
        "insufficient_positive_expectancy_windows",
    )


def test_drawdown_within_limit_passes():
    # default oos_max_drawdown=0.15 < 2 * 0.10 = 0.20 → drawdown_safe for all windows
    result = validate_walk_forward((_window("wf-1"), _window("wf-2"), _window("wf-3")))
    assert result.supportive is True
    assert result.drawdown_safe_window_count == 3
    assert result.rejection_reasons == ()


def test_drawdown_exactly_2x_rejects():
    # 0.20 >= 2 * 0.10 = 0.20 → boundary rejects (not strictly less than)
    result = validate_walk_forward(
        (
            _window("wf-1", oos_max_drawdown=0.20),
            _window("wf-2"),
            _window("wf-3"),
        )
    )
    assert result.supportive is False
    assert result.window_results[0].drawdown_safe is False
    assert "window[0]:oos_drawdown_exceeds_limit" in result.rejection_reasons


def test_drawdown_above_2x_rejects():
    # 0.25 > 2 * 0.10 = 0.20 → rejects
    result = validate_walk_forward(
        (
            _window("wf-1", oos_max_drawdown=0.25),
            _window("wf-2"),
            _window("wf-3"),
        )
    )
    assert result.supportive is False
    assert result.drawdown_safe_window_count == 2
    assert "window[0]:oos_drawdown_exceeds_limit" in result.rejection_reasons


def test_in_sample_max_drawdown_zero_fails_closed():
    result = validate_walk_forward(
        (
            _window("wf-1", in_sample_max_drawdown=0.0),
            _window("wf-2"),
            _window("wf-3"),
        )
    )
    assert result.supportive is False
    assert result.valid_oos_window_count == 2
    assert "window[0]:malformed_in_sample_max_drawdown" in result.rejection_reasons


def test_negative_oos_max_drawdown_fails_closed():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_max_drawdown=-0.01),
            _window("wf-2"),
            _window("wf-3"),
        )
    )
    assert result.supportive is False
    assert result.valid_oos_window_count == 2
    assert "window[0]:malformed_oos_max_drawdown" in result.rejection_reasons


def test_profit_factor_two_of_three_passes():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_profit_factor=1.5),
            _window("wf-2", oos_profit_factor=0.8),
            _window("wf-3", oos_profit_factor=1.1),
        )
    )
    assert result.supportive is True
    assert result.positive_profit_factor_window_count == 2
    assert result.required_positive_profit_factor_window_count == 2
    assert result.rejection_reasons == ()


def test_profit_factor_one_of_three_fails():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_profit_factor=1.5),
            _window("wf-2", oos_profit_factor=0.8),
            _window("wf-3", oos_profit_factor=0.9),
        )
    )
    assert result.supportive is False
    assert result.positive_profit_factor_window_count == 1
    assert result.required_positive_profit_factor_window_count == 2
    assert result.rejection_reasons == ("insufficient_profit_factor_windows",)


def test_profit_factor_three_of_four_requires_three_windows():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_profit_factor=1.5),
            _window("wf-2", oos_profit_factor=1.1),
            _window("wf-3", oos_profit_factor=0.9),
            _window("wf-4", oos_profit_factor=0.8),
        )
    )
    assert result.supportive is False
    assert result.valid_oos_window_count == 4
    assert result.positive_profit_factor_window_count == 2
    assert result.required_positive_profit_factor_window_count == 3
    assert result.rejection_reasons == ("insufficient_profit_factor_windows",)


def test_profit_factor_exactly_1_0_boundary_is_non_supportive():
    # exactly 1.0 is NOT > 1.0 → not profit_factor_supportive
    result = validate_walk_forward(
        (
            _window("wf-1", oos_profit_factor=1.5),
            _window("wf-2", oos_profit_factor=1.0),
            _window("wf-3", oos_profit_factor=1.2),
        )
    )
    assert result.supportive is True  # wf-1 and wf-3 pass: 2 >= ceil(3*2/3)=2
    assert result.positive_profit_factor_window_count == 2
    assert result.required_positive_profit_factor_window_count == 2
    assert result.window_results[1].profit_factor_supportive is False
    assert result.rejection_reasons == ()


def test_drawdown_and_profit_factor_compound_rejection_reasons_ordered():
    result = validate_walk_forward(
        (
            _window("wf-1", oos_max_drawdown=0.25, oos_profit_factor=0.8),
            _window("wf-2", oos_profit_factor=0.9),
            _window("wf-3"),
        )
    )
    assert result.supportive is False
    assert result.rejection_reasons == (
        "window[0]:oos_drawdown_exceeds_limit",
        "insufficient_profit_factor_windows",
    )
    assert result.drawdown_safe_window_count == 2
    assert result.positive_profit_factor_window_count == 1
    assert result.required_positive_profit_factor_window_count == 2
