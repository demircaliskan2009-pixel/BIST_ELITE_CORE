# FAZ596: Sanity check — python, RepoRoot, SnapshotRoot. No live ops.
param(
    [string]$SnapshotRoot = ""
)

$ErrorActionPreference = "Stop"
try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

Write-Host "sanity_check: Python" -ForegroundColor Cyan
$py = Get-Command python -ErrorAction SilentlyContinue
if ($py) {
    Write-Host "  Location: $($py.Source)"
    & python --version 2>&1
} else {
    Write-Host "  NOT FOUND" -ForegroundColor Red
    exit 2
}

Write-Host "sanity_check: RepoRoot = $RepoRoot" -ForegroundColor Cyan

# SnapshotRoot: param -> env -> auto-discover (same rule as live_session)
if (-not $SnapshotRoot -and $env:BIST_SNAPSHOT_ROOT) { $SnapshotRoot = $env:BIST_SNAPSHOT_ROOT }
if (-not $SnapshotRoot) {
    $searchBase = Join-Path $RepoRoot "data"
    if (Test-Path -LiteralPath $searchBase) {
        $hits = Get-ChildItem -Path $searchBase -Filter "snapshot.csv" -Recurse -File -ErrorAction SilentlyContinue
        $roots = @($hits | ForEach-Object {
            $dayDir = Split-Path $_.FullName -Parent
            Split-Path $dayDir -Parent
        } | Sort-Object -Unique)
        $roots = @($roots)
        if ($roots.Count -eq 1) {
            $SnapshotRoot = [string]($roots | Select-Object -First 1)
        } elseif ($roots.Count -gt 1) {
            $priority = @(
                (Join-Path $RepoRoot "data\eod\snapshots"),
                (Join-Path $RepoRoot "data\snapshots"),
                (Join-Path $RepoRoot "data\raw\eod")
            )
            $pick = $null
            foreach ($p in $priority) {
                $pNorm = [System.IO.Path]::GetFullPath($p)
                $m = @($roots | Where-Object { [System.IO.Path]::GetFullPath($_) -ieq $pNorm })
                if ($m.Count -eq 1) { $pick = $m[0]; break }
            }
            if ($pick) { $SnapshotRoot = [string]$pick }
        }
    }
}

if (-not $SnapshotRoot) {
    Write-Host "sanity_check: SnapshotRoot NOT RESOLVED" -ForegroundColor Red
    Write-Host "  Set env:BIST_SNAPSHOT_ROOT or pass -SnapshotRoot"
    Write-Host "  Example: `$env:BIST_SNAPSHOT_ROOT = 'C:\path\to\data\eod\snapshots'"
    Write-Host "  See tools\env_example.ps1"
    exit 2
}

$SnapshotRootResolved = if ([System.IO.Path]::IsPathRooted($SnapshotRoot)) {
    [System.IO.Path]::GetFullPath($SnapshotRoot)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $RepoRoot $SnapshotRoot))
}

Write-Host "sanity_check: SnapshotRoot = $SnapshotRootResolved" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $SnapshotRootResolved)) {
    Write-Host "sanity_check: SnapshotRoot path does NOT exist" -ForegroundColor Red
    Write-Host "  Set BIST_SNAPSHOT_ROOT to a valid directory containing snapshot.csv files"
    exit 2
}

if (-not (Test-Path -LiteralPath $SnapshotRootResolved -PathType Container)) {
    Write-Host "sanity_check: SnapshotRoot is not a directory" -ForegroundColor Red
    exit 2
}

# Scan snapshot days, warn if any > today
$today = (Get-Date).ToString('yyyy-MM-dd')
$days = @()
$dirsA = @(Get-ChildItem -LiteralPath $SnapshotRootResolved -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
    Where-Object { Test-Path -LiteralPath (Join-Path -Path $_.FullName -ChildPath 'snapshot.csv') -PathType Leaf } |
    Select-Object -ExpandProperty Name)
$days += $dirsA
$snapDir = Join-Path -Path $SnapshotRootResolved -ChildPath 'snapshots'
if (Test-Path -LiteralPath $snapDir -PathType Container) {
    $dirsB = @(Get-ChildItem -LiteralPath $snapDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } |
        Where-Object { Test-Path -LiteralPath (Join-Path -Path $_.FullName -ChildPath 'snapshot.csv') -PathType Leaf } |
        Select-Object -ExpandProperty Name)
    $days += $dirsB
}
$days = @($days | Sort-Object -Unique)
$daysFuture = @($days | Where-Object { $_ -gt $today })
if ($daysFuture.Count -gt 0) {
    $futureList = ($daysFuture | Sort-Object) -join ', '
    Write-Host "sanity_check: warning - snapshot days > today: $futureList" -ForegroundColor Yellow
}

Write-Host "sanity_check: OK" -ForegroundColor Green
exit 0
