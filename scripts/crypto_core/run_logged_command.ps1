[CmdletBinding(PositionalBinding = $false)]
param(
    [switch]$Help,
    [string]$CommandName = "",
    [int]$TimeoutSeconds = 300,
    [string]$LogPrefix = "crypto_core_logged_command",
    [string]$Command = "",
    [string[]]$Arguments = @(),
    [string]$RepoRoot = "",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArguments = @()
)

if ($Help) {
    Write-Output "Run one local validation command with timeout and C:\tmp stdout/stderr logs."
    Write-Output "Usage:"
    Write-Output '  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_logged_command.ps1 -CommandName "<name>" -TimeoutSeconds <seconds> -LogPrefix "<prefix>" -Command "python" -Arguments "--version"'
    Write-Output '  powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_logged_command.ps1 -CommandName "targeted-pytest" -TimeoutSeconds 180 -LogPrefix "targeted_pytest" -Command "python" -Arguments "-m" "pytest" "-x" "-q" "tests/crypto_core/audit/test_example.py"'
    Write-Output "Optional: -RepoRoot <path>"
    Write-Output "On timeout, only the child process started by this helper is stopped."
    exit 0
}

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($CommandName)) {
    throw "run_logged_command:command_name_required"
}
if ([string]::IsNullOrWhiteSpace($Command)) {
    throw "run_logged_command:command_required"
}
if ($TimeoutSeconds -lt 1) {
    throw "run_logged_command:timeout_seconds_invalid"
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
}
if ($RemainingArguments.Count -gt 0) {
    $Arguments = @($Arguments) + @($RemainingArguments)
}

$env:TMP = "C:\tmp"
$env:TEMP = "C:\tmp"
New-Item -ItemType Directory -Force "C:\tmp" | Out-Null

function ConvertTo-CommandLineArgument {
    param([string]$Value)

    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -notmatch '[\s"]') {
        return $Value
    }
    $escaped = $Value -replace '"', '\"'
    return '"' + $escaped + '"'
}

$stamp = Get-Date -Format "yyyyMMddHHmmss"
$runId = [guid]::NewGuid().ToString("N")
$pathSuffix = "${stamp}_${PID}_${runId}"
$safePrefix = ($LogPrefix -replace '[^A-Za-z0-9_.-]', '_')
$stdoutLog = "C:\tmp\${safePrefix}_${pathSuffix}.out.log"
$stderrLog = "C:\tmp\${safePrefix}_${pathSuffix}.err.log"
$argumentString = (($Arguments | ForEach-Object { ConvertTo-CommandLineArgument $_ }) -join " ")

Write-Output "COMMAND_NAME=$CommandName"
Write-Output "COMMAND=$Command"
Write-Output "ARGUMENTS=$argumentString"
Write-Output "TIMEOUT_SECONDS=$TimeoutSeconds"
Write-Output "STDOUT_LOG=$stdoutLog"
Write-Output "STDERR_LOG=$stderrLog"

$psi = [System.Diagnostics.ProcessStartInfo]::new()
$psi.FileName = $Command
$psi.Arguments = $argumentString
$psi.WorkingDirectory = $RepoRoot
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$process = [System.Diagnostics.Process]::new()
$process.StartInfo = $psi
[void]$process.Start()

$stdoutTask = $process.StandardOutput.ReadToEndAsync()
$stderrTask = $process.StandardError.ReadToEndAsync()
$exited = $process.WaitForExit($TimeoutSeconds * 1000)
$timedOut = -not $exited

if ($timedOut) {
    Write-Output "COMMAND_TIMEOUT PID=$($process.Id)"
    $process.Kill()
    $process.WaitForExit()
}

$stdout = $stdoutTask.GetAwaiter().GetResult()
$stderr = $stderrTask.GetAwaiter().GetResult()
[System.IO.File]::WriteAllText($stdoutLog, $stdout)
[System.IO.File]::WriteAllText($stderrLog, $stderr)

Write-Output "COMMAND_EXIT=$($process.ExitCode)"
Write-Output "COMMAND_TIMED_OUT=$timedOut"
Write-Output "=== STDOUT TAIL ==="
Get-Content $stdoutLog -Tail 120 -ErrorAction SilentlyContinue
Write-Output "=== STDERR TAIL ==="
Get-Content $stderrLog -Tail 120 -ErrorAction SilentlyContinue

if ($timedOut) {
    exit 124
}
exit $process.ExitCode
