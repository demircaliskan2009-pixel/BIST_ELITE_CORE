# FAZ584: TopN horizon bundle report wrapper.
param(
    [Parameter(Mandatory=$true)][string]$Day,
    [Parameter(Mandatory=$true)][int]$Horizon,
    [int]$Top = 5,
    [string]$ReportsRoot = "data/log/reports",
    [string]$SnapshotRoot = ""
)

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $args = @("--day", $Day, "--horizon", $Horizon, "--top", $Top, "--reports-root", $ReportsRoot)
    if ($SnapshotRoot) { $args += @("--snapshot-root", $SnapshotRoot) }
    & python (Join-Path $repoRoot "tools\topn_bundle_report.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
