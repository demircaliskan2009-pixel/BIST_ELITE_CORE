# PRDV3 final acceptance — E2E integrity (see docs/PRDV3_HONEST_STATUS.md).
# Requires BIST_IDEAL_DATA_PATH (no silent default).
# Usage:
#   $env:BIST_IDEAL_DATA_PATH="D:\path\to\IMKBH\01"; .\tools\prdv3_final_acceptance.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== PRDV3 FINAL ACCEPTANCE (E2E integrity) ==="
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
& python (Join-Path $scriptDir "prdv3_final_acceptance.py")
exit $LASTEXITCODE
