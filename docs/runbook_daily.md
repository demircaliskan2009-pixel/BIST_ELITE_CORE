# Daily Run Runbook (FAZ596)

Offline daily session: validate → live run → artifact check → order ticket. No broker integration.

## Setup

1. **Activate venv**
   ```powershell
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install package**
   ```powershell
   pip install -e .
   ```

3. **Place snapshots**
   - Layout A: `SnapshotRoot\<YYYY-MM-DD>\snapshot.csv`
   - Layout B: `SnapshotRoot\snapshots\<YYYY-MM-DD>\snapshot.csv`
   - CSV: `symbol,close` (optional: date, open, high, low, volume)

4. **Set environment** (recommended)
   ```powershell
   . .\tools\env_example.ps1
   # Edit paths/values as needed. Never commit secrets.
   ```

5. **Sanity check**
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\tools\sanity_check.ps1
   ```
   Exit 0 = OK. Nonzero = SnapshotRoot missing or invalid.

## Daily run examples

### a) With env only (recommended)

```powershell
$env:BIST_SNAPSHOT_ROOT = "C:\path\to\data\eod\snapshots"
$env:BIST_CAPITAL_TRY = "30000"
$env:BIST_RISK_PCT = "0.02"
$env:BIST_ATR_N = "14"
$env:BIST_STOP_ATR_MULT = "2.0"
$env:BIST_TP_R_MULT = "2.0"

.\tools\live_session.ps1
```

### b) With explicit -SnapshotRoot

```powershell
.\tools\live_session.ps1 -SnapshotRoot "C:\path\to\data\eod\snapshots"
```

### c) With explicit -Day

```powershell
.\tools\live_session.ps1 -Day 2025-03-15 -SnapshotRoot "C:\path\to\data\eod\snapshots"
```

## Output directories and key artifacts

| Path | Contents |
|------|----------|
| `data\log\reports\<DAY>\summary.html` | Phone-friendly index (scan, ask, performance) |
| `data\log\reports\<DAY>\topn_h*.csv` | TopN horizon rankings |
| `data\log\reports\<DAY>\topn_h*.json` | Same in JSON |
| `data\log\reports\<DAY>\risk_plan_h*.csv` | Risk budget per symbol |
| `data\log\reports\<DAY>\risk_plan_h*.txt` | Human-readable risk plan |
| `data\log\reports\<DAY>\risk_plan_h*.json` | Same in JSON |
| `data\log\reports\<DAY>\order_ticket_h3.txt` | Order ticket (default horizon 3) |
| `data\log\picks\<DAY>\picks_h*.csv` | Locked picks |
| `data\log\picks\<DAY>\picks_h*.json` | Same in JSON |
| `data\log\picks\<DAY>\eval_h*.csv` | Pick evaluation (OK/PENDING) |
| `data\log\picks\<DAY>\eval_h*.json` | Same in JSON |

## Manual order workflow

1. **Run live_session** — produces `order_ticket_h<TicketHorizon>.txt` in `reports\<DAY>\`.

2. **Review ticket**
   - Open `data\log\reports\<DAY>\order_ticket_h3.txt`
   - Contains: symbol, side, order_type, qty, limit_price per action

3. **Place orders manually** — Use your broker UI or API. No automated execution.

4. **Journal** — Record in `templates\trade_journal.csv` (or your copy).

## Day selection

- **-Day provided:** Uses that day. Snapshot must exist under SnapshotRoot.
- **-Day omitted:** Picks latest snapshot day **<= today** under SnapshotRoot. Future days are ignored (warning printed).
