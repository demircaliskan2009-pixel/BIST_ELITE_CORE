$ErrorActionPreference = "Stop"
$root = (git rev-parse --show-toplevel)
Set-Location $root
Write-Host ("[ROOT] " + (Get-Location).Path)

Write-Host "Setting repo-local Git EOL config..."
git config --local core.autocrlf false
git config --local core.eol lf

Write-Host "Renormalizing index (expected no-op on clean repo)..."
git add --renormalize .

Write-Host "Status:"
git status --porcelain
git diff --stat

Write-Host "DONE."
