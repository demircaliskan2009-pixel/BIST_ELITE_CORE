# Token Efficiency V2 - GPT-5.6 named lanes and compact prompts

Active routing is `agent_workflow.md` section 23. Lanes compress procedure, not safety. Every serious prompt
includes `MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`, `REASONING_ACTUAL`,
`EXACT_MODEL_REQUIRED`, declared fallback, exact scope, forbidden actions, validation, stops, and report.
An exact-model mismatch is `STOP_WITH_PROOF`; otherwise actual runtime is reported without overclaim.

## 1. Shared lanes

`LANE:ENV-STD` - set noninteractive pager/color variables.

`LANE:PRECHECK-STD(expect_main_at=<sha>)` - prove repo, clean main, expected HEAD, and open PR count. Stop
on dirty state, head mismatch, open-PR conflict, or unavailable GitHub proof.

`LANE:VALIDATE-STD(files=<paths>)` - one command at a time: scoped Ruff/format where code exists, targeted
validation, logged full suite when required, `git diff --check`, exact changed-file proof.

`LANE:PR-STD(branch=<feature|chore path>, title=<title>)` - exact scope gate, scoped add, commit/push, one
PR, bounded CI/thread snapshots, no merge.

`LANE:REPORT-STD` - result, actual model, state proof, files, validation, PR/check/thread state, blockers,
and next safe action; failure tails only.

## 2. Active model lanes

`LANE:LUNA_STATE` - T0 only: git/gh state, CI polling, review-thread status, and postverify command runner.
No broad design or feature implementation.

`LANE:LUNA_METADATA` - explicitly authorized PR title/body/label metadata update only. Re-prove head and
metadata target; no code, review, thread resolution, or merge.

`LANE:TERRA_IMPLEMENT` - T2 exact-file bounded implementation or docs setup. Preserve deterministic,
fail-closed, paper-only invariants; no merge.

`LANE:TERRA_AUDIT` - fresh-context, pinned-head independent P1/P2 audit. Never audit the implementation from
the same context that produced it.

`LANE:TERRA_REPAIR` - T3 current valid P1/P2 repair on the same branch with regression proof. Stop if scope
widens or the loop becomes broad; route broad/long work to Opus.

`LANE:SOL_CROSS_CONTRACT` - scarce T4 trust/governance/SM-5-SM-6/readiness provenance design or audit.
Use `xhigh` by default; `max` requires controller gate. No polling, merge mechanics, or routine docs.

`LANE:OPUS_HEAVY_LOCAL` - large bounded implementation/refactor, broad local reading, or long validation
loops. It does not replace fresh-context Codex audit.

`LANE:DEEP_RESEARCH_EXTERNAL` - cited external/current facts only; advisory and read-only.

`LANE:CONNECTOR_FINAL_GATE` - read-only source-of-truth verification of head, files, checks, reviews, and
threads before merge authorization.

`LANE:PURSUE_PREFLIGHT` - bounded single-goal terminal preflight/sync/CI/status/closeout/authorized
postverify. Never broad repo pursuit, unscoped design, or unscoped implementation.

`LANE:MODEL_FALLBACK` - exact model mismatch stops. Otherwise declare actual model/reasoning and use only the
approved fallback: Sol -> Opus draft plus independent Codex audit; Terra -> Opus bounded work; Luna ->
terminal/gh mechanical path; Opus -> split broad work or Terra only when truly bounded.

## 3. Copy templates

All templates below require this model header before task-specific fields:
`MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`, `REASONING_ACTUAL`,
`EXACT_MODEL_REQUIRED`, and `MODEL_FALLBACK`. Print actual runtime first. Exact mismatch stops; otherwise
apply only the declared fallback and never claim unavailable-model quality.

### PROMPT:SOL_CROSS_CONTRACT
```text
ROLE: independent design/audit. TASK_CLASS: T4 SOL_CROSS_CONTRACT.
MODEL_REQUESTED: GPT-5.6 Sol. REASONING_REQUESTED: xhigh. EXACT_MODEL_REQUIRED: <true|false>.
MODEL_ACTUAL: <print first>. REASONING_ACTUAL: <print first>. MODEL_FALLBACK: <declared path>.
LANE:PRECHECK-STD(expect_main_at=<sha>); LANE:SOL_CROSS_CONTRACT.
READ: <exact evidence pack>. FORBIDDEN: implementation, CI polling, merge, live/readiness claims.
REPORT: decisions, P1/P2, model actual, fallback, required next action.
```

### PROMPT:TERRA_IMPLEMENT
```text
ROLE: implementer. TASK_CLASS: T2 TERRA_BOUNDED_CODE. MODEL_REQUESTED: GPT-5.6 Terra.
REASONING_REQUESTED: high. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: Opus only if declared.
LANE:PRECHECK-STD(expect_main_at=<sha>). ALLOWED_FILES: <exact paths>.
LANE:TERRA_IMPLEMENT; LANE:VALIDATE-STD(files=<paths>);
LANE:PR-STD(branch=feature/<scope>-prN, title="<title>"). No merge.
```

### PROMPT:TERRA_INDEPENDENT_AUDIT
```text
ROLE: independent auditor. TASK_CLASS: T1 or T3. MODEL_REQUESTED: GPT-5.6 Terra.
REASONING_REQUESTED: high. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: <declared path>.
Fresh context; pinned PR head <sha>; changed files plus direct dependencies only. LANE:TERRA_AUDIT.
No edits/comments/merge. Report P1/P2/P3, thread relevance, readiness, and actual model.
```

### PROMPT:TERRA_EMERGENCY_REPAIR
```text
ROLE: same-branch repair. TASK_CLASS: T3. MODEL_REQUESTED: GPT-5.6 Terra.
REASONING_REQUESTED: xhigh. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: Opus if broad/long-loop.
PR #<N>, head <sha>, finding <id>, allowed files <paths>. LANE:TERRA_REPAIR; add regression proof;
validate; push. Stop on scope expansion. No merge or thread resolution without explicit guarded authority.
```

### PROMPT:LUNA_CI_STATUS
```text
ROLE: mechanical executor. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna.
REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: terminal/gh or declared mechanical lane.
LANE:LUNA_STATE. Exact PR/head required. No code/design/review/merge. Return terminal or pending proof.
```

### PROMPT:LUNA_METADATA_UPDATE
```text
ROLE: authorized metadata executor. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna.
REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: terminal/gh or declared mechanical lane.
LANE:LUNA_METADATA. Exact PR, head, and body/title/label field required. No code, review, thread resolution,
or merge. Re-read metadata after update and report proof.
```

### PROMPT:LUNA_MERGE_POSTVERIFY
```text
ROLE: authorized mechanical executor. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna.
REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: terminal/gh or declared mechanical lane.
USER AUTHORIZATION names PR and exact merge command. Re-prove head/files/checks/threads; standard head-pinned
merge only; LANE:LUNA_STATE postverify main. No edits, no next feature, no thread resolution.
```

### PROMPT:OPUS_HEAVY_LOCAL
```text
ROLE: heavy local implementer. TASK_CLASS: T3. MODEL_REQUESTED: Claude Opus 4.8.
REASONING_REQUESTED: xhigh. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: split scope or declared Terra path if truly bounded.
Clean main@<sha>; branch feature/<scope>-prN; named broad-but-bounded files; long validation allowed.
No merge. Require separate fresh-context Terra or Sol audit before connector gate.
```

### PROMPT:DEEP_RESEARCH
```text
ROLE: external fact researcher. TASK_CLASS: XR. MODEL_REQUESTED: Deep Research.
REASONING_REQUESTED: <runtime policy>. EXACT_MODEL_REQUIRED: false. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: STOP_WITH_PROOF if cited research cannot run.
Exact current question: <question>. Cite sources; separate REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE /
UNKNOWN. Read-only advisory only.
```

### PROMPT:CONNECTOR_FINAL_GATE
```text
ROLE: final evidence gate. TASK_CLASS: CONTROLLER_CONNECTOR_GATE. MODEL_REQUESTED: GitHub connector/gh.
REASONING_REQUESTED: not-applicable. EXACT_MODEL_REQUIRED: false. MODEL_ACTUAL: <connector or gh>.
REASONING_ACTUAL: not-applicable. MODEL_FALLBACK: gh-native mechanism only; never a gate waiver.
Verify PR open/non-draft, head, exact files, terminal checks, reviews, threads, code scanning, and one-open-PR
rule. Output READY_FOR_MERGE_AUTHORIZATION or NOT_READY with proof. No mutation.
```

### PROMPT:PURSUE_PREFLIGHT
```text
ROLE: bounded terminal loop. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna.
REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: declared mechanical path.
LANE:PURSUE_PREFLIGHT; exact goal <preflight|sync|CI|closeout|postverify>. No broad design or patching.
```

### PROMPT:MODEL_FALLBACK
```text
ROLE: routing control. TASK_CLASS: <T0|T1|T2|T3|T4|XR>. MODEL_REQUESTED: <model>.
REASONING_REQUESTED: <level>. EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
REASONING_ACTUAL: <print first>. MODEL_FALLBACK: <Luna->terminal/gh; Terra->Opus; Sol->Opus plus independent
Codex audit; Opus->split scope or Terra only when bounded>. Stop on required exact mismatch.
```
## 4. Invariants

One open PR; no direct main push; standard merge only; explicit human merge authorization; pending CI is
NOT_READY; current P1/P2 block; connector final gate never waived; postmerge verification before next work;
crypto_core-only; no BIST/live/private API/orders/scheduler/readiness/shadow/capital work. Historical Fable
prompts are archived in `fable_exit_contract_index.md`, never active lanes.