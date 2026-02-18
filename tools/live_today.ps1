# FAZ567: Today runner — validate then live_daily. Istanbul/local time.
param(
    [int]$TopN = 5,
    [string]$OutRoot = "data/log",
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$Day = (Get-Date).ToString("yyyy-MM-dd")

Push-Location $repoRoot

try {
    # Validate first
    $valArgs = @("-Day", $Day)
    if ($SnapshotRoot) { $valArgs += @("-SnapshotRoot", $SnapshotRoot) }
    & $PSScriptRoot\live_validate.ps1 @valArgs
    if ($LASTEXITCODE -eq 2) {
        Write-Host "Validate failed (exit 2). No live run."
        exit 2
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Validate error (exit $LASTEXITCODE)."
        exit $LASTEXITCODE
    }

    # Run live daily
    $dailyArgs = @("-Day", $Day, "-TopN", $TopN, "-OutRoot", $OutRoot)
    if ($SnapshotRoot) { $dailyArgs += @("-SnapshotRoot", $SnapshotRoot) }
    & $PSScriptRoot\live_daily.ps1 @dailyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
