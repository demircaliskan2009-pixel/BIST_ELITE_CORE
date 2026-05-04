"""Deterministic Stage 4 paper-vs-backtest comparator foundation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from crypto_core.validation.walk_forward import WalkForwardWindow

_DAY_NS = 86400 * 1_000_000_000
_STATUS_PASS = "PASS"  # noqa: S105 - status label, not a credential.
_STATUS_REJECT = "REJECT"  # noqa: S105 - status label, not a credential.
_STATUS_INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # noqa: S105 - status label, not a credential.


@dataclass(frozen=True)
class Stage4BacktestBaseline:
    baseline_id: str
    edge_id: str
    as_of_ns: int
    backtest_sharpe: float
    backtest_hit_rate: float
    backtest_slippage_bps: float | None = None
    backtest_fill_rate: float | None = None
    source_window_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Stage4PaperSummary:
    paper_id: str
    edge_id: str
    started_at_ns: int
    stopped_at_ns: int
    paper_sharpe: float | None
    paper_hit_rate: float | None = None
    paper_slippage_bps: float | None = None
    paper_fill_rate: float | None = None
    paper_trade_count: int = 0

    @property
    def session_duration_days(self) -> float | None:
        if not _is_positive_int(self.started_at_ns) or not _is_positive_int(self.stopped_at_ns):
            return None
        if self.stopped_at_ns <= self.started_at_ns:
            return None
        return (self.stopped_at_ns - self.started_at_ns) / _DAY_NS


@dataclass(frozen=True)
class Stage4ComparisonResult:
    evaluated: bool
    passed: bool
    status: str
    baseline_id: str | None
    paper_id: str | None
    edge_id: str | None
    session_duration_days: float | None
    required_duration_days: float
    backtest_sharpe: float | None
    paper_sharpe: float | None
    required_min_paper_sharpe: float | None
    sharpe_retention_ratio: float | None
    paper_hit_rate: float | None
    backtest_hit_rate: float | None
    paper_slippage_bps: float | None
    backtest_slippage_bps: float | None
    paper_fill_rate: float | None
    backtest_fill_rate: float | None
    rejection_reasons: tuple[str, ...]


def _is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _is_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _is_rate(value: object) -> bool:
    return _is_finite_number(value) and 0.0 <= float(value) <= 1.0


def _is_non_negative_optional_number(value: object) -> bool:
    return value is None or (_is_finite_number(value) and float(value) >= 0.0)


def _is_string_tuple(value: object) -> bool:
    return isinstance(value, tuple) and all(_is_non_empty_str(item) for item in value)


def _string_or_none(value: object) -> str | None:
    return value if _is_non_empty_str(value) else None


def _float_or_none(value: object) -> float | None:
    return float(value) if _is_finite_number(value) else None


def _result(
    *,
    evaluated: bool,
    passed: bool,
    status: str,
    baseline: Stage4BacktestBaseline | None,
    paper: Stage4PaperSummary | None,
    required_duration_days: float,
    rejection_reasons: tuple[str, ...],
) -> Stage4ComparisonResult:
    backtest_sharpe = _float_or_none(getattr(baseline, "backtest_sharpe", None))
    paper_sharpe = _float_or_none(getattr(paper, "paper_sharpe", None))
    sharpe_retention_ratio = None
    if backtest_sharpe is not None and backtest_sharpe > 0.0:
        if paper_sharpe is not None:
            sharpe_retention_ratio = paper_sharpe / backtest_sharpe
    edge_id = _string_or_none(getattr(baseline, "edge_id", None))
    if edge_id is None:
        edge_id = _string_or_none(getattr(paper, "edge_id", None))
    return Stage4ComparisonResult(
        evaluated=evaluated,
        passed=passed,
        status=status,
        baseline_id=_string_or_none(getattr(baseline, "baseline_id", None)),
        paper_id=_string_or_none(getattr(paper, "paper_id", None)),
        edge_id=edge_id,
        session_duration_days=(paper.session_duration_days if isinstance(paper, Stage4PaperSummary) else None),
        required_duration_days=required_duration_days,
        backtest_sharpe=backtest_sharpe,
        paper_sharpe=paper_sharpe,
        required_min_paper_sharpe=None,
        sharpe_retention_ratio=sharpe_retention_ratio,
        paper_hit_rate=_float_or_none(getattr(paper, "paper_hit_rate", None)),
        backtest_hit_rate=_float_or_none(getattr(baseline, "backtest_hit_rate", None)),
        paper_slippage_bps=_float_or_none(getattr(paper, "paper_slippage_bps", None)),
        backtest_slippage_bps=_float_or_none(getattr(baseline, "backtest_slippage_bps", None)),
        paper_fill_rate=_float_or_none(getattr(paper, "paper_fill_rate", None)),
        backtest_fill_rate=_float_or_none(getattr(baseline, "backtest_fill_rate", None)),
        rejection_reasons=rejection_reasons,
    )


def _validate_baseline(baseline: Stage4BacktestBaseline | None) -> tuple[str, ...]:
    if not isinstance(baseline, Stage4BacktestBaseline):
        return ("stage4:backtest_baseline_malformed",)
    reasons: list[str] = []
    if not _is_non_empty_str(baseline.baseline_id):
        reasons.append("stage4:baseline_id_missing")
    if not _is_non_empty_str(baseline.edge_id):
        reasons.append("stage4:baseline_edge_id_missing")
    if not _is_positive_int(baseline.as_of_ns):
        reasons.append("stage4:baseline_as_of_invalid")
    if not _is_finite_number(baseline.backtest_sharpe) or float(baseline.backtest_sharpe) <= 0.0:
        reasons.append("stage4:backtest_sharpe_non_positive")
    if not _is_rate(baseline.backtest_hit_rate):
        reasons.append("stage4:backtest_hit_rate_invalid")
    if not _is_non_negative_optional_number(baseline.backtest_slippage_bps):
        reasons.append("stage4:backtest_slippage_invalid")
    if baseline.backtest_fill_rate is not None and not _is_rate(baseline.backtest_fill_rate):
        reasons.append("stage4:backtest_fill_rate_invalid")
    if not _is_string_tuple(baseline.source_window_ids):
        reasons.append("stage4:source_window_ids_invalid")
    return tuple(reasons)


def _validate_paper(paper: Stage4PaperSummary | None) -> tuple[str, ...]:
    if not isinstance(paper, Stage4PaperSummary):
        return ("stage4:paper_summary_malformed",)
    reasons: list[str] = []
    if not _is_non_empty_str(paper.paper_id):
        reasons.append("stage4:paper_id_missing")
    if not _is_non_empty_str(paper.edge_id):
        reasons.append("stage4:paper_edge_id_missing")
    if paper.session_duration_days is None:
        reasons.append("stage4:paper_time_invalid")
    if paper.paper_sharpe is None or not _is_finite_number(paper.paper_sharpe):
        reasons.append("stage4:paper_sharpe_not_computable")
    if paper.paper_hit_rate is not None and not _is_rate(paper.paper_hit_rate):
        reasons.append("stage4:paper_hit_rate_invalid")
    if not _is_non_negative_optional_number(paper.paper_slippage_bps):
        reasons.append("stage4:paper_slippage_invalid")
    if paper.paper_fill_rate is not None and not _is_rate(paper.paper_fill_rate):
        reasons.append("stage4:paper_fill_rate_invalid")
    if not _is_non_negative_int(paper.paper_trade_count):
        reasons.append("stage4:paper_trade_count_invalid")
    return tuple(reasons)


def _validate_thresholds(min_duration_days: float, min_sharpe_retention_ratio: float) -> tuple[str, ...]:
    reasons: list[str] = []
    if not _is_finite_number(min_duration_days) or float(min_duration_days) <= 0.0:
        reasons.append("stage4:min_duration_invalid")
    if not _is_finite_number(min_sharpe_retention_ratio) or float(min_sharpe_retention_ratio) < 0.0:
        reasons.append("stage4:min_sharpe_retention_ratio_invalid")
    return tuple(reasons)


def build_stage4_backtest_baseline(
    *,
    baseline_id: str,
    edge_id: str,
    as_of_ns: int,
    backtest_sharpe: float,
    backtest_hit_rate: float,
    backtest_slippage_bps: float | None = None,
    backtest_fill_rate: float | None = None,
    source_window_ids: tuple[str, ...] = (),
) -> Stage4BacktestBaseline:
    return Stage4BacktestBaseline(
        baseline_id=baseline_id,
        edge_id=edge_id,
        as_of_ns=as_of_ns,
        backtest_sharpe=backtest_sharpe,
        backtest_hit_rate=backtest_hit_rate,
        backtest_slippage_bps=backtest_slippage_bps,
        backtest_fill_rate=backtest_fill_rate,
        source_window_ids=tuple(source_window_ids),
    )


def build_stage4_backtest_baseline_from_windows(
    windows: tuple[WalkForwardWindow, ...] | list[WalkForwardWindow],
    *,
    baseline_id: str,
    edge_id: str,
    as_of_ns: int,
    backtest_slippage_bps: float | None = None,
    backtest_fill_rate: float | None = None,
) -> Stage4BacktestBaseline:
    ordered_windows = tuple(windows)
    valid_windows = tuple(
        window
        for window in ordered_windows
        if isinstance(window, WalkForwardWindow)
        and _is_finite_number(window.out_of_sample_sharpe)
        and _is_rate(window.out_of_sample_hit_rate)
    )
    if not valid_windows:
        raise ValueError("stage4: no valid OOS windows for baseline")
    backtest_sharpe = sum(float(window.out_of_sample_sharpe) for window in valid_windows) / len(valid_windows)
    backtest_hit_rate = sum(float(window.out_of_sample_hit_rate) for window in valid_windows) / len(valid_windows)
    return build_stage4_backtest_baseline(
        baseline_id=baseline_id,
        edge_id=edge_id,
        as_of_ns=as_of_ns,
        backtest_sharpe=backtest_sharpe,
        backtest_hit_rate=backtest_hit_rate,
        backtest_slippage_bps=backtest_slippage_bps,
        backtest_fill_rate=backtest_fill_rate,
        source_window_ids=tuple(window.window_id for window in valid_windows),
    )


def compare_stage4(
    baseline: Stage4BacktestBaseline | None,
    paper: Stage4PaperSummary | None,
    *,
    min_duration_days: float = 30.0,
    min_sharpe_retention_ratio: float = 0.5,
) -> Stage4ComparisonResult:
    required_duration_days = float(min_duration_days) if _is_finite_number(min_duration_days) else 0.0
    if baseline is None:
        return _result(
            evaluated=False,
            passed=False,
            status=_STATUS_INSUFFICIENT_EVIDENCE,
            baseline=baseline,
            paper=paper,
            required_duration_days=required_duration_days,
            rejection_reasons=("stage4:backtest_baseline_missing",),
        )
    if paper is None:
        return _result(
            evaluated=False,
            passed=False,
            status=_STATUS_INSUFFICIENT_EVIDENCE,
            baseline=baseline,
            paper=paper,
            required_duration_days=required_duration_days,
            rejection_reasons=("stage4:paper_summary_missing",),
        )

    threshold_reasons = _validate_thresholds(min_duration_days, min_sharpe_retention_ratio)
    baseline_reasons = _validate_baseline(baseline)
    paper_reasons = _validate_paper(paper)
    malformed_reasons = threshold_reasons + baseline_reasons + paper_reasons
    if malformed_reasons:
        return _result(
            evaluated=False,
            passed=False,
            status=_STATUS_INSUFFICIENT_EVIDENCE,
            baseline=baseline,
            paper=paper,
            required_duration_days=required_duration_days,
            rejection_reasons=malformed_reasons,
        )

    required_min_paper_sharpe = float(min_sharpe_retention_ratio) * float(baseline.backtest_sharpe)
    sharpe_retention_ratio = float(paper.paper_sharpe) / float(baseline.backtest_sharpe)

    if baseline.edge_id != paper.edge_id:
        return Stage4ComparisonResult(
            evaluated=True,
            passed=False,
            status=_STATUS_REJECT,
            baseline_id=baseline.baseline_id,
            paper_id=paper.paper_id,
            edge_id=baseline.edge_id,
            session_duration_days=paper.session_duration_days,
            required_duration_days=required_duration_days,
            backtest_sharpe=float(baseline.backtest_sharpe),
            paper_sharpe=float(paper.paper_sharpe),
            required_min_paper_sharpe=required_min_paper_sharpe,
            sharpe_retention_ratio=sharpe_retention_ratio,
            paper_hit_rate=_float_or_none(paper.paper_hit_rate),
            backtest_hit_rate=float(baseline.backtest_hit_rate),
            paper_slippage_bps=_float_or_none(paper.paper_slippage_bps),
            backtest_slippage_bps=_float_or_none(baseline.backtest_slippage_bps),
            paper_fill_rate=_float_or_none(paper.paper_fill_rate),
            backtest_fill_rate=_float_or_none(baseline.backtest_fill_rate),
            rejection_reasons=("stage4:edge_id_mismatch",),
        )

    if paper.session_duration_days is None or paper.session_duration_days < float(min_duration_days):
        return Stage4ComparisonResult(
            evaluated=True,
            passed=False,
            status=_STATUS_REJECT,
            baseline_id=baseline.baseline_id,
            paper_id=paper.paper_id,
            edge_id=baseline.edge_id,
            session_duration_days=paper.session_duration_days,
            required_duration_days=float(min_duration_days),
            backtest_sharpe=float(baseline.backtest_sharpe),
            paper_sharpe=float(paper.paper_sharpe),
            required_min_paper_sharpe=required_min_paper_sharpe,
            sharpe_retention_ratio=sharpe_retention_ratio,
            paper_hit_rate=_float_or_none(paper.paper_hit_rate),
            backtest_hit_rate=float(baseline.backtest_hit_rate),
            paper_slippage_bps=_float_or_none(paper.paper_slippage_bps),
            backtest_slippage_bps=_float_or_none(baseline.backtest_slippage_bps),
            paper_fill_rate=_float_or_none(paper.paper_fill_rate),
            backtest_fill_rate=_float_or_none(baseline.backtest_fill_rate),
            rejection_reasons=("stage4:duration_below_minimum",),
        )

    if float(paper.paper_sharpe) < required_min_paper_sharpe:
        return Stage4ComparisonResult(
            evaluated=True,
            passed=False,
            status=_STATUS_REJECT,
            baseline_id=baseline.baseline_id,
            paper_id=paper.paper_id,
            edge_id=baseline.edge_id,
            session_duration_days=paper.session_duration_days,
            required_duration_days=float(min_duration_days),
            backtest_sharpe=float(baseline.backtest_sharpe),
            paper_sharpe=float(paper.paper_sharpe),
            required_min_paper_sharpe=required_min_paper_sharpe,
            sharpe_retention_ratio=sharpe_retention_ratio,
            paper_hit_rate=_float_or_none(paper.paper_hit_rate),
            backtest_hit_rate=float(baseline.backtest_hit_rate),
            paper_slippage_bps=_float_or_none(paper.paper_slippage_bps),
            backtest_slippage_bps=_float_or_none(baseline.backtest_slippage_bps),
            paper_fill_rate=_float_or_none(paper.paper_fill_rate),
            backtest_fill_rate=_float_or_none(baseline.backtest_fill_rate),
            rejection_reasons=("stage4:paper_sharpe_below_backtest_threshold",),
        )

    return Stage4ComparisonResult(
        evaluated=True,
        passed=True,
        status=_STATUS_PASS,
        baseline_id=baseline.baseline_id,
        paper_id=paper.paper_id,
        edge_id=baseline.edge_id,
        session_duration_days=paper.session_duration_days,
        required_duration_days=float(min_duration_days),
        backtest_sharpe=float(baseline.backtest_sharpe),
        paper_sharpe=float(paper.paper_sharpe),
        required_min_paper_sharpe=required_min_paper_sharpe,
        sharpe_retention_ratio=sharpe_retention_ratio,
        paper_hit_rate=_float_or_none(paper.paper_hit_rate),
        backtest_hit_rate=float(baseline.backtest_hit_rate),
        paper_slippage_bps=_float_or_none(paper.paper_slippage_bps),
        backtest_slippage_bps=_float_or_none(baseline.backtest_slippage_bps),
        paper_fill_rate=_float_or_none(paper.paper_fill_rate),
        backtest_fill_rate=_float_or_none(baseline.backtest_fill_rate),
        rejection_reasons=(),
    )


def stage4_backtest_baseline_to_dict(baseline: Stage4BacktestBaseline) -> dict:
    return {
        "baseline_id": baseline.baseline_id,
        "edge_id": baseline.edge_id,
        "as_of_ns": baseline.as_of_ns,
        "backtest_sharpe": baseline.backtest_sharpe,
        "backtest_hit_rate": baseline.backtest_hit_rate,
        "backtest_slippage_bps": baseline.backtest_slippage_bps,
        "backtest_fill_rate": baseline.backtest_fill_rate,
        "source_window_ids": list(baseline.source_window_ids),
    }


def stage4_paper_summary_to_dict(paper: Stage4PaperSummary) -> dict:
    return {
        "paper_id": paper.paper_id,
        "edge_id": paper.edge_id,
        "started_at_ns": paper.started_at_ns,
        "stopped_at_ns": paper.stopped_at_ns,
        "session_duration_days": paper.session_duration_days,
        "paper_sharpe": paper.paper_sharpe,
        "paper_hit_rate": paper.paper_hit_rate,
        "paper_slippage_bps": paper.paper_slippage_bps,
        "paper_fill_rate": paper.paper_fill_rate,
        "paper_trade_count": paper.paper_trade_count,
    }


def stage4_comparison_result_to_dict(result: Stage4ComparisonResult) -> dict:
    return {
        "evaluated": result.evaluated,
        "passed": result.passed,
        "status": result.status,
        "baseline_id": result.baseline_id,
        "paper_id": result.paper_id,
        "edge_id": result.edge_id,
        "session_duration_days": result.session_duration_days,
        "required_duration_days": result.required_duration_days,
        "backtest_sharpe": result.backtest_sharpe,
        "paper_sharpe": result.paper_sharpe,
        "required_min_paper_sharpe": result.required_min_paper_sharpe,
        "sharpe_retention_ratio": result.sharpe_retention_ratio,
        "paper_hit_rate": result.paper_hit_rate,
        "backtest_hit_rate": result.backtest_hit_rate,
        "paper_slippage_bps": result.paper_slippage_bps,
        "backtest_slippage_bps": result.backtest_slippage_bps,
        "paper_fill_rate": result.paper_fill_rate,
        "backtest_fill_rate": result.backtest_fill_rate,
        "rejection_reasons": list(result.rejection_reasons),
    }


__all__ = [
    "Stage4BacktestBaseline",
    "Stage4PaperSummary",
    "Stage4ComparisonResult",
    "build_stage4_backtest_baseline",
    "build_stage4_backtest_baseline_from_windows",
    "compare_stage4",
    "stage4_backtest_baseline_to_dict",
    "stage4_paper_summary_to_dict",
    "stage4_comparison_result_to_dict",
]
