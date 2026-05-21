# Deribit MarketEvent Normalization - Phase 29A

status: PUBLIC_BOOK_MARKETEVENT_NORMALIZATION_READY
phase: 29A
generated_at: 2026-05-21
scope: DERIBIT_PUBLIC_MARKET_DATA_NORMALIZATION_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_ci_live_network_dependency: true

## Verified Starting State

| field | value |
|---|---|
| `main` | `293d8d050253a798ac9a066e30589a2626107ff7` |
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

## Existing MarketEvent Seam

The canonical public-data normalization seam is
`crypto_core.venue.contracts.PublicMarketDataEvent`. The same module also
contains typed order-book contracts, `OrderBookSnapshot` and `OrderBookDelta`,
for observations whose venue event type proves snapshot or change semantics.

This phase deliberately avoids the paper/shadow session `MarketEvent` classes
because those are downstream execution-simulation surfaces and are not needed
for public market data normalization.

## Mapping

| Deribit observation field | Normalized field |
|---|---|
| `venue_id=deribit` | `PublicMarketDataEvent.venue_id` |
| `instrument_name=BTC-PERPETUAL` | `symbol=BTC-PERPETUAL`, `canonical_symbol=BTC-PERP` from registry |
| `feed_type=l2_orderbook` | `PublicMarketDataEvent.feed_type` |
| `event_time_ns` | `PublicMarketDataEvent.event_time_ns` |
| `received_at_ns` | `PublicMarketDataEvent.receive_time_ns` |
| `change_id` | `PublicMarketDataEvent.sequence_id` |
| deterministic observation JSON hash | `PublicMarketDataEvent.payload_hash` |
| deterministic source reference | `PublicMarketDataEvent.raw_payload_ref` |
| accepted pre-normalization observation | `normalized=True` |

If `event_type=snapshot`, the normalizer also emits an `OrderBookSnapshot`. If
`event_type=change` or `event_type=delta`, it emits an `OrderBookDelta` only
when `prev_change_id` is present. If `event_type=unspecified`, it emits only
the canonical `PublicMarketDataEvent` and does not invent snapshot/delta
semantics.

## Fail-Closed Gates

The normalizer rejects malformed observations, wrong venue/feed/channel,
unknown instrument identity, negative sequence IDs, timestamp defects,
receive-lag breaches, stale events, detectable sequence gaps, checksum-policy
mismatch, non-zero gap tolerance, crossed books, malformed levels, and rejected
pre-normalization parse results.

## Non-Trading Scope

No private API, credentials, auth signing, account state, positions, balances,
orders, execution adapters, paper execution, shadow execution, live trading, or
strategy logic is added. Unit tests are offline and use deterministic sample
payloads only.

## Next Phase

The next safe phase is a data-quality runtime gate or public feed ingest wiring
from normalized `PublicMarketDataEvent` values, still without orders or
trading.
