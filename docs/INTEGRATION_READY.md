# Broker Integration Readiness

Contract and adapter layout for future broker integration. No network, no secrets, no real trading.

## Inputs / outputs contract

### Orders intent (input)

Schema v2. Required keys:

| Key | Type | Required |
|-----|------|----------|
| `day` | str | Yes |
| `actions` | list | Yes |

Each action:

| Key | Type | Required |
|-----|------|----------|
| `symbol` | str | Yes |
| `side` | str | Yes (BUY/SELL) |

Validation: `bist_core.orders.schema.validate_orders_intent_v2`.

### Risk gate (pre-execution)

Orders must pass risk gates before reaching the broker adapter. `bist_core.risk.gates.run_all` returns `{ok, blocked, errors, codes}`. If `blocked` is True, execution must not proceed.

### Execution result (output)

| Key | Type |
|-----|------|
| `ok` | bool |
| `errors` | list[str] |
| `broker` | str |
| `sent` | int |
| `details` | dict |

Provider interface: `ExecutionProvider.submit_orders(orders, *, dry_run=True)`.

## Where a real broker adapter goes

1. **ExecutionProvider** — Implement `submit_orders` in `src/bist_core/execution/adapters/`.
2. **Registry** — Register via `bist_core.execution.adapters.registry.register_execution_provider(name, factory)`.
3. **BrokerAdapter** (optional) — For low-level place_orders/cancel/get_fills, implement `BrokerAdapter` in `src/bist_core/execution/broker_adapter.py` and wrap in an ExecutionProvider.

## Dry-run adapter

`DryRunExecutionProvider` validates schema, enforces `gates.blocked` when present, and returns a deterministic summary. Use for:

- Pre-flight validation before connecting to a real broker
- CI/tests without network
- Human review of what would be sent

```python
from bist_core.execution import DryRunExecutionProvider

provider = DryRunExecutionProvider()
result = provider.submit_orders(orders_intent, dry_run=True)
# result["ok"], result["details"]["summary"]
```

## What must be unit-tested

- Schema validation: invalid/missing fields => `ok=False`, sorted error codes
- Deterministic output: same input => same summary (symbols sorted)
- Fail-closed: `gates.blocked=True` => `ok=False`
- No network, no secrets in dry-run path
