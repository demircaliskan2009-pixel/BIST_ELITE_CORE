# Deribit Public Feed Ingest Wiring - Phase 31A

status: DERIBIT_PUBLIC_FEED_INGEST_WIRING_READY
phase: 31A
generated_at: 2026-05-21
scope: DERIBIT_NORMALIZED_PUBLIC_MARKET_DATA_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_ci_live_network_dependency: true

## Verified Baseline

| field | value |
|---|---|
| `main` | `2cb1bd926c5c4b9b90f184dbac43aff1720c16de` |
| `accepted` | `True` |
| `connector_ready_dialects_count` | `1` |
| `data_quality_gate_status` | `READY` |

## Wiring Decision

Phase 31A reuses `src/crypto_core/data/public_feed_ingest.py` instead of adding
another store or network connector. The Deribit wrapper requires an accepted
`DeribitPublicDataQualityResult`, derives `PublicFeedPolicy` from
`deribit:l2_orderbook:book_instrument_interval`, builds a single-event
`PublicFeedBatch` and `RawPublicFeedEnvelope`, and calls
`ingest_public_feed_events()`.

The wrapper keeps `require_public_data_ready=False` and `require_order_book=True`
so ingest completes, replay is checked, and `accepted_for_paper` remains False by
design.

## Fail-Closed Boundary

Rejected quality-gate outputs never enter ingest. Post-gate receive-lag breaches
still fail closed at ingest.

## Non-Trading Scope

This phase adds no private API, credentials, orders, execution adapters, paper
fills, shadow execution, live trading, or BIST integration.

## Next Phase

The next safe phase is deterministic order-book state apply/replay behind this
ingest wiring, still without orders or live trading.