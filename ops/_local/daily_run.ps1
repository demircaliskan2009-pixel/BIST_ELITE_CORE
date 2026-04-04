param(
  [string]$DAY = ""
)

$ErrorActionPreference = "Stop"

# --- Robust repo root (Scheduler/System32 dahil) ---
$scriptPath = $MyInvocation.MyCommand.Path
if ($scriptPath) {
  $opsDir = Split-Path -Parent $scriptPath
  $ROOT = (Resolve-Path (Join-Path $opsDir "..")).Path
} elseif ($PSScriptRoot) {
  $ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
} else {
  $ROOT = (Resolve-Path ".").Path
}
Set-Location $ROOT

# --- venv ---
$VENV = Join-Path $ROOT ".venv\Scripts\Activate.ps1"
if (!(Test-Path $VENV)) { throw "Missing venv activate: $VENV" }
. $VENV

# --- UTF-8 ---
chcp 65001 > $null
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$utf8 = New-Object System.Text.UTF8Encoding($false)

if ([string]::IsNullOrWhiteSpace($DAY)) {
  $DAY = (Get-Date).ToString("yyyy-MM-dd")
}

$DATA_ROOT = (Resolve-Path ".\data").Path
$OUT_DIR  = Join-Path $ROOT "out\$DAY"
$LOG_DIR  = Join-Path $ROOT "logs"
New-Item -ItemType Directory -Force $OUT_DIR | Out-Null
New-Item -ItemType Directory -Force $LOG_DIR | Out-Null
$LOG = Join-Path $LOG_DIR "$DAY.log"

function LogLine([string]$s) {
  [IO.File]::AppendAllText($LOG, $s + "`r`n", $utf8)
}

function RunPythonRedirect(
  [string]$stdoutPath,
  [string]$stderrPath,
  [string]$tag,
  [string[]]$pyArgs,
  [int]$timeoutSec = 180,
  [switch]$AllowFail
) {
  if (-not $pyArgs -or $pyArgs.Count -eq 0) { throw "Internal: empty pyArgs for tag=$tag" }

  if (Test-Path $stdoutPath) { Remove-Item $stdoutPath -Force }
  if (Test-Path $stderrPath) { Remove-Item $stderrPath -Force }

  $argLine = ($pyArgs -join ' ')
  Write-Host ">>> [$tag] python $argLine" -ForegroundColor Cyan
  LogLine ("[RUN] " + $tag + " :: python " + $argLine)

  $p = Start-Process -FilePath "python" -ArgumentList $pyArgs -WorkingDirectory $ROOT -NoNewWindow -PassThru `
        -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath

  $sw = [Diagnostics.Stopwatch]::StartNew()
  while (-not $p.HasExited) {
    Start-Sleep -Seconds 1
    if ($sw.Elapsed.TotalSeconds -gt $timeoutSec) {
      try { $p.Kill() } catch {}
      $msg = "TIMEOUT ${timeoutSec}s :: $tag"
      LogLine ("[TIMEOUT] " + $msg + " :: stdout=" + $stdoutPath + " stderr=" + $stderrPath)
      if ($AllowFail) { return }
      throw $msg
    }
  }

  # PS 5.1: ExitCode bazen WaitForExit olmadan boş kalıyor
  try { $p.WaitForExit() } catch {}

  $sw.Stop()

  $exit = 0
  try { $exit = [int]$p.ExitCode } catch { $exit = 0 }

  LogLine ("[DONE] " + $tag + " exit=" + $exit + " ms=" + [int]$sw.Elapsed.TotalMilliseconds + " :: stdout=" + $stdoutPath)

  if ($exit -ne 0) {
    $msg = "python failed exit=$exit :: $tag (bkz: $stderrPath)"
    if ($AllowFail) { LogLine("[WARN] " + $msg); return }
    throw $msg
  }
}

$HORIZON="mid"
$RISK="low"
$CAPITAL="300000"
$MAXLOSS="20000"

$WATCH = Join-Path $DATA_ROOT "universe\watchlist.txt"
if (!(Test-Path $WATCH)) { throw "Missing watchlist: $WATCH" }

[IO.File]::WriteAllText($LOG, "=== DAILY RUN $DAY ===`r`n", $utf8)
LogLine "ROOT=$ROOT"
LogLine "DATA_ROOT=$DATA_ROOT"
LogLine "OUT_DIR=$OUT_DIR"

# 1) scan
LogLine "--- scan ---"
RunPythonRedirect `
  (Join-Path $OUT_DIR "scan.json") `
  (Join-Path $OUT_DIR "scan.stderr.txt") `
  "scan" `
  @(
    "-X","utf8",
    "-m","bist_core.cli.main","scan",
    "--day",$DAY,"--root",$DATA_ROOT,
    "--top-n","20",
    "--horizon",$HORIZON,"--risk",$RISK,
    "--capital",$CAPITAL,"--max-loss-tl",$MAXLOSS,
    "--json"
  ) `
  -timeoutSec 180 -AllowFail

# 2) ask per watchlist
Get-Content $WATCH | ForEach-Object {
  $SYM = $_.Trim().ToUpper()
  if ($SYM -eq "") { return }

  LogLine "--- ask $SYM ---"
  RunPythonRedirect `
    (Join-Path $OUT_DIR "$SYM.json") `
    (Join-Path $OUT_DIR "$SYM.stderr.txt") `
    ("ask:" + $SYM) `
    @(
      "-X","utf8",
      "-m","bist_core.cli.main","ask",$SYM,
      "--day",$DAY,"--root",$DATA_ROOT,
      "--horizon",$HORIZON,"--risk",$RISK,
      "--capital",$CAPITAL,"--max-loss-tl",$MAXLOSS,
      "--json"
    ) `
    -timeoutSec 120
}

LogLine "=== DONE $DAY ==="
Write-Host "=== DONE $DAY ===" -ForegroundColor Green
