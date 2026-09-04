# Token Efficiency V2 - Agent OS named lanes and compact prompts

**This document is a prompt-compression guide, not a routing authority.** The only canonical
`ROLE_ROUTING_MATRIX` is `docs/crypto_core/agent_os_v2.md` section 3.

Active doctrine is `docs/crypto_core/agent_os_v2.md` (`CRYPTO_CORE_AGENT_OS_V2`), with `agent_workflow.md`
section 24 as the inherited class/effort companion. Compiled prompts follow `PROMPT_COMPILER_V2`
(`agent_os_v2.md` section 8) and `PROMPT_LANGUAGE_PROHIBITED`: no restart-until-success, no blanket GitHub
or merge authority, no hidden loops, no unbounded discovery during repair, no hidden chain-of-thought
requests. Lanes compress procedure, not safety. Every serious prompt includes `MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`,
`REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`, declared fallback, the `SETUP_*` block, exact scope, forbidden
actions, validation, stops, and the `AGENT_OS_HANDOFF_V1` report. An exact-model mismatch is
`STOP_WITH_PROOF`; otherwise actual runtime is reported without overclaim. Every serious prompt inherits
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2). The active lane set is exactly nine (ChatGPT GPT-5.6
Thinking read-only-first controller, ChatGPT Work Local/Cloud read-only research and synthesis, GitHub
connector, Deep Research, Claude Opus 5, Claude Sonnet 5, Codex Sol/Terra/Luna). Lane and effort selection
is not restated here: the single canonical `ROLE_ROUTING_MATRIX` is `docs/crypto_core/agent_os_v2.md`
section 3, the inherited class/effort detail is `agent_workflow.md` sections 24.3 and 24.12, and Claude
prompt templates plus the prompt-compiler contract live in
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`. Claude
mutation lanes require the exact model id (`claude-opus-5` / `claude-sonnet-5`) plus session-level proof of
the actual effort — an unresolved alias is not proof. Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5` and Claude
Fable 5 is `INACTIVE_EXPIRED_RETIRED` (section 24.10) — neither is an active lane, fallback, or dependency;
pre-v5.2 Fable prompts are archived in `fable_exit_contract_index.md` and are never active.

<!-- PROMPT_COMPILER_V2_FIELDS:BEGIN -->

`PROMPT_COMPILER_V2_TASK_DELTA` — every serious prompt built from this document instantiates exactly this
canonical delta packet. A template may be terse, but all twelve fields must be representable and none may
be omitted or replaced by prose such as "follow PROMPT_COMPILER_V2".

- `TASK_INTENT`
- `SEMANTIC_BOUNDARY`
- `STATE_PIN`
- `MODEL_RUNTIME_PROOF`
- `ALLOWED_FILES`
- `INVARIANTS`
- `BLOCKER_INVENTORY`
- `VALIDATION_MATRIX`
- `GITHUB_AUTHORIZATION`
- `FORBIDDEN`
- `STOP_CONDITIONS`
- `HANDOFF`

<!-- PROMPT_COMPILER_V2_FIELDS:END -->

## 1. Shared lanes

`LANE:ENV-STD` - set noninteractive pager/color variables.

`LANE:PRECHECK-STD(expect_main_at=<sha>)` - prove repo, clean main, expected HEAD, and open PR count. Stop
on dirty state, head mismatch, open-PR conflict, or unavailable GitHub proof.

`LANE:VALIDATE-STD(files=<paths>)` - one command at a time: scoped Ruff/format where code exists, targeted
validation, logged full suite when required, `git diff --check`, exact changed-file proof.

`LANE:PR-STD(branch=<feature|chore path>, title=<title>)` - exact scope gate, scoped add, commit/push, one
PR, bounded CI/thread snapshots, no merge.

`LANE:HANDOFF-STD` - end with an `AGENT_OS_HANDOFF_V1` packet: result, actual model, setup fields, state
proof, files, validation, PR/check/thread state, audit class, blockers, exactly one next safe action;
failure tails only.

## 2. Controller lanes (ChatGPT GPT-5.6 Thinking + GitHub connector)

`LANE:CONTROLLER_STATE_PROOF` - pin main/PR/head/files/checks/threads/open-PR count from live connector
evidence; never memory; output pinned state for downstream packets.

