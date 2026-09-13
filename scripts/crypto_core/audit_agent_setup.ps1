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
    2. local workspace configuration that is provable offline (.vscode JSON validity and the MCP
       server count, both parsed by the validator's strict JSON primitive, and the legacy BIST
       cursor rule, judged by the validator's one NON_APPLYING front-matter contract).
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

.PARAMETER PythonExe
  Interpreter to run the validator with. Defaults to the normal resolution order. It exists so the
  contract oracle can drive the REAL validator-invocation path with an interpreter that cannot
  launch; source inspection cannot prove a fail-closed launch.

.PARAMETER ValidatorOnly
  Run only the deterministic control-plane section and exit with its verdict. Offline and fast, so
  the oracle can execute this script without the informational network probes.

.PARAMETER Offline
  Skip the only network probe, the best-effort open-PR count, so the contract oracle can execute
  every deterministic check - including the workspace JSON checks - without network access.
#>

[CmdletBinding(PositionalBinding = $false)]
param(
  [string]$PythonExe = '',
  [switch]$ValidatorOnly,
  [switch]$Offline,
  [switch]$ExitStatusProbe,
  $ProbeExitStatus = $null
)

if ($ExitStatusProbe) {
  # Drives ONLY the exit-status classification above, with a caller-supplied value, so the contract
  # oracle can prove the type rule against shapes no real process can produce.
  $validatorExit = $ProbeExitStatus
  if ($null -eq $validatorExit) { Write-Output 'VALIDATOR_EXIT=NO_EXIT_STATUS'; exit 1 }
  if (-not ($validatorExit -is [int])) {
    Write-Output ("VALIDATOR_EXIT=INVALID_EXIT_STATUS_TYPE (" + $validatorExit.GetType().FullName + ")")
    exit 1
  }
  if ($validatorExit -eq 0) { Write-Output 'VALIDATOR_EXIT=0'; exit 0 }
  Write-Output "VALIDATOR_EXIT=$validatorExit"
  exit 1
}

$ErrorActionPreference = 'Continue'
$repo = 'demircaliskan2009-pixel/BIST_ELITE_CORE'
$validator = 'scripts/crypto_core/validate_agent_os_v2.py'

$deterministicFailures = New-Object System.Collections.Generic.List[string]

function Write-Section($name) { Write-Output ''; Write-Output "=== $name ===" }

# Resolve a Python interpreter (prefer the repo .venv). Required: the deterministic gate needs it.
$python = $null
if ($PythonExe -ne '') {
  $python = $PythonExe
} else {
  foreach ($cand in @('.venv\Scripts\python.exe', 'python', 'python3')) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    if ($cmd) { $python = $cmd.Source; break }
  }
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
  # FAIL_CLOSED_SETUP_AUDIT_EXECUTION_V1. $LASTEXITCODE is a global automatic variable and a
  # launch that never starts a process does not set it, so a 0 left by ANY earlier native command
  # was being read as 'the validator passed'. Clear it first: 'no exit status' must be
  # distinguishable from 'exit status 0'. The try/catch covers a terminating launch error.
  $global:LASTEXITCODE = $null
  $validatorExit = $null
  $launchError = ''
  try {
    & $python $validator
    $validatorExit = $global:LASTEXITCODE
  } catch {
    $launchError = $_.Exception.Message
  }
  # EXACT_EXECUTION_STATUS_TYPE. '-ne 0' coerces: '0', 0.0 and $false all compare equal to 0, and
  # '@() -ne 0' returns an empty array whose falsiness skips the failure branch. Four non-process
  # values were therefore readable as a successful run. A process exit status is an [int]; that type
  # is established BEFORE any zero/nonzero judgement, and everything else fails closed by name.
  if ($null -eq $validatorExit) {
    Write-Output 'VALIDATOR_EXIT=NO_EXIT_STATUS'
    $detail = if ($launchError -ne '') { $launchError } else { 'the process did not start' }
    $deterministicFailures.Add(
      "control-plane contract NOT EXECUTED: the validator produced no exit status ($detail); " +
      'an absent exit status is never success')
  } elseif (-not ($validatorExit -is [int])) {
    $observed = $validatorExit.GetType().FullName
    Write-Output "VALIDATOR_EXIT=INVALID_EXIT_STATUS_TYPE ($observed)"
    $deterministicFailures.Add(
      "control-plane contract NOT EXECUTED: the exit status was [$observed], not a process exit " +
      'code; a value PowerShell can merely coerce to zero is never success')
  } elseif ($validatorExit -eq 0) {
    Write-Output 'VALIDATOR_EXIT=0'
  } else {
    Write-Output "VALIDATOR_EXIT=$validatorExit"
    $deterministicFailures.Add("control-plane contract failed (validator exit $validatorExit)")
  }
}

if ($ValidatorOnly) {
  Write-Output ''
  Write-Output '=== RESULT ==='
  if ($deterministicFailures.Count -gt 0) {
    foreach ($f in $deterministicFailures) { Write-Output "FAIL: $f" }
    Write-Output 'AGENT_SETUP_AUDIT: FAIL (validator-only)'
    exit 1
  }
  Write-Output 'AGENT_SETUP_AUDIT: PASS (validator-only)'
  exit 0
}

Write-Section 'VSCODE JSON VALIDATION (deterministic)'
# STRICT_JSON_EVIDENCE_BOUNDARY. `python -m json.tool` and `json.load` keep the LAST copy of a
# repeated member name and accept NaN, so an ambiguous file was reported VALID and a server list
# hidden behind a later duplicate was counted as zero. Every JSON file this audit judges is parsed
# by the validator's one strict primitive instead; -B keeps that import from writing bytecode
# into the repository. The same exit-status type rule as the validator call applies.
$agentOs = "import sys; sys.path.insert(0, 'scripts/crypto_core'); import validate_agent_os_v2 as agent_os; "
$vscodeJson = @('.vscode/settings.json', '.vscode/extensions.json', '.vscode/mcp.json')
foreach ($f in $vscodeJson) {
  if (-not (Test-Path -LiteralPath $f)) { Write-Output "$f : ABSENT"; continue }
  if ($null -eq $python) {
    $deterministicFailures.Add("$f present but could not be parsed (no python interpreter)")
    Write-Output "$f : NOT_PARSED (no python interpreter)"
    continue
  }
  $global:LASTEXITCODE = $null
  & $python -B -c ($agentOs + 'agent_os.load_strict_json_file(sys.argv[1])') $f > $null 2>&1
  if (($LASTEXITCODE -is [int]) -and $LASTEXITCODE -eq 0) {
    Write-Output "$f : VALID JSON"
  } else {
    Write-Output "$f : INVALID JSON"
    $deterministicFailures.Add("$f is not valid strict JSON (repeated member names, non-finite numbers and malformed JSON are refused)")
  }
}

Write-Section 'MCP SERVERS (deterministic)'
if (-not (Test-Path -LiteralPath '.vscode/mcp.json')) {
  Write-Output 'MCP_FILE=ABSENT (no MCP configured)'
} elseif ($null -ne $python) {
  $global:LASTEXITCODE = $null
  $count = & $python -B -c ($agentOs + "d = agent_os.load_strict_json_file('.vscode/mcp.json'); print(len(d.get('servers') or {}))") 2>$null
  if (-not ($LASTEXITCODE -is [int]) -or $LASTEXITCODE -ne 0 -or $null -eq $count) {
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
# ACTIVE_CONTROL_PLANE_SURFACE_SEMANTICS. Whether this rule can apply is decided in exactly one place: the
# validator's NON_APPLYING front-matter contract. A local 'alwaysApply:\s*true' search here reported OK for
# a quoted "true", yes, a missing flag, missing front matter and a globs auto-attach.
$cursorRule = '.cursor/rules/prdv3-constitution.mdc'
if (-not (Test-Path -LiteralPath $cursorRule)) {
  Write-Output "$cursorRule : ABSENT"
} elseif ($null -eq $python) {
  Write-Output "$cursorRule : NOT_CHECKED (no python interpreter)"
  $deterministicFailures.Add("$cursorRule is present but its NON_APPLYING contract could not be checked (no python interpreter)")
} else {
  $global:LASTEXITCODE = $null
  $contract = "import pathlib; rel = sys.argv[1]; found = agent_os.non_applying_failures(rel, pathlib.Path(rel).read_text(encoding='utf-8-sig')); print(chr(10).join(found)); sys.exit(1 if found else 0)"
  $reasons = & $python -B -c ($agentOs + $contract) $cursorRule 2>$null
  if (($LASTEXITCODE -is [int]) -and $LASTEXITCODE -eq 0) {
    Write-Output "$cursorRule : NON_APPLYING (the validator's front-matter contract holds)"
  } else {
    Write-Output "$cursorRule : NOT_PROVEN_NON_APPLYING"
    foreach ($reason in @($reasons)) { if ($reason) { Write-Output "  $reason" } }
    $deterministicFailures.Add("$cursorRule is not proven NON_APPLYING by the validator's front-matter contract")
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
if ($Offline) {
  Write-Output 'OPEN_PR_COUNT=UNKNOWN (offline run; the network probe was skipped)'
} elseif ($gh) {
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
