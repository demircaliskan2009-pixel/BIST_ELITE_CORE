# FAZ570: Snapshot prepare SOP. Ensure folder exists, validate. Fail-closed. Exit 0=ok, 2=invalid/missing.
param(
    [string]$Day = "",
    [string]$SnapshotRoot = "data/eod/snapshots",
    [string]$TemplateSource = ""
)

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path $PSScriptRoot -Parent
$env:PYTHONPATH = Join-Path $repoRoot "src"
Push-Location $repoRoot

try {
    $args = @()
    if ($Day) { $args += @("--day", $Day) }
    $args += @("--snapshot-root", $SnapshotRoot)
    if ($TemplateSource) { $args += @("--template-source", $TemplateSource) }

    & python (Join-Path $repoRoot "tools\live_snapshot_prepare.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
