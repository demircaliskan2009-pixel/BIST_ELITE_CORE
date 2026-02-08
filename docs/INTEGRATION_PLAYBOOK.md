# Integration Playbook

Minimal manual workflow and integration points for BIST Elite Core.

## Minimal manual workflow

1. **Snapshot** — Produce EOD snapshot for a day (market data → `snapshot.csv`).
2. **Advisory / ask** — Run advisory step; get signals/advice for the universe.
3. **orders_intent** — Build `orders_intent.json` from advice (strategy + risk gates).
4. **Paper / manual execute** — Run execution (paper broker or BrokerAdapter for live).

Example CLI sequence:

```bash
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD
python -m bist_core.cli eod run --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD --emit-orders --orders-strategy equal_weight
python -m bist_core.cli eod execute --day YYYY-MM-DD --outdir data/eod/runs/YYYY-MM-DD --execution paper
```

## Integration ports

- **Market data provider** — EOD snapshot source. Default/local: CSV; for live data use a vendor adapter (e.g. VendorAPIProvider or custom provider).
- **KAP events provider** — Corporate disclosure / events. Use KapHtmlEventsProvider (HTML) or vendor API; configurable via URL template and cache dir.
- **BrokerAdapter** — Order execution. Paper broker for simulation; for live trading plug in a BrokerAdapter implementation (config via BIST_BROKER_CONFIG).

## Required / common env vars

- **BIST_CORE_HOME** — Optional; base directory for core data (registry, etc.).
- **BIST_CORE_ALLOW_NETWORK** — Must be `1` (or `true`/`yes`) to allow outbound HTTP. Default is off (fail-closed).
- **KAP cache dir** — `BIST_KAP_RAW_DIR` or `BIST_RAW_DIR` for KAP HTML cache.
- **Vendor / base URL** — `BIST_KAP_BASE_URL`, `BIST_KAP_URL_TEMPLATE` (or equivalent) for KAP; vendor EOD URL for market data when using VendorAPIProvider.

## Fail-closed rules

- **Network disabled by default** — Outbound requests (VendorAPIProvider, KapHtmlEventsProvider fetch) are blocked unless `BIST_CORE_ALLOW_NETWORK=1` (or equivalent). Cache-only or offline flows do not require network.
- **Env contract** — Only whitelisted `BIST_*` env keys are allowed; unknown keys cause preflight failure.
- **Execution** — Live execute requires valid config, broker config, rulespack, and manifest; otherwise exit 2 with execution_result.json.
