# FAZ108: Clean repo — remove __pycache__/, .pyc, .pyo, .bak*, .broken*, proof_*.txt. Skip .git/.venv/node_modules/env/venv.
$repoRoot = Split-Path $PSScriptRoot -Parent

function ShouldSkip {
    param([string]$path)
    $path = $path -replace '/', '\'
    if ($path -match '\.git\\') { return $true }
    if ($path -match '\.venv\\') { return $true }
    if ($path -match '\\node_modules\\') { return $true }
    if ($path -match '\\env\\') { return $true }
    if ($path -match '\\venv\\') { return $true }
    return $false
}

# Remove __pycache__ directories
Get-ChildItem -Path $repoRoot -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue | ForEach-Object {
    if (-not (ShouldSkip $_.FullName)) {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Remove .pyc, .pyo, *\.bak*, *\.broken*, proof_*.txt
Get-ChildItem -Path $repoRoot -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    if (ShouldSkip $_.FullName) { return }
    if ($_.Extension -eq ".pyc" -or $_.Extension -eq ".pyo") {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        return
    }
    if ($_.Name -like "proof_*.txt") {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
        return
    }
    if ($_.Name -match "\.bak" -or $_.Name -match "\.broken") {
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }
}
