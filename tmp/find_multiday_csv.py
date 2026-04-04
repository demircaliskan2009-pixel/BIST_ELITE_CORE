from pathlib import Path
import pandas as pd
import json
import sys

repo = Path(".")
cands = []

for p in repo.rglob("*.csv"):
    try:
        df = pd.read_csv(p, nrows=50000)
    except Exception:
        continue

    cols = {str(c).strip().lower(): str(c) for c in df.columns}
    if "date" not in cols or "symbol" not in cols:
        continue

    try:
        d = pd.to_datetime(df[cols["date"]], errors="coerce")
        ndays = int(d.dropna().dt.date.nunique())
    except Exception:
        ndays = 0

    nsym = int(df[cols["symbol"]].astype(str).nunique())
    nrows = int(len(df))

    if ndays >= 20:
        cands.append({
            "path": str(p),
            "days": ndays,
            "symbols": nsym,
            "rows": nrows
        })

cands.sort(key=lambda x: (x["days"], x["symbols"], x["rows"]), reverse=True)

if not cands:
    print("NO_LOCAL_MULTI_DAY_CSV_FOUND")
    sys.exit(12)

best = cands[0]
print(json.dumps(best, ensure_ascii=False, indent=2))
Path(".selected_multiday_csv.txt").write_text(best["path"], encoding="utf-8")
