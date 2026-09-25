# Token Efficiency V2 - Agent OS named lanes and compact prompts

Active doctrine is `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`). Lanes compress procedure, not
safety, and this companion holds no routing, sizing, budget or merge authority: the council is section 24.3,
audit routing and `ASTRA_PROTECTED_TRIGGER_MATRIX_V1` are section 24.4, the lifecycle and budget are section 24.8,
and runtime proof and effort are section 24.12. A lane named here that disagrees with section 24 is not active.
Every serious prompt follows the section 24.6 `SERIOUS_PROMPT_COMPILER` order, carries the section 24.12
runtime-proof block and the `SETUP_*` block, inherits `CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2), and
ends in an `AGENT_OS_HANDOFF_V1` report. Claude prompt templates live in
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`. The Claude mutation lane requires the exact model id
(`claude-opus-5-5`) — an unresolved alias is not proof. Claude Opus 5 is `SUPERSEDED_BY_OPUS_5_5`, Claude Opus
4.8 is `SUPERSEDED_BY_OPUS_5`, Claude Sonnet 5, Codex Terra and Codex Luna are `NOT_IN_ACTIVE_COUNCIL`, and Claude
Fable 5 is `INACTIVE_EXPIRED_RETIRED` — none is an active lane, fallback, or dependency; pre-v5.2 Fable prompts
are archived in `fable_exit_contract_index.md` and are never active.

## 1. Shared lanes

`LANE:ENV-STD` - set noninteractive pager/color variables.

`LANE:PRECHECK-STD(expect_main_at=<sha>)` - prove repo, clean main, expected HEAD, and open PR count. Stop
on dirty state, head mismatch, open-PR conflict, or unavailable GitHub proof.

`LANE:VALIDATE-STD(files=<paths>)` - one command at a time: scoped Ruff/format where code exists, targeted
validation, logged full suite when required, `git diff --check`, exact changed-file proof.

`LANE:PR-STD(branch=<feature|chore path>, title=<title>)` - exact scope gate, scoped add, commit/push, one
PR, bounded CI/thread snapshots, no merge.

`LANE:HANDOFF-STD` - end with an `AGENT_OS_HANDOFF_V1` packet: result, runtime proof, setup fields, state
proof, files, validation, PR/check/thread state, protected classification, blockers, the specialist and
challenge counts, exactly one next safe action; failure tails only.

## 2. Controller lanes (ChatGPT controller + GitHub connector; read-only first)

`LANE:CONTROLLER_STATE_PROOF` - pin main/PR/head/tree/files/checks/threads/open-PR count from live connector
evidence; never memory; output pinned state for downstream packets.

`LANE:CONTROLLER_DESIGN_SYNTHESIS` - map surfaces/symbols/contracts from pinned evidence; define invariants,
fail-closed matrix, raise-vs-REJECTED boundaries, allowed files, negative-path tests, validation ladder,
stops; emit one bounded PR contract; decide whether Deep Research is required. No implementation.

`LANE:CONTROLLER_TO_IMPLEMENTER` - issue the serious implementation prompt to Claude Opus 5.5: pinned state,
exact read set, symbol map, exact allowed files, invariants, forbidden surfaces, protected classification,
exact tests, validation ladder, branch/commit/PR contract, stop conditions.

`LANE:CONTROLLER_REPORT_VERIFY` - check every executor claim against live PR metadata, pinned head/base,
exact files, commits, runs/jobs, tests, CodeQL, reviews, threads, open-PR count, merge state, pinned file
contents. No report is self-authenticating; unverified claims stay UNKNOWN/UNPROVEN. Output
HANDOFF_ACCEPTED / HANDOFF_REPAIR_REQUIRED / HANDOFF_REJECTED / HANDOFF_UNKNOWN.

`LANE:CONTROLLER_PROTECTED_CLASSIFICATION` - classify the candidate against `ASTRA_PROTECTED_TRIGGER_MATRIX_V1`
(A-G) and record the trigger letters or `NONE`; classify upward when ambiguity remains, never downward to save
quota.

