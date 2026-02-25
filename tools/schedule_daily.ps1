# FAZ601: Optional Windows scheduler for tools/daily.ps1 (offline).
param(
    [switch]$Enable,
    [switch]$Disable,
    [string]$TaskName = "BIST_ELITE_CORE_Daily",
    [string]$Time = "09:00"
)

$ErrorActionPreference = "Stop"

try {
    $r = git rev-parse --show-toplevel 2>$null
    $RepoRoot = if ($r) { $r.Trim() } else { $null }
    if (-not $RepoRoot) { throw }
} catch {
    $RepoRoot = Split-Path $PSScriptRoot -Parent
}

if (-not $Enable -and -not $Disable) {
    Write-Host "schedule_daily: no action specified. Use -Enable to register or -Disable to remove the task." -ForegroundColor Yellow
    exit 1
}

$scriptPath = Join-Path $RepoRoot "tools\daily.ps1"
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) {
    Write-Host "schedule_daily: daily.ps1 not found at $scriptPath" -ForegroundColor Red
    exit 2
}

if ($Disable) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "schedule_daily: task '$TaskName' removed." -ForegroundColor Green
    } else {
        Write-Host "schedule_daily: task '$TaskName' not found; nothing to remove." -ForegroundColor Yellow
    }
    exit 0
}

# Enable path: create/update scheduled task for current user
try {
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
} catch {
    Write-Host "schedule_daily: failed to create daily trigger at $Time. Use HH:MM 24-hour format." -ForegroundColor Red
    exit 2
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$user = "$env:UserDomain\$env:UserName"
if (-not $env:UserDomain) {
    $user = $env:UserName
}

$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "BIST_ELITE_CORE daily offline run (tools/daily.ps1)" -User $user | Out-Null

Write-Host "schedule_daily: task '$TaskName' registered for user '$user' at $Time (local time)." -ForegroundColor Green
Write-Host "schedule_daily: task runs tools/daily.ps1 with no arguments, under the current user context. No secrets are stored in the task definition." -ForegroundColor Yellow

exit 0

