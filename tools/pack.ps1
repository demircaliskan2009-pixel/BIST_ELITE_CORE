# Cross-platform packaging script. Run from repo root or tools/.
# Builds sdist + wheel. Requires: python, pip, build (pip install build)
param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$repoRoot = if ($PSScriptRoot) {
    Split-Path $PSScriptRoot -Parent
} else {
    $PWD.Path
}

Push-Location $repoRoot

try {
    $distDir = Join-Path $repoRoot "dist"
    if ($Clean -and (Test-Path $distDir)) {
        Remove-Item -Recurse -Force $distDir
    }
    New-Item -ItemType Directory -Force -Path $distDir | Out-Null

    # Use python -m build (pip install build) for cross-platform sdist + wheel
    $hasBuild = python -c "import build" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing build package..."
        python -m pip install --quiet build
    }
    python -m build --outdir dist
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host "Artifacts in dist/:"
    Get-ChildItem $distDir | ForEach-Object { Write-Host "  $($_.Name)" }
} finally {
    Pop-Location
}
