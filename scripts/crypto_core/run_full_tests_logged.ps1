[CmdletBinding()]
param(
    [switch]$Help,
    [string]$RepoRoot = ""
)

if ($Help) {
    Write-Output "Run full crypto_core pytest with unique C:\tmp cache/base/log paths."
    Write-Output "Usage: powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_full_tests_logged.ps1"
    Write-Output "Optional: -RepoRoot <path>"
    exit 0
}

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}

$env:TMP = "C:\tmp"
$env:TEMP = "C:\tmp"
New-Item -ItemType Directory -Force "C:\tmp" | Out-Null

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$cache = "C:\tmp\pytest_cache_crypto_core_full_$stamp"
$base = "C:\tmp\pytest_basetemp_crypto_core_full_$stamp"
$log = "C:\tmp\crypto_core_full_pytest_$stamp.log"

Write-Output "PYTEST_CACHE=$cache"
Write-Output "PYTEST_BASETEMP=$base"
Write-Output "PYTEST_LOG=$log"

Push-Location $RepoRoot
try {
    python -m pytest -x -q tests/crypto_core -o cache_dir=$cache --basetemp=$base *> $log
    $exit = $LASTEXITCODE
}
finally {
    Pop-Location
}

Write-Output "PYTEST_EXIT=$exit"
if (Test-Path $log) {
    Get-Content $log -Tail 160
}
exit $exit
