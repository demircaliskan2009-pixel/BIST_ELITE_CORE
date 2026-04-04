# FAZ566: Live daily runner — scan, ask, evaluate, report. Offline. Deterministic.
# Usage: .\tools\live_daily.ps1 -Day 2025-01-15 [-TopN 5] [-OutRoot "data/log"] [-SnapshotRoot "data/eod/snapshots"]
param(
    [Parameter(Mandatory=$true)]
    [string]$Day,
    [int]$TopN = 5,
    [string]$OutRoot = "data/log",
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $args = @("--day", $Day, "--top-n", $TopN, "--out-root", $OutRoot)
    if ($SnapshotRoot) {
        $args += @("--snapshot-root", $SnapshotRoot)
    }
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & python (Join-Path $repoRoot "tools\live_daily_runner.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
