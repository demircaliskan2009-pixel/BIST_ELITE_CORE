# FAZ601/FAZ604: Optional Windows scheduler for tools/daily.ps1 (offline).
param(
    [switch]$Enable,
    [switch]$Disable,
    [string]$TaskName = "BIST_ELITE_CORE_Daily",
    [string]$Time = "09:00",
    [string]$SnapshotRoot = "",
    [string]$CapitalTry = "",
    [string]$RiskPct = "",
    [string]$AtrN = "",
    [string]$StopAtrMult = "",
    [string]$TpRMult = "",
    [int]$TicketHorizon = 0
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

# Determine whether any explicit daily.ps1 args were provided
$anyExplicitArgs = $false
foreach ($name in @("SnapshotRoot", "CapitalTry", "RiskPct", "AtrN", "StopAtrMult", "TpRMult", "TicketHorizon")) {
    if ($PSBoundParameters.ContainsKey($name)) {
        if ($name -eq "TicketHorizon") {
            if ($TicketHorizon -gt 0) { $anyExplicitArgs = $true; break }
        } else {
            $val = Get-Variable -Name $name -ValueOnly
            if ($val -and ($val -isnot [string] -or $val.Trim() -ne "")) {
                $anyExplicitArgs = $true
                break
            }
        }
    }
}

# Resolve SnapshotRoot for scheduled runs (optional)
$effectiveSnapshotRoot = $null
if ($PSBoundParameters.ContainsKey("SnapshotRoot") -and $SnapshotRoot) {
    $effectiveSnapshotRoot = $SnapshotRoot
} elseif ($anyExplicitArgs) {
    if ($env:BIST_SNAPSHOT_ROOT) {
        $effectiveSnapshotRoot = $env:BIST_SNAPSHOT_ROOT
    } else {
        $defaultSnapshots = Join-Path $RepoRoot "data\eod\snapshots"
        if (Test-Path -LiteralPath $defaultSnapshots -PathType Container) {
            $effectiveSnapshotRoot = $defaultSnapshots
        }
    }
}

# Build argument list for powershell.exe
$argList = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$scriptPath`""
)

if ($anyExplicitArgs -or $effectiveSnapshotRoot) {
    if ($effectiveSnapshotRoot) {
        $argList += @("-SnapshotRoot", "`"$effectiveSnapshotRoot`"")
    }
    if ($PSBoundParameters.ContainsKey("CapitalTry") -and $CapitalTry -and $CapitalTry.Trim() -ne "") {
        $argList += @("-CapitalTry", $CapitalTry)
    }
    if ($PSBoundParameters.ContainsKey("RiskPct") -and $RiskPct -and $RiskPct.Trim() -ne "") {
        $argList += @("-RiskPct", $RiskPct)
    }
    if ($PSBoundParameters.ContainsKey("AtrN") -and $AtrN -and $AtrN.Trim() -ne "") {
        $argList += @("-AtrN", $AtrN)
    }
    if ($PSBoundParameters.ContainsKey("StopAtrMult") -and $StopAtrMult -and $StopAtrMult.Trim() -ne "") {
        $argList += @("-StopAtrMult", $StopAtrMult)
    }
    if ($PSBoundParameters.ContainsKey("TpRMult") -and $TpRMult -and $TpRMult.Trim() -ne "") {
        $argList += @("-TpRMult", $TpRMult)
    }
    if ($PSBoundParameters.ContainsKey("TicketHorizon") -and $TicketHorizon -gt 0) {
        $argList += @("-TicketHorizon", $TicketHorizon)
    }
}

$argument = [string]::Join(" ", $argList)

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argument

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
Write-Host "schedule_daily: command line:" -ForegroundColor Cyan
Write-Host "  powershell.exe $argument" -ForegroundColor Cyan
Write-Host "schedule_daily: task runs tools/daily.ps1 under the current user context. No secrets are stored in the task definition." -ForegroundColor Yellow

exit 0

