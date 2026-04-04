# FAZ587: Risk plan -> orders_intent draft -> Midas order ticket (CSV+TXT).
# FAZ595: -RiskPlanPath/-OutPath for deterministic path-based invocation.
param(
    [string]$RiskPlanPath = "",
    [string]$OutPath = "",
    [string]$Day = "",
    [int]$Horizon = 0,
    [int]$Top = 5,
    [string]$ReportsRoot = "data/log/reports",
    [string]$Side = "BUY",
    [string]$OrderType = "MARKET",
    [string]$LimitPriceMode = "NONE",
    [string]$SnapshotRoot = "",
    [string]$Out = ""
)

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $usePathMode = $RiskPlanPath -and $OutPath
    if ($usePathMode) {
        $riskPlanPath = if ([System.IO.Path]::IsPathRooted($RiskPlanPath)) {
            $RiskPlanPath
        } else {
            (Join-Path $repoRoot $RiskPlanPath) | Resolve-Path -ErrorAction Stop
        }
        if (-not (Test-Path $riskPlanPath)) {
            Write-Host "midas_ticket: RiskPlanPath not found: $riskPlanPath" -ForegroundColor Red
            exit 2
        }
        $reportsDir = Split-Path $riskPlanPath -Parent
        $Day = Split-Path $reportsDir -Leaf
        $ReportsRoot = Split-Path $reportsDir -Parent
        if ($riskPlanPath -match 'risk_plan_h(\d+)\.(csv|json)$') {
            $Horizon = [int]$Matches[1]
        } else {
            Write-Host "midas_ticket: cannot parse horizon from RiskPlanPath" -ForegroundColor Red
            exit 2
        }
        $outPathResolved = if ([System.IO.Path]::IsPathRooted($OutPath)) {
            $OutPath
        } else {
            Join-Path $repoRoot $OutPath
        }
    } else {
        if (-not $Day -or $Horizon -eq 0) {
            Write-Host "midas_ticket: provide -RiskPlanPath and -OutPath, or -Day and -Horizon" -ForegroundColor Red
            exit 2
        }
        $outPathResolved = $null
    }

    # 1) Generate orders_intent draft from risk_plan
    $args1 = @("--day", $Day, "--horizon", $Horizon, "--top", $Top, "--reports-root", $ReportsRoot, "--side", $Side, "--order-type", $OrderType, "--limit-price-mode", $LimitPriceMode)
    if ($SnapshotRoot) { $args1 += @("--snapshot-root", $SnapshotRoot) }
    & python (Join-Path $repoRoot "tools\orders_intent_from_risk_plan.py") @args1
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # 2) Export to order ticket
    $reportsPath = if ([System.IO.Path]::IsPathRooted($ReportsRoot)) { $ReportsRoot } else { Join-Path $repoRoot $ReportsRoot }
    $draftPath = Join-Path $reportsPath "$Day\orders_intent_draft_h$Horizon.json"
    if (-not (Test-Path $draftPath)) {
        Write-Host "midas_ticket: orders_intent draft not found: $draftPath" -ForegroundColor Red
        exit 2
    }
    if ($usePathMode) {
        $tempDir = Join-Path ([System.IO.Path]::GetTempPath()) "midas_ticket_$([guid]::NewGuid().ToString('N').Substring(0,8))"
        New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
        try {
            $args2 = @("--orders", $draftPath, "--out", $tempDir)
            & python (Join-Path $repoRoot "tools\order_ticket_export.py") @args2
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            $tempTxt = Join-Path $tempDir "order_ticket.txt"
            if (-not (Test-Path $tempTxt)) {
                Write-Host "midas_ticket: order_ticket.txt not produced" -ForegroundColor Red
                exit 2
            }
            $outDir = Split-Path $outPathResolved -Parent
            if (-not (Test-Path $outDir)) { New-Item -ItemType Directory -Path $outDir -Force | Out-Null }
            Move-Item -Path $tempTxt -Destination $outPathResolved -Force
        } finally {
            if (Test-Path $tempDir) { Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue }
        }
    } else {
        $outDir = if ($Out) { $Out } else { Join-Path $repoRoot "data\out\order_ticket\$Day" }
        $args2 = @("--orders", $draftPath, "--out", $outDir)
        & python (Join-Path $repoRoot "tools\order_ticket_export.py") @args2
    }
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
