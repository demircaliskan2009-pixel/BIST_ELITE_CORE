# FAZ599: Weekly review wrapper — offline, filesystem-only.
param(
    [int]$WeeksBack = 0
)

$ErrorActionPreference = "Stop"

try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

Push-Location $RepoRoot
try {
    $env:PYTHONPATH = Join-Path $RepoRoot "src"
    & python -m bist_core.review.weekly --weeks-back $WeeksBack
    if ($LASTEXITCODE -ne 0) {
        Write-Host "weekly_review: python module failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
    exit 0
} finally {
    Pop-Location
}

