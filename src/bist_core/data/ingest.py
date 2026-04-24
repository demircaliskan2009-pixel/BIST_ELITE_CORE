"""Deterministic OHLCV CSV ingest — stdlib only, no pandas.

Reads CSV with required columns: timestamp, open, high, low, close, volume.
Converts to list[OHLCVBar]. Fail-closed on any validation issue.

Also re-exports read_csv, register_dataset, load_registered_dataset from local_csv.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from bist_core.backtest.backtest_engine import OHLCVBar
from bist_core.models.ohlcv import OHLCVBar as CanonicalOHLCVBar
from bist_core.providers.base import FailClosedError
from bist_core.services.trading_calendar import is_trading_day

from .local_csv import (
    load_registered_dataset,
    read_csv,
    register_dataset,
)


REQUIRED_COLUMNS = ("timestamp", "open", "high", "low", "close", "volume")
STRICT_REQUIRED_PRICE_COLUMNS = ("open", "high", "low", "close", "volume")


class InvalidDataError(FailClosedError):
    """Raised when CSV data fails validation (schema, values, or ordering)."""

    pass


@dataclass(frozen=True)
class BISTDataQualityReport:
    valid: bool
    total_rows: int
    anomalies: int
    missing_days: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "total_rows": self.total_rows,
            "anomalies": self.anomalies,
            "missing_days": self.missing_days,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "incomplete": self.incomplete,
        }


@dataclass(frozen=True)
class BISTCSVAnomaly:
    row_number: int
    timestamp: int
    return_pct: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_number": self.row_number,
            "timestamp": self.timestamp,
            "return_pct": self.return_pct,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class BISTCSVDataPipelineResult:
    bars: tuple[CanonicalOHLCVBar, ...]
    report: BISTDataQualityReport
    anomalies: tuple[BISTCSVAnomaly, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "bars": [
                {
                    "timestamp": bar.timestamp,
                    "symbol": bar.symbol,
                    "open": bar.open,
                    "high": bar.high,
                    "low": bar.low,
                    "close": bar.close,
                    "volume": bar.volume,
                }
                for bar in self.bars
            ],
            "report": self.report.to_dict(),
            "anomalies": [item.to_dict() for item in self.anomalies],
        }

    def to_data_stage_contract(self) -> dict[str, Any]:
        symbol = self.bars[0].symbol if self.bars else ""
        return {
            "stage": "data",
            "status": "SAFE" if self.report.valid else "UNSAFE",
            "dataset_scope": {
                "symbols": [symbol] if symbol else [],
                "symbol_count": 1 if symbol else 0,
                "universe": "BIST",
                "timeframe": "1d",
                "granularity": "1d",
            },
            "ohlcv_schema": {
                "columns": ["timestamp", "symbol", "open", "high", "low", "close", "volume"],
            },
            "validation_summary": f"rows={self.report.total_rows}; anomalies={self.report.anomalies}; missing_days={self.report.missing_days}",
            "anomaly_summary": "none" if not self.report.warnings else "; ".join(self.report.warnings),
            "validation_evidence": "strict_csv_validation_passed" if self.report.valid else "strict_csv_validation_failed",
            "next_action": "admit_to_backtest" if self.report.valid else "repair_input_csv",
            "blocking_reason": None if self.report.valid else "; ".join(self.report.errors),
        }


class BISTCSVDataPipelineError(InvalidDataError):
    """Fail-closed exception for strict BIST CSV pipeline admission."""

    def __init__(self, message: str, report: BISTDataQualityReport) -> None:
        super().__init__(message)
        self.report = report


@dataclass(frozen=True)
class BISTCSVIngestionConfig:
    symbol: str | None = None
    calendar_file: str | Path | None = None
    daily_return_anomaly_threshold: float = 0.30


def _failed_report(*, total_rows: int, errors: list[str], warnings: list[str] | None = None) -> BISTDataQualityReport:
    return BISTDataQualityReport(
        valid=False,
        total_rows=int(total_rows),
        anomalies=0,
        missing_days=0,
        warnings=tuple(warnings or ()),
        errors=tuple(errors),
        incomplete=False,
    )


def _normalize_headers(fieldnames: list[str] | None) -> dict[str, str]:
    if fieldnames is None:
        return {}
    normalized: dict[str, str] = {}
    for original in fieldnames:
        token = str(original or "").strip().casefold()
        if token:
            normalized[token] = original
    return normalized


def _resolve_column(headers: dict[str, str], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        token = alias.casefold()
        if token in headers:
            return headers[token]
    return None


def _parse_timestamp_value(raw: str, row_number: int) -> int:
    value = str(raw or "").strip()
    if not value:
        raise BISTCSVDataPipelineError(
            f"row {row_number}: empty timestamp",
            _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: empty timestamp"]),
        )

    try:
        numeric = float(value.replace(",", "."))
    except ValueError:
        numeric = None

    if numeric is not None:
        if not math.isfinite(numeric):
            raise BISTCSVDataPipelineError(
                f"row {row_number}: invalid timestamp",
                _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: invalid timestamp"]),
            )
        integer_value = int(numeric)
        if abs(numeric - integer_value) > 1e-9:
            raise BISTCSVDataPipelineError(
                f"row {row_number}: timestamp must be integer-valued",
                _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: timestamp must be integer-valued"]),
            )
        return integer_value

    timestamp_candidate = value.replace("Z", "+00:00")
    try:
        parsed_dt = datetime.fromisoformat(timestamp_candidate)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(timestamp_candidate)
        except ValueError as exc:
            raise BISTCSVDataPipelineError(
                f"row {row_number}: invalid timestamp {raw!r}",
                _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: invalid timestamp {raw!r}"]),
            ) from exc
        parsed_dt = datetime.combine(parsed_date, time.min, tzinfo=timezone.utc)
    else:
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else:
            parsed_dt = parsed_dt.astimezone(timezone.utc)
    return int(parsed_dt.timestamp())


def _parse_numeric_value(raw: str, *, field_name: str, row_number: int) -> float:
    value = str(raw or "").strip().replace(",", ".")
    if not value:
        raise BISTCSVDataPipelineError(
            f"row {row_number}: empty {field_name}",
            _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: empty {field_name}"]),
        )
    try:
        numeric = float(value)
    except ValueError as exc:
        raise BISTCSVDataPipelineError(
            f"row {row_number}: invalid {field_name} {raw!r}",
            _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: invalid {field_name} {raw!r}"]),
        ) from exc
    if not math.isfinite(numeric):
        raise BISTCSVDataPipelineError(
            f"row {row_number}: non-finite {field_name}",
            _failed_report(total_rows=row_number - 1, errors=[f"row {row_number}: non-finite {field_name}"]),
        )
    return numeric


def _resolve_symbol(rows: list[dict[str, str]], headers: dict[str, str], config: BISTCSVIngestionConfig) -> str:
    explicit_symbol = str(config.symbol or "").strip().upper()
    if explicit_symbol:
        return explicit_symbol

    symbol_column = _resolve_column(headers, ("symbol",))
    if symbol_column is None:
        raise BISTCSVDataPipelineError(
            "missing symbol: provide symbol argument or stable symbol column",
            _failed_report(total_rows=len(rows), errors=["missing symbol: provide symbol argument or stable symbol column"]),
        )

    symbols = sorted({str(row.get(symbol_column, "") or "").strip().upper() for row in rows if str(row.get(symbol_column, "") or "").strip()})
    if len(symbols) != 1:
        raise BISTCSVDataPipelineError(
            "symbol column must contain exactly one stable symbol",
            _failed_report(total_rows=len(rows), errors=["symbol column must contain exactly one stable symbol"]),
        )
    return symbols[0]


def _detect_missing_days(
    bars: list[CanonicalOHLCVBar],
    *,
    calendar_file: Path | None,
) -> tuple[int, list[str]]:
    if len(bars) < 2:
        return 0, []

    missing_days = 0
    warnings: list[str] = []
    for previous, current in zip(bars, bars[1:]):
        previous_day = datetime.fromtimestamp(previous.timestamp, tz=timezone.utc).date()
        current_day = datetime.fromtimestamp(current.timestamp, tz=timezone.utc).date()
        candidate = previous_day + timedelta(days=1)
        gap_days: list[str] = []
        while candidate < current_day:
            candidate_str = candidate.isoformat()
            is_open, _, _, _ = is_trading_day(candidate_str, calendar_file)
            if is_open:
                gap_days.append(candidate_str)
            candidate += timedelta(days=1)
        if gap_days:
            missing_days += len(gap_days)
            warnings.append(
                f"missing_trading_days_between:{previous_day.isoformat()}:{current_day.isoformat()}:{','.join(gap_days)}"
            )
    return missing_days, warnings


def load_bist_csv_ohlcv(
    path: str | Path,
    *,
    config: BISTCSVIngestionConfig | None = None,
) -> BISTCSVDataPipelineResult:
    config = config or BISTCSVIngestionConfig()
    csv_path = Path(path)
    if not csv_path.exists():
        report = _failed_report(total_rows=0, errors=[f"file not found: {csv_path}"])
        raise BISTCSVDataPipelineError(f"file not found: {csv_path}", report)

    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = _normalize_headers(reader.fieldnames)
        if not headers:
            report = _failed_report(total_rows=0, errors=["CSV has no header"])
            raise BISTCSVDataPipelineError("CSV has no header", report)

        timestamp_column = _resolve_column(headers, ("timestamp", "date"))
        missing_columns = [
            column
            for column in STRICT_REQUIRED_PRICE_COLUMNS
            if _resolve_column(headers, (column,)) is None
        ]
        if timestamp_column is None:
            missing_columns.insert(0, "timestamp/date")
        if missing_columns:
            report = _failed_report(total_rows=0, errors=[f"missing required columns: {missing_columns}"])
            raise BISTCSVDataPipelineError(f"missing required columns: {missing_columns}", report)

        rows = [dict(row) for row in reader]

    if not rows:
        report = _failed_report(total_rows=0, errors=["empty dataset"])
        raise BISTCSVDataPipelineError("empty dataset", report)

    symbol = _resolve_symbol(rows, headers, config)
    calendar_path = Path(config.calendar_file) if config.calendar_file is not None else None
    if calendar_path is not None and not calendar_path.exists():
        report = _failed_report(total_rows=len(rows), errors=[f"calendar file not found: {calendar_path}"])
        raise BISTCSVDataPipelineError(f"calendar file not found: {calendar_path}", report)

    open_column = _resolve_column(headers, ("open",))
    high_column = _resolve_column(headers, ("high",))
    low_column = _resolve_column(headers, ("low",))
    close_column = _resolve_column(headers, ("close",))
    volume_column = _resolve_column(headers, ("volume",))
    assert timestamp_column is not None
    assert open_column is not None
    assert high_column is not None
    assert low_column is not None
    assert close_column is not None
    assert volume_column is not None

    bars: list[CanonicalOHLCVBar] = []
    anomalies: list[BISTCSVAnomaly] = []
    previous_timestamp: int | None = None
    previous_close: float | None = None

    for index, row in enumerate(rows, start=2):
        timestamp = _parse_timestamp_value(row.get(timestamp_column, ""), index)
        open_price = _parse_numeric_value(row.get(open_column, ""), field_name="open", row_number=index)
        high_price = _parse_numeric_value(row.get(high_column, ""), field_name="high", row_number=index)
        low_price = _parse_numeric_value(row.get(low_column, ""), field_name="low", row_number=index)
        close_price = _parse_numeric_value(row.get(close_column, ""), field_name="close", row_number=index)
        volume = _parse_numeric_value(row.get(volume_column, ""), field_name="volume", row_number=index)

        if open_price <= 0.0 or high_price <= 0.0 or low_price <= 0.0 or close_price <= 0.0:
            report = _failed_report(total_rows=len(rows), errors=[f"row {index}: zero_or_negative_price"])
            raise BISTCSVDataPipelineError(f"row {index}: zero_or_negative_price", report)
        if volume < 0.0:
            report = _failed_report(total_rows=len(rows), errors=[f"row {index}: negative_volume"])
            raise BISTCSVDataPipelineError(f"row {index}: negative_volume", report)
        if high_price < low_price or high_price < open_price or high_price < close_price:
            report = _failed_report(total_rows=len(rows), errors=[f"row {index}: invalid price logic: high bound violation"])
            raise BISTCSVDataPipelineError(f"row {index}: invalid price logic: high bound violation", report)
        if low_price > open_price or low_price > close_price:
            report = _failed_report(total_rows=len(rows), errors=[f"row {index}: invalid price logic: low bound violation"])
            raise BISTCSVDataPipelineError(f"row {index}: invalid price logic: low bound violation", report)
        if previous_timestamp is not None and timestamp <= previous_timestamp:
            reason = "duplicate timestamp" if timestamp == previous_timestamp else "unordered timestamps"
            report = _failed_report(total_rows=len(rows), errors=[f"row {index}: {reason}"])
            raise BISTCSVDataPipelineError(f"row {index}: {reason}", report)

        if previous_close is not None:
            daily_return = (close_price / previous_close) - 1.0
            if abs(daily_return) > config.daily_return_anomaly_threshold:
                anomalies.append(
                    BISTCSVAnomaly(
                        row_number=index,
                        timestamp=timestamp,
                        return_pct=round(daily_return, 6),
                        reason="daily_return_gt_30pct",
                    )
                )

        bars.append(
            CanonicalOHLCVBar(
                timestamp=timestamp,
                symbol=symbol,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
            )
        )
        previous_timestamp = timestamp
        previous_close = close_price

    missing_days, gap_warnings = _detect_missing_days(bars, calendar_file=calendar_path)
    warnings = list(gap_warnings)
    if anomalies:
        warnings.append(f"anomaly_count={len(anomalies)}")

    report = BISTDataQualityReport(
        valid=True,
        total_rows=len(rows),
        anomalies=len(anomalies),
        missing_days=missing_days,
        warnings=tuple(warnings),
        errors=(),
        incomplete=missing_days > 0,
    )
    return BISTCSVDataPipelineResult(
        bars=tuple(bars),
        report=report,
        anomalies=tuple(anomalies),
    )


def _parse_timestamp(s: str) -> int:
    """Parse timestamp string to int (Unix epoch)."""
    v = str(s).strip().replace(",", ".")
    if not v:
        raise InvalidDataError("empty timestamp")
    try:
        f = float(v)
        i = int(f)
        if i != f and abs(f - i) > 1e-9:
            raise InvalidDataError("timestamp must be integer")
        return i
    except (ValueError, OverflowError) as e:
        raise InvalidDataError(f"invalid timestamp: {s!r}") from e


def _parse_float(s: str, name: str) -> float:
    """Parse string to float."""
    v = str(s).strip().replace(",", ".")
    if v == "":
        raise InvalidDataError(f"empty {name}")
    try:
        return float(v)
    except ValueError as e:
        raise InvalidDataError(f"invalid {name}: {s!r}") from e


def ingest_ohlcv_from_file(path: str) -> list[OHLCVBar]:
    """Read OHLCV CSV and return sorted list of OHLCVBar.

    Requirements:
    - Required columns: timestamp, open, high, low, close, volume
    - timestamp -> int (Unix epoch)
    - open, high, low, close, volume -> float
    - Non-empty
    - Strictly increasing timestamps
    - All prices > 0
    - volume >= 0

    Raises InvalidDataError on any issue.
    """
    p = Path(path)
    if not p.exists():
        raise InvalidDataError(f"file not found: {path}")

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise InvalidDataError("CSV has no header")

        cols = [c.strip() for c in reader.fieldnames if c]
        missing = [c for c in REQUIRED_COLUMNS if c not in cols]
        if missing:
            raise InvalidDataError(f"missing required columns: {missing}")

        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(dict(row))

    if not rows:
        raise InvalidDataError("empty file")

    bars: list[tuple[int, OHLCVBar]] = []
    for i, row in enumerate(rows):
        try:
            ts = _parse_timestamp(row.get("timestamp", ""))
            o = _parse_float(row.get("open", ""), "open")
            h = _parse_float(row.get("high", ""), "high")
            lo = _parse_float(row.get("low", ""), "low")
            c = _parse_float(row.get("close", ""), "close")
            v = _parse_float(row.get("volume", ""), "volume")
        except InvalidDataError:
            raise
        except Exception as e:
            raise InvalidDataError(f"row {i + 2}: {e}") from e

        if o <= 0 or h <= 0 or lo <= 0 or c <= 0:
            raise InvalidDataError(f"row {i + 2}: all prices must be > 0")
        if v < 0:
            raise InvalidDataError(f"row {i + 2}: volume must be >= 0")

        bar = OHLCVBar(
            timestamp=str(ts),
            symbol="",
            open=o,
            high=h,
            low=lo,
            close=c,
            volume=v,
        )
        bars.append((ts, bar))

    bars.sort(key=lambda x: x[0])

    for i in range(1, len(bars)):
        if bars[i][0] <= bars[i - 1][0]:
            raise InvalidDataError(
                f"timestamps must be strictly increasing: {bars[i - 1][0]} then {bars[i][0]}"
            )

    return [b for _, b in bars]


__all__ = [
    "BISTCSVAnomaly",
    "BISTCSVDataPipelineError",
    "BISTCSVDataPipelineResult",
    "BISTCSVIngestionConfig",
    "BISTDataQualityReport",
    "InvalidDataError",
    "ingest_ohlcv_from_file",
    "load_registered_dataset",
    "load_bist_csv_ohlcv",
    "read_csv",
    "register_dataset",
]
