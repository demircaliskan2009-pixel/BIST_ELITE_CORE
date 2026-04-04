# BIST RulesPack (FAZ45)

Data-driven tick size and price band rules for order validation.

- **Location**: Folder `data/bist_rules` (override: env `BIST_RULESPACK_DIR`).
- **Files**: `tick_sizes.csv` (min_price, max_price, tick), `price_bands.csv` (band_pct, optional market).
- **API**: `bist_core.risk.rulespack` — `load_rulespack()`, `validate_tick()`, `validate_band()`, provenance in loaded pack.
- **Gates**: `RiskGateEngine.evaluate(..., rulespack=pack)` optionally validates action prices against tick and band when provided.
