# Fills CSV Format (FAZ597)

Offline execution layer: import broker fills, validate, compute FIFO realized PnL.

## Required columns

| Column | Type | Description |
|--------|------|-------------|
| ts | datetime | Fill timestamp (ISO or YYYY-MM-DD HH:MM:SS) |
| symbol | string | Instrument symbol (e.g. AAA) |
| side | string | BUY or SELL |
| qty | int | Quantity (must be > 0) |
| price | decimal | Fill price (must be > 0) |

## Optional columns

| Column | Type | Description |
|--------|------|-------------|
| fee_try | decimal | Commission/fee in TRY (default 0) |

## Example

```csv
ts,symbol,side,qty,price,fee_try
2026-02-14T10:00:00+03:00,AAA,BUY,10,100,0
2026-02-14T11:00:00+03:00,AAA,BUY,5,110,0
2026-02-14T12:00:00+03:00,AAA,SELL,12,120,0
```

## Export tips

- **Matriks:** Export to CSV; ensure columns match (ts, symbol, side, qty, price).
- **Other brokers:** Map your export columns to the required names (case-insensitive).
- **Timestamps:** Use ISO 8601 (`YYYY-MM-DDTHH:MM:SS` or with timezone). Naive timestamps treated as local.

## Common errors

- **Missing column:** All of ts, symbol, side, qty, price required.
- **qty <= 0:** Rejected.
- **price <= 0:** Rejected.
- **side not BUY/SELL:** Rejected.
- **SELL exceeds available:** Fail-closed (no shorting). Ensure BUY fills precede SELL for that symbol, or that lots exist.

## Usage

```powershell
.\tools\import_fills.ps1 -Day 2026-02-14 -FillsPath .\broker_fills.csv
```

Or via Python:

```powershell
python -m bist_core.execution.import_fills --day 2026-02-14 --fills .\broker_fills.csv --out-root data\log\execution
```
