# FAZ583: Horizon probabilistic TopN ranker wrapper.
param(
    [Parameter(Mandatory=$true)][string]$Day,
    [Parameter(Mandatory=$true)][int]$Horizon,
    [int]$Top = 5,
    [string]$Scan = "",
    [string]$OutRoot = "data/log",
    [string]$SnapshotRoot = ""
)

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $args = @("--day", $Day, "--horizon", $Horizon, "--top", $Top, "--out-root", $OutRoot)
    if ($Scan) { $args += @("--scan", $Scan) }
    if ($SnapshotRoot) { $args += @("--snapshot-root", $SnapshotRoot) }
    & python (Join-Path $repoRoot "tools\topn_horizon_rank.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
