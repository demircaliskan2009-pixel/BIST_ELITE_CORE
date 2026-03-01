# FAZ567: Today runner — validate then live_daily. Istanbul/local time.
# FAZ588: -Day override for offline runs (explicit snapshot day).
param(
    [string]$Day = "",
    [int]$TopN = 5,
    [string]$OutRoot = "data/log",
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
if (-not $Day) {
    if ($SnapshotRoot) {
        $today = (Get-Date).ToString("yyyy-MM-dd")
        $candidates = Get-ChildItem -Path $SnapshotRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
            Where-Object { $_.Name -le $today } |
            Sort-Object Name -Descending
        if ($candidates) {
            $Day = $candidates[0].Name
        } else {
            $Day = $today
        }
    } else {
        $Day = (Get-Date).ToString("yyyy-MM-dd")
    }
}

Push-Location $repoRoot

try {
    # Validate first (hashtable splat for named params)
    $valParams = @{ Day = $Day }
    if ($SnapshotRoot) { $valParams.SnapshotRoot = $SnapshotRoot }
    & $PSScriptRoot\live_validate.ps1 @valParams
    if ($LASTEXITCODE -eq 2) {
        Write-Host "Validate failed (exit 2). No live run."
        exit 2
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Validate error (exit $LASTEXITCODE)."
        exit $LASTEXITCODE
    }

    # Run live daily (hashtable splat for named params)
    $dailyParams = @{ Day = $Day; TopN = $TopN; OutRoot = $OutRoot }
    if ($SnapshotRoot) { $dailyParams.SnapshotRoot = $SnapshotRoot }
    & $PSScriptRoot\live_daily.ps1 @dailyParams
    $dailyExit = $LASTEXITCODE

    # Publish summary (best-effort; do not fail run)
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & python (Join-Path $repoRoot "tools\live_publish_summary.py") --day $Day --out-root $OutRoot 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Warning: summary.html publish failed (non-fatal)"
    }

    exit $dailyExit
} finally {
    Pop-Location
}
