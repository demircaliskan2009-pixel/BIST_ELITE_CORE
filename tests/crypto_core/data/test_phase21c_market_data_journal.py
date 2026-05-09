from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from crypto_core.data.market_data_journal import (
    PublicMarketDataJournalEntry,
    PublicMarketDataJournalError,
    PublicMarketDataReplayCursor,
    build_journal_entry_from_public_event,
    public_market_data_journal_entry_from_dict,
    public_market_data_journal_entry_to_dict,
    public_market_data_replay_cursor_from_dict,
    public_market_data_replay_cursor_to_dict,
    replay_cursor_ready,
    replay_journal_entries,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue.contracts import PublicFeedType, PublicMarketDataEvent, VenueId


def test_valid_public_event_builds_journal_entry():
    entry = build_journal_entry_from_public_event(_event(sequence_id=10), entry_id="entry-10")

    assert entry.entry_id == "entry-10"
    assert entry.venue_id is VenueId.BINANCE_USDM
    assert entry.feed_type is PublicFeedType.L2_ORDERBOOK
    assert entry.sequence_id == 10
    assert entry.payload_ref == "raw:10"
    assert entry.event_kind == "l2_orderbook"
    assert entry.normalized is True


def test_journal_entry_rejects_empty_payload_hash():
    payload = public_market_data_journal_entry_to_dict(
        build_journal_entry_from_public_event(_event(sequence_id=10), entry_id="entry-10")
    )
    payload["payload_hash"] = ""

    with pytest.raises(PublicMarketDataJournalError, match="payload_hash"):
        public_market_data_journal_entry_from_dict(payload)


def test_journal_entry_rejects_invalid_timestamps():
    payload = public_market_data_journal_entry_to_dict(
        build_journal_entry_from_public_event(_event(sequence_id=10), entry_id="entry-10")
    )
    payload["receive_time_ns"] = payload["event_time_ns"] - 1

    with pytest.raises(PublicMarketDataJournalError, match="receive_time_ns"):
        public_market_data_journal_entry_from_dict(payload)


def test_replay_rejects_empty_entries():
    result = replay_journal_entries(())

    assert result.applied is False
    assert result.cursor is None
    assert result.rejection_reasons == ("market_data_journal:entries_empty",)


def test_replay_rejects_mixed_venues():
    entries = (_entry(10), _entry(11, venue_id=VenueId.DERIBIT))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:venue_mismatch" in result.rejection_reasons


def test_replay_rejects_mixed_symbols():
    entries = (_entry(10), _entry(11, symbol="ETHUSDT", canonical_symbol="ETH-USDT-PERP"))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:symbol_mismatch" in result.rejection_reasons


def test_replay_rejects_mixed_feed_types():
    entries = (_entry(10), _entry(11, feed_type=PublicFeedType.TRADES))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:feed_type_mismatch" in result.rejection_reasons


def test_replay_rejects_duplicate_entry_id():
    entries = (_entry(10, entry_id="entry-dup"), _entry(11, entry_id="entry-dup"))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:duplicate_entry_id" in result.rejection_reasons


def test_replay_rejects_duplicate_sequence_id():
    entries = (_entry(10), _entry(10, entry_id="entry-10b", event_time_ns=1_010))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert result.gap_detected is True
    assert "market_data_journal:duplicate_sequence_id" in result.rejection_reasons


def test_replay_rejects_non_monotonic_sequence_id():
    entries = (_entry(11), _entry(10, event_time_ns=1_010))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert result.gap_detected is True
    assert "market_data_journal:sequence_not_monotonic" in result.rejection_reasons


def test_replay_rejects_non_monotonic_event_time_ns():
    entries = (_entry(10, event_time_ns=1_000), _entry(11, event_time_ns=999))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert result.stale_detected is True
    assert "market_data_journal:event_time_not_monotonic" in result.rejection_reasons


def test_replay_rejects_normalized_false_entry():
    entries = (_entry(10), _entry(11, normalized=False))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:not_normalized" in result.rejection_reasons


def test_replay_rejects_entry_with_existing_rejection_reasons():
    entries = (_entry(10), _entry(11, rejection_reasons=("market_data_journal:manual_block",)))

    result = replay_journal_entries(entries)

    assert result.applied is False
    assert "market_data_journal:manual_block" in result.rejection_reasons


def test_valid_replay_builds_ready_cursor():
    result = replay_journal_entries((_entry(10), _entry(11), _entry(12)))

    assert result.applied is True
    assert result.cursor is not None
    assert result.cursor.last_sequence_id == 12
    assert result.cursor.entry_count == 3
    assert replay_cursor_ready(result.cursor) is True


def test_replay_cursor_ready_false_for_none_or_bad_cursor():
    bad = PublicMarketDataReplayCursor(
        journal_id="journal-bad",
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        last_sequence_id=12,
        last_event_time_ns=1_020,
        entry_count=3,
        healthy=False,
        rejection_reasons=("market_data_journal:manual_block",),
    )

    assert replay_cursor_ready(None) is False
    assert replay_cursor_ready(object()) is False  # type: ignore[arg-type]
    assert replay_cursor_ready(bad) is False


def test_journal_entry_serializer_roundtrip():
    entry = _entry(10)

    payload = public_market_data_journal_entry_to_dict(entry)

    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert public_market_data_journal_entry_from_dict(payload) == entry


def test_replay_cursor_serializer_roundtrip():
    result = replay_journal_entries((_entry(10), _entry(11)))
    assert result.cursor is not None

    payload = public_market_data_replay_cursor_to_dict(result.cursor)

    assert json.loads(json.dumps(payload, sort_keys=True)) == payload
    assert public_market_data_replay_cursor_from_dict(payload) == result.cursor


def test_deterministic_replay_same_entries_same_cursor():
    entries = (_entry(10), _entry(11), _entry(12))

    first = replay_journal_entries(entries)
    second = replay_journal_entries(entries)

    assert first.cursor is not None
    assert second.cursor is not None
    assert public_market_data_replay_cursor_to_dict(first.cursor) == public_market_data_replay_cursor_to_dict(
        second.cursor
    )


def test_no_env_credential_network_imports_in_new_module():
    path = Path("src/crypto_core/data/market_data_journal.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
    imported_roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint(forbidden_import_roots)


def test_lifecycle_live_still_rejected():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _entry(
    sequence_id: int,
    *,
    entry_id: str | None = None,
    venue_id: VenueId = VenueId.BINANCE_USDM,
    symbol: str = "BTCUSDT",
    canonical_symbol: str = "BTC-USDT-PERP",
    feed_type: PublicFeedType = PublicFeedType.L2_ORDERBOOK,
    event_time_ns: int | None = None,
    normalized: bool = True,
    rejection_reasons: tuple[str, ...] = (),
) -> PublicMarketDataJournalEntry:
    return PublicMarketDataJournalEntry(
        entry_id=entry_id or f"entry-{sequence_id}",
        venue_id=venue_id,
        symbol=symbol,
        canonical_symbol=canonical_symbol,
        feed_type=feed_type,
        event_time_ns=event_time_ns if event_time_ns is not None else 1_000 + sequence_id,
        receive_time_ns=(event_time_ns if event_time_ns is not None else 1_000 + sequence_id) + 1,
        sequence_id=sequence_id,
        payload_hash=f"payload-hash-{sequence_id}",
        payload_ref=f"raw:{sequence_id}",
        event_kind=feed_type.value,
        normalized=normalized,
        rejection_reasons=rejection_reasons,
    )


def _event(sequence_id: int) -> PublicMarketDataEvent:
    return PublicMarketDataEvent(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        event_time_ns=1_000 + sequence_id,
        receive_time_ns=1_001 + sequence_id,
        sequence_id=sequence_id,
        payload_hash=f"payload-hash-{sequence_id}",
        raw_payload_ref=f"raw:{sequence_id}",
        normalized=True,
    )


def _execution_request() -> ExecutionRequest:
    edge_signal = EdgeSignal(
        family=EdgeFamily.ORDER_FLOW_IMBALANCE,
        symbol="BTCUSDT",
        exchange="binance",
        direction=SignalDirection.BUY,
        confidence=0.5,
        score=0.5,
        evidence={"ofi": 0.5},
        timestamp_ns=100,
        is_valid=True,
        block_reason=None,
    )
    return ExecutionRequest(
        symbol="BTCUSDT",
        exchange="binance",
        intent=OrderIntent.BUY,
        size=0.01,
        price_hint=50_000.0,
        risk_evaluation=RiskEvaluation(
            decision=RiskDecision.APPROVED,
            block_reason=None,
            system_state=SystemState.NORMAL,
            edge_signal=edge_signal,
            no_trade_decision=NoTradeDecision.allow(),
            evidence={},
            timestamp_ns=100,
        ),
        timestamp_ns=100,
    )
