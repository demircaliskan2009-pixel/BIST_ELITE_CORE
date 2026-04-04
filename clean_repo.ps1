# FAZ119: Root wrapper — forwards to tools/clean_repo.ps1
& (Join-Path $PSScriptRoot "tools\clean_repo.ps1") @args
