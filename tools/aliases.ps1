# FAZ119: PowerShell convenience aliases. Dot-source from repo root: . .\tools\aliases.ps1
$BistRepoRoot = Split-Path $PSScriptRoot -Parent

function clean_repo {
    Push-Location $BistRepoRoot
    try {
        powershell -ExecutionPolicy Bypass -File .\tools\clean_repo.ps1
    } finally {
        Pop-Location
    }
}

function proof_pack {
    Push-Location $BistRepoRoot
    try {
        powershell -ExecutionPolicy Bypass -File .\tools\proof_pack.ps1 @args
    } finally {
        Pop-Location
    }
}

function run_proof {
    clean_repo
    proof_pack @args
}

Write-Host "Loaded BIST tools aliases."