`LANE:CONTROLLER_NONPROTECTED_AUDIT` - `CONTROLLER_INDEPENDENT_AUDIT_NONPROTECTED` for a candidate classified
`NONE` that the controller (including through ChatGPT Work) neither implemented nor repaired: fresh exact-head
proof, every changed file, load-bearing dependencies, CI and threads, supported-path adversarial reasoning,
P1/P2/P3 materiality, scope and non-claims, determinism and fail-closed review, the complete material blocker
set. Test/CI evidence informs it and never replaces it. Zero Codex quota; never GPT-6 Astra; Sol only as a
recorded reserve when the controller is ineligible.

`LANE:CONTROLLER_PROTECTED_PREFLIGHT_AND_PACKET` - for a protected candidate: `CONTROLLER_PREFLIGHT_REVIEW` to the
coverage of the non-protected audit; route an Opus 5.5 challenge when it lowers the risk of wasting Astra; route
the one consolidated repair first when a material P1/P2 is confirmed; then compile `PROTECTED_AUDIT_PACKET_V1`
(exact base/head/tree, changed files, triggers, critical claims needing Astra authority, load-bearing protected
dependencies, preflight result, challenge result, CI, threads, unresolved P1/P2, exact protected acceptance
questions) on a stabilized head. Repository references, never chat-history recovery; missing evidence
`UNKNOWN`. Delivers no acceptance verdict.

`LANE:CONTROLLER_FINAL_GATE` - read-only merge-readiness verification: PR open/non-draft, base main, pinned
head unchanged, exact files, required checks terminal success (accepted skips only), CodeQL clean, no
current valid unresolved P1/P2, exactly one open PR, no forbidden scope, the correct acceptance audit completed
(controller for non-protected, GPT-6 Astra for protected). Output READY_FOR_MERGE_AUTHORIZATION | NOT_READY |
UNKNOWN. Never merges.

`LANE:CONTROLLER_AUTHORIZED_ACTION` - execute ONLY an explicitly human-named GitHub action (standard merge,
metadata, label, reviewer, draft/ready, comment, guarded thread closeout, bounded workflow rerun): re-prove
state immediately before, perform only the named action, re-read the result, report proof. Never direct main
push, force push, squash/rebase, self-approval, blind retry, or opportunistic adjacent mutation.

## 3. Specialist lanes

`LANE:OPUS55_IMPLEMENTATION` - Claude Opus 5.5 (`claude-opus-5-5`), `xhigh` by default: the whole implementation
arc on the named semantic boundary, including its repo-native navigation, tests, local validation and CI
diagnosis; local state proven independently; no merge. Template: playbook 3.1.

`LANE:OPUS55_CONSOLIDATED_REPAIR` - the ONE consolidated repair of the complete confirmed P1/P2 set by root
cause, same branch; never a second repair, never on a frozen candidate. Template: playbook 3.2.

`LANE:OPUS55_READONLY_CHALLENGE` - `OPUS55_FRESH_READONLY_CHALLENGE`: fresh context, READ_ONLY, focused semantic
bug finding / adversarial cases / numeric review / dependency tracing / test gaps / protected-boundary preflight;
`CHALLENGE_EVIDENCE_ONLY`, never acceptance; at most two per lifecycle. Template: playbook 3.3.

`LANE:ASTRA_PROTECTED_AUDIT` - GPT-6 Astra (`gpt-6-astra`, `Ultra`, fallback prohibited, thinking enabled) on a
`PROTECTED_AUDIT_PACKET_V1` only: the complete protected cross-contract boundary, every fact protected acceptance
rests on verified independently, the complete material P1/P2 set, the protected Class-C and terminal verdict. No
discovery already proven, polling, mechanics or mutation. Quota-blocked → the protected head freezes and waits.

`LANE:SOL_RESERVE` - Codex GPT-5.6 Sol only with a recorded `SOL_RESERVE_ONLY` gap (for example the non-protected
acceptance audit when the controller is ineligible); never protected acceptance, never model diversity.

`LANE:IMPLEMENTER_HANDOFF` - close any implementation turn: actual files/head/commits, local tests,
logged-full-suite result, CI snapshot, unresolved issues, no self-audit claim, one next safe action, in
`AGENT_OS_HANDOFF_V1` form.

