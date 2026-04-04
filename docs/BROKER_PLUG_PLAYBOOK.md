# Broker Plug Playbook (FAZ578)

Step-by-step checklist for bringing up a future real broker adapter. No network, no secrets. Dry-run remains the default safe path.

## Invariants

- **No network** — Harness and contract tests run offline.
- **No secrets** — No API keys, tokens, or credentials in code paths.
- **Fail-closed** — Gates (schema, risk) are the source of truth; invalid input => `ok=False`.
- **Dry-run default** — `submit_orders(orders, dry_run=True)` is the safe path; live requires explicit opt-in.

## Pre-requisites

- [ ] `orders_intent.json` schema v2 understood (see [INTEGRATION_READY.md](INTEGRATION_READY.md))
- [ ] `ExecutionProvider` protocol understood: `submit_orders(orders, *, dry_run=True) -> ExecutionResult`
- [ ] `DryRunExecutionProvider` used for validation and deterministic summary

## Checklist: Adapter bring-up

### 1. Contract compliance

- [ ] Implement `ExecutionProvider` protocol: `submit_orders(orders, *, dry_run=True) -> dict`
- [ ] Return `ExecutionResult`: `{ok, errors, broker, sent, details}`
- [ ] Pass `tests/test_broker_adapter_contract_harness.py` (run harness with your provider)
- [ ] When `dry_run=True`: no network, no side effects; validate schema and gates only

### 2. Schema validation

- [ ] Use `bist_core.orders.schema.validate_orders_intent_v2(orders)` before any broker call
- [ ] Invalid schema => `ok=False`, `errors` = sorted error codes
- [ ] Required: `day` (str), `actions` (list). Each action: `symbol`, `side` (BUY/SELL)

### 3. Risk gate

- [ ] Check `orders.get("gates", {}).get("blocked")` before submitting
- [ ] If `blocked=True` => `ok=False`, `errors=["risk_gate_blocked"]`
- [ ] Do not call broker when blocked

### 4. Registry (optional)

- [ ] Register via `bist_core.execution.adapters.registry.register_execution_provider(name, factory)`
- [ ] Factory signature: `factory(*, broker_config_path, broker_config, outdir, day, broker_name, execution) -> ExecutionProvider`
- [ ] Name normalized (strip + lower)

### 5. Harness validation

- [ ] Run: `python tools/broker_harness.py --orders path/to/orders_intent.json`
- [ ] Harness uses `DryRunExecutionProvider` by default (deterministic, offline)
- [ ] Output: `ok`, `errors`, `broker`, `sent`, `details.summary`

### 6. BrokerAdapter (optional, low-level)

- [ ] If wrapping a low-level API: implement `BrokerAdapter` in `bist_core.execution.broker_adapter`
- [ ] Methods: `place_orders`, `cancel`, `get_fills` with strict input/output schemas
- [ ] See `StubBrokerAdapter` for fixture-based testing

## Harness usage

```powershell
# Validate orders_intent from file (DryRunExecutionProvider, deterministic)
python tools/broker_harness.py --orders data/log/orders/2025-01-15/orders_intent.json

# With fixture
python tools/broker_harness.py --orders tools/fixtures/orders_intent_valid.json
```

Exit codes: 0 = ok, 1 = validation failed, 2 = file/IO error.

## Default safe path

- **EOD execute** — `--dry-run` is default; live requires `--execution live` and broker config.
- **ExecutionProvider** — `dry_run=True` is the default parameter.
- **DryRunExecutionProvider** — Always validates; never connects to a broker.

## References

- [INTEGRATION_READY.md](INTEGRATION_READY.md) — Contract and adapter layout
- [INTEGRATION_PLAYBOOK.md](INTEGRATION_PLAYBOOK.md) — Registry and fail-closed rules
- `bist_core.execution.base` — ExecutionProvider protocol, execution_result()
- `bist_core.execution.adapters.dry_run` — DryRunExecutionProvider
