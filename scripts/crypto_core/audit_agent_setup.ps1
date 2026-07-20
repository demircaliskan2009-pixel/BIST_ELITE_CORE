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

Write-Section 'AGENT OS v5.2 ROUTING (CRYPTO_CORE_AGENT_OS_V1)'
# Deterministic verification that Fable is retired and the eight-lane read-only-first controller doctrine is
# in force. Advisory (this script always exits 0); it never mutates and never weakens the checks above.

$os52 = New-Object System.Collections.Generic.List[string]

# Active doctrine text with the HISTORICAL sections (agent_workflow.md 20-23) and trailing dated changelog
# blocks removed, so legitimate archival/changelog Fable history never trips the active-routing checks.
function Get-ActiveDoctrineText($path) {
  if (-not (Test-Path $path)) { return $null }
  $raw = Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue
  if ($null -eq $raw) { return $null }
  $lines = $raw -split "`r?`n"
  $out = New-Object System.Collections.Generic.List[string]
  $inHist = $false
  foreach ($ln in $lines) {
    if ($ln -match '^## 20\. HISTORICAL') { $inHist = $true; continue }
    if ($ln -match '^## 24\. Active') { $inHist = $false }
    if ($ln -match '^\*(v[0-9]|Last updated)') { break }
    if ($inHist) { continue }
    $out.Add($ln)
  }
  return ($out -join "`n")
}

function Get-RawText($path) {
  if (-not (Test-Path $path)) { return $null }
  return (Get-Content -LiteralPath $path -Raw -ErrorAction SilentlyContinue)
}

$activeDoctrineFiles = @(
  'AGENTS.md',
  'CLAUDE.md',
  'docs/crypto_core/agent_workflow.md',
  'docs/crypto_core/model_prompting_guide.md',
  'docs/crypto_core/token_efficiency_playbook.md',
  'docs/crypto_core/agent_prompts/token_efficiency_v2.md',
  'docs/crypto_core/deep_research_protocol.md',
  '.claude/skills/crypto-core-token-efficient-loop/SKILL.md',
  '.codex/skills/crypto-core-max-safe/SKILL.md'
)

# 1) Exactly the eight active lanes are named in AGENTS.md, and Fable is not among them.
$agentsRaw = Get-RawText 'AGENTS.md'
$eightLanes = @(
  'ChatGPT GPT-5.6 Thinking', 'GitHub connector', 'Deep Research', 'Claude Opus 4.8',
  'Claude Sonnet 5', 'Codex GPT-5.6 Sol', 'Codex GPT-5.6 Terra', 'Codex GPT-5.6 Luna'
)
if ($null -eq $agentsRaw) {
  $os52.Add('AGENTS.md missing')
} else {
  foreach ($lane in $eightLanes) {
    if ($agentsRaw -notmatch [regex]::Escape($lane)) { $os52.Add("active lane missing in AGENTS.md: $lane") }
  }
}

# 2) Fable is retired everywhere it is named as an active lane, and active surge machinery is gone.
$forbiddenActivePhrases = @(
  'ACTIVE but CONDITIONAL', 'ACTIVE, CONDITIONAL', 'ACTIVE CONDITIONAL',
  'runtime-proven premium surge lane', 'runtime-proven PREMIUM SURGE', 'premium surge lane (ACTIVE',
  'active Fable routing exists', 'Fable 5 surge (gate-passed)', 'Fable 5 surge (justification-gated)',
  'Fable 5 challenge (optional', 'gate-justified surge'
)
$surgeTokenPattern = 'FABLE5_PREMIUM_SURGE_LANE|FABLE5_JUSTIFICATION_GATE|FABLE5_SURGE_IMPLEMENTER|FABLE5_CROSS_CONTRACT_CHALLENGE|FABLE5_FULL_REPO_AUDIT|FABLE_SECOND_OPINION_IF_JUSTIFIED'
$retiredMarker = 'retired|INACTIVE_EXPIRED_RETIRED|HISTORICAL|SUPERSEDED|ARCHIVAL|archiv|former|Pre-v5|never|not an active|not a research|routable|redistribut|no `FABLE|no FABLE'
foreach ($f in $activeDoctrineFiles) {
  if ($f -eq 'docs/crypto_core/agent_workflow.md') { $text = Get-ActiveDoctrineText $f } else { $text = Get-RawText $f }
  if ($null -eq $text) { $os52.Add("active doctrine file missing: $f"); continue }
  foreach ($p in $forbiddenActivePhrases) {
    if ($text -match [regex]::Escape($p)) { $os52.Add("active Fable phrase '$p' present in $f") }
  }
  foreach ($ln in ($text -split "`r?`n")) {
    if ($ln -match $surgeTokenPattern -and $ln -notmatch $retiredMarker) {
      $os52.Add("active Fable surge token without retirement marker in ${f}: $($ln.Trim())")
    }
  }
}

