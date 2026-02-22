# FAZ587: Risk plan -> orders_intent draft -> Midas order ticket (CSV+TXT).
param(
    [Parameter(Mandatory=$true)][string]$Day,
    [Parameter(Mandatory=$true)][int]$Horizon,
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
    # 1) Generate orders_intent draft from risk_plan
    $args1 = @("--day", $Day, "--horizon", $Horizon, "--top", $Top, "--reports-root", $ReportsRoot, "--side", $Side, "--order-type", $OrderType, "--limit-price-mode", $LimitPriceMode)
    if ($SnapshotRoot) { $args1 += @("--snapshot-root", $SnapshotRoot) }
    & python (Join-Path $repoRoot "tools\orders_intent_from_risk_plan.py") @args1
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    # 2) Export to order ticket
    $reportsPath = if ([System.IO.Path]::IsPathRooted($ReportsRoot)) { $ReportsRoot } else { Join-Path $repoRoot $ReportsRoot }
    $draftPath = Join-Path $reportsPath "$Day\orders_intent_draft_h$Horizon.json"
    $outDir = if ($Out) { $Out } else { Join-Path $repoRoot "data\out\order_ticket\$Day" }
    $args2 = @("--orders", $draftPath, "--out", $outDir)
    & python (Join-Path $repoRoot "tools\order_ticket_export.py") @args2
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
