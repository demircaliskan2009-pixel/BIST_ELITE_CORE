[CmdletBinding()]
param(
  [int]$Tail = 120
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$logRoot  = Join-Path $RepoRoot "data\log\scheduler"
$lastPath = Join-Path $logRoot  "last_run.json"
$runsRoot = Join-Path $logRoot  "runs"

function Read-Json([string]$p) {
  if (Test-Path $p) { return (Get-Content $p -Raw | ConvertFrom-Json) }
  return $null
}

$last = Read-Json $lastPath
$runDir = $null

if ($last -and $last.run_dir) { $runDir = [string]$last.run_dir }

if (-not $runDir -or -not (Test-Path $runDir)) {
  if (Test-Path $runsRoot) {
    $latest = Get-ChildItem $runsRoot -Recurse -Directory -ErrorAction SilentlyContinue |
      Sort-Object LastWriteTime -Descending |
      Select-Object -First 1
    if ($latest) { $runDir = $latest.FullName }
  }
}

if (-not $runDir) {
  Write-Host "scheduler_status: no runs found under $runsRoot" -ForegroundColor Yellow
  exit 2
}

$meta = Read-Json (Join-Path $runDir "meta.json")
$res  = Read-Json (Join-Path $runDir "result.json")
$runLog = Join-Path $runDir "run.log"

Write-Host "=== SCHEDULER STATUS ==="
Write-Host "run_dir: $runDir"
if ($meta) {
  Write-Host ("start_local: " + $meta.start_time_local)
  if ($meta.repo_sha) { Write-Host ("repo_sha:     " + $meta.repo_sha) }
}
if ($res) {
  Write-Host ("end_local:    " + $res.end_time_local)
  Write-Host ("exit_code:    " + $res.exit_code)
  Write-Host ("ok:           " + $res.ok)
  Write-Host ("duration_sec: " + $res.duration_sec)
}

if (Test-Path $runLog) {
  Write-Host ""
  Write-Host "=== run.log (tail $Tail) ==="
  Get-Content $runLog -Tail $Tail
} else {
  Write-Host "run.log missing: $runLog" -ForegroundColor Yellow
}

try {
  $t = "BIST_ELITE_CORE_Daily"
  $st = Get-ScheduledTask -TaskName $t -ErrorAction Stop
  $info = Get-ScheduledTaskInfo -TaskName $t -ErrorAction Stop
  Write-Host ""
  Write-Host "=== TaskScheduler ==="
  Write-Host "TaskName: $t"
  Write-Host "State:    $($st.State)"
  Write-Host "LastRun:  $($info.LastRunTime)"
  Write-Host "LastRes:  $($info.LastTaskResult)"
  Write-Host "NextRun:  $($info.NextRunTime)"
} catch { }
