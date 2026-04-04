# BIST Elite Core — run CLI. Run from repo root.
# Usage: .\run.ps1 <subcommand> [args...]
# Example: .\run.ps1 doctor
#          .\run.ps1 ask ASELS --day 2025-01-15 --json
param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CmdArgs
)

$ErrorActionPreference = "Stop"
$root = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
$pyproject = Join-Path $root "pyproject.toml"
if (-not (Test-Path $pyproject)) {
    Write-Error "pyproject.toml not found. Run from repo root."
    exit 1
}

$env:PYTHONPATH = if ($env:PYTHONPATH) { "$root\src;$env:PYTHONPATH" } else { "$root\src" }
if (-not $CmdArgs -or $CmdArgs.Count -eq 0) {
    python -m bist_core.cli --help
} else {
    & python -m bist_core.cli @CmdArgs
}
exit $LASTEXITCODE
