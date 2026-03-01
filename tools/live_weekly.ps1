# FAZ577: Weekly live review — scoreboard + performance + journal. One command.
# Usage: .\tools\live_weekly.ps1 [-Week "2025-W03"] [-OutRoot "data/log"] [-Journal "path/to/journal.csv"]
param(
    [string]$Week = "",
    [string]$OutRoot = "data/log",
    [string]$Journal = ""
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $args = @("--out-root", $OutRoot)
    if ($Week) { $args += @("--week", $Week) }
    if ($Journal) { $args += @("--journal", $Journal) }
    $env:PYTHONPATH = Join-Path $repoRoot "src"
    & python (Join-Path $repoRoot "tools\live_weekly_report.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
