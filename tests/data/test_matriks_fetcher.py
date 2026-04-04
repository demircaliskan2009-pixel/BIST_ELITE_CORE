"""Matriks fetcher unit tests — mocked HTTP, no real network."""

from __future__ import annotations

import gzip
import json
from unittest.mock import patch

import pytest

from bist_core.data.matriks_fetcher import fetch_bars

_SAMPLE_RAW = [
    {"symbol": "GARAN", "date": "2024-01-01", "open": 30.0, "high": 31.0, "low": 29.5, "close": 30.5, "volume": 1_000_000},
    {"symbol": "GARAN", "date": "2024-01-02", "open": 30.5, "high": 32.0, "low": 30.0, "close": 31.5, "volume": 1_200_000},
] * 10  # 20 bars


def _gzip_json(data: list) -> bytes:
    return gzip.compress(json.dumps(data).encode("utf-8"))


@pytest.fixture(autouse=True)
def _enable_network_and_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_CORE_NETWORK_ENABLED", "1")
    monkeypatch.setenv("MATRIKS_API_TOKEN", "test_token")


class TestFetchBars:
    def test_returns_more_than_10_bars(self) -> None:
        with patch("bist_core.data.matriks_fetcher.requests.get") as m:
            m.return_value.status_code = 200
            m.return_value.content = _gzip_json(_SAMPLE_RAW)
            m.return_value.text = ""
            bars = fetch_bars("GARAN")
        assert len(bars) > 10
        assert bars[0].symbol == "GARAN"
        assert bars[0].close == 30.5

    def test_raises_when_network_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIST_CORE_NETWORK_ENABLED", raising=False)
        with pytest.raises(Exception, match="MATRİKS DATA FETCH FAILED"):
            fetch_bars("GARAN")

    def test_raises_when_token_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MATRIKS_API_TOKEN", raising=False)
        with pytest.raises(Exception, match="MATRİKS DATA FETCH FAILED"):
            fetch_bars("GARAN")

    def test_raises_on_http_error(self) -> None:
        with patch("bist_core.data.matriks_fetcher.requests.get") as m:
            m.return_value.status_code = 403
            m.return_value.text = "Forbidden"
            with pytest.raises(Exception, match="MATRİKS ERROR"):
                fetch_bars("GARAN")

    def test_raises_on_empty_json_list(self) -> None:
        with patch("bist_core.data.matriks_fetcher.requests.get") as m:
            m.return_value.status_code = 200
            m.return_value.content = _gzip_json([])
            m.return_value.text = ""
            with pytest.raises(Exception, match="MATRİKS ERROR"):
                fetch_bars("GARAN")

    def test_accepts_plain_json(self) -> None:
        with patch("bist_core.data.matriks_fetcher.requests.get") as m:
            m.return_value.status_code = 200
            m.return_value.content = json.dumps(_SAMPLE_RAW).encode("utf-8")
            m.return_value.text = ""
            bars = fetch_bars("GARAN")
        assert len(bars) > 10
