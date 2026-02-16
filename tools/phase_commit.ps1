# Phase commit: runs phase_guard, then commits + tags + ledger entry.
# Usage: .\tools\phase_commit.ps1 -Phase faz127 -Message "snapshots doctor --symbol bars_count"
param(
    [Parameter(Mandatory=$true)][string]$Phase,
    [Parameter(Mandatory=$true)][string]$Message
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

# Guard: clean tree + proof pack
& (Join-Path $repoRoot "tools\phase_guard.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Host "phase_guard failed; refusing to commit." -ForegroundColor Red
    Pop-Location
    exit 1
}

# Require changes to commit
$status = git status --porcelain
if (-not $status) {
    Write-Host "FAIL: No changes to commit. Working tree clean." -ForegroundColor Red
    Pop-Location
    exit 1
}

$msg = "${Phase}: $Message"
git add -A
git commit -m $msg
$commitHash = git rev-parse --short HEAD
git tag $Phase

$ledgerPath = Join-Path $repoRoot "phases\ledger.jsonl"
$entry = @{phase=$Phase; commit=$commitHash; summary=$Message; tests="pytest"} | ConvertTo-Json -Compress
Add-Content -Path $ledgerPath -Value $entry

Write-Host "Committed: $msg" -ForegroundColor Green
Write-Host "Tag: $Phase" -ForegroundColor Green
Write-Host "Ledger: $ledgerPath" -ForegroundColor Cyan
Pop-Location
