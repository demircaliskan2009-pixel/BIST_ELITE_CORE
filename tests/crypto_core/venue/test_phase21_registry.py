from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode, ExecutionRequest, OrderIntent, RejectionReason
from crypto_core.guard.models import NoTradeDecision
from crypto_core.risk.models import RiskDecision, RiskEvaluation
from crypto_core.state.models import SystemState
from crypto_core.venue import (
    InstrumentSpec,
    InstrumentType,
    OrderBookDelta,
    OrderBookLevel,
    OrderBookSnapshot,
    PublicFeedHealth,
    PublicFeedType,
    PublicMarketDataEvent,
    VenueContractError,
    VenueId,
    VenueRegistryError,
    ensure_instrument_usable_for_downstream,
    ensure_public_feed_usable_for_downstream,
    get_instrument_spec,
    get_venue_capability,
    instrument_downstream_rejection_reasons,
    instrument_spec_from_dict,
    instrument_spec_to_dict,
    order_book_snapshot_from_dict,
    order_book_snapshot_to_dict,
    public_feed_downstream_rejection_reasons,
    public_market_data_event_from_dict,
    public_market_data_event_to_dict,
    venue_capabilities,
    venue_capability_from_dict,
    venue_capability_to_dict,
)


def test_registry_deterministic_ordering():
    capabilities = venue_capabilities()

    assert tuple(capability.venue_id for capability in capabilities) == (
        VenueId.DERIBIT,
        VenueId.BINANCE_USDM,
        VenueId.BYBIT_USDT_PERP,
        VenueId.OKX_SWAP,
        VenueId.KRAKEN_FUTURES,
        VenueId.COINBASE_DERIVATIVES,
    )
    assert tuple(capability.initial_recommendation_rank for capability in capabilities) == (1, 2, 3, 4, 5, 6)


def test_deribit_ranked_first_for_read_only_derivatives_vol_research():
    deribit = venue_capabilities()[0]

    assert deribit.venue_id is VenueId.DERIBIT
    assert deribit.enabled_for_public_data is True
    assert deribit.enabled_for_live is False
    assert deribit.supports_options is True
    assert deribit.initial_recommendation_rank == 1


def test_binance_usdm_present_as_l2_reconstruction_reference():
    capability = get_venue_capability(VenueId.BINANCE_USDM)

    assert capability.supports_l2_orderbook is True
    assert capability.rest_snapshot_available is True
    assert "L2 reconstruction" in capability.notes[0]
    assert capability.enabled_for_live is False


def test_coinbase_derivatives_marked_avoided_initially():
    capability = get_venue_capability("coinbase_derivatives")

    assert capability.avoided_initially is True
    assert capability.avoided_initially_reason is not None
    assert capability.enabled_for_live is False


def test_unknown_venue_fails_closed():
    with pytest.raises(VenueRegistryError, match="unknown venue"):
        get_venue_capability("unknown_venue")


def test_unknown_instrument_fails_closed():
    with pytest.raises(VenueRegistryError, match="unknown instrument"):
        get_instrument_spec(VenueId.DERIBIT, "UNKNOWN-PERP")


def test_malformed_instrument_spec_rejected():
    with pytest.raises(VenueContractError, match="tick_size"):
        InstrumentSpec(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            instrument_type=InstrumentType.USDT_PERP,
            base_asset="BTC",
            quote_asset="USDT",
            settlement_asset="USDT",
            contract_size=1.0,
            tick_size=0.0,
            lot_size=0.001,
            min_order_size=0.001,
            min_notional=5.0,
            price_precision=1,
            quantity_precision=3,
            inverse_contract=False,
            linear_contract=True,
            active=True,
        )


def test_inactive_instrument_rejected_for_downstream_use():
    inactive = get_instrument_spec(VenueId.COINBASE_DERIVATIVES, "BTC-MONTHLY")

    assert instrument_downstream_rejection_reasons(inactive) == ("instrument:inactive",)
    with pytest.raises(VenueRegistryError, match="instrument:inactive"):
        ensure_instrument_usable_for_downstream(inactive)


def test_feed_health_stale_or_unhealthy_blocks_downstream_use():
    health = PublicFeedHealth(
        venue_id=VenueId.BINANCE_USDM,
        feed_type=PublicFeedType.L2_ORDERBOOK,
        symbol="BTCUSDT",
        healthy=False,
        stale=True,
        last_event_time_ns=1_000,
        last_receive_time_ns=1_001,
        gap_detected=True,
        resync_required=True,
        rejection_reasons=("public_feed:manual_block",),
    )

    assert public_feed_downstream_rejection_reasons(health) == (
        "public_feed:unhealthy",
        "public_feed:stale",
        "public_feed:gap_detected",
        "public_feed:resync_required",
        "public_feed:manual_block",
    )
    with pytest.raises(VenueRegistryError, match="public_feed:unhealthy"):
        ensure_public_feed_usable_for_downstream(health)


