# Full system validation (automated)

From repository root (PowerShell):

```powershell
.\tools\run_system_validation.ps1
```

This sets `PYTHONPATH=src`, `PYTHONUNBUFFERED=1`, `BIST_LIVE_VALIDATION_MODE=1` (capture completes even if proof would raise), the env block (ideal path, 800 cycles, exec/risk/adaptive, 10 symbols, Matriks off), runs `python -m bist_core.live.live_runner`, captures output to `validation_run.txt`, then runs:

```powershell
python -m bist_core.validation --input validation_run.txt
```

`live_runner` emits the five metric blocks as **single-line JSON** (plus legacy `repr` lines still parse). The analyzer extracts `SIMULATION_SUMMARY`, `MARKET_REALISM`, `EXECUTION_METRICS`, `RISK_METRICS`, `SYSTEM_STATUS_REPORT`, computes derived metrics, failure flags, edge classification, diagnosis JSON, and fix suggestions. Final line:

`SYSTEM VALIDATION COMPLETE — TRUTH REVEALED`

Override `BIST_IDEAL_DATA_PATH` if your iDeal root differs.

## Auto-optimization loop (self-fixing, max 3 iterations)

```powershell
.\tools\run_auto_optimize.ps1
```

Runs `run_system_validation.ps1 -CaptureOnly` (live capture + `validation_run.txt`), then `python -m bist_core.validation --json-output validation_analysis_iter_N.json`, then `python -m bist_core.validation.auto_optimizer` which updates `tools/optimizer_env.ps1` and `tools/optimizer_state.json` with deterministic env knobs. Stops when `EDGE_CONFIDENCE >= 0.75` and `SYSTEM_TYPE == REAL_EDGE`, or after 3 iterations. Final JSON: `tools/auto_optimize_report.json`.

To reset knobs: delete `tools/optimizer_env.ps1` and `tools/optimizer_state.json`.
