param(
    [ValidateSet("core","comparison_only")]
    [string]$Mode = "core"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..").Path

if (Test-Path ".\.venv\Scripts\Activate.ps1") { & .\.venv\Scripts\Activate.ps1 }
chcp 65001 > $null
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:GIT_PAGER = "cat"
git config --local core.pager cat | Out-Null

Write-Host "===== MODE ====="
Write-Host $Mode

Write-Host "`n===== GIT STATUS ====="
git status --short

Write-Host "`n===== PYTEST ====="
if ($Mode -eq "comparison_only") {
    $cmds = @(
        "python -m pytest -q .\tests\services\test_symbol_comparison.py",
        "python -m pytest -q .\tests\services\test_symbol_comparison_dual_rationale_contract.py",
        "python -m pytest -q .\tests\services\test_advisor_public_comparison_dual_rationale_contract.py",
        "python -m pytest -q .\tests\services -k comparison"
    )
}
else {
    $cmds = @(
        "python -m pytest -q .\tests\services\test_advisor_public_chat_entrypoints.py",
        "python -m pytest -q .\tests\services\test_advisor_chat_service.py",
        "python -m pytest -q .\tests\services\test_chat_service.py",
        "python -m pytest -q .\tests\services\test_chat_response_builder.py",
        "python -m pytest -q .\tests\services\test_chat_pipeline.py",
        "python -m pytest -q .\tests\services\test_chat_facade.py",
        "python -m pytest -q .\tests\services\test_chat_application_service.py",
        "python -m pytest -q .\tests\services\test_chat_endpoint_payload.py"
    )
}

foreach ($cmd in $cmds) {
    Write-Host "`n>>> $cmd"
    Invoke-Expression $cmd
}
