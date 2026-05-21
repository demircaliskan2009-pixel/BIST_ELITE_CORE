# Paper Order Intent Risk Gate - Phase 35A

status: PAPER_ORDER_INTENT_RISK_GATE_READY
phase: 35A
generated_at: 2026-05-21
scope: PAPER_ONLY_ORDER_INTENT_PREFILL_VALIDATION
NOT_private_api: true
NOT_credentials: true
NOT_exchange_orders: true
NOT_execution_adapter: true
NOT_order_routing: true
NOT_strategy_alpha: true
NOT_persistent_ledger_mutation: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #77 State

| field | value |
|---|---|
| `main` | `095d3bca5837b3ea02567f75159dd807b0c50057` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `paper_feed_input_status` | `READY` |
| `paper_fill_model_contract_status` | `READY` |
| `paper_execution_loop_readiness` | `NO` |
| `trade_readiness` | `NO` |

## Selected Seam

Phase 35A adds `src/crypto_core/venue/deribit_paper_order_intent.py` as a
venue-local, paper-only validation boundary. Existing service-level
paper-shadow and execution surfaces are intentionally not used because they
include lifecycle, position, and execution-session concepts beyond this phase.

The accepted boundary is:

`DeribitPaperFeedFrame` + `DeribitPaperOrderIntent` -> pre-fill validation -> `DeribitPaperFillRequest`

The emitted request is only the Phase 34 simulation request. It is not a
routeable venue command and is not automatically sent to the fill model.

## Required Upstream

The gate requires an accepted Phase 33 read-only `DeribitPaperFeedFrame` and
bridges only to the Phase 34 deterministic limit-only fill model contract.
The paper-feed frame must remain `paper_execution_ready=False` and
`trade_ready=False`.

## Intent Vocabulary

The intent contract is simulation-only and contains:

- Deribit venue and instrument identity
- BUY or SELL side
- LIMIT order style only
- positive limit price and quantity
- idempotency key
- `simulation_only=True`
- explicit false live and shadow flags

MARKET, STOP, POST_ONLY, IOC, FOK, leverage, margin mode, and time-in-force
flags are fail-closed in this phase.

## Pre-Fill Gates

The deterministic gates are:

- global kill switch must be clear
- quantity must be within `max_order_qty`
- notional must be within `max_order_notional`
- required accounting state must be present only when policy demands it
- ledger mutation is always disabled
- slippage and fee policy are explicitly `NOT_IMPLEMENTED`

When accounting state is absent and not required by policy, the intent may be
accepted for fill-model request creation, but the accounting gate remains
`NOT_READY_FOR_LEDGER_MUTATION`.

## Fail-Closed Rules

The gate rejects malformed frames or intents, stale or receive-lag-breached
frames, instrument mismatches, non-simulation intents, non-limit styles, invalid
quantity or price, live or shadow flags, kill-switch activation, quantity or
notional breaches, required-but-absent accounting state, and source strings that
suggest private/account/credential/execution scope.

## Non-Scope

This phase does not add private API, credentials, exchange orders, execution
adapters, order routing, venue submission, strategy or alpha generation,
automatic paper loops, persistent ledger mutation, position mutation, shadow
trading, live trading, or network execution in CI.

## Next Phase

The next safest phase is paper fill application plus a paper ledger/accounting
mutation boundary behind this intent gate.