`LANE:CONTROLLER_DESIGN_SYNTHESIS` - map surfaces/symbols/contracts from pinned evidence; define invariants,
fail-closed matrix, raise-vs-REJECTED boundaries, allowed files, negative-path tests, validation ladder,
stops; emit one bounded PR contract; decide whether Deep Research is required. No implementation.

`LANE:CONTROLLER_TO_IMPLEMENTER` - issue the implementation packet: pinned state, exact read set, symbol
map, exact allowed files, invariants, forbidden surfaces, protected-risk class, exact tests, validation
ladder, branch/commit/PR contract, stop conditions.

`LANE:CONTROLLER_PRE_CODEX_TRIAGE` - verify PR/base/head/files/patches/dependencies/CI/threads; run the
protected-trigger matrix; strip questions already proven; emit the narrow Codex packet (pinned head, exact
changes, direct dependencies, unresolved semantic questions, adversarial cases, report contract).

`LANE:CONTROLLER_REPORT_VERIFY` - check every executor claim against live PR metadata, pinned head/base,
exact files, commits, runs/jobs, tests, CodeQL, reviews, threads, open-PR count, merge state, pinned file
contents. No report is self-authenticating; unverified claims stay UNKNOWN/UNPROVEN. Output
HANDOFF_ACCEPTED / HANDOFF_REPAIR_REQUIRED / HANDOFF_REJECTED / HANDOFF_UNKNOWN.

`LANE:CONTROLLER_LOW_RISK_AUDIT` - Class-A independent audit (docs/setup/prompt/skill/workflow/low-risk CI
config/helper scripts): fresh pinned-head reread, complete patch, exact files, terminal CI, thread state,
P1/P2/P3 classification, explicit statement why Class A applies. Final gate and merge stay separate.

`LANE:CONTROLLER_REPO_READONLY_AUDIT` - connector-backed read-only repository/setup/workflow/architecture
consistency audit (`CONTROLLER_READONLY_FIRST_POLICY`): tracked-file + dependency surface map,
model-routing/lane consistency, stale-state/drift detection, evidence vs inference, severity P1/P2/P3. No
edits/commits/PRs/merge/product implementation; never treats memory as repo state; never replaces Class-C
Sol; output read-only audit handoff + one next safe action.

`LANE:CONTROLLER_CLASS_B_AUDIT` - controller-first read-only audit of ordinary bounded product code:
source/test + dependency map, negative-test check, fail-closed first pass, CI/CodeQL, full protected-trigger
checklist; controller-only closeout only when every no-Codex criterion is proven, else Terra ordinary audit /
escalate to Class C on any uncertainty. `CODEX_REQUIRED: NO` carries the exact reason + trigger checklist.

`LANE:CONTROLLER_FINAL_GATE` - read-only merge-readiness verification: PR open/non-draft, base main, pinned
head unchanged, exact files, required checks terminal success (accepted skips only), CodeQL clean, no
current valid unresolved P1/P2, exactly one open PR, no forbidden scope, correct audit class completed.
Output READY_FOR_MERGE_AUTHORIZATION | NOT_READY | UNKNOWN. Never merges.

`LANE:CONTROLLER_AUTHORIZED_ACTION` - execute ONLY an explicitly human-named GitHub action (standard merge,
metadata, label, reviewer, draft/ready, comment, guarded thread closeout, bounded workflow rerun): re-prove
state immediately before, perform only the named action, re-read the result, report proof. Never direct main
push, force push, squash/rebase, self-approval, blind retry, or opportunistic adjacent mutation.

## 3. Executor lanes

`LANE:LUNA_MECHANICS` - T0 only: git/gh state, bounded CI polling, PR metadata (only when explicitly
authorized), thread status, authorized standard merge + postverify command running. Reasoning none/low; no
design, code, audit judgment, or thread resolution.

`LANE:SONNET_BOUNDED_IMPLEMENTATION` - runtime-proven Claude Sonnet 5 only (print MODEL_ACTUAL first; stop
if unproven): T1/T2 bounded reads, small/medium deterministic implementation, docs/tests, mechanical code,
simple same-branch repair. Never protected/digest/SM/Stage-4/readiness/capital work, never T4, never
Class-C audit. Fallback Terra (bounded) / Opus (broad).

`LANE:TERRA_BOUNDED_IMPLEMENTATION` - T2 exact-file bounded implementation or docs/tests from the controller
packet; deterministic, fail-closed, paper-only invariants preserved; no merge.

