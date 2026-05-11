from __future__ import annotations

import json
from pathlib import Path

import pytest

from bist_core.data import BISTCSVDataPipelineError, BISTCSVIngestionConfig, load_bist_csv_ohlcv


def _write_csv(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _write_calendar(tmp_path: Path, trading_days: list[str]) -> Path:
    path = tmp_path / "calendar.json"
    path.write_text(json.dumps({"trading_days": trading_days}, indent=2), encoding="utf-8")
    return path


def test_load_bist_csv_ohlcv_fails_on_missing_required_column(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "broken.csv",
        "date,open,high,low,volume\n2026-01-02,10,11,9,1000\n",
    )

    with pytest.raises(BISTCSVDataPipelineError) as exc_info:
        load_bist_csv_ohlcv(csv_path, config=BISTCSVIngestionConfig(symbol="ASELS"))

    assert exc_info.value.report.to_dict() == {
        "valid": False,
        "total_rows": 0,
        "anomalies": 0,
        "missing_days": 0,
        "warnings": [],
        "errors": ["missing required columns: ['close']"],
        "incomplete": False,
    }


def test_load_bist_csv_ohlcv_fails_on_unordered_data(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "unordered.csv",
        "date,open,high,low,close,volume\n"
        "2026-01-03,10,11,9,10.5,1000\n"
        "2026-01-02,10.5,11.5,10,11,1200\n",
    )

    with pytest.raises(BISTCSVDataPipelineError) as exc_info:
        load_bist_csv_ohlcv(csv_path, config=BISTCSVIngestionConfig(symbol="ASELS"))

    assert "unordered timestamps" in str(exc_info.value)
    assert exc_info.value.report.valid is False


def test_load_bist_csv_ohlcv_fails_on_negative_price(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "negative.csv",
        "date,open,high,low,close,volume\n"
        "2026-01-02,-10,11,9,10.5,1000\n",
    )

    with pytest.raises(BISTCSVDataPipelineError) as exc_info:
        load_bist_csv_ohlcv(csv_path, config=BISTCSVIngestionConfig(symbol="ASELS"))

    assert "zero_or_negative_price" in str(exc_info.value)
    assert exc_info.value.report.errors == ("row 2: zero_or_negative_price",)


def test_load_bist_csv_ohlcv_flags_anomaly_without_deleting_bar(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "anomaly.csv",
        "date,open,high,low,close,volume\n"
        "2026-01-02,10,11,9,10,1000\n"
        "2026-01-05,14,15,13,14.5,1100\n"
        "2026-01-06,14.4,14.8,14.0,14.2,1200\n",
    )
    calendar_path = _write_calendar(tmp_path, ["2026-01-02", "2026-01-05", "2026-01-06"])

    result = load_bist_csv_ohlcv(
        csv_path,
        config=BISTCSVIngestionConfig(symbol="ASELS", calendar_file=calendar_path),
    )

    assert result.report.valid is True
    assert result.report.anomalies == 1
    assert result.report.missing_days == 0
    assert len(result.bars) == 3
    assert result.anomalies[0].row_number == 3
    assert result.anomalies[0].reason == "daily_return_gt_30pct"


def test_load_bist_csv_ohlcv_warns_on_missing_trading_days(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "gaps.csv",
        "date,open,high,low,close,volume\n"
        "2026-01-02,10,11,9,10,1000\n"
        "2026-01-06,10.1,11.1,9.5,10.2,1100\n",
    )
    calendar_path = _write_calendar(tmp_path, ["2026-01-02", "2026-01-05", "2026-01-06"])

    result = load_bist_csv_ohlcv(
        csv_path,
        config=BISTCSVIngestionConfig(symbol="ASELS", calendar_file=calendar_path),
    )

    assert result.report.valid is True
    assert result.report.missing_days == 1
    assert result.report.incomplete is True
    assert result.report.warnings == (
        "missing_trading_days_between:2026-01-02:2026-01-06:2026-01-05",
    )


def test_load_bist_csv_ohlcv_is_deterministic(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path,
        "valid.csv",
        "date,open,high,low,close,volume\n"
        "2026-01-02,10,11,9,10,1000\n"
        "2026-01-05,10.1,11.1,9.5,10.2,1100\n"
        "2026-01-06,10.2,11.3,10.1,10.4,1200\n",
    )
    calendar_path = _write_calendar(tmp_path, ["2026-01-02", "2026-01-05", "2026-01-06"])
    config = BISTCSVIngestionConfig(symbol="ASELS", calendar_file=calendar_path)

    first = load_bist_csv_ohlcv(csv_path, config=config)
    second = load_bist_csv_ohlcv(csv_path, config=config)

    assert first.to_dict() == second.to_dict()
    assert first.report.valid is True
    assert [bar.timestamp for bar in first.bars] == [1767312000, 1767571200, 1767657600]