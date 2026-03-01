# FAZ597: Import fills CSV — validate, FIFO PnL, reports. Offline.
param(
    [Parameter(Mandatory=$true)][string]$Day,
    [Parameter(Mandatory=$true)][string]$FillsPath,
    [string]$OutRoot = ".\data\log\execution"
)

$ErrorActionPreference = "Stop"
try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

$FillsPathResolved = if ([System.IO.Path]::IsPathRooted($FillsPath)) {
    [System.IO.Path]::GetFullPath($FillsPath)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $FillsPath))
}
$OutRootResolved = if ([System.IO.Path]::IsPathRooted($OutRoot)) {
    [System.IO.Path]::GetFullPath($OutRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $OutRoot))
}

if (-not (Test-Path -LiteralPath $FillsPathResolved)) {
    Write-Host "import_fills: FillsPath not found: $FillsPathResolved" -ForegroundColor Red
    exit 2
}

$env:PYTHONPATH = Join-Path $RepoRoot "src"
& python -m bist_core.execution.import_fills --day $Day --fills $FillsPathResolved --out-root $OutRootResolved
if ($LASTEXITCODE -ne 0) {
    Write-Host "import_fills failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}
