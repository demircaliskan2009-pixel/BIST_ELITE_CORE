# Paper Simulator Fill Model - Phase 34A

status: PAPER_SIMULATOR_FILL_MODEL_CONTRACT_READY
phase: 34A
generated_at: 2026-05-21
scope: PAPER_ONLY_FILL_EVALUATION_CONTRACT
NOT_private_api: true
NOT_credentials: true
NOT_exchange_orders: true
NOT_execution_adapter: true
NOT_order_routing: true
NOT_strategy_alpha: true
NOT_position_accounting_mutation: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #76 State

| field | value |
|---|---|
| `main` | `484e6c893e587529772d82785e6f2574eff1880c` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `paper_feed_input_status` | `READY` |
| `paper_execution_fill_readiness` | `NO` |
| `trade_readiness` | `NO` |

## Selected Simulator Seam

Phase 34A adds `src/crypto_core/venue/deribit_paper_fill_model.py` as a
venue-local contract because the existing paper adapter lives inside the
execution stack and already simulates submissions and lifecycle events. That
surface is intentionally outside this phase.

The accepted boundary is:

`DeribitPaperFeedFrame` -> simulation-only fill evaluation -> typed result

The input frame must already come from the Phase 33 read-only paper-feed
pipeline, which itself requires accepted public data quality, ingest, journal
replay, and order-book replay.

## Simulation Vocabulary

The contract defines only:

- `DeribitPaperFillRequest`
- `DeribitPaperFillSide`
- `DeribitPaperFillStyle`
- `DeribitPaperFillResult`

The request must set `simulation_only=True`. It is not an exchange order, not
an order intent, and not a routeable command.

## Fill Policy

Only deterministic limit evaluation is implemented:

- buy limit fills when `limit_price >= best_ask`
- sell limit fills when `limit_price <= best_bid`
- non-crossing limits return an accepted no-fill result
- quantity must be fully covered by top-of-book quantity
- market style is fail-closed as `NOT_IMPLEMENTED`
- slippage and fees are `NOT_IMPLEMENTED` in this phase

The result carries simulated price and quantity only when filled. It also
records source venue, symbol, canonical symbol, feed timestamps, sequence, and
policy references.

## Fail-Closed Rules

The model rejects malformed requests, non-simulation requests, invalid side or
style, zero or negative quantity, zero or negative limit price, missing or
crossed book data, stale frames, receive-lag breaches, insufficient top-of-book
quantity, and source strings that suggest private/account/credential scope.

## Non-Scope

This phase does not add private API, credentials, exchange orders, execution
adapters, routeable order intents, strategy or alpha logic, risk approval,
position or accounting mutation, automatic paper loops, shadow trading, live
trading, or network execution in CI.

## Next Phase

The next safest phase is a paper-only order-intent boundary with explicit
risk, kill-switch, and accounting gates before any first paper trade.
