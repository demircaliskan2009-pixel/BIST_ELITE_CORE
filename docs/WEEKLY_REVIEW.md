# Weekly Review Pack (FAZ599)

Offline weekly review: scan execution summaries and daily reports, then produce a markdown summary per ISO week. No network, filesystem-only.

## Usage

From the repo root:

```powershell
.\tools\weekly_review.ps1 -WeeksBack 0
```

- `WeeksBack = 0` → current ISO week
- `WeeksBack = 1` → previous week
- etc.

The PowerShell wrapper calls:

```powershell
python -m bist_core.review.weekly --weeks-back <WeeksBack>
```

## Output layout

- Root: `data\log\review\<YYYY-WW>\summary.md`
  - `YYYY` = ISO year
  - `WW`   = ISO week number (01–53)

Each `summary.md` contains a table with:

- Day (YYYY-MM-DD)
- Whether a daily `summary.html` report exists
- Whether an `execution_summary.json` exists
- Number of fills (`n_fills`) if available
- Realized PnL in TRY if available

The script uses only local `data\log\execution\<DAY>\execution_summary.json` and `data\log\reports\<DAY>\summary.html` artifacts and never performs network calls.

