param(
    [ValidateSet("comparison","scan","live","baseline","prdv3")]
    [string]$Mode = "comparison"
)

$ErrorActionPreference = "Stop"
Set-Location (Resolve-Path "$PSScriptRoot\..").Path

if (Test-Path ".\.venv\Scripts\Activate.ps1") { & .\.venv\Scripts\Activate.ps1 }
chcp 65001 > $null
$env:PYTHONUTF8 = "1"
$env:PYTHONDONTWRITEBYTECODE = "1"
$env:GIT_PAGER = "cat"
git config --local core.pager cat | Out-Null

$diffTargets = @()
$pytestCmd = $null

switch ($Mode) {
    "comparison" {
        $diffTargets = @(
            ".\src\bist_core\services\symbol_comparison.py",
            ".\tests\services\test_symbol_comparison_dual_rationale_contract.py",
            ".\tests\services\test_advisor_public_comparison_dual_rationale_contract.py"
        )
        $pytestCmd = @(
            "python -m pytest -q .\tests\services\test_symbol_comparison.py",
            "python -m pytest -q .\tests\services\test_symbol_comparison_dual_rationale_contract.py",
            "python -m pytest -q .\tests\services\test_advisor_public_comparison_dual_rationale_contract.py",
            "python -m pytest -q .\tests\services -k comparison"
        )
    }
    "scan" {
        $diffTargets = @(
            ".\src\bist_core\services\scan_ranking.py",
            ".\src\bist_core\services\market_overview_brief.py",
            ".\tests\services\test_scan_ranking_enrichment_contract.py",
            ".\tests\services\test_market_overview_brief_enrichment_contract.py",
            ".\tests\services\test_advisor_public_scan_enrichment_contract.py"
        )
        $pytestCmd = @(
            "python -m pytest -q .\tests\services\test_scan_ranking.py",
            "python -m pytest -q .\tests\services\test_market_overview_brief.py",
            "python -m pytest -q .\tests\services\test_scan_ranking_enrichment_contract.py",
            "python -m pytest -q .\tests\services\test_market_overview_brief_enrichment_contract.py",
            "python -m pytest -q .\tests\services\test_advisor_public_scan_enrichment_contract.py",
            "python -m pytest -q .\tests\services -k 'scan or market_overview or overview or brief'"
        )
    }
    "live" {
        $diffTargets = @(
            ".\src\bist_core\services\advisor_chat_runtime.py",
            ".\src\bist_core\services\live_price_sanity.py"
        )
        $pytestCmd = @(
            "python -m pytest -q .\tests\services\test_advisor_real_public_multi_route_live_reason_contract.py",
            "python -m pytest -q .\tests\services\test_advisor_chat_live_sanity.py",
            "python -m pytest -q .\tests\services\test_advisor_chat_asof_transparency.py",
            "python -m pytest -q .\tests\services\test_advisor_live_context_metadata.py"
        )
    }
    "baseline" {
        $diffTargets = @(".")
        $pytestCmd = @("python -m pytest -q")
    }
    "prdv3" {
        $diffTargets = @(
            ".\docs\PRDV3_FINAL_GOD_ARCHITECTURE.md",
            ".\docs\PRDV3_COMPLIANCE_MATRIX.md",
            ".\tests\test_prdv3_constitution_smoke.py",
            ".\tests\test_walkforward.py",
            ".\tests\test_execution_acceptance.py",
            ".\tests\test_portfolio_acceptance.py",
            ".\tests\test_normalization_determinism.py",
            ".\tests\test_brain_discrimination.py",
            ".\tests\test_multi_timeframe_data.py",
            ".\tests\test_risk_engine.py",
            ".\tests\test_confidence_distribution.py",
            ".\tests\test_edge_signal_module.py",
            ".\tools\prdv3_final_acceptance.py"
        )
        $pytestCmd = @(
            "python -m pytest -q .\tests\test_prdv3_constitution_smoke.py",
            "python -m pytest -q .\tests\test_walkforward.py",
            "python -m pytest -q .\tests\test_execution_acceptance.py",
            "python -m pytest -q .\tests\test_portfolio_acceptance.py",
            "python -m pytest -q .\tests\test_normalization_determinism.py",
            "python -m pytest -q .\tests\test_brain_discrimination.py",
            "python -m pytest -q .\tests\test_multi_timeframe_data.py",
            "python -m pytest -q .\tests\test_risk_engine.py",
            "python -m pytest -q .\tests\test_confidence_distribution.py",
            "python -m pytest -q .\tests\test_edge_signal_module.py"
        )
    }
}

Write-Host "===== MODE ====="
Write-Host $Mode

Write-Host "`n===== GIT STATUS ====="
git status --short

Write-Host "`n===== DIFF ====="
if ($diffTargets.Count -eq 1 -and $diffTargets[0] -eq ".") {
    git diff -- .
} else {
    git diff -- @diffTargets
}

Write-Host "`n===== PYTEST ====="
foreach ($cmd in $pytestCmd) {
    Write-Host "`n>>> $cmd"
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

# alignment check (canonical script lives under scripts/)
python scripts/verify_alignment.py
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
# hygiene gate only (matches AGENTS.md; mode-specific pytest runs above)
python tools/release_check.py --hygiene-only
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
