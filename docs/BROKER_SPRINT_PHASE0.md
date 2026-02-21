# Broker Sprint Phase 0 — Offline-First Skeleton

Phase 0 prepares the repo for future real broker integration **without any network access**.

## What is included

- **RealBrokerExecutionProvider** skeleton in `src/bist_core/execution/adapters/real_broker_skeleton.py`
- **Provider selector** in `src/bist_core/execution/provider_selector.py` — reads `BIST_EXEC_PROVIDER`
- **Config/feature-flag** — DryRunExecutionProvider remains the default unless explicit opt-in

## Default behavior

- **BIST_EXEC_PROVIDER** unset or empty → `DryRunExecutionProvider`
- **BIST_EXEC_PROVIDER=real_skeleton** → `RealBrokerExecutionProvider(transport=None)`

## RealBrokerExecutionProvider behavior

| dry_run | transport | Result |
|---------|-----------|--------|
| True | any | Validation only (same as DryRun). ok=True when valid. |
| False | None | `ok=False`, `errors=["broker_transport_missing"]` |
| False | StubBrokerAdapter (fixture) | Offline fixture mode — ok=True when fixture returns success |

## Why it is blocked without transport/config

When `dry_run=False` and no transport is injected:

- **broker_transport_missing** — deterministic error
- **sent=0** — no orders sent
- **Fail-closed** — no network, no secrets, no real orders

This ensures:
1. No accidental live execution
2. Offline tests can use fixture mode (StubBrokerAdapter)
3. Future: inject real broker transport only when explicitly configured

## How to opt-in (Phase 0)

1. Set `BIST_EXEC_PROVIDER=real_skeleton` to use the skeleton provider.
2. For dry-run: no config needed — validation behaves like DryRun.
3. For live: inject a transport (e.g. `StubBrokerAdapter` with fixture dir) for offline tests.

## No network, no secrets

- No API keys, endpoints, or tokens in this phase.
- StubBrokerAdapter reads from fixtures only.
- proof_pack and tests run fully offline.