# 3) The active FABLE5_JUSTIFICATION_GATE machinery must not be present un-negated in the active surface.
foreach ($f in @('AGENTS.md', 'CLAUDE.md', 'docs/crypto_core/model_prompting_guide.md', 'docs/crypto_core/agent_prompts/token_efficiency_v2.md')) {
  $text = Get-RawText $f
  if ($null -ne $text) {
    foreach ($ln in ($text -split "`r?`n")) {
      if ($ln -match 'FABLE5_JUSTIFICATION_GATE' -and $ln -notmatch $retiredMarker) {
        $os52.Add("FABLE5_JUSTIFICATION_GATE present un-negated in ${f}: $($ln.Trim())")
      }
    }
  }
}

# 4) CONTROLLER_READONLY_FIRST_POLICY markers exist in the required surfaces.
$policySurfaces = @(
  'AGENTS.md', 'docs/crypto_core/agent_workflow.md', 'docs/crypto_core/model_prompting_guide.md',
  '.codex/skills/crypto-core-max-safe/SKILL.md', '.claude/skills/crypto-core-token-efficient-loop/SKILL.md'
)
foreach ($f in $policySurfaces) {
  $text = Get-RawText $f
  if ($null -eq $text -or $text -notmatch 'CONTROLLER_READONLY_FIRST_POLICY') {
    $os52.Add("CONTROLLER_READONLY_FIRST_POLICY marker missing in $f")
  }
}

# 5) Role keywords: Opus default-heavy, Sonnet bounded, Sol Class-C, Terra conditional audit, Luna mechanical.
$wf = Get-RawText 'docs/crypto_core/agent_workflow.md'
if ($null -ne $wf) {
  if ($wf -notmatch 'default heavy local executor') { $os52.Add('Opus default-heavy role phrase missing in agent_workflow.md') }
  if ($wf -notmatch 'Sonnet 5') { $os52.Add('Sonnet 5 bounded role missing in agent_workflow.md') }
  if ($wf -notmatch 'Class-C' -and $wf -notmatch 'Class C') { $os52.Add('Sol Class-C role missing in agent_workflow.md') }
  if ($wf -notmatch 'Terra') { $os52.Add('Terra role missing in agent_workflow.md') }
  if ($wf -notmatch 'LUNA_MECHANICAL' -and $wf -notmatch 'Luna') { $os52.Add('Luna mechanical role missing in agent_workflow.md') }
}

# 6) Copilot remains INACTIVE_UNAVAILABLE, Fable labelled INACTIVE_EXPIRED_RETIRED.
if ($null -ne $agentsRaw -and $agentsRaw -notmatch 'INACTIVE_UNAVAILABLE') { $os52.Add('Copilot INACTIVE_UNAVAILABLE marker missing in AGENTS.md') }
foreach ($f in @('AGENTS.md', 'CLAUDE.md', 'docs/crypto_core/agent_workflow.md', 'docs/crypto_core/model_prompting_guide.md')) {
  $text = Get-RawText $f
  if ($null -ne $text -and $text -notmatch 'INACTIVE_EXPIRED_RETIRED') { $os52.Add("Fable INACTIVE_EXPIRED_RETIRED marker missing in $f") }
}

# 7) No active hardcoded current-state SHA/PR pin in the active routing surfaces (LIVE_STATE_POLICY).
foreach ($f in @('AGENTS.md', 'docs/crypto_core/agent_workflow.md')) {
  $text = Get-ActiveDoctrineText $f
  if ($null -ne $text) {
    if ($text -match '[0-9a-f]{40}') { $os52.Add("active hardcoded 40-hex SHA pin present in $f") }
    if ($text -match 'main contains PR') { $os52.Add("active 'main contains PR' state pin present in $f") }
  }
}

# 8) Local CLAUDE.local.md, when present, has no active Fable routing (active region only).
if (Test-Path 'CLAUDE.local.md') {
  $localText = Get-ActiveDoctrineText 'CLAUDE.local.md'
  if ($null -ne $localText) {
    foreach ($p in $forbiddenActivePhrases) {
      if ($localText -match [regex]::Escape($p)) { $os52.Add("active Fable phrase '$p' present in CLAUDE.local.md") }
    }
    foreach ($ln in ($localText -split "`r?`n")) {
      if ($ln -match $surgeTokenPattern -and $ln -notmatch $retiredMarker) {
        $os52.Add("active Fable surge token without retirement marker in CLAUDE.local.md: $($ln.Trim())")
      }
    }
  }
  Write-Output 'CLAUDE_LOCAL=PRESENT (untracked; active-region Fable routing checked)'
} else {
  Write-Output 'CLAUDE_LOCAL=ABSENT (skipped)'
}

if ($os52.Count -eq 0) {
  Write-Output 'AGENT_OS_V52_ROUTING_AUDIT: PASS (8 active lanes; Fable INACTIVE_EXPIRED_RETIRED; controller read-only-first; no active state pins)'
} else {
  Write-Output "AGENT_OS_V52_ROUTING_AUDIT: FAIL ($($os52.Count) issue(s))"
  foreach ($i in $os52) { Write-Output "  - $i" }
}

Write-Section 'CANONICAL DOCTRINE'
Write-Output 'AGENTS.md + docs/crypto_core/agent_workflow.md + .codex/skills/crypto-core-max-safe/SKILL.md + docs/crypto_core/agent_lessons.md'
Write-Output 'Terminal/git/gh/pytest/ruff are the source of truth; extensions are helpers only.'

exit 0
