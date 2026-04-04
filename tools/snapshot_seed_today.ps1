[CmdletBinding()]
param(
  [string]$SnapshotRoot = "",
  [switch]$TouchTimestamp
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

$RepoRoot = Resolve-RepoRoot

if ([string]::IsNullOrWhiteSpace($SnapshotRoot)) {
  if (-not [string]::IsNullOrWhiteSpace($env:BIST_SNAPSHOT_ROOT)) {
    $SnapshotRoot = $env:BIST_SNAPSHOT_ROOT
  } else {
    $SnapshotRoot = Join-Path $RepoRoot "data\eod\snapshots"
  }
}

if (-not (Test-Path $SnapshotRoot)) {
  Write-Host "snapshot_seed_today: SnapshotRoot not found: $SnapshotRoot" -ForegroundColor Red
  exit 2
}

$today  = (Get-Date).ToString("yyyy-MM-dd")
$dstDir = Join-Path $SnapshotRoot $today
$dstCsv = Join-Path $dstDir "snapshot.csv"

if (Test-Path $dstCsv) {
  Write-Host "snapshot_seed_today: OK (already exists): $dstCsv" -ForegroundColor Green
  exit 0
}

# Find latest day <= today that has snapshot.csv
$src = Get-ChildItem $SnapshotRoot -Directory |
  Where-Object {
    $_.Name -match '^\d{4}-\d{2}-\d{2}$' -and
    $_.Name -le $today -and
    (Test-Path (Join-Path $_.FullName "snapshot.csv"))
  } |
  Sort-Object Name -Descending |
  Select-Object -First 1

if (-not $src) {
  Write-Host "snapshot_seed_today: No source snapshot.csv found under $SnapshotRoot for any day <= $today" -ForegroundColor Red
  exit 2
}

$srcCsv = Join-Path $src.FullName "snapshot.csv"

New-Item -ItemType Directory -Force $dstDir | Out-Null
Copy-Item $srcCsv $dstCsv -Force

if ($TouchTimestamp) {
  (Get-Item $dstCsv).LastWriteTime = Get-Date
}

Write-Host "snapshot_seed_today: COPIED $($src.Name)\snapshot.csv -> $today\snapshot.csv" -ForegroundColor Yellow
Write-Host "snapshot_seed_today: dst=$dstCsv"
exit 0