`LANE:TERRA_INDEPENDENT_AUDIT` - fresh-context, pinned-head ordinary independent audit (Class B when
required); never the implementation context; changed files + direct dependencies only; no
edits/comments/merge; AUDITOR handoff with P1/P2/P3 + exact evidence.

`LANE:OPUS_HEAVY_IMPLEMENTATION` - T3 broad-but-bounded local implementation/refactor/forensic debug/long
validation loops on named files; local state proven independently; separate independent audit still required
for protected work; no merge.

`LANE:SOL_PROTECTED_DESIGN_AUDIT` - scarce T4 protected design/audit on a controller-prepared narrow packet
only (digest/provenance/trust boundaries, SM-5/SM-6, Stage-4, readiness/Deribit, complex security). xhigh
default; max only controller-gated. No discovery, polling, mechanics, or implementation in audit mode.

`LANE:IMPLEMENTER_HANDOFF` - close any implementation turn: actual files/head/commits, local tests,
logged-full-suite result, CI snapshot, unresolved issues, no self-audit claim, one next safe action, in
`AGENT_OS_HANDOFF_V1` form.

`LANE:POST_MERGE_HANDOFF` - after an authorized merge: PR, merge commit, local/origin main equality, Ruff,
format, full suite, setup audit, diff check, open PRs, clean tree, residual blockers, one next action.

Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` (section 24.10): the retired `LANE:FABLE5_*` surge / challenge /
full-repo-audit lanes and the retired Fable justification gate are never issued. Route former Fable work
instead: broad-but-bounded T3 →
`LANE:OPUS_HEAVY_IMPLEMENTATION` (bounded T2 → `LANE:SONNET_BOUNDED_IMPLEMENTATION` /
`LANE:TERRA_BOUNDED_IMPLEMENTATION`); non-Class-C read-only architecture/contradiction/full-repo consistency
analysis → the controller read-only-first lanes in §2 (`LANE:CONTROLLER_REPO_READONLY_AUDIT`,
`LANE:CONTROLLER_LOW_RISK_AUDIT`, `LANE:CONTROLLER_CLASS_B_AUDIT`); protected Class-C →
`LANE:SOL_PROTECTED_DESIGN_AUDIT`.

`GATE:MODEL_EXPECTED_VALUE_PER_TOKEN` - serious prompts state: TOKEN_CLASS, TOKEN_BUDGET_ASSESSMENT,
EXPECTED_VALUE_PER_TOKEN, EXPECTED_PROMPTS, MAX_REPAIR_CYCLES, CONTEXT_REUSE_PACKET, WHY_THIS_MODEL,
CHEAPER_SAFE_ALTERNATIVE, STOP_IF_BUDGET_INSUFFICIENT. Measured harness cost, never hard-coded price
rankings; correctness never sacrificed for tokens.

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
ROLE: <one role>. TASK_CLASS: <T0|T1|T2|T3|T4|XR|CONTROLLER_CONNECTOR_GATE>.
MODEL_REQUESTED: <lane model>. REASONING_REQUESTED: <level>. EXACT_MODEL_REQUIRED: <true|false>.
MODEL_ACTUAL: <print first>. REASONING_ACTUAL: <print first>. MODEL_FALLBACK: <declared path or STOP>.
SETUP_REQUESTED: <per SETUP_LOAD_CONTRACT_V1>. SETUP_ACTUAL/SETUP_FILES_READ/SETUP_GAPS: <print>.
PROFILE: CRYPTO_CORE_DOMAIN_OPERATING_PROFILE. STATE: <pinned main/PR/head>. SCOPE: <exact files>.
FORBIDDEN: <task-specific + standing rails>. VALIDATION: <exact ladder>. STOP_WITH_PROOF: <conditions>.
REPORT: AGENT_OS_HANDOFF_V1.
```

## 6. Invariants

One open PR; one repository writer at a time; no direct main push; standard merge only; explicit human merge
authorization; pending CI is NOT_READY; current valid P1/P2 block; Class-C Codex audit never replaceable;
connector final gate never waived; postmerge verification before next work; research never mutates;
crypto_core-only; no BIST/live/private API/orders/scheduler/readiness/shadow/capital work. No autonomous
scheduler, no auto-loop, no direct model-to-model runtime messaging. ChatGPT is the read-only-first
controller-auditor for non-Class-C work and never replaces local tests or the Class-C Sol audit. Claude
Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a lane, fallback, or dependency; pre-v5.2 Fable prompts are
archived in `fable_exit_contract_index.md`, never active lanes.
