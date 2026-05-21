# Paper Ledger Fill Application - Phase 36A

status: PAPER_LEDGER_FILL_APPLICATION_READY
phase: 36A
generated_at: 2026-05-21
scope: PAPER_ONLY_FILL_APPLICATION_AND_LEDGER_BOUNDARY
NOT_private_api: true
NOT_credentials: true
NOT_exchange_orders: true
NOT_execution_adapter: true
NOT_order_routing: true
NOT_strategy_alpha: true
NOT_automatic_paper_loop: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #78 State

| field | value |
|---|---|
| `main` | `360ee551fe55dfdba0daacbcd76610f179c1cf10` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `paper_fill_model_contract_status` | `READY` |
| `paper_order_intent_gate_status` | `READY` |
| `fill_model_bridge` | `DeribitPaperFillRequest only` |
| `ledger_mutation_ready` | `NO` |
| `paper_trade_readiness` | `NO` |
| `live_trade_readiness` | `NO` |

## Selected Ledger / Accounting Seam

No safe canonical paper-ledger owner exists in `crypto_core` for this phase.
`crypto_core.portfolio` and the execution paper adapter already carry broader
execution, lifecycle, leverage, or session semantics that exceed the phase-36
 boundary. Phase 36A therefore adds a narrow venue-local seam in
`src/crypto_core/venue/deribit_paper_ledger.py`.

## Exact Boundary

`accepted normalized intent reference` + `accepted explicit DeribitPaperFillResult`
-> deterministic isolated paper ledger mutation

The ledger boundary never calls the fill model automatically. It only accepts an
explicit simulated fill result and an explicit isolated ledger state.

## Accounting Fields Tracked

- explicit isolated `cash_balance`
- signed `position_qty` per instrument
- `average_entry_price`
- `realized_pnl`
- `applied_fill_ids`, `applied_request_ids`, `applied_idempotency_keys`
- append-only paper audit entries

Cash balance only changes by deterministic realized PnL on reductions, closes,
or flips. Notional, margin, leverage, funding, fees, and extra slippage are not
simulated in this phase.

## Idempotency / Duplicate-Fill Rule

The ledger rejects duplicate `fill_id`, duplicate `request_id`, and duplicate
intent `idempotency_key`. Rejected or no-fill results never mutate the ledger.

## Fail-Closed Behavior

The ledger rejects rejected fills, no-fill results, absent ledger state, kill
switch activation, missing ids, venue or instrument mismatch, zero or negative
quantity or price, scope contamination suggesting private or live behavior, and
any fill result that looks venue-submittable or trade-ready.

## Explicit Non-Scope

This phase does not add live orders, exchange orders, private API, execution
adapters, order routing, strategy generation, automatic paper loops, shadow
trading, live trading, or CI live-network dependency.

## Next Phase

The next safest phase is the first explicit paper-trade gate or orchestrator
behind this ledger boundary, still fail-closed and still without live trading.