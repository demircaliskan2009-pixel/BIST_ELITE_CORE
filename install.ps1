# BIST Elite Core — install script. Run from repo root.
# Installs package in editable mode with dev dependencies. No network required for core.
param(
    [switch]$Editable = $true,
    [switch]$Dev
)

$ErrorActionPreference = "Stop"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
if (-not (Test-Path (Join-Path $root "pyproject.toml"))) {
    Write-Error "pyproject.toml not found. Run from repo root."
    exit 1
}

Push-Location $root
try {
    Write-Host "Installing bist-elite-core..." -ForegroundColor Cyan
    $extras = if ($Dev) { "[dev]" } else { "" }
    $mode = if ($Editable) { "-e" } else { "" }
    python -m pip install $mode . $extras
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host "Done. Run: .\run.ps1 doctor" -ForegroundColor Green
} finally {
    Pop-Location
}
