# FAZ601: Windows bootstrap — venv + editable install + sanity check.
param(
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"

try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

Write-Host "bootstrap: RepoRoot = $RepoRoot" -ForegroundColor Cyan

# 1) Python check
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "bootstrap: python not found on PATH. Install Python 3.x first." -ForegroundColor Red
    exit 2
}

# 2) Create or reuse .venv under repo
$VenvPath = Join-Path $RepoRoot ".venv"
$VenvPython = Join-Path $VenvPath "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Host "bootstrap: creating virtual environment at $VenvPath" -ForegroundColor Cyan
    & python -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host "bootstrap: venv creation failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} else {
    Write-Host "bootstrap: reusing existing virtual environment at $VenvPath" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    Write-Host "bootstrap: expected venv python not found at $VenvPython" -ForegroundColor Red
    exit 2
}

# 3) Install package in editable mode (prefer pyproject.toml, else requirements.txt)
Push-Location $RepoRoot
try {
    & $VenvPython -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) {
        Write-Host "bootstrap: pip upgrade failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    $hasPyproject = Test-Path -LiteralPath (Join-Path $RepoRoot "pyproject.toml")
    $hasReq = Test-Path -LiteralPath (Join-Path $RepoRoot "requirements.txt")

    if ($hasPyproject) {
        Write-Host "bootstrap: installing package in editable mode (pyproject.toml detected)" -ForegroundColor Cyan
        & $VenvPython -m pip install -e .
    } elseif ($hasReq) {
        Write-Host "bootstrap: installing requirements from requirements.txt" -ForegroundColor Cyan
        & $VenvPython -m pip install -r requirements.txt
    } else {
        Write-Host "bootstrap: no pyproject.toml or requirements.txt found; skipping dependency install." -ForegroundColor Yellow
    }

    if ($LASTEXITCODE -ne 0) {
        Write-Host "bootstrap: dependency install failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}

# 4) Optional SnapshotRoot environment wiring
if ($SnapshotRoot) {
    $env:BIST_SNAPSHOT_ROOT = $SnapshotRoot
    Write-Host "bootstrap: set BIST_SNAPSHOT_ROOT = $SnapshotRoot" -ForegroundColor Cyan
}

# 5) Final sanity check (offline)
Write-Host "bootstrap: running tools\sanity_check.ps1" -ForegroundColor Cyan
if ($SnapshotRoot) {
    & $PSScriptRoot\sanity_check.ps1 -SnapshotRoot $SnapshotRoot
} else {
    & $PSScriptRoot\sanity_check.ps1
}

if ($LASTEXITCODE -ne 0) {
    Write-Host "bootstrap: sanity_check failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "bootstrap: OK — venv ready, package installed, sanity_check passed." -ForegroundColor Green
Write-Host "To activate venv for this shell: .\\.venv\\Scripts\\Activate.ps1" -ForegroundColor Cyan

exit 0

