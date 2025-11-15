# BIST_ELITE_CORE — Minimal Working Core
Runs offline on CSVs; plug-in ready for vendors and brokers.
### Faz-2: CLI akışı (eod → plan → orders)

```bash
# 1) EOD (snapshot) üretir → data/eod/snapshots/YYYY-MM-DD/snapshot.csv
python -m bist_core.cli.main eod    --date 2025-01-15

# 2) Eşit ağırlık planı → plan_equal_weight.csv  (header: symbol,weight)
python -m bist_core.cli.main plan   --date 2025-01-15

# 3) Risk kapılı siparişler → orders_equal_weight.csv (header: symbol,target_weight)
#    Meta PASS/FAIL: orders_meta.txt    Exit code: PASS=0, FAIL=2
python -m bist_core.cli.main orders --date 2025-01-15
