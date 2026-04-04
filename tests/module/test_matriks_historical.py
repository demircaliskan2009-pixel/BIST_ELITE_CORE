"""Tests for Matriks historical ingestion (mocked HTTP, deterministic)."""

from __future__ import annotations

import os
from datetime import date
from unittest.mock import MagicMock, patch

from bist_core.data.matriks_historical import MatriksHistorical
from bist_core.models.ohlcv import OHLCVBar


def _row(ts: int, close: float = 10.5, vol: float = 1000.0) -> dict:
    return {
        "t": ts,
        "o": close - 0.1,
        "h": close + 0.2,
        "l": close - 0.2,
        "c": close,
        "v": vol,
    }


def _make_day_rows(start_ts: int, n: int) -> list[dict]:
    return [_row(start_ts + i, 10.0 + (i % 5) * 0.01) for i in range(n)]


def test_disabled_returns_empty() -> None:
    with patch.dict(os.environ, {"MATRIKS_ENABLED": "0", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        assert mh.fetch_bars("ASELS", date(2024, 1, 1), date(2024, 1, 3)) == []


def test_no_token_returns_empty() -> None:
    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": ""}):
        mh = MatriksHistorical()
        assert mh.fetch_bars("ASELS", date(2024, 1, 1), date(2024, 1, 3)) == []


def test_under_200_bars_returns_empty() -> None:
    """Fail-closed: merged bars must be >= 200."""
    day1 = _make_day_rows(1_700_000_000, 50)
    day2 = _make_day_rows(1_700_008_640, 50)
    responses = [
        MagicMock(status_code=200, json=lambda: {"data": day1}),
        MagicMock(status_code=200, json=lambda: {"data": day2}),
    ]

    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        with patch("requests.get", side_effect=responses):
            out = mh.fetch_bars("ASELS", date(2024, 1, 1), date(2024, 1, 2))
    assert out == []


def test_success_dedup_sort_cache() -> None:
    """3 days × 70 rows = 210; dedupe by timestamp; sorted ascending."""
    days: list[list[dict]] = []
    base = 1_700_000_000
    for d in range(3):
        days.append(_make_day_rows(base + d * 100_000, 70))

    responses: list[MagicMock] = []
    for i in range(3):
        m = MagicMock(status_code=200)
        m.json = lambda i=i: {"data": days[i]}
        responses.append(m)

    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        with patch("requests.get", side_effect=responses) as rg:
            out = mh.fetch_bars("ASELS", date(2024, 1, 1), date(2024, 1, 3))
        assert rg.call_count == 3

    assert len(out) == 210
    ts_vals = [int(b.timestamp) for b in out]
    assert ts_vals == sorted(ts_vals)
    assert all(b.symbol == "ASELS" for b in out)

    key = ("ASELS", "2024-01-01", "2024-01-03", "1m")
    assert key in mh.cache
    out2 = mh.fetch_bars("ASELS", date(2024, 1, 1), date(2024, 1, 3))
    assert out2 == out


def test_invalid_row_fails_closed() -> None:
    bad = _make_day_rows(1, 70)
    bad[10]["c"] = -1.0
    responses = [
        MagicMock(status_code=200, json=lambda: {"data": bad}),
        MagicMock(status_code=200, json=lambda: _make_day_rows(100_000, 70)),
        MagicMock(status_code=200, json=lambda: _make_day_rows(200_000, 70)),
    ]

    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        with patch("requests.get", side_effect=responses):
            out = mh.fetch_bars("X", date(2024, 1, 1), date(2024, 1, 3))
    assert out == []


def test_list_response_parsed() -> None:
    rows = _make_day_rows(1, 200)
    r = MagicMock(status_code=200, json=lambda: rows)

    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        with patch("requests.get", return_value=r):
            out = mh.fetch_bars("GARAN", date(2024, 6, 1), date(2024, 6, 1))

    assert len(out) == 200
    assert isinstance(out[0], OHLCVBar)


def test_http_error_fails_closed() -> None:
    r = MagicMock(status_code=500)
    with patch.dict(os.environ, {"MATRIKS_ENABLED": "1", "MATRIKS_TOKEN": "tok"}):
        mh = MatriksHistorical()
        with patch("requests.get", return_value=r):
            out = mh.fetch_bars("X", date(2024, 1, 1), date(2024, 1, 1))
    assert out == []
