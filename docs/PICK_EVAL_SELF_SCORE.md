# Pick Lock + Outcome Evaluator (FAZ586)

Self-measurement for TopN horizons: lock today's picks, evaluate realized returns after H trading days, produce summaries so the robot can "know if it was right."

## How It Works

1. **Pick Lock** (`tools/pick_lock.py`): After TopN horizon ranking, locks the top N symbols into an immutable log under `data/log/picks/<DAY>/`.
2. **Pick Eval** (`tools/pick_eval.py`): After H trading days, evaluates each pick against realized close prices from EOD snapshots.

### Flow

```
topn_h{H}.csv  →  pick_lock  →  picks_h{H}.json, picks_h{H}.csv
                                      ↓
                              pick_eval (when exit-day data exists)
                                      ↓
                              eval_h{H}.json, eval_h{H}.csv
```

### Trading-Day Logic

- **Entry day**: The day the pick was locked (same as TopN day).
- **Exit day**: The H-th trading day *after* the entry day, derived from available snapshot dates.
- If the exit-day snapshot is missing → status `PENDING` (no failure).

## Outputs

### picks_h{H}.json / picks_h{H}.csv

| Field        | Description                          |
|-------------|--------------------------------------|
| day         | Entry date (YYYY-MM-DD)              |
| horizon_days| Horizon (1, 3, 5, or 20)             |
| rank        | Pick rank (1-based)                  |
| symbol      | Symbol                               |
| score       | TopN score                           |
| p_up        | P(up) from horizon ranker            |
| p_gt_cost   | P(return > cost)                     |
| mu_hat      | Estimated mean return                |
| sigma_hat   | Estimated volatility                 |
| locked_at   | Lock timestamp (YYYY-MM-DDTHH:MM:SSZ)|

### eval_h{H}.json / eval_h{H}.csv

| Field         | Description                                      |
|---------------|--------------------------------------------------|
| day           | Entry date                                      |
| horizon_days  | Horizon                                         |
| rank          | Pick rank                                      |
| symbol        | Symbol                                         |
| entry_close   | Close at entry day                             |
| exit_close    | Close at exit day (H trading days later)       |
| log_return    | ln(exit/entry)                                 |
| simple_return | (exit - entry) / entry                         |
| hit_up        | True if exit_close > entry_close               |
| hit_gt_cost   | True if simple_return > 10 bps (0.1%)          |
| status        | OK \| PENDING \| NO_DATA                       |

**Status values:**

- **OK**: Both entry and exit closes available; metrics computed.
- **PENDING**: Exit-day snapshot missing; evaluation deferred.
- **NO_DATA**: Entry-day close missing for symbol.

## How to Read Outputs

- **hit_up**: Did the price go up? (Boolean)
- **hit_gt_cost**: Did the return beat the cost threshold (10 bps)? (Boolean)
- **simple_return**: Realized return; compare to `mu_hat` from the ranker.
- **status**: Use `OK` rows for scoring; ignore or retry `PENDING` later.

## Weekly Review

1. Open `data/log/picks/<DAY>/eval_h1.csv` (and h3, h5, h20).
2. Filter `status == OK`.
3. Aggregate: e.g. `hit_up` rate, `hit_gt_cost` rate, mean `simple_return`.
4. Compare to TopN expectations (`p_up`, `p_gt_cost`, `mu_hat`).

## Usage

### Manual

```bash
# Lock picks (after topn generation)
python tools/pick_lock.py --day 2025-03-15 --horizon 1 --top 5 --reports-root data/log/reports --picks-root data/log/picks

# Evaluate (when exit-day snapshots exist)
python tools/pick_eval.py --day 2025-03-15 --horizon 1 --picks-root data/log/picks --snapshot-root data/eod/snapshots
```

### Integrated

The live pipeline (`tools/live_daily_runner.py`) runs pick lock and pick eval automatically after TopN generation. Picks are locked for H=1,3,5,20; eval runs when exit-day data is available (e.g. backfill).
