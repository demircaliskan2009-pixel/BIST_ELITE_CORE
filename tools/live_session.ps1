# FAZ595: Single-command daily session — validate, live_today, artifact check, order ticket.
param(
    [string]$Day = "",
    [string]$SnapshotRoot = "",
    [string]$Horizons = "1,3,5,20",
    [int]$TicketHorizon = 3,
    [string]$CapitalTry = "",
    [string]$RiskPct = "",
    [string]$AtrN = "",
    [string]$StopAtrMult = "",
    [string]$TpRMult = "",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$outRoot = "data/log"
$reportsBase = Join-Path $repoRoot ($outRoot -replace "/", "\") | Join-Path -ChildPath "reports"
$picksBase = Join-Path $repoRoot ($outRoot -replace "/", "\") | Join-Path -ChildPath "picks"

# Set risk params from params or env; validate before live_today
$riskVars = @{
    "BIST_CAPITAL_TRY" = if ($CapitalTry) { $CapitalTry } else { $env:BIST_CAPITAL_TRY }
    "BIST_RISK_PCT" = if ($RiskPct) { $RiskPct } else { $env:BIST_RISK_PCT }
    "BIST_ATR_N" = if ($AtrN) { $AtrN } else { $env:BIST_ATR_N }
    "BIST_STOP_ATR_MULT" = if ($StopAtrMult) { $StopAtrMult } else { $env:BIST_STOP_ATR_MULT }
    "BIST_TP_R_MULT" = if ($TpRMult) { $TpRMult } else { $env:BIST_TP_R_MULT }
}
$missing = @()
foreach ($k in $riskVars.Keys) {
    $v = $riskVars[$k]
    if (-not $v -or ($v -is [string] -and $v.Trim() -eq "")) {
        $missing += $k
    }
}
if ($missing.Count -gt 0) {
    Write-Host "live_session: risk params required for ticket generation. Missing: $($missing -join ', ')" -ForegroundColor Red
    Write-Host "Set env vars or pass -CapitalTry, -RiskPct, -AtrN, -StopAtrMult, -TpRMult"
    exit 2
}
foreach ($k in $riskVars.Keys) {
    Set-Item -Path "env:$k" -Value $riskVars[$k]
}

Push-Location $repoRoot
try {
    # 1) Run live_today
    $todayParams = @{ TopN = 5; OutRoot = $outRoot }
    if ($Day) { $todayParams.Day = $Day }
    if ($SnapshotRoot) { $todayParams.SnapshotRoot = $SnapshotRoot }
    & $PSScriptRoot\live_today.ps1 @todayParams
    if ($LASTEXITCODE -ne 0) {
        Write-Host "live_today failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }

    # 2) Determine DAY
    $resolvedDay = $Day
    if (-not $resolvedDay) {
        if (-not (Test-Path $reportsBase)) {
            Write-Host "live_session: reports dir missing: $reportsBase"
            exit 2
        }
        $candidates = Get-ChildItem -Path $reportsBase -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
            Sort-Object Name -Descending
        if (-not $candidates) {
            Write-Host "live_session: no day folder under reports"
            exit 2
        }
        $resolvedDay = $candidates[0].Name
    }

    $reportDir = Join-Path $reportsBase $resolvedDay
    $picksDir = Join-Path $picksBase $resolvedDay

    # 3) Validate required artifacts
    $required = @(
        (Join-Path $reportDir "summary.html"),
        (Join-Path $reportDir "topn_h1.csv"),
        (Join-Path $reportDir "topn_h1.json"),
        (Join-Path $reportDir "risk_plan_h$TicketHorizon.csv"),
        (Join-Path $picksDir "picks_h$TicketHorizon.csv"),
        (Join-Path $picksDir "eval_h$TicketHorizon.csv")
    )
    $missingArtifacts = @()
    foreach ($p in $required) {
        if (-not (Test-Path $p)) {
            $missingArtifacts += $p
        }
    }
    if ($missingArtifacts.Count -gt 0) {
        Write-Host "live_session: missing required artifacts:" -ForegroundColor Red
        $missingArtifacts | ForEach-Object { Write-Host "  $_" }
        exit 2
    }

    # 4) Generate order ticket (atomic write via midas)
    $riskPlanCsv = Join-Path $reportDir "risk_plan_h$TicketHorizon.csv"
    $outTicket = Join-Path $reportDir "order_ticket_h$TicketHorizon.txt"
    & $PSScriptRoot\midas_ticket_from_risk_plan.ps1 -RiskPlanPath $riskPlanCsv -OutPath $outTicket
    if ($LASTEXITCODE -ne 0) {
        Write-Host "midas_ticket failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }

    # 5) Session summary
    Write-Host ""
    Write-Host "=== live_session summary ===" -ForegroundColor Cyan
    Write-Host "Day: $resolvedDay"
    Write-Host "Reports: $reportDir"
    Write-Host "Picks: $picksDir"
    Write-Host "Order ticket: $outTicket"
    Write-Host ""

    exit 0
} finally {
    Pop-Location
}
