# Hard Capped Paper Session Gate - Phase 42A

status: HARD_CAPPED_PAPER_SESSION_GATE_READY
phase: 42A
generated_at: 2026-05-24
scope: EXPLICIT_OPERATOR_TRIGGERED_HARD_CAPPED_PAPER_SESSION
NOT_private_api: true
NOT_credentials: true
NOT_exchange_orders: true
NOT_execution_adapter: true
NOT_order_routing: true
NOT_strategy_alpha: true
NOT_scheduler: true
NOT_automatic_paper_loop: true
NOT_shadow_live_trading: true
NOT_ci_live_network_dependency: true

## Verified PR #84 State

| field | value |
|---|---|
| `main` | `c7ba8ab9da34ef17288a123fbbc45e783c350ab2` |
| `accepted` | `True` |
| `B1` | `READY_FOR_HUMAN_GATE` |
| `B2` | `READY` |
| `B3` | `READY` |
| `B4` | `READY` |
| `B5` | `READY` |
| `connector_ready_dialects` | `1` |
| `phase40_bounded_run_harness_status` | `READY` |
| `phase41_telemetry_reporting_status` | `PASS` |
| `automatic_paper_loop_status` | `NO` |
| `scheduler_status` | `NO` |
| `live_or_shadow_status` | `NO` |

## Session Boundary

`explicit operator session request` -> `bounded list of explicit paper trade inputs` -> `Phase40 bounded run harness` -> `Phase37 paper trade gate` -> `isolated immutable paper ledger result`

Every trade input is operator-provided and prebuilt from the existing paper-only
fixture path. The session gate does not discover trades, generate strategy
signals, poll markets, schedule itself, loop automatically, route exchange
orders, or call private/live APIs.

## Hard Cap Policy

The session hard cap is `3` explicit paper trades. A session request must set
`max_session_trades > 0` and `max_session_trades <= 3`. Trade input count must
not exceed either `max_session_trades` or the hard cap.

The committed Phase42 artifact uses `max_session_trades=2` and two explicit
BUY limit paper-trade inputs. This demonstrates multi-run behavior without
creating an unbounded session.

## Session Request Requirements

- non-empty `operator_id`
- non-empty `session_id`
- non-empty `idempotency_key`
- `simulation_only=True`
- `live_enabled=False`
- `shadow_enabled=False`
- `auto_loop_enabled=False`
- `scheduler_enabled=False`
- kill switch clear
- all trade inputs explicit and compatible with the Phase40/37 paper-only path

## Idempotency and Kill-Switch Rules

- duplicate trade request ids fail closed through the Phase40/37 path
- duplicate trade idempotency keys fail closed through the Phase40/37 path
- duplicate session identity markers present in the initial ledger fail closed
- `kill_switch_active=True` rejects the session before any trade attempt
- the first rejected trade stops the session and the accepted result is not
  returned as a successful session

## Scheduler and Auto-Loop Distinction

This phase creates a bounded operator-triggered session gate only. It is not a
scheduler, polling loop, daemon, workflow runner, paper trading loop, shadow
runner, or live runner. It requires explicit inputs and never self-generates
trade decisions.

## Explicit Non-Scope

This phase does not add private API, credentials, exchange orders, execution
adapters, order routing, strategy or alpha generation, scheduler behavior,
automatic paper loops, shadow trading, live trading, or CI live-network
dependency. It does not mark the system live-ready.

## Next Phase

The next safest phase is repeated hard-capped session telemetry/reporting and
promotion criteria. Scheduler-driven operation, live trading, and shadow trading
remain out of scope.
