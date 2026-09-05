#requires -Version 5.1
<#
.SYNOPSIS
  Read-only crypto_core agent-setup audit. Never modifies files, never installs extensions, never reads
  secrets, and makes no network call except an optional best-effort `gh` open-PR count.

.DESCRIPTION
  This script has TWO kinds of check and they are deliberately separated.

  DETERMINISTIC checks decide the exit code. They are:
    1. the Agent OS control-plane contract, delegated in full to
       scripts/crypto_core/validate_agent_os_v2.py;
    2. local workspace configuration that is provable offline (.vscode JSON validity, MCP server
       count, the legacy BIST cursor rule not auto-applying).
  Any deterministic failure - including being unable to EXECUTE the validator - exits non-zero.

  INFORMATIONAL probes never affect the exit code: the tracked setup-file listing and the best-effort
  open-PR count, which needs network and authentication and is therefore reported as UNKNOWN when it
  cannot run.

  Design note (root-cause fix). Earlier revisions of this script re-implemented doctrine parsing here,
  using markdown HEADING NAMES ('## 20. HISTORICAL', '## 24. Active') to decide which region of a
  document was active, and always exited 0. Both were fail-open: renaming or renumbering a heading
  silently skipped the active region, and a real failure still reported success. Region logic now
  lives in exactly one place - the Python validator, which uses explicit structural markers - and this
  script propagates its verdict instead of guessing at one.

  ASCII-only by design (PowerShell 5.1 reads .ps1 as ANSI without a BOM).
#>

$ErrorActionPreference = 'Continue'
$repo = 'demircaliskan2009-pixel/BIST_ELITE_CORE'
$validator = 'scripts/crypto_core/validate_agent_os_v2.py'

$deterministicFailures = New-Object System.Collections.Generic.List[string]

function Write-Section($name) { Write-Output ''; Write-Output "=== $name ===" }

# Resolve a Python interpreter (prefer the repo .venv). Required: the deterministic gate needs it.
$python = $null
foreach ($cand in @('.venv\Scripts\python.exe', 'python', 'python3')) {
  $cmd = Get-Command $cand -ErrorAction SilentlyContinue
  if ($cmd) { $python = $cmd.Source; break }
}

Write-Section 'AGENT OS CONTROL PLANE (deterministic)'
if (-not (Test-Path -LiteralPath $validator)) {
  $deterministicFailures.Add("control-plane validator missing: $validator")
  Write-Output "VALIDATOR=MISSING ($validator)"
} elseif ($null -eq $python) {
  # Cannot execute the deterministic gate. This is a FAILURE, never a silent skip.
  $deterministicFailures.Add('python interpreter not found; the control-plane contract could not be executed')
  Write-Output 'VALIDATOR=NOT_EXECUTED (no python interpreter found)'
} else {
  Write-Output "VALIDATOR=$validator"
  Write-Output "PYTHON=$python"
  & $python $validator
  $validatorExit = $LASTEXITCODE
  Write-Output "VALIDATOR_EXIT=$validatorExit"
  if ($validatorExit -ne 0) {
    $deterministicFailures.Add("control-plane contract failed (validator exit $validatorExit)")
  }
}

Write-Section 'VSCODE JSON VALIDATION (deterministic)'
$vscodeJson = @('.vscode/settings.json', '.vscode/extensions.json', '.vscode/mcp.json')
foreach ($f in $vscodeJson) {
  if (-not (Test-Path -LiteralPath $f)) { Write-Output "$f : ABSENT"; continue }
  if ($null -eq $python) {
    $deterministicFailures.Add("$f present but could not be parsed (no python interpreter)")
    Write-Output "$f : NOT_PARSED (no python interpreter)"
    continue
  }
  & $python -m json.tool $f > $null 2>&1
  if ($LASTEXITCODE -eq 0) {
    Write-Output "$f : VALID JSON"
  } else {
    Write-Output "$f : INVALID JSON"
    $deterministicFailures.Add("$f is not valid JSON")
  }
}

