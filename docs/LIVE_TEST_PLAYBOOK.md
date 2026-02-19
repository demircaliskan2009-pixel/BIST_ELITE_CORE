# Live Test Playbook (6‑month offline manual)

Offline manual live-test workflow. No broker integration. No network by default.

## Tag push

Use `.\tools\push_tags_safe.ps1` instead of `git push --tags`. If a tag exists remotely, do not overwrite; create a new faz tag. See [docs/TAGGING.md](TAGGING.md).

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

0. **Put EOD snapshot** — Place `data/eod/snapshots/<DAY>/snapshot.csv` (symbol, close; optional: date, open, high, low, volume).
0.1. **Prepare / validate** — `.\tools\live_snapshot_prepare.ps1` (or `.\tools\live_validate.ps1 -Day YYYY-MM-DD`). Ensures folder exists; optionally `-TemplateSource templates/snapshot_minimal.csv` to copy minimal fixture if empty. Fails with exit 2 if snapshot missing/invalid.
1. **Live run** — `.\tools\live_today.ps1` (or `.\tools\live_daily.ps1 -Day YYYY-MM-DD`). Runs validate first; refuses to run if validate fails.
2. **Read outputs** — TOP5 in `data/log/daily_scan/<DAY>/scan.json`. Open `data/log/reports/<DAY>/summary.html` on phone for a single-page index of scan, ask artifacts, and performance.
3. **Manual trade** — Pick symbol, open `data/log/ask/<DAY>/<SYMBOL>.json` for plan.
4. **Journal entry** — Record in `templates/trade_journal.csv` (or your copy).

**Rule:** No trade if validate fails (exit 2).

## Phone-friendly summary

After `live_today.ps1`, open `data/log/reports/<DAY>/summary.html` on your phone (e.g. via file sync or local server). It links to scan.json, each ask artifact, and performance.json/csv. No server required — open the file directly.

## Folder map (`data/log/`)

| Path | Contents |
|------|----------|
| `daily_scan/<DAY>/scan.json` | TOP-N ranked symbols |
| `daily_scan/<DAY>/strategies.jsonl` | Logged strategies |
| `ask/<DAY>/<SYMBOL>.json` | Ask artifacts per symbol |
| `outcomes/<DAY>/strategy_outcomes.jsonl` | Evaluated outcomes |
| `reports/<DAY>/performance.json` | Win-rate, avg R, max DD |
| `reports/<DAY>/performance.csv` | Same metrics in CSV |
| `reports/<DAY>/summary.html` | Phone-friendly index (links to scan, ask, performance) |
| `reports/<WEEK_OR_RANGE>/` | Journal rollup reports |

## Weekly rollup

```powershell
python tools/live_journal_report.py --from 2026-01-06 --to 2026-01-10 --journal path/to/journal.csv --out-root data/log
```

Output: `data/log/reports/<range>/realized_report.json` and `.csv`.

## Timezone

All dates use **Europe/Istanbul** assumptions. Snapshot day = trading day close in Istanbul.
