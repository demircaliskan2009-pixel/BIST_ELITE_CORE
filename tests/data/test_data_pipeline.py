"""Data pipeline unit tests — symbol loading, dataset building, cache, ordering, errors."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from bist_core.data.data_pipeline import (
    build_dataset,
    fetch_symbol_history,
    load_symbols,
    _cache_key,
    _read_cache,
    _write_cache,
)
from bist_core.data.matriks_client import (
    MatriksAPIError,
    MatriksClient,
    NetworkDisabledError,
)
from bist_core.backtest.backtest_engine import OHLCVBar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE_RAW = [
    {"symbol": "GARAN", "date": "2026-01-15", "open": 30.5, "high": 31.0, "low": 30.0, "close": 30.8, "volume": 1_000_000},
    {"symbol": "GARAN", "date": "2026-01-16", "open": 30.8, "high": 32.0, "low": 30.5, "close": 31.5, "volume": 1_200_000},
]


def _mock_response(body, status=200):
    encoded = json.dumps(body).encode("utf-8") if not isinstance(body, bytes) else body
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = encoded
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


@pytest.fixture(autouse=True)
def _enable_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BIST_CORE_NETWORK_ENABLED", "1")


# ── Symbol loading ────────────────────────────────────────────────────────

class TestLoadSymbols:
    def test_offline_from_raw_list(self) -> None:
        syms = load_symbols(raw_symbols=["garan.e", "THYAO", "akbnk.IS", ""])
        assert syms == ["AKBNK", "GARAN", "THYAO"]

    def test_offline_deduplicates(self) -> None:
        syms = load_symbols(raw_symbols=["GARAN", "garan", "GARAN.E"])
        assert syms == ["GARAN"]

    def test_offline_empty(self) -> None:
        assert load_symbols(raw_symbols=[]) == []

    def test_network_list_response(self) -> None:
        resp = _mock_response(["GARAN", "THYAO", "AKBNK"])
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            syms = load_symbols(client=MatriksClient(token="t"))
            assert syms == ["AKBNK", "GARAN", "THYAO"]

    def test_network_dict_response(self) -> None:
        resp = _mock_response({"symbols": [{"symbol": "ASELS"}, {"ticker": "EREGL"}]})
        with patch("bist_core.data.matriks_client.urlopen", return_value=resp):
            syms = load_symbols(client=MatriksClient(token="t"))
            assert syms == ["ASELS", "EREGL"]

    def test_network_error_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIST_CORE_NETWORK_ENABLED", raising=False)
        syms = load_symbols()
        assert syms == []


# ── Dataset building ──────────────────────────────────────────────────────

class TestBuildDataset:
    def test_build_dataset_single_symbol(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_RAW)):
            ds = build_dataset(["GARAN"], "2026-01-15", "2026-01-16", client=MatriksClient(token="t"))
            assert "GARAN" in ds
            assert len(ds["GARAN"]) == 2

    def test_build_dataset_multiple_symbols(self) -> None:
        bars_a = [{"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
        bars_b = [{"symbol": "B", "date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 200}]

        call_count = {"n": 0}
        def mock_urlopen(*args, **kwargs):
            call_count["n"] += 1
            data = bars_a if call_count["n"] == 1 else bars_b
            return _mock_response(data)

        with patch("bist_core.data.matriks_client.urlopen", side_effect=mock_urlopen):
            ds = build_dataset(["A", "B"], "2026-01-01", "2026-01-01", client=MatriksClient(token="t"))
            assert "A" in ds
            assert "B" in ds

    def test_build_dataset_skips_failed_symbol(self) -> None:
        def mock_urlopen(*args, **kwargs):
            raise MatriksAPIError("Server error", status_code=500)

        with patch("bist_core.data.matriks_client.urlopen", side_effect=mock_urlopen):
            ds = build_dataset(["FAIL"], "2026-01-01", "2026-01-31", client=MatriksClient(token="t"))
            assert ds == {}

    def test_build_dataset_skips_empty_symbol(self) -> None:
        ds = build_dataset(["", "   "], "2026-01-01", "2026-01-31")
        assert ds == {}

    def test_build_dataset_deduplicates_symbols(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_RAW)):
            ds = build_dataset(["GARAN", "garan"], "2026-01-15", "2026-01-16", client=MatriksClient(token="t"))
            assert len(ds) == 1
            assert "GARAN" in ds


# ── Cache behavior ────────────────────────────────────────────────────────

class TestCacheBehavior:
    def test_cache_key_format(self) -> None:
        key = _cache_key("GARAN", "1d", "2026-01-01", "2026-01-31")
        assert key == "GARAN_1d_2026-01-01_2026-01-31.json"

    def test_write_and_read_cache(self, tmp_path: Path) -> None:
        bars = [
            OHLCVBar("2026-01-01", "X", 1.0, 2.0, 0.5, 1.5, 100.0),
            OHLCVBar("2026-01-02", "X", 1.5, 2.5, 1.0, 2.0, 200.0),
        ]
        _write_cache(tmp_path, "test.json", bars)
        cached = _read_cache(tmp_path, "test.json")
        assert cached is not None
        assert len(cached) == 2
        assert cached[0]["symbol"] == "X"

    def test_read_cache_missing(self, tmp_path: Path) -> None:
        assert _read_cache(tmp_path, "nonexistent.json") is None

    def test_read_cache_corrupt(self, tmp_path: Path) -> None:
        (tmp_path / "bad.json").write_text("not valid json{{{", encoding="utf-8")
        assert _read_cache(tmp_path, "bad.json") is None

    def test_build_dataset_uses_cache(self, tmp_path: Path) -> None:
        bars = [OHLCVBar("2026-01-01", "GARAN", 30.0, 31.0, 29.0, 30.5, 1_000_000.0)]
        _write_cache(tmp_path, _cache_key("GARAN", "1d", "2026-01-01", "2026-01-01"), bars)

        ds = build_dataset(
            ["GARAN"], "2026-01-01", "2026-01-01",
            cache_dir=tmp_path,
        )
        assert "GARAN" in ds
        assert len(ds["GARAN"]) == 1

    def test_build_dataset_populates_cache(self, tmp_path: Path) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_RAW)):
            ds = build_dataset(
                ["GARAN"], "2026-01-15", "2026-01-16",
                client=MatriksClient(token="t"),
                cache_dir=tmp_path,
            )
            assert "GARAN" in ds
            key = _cache_key("GARAN", "1d", "2026-01-15", "2026-01-16")
            assert (tmp_path / key).is_file()


# ── Deterministic ordering ───────────────────────────────────────────────

class TestDeterministicOrdering:
    def test_symbols_sorted_in_output(self) -> None:
        bars_z = [{"symbol": "Z", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
        bars_a = [{"symbol": "A", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100}]
        call_count = {"n": 0}
        def mock_urlopen(*args, **kwargs):
            call_count["n"] += 1
            return _mock_response(bars_a if call_count["n"] == 1 else bars_z)
        with patch("bist_core.data.matriks_client.urlopen", side_effect=mock_urlopen):
            ds = build_dataset(["Z", "A"], "2026-01-01", "2026-01-01", client=MatriksClient(token="t"))
            assert list(ds.keys()) == ["A", "Z"]

    def test_bars_sorted_by_timestamp(self) -> None:
        raw = [
            {"symbol": "X", "date": "2026-01-03", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
            {"symbol": "X", "date": "2026-01-01", "open": 1, "high": 2, "low": 0.5, "close": 1.5, "volume": 100},
        ]
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(raw)):
            ds = build_dataset(["X"], "2026-01-01", "2026-01-03", client=MatriksClient(token="t"))
            timestamps = [b.timestamp for b in ds["X"]]
            assert timestamps == sorted(timestamps)

    def test_identical_runs_identical_output(self) -> None:
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_RAW)):
            c = MatriksClient(token="t")
            ds1 = build_dataset(["GARAN"], "2026-01-15", "2026-01-16", client=c)
        with patch("bist_core.data.matriks_client.urlopen", return_value=_mock_response(_SAMPLE_RAW)):
            c = MatriksClient(token="t")
            ds2 = build_dataset(["GARAN"], "2026-01-15", "2026-01-16", client=c)
        assert list(ds1.keys()) == list(ds2.keys())
        for sym in ds1:
            assert ds1[sym] == ds2[sym]


# ── Error handling ────────────────────────────────────────────────────────

class TestErrorHandling:
    def test_network_disabled_skips_gracefully(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BIST_CORE_NETWORK_ENABLED", raising=False)
        ds = build_dataset(["GARAN"], "2026-01-01", "2026-01-31")
        assert ds == {}

    def test_api_error_skips_symbol(self) -> None:
        call_count = {"n": 0}
        def mock_urlopen(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise MatriksAPIError("boom", status_code=500)
            return _mock_response(_SAMPLE_RAW)
        with patch("bist_core.data.matriks_client.urlopen", side_effect=mock_urlopen):
            ds = build_dataset(["FAIL", "GARAN"], "2026-01-15", "2026-01-16", client=MatriksClient(token="t"))
            assert "FAIL" not in ds
            assert "GARAN" in ds
