# FAZ601: Release pack — zip offline dist with core code and docs.
param(
    [string]$OutDir = ".\dist"
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
    if (-not (Test-Path -LiteralPath $OutDir)) {
        New-Item -ItemType Directory -Path $OutDir | Out-Null
    }

    # Determine version string from git
    $desc = (& git describe --tags --always 2>$null).Trim()
    if (-not $desc) {
        $desc = (& git rev-parse --short HEAD 2>$null).Trim()
    }
    if (-not $desc) {
        $desc = "unknown"
    }

    $zipName = "BIST_ELITE_CORE_$desc.zip"
    $zipPath = Join-Path $OutDir $zipName

    Write-Host "release_pack: building $zipPath" -ForegroundColor Cyan

    $includeRoots = @(
        "src",
        "tools",
        "docs"
    )

    $files = @()

    foreach ($root in $includeRoots) {
        $full = Join-Path $RepoRoot $root
        if (Test-Path -LiteralPath $full -PathType Container) {
            $files += Get-ChildItem -LiteralPath $full -Recurse -File -ErrorAction SilentlyContinue
        }
    }

    # Include example configs only
    $configDir = Join-Path $RepoRoot "config"
    if (Test-Path -LiteralPath $configDir -PathType Container) {
        $files += Get-ChildItem -LiteralPath $configDir -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like "*example*" }
    }

    # Include root files if present
    $rootFiles = @("README.md", "pyproject.toml", "requirements.txt", "LICENSE")
    foreach ($rf in $rootFiles) {
        $p = Join-Path $RepoRoot $rf
        if (Test-Path -LiteralPath $p -PathType Leaf) {
            $files += Get-Item -LiteralPath $p
        }
    }

    # Exclusions: .venv, data/log, data/eod/snapshots, __pycache__
    $files = $files | Where-Object {
        $fullPath = $_.FullName
        ($fullPath -notmatch "\\.venv(\\|$)") -and
        ($fullPath -notmatch "[\\/]data[\\/]log[\\/]") -and
        ($fullPath -notmatch "[\\/]data[\\/]eod[\\/]snapshots[\\/]") -and
        ($fullPath -notmatch "[\\/]__pycache__[\\/]")
    }

    if ($files.Count -eq 0) {
        Write-Host "release_pack: no files selected; aborting." -ForegroundColor Red
        exit 2
    }

    # Ensure paths are unique
    $files = $files | Sort-Object FullName -Unique

    if (Test-Path -LiteralPath $zipPath -PathType Leaf) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    Compress-Archive -Path $files.FullName -DestinationPath $zipPath -Force

    Write-Host "release_pack: OK -> $zipPath" -ForegroundColor Green
    exit 0
} finally {
    Pop-Location
}