`LANE:POST_MERGE_HANDOFF` - after an authorized merge: PR, merge commit, local/origin main equality, Ruff,
format, full suite, setup audit, diff check, open PRs, clean tree, residual blockers, one next action.

## 4. Research lanes (controller-orchestrated; read-only)

`LANE:DEEP_RESEARCH_FACT_CHECK` - XR_FACT_CHECK: one narrow current external question; official/primary
sources first; retrieval date + source version; unresolved facts stay UNKNOWN; no implementation.

`LANE:DEEP_RESEARCH_ARCHITECTURE_BENCHMARK` - XR_ARCHITECTURE_BENCHMARK: compare against Hummingbot /
Freqtrade / NautilusTrader / QuantConnect LEAN / credible institutional systems on capabilities and
evidence (never stars/marketing); architectural intent vs implemented proof; bounded repo-relevant
recommendations; no blind copy; license/IP respected.

`LANE:DEEP_RESEARCH_PHASE_GATE` - XR_PHASE_GATE_REVIEW: mandatory before material phase transitions with
external/current assumptions (paper-DONE claims, machine-time, first connector/readiness, Deribit,
shadow/live, custody/security/regulatory, resilience); also after major phase bundles, before roadmap
changes on external assumptions, on stale prior evidence.

`LANE:DEEP_RESEARCH_OVERENGINEERING` - XR_OVERENGINEERING_AUDIT: artifact proliferation vs end-to-end
wiring; duplicates/unused modules/excess governance layers; freeze/consolidate/integrate recommendations;
underbuilding check; tests-verify-composition check. Advisory until controller triage.

All research lanes: connector-bound packet in (pinned repo state, exact files, benchmark set, source-quality
requirements), `DEEP_RESEARCH_TO_CONTROLLER` packet out (research date, pinned state, source quality,
REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN, stale findings, bounded recommendations, exact next
PR proposal, refresh trigger). Never mutation, never merge authority, never a gate waiver.

## 5. Copy header (all serious templates)

```text
TASK_INTENT: <IMPLEMENTATION|REPAIR|CHALLENGE|AUDIT|REAUDIT|ARCHITECTURE|CLOSEOUT>. SEMANTIC_BOUNDARY: <one contract>.
STATE_PIN: <pinned main/PR/head/tree>. PROTECTED: <trigger letters | NONE>.
MODEL_RUNTIME_PROOF: MODEL_REQUESTED / MODEL_ID_REQUIRED / MODEL_ACTUAL / MODEL_EFFORT_REQUESTED /
  MODEL_EFFORT_ACTUAL / MODEL_FALLBACK / THINKING_ACTUAL / MODEL_IDENTITY_EVIDENCE / MODEL_EFFORT_EVIDENCE.
SETUP_REQUESTED: <per SETUP_LOAD_CONTRACT_V1>. SETUP_ACTUAL/SETUP_FILES_READ/SETUP_GAPS: <print>.
PROFILE: CRYPTO_CORE_DOMAIN_OPERATING_PROFILE. ALLOWED_FILES: <exact>. INVARIANTS / BLOCKER_INVENTORY: <exact>.
VALIDATION_MATRIX: <exact ladder>. GITHUB_AUTHORIZATION: <authorized vs not>. FORBIDDEN: <task + standing rails>.
STOP_CONDITIONS: <enumerated>. HANDOFF: AGENT_OS_HANDOFF_V1.
```

## 6. Invariants

One open PR; one repository writer at a time; no direct main push; standard merge only; explicit human merge
authorization; pending CI is NOT_READY; current valid P1/P2 block; GPT-6 Astra is the sole protected acceptance
and is never replaced; an Opus challenge never accepts; postmerge verification before next work; research never
mutates; crypto_core-only; no BIST/live/private API/orders/scheduler/readiness/shadow/capital work. No autonomous
scheduler, no auto-loop, no direct model-to-model runtime messaging. The ChatGPT controller is the read-only-first
default acceptance auditor for non-protected work and never replaces local tests or the protected GPT-6 Astra
audit. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a lane, fallback, or dependency; pre-v5.2 Fable
prompts are archived in `fable_exit_contract_index.md`, never active lanes.
