param(
    [ValidateSet("full","fast")]
    [string]$Mode = "full"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..").Path

if (Test-Path ".\.venv\Scripts\Activate.ps1") { & .\.venv\Scripts\Activate.ps1 }
chcp 65001 > $null
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:GIT_PAGER = "cat"
git config --local core.pager cat | Out-Null

Write-Host "===== BRAIN PARITY PACK ====="
Write-Host "Mode: $Mode"

Write-Host "`n===== STEP 1 / COMPARISON ====="
.\tools\proof_pack.ps1 -Mode comparison

Write-Host "`n===== STEP 2 / SCAN ====="
.\tools\proof_pack.ps1 -Mode scan

if ($Mode -eq "full") {
    Write-Host "`n===== STEP 3 / LIVE ====="
    .\tools\proof_pack.ps1 -Mode live
}

Write-Host "`n===== STEP 4 / CORE ====="
.\tools\brain_smoke_pack.ps1 -Mode core
