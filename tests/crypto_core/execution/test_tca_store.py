"""Tests for TCA persistence store — Phase 9B.

Covers:
  - TCAStore append + load round-trip
  - Separate TCA records and attribution records
  - Line count tracking
  - Empty file load
  - Corrupt file → TCAStoreCorruptError (fail-closed)
  - Store stats accuracy
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_core.execution.attribution import AttributionStatus, TradeAttribution
from crypto_core.execution.tca import TCARecord, TCAStatus
from crypto_core.execution.tca_store import RestoredTCAState, TCAStore, TCAStoreCorruptError, TCAStoreStats


@pytest.fixture()
def tmp_store(tmp_path: Path) -> TCAStore:
    return TCAStore(tmp_path / "tca_records.jsonl")


def _make_tca_record() -> TCARecord:
    """Minimal TCARecord for testing."""
    return TCARecord(
        order_id="ord_001",
        symbol="BTCUSDT",
        exchange="binance",
        intent="buy",
        timestamp_ns=1_000_000_000,
        status=TCAStatus.COMPLETE,
        execution_price=50000.0,
        decision_price=49990.0,
        arrival_price=49985.0,
    )


def _make_attribution_record() -> TradeAttribution:
    """Minimal TradeAttribution for testing."""
    return TradeAttribution(
        order_id="ord_001",
        symbol="BTCUSDT",
        exchange="binance",
        intent="buy",
        timestamp_ns=1_000_000_000,
        status=AttributionStatus.COMPLETE,
        total_pnl_bps=5.0,
        forecast_alpha_bps=3.0,
    )


class TestTCAStoreBasics:
    def test_append_and_load_tca_record(self, tmp_store: TCAStore) -> None:
        rec = _make_tca_record()
        tmp_store.append_tca(rec)

        state: RestoredTCAState = tmp_store.load()
        assert state.stats.tca_record_count == 1
        assert state.stats.attribution_record_count == 0
        assert len(state.tca_records) == 1
        assert state.tca_records[0].order_id == "ord_001"

    def test_append_and_load_attribution_record(self, tmp_store: TCAStore) -> None:
        rec = _make_attribution_record()
        tmp_store.append_attribution(rec)

        state = tmp_store.load()
        assert state.stats.attribution_record_count == 1
        assert state.stats.tca_record_count == 0
        assert len(state.attribution_records) == 1

    def test_mixed_records(self, tmp_store: TCAStore) -> None:
        tmp_store.append_tca(_make_tca_record())
        tmp_store.append_attribution(_make_attribution_record())
        tmp_store.append_tca(_make_tca_record())

        state = tmp_store.load()
        assert state.stats.tca_record_count == 2
        assert state.stats.attribution_record_count == 1
        assert state.stats.total_lines == 3


class TestTCAStoreLineCount:
    def test_line_count_empty(self, tmp_store: TCAStore) -> None:
        assert tmp_store.line_count() == 0

    def test_line_count_tracks(self, tmp_store: TCAStore) -> None:
        tmp_store.append_tca(_make_tca_record())
        tmp_store.append_tca(_make_tca_record())
        assert tmp_store.line_count() == 2


class TestTCAStoreEmptyLoad:
    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        store = TCAStore(tmp_path / "nonexistent.jsonl")
        state = store.load()
        assert state.stats.total_lines == 0
        assert len(state.tca_records) == 0
        assert len(state.attribution_records) == 0


class TestTCAStoreCorruption:
    def test_corrupt_line_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "corrupt.jsonl"
        path.write_text("not valid json\n", encoding="utf-8")

        store = TCAStore(path)
        with pytest.raises(TCAStoreCorruptError, match="invalid JSON"):
            store.load()

    def test_missing_schema_version_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad_schema.jsonl"
        line = json.dumps({"record_type": "tca_record", "payload": {}}) + "\n"
        path.write_text(line, encoding="utf-8")

        store = TCAStore(path)
        with pytest.raises(TCAStoreCorruptError):
            store.load()

    def test_unknown_record_type_counted(self, tmp_path: Path) -> None:
        path = tmp_path / "unknown.jsonl"
        line = (
            json.dumps(
                {
                    "schema_version": "1",
                    "record_type": "future_type",
                    "payload": {},
                }
            )
            + "\n"
        )
        path.write_text(line, encoding="utf-8")

        store = TCAStore(path)
        state = store.load()
        assert state.stats.unknown_record_count == 1


class TestTCAStoreStats:
    def test_frozen(self) -> None:
        s = TCAStoreStats(
            tca_record_count=1,
            attribution_record_count=2,
            unknown_record_count=0,
            total_lines=3,
        )
        with pytest.raises(AttributeError):
            s.total_lines = 99  # type: ignore[misc]
