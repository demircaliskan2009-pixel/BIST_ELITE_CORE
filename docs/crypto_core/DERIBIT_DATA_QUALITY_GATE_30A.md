# Deribit Data Quality Gate - Phase 30A

status: DERIBIT_NORMALIZED_PUBLIC_DATA_QUALITY_GATE_READY
phase: 30A
generated_at: 2026-05-21
scope: DERIBIT_NORMALIZED_PUBLIC_MARKET_DATA_ONLY
NOT_private_api: true
NOT_credentials: true
NOT_orders: true
NOT_live_trading: true
NOT_paper_shadow_execution: true
NOT_ci_live_network_dependency: true

## Verified PR #72 State

| field | value |
|---|---|
| `main` | `d0ea97250c01ec337393986e2521aeda38a68feb` |
| `accepted` | `True` |
| `evidence_review_complete` | `True` |
| `ready_for_engineering_patch` | `True` |
| `connector_enablement_ready` | `True` |
| `pending_rows` | `0` |
| `deferred_rows` | `()` |
| `rejection_reasons` | `()` |
| `connector_ready_dialects_count` | `1` |
| `connector_ready_dialects` | `deribit:l2_orderbook:book_instrument_interval` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |

## Normalized Event Seam

The canonical seam remains the Phase 29 normalizer:

- `normalize_deribit_public_book_parse_result()`
- `normalize_deribit_public_book_observation()`

These produce a normalized `PublicMarketDataEvent` and, when the event type is
proven, an `OrderBookSnapshot` or `OrderBookDelta`. Phase 30A adds a pure,
deterministic runtime gate over those normalized contracts only.

## Quality Gate Checks

The new gate validates the following without network access:

1. Deribit venue identity and `l2_orderbook` feed identity
2. Known instrument and canonical symbol consistency
3. `PublicMarketDataEvent` timestamp integrity
4. `staleness_ns <= 2_000_000_000`
5. `receive_lag_ns <= 1_000_000_000`
6. `max_gap_tolerance == 0` when delta sequence continuity is detectable
7. checksum remains unsupported/False (`supports_checksum=False`, `checksum_model=none`)
8. `OrderBookSnapshot` / `OrderBookDelta` contract identity consistency
9. bid/ask level shape validation and numeric validation
10. crossed-book rejection
11. private/account/order-like contamination rejection
12. downstream public-feed usability via `PublicFeedHealth`

## Fail-Closed Behavior

The gate rejects the normalized event when any required identity, timing,
sequence, book-shape, checksum-policy, or contamination check fails. It does
not weaken Phase 28 or Phase 29 fail-closed checks; it adds a separate
post-normalization quality decision before any future ingest wiring.

## Non-Trading Scope

This phase does not add private API, auth signing, credentials, balances,
positions, order placement, execution adapters, paper fills, shadow execution,
live trading, strategy logic, or BIST integration.

## CI Policy

Unit tests are fully offline and deterministic. No live-network CI dependency
is introduced. The gate is a pure validation layer over already-normalized
public market data contracts.

## Next Phase

The next safe phase is public feed ingest wiring behind this quality gate, or a
bounded non-trading paper-feed pipeline, still without orders or live trading.