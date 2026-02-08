# FAZ107: Fail-closed proof pack runner. Run from repo root or tools/.
param(
    [string]$OneTest = ""
)

function Invoke-Step {
    param([scriptblock]$Block)
    & $Block
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    Invoke-Step { git --no-pager diff --stat }
    Invoke-Step { git status --porcelain }
    Invoke-Step { python .\scripts\verify_alignment.py }
    Invoke-Step { python .\tools\release_check.py --hygiene-only }
    if ($OneTest) {
        Invoke-Step { python -m pytest -q $OneTest }
    } else {
        Invoke-Step { python -m pytest -q }
    }
} finally {
    Pop-Location
}
