# TopN Horizon Probabilistic Ranking

Horizon-specific, probabilistic ranking for "top N symbols" using offline artifacts and EOD bars. **This is NOT a guarantee engine** — it is an evaluated ranking module that can be scored with the existing scoreboard.

## What it is / isn't

- **Is:** Offline, deterministic ranking by expected return and probability of beating cost
- **Is:** Uses only existing snapshots + scan.json (optional)
- **Is not:** A trading signal or guarantee of future returns
- **Is not:** Network-connected; no secrets, no API calls

## Horizons

| Horizon | Trading days | Use case |
|---------|--------------|----------|
| 1 | 1 day | "Bugünden itibaren 1 gün" |
| 3 | 3 days | Short-term |
| 5 | 5 days (1 week) | "1 hafta" |
| 20 | 20 days (1 month) | "1 ay" |

## Model v0 (simple, transparent)

- **Lookback K:** 60 days (configurable via `--lookback`)
- **Daily log returns** from close prices
- **mu_hat** = mean(last K returns) × H
- **sigma_hat** = std(last K returns) × √H
- **p_up** = P(return > 0) = 1 − Φ(−μ/σ); if σ=0 → 0.5
- **cost_bps:** 10 (0.10%), configurable via `--cost-bps`
- **p_gt_cost** = P(return > cost)
- **score** = (μ − cost) × p_gt_cost

## Outputs

Under `data/log/reports/<DAY>/`:

| File | Description |
|------|--------------|
| `topn_h1.json` | Horizon 1 ranking (JSON) |
| `topn_h1.csv` | Same in CSV |
| `topn_h3.json` / `.csv` | Horizon 3 |
| `topn_h5.json` / `.csv` | Horizon 5 |
| `topn_h20.json` / `.csv` | Horizon 20 |

Columns: `day`, `horizon_days`, `symbol`, `bars_used`, `lookback_used`, `mu_hat`, `sigma_hat`, `p_up`, `p_gt_cost`, `score`, `notes`.

## Running manually

```bash
python tools/topn_horizon_rank.py --day 2025-01-15 --horizon 1 --top 5
python tools/topn_horizon_rank.py --day 2025-01-15 --horizon 5 --top 10 --scan data/log/daily_scan/2025-01-15/scan.json
```

PowerShell:

```powershell
.\tools\topn_horizon_rank.ps1 -Day 2025-01-15 -Horizon 1 -Top 5
```

## Integration

The live pipeline (`live_daily_runner`) generates `topn_h1`, `topn_h3`, `topn_h5`, `topn_h20` automatically. Outputs are listed in `run_manifest.json`.

## Evaluation with scoreboard / weekly pack

- Scoreboard tracks forward returns for scan symbols
- TopN horizon ranking can be evaluated by comparing predicted score vs. realized return over the horizon
- Weekly pack aggregates outcomes

## Eligibility (fail-closed)

- **InsufficientHistory:** bars_count < (K + H + 1) → symbol skipped
- **NoBars:** no close data → symbol skipped
