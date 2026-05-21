# Deribit Paper Feed Pipeline - Phase 33A

status: DERIBIT_PAPER_FEED_INPUT_READY
phase: 33A
generated_at: 2026-05-21
scope: DERIBIT_PUBLIC_MARKET_DATA_PAPER_FEED_INPUT_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_order_intents: true
NOT_execution_adapter: true
NOT_fills: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #75 State

| field | value |
|---|---|
| `main` | `ef684f61a9e9d5b2143a2a412abedbc712ecc6bb` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `order_book_replay_status` | `READY` |

## Selected Paper-Feed Input Seam

Phase 33A adds `src/crypto_core/venue/deribit_paper_feed.py` as a narrow
read-only boundary behind the Phase 32 replay gate.

The accepted path is:

1. Deribit public book payload is normalized.
2. Data quality gate accepts the normalized public book event.
3. Public feed ingest accepts the event and journal replay cursor.
4. Order-book replay accepts and produces `OrderBookState`.
5. Paper-feed input accepts only that replayed public order-book state.

The paper-feed module also builds the existing `PublicDataReadinessSnapshot`
with the replay cursor and order-book state. The existing
`accepted_for_paper` flag is used only as market-data paper-feed input
readiness. It is not paper execution readiness.

## Paper-Feed Frame

The emitted `DeribitPaperFeedFrame` contains read-only market data:

- venue, instrument, and canonical symbol
- event and receive timestamps
- sequence or change-id equivalent from the replayed book
- best bid and best ask
- bid/ask depth summary and deterministic level tuples
- explicit `read_only_market_data=True`
- explicit `paper_execution_ready=False`
- explicit `trade_ready=False`

## Fail-Closed Rules

The paper-feed input rejects:

- malformed or rejected replay results
- absent, unhealthy, or invalid order-book state
- missing public-feed health or journal replay proof
- stale or receive-lag-breached readiness snapshots
- checksum assumptions
- source contamination suggesting account, credential, private, or transfer scope

## Non-Scope

This phase does not add private API, credentials, order intents, strategy
signals, execution adapters, fills, paper execution, shadow trading, live
trading, account state, or network execution in CI.

## Next Phase

The next safest phase is a paper-only strategy/signal intake boundary or a
paper simulator/fill model, whichever can be implemented with explicit
operator authorization and no live-trading capability.
