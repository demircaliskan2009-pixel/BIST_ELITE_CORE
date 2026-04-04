# FAZ575: Windows-first bootstrap — venv, deps, sanity checks, ENV REPORT.
# Run from repo root or tools/. No network required at runtime (install step may use pip).
param()

$ErrorActionPreference = "Stop"
$repoRoot = if ($PSScriptRoot) { Split-Path $PSScriptRoot -Parent } else { Get-Location }
Push-Location $repoRoot

function Invoke-Step {
    param([string]$Name, [scriptblock]$Block)
    Write-Host "bootstrap: $Name" -ForegroundColor Cyan
    & $Block
    if ($LASTEXITCODE -ne 0) {
        Write-Host "bootstrap: $Name FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
        Pop-Location
        exit $LASTEXITCODE
    }
}

try {
    # 1) Create .venv if missing
    $venvPath = Join-Path $repoRoot ".venv"
    if (-not (Test-Path (Join-Path $venvPath "Scripts\python.exe"))) {
        Invoke-Step "create venv" { python -m venv $venvPath }
    } else {
        Write-Host "bootstrap: venv exists" -ForegroundColor Cyan
    }

    $py = Join-Path $venvPath "Scripts\python.exe"
    $pip = Join-Path $venvPath "Scripts\pip.exe"

    # 2) Install dependencies (pyproject + requirements.txt)
    Invoke-Step "install deps" {
        & $pip install -e . --quiet
        if (Test-Path "requirements.txt") {
            & $pip install -r requirements.txt --quiet
        }
    }

    # 3) Sanity checks (offline)
    Invoke-Step "verify_alignment" { & $py scripts\verify_alignment.py }
    Invoke-Step "release_check hygiene" { & $py tools\release_check.py --hygiene-only }

    # 4) Short smoke test subset (fast)
    $smokeTests = @(
        "tests/test_faz107_proof_pack_script_exists.py",
        "tests/test_faz103_release_check_hygiene_only.py",
        "tests/test_faz2_localcsv_provider.py",
        "tests/test_faz100_core_complete_sentinel.py"
    )
    Invoke-Step "smoke tests" { & $py -m pytest -q $smokeTests }

    # 5) ENV REPORT
    $pyVer = & $py -c "import sys; print(sys.version.split()[0])" 2>$null
    $pipVer = & $pip --version 2>$null
    $osInfo = [System.Environment]::OSVersion.VersionString
    $sha = git rev-parse --short HEAD 2>$null
    if (-not $sha) { $sha = "n/a" }
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if (-not $branch) { $branch = "n/a" }

    Write-Host ""
    Write-Host "========== ENV REPORT ==========" -ForegroundColor Green
    Write-Host "python:   $pyVer"
    Write-Host "pip:      $pipVer"
    Write-Host "OS:       $osInfo"
    Write-Host "repo sha: $sha"
    Write-Host "branch:   $branch"
    Write-Host "===============================" -ForegroundColor Green
    Write-Host ""
}
finally {
    Pop-Location
}
