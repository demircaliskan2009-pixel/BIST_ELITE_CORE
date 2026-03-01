# FAZ569: Safe tag push — only push tags that do NOT exist on origin. No clobber.
param(
    [string]$Remote = "origin"
)

$repoRoot = Split-Path $PSScriptRoot -Parent
Push-Location $repoRoot

try {
    # Fetch tags from remote (may fail if local tags would clobber; we continue)
    git fetch --tags $Remote 2>$null
    # Don't exit on fetch failure — ls-remote will determine existence

    # Get local tags matching faz### or fazX-stepY
    $allTags = git tag -l | Where-Object { $_ -match '^faz\d+$' -or $_ -match '^faz\d+-step\d+$' }
    $tags = $allTags | Sort-Object

    $pushed = 0
    $skipped = 0

    foreach ($tag in $tags) {
        $ref = "refs/tags/$tag"
        $remoteRef = git ls-remote --tags $Remote $ref 2>&1
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

        $existsOnRemote = $remoteRef -and ("$remoteRef".Trim().Length -gt 0)
        if ($existsOnRemote) {
            Write-Host "SKIP (exists): $tag"
            $skipped++
        } else {
            git push $Remote $ref 2>&1
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            Write-Host "PUSHED: $tag"
            $pushed++
        }
    }

    Write-Host ""
    Write-Host "Summary: pushed=$pushed skipped=$skipped"
    exit 0
} finally {
    Pop-Location
}
