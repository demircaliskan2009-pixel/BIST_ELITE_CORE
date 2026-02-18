# Live Test Playbook (6‑month offline manual)

Offline manual live-test workflow. No broker integration. No network by default.

## Release branch policy

- **`release/live-test-2026H1`** — branch used for daily runs during H1 2026.
- **`main`** — can evolve; only cherry-pick critical fixes into the release branch.
- **Cherry-pick flow:** `git checkout release/live-test-2026H1` → `git cherry-pick <commit>` → run `.\tools\proof_pack.ps1` → push.

```powershell
# Create release branch (once)
git checkout main
git checkout -b release/live-test-2026H1
git push -u origin release/live-test-2026H1

# Cherry-pick a fix from main
git checkout release/live-test-2026H1
git cherry-pick <sha>
.\tools\proof_pack.ps1
git push origin release/live-test-2026H1
```

## Daily routine

1. **EOD snapshot update** — Ensure `data/eod/snapshots/<DAY>/snapshot.csv` exists and is valid.
2. **Validate** — `.\tools\live_validate.ps1 -Day YYYY-MM-DD` (or `.\tools\live_today.ps1`).
3. **Live run** — If validate passes: `.\tools\live_today.ps1` (or `.\tools\live_daily.ps1 -Day YYYY-MM-DD`).
4. **Read outputs** — TOP5 in `data/log/daily_scan/<DAY>/scan.json`.
5. **Manual trade** — Pick symbol, open `data/log/ask/<DAY>/<SYMBOL>.json` for plan.
6. **Journal entry** — Record in `templates/trade_journal.csv` (or your copy).

**Rule:** No trade if validate fails (exit 2).

## Folder map (`data/log/`)

| Path | Contents |
|------|----------|
| `daily_scan/<DAY>/scan.json` | TOP-N ranked symbols |
| `daily_scan/<DAY>/strategies.jsonl` | Logged strategies |
| `ask/<DAY>/<SYMBOL>.json` | Ask artifacts per symbol |
| `outcomes/<DAY>/strategy_outcomes.jsonl` | Evaluated outcomes |
| `reports/<DAY>/performance.json` | Win-rate, avg R, max DD |
| `reports/<DAY>/performance.csv` | Same metrics in CSV |
| `reports/<WEEK_OR_RANGE>/` | Journal rollup reports |

## Weekly rollup

```powershell
python tools/live_journal_report.py --from 2026-01-06 --to 2026-01-10 --journal path/to/journal.csv --out-root data/log
```

Output: `data/log/reports/<range>/realized_report.json` and `.csv`.

## Timezone

All dates use **Europe/Istanbul** assumptions. Snapshot day = trading day close in Istanbul.
