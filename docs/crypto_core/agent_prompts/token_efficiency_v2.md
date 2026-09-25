# Token Efficiency V2 - Agent OS named lanes and compact prompts

Active doctrine is `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`). Lanes compress procedure, not
safety. Every serious prompt includes `MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`,
`REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`, declared fallback, the `SETUP_*` block, exact scope, forbidden
actions, validation, stops, and the `AGENT_OS_HANDOFF_V1` report. An exact-model mismatch is
`STOP_WITH_PROOF`; otherwise actual runtime is reported without overclaim. Every serious prompt inherits
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2). The active council is not restated here: the single
`AUTHORITATIVE_ROUTING_MATRIX` is section 24.3,
the effort/thinking architecture is section 24.12, and Claude prompt templates plus the
prompt-compiler contract live in `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`. The Claude
mutation lane requires the exact model id (`claude-opus-5-5`) plus session-level proof of
the actual effort — an unresolved alias is not proof. Claude Opus 5 is `SUPERSEDED_BY_OPUS_5_5`, Claude Opus
4.8 is `SUPERSEDED_BY_OPUS_5` and Claude
Fable 5 is `INACTIVE_EXPIRED_RETIRED` (section 24.10) — none is an active lane, fallback, or dependency;
pre-v5.2 Fable prompts are archived in `fable_exit_contract_index.md` and are never active.

## 1. Shared lanes

`LANE:ENV-STD` - set noninteractive pager/color variables.

`LANE:PRECHECK-STD(expect_main_at=<sha>)` - prove repo, clean main, expected HEAD, and open PR count. Stop
on dirty state, head mismatch, open-PR conflict, or unavailable GitHub proof.

`LANE:VALIDATE-STD(files=<paths>)` - one command at a time: scoped Ruff/format where code exists, targeted
validation, logged full suite when required, `git diff --check`, exact changed-file proof.

`LANE:PR-STD(branch=<feature|chore path>, title=<title>)` - exact scope gate, scoped add, commit/push, one
PR, bounded CI/thread snapshots, no merge.

`LANE:HANDOFF-STD` - end with an `AGENT_OS_HANDOFF_V1` packet: result, actual model, setup fields, state
proof, files, validation, PR/check/thread state, protected classification, blockers, the actual
meaningful-execution and challenge counts (section 24.8), exactly one next safe action; failure tails only.

## 2. Controller lanes (ChatGPT GPT-5.6 Thinking + GitHub connector)

`LANE:CONTROLLER_STATE_PROOF` - pin main/PR/head/files/checks/threads/open-PR count from live connector
evidence; never memory; output pinned state for downstream packets.

`LANE:CONTROLLER_DESIGN_SYNTHESIS` - map surfaces/symbols/contracts from pinned evidence; define invariants,
fail-closed matrix, raise-vs-REJECTED boundaries, allowed files, negative-path tests, validation ladder,
stops; emit one bounded PR contract; decide whether Deep Research is required. No implementation.

`LANE:CONTROLLER_TO_IMPLEMENTER` - issue the implementation packet: pinned state, exact read set, symbol
map, exact allowed files, invariants, forbidden surfaces, protected-risk class, exact tests, validation
ladder, branch/commit/PR contract, stop conditions.

`LANE:CONTROLLER_PROTECTED_PREFLIGHT` - `CONTROLLER_PROTECTED_PREFLIGHT` and `PROTECTED_AUDIT_PACKET_V2`
(section 24.4): classify against `PROTECTED_TRIGGER_MATRIX_V2`, do every safely controller-owned check at zero
count, and either open the one repair on a confirmed complete P1/P2 set or emit the packet for one GPT-6 Astra
audit on a stabilized head. Delivers no acceptance verdict.

`LANE:CONTROLLER_REPORT_VERIFY` - check every executor claim against live PR metadata, pinned head/base,
exact files, commits, runs/jobs, tests, CodeQL, reviews, threads, open-PR count, merge state, pinned file
contents. No report is self-authenticating; unverified claims stay UNKNOWN/UNPROVEN. Output
HANDOFF_ACCEPTED / HANDOFF_REPAIR_REQUIRED / HANDOFF_REJECTED / HANDOFF_UNKNOWN.

`LANE:CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT` - `CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT` (section 24.4) for a
candidate classified `NONE` that the controller (including through ChatGPT Work) neither implemented nor
repaired: the acceptance-audit standard and coverage of section 24.4, the complete material blocker set, zero
Astra executions; a meaningful prompt of the hard-five budget.

