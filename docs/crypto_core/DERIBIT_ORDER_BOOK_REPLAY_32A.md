# Deribit Order Book Replay - Phase 32A

status: DERIBIT_ORDER_BOOK_REPLAY_READY
phase: 32A
generated_at: 2026-05-21
scope: DERIBIT_NORMALIZED_PUBLIC_MARKET_DATA_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_ci_live_network_dependency: true

## Verified PR #74 State

| field | value |
|---|---|
| `main` | `87b7798837b0062e457582c42e99e48d64d7e267` |
| `accepted` | `True` |
| `connector_ready_dialects_count` | `1` |
| `public_feed_ingest_wiring_status` | `READY` |
| `feed_gate_ready` | `NOT_READY_BY_DESIGN` |
| `paper_readiness` | `NOT_READY_BY_DESIGN` |

## Selected Replay Seam

Phase 32A reuses the existing generic order-book state engine in
`src/crypto_core/data/order_book.py` and adds only a Deribit adapter in
`src/crypto_core/venue/deribit_order_book_replay.py`.

The adapter requires both:

1. an accepted `DeribitPublicDataQualityResult` carrying the validated
   `OrderBookSnapshot` or `OrderBookDelta`
2. an accepted `DeribitPublicFeedIngestResult` proving the same event already
   passed the mandatory ingest seam

## Snapshot/Delta Apply Rules

1. Snapshot initializes state.
2. Delta requires an initialized state.
3. Snapshot re-initialization is rejected in this phase.
4. Delta application reuses generic `apply_order_book_delta()`.
5. State is immutable on failure; rejected events do not mutate the last good
   book state.

## Zero-Gap Policy

Sequence continuity remains exact and fail-closed:

- `prev_update_id` must equal the current `last_sequence_id`
- `first_update_id` must equal `last_sequence_id + 1`
- any mismatch fails closed
- gap tolerance remains `0`

## Crossed / Negative / Malformed Failure Behavior

- malformed or negative levels remain blocked by the mandatory upstream
  quality gate
- crossed resulting state remains blocked by the generic order-book engine
- any rejected replay event returns an explicit reason and preserves the last
  good state

## Non-Trading Scope

This phase adds no private API, credentials, orders, execution adapters, paper
fills, shadow execution, live trading, strategy logic, or BIST integration.

## CI Policy

Unit tests are offline and deterministic. No live-network CI dependency or
auto-network import behavior is introduced.

## Next Phase

The next safe phase is a paper feed pipeline behind this replay gate, still
without orders, execution, or live trading.