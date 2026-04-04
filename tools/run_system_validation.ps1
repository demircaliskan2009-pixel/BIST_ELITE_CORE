# Full system validation: env -> live_runner -> validation_run.txt -> analyze_validation_run.py
# Repository root: run from BIST_ELITE_CORE (or set REPO_ROOT).
# -CaptureOnly : only capture validation_run.txt (for run_auto_optimize.ps1).

param(
    [switch]$CaptureOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot

$optEnv = Join-Path $PSScriptRoot "optimizer_env.ps1"
if (Test-Path $optEnv) {
    Write-Host "Loading optimizer_env.ps1"
    . $optEnv
}

$env:PYTHONPATH = "src"
$env:PYTHONUNBUFFERED = "1"
$env:BIST_LIVE_VALIDATION_MODE = "1"
$env:BIST_IDEAL_DATA_PATH = "C:\iDeal\ChartData\IMKBH\01"
$env:BIST_LIVE_MAX_CYCLES = "800"
$env:BIST_LIVE_POLL_SECONDS = "0"
$env:BIST_EXEC_INTEL = "1"
$env:BIST_EXEC_PARTIAL = "1"
$env:BIST_ADAPTIVE_MODE = "1"
$env:BIST_RISK_ENGINE = "1"
$env:MATRIKS_ENABLED = "0"
$env:BIST_MATRIX_SIMULATION = "0"
$env:BIST_SYMBOLS = "ASELS,THYAO,SISE,KCHOL,GARAN,AKBNK,EREGL,ISCTR,FROTO,TOASO"

$out = Join-Path $RepoRoot "validation_run.txt"
Write-Host "Capturing live_runner to $out"
& python -m bist_core.live.live_runner *>&1 | Tee-Object -FilePath $out
$exitRun = $LASTEXITCODE

if ($CaptureOnly) {
    exit $exitRun
}

Write-Host "Analyzing..."
& python -m bist_core.validation --input $out
$exitAn = $LASTEXITCODE
if ($exitRun -ne 0) { exit $exitRun }
exit $exitAn
