[CmdletBinding()]
param(
  [string]$SnapshotRoot = "",
  [double]$CapitalTry = 30000,
  [double]$RiskPct = 0.02,
  [int]$AtrN = 14,
  [double]$StopAtrMult = 2.0,
  [double]$TpRMult = 2.0,
  [int]$TicketHorizon = 3,
  [string]$Day = "",
  [string]$FillsPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  return (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

function Write-JsonFile([string]$Path, [object]$Obj) {
  ($Obj | ConvertTo-Json -Depth 20) | Set-Content -Encoding UTF8 $Path
}

$RepoRoot = Resolve-RepoRoot
Set-Location $RepoRoot

$logRoot  = Join-Path $RepoRoot "data\log\scheduler"
$runsRoot = Join-Path $logRoot  "runs"
$lockPath = Join-Path $logRoot  "scheduler.lock"
New-Item -ItemType Directory -Force $runsRoot | Out-Null

$startLocal = Get-Date
$startUtc   = $startLocal.ToUniversalTime()

# Acquire lock (fail-closed if already running)
$lockStream = $null
try {
  New-Item -ItemType Directory -Force $logRoot | Out-Null
  $lockStream = [System.IO.File]::Open(
    $lockPath,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::None
  )
  $lockStream.SetLength(0)
  $w = New-Object System.IO.StreamWriter($lockStream, [System.Text.Encoding]::UTF8, 1024, $true)
  $w.WriteLine("pid=$PID")
  $w.WriteLine("start_local=$($startLocal.ToString('o'))")
  $w.Flush()
} catch {
  Write-Host "scheduler_entrypoint: lock busy (another run active). fail-closed." -ForegroundColor Yellow
  Write-Host "  lock: $lockPath"
  Write-Host "  err:  $($_.Exception.Message)"
  exit 3
}

$dayStamp  = $startLocal.ToString("yyyy-MM-dd")
$timeStamp = $startLocal.ToString("HHmmss")
$runDir = Join-Path $runsRoot (Join-Path $dayStamp $timeStamp)
New-Item -ItemType Directory -Force $runDir | Out-Null

$runLog   = Join-Path $runDir "run.log"
$metaPath = Join-Path $runDir "meta.json"
$resPath  = Join-Path $runDir "result.json"
$lastPath = Join-Path $logRoot "last_run.json"

$sha = ""
try { $sha = (git rev-parse HEAD 2>$null).Trim() } catch { $sha = "" }

$meta = [ordered]@{
  start_time_local = $startLocal.ToString("o")
  start_time_utc   = $startUtc.ToString("o")
  pid              = $PID
  user             = "$env:USERDOMAIN\$env:USERNAME"
  host             = $env:COMPUTERNAME
  repo_root        = $RepoRoot
  repo_sha         = $sha
  args = [ordered]@{
    SnapshotRoot  = $SnapshotRoot
    CapitalTry    = $CapitalTry
    RiskPct       = $RiskPct
    AtrN          = $AtrN
    StopAtrMult   = $StopAtrMult
    TpRMult       = $TpRMult
    TicketHorizon = $TicketHorizon
    Day           = $Day
    FillsPath     = $FillsPath
  }
}
Write-JsonFile -Path $metaPath -Obj $meta

$dailyPath = Join-Path $RepoRoot "tools\daily.ps1"
if (-not (Test-Path $dailyPath)) {
  "daily.ps1 not found: $dailyPath" | Set-Content -Encoding UTF8 $runLog
  exit 2
}

$dailyArgs = @()
if ($SnapshotRoot) { $dailyArgs += @("-SnapshotRoot", $SnapshotRoot) }
$dailyArgs += @("-CapitalTry", "$CapitalTry")
$dailyArgs += @("-RiskPct", "$RiskPct")
$dailyArgs += @("-AtrN", "$AtrN")
$dailyArgs += @("-StopAtrMult", "$StopAtrMult")
$dailyArgs += @("-TpRMult", "$TpRMult")
$dailyArgs += @("-TicketHorizon", "$TicketHorizon")
if ($Day)       { $dailyArgs += @("-Day", $Day) }
if ($FillsPath) { $dailyArgs += @("-FillsPath", $FillsPath) }

$exitCode = 1
try {
  "scheduler_entrypoint: start $($startLocal.ToString('u'))" | Add-Content -Encoding UTF8 $runLog
  "scheduler_entrypoint: daily args: $($dailyArgs -join ' ')" | Add-Content -Encoding UTF8 $runLog

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $dailyPath @dailyArgs 2>&1 |
    Tee-Object -FilePath $runLog -Append

  $exitCode = $LASTEXITCODE
} catch {
  $exitCode = 1
  "scheduler_entrypoint: exception: $($_.Exception.Message)" | Add-Content -Encoding UTF8 $runLog
} finally {
  $endLocal = Get-Date
  $endUtc   = $endLocal.ToUniversalTime()
  $durSec   = [math]::Round(($endLocal - $startLocal).TotalSeconds, 3)

  $res = [ordered]@{
    end_time_local = $endLocal.ToString("o")
    end_time_utc   = $endUtc.ToString("o")
    duration_sec   = $durSec
    exit_code      = $exitCode
    ok             = ($exitCode -eq 0)
    run_dir        = $runDir
  }

  Write-JsonFile -Path $resPath  -Obj $res
  Write-JsonFile -Path $lastPath -Obj $res

  try {
    if ($lockStream) {
      $lockStream.SetLength(0)
      $w2 = New-Object System.IO.StreamWriter($lockStream, [System.Text.Encoding]::UTF8, 1024, $true)
      $w2.WriteLine("pid=$PID")
      $w2.WriteLine("start_local=$($startLocal.ToString('o'))")
      $w2.WriteLine("end_local=$($endLocal.ToString('o'))")
      $w2.WriteLine("exit_code=$exitCode")
      $w2.Flush()
    }
  } catch { }

  if ($lockStream) { $lockStream.Close(); $lockStream.Dispose() }
}

Write-Host "scheduler_entrypoint: exit_code=$exitCode run_dir=$runDir"
exit $exitCode
