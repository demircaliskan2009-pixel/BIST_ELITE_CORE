# FAZ598a/FAZ600: Broker runner — manual (offline) and real (fail-closed stub).
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("manual", "real")]
    [string]$Mode,
    [Parameter(Mandatory=$true)]
    [string]$Day,
    [string]$TicketPath = ".\data\log\reports\$Day\order_ticket_h3.txt",
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

if ($Mode -eq "real") {
    Write-Host "broker_run: real mode is not enabled in this repo (fail-closed)." -ForegroundColor Yellow
    Write-Host "  See docs\secrets_policy.md and config\broker.example.yaml for guidance on safe real broker setup." -ForegroundColor Yellow
    Write-Host "  No network calls were made and no orders were sent." -ForegroundColor Green
    exit 2
}

if (-not $FillsPath) {
    Write-Host "broker_run: FillsPath is required in manual mode." -ForegroundColor Red
    exit 2
}

$TicketPathResolved = if ([System.IO.Path]::IsPathRooted($TicketPath)) {
    [System.IO.Path]::GetFullPath($TicketPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $TicketPath))
}

if (-not (Test-Path -LiteralPath $TicketPathResolved)) {
    Write-Host "broker_run: TicketPath not found: $TicketPathResolved" -ForegroundColor Red
    exit 2
}

$FillsPathResolved = if ([System.IO.Path]::IsPathRooted($FillsPath)) {
    [System.IO.Path]::GetFullPath($FillsPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $FillsPath))
}

if (-not (Test-Path -LiteralPath $FillsPathResolved)) {
    Write-Host "broker_run: FillsPath not found: $FillsPathResolved" -ForegroundColor Red
    exit 2
}

$OutRoot = ".\data\log\execution"
$OutRootResolved = if ([System.IO.Path]::IsPathRooted($OutRoot)) {
    [System.IO.Path]::GetFullPath($OutRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutRoot))
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"
& python -m bist_core.execution.import_fills --day $Day --fills $FillsPathResolved --out-root $OutRootResolved
if ($LASTEXITCODE -ne 0) {
    Write-Host "broker_run: import_fills failed (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "broker_run: mode=$Mode day=$Day" -ForegroundColor Green
Write-Host "  ticket: $TicketPathResolved"
Write-Host "  fills:  $FillsPathResolved"
Write-Host "  out:    $OutRootResolved\$Day"

