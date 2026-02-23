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
try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

function Resolve-RepoPath($p) {
    if ([string]::IsNullOrWhiteSpace($p)) { return $null }
    if ([System.IO.Path]::IsPathRooted($p)) { return [System.IO.Path]::GetFullPath($p) }
    $joined = Join-Path $RepoRoot $p
    return [System.IO.Path]::GetFullPath($joined)
}

$outRoot = "data/log"
$reportsBase = Join-Path $RepoRoot ($outRoot -replace "/", "\") | Join-Path -ChildPath "reports"
$picksBase = Join-Path $RepoRoot ($outRoot -replace "/", "\") | Join-Path -ChildPath "picks"

# SnapshotRoot source order: param -> env(BIST_SNAPSHOT_ROOT) -> auto-discover under repo\data
if (-not $SnapshotRoot -and $env:BIST_SNAPSHOT_ROOT) { $SnapshotRoot = $env:BIST_SNAPSHOT_ROOT }
if (-not $SnapshotRoot) {
    $searchBase = Join-Path $RepoRoot "data"
    if (Test-Path -LiteralPath $searchBase) {
        $hits = Get-ChildItem -Path $searchBase -Filter "snapshot.csv" -Recurse -File -ErrorAction SilentlyContinue
        $hitPaths = $hits | Select-Object -First 10 -ExpandProperty FullName
        $roots = @($hits | ForEach-Object {
            $dayDir = Split-Path $_.FullName -Parent
            Split-Path $dayDir -Parent
        } | Sort-Object -Unique)
        if ($roots.Count -eq 1) {
            $SnapshotRoot = $roots[0]
        } else {
            Write-Host "No SnapshotRoot provided and none resolved." -ForegroundColor Red
            Write-Host "Searched for snapshot.csv under: $searchBase"
            if ($hitPaths) {
                Write-Host "Found snapshot.csv examples:"
                $hitPaths | ForEach-Object { Write-Host "  $_" }
            } else {
                Write-Host "Found snapshot.csv examples: none"
            }
            if ($roots) {
                Write-Host "Candidate snapshot roots:"
                $roots | ForEach-Object { Write-Host "  $_" }
            } else {
                Write-Host "Candidate snapshot roots: none"
            }
            throw "SnapshotRoot unresolved. Provide -SnapshotRoot (absolute) or set env:BIST_SNAPSHOT_ROOT."
        }
    } else {
        Write-Host "No SnapshotRoot provided and none resolved." -ForegroundColor Red
        Write-Host "Searched for snapshot.csv under: $searchBase"
        Write-Host "Found snapshot.csv examples: none (search base missing)"
        Write-Host "Candidate snapshot roots: none"
        throw "SnapshotRoot unresolved. Provide -SnapshotRoot (absolute) or set env:BIST_SNAPSHOT_ROOT."
    }
}

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

Push-Location $RepoRoot
try {
    # 1) Resolve SnapshotRoot (repo-root absolute)
    $SnapshotRootResolved = Resolve-RepoPath $SnapshotRoot
    if (-not $SnapshotRootResolved) {
        throw "SnapshotRoot unresolved (internal error)"
    }
    if (-not (Test-Path -LiteralPath $SnapshotRootResolved)) {
        throw "SnapshotRoot missing: given='$SnapshotRoot' resolved='$SnapshotRootResolved'"
    }
    if (-not (Test-Path -LiteralPath $SnapshotRootResolved -PathType Container)) {
        throw "SnapshotRoot is not a directory: $SnapshotRootResolved"
    }

    # 2) Run live_today
    $todayParams = @{ TopN = 5; OutRoot = $outRoot }
    if ($Day) { $todayParams.Day = $Day }
    if ($SnapshotRootResolved) { $todayParams.SnapshotRoot = $SnapshotRootResolved }
    & $PSScriptRoot\live_today.ps1 @todayParams
    if ($LASTEXITCODE -ne 0) {
        Write-Host "live_today failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }

    # 3) Determine DAY
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

    # 4) Validate required artifacts
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

    # 5) Generate order ticket (atomic write via midas)
    $riskPlanCsv = Join-Path $reportDir "risk_plan_h$TicketHorizon.csv"
    $outTicket = Join-Path $reportDir "order_ticket_h$TicketHorizon.txt"
    & $PSScriptRoot\midas_ticket_from_risk_plan.ps1 -RiskPlanPath $riskPlanCsv -OutPath $outTicket
    if ($LASTEXITCODE -ne 0) {
        Write-Host "midas_ticket failed (exit $LASTEXITCODE)"
        exit $LASTEXITCODE
    }

    # 6) Session summary
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