Write-Section 'MCP SERVERS (deterministic)'
if (-not (Test-Path -LiteralPath '.vscode/mcp.json')) {
  Write-Output 'MCP_FILE=ABSENT (no MCP configured)'
} elseif ($null -ne $python) {
  $count = & $python -c "import json; d=json.load(open('.vscode/mcp.json')); print(len(d.get('servers') or {}))" 2>$null
  if ($LASTEXITCODE -ne 0 -or $null -eq $count) {
    Write-Output 'MCP_FILE=PRESENT MCP_SERVER_COUNT=UNPARSEABLE'
    $deterministicFailures.Add('.vscode/mcp.json server count could not be parsed')
  } else {
    Write-Output "MCP_FILE=PRESENT MCP_SERVER_COUNT=$count (expected 0; MCP is opt-in and manual)"
    if ([int]$count -ne 0) {
      $deterministicFailures.Add("MCP server count is $count; expected 0 (MCP is opt-in and manual)")
    }
  }
} else {
  Write-Output 'MCP_FILE=PRESENT (no python interpreter; server count not parsed)'
  $deterministicFailures.Add('.vscode/mcp.json present but the server count could not be parsed')
}

Write-Section 'LEGACY BIST CURSOR RULE (deterministic)'
$cursorRule = '.cursor/rules/prdv3-constitution.mdc'
if (-not (Test-Path -LiteralPath $cursorRule)) {
  Write-Output "$cursorRule : ABSENT"
} else {
  $always = Select-String -Path $cursorRule -Pattern 'alwaysApply:\s*true' -ErrorAction SilentlyContinue
  if ($always) {
    Write-Output "$cursorRule : alwaysApply=true (BIST rule must NOT auto-apply to crypto_core)"
    $deterministicFailures.Add("$cursorRule sets alwaysApply=true; the legacy BIST rule must not auto-apply")
  } else {
    Write-Output "$cursorRule : alwaysApply not true (OK: historical, non-applying)"
  }
}

Write-Section 'TRACKED SETUP FILES (informational)'
# Setup PATHS only. A content-word pattern (for example 'agent' or 'continuity') also matches
# hundreds of product test filenames, which buries the setup inventory it is meant to show.
$pattern = '^(AGENTS\.md|CLAUDE\.md|\.claude/|\.codex/|\.github/|\.vscode/|\.cursor/|docs/crypto_core/|scripts/crypto_core/(audit|validate))'
try {
  $tracked = git ls-files | Where-Object { $_ -match $pattern }
  if ($tracked) { $tracked | ForEach-Object { Write-Output $_ } } else { Write-Output '(none)' }
} catch {
  Write-Output "git ls-files unavailable: $($_.Exception.Message)"
}

Write-Section 'OPEN PRS (informational, best-effort)'
$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
  $open = gh pr list --repo $repo --state open --json number --jq 'length' 2>$null
  if ($LASTEXITCODE -eq 0 -and $null -ne $open) {
    Write-Output "OPEN_PR_COUNT=$open (one-open-PR doctrine; informational only)"
  } else {
    Write-Output 'OPEN_PR_COUNT=UNKNOWN (gh not authenticated or offline)'
  }
} else {
  Write-Output 'OPEN_PR_COUNT=UNKNOWN (gh not installed)'
}

Write-Section 'CANONICAL DOCTRINE'
Write-Output 'Canonical authority: docs/crypto_core/agent_os_v2.md'
Write-Output 'Entrypoint: AGENTS.md   Continuity: docs/crypto_core/continuity/CONTINUITY_INDEX.md'
Write-Output 'Terminal, git, gh, pytest and ruff are the source of truth; extensions are helpers only.'

Write-Section 'RESULT'
if ($deterministicFailures.Count -eq 0) {
  Write-Output 'AGENT_SETUP_AUDIT: PASS (control-plane contract and local configuration checks all passed)'
  $exitCode = 0
} else {
  Write-Output "AGENT_SETUP_AUDIT: FAIL ($($deterministicFailures.Count) deterministic issue(s))"
  foreach ($item in $deterministicFailures) { Write-Output "  - $item" }
  $exitCode = 1
}

if ($MyInvocation.InvocationName -ne '.') {
  exit $exitCode
}
