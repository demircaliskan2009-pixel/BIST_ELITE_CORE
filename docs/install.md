# Install & Daily Loop (Windows, Offline) — FAZ601

This quickstart focuses on the offline daily loop and uses only local CSVs. No network, no secrets, no real broker.

## 1. Bootstrap (once per machine)

From the repo root:

```powershell
.\tools\bootstrap.ps1
```

This will:

- Create/reuse a `.venv` under the repo
- Install the package (editable mode if `pyproject.toml` exists)
- Run `tools\sanity_check.ps1`

Optionally wire your snapshot root:

```powershell
.\tools\bootstrap.ps1 -SnapshotRoot "C:\path\to\data\eod\snapshots"
```

## 2. Run the daily loop (offline)

```powershell
.\tools\daily.ps1
```

This will:

- Validate environment and snapshot root
- Run the live daily session (scan → ask → evaluate → reports)
- Produce `data\log\reports\<DAY>\summary.html` and `order_ticket_h3.txt`

See `docs/runbook_daily.md` for artifact details.

## 3. Optional: Import broker fills (manual mode)

After placing orders manually and downloading the official fills CSV:

```powershell
.\tools\broker_run.ps1 -Mode manual -Day 2025-03-15 -FillsPath "C:\path\to\fills_2025-03-15.csv"
```

This imports fills via the offline `import_fills` pipeline and writes execution reports under `data\log\execution\<DAY>\`.

Real broker mode remains **blocked (fail-closed)**. See:

- `docs/secrets_policy.md`
- `config/broker.example.yaml`

for how any future real integration must keep secrets and network credentials out of this repo.

## 4. Optional: Weekly review

```powershell
.\tools\weekly_review.ps1 -WeeksBack 0
```

Outputs a markdown summary under `data\log\review\<YYYY-WW>\summary.md` aggregating reports and execution summaries for that ISO week.

## 5. Optional: Windows scheduler (advanced)

To register a daily task (current user context) that runs the offline daily loop:

```powershell
.\tools\schedule_daily.ps1 -Enable -Time "09:00"
```

To remove the task:

```powershell
.\tools\schedule_daily.ps1 -Disable
```

The scheduled task never stores secrets; it simply calls `tools\daily.ps1` under your user account.