`LANE:CONTROLLER_REPO_READONLY_AUDIT` - connector-backed read-only repository/setup/workflow/architecture
consistency audit (`CONTROLLER_READONLY_FIRST_POLICY`): tracked-file + dependency surface map,
model-routing/lane consistency, stale-state/drift detection, evidence vs inference, severity P1/P2/P3. No
edits/commits/PRs/merge/product implementation; never treats memory as repo state; never replaces protected
acceptance by GPT-6 Astra; output read-only audit handoff + one next safe action.

`LANE:CONTROLLER_FINAL_GATE` - read-only merge-readiness verification: PR open/non-draft, base main, pinned
head unchanged, exact files, required checks terminal success (accepted skips only), CodeQL clean, no
current valid unresolved P1/P2, exactly one open PR, no forbidden scope, the acceptance audit of the lane
section 24.4 fixes completed.
Output READY_FOR_MERGE_AUTHORIZATION | NOT_READY | UNKNOWN. Never merges.

`LANE:CONTROLLER_AUTHORIZED_ACTION` - execute ONLY an explicitly human-named GitHub action (standard merge,
metadata, label, reviewer, draft/ready, comment, guarded thread closeout, bounded workflow rerun): re-prove
state immediately before, perform only the named action, re-read the result, report proof. Never direct main
push, force push, squash/rebase, self-approval, blind retry, or opportunistic adjacent mutation.

## 3. Executor lanes

Lane roles are section 24.3 and 24.4; the lanes below only name them for compact prompts.

`LANE:OPUS55_IMPLEMENTATION` - Claude Opus 5.5 implementation of one semantic boundary with its repo-native
work and exhaustive self-audit; local state proven independently; no merge. Template: playbook 3.1.

`LANE:OPUS55_CONSOLIDATED_REPAIR` - the ONE repair, opened through a `REPAIR_ENTRY_MODE` (section 24.8), carrying
the mode, the complete blocker inventory and the actual counts. Template: playbook 3.2.

`LANE:OPUS55_READONLY_CHALLENGE` - optional, default-off, READ_ONLY evidence-only challenge; a meaningful prompt
of the hard-five budget, admitted only by `BUDGET_ADMISSION_RULE`. Template: playbook 3.3.

`LANE:ASTRA_PROTECTED_AUDIT` - GPT-6 Astra (`gpt-6-astra`, `Ultra`, fallback prohibited, thinking enabled) on a
`PROTECTED_AUDIT_PACKET_V2` only: sole protected acceptance audit or re-audit of a stabilized head; no discovery,
polling, mechanics or mutation; quota-blocked → `ASTRA_QUOTA_BLOCK_FREEZE`.

`LANE:SOL_RESERVE` - Codex GPT-5.6 Sol only on a controller-recorded capability or eligibility gap
(`SOL_RESERVE_ONLY`); never protected acceptance, never model diversity.

`LANE:IMPLEMENTER_HANDOFF` - close any implementation turn: actual files/head/commits, local tests,
logged-full-suite result, CI snapshot, unresolved issues, no self-audit claim, one next safe action, in
`AGENT_OS_HANDOFF_V1` form.

`LANE:POST_MERGE_HANDOFF` - after an authorized merge: PR, merge commit, local/origin main equality, Ruff,
format, full suite, setup audit, diff check, open PRs, clean tree, residual blockers, one next action.

Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` (section 24.10): the retired `LANE:FABLE5_*` surge / challenge /
full-repo-audit lanes and the retired Fable justification gate are never issued; the retired Luna, Sonnet 5 and
Terra lanes and the former Sol protected-audit lane are likewise never issued. Former Fable work routes to
`LANE:OPUS55_IMPLEMENTATION` or to the controller read-only-first lanes in §2; protected acceptance routes only to
`LANE:ASTRA_PROTECTED_AUDIT`.

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
authorization; pending CI is NOT_READY; current valid P1/P2 block; protected acceptance by GPT-6 Astra alone,
never replaceable; connector final gate never waived; postmerge verification before next work; research never
mutates; crypto_core-only; no BIST/live/private API/orders/scheduler/readiness/shadow/capital work. No autonomous
scheduler, no auto-loop, no direct model-to-model runtime messaging. ChatGPT is the read-only-first default
acceptance auditor for non-protected work and never replaces local tests or the protected GPT-6 Astra audit. Claude
Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a lane, fallback, or dependency; pre-v5.2 Fable prompts are
archived in `fable_exit_contract_index.md`, never active lanes.
