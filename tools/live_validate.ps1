# FAZ567: Snapshot validity gate. Exit 0=ok, 2=invalid, 1=error.
param(
    [Parameter(Mandatory=$true)]
    [string]$Day,
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    $pyArgs = @("--day", $Day)
    if ($SnapshotRoot) { $pyArgs += @("--snapshot-root", $SnapshotRoot) }
    & python (Join-Path $repoRoot "tools\live_validate.py") @pyArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
