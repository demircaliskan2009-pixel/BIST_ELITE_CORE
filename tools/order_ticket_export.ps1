# FAZ582: Midas Stage-1 order ticket export wrapper.
param(
    [Parameter(Mandatory=$true)][string]$Orders,
    [string]$Out = ""
)

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    $args = @("--orders", $Orders)
    if ($Out) { $args += @("--out", $Out) }
    & python (Join-Path $repoRoot "tools\order_ticket_export.py") @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
