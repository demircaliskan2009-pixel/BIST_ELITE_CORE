# FAZ568: Human gate — run proof_pack before push. One-line PASS/FAIL.
$repoRoot = Split-Path $PSScriptRoot -Parent
$proofPack = Join-Path $PSScriptRoot "proof_pack.ps1"
Push-Location $repoRoot
try {
    & $proofPack
    if ($LASTEXITCODE -eq 0) {
        Write-Host "PASS"
        exit 0
    } else {
        Write-Host "FAIL"
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
