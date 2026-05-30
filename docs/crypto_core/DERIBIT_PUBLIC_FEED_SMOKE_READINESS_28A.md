# Deribit Public Feed Smoke Readiness - Phase 28A

status: PUBLIC_FEED_NON_ORDER_SMOKE_READY
phase: 28A
generated_at: 2026-05-21
scope: DERIBIT_PUBLIC_MARKET_DATA_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_ci_live_network_dependency: true

## Verified Starting State

| field | value |
|---|---|
| `main` | `d83f8fbeed01e92bf708b7d8b2a7e45a04283106` |
| `accepted` | `True` |
| `evidence_review_complete` | `True` |
| `connector_enablement_ready` | `True` |
| `pending_rows` | `0` |
| `deferred_rows` | `()` |
| `connector_ready_dialects_count` | `1` |
| `connector_ready_dialects` | `deribit:l2_orderbook:book_instrument_interval` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |

## Enabled Deribit Public Dialect

| field | value |
|---|---|
| `venue` | `deribit` |
| `feed_type` | `l2_orderbook` |
| `channel` | `book.BTC-PERPETUAL.none.10.100ms` |
| `sequence_model` | `snapshot_delta_range` |
| `supports_checksum` | `False` |
| `checksum_model` | `none` |
| `max_gap_tolerance` | `0` |
| `max_staleness_ns` | `2_000_000_000` |
| `max_receive_lag_ns` | `1_000_000_000` |

## Smoke Design

Phase 28A-28F adds an offline-testable Deribit public book adapter. It accepts
raw JSON subscription payloads for the enabled public book dialect and returns a
pre-normalization observation only when the payload passes fail-closed public
market data checks.

The manual smoke surface is a deterministic plan builder, not an auto-starting
network client. Operators must explicitly invoke any future public network
runner, choose an approved public WebSocket endpoint, set bounded timeout and
event limits, and provide an explicit artifact path.

## Forbidden Scope

This phase does not add private API access, credentials, auth signing, account
state, positions, balances, deposits, withdrawals, order placement, execution
adapters, paper execution, shadow execution, live trading, strategy logic, or
BIST integration.

## CI Policy

Unit tests use sample payloads and do not connect to Deribit. Live public
network evidence remains an optional manual artifact and is not required for CI.

## Next Phase

The next bounded phase is normalized `MarketEvent` integration from verified
pre-normalization public-feed observations. Trade readiness remains out of
scope.