def test_venue_and_instrument_json_roundtrip_stable():
    capability = get_venue_capability(VenueId.DERIBIT)
    spec = get_instrument_spec(VenueId.BINANCE_USDM, "BTCUSDT")

    capability_payload = venue_capability_to_dict(capability)
    spec_payload = instrument_spec_to_dict(spec)

    assert json.loads(json.dumps(capability_payload, sort_keys=True)) == capability_payload
    assert json.loads(json.dumps(spec_payload, sort_keys=True)) == spec_payload
    assert venue_capability_from_dict(capability_payload) == capability
    assert instrument_spec_from_dict(spec_payload) == spec


def test_new_modules_contain_no_env_credential_network_imports():
    forbidden_import_roots = {"os", "requests", "httpx", "aiohttp", "websocket", "websockets"}
    for path in _new_source_paths():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            if isinstance(node, ast.ImportFrom) and node.module is not None:
                imported_roots.add(node.module.split(".")[0])
        assert imported_roots.isdisjoint(forbidden_import_roots)


def test_no_scope_leak_strings_in_new_modules():
    forbidden = ("BIST", "Matriks", "iDeal", "KAP", "VIOP")
    for path in _new_source_paths():
        text = path.read_text(encoding="utf-8")
        assert not any(value in text for value in forbidden)


def test_existing_lifecycle_live_rejection_remains_intact():
    result = ExecutionLifecycleEngine(ExecutionLifecycleConfig(mode=ExecutionMode.LIVE)).process(_execution_request())

    assert result.approved is False
    assert result.rejection_reason == RejectionReason.LIVE_NOT_ENABLED


def _new_source_paths() -> tuple[Path, ...]:
    root = Path("src/crypto_core/venue")
    return tuple(path for path in root.glob("*.py") if path.name != "__pycache__")


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


def test_order_book_snapshot_rejects_crossed_empty_or_invalid_books():
    with pytest.raises(VenueContractError, match="crossed"):
        OrderBookSnapshot(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            event_time_ns=1_000,
            receive_time_ns=1_001,
            sequence_id=10,
            bids=(OrderBookLevel(price=100.0, quantity=1.0),),
            asks=(OrderBookLevel(price=99.0, quantity=1.0),),
            checksum="abc",
            depth=1,
            source="fixture",
        )

    with pytest.raises(VenueContractError, match="must not be empty"):
        OrderBookSnapshot(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            event_time_ns=1_000,
            receive_time_ns=1_001,
            sequence_id=10,
            bids=(),
            asks=(OrderBookLevel(price=101.0, quantity=1.0),),
            checksum=None,
            depth=1,
            source="fixture",
        )


def test_order_book_delta_rejects_invalid_sequence_range():
    with pytest.raises(VenueContractError, match="first_update_id"):
        OrderBookDelta(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            event_time_ns=1_000,
            receive_time_ns=1_001,
            first_update_id=12,
            final_update_id=11,
            prev_update_id=10,
            bid_updates=(OrderBookLevel(price=100.0, quantity=1.0),),
            ask_updates=(),
            checksum=None,
            source="fixture",
        )


def test_public_event_rejects_invalid_timestamps_or_empty_payload_hash():
    with pytest.raises(VenueContractError, match="receive_time_ns"):
        PublicMarketDataEvent(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            feed_type=PublicFeedType.TRADES,
            event_time_ns=1_000,
            receive_time_ns=999,
            sequence_id=1,
            payload_hash="hash",
            raw_payload_ref=None,
            normalized=True,
        )

    with pytest.raises(VenueContractError, match="payload_hash"):
        PublicMarketDataEvent(
            venue_id=VenueId.BINANCE_USDM,
            symbol="BTCUSDT",
            canonical_symbol="BTC-USDT-PERP",
            feed_type=PublicFeedType.TRADES,
            event_time_ns=1_000,
            receive_time_ns=1_001,
            sequence_id=1,
            payload_hash="",
            raw_payload_ref=None,
            normalized=True,
        )


def test_market_data_event_and_snapshot_roundtrip_json_safe():
    event = PublicMarketDataEvent(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        feed_type=PublicFeedType.L2_ORDERBOOK,
        event_time_ns=1_000,
        receive_time_ns=1_001,
        sequence_id=10,
        payload_hash="payload-hash",
        raw_payload_ref="raw:fixture",
        normalized=True,
    )
    snapshot = OrderBookSnapshot(
        venue_id=VenueId.BINANCE_USDM,
        symbol="BTCUSDT",
        canonical_symbol="BTC-USDT-PERP",
        event_time_ns=1_000,
        receive_time_ns=1_001,
        sequence_id=10,
        bids=(OrderBookLevel(price=99.0, quantity=1.0),),
        asks=(OrderBookLevel(price=101.0, quantity=1.0),),
        checksum="checksum",
        depth=1,
        source="fixture",
    )

    event_payload = public_market_data_event_to_dict(event)
    snapshot_payload = order_book_snapshot_to_dict(snapshot)

    assert json.loads(json.dumps(event_payload, sort_keys=True)) == event_payload
    assert json.loads(json.dumps(snapshot_payload, sort_keys=True)) == snapshot_payload
    assert public_market_data_event_from_dict(event_payload) == event
    assert order_book_snapshot_from_dict(snapshot_payload) == snapshot
