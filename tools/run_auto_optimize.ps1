# Self-improving loop: validation -> analyze -> auto_optimizer -> re-run (max 3 iterations).
# Repository root. No manual steps.

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $RepoRoot
$env:PYTHONPATH = "src"

$maxIt = 3
$iter = 1

while ($iter -le $maxIt) {
    Write-Host "=== AUTO-OPTIMIZE ITERATION $iter / $maxIt ==="
    & (Join-Path $PSScriptRoot "run_system_validation.ps1") -CaptureOnly
    $ja = Join-Path $RepoRoot "validation_analysis_iter_$iter.json"
    & python -m bist_core.validation --input (Join-Path $RepoRoot "validation_run.txt") --json-output $ja
    & python -m bist_core.validation.auto_optimizer --analysis $ja --iteration $iter --max-iterations $maxIt
    $code = $LASTEXITCODE
    if ($code -eq 0) { break }
    $iter++
}
