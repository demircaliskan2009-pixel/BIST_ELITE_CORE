# FAZ598b: One-command daily loop — sanity check, live_session, optional fills import.
param(
    [string]$Day = "",
    [string]$SnapshotRoot = "",
    [string]$CapitalTry = "",
    [string]$RiskPct = "",
    [string]$AtrN = "",
    [string]$StopAtrMult = "",
    [string]$TpRMult = "",
    [int]$TicketHorizon = 3,
    [string]$FillsPath = ""
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
    # 1) Sanity check
    $sanityArgs = @{}
    if ($SnapshotRoot) {
        $sanityArgs.SnapshotRoot = $SnapshotRoot
    }
    & $PSScriptRoot\sanity_check.ps1 @sanityArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "daily: sanity_check failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    # 2) Live session (scan, ask, evaluate, ticket)
    $sessionArgs = @{
        TicketHorizon = $TicketHorizon
    }
    if ($Day) { $sessionArgs.Day = $Day }
    if ($SnapshotRoot) { $sessionArgs.SnapshotRoot = $SnapshotRoot }
    if ($CapitalTry) { $sessionArgs.CapitalTry = $CapitalTry }
    if ($RiskPct) { $sessionArgs.RiskPct = $RiskPct }
    if ($AtrN) { $sessionArgs.AtrN = $AtrN }
    if ($StopAtrMult) { $sessionArgs.StopAtrMult = $StopAtrMult }
    if ($TpRMult) { $sessionArgs.TpRMult = $TpRMult }

    & $PSScriptRoot\live_session.ps1 @sessionArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Host "daily: live_session failed (exit $LASTEXITCODE)" -ForegroundColor Red
        exit $LASTEXITCODE
    }

    # 3) Determine RunDay from reports directory (matches live_session OutRoot semantics)
    $reportsRoot = Join-Path $RepoRoot "data\log\reports"
    if (-not (Test-Path -LiteralPath $reportsRoot -PathType Container)) {
        Write-Host "daily: reports root not found: $reportsRoot" -ForegroundColor Red
        exit 2
    }

    if ($Day) {
        $RunDay = $Day
    } else {
        $today = (Get-Date).ToString('yyyy-MM-dd')
        $dirs = @(Get-ChildItem -LiteralPath $reportsRoot -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
            Select-Object -ExpandProperty Name)
        $dirs = @($dirs | Sort-Object -Unique)
        $daysOk = @($dirs | Where-Object { $_ -le $today })
        if ($daysOk.Count -lt 1) {
            Write-Host "daily: no report days <= today under $reportsRoot" -ForegroundColor Red
            exit 2
        }
        $RunDay = [string]($daysOk | Sort-Object | Select-Object -Last 1)
    }

    $reportDir = Join-Path $reportsRoot $RunDay
    $ticketPath = Join-Path $reportDir "order_ticket_h$TicketHorizon.txt"
    $summaryPath = Join-Path $reportDir "summary.html"

    # 4) Optional fills import via manual broker
    if ($FillsPath) {
        & $PSScriptRoot\broker_run.ps1 -Mode manual -Day $RunDay -TicketPath ".\data\log\reports\$RunDay\order_ticket_h$TicketHorizon.txt" -FillsPath $FillsPath
        if ($LASTEXITCODE -ne 0) {
            Write-Host "daily: broker_run failed (exit $LASTEXITCODE)" -ForegroundColor Red
            exit $LASTEXITCODE
        }
    }

    $execSummaryPath = Join-Path $RepoRoot "data\log\execution\$RunDay\execution_summary.json"

    # 5) Final pointers
    Write-Host ""
    Write-Host "=== daily session pointers ===" -ForegroundColor Cyan
    Write-Host "Day: $RunDay"
    Write-Host "Summary: $summaryPath"
    Write-Host "Order ticket: $ticketPath"
    if (Test-Path -LiteralPath $execSummaryPath) {
        Write-Host "Execution summary: $execSummaryPath"
    } else {
        Write-Host "Execution summary: (none yet; run with -FillsPath to import)" -ForegroundColor Yellow
    }
    Write-Host ""

    exit 0
} finally {
    Pop-Location
}

