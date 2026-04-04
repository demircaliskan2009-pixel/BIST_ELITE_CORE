# Phase guard: runs proof pack. Exit non-zero if invalid.
# Clean tree enforced by phase_commit (refuses if nothing to commit).
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    & (Join-Path $repoRoot "proof_pack.ps1")
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    Write-Host "PASS: phase_guard" -ForegroundColor Green
} finally {
    Pop-Location
}
