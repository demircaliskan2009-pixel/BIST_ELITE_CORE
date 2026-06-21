#requires -Version 5.1
<#
.SYNOPSIS
  Read-only crypto_core agent-setup audit. Never modifies files, never installs extensions, never reads
  secrets, never makes network calls except an optional `gh` open-PR count when gh is already authenticated.

.DESCRIPTION
  Prints tracked setup files, validates .vscode/*.json with a JSON parser, reports .vscode/mcp.json server
  state, reports the .cursor BIST alwaysApply rule state, and (best-effort) the open-PR count. Exit code is
  always 0 (advisory). Canonical doctrine: AGENTS.md + docs/crypto_core/agent_workflow.md +
  .codex/skills/crypto-core-max-safe/SKILL.md + docs/crypto_core/agent_lessons.md.
  ASCII-only by design (PowerShell 5.1 reads .ps1 as ANSI without a BOM).
#>

$ErrorActionPreference = 'Continue'
$repo = 'demircaliskan2009-pixel/BIST_ELITE_CORE'

function Write-Section($name) { Write-Output ''; Write-Output "=== $name ===" }

# Resolve a Python interpreter for JSON validation (prefer repo .venv; never required).
$python = $null
foreach ($cand in @('.venv\Scripts\python.exe', 'python', 'python3')) {
  $cmd = Get-Command $cand -ErrorAction SilentlyContinue
  if ($cmd) { $python = $cmd.Source; break }
}

Write-Section 'TRACKED SETUP FILES'
$pattern = 'CLAUDE|AGENTS|codex|claude|vscode|cursor|agent|skill|hook|command|prompt|instruction|lessons|mcp'
try {
  $tracked = git ls-files | Where-Object { $_ -match $pattern }
  if ($tracked) { $tracked | ForEach-Object { Write-Output $_ } } else { Write-Output '(none)' }
} catch { Write-Output "git ls-files unavailable: $($_.Exception.Message)" }

Write-Section 'VSCODE JSON VALIDATION'
$vscodeJson = @('.vscode/settings.json', '.vscode/extensions.json', '.vscode/mcp.json')
foreach ($f in $vscodeJson) {
  if (-not (Test-Path $f)) { Write-Output "$f : ABSENT"; continue }
  if ($null -eq $python) { Write-Output "$f : PRESENT (python not found; not parsed)"; continue }
  & $python -m json.tool $f > $null 2>&1
  if ($LASTEXITCODE -eq 0) { Write-Output "$f : VALID JSON" } else { Write-Output "$f : INVALID JSON" }
}

Write-Section 'MCP SERVERS'
if (-not (Test-Path '.vscode/mcp.json')) {
  Write-Output 'MCP_FILE=ABSENT (no MCP configured)'
} elseif ($null -ne $python) {
  $count = & $python -c "import json; d=json.load(open('.vscode/mcp.json')); print(len(d.get('servers') or {}))" 2>$null
  Write-Output "MCP_FILE=PRESENT MCP_SERVER_COUNT=$count (expected 0; MCP is opt-in/manual)"
} else {
  Write-Output 'MCP_FILE=PRESENT (python not found; server count not parsed)'
}

Write-Section 'CURSOR BIST RULE'
$cursorRule = '.cursor/rules/prdv3-constitution.mdc'
if (-not (Test-Path $cursorRule)) {
  Write-Output "$cursorRule : ABSENT"
} else {
  $always = Select-String -Path $cursorRule -Pattern 'alwaysApply:\s*true' -ErrorAction SilentlyContinue
  if ($always) {
    Write-Output "$cursorRule : alwaysApply=true (WARN: BIST rule should NOT auto-apply to crypto_core)"
  } else {
    Write-Output "$cursorRule : alwaysApply not true (OK: historical, non-applying)"
  }
}

Write-Section 'OPEN PRS (best-effort)'
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
  $open = gh pr list --repo $repo --state open --json number --jq 'length' 2>$null
  if ($LASTEXITCODE -eq 0 -and $null -ne $open) {
    Write-Output "OPEN_PR_COUNT=$open (one-open-PR doctrine)"
  } else {
    Write-Output 'OPEN_PR_COUNT=UNKNOWN (gh not authenticated or offline)'
  }
} else {
  Write-Output 'OPEN_PR_COUNT=UNKNOWN (gh not installed)'
}

Write-Section 'CANONICAL DOCTRINE'
Write-Output 'AGENTS.md + docs/crypto_core/agent_workflow.md + .codex/skills/crypto-core-max-safe/SKILL.md + docs/crypto_core/agent_lessons.md'
Write-Output 'Terminal/git/gh/pytest/ruff are the source of truth; extensions are helpers only.'

exit 0
