# Claude Opus 5 Prompting Playbook (crypto_core)

**This playbook is a prompt-authoring guide, not a routing authority.** The only canonical
`ROLE_ROUTING_MATRIX` is `docs/crypto_core/agent_os_v2.md` section 3.

Durable authority for HOW to prompt the Claude lanes in `CRYPTO_CORE_AGENT_OS_V2`. The routing authority is
the canonical `ROLE_ROUTING_MATRIX` in `docs/crypto_core/agent_os_v2.md` section 3; the inherited
class → model id → effort detail is `docs/crypto_core/agent_workflow.md` section 24.3 and the
effort/thinking architecture is section 24.12 (`CLAUDE_MODEL_EFFORT_ARCHITECTURE_V1`). The canonical
prompt-compiler policy is `PROMPT_COMPILER_V2` (`agent_os_v2.md` section 8); the templates and
`PROMPT_COMPILER_CONTRACT_V1` below are its Claude-lane implementation and must stay compatible with it —
one role, one semantic outcome, one writer or one read-only reviewer, one report contract, one next safe
action, stable doctrine loaded from the repo rather than pasted, and no `PROMPT_LANGUAGE_PROHIBITED`
wording (restart-until-success, blanket GitHub or merge authority, hidden loops, unbounded discovery during
repair, hidden chain-of-thought requests). This playbook never overrides the control plane — it teaches
prompt construction and supplies reusable templates. On any conflict, `agent_os_v2.md`, then section 24,
then the stricter safety rule win.

Active Claude lanes: **Claude Opus 5** (`claude-opus-5`, default heavy local executor) and **Claude
Sonnet 5** (`claude-sonnet-5`, runtime-proven, default for T0/T1/T2). Claude Opus 4.8 is
`SUPERSEDED_BY_OPUS_5` and Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`; both survive only as historical
evidence. Nothing here proves repository state, grants merge authority, or satisfies a Class-C independent
Codex audit.

---

## 1. Effort-selection guide

"Thinking level" in conversation means Claude's `effort` setting. The API effort levels are exactly `low`,
`medium`, `high`, `xhigh`, `max`.

| Effort | Use it for | Do NOT use it for |
|---|---|---|
| `low` | Extremely narrow read-only classification; a cheap high-volume review subtask; concise extraction where an Opus-specific capability is still genuinely required. Normally prefer Sonnet 5 instead. | Any mutation across a trust boundary; anything semantic. |
| `medium` | Focused one- or two-file code review; bounded bug discovery; narrow read-only audit; prompt refinement; constrained architecture comparison; cost-sensitive Opus work that repository evidence shows is sufficient. | Broad multi-module review; architecture with interacting consequences; complex implementation. |
| `high` | Nuanced review; architecture selection; complex prompt design; difficult read-only analysis; moderate multi-step reasoning where long-horizon coding is not required. | Long-horizon multi-file implementation (use `xhigh`); capability-critical boundaries (use `max`). |
| `xhigh` | **The normal Opus 5 coding/agentic starting point.** Difficult implementation; multi-file work; protocol semantics; long-running tool use; complex repair; deep repository exploration; interacting invariants. | Status, polling, closeout, formatting, ordinary docs — those are Sonnet lanes. |
| `max` | Capability-critical work only. **MAX requires an explicit named maximum-effort trigger inside the selected task family** — the T3B implementation/repair triggers below, the T3D architecture triggers, or the T3E prompt-architecture triggers. | Polling; merge closeout; formatting; routine tests; simple documentation; ordinary one-line repair; a task merely because it is important. |

**T3B `max` triggers (the complete list — IMPLEMENTATION or REPAIR mutation only).** Cryptographic
verification boundary implementation; readiness/provenance promotion implementation; protocol ambiguity
with safety consequences inside an implementation; complex trust-boundary repair; **complex semantic**
controller P1/P2 repair; unexpected cross-layer implementation failure; work the controller explicitly
designates capability-critical IMPLEMENTATION or REPAIR. Naming the fired trigger is mandatory — if you
cannot name one, the task is not T3B.

These triggers apply only when `TASK_INTENT ∈ {IMPLEMENTATION, REPAIR}` and the task is a mutation. They are
never a route into T3B on their own:
- **Agent OS or model-routing ARCHITECTURE** (a decision, not a diff) → `T3D` / `max`, per the existing T3D
  policy — never T3B.
- **Agent OS or model-routing PROMPT_ARCHITECTURE** (writing the execution contract) → `T3E` / `max` — never
  T3B.
- **Several candidate architectures with materially different safety outcomes** → `T3D`, effort selected by
  the existing T3D policy (`high` / `xhigh` / `max`) — never T3B.
These concepts become T3B only when the actual authorized task is an implementation/repair mutation that
also fires one of the named triggers above — never merely because the subject matter is architectural.

**Audit origin is an input, not a trigger.** That work follows a P1/P2 finding says nothing about its
complexity. A mechanical or obvious post-audit repair — a one-file documentation correction, a PR-body fix,
a renamed constant, a missing assertion — stays **T2 / Sonnet 5 / medium**. Only a post-audit repair that is
genuinely semantic, trust-boundary, protocol/crypto or cross-layer reaches T3B/`max`. A bare
`prior_audit_failure` never escalates anything on its own.

**Complexity is not file count.** T3A is proven by evidence — interacting invariants, a novel semantic
contract, fail-closed artifact design, cross-module behavior, a substantial validation loop, an
architectural choice inside the authorized scope, or a complex repair. A bounded two-file
production-plus-test protocol-semantic slice is correctly **T3A / Opus 5 / xhigh**; it must never be demoted
or left unresolved because it touches only two files.

**Task family is chosen before effort.** Routing is intent-first: `TASK_INTENT` selects the family
(`STATUS`, `CLOSEOUT`, `BOUNDED_READ`, `IMPLEMENTATION`, `REPAIR`, `REVIEW`, `ARCHITECTURE`,
`PROMPT_ARCHITECTURE`, `CLASS_C_CROSS_CONTRACT`, `EXTERNAL_RESEARCH`), and only then do risk and complexity
choose the effort inside it. **T3B accepts IMPLEMENTATION or REPAIR mutation only** — it can never absorb a
review, an architecture decision or a prompt design, no matter which risk flags are set. A cryptographic
review is still a review (T3C, effort `xhigh`). A readiness architecture decision is still architecture
(T3D, effort `max`). A capability-critical prompt design is still prompt architecture (T3E, effort `max`).
If two families are implied and no explicit `TASK_INTENT` is given, the task is `UNRESOLVED` and read-only
until the controller classifies it — never a silent T3B.

**An authorized merge is T1 even though it mutates.** Governed mechanical closeout — standard merge,
post-merge commands,
parent/digest verification, clean-main proof — stays **T1 / Sonnet 5 / low** when it is fully authorized,
mechanically bounded, free of semantic anomaly and free of any readiness/connector transition. Mutation
alone does not push it into T2. If any of those conditions fails, it leaves T1 and escalates.

**Why indiscriminate `max` is inefficient.** It produces more tool calls, longer reasoning and higher
latency, consumes more tokens and premium requests, and increases the chance of overthinking and
unnecessary scope exploration. `max` everywhere degrades throughput without improving correctness on work
that `xhigh` already proves.

**Thinking policy.** Adaptive thinking stays enabled. Never request or set `thinking: disabled` on a T3
mutation lane, and never combine disabled thinking with `xhigh` or `max`. Control cost through effort
selection, scope and context — never by suppressing reasoning.

**Runtime proof.** Before mutation the session proves `MODEL_ACTUAL` and `MODEL_EFFORT_ACTUAL` from
session-level evidence (runtime banner, `/model`, `/status`, or an equivalent local diagnostic), not from a
settings file alone. An unresolved alias such as `opus` is insufficient. Mismatch or fallback is
`STOP_WITH_PROOF` before mutation. A human may waive an effort mismatch for a specific task; the waiver and
the TRUE actual effort are both recorded, and the actual is never restated as the requested value.

**`ULTRACODE_POLICY`.** If a Claude Code build exposes `ultracode`, treat it as an orchestration mode, not
an effort level. Never a default, never persisted; requires runtime proof, explicit controller
authorization, genuinely independent substantial parallel work, isolated ownership, no overlapping
mutations, and primary-agent verification. Otherwise use single-agent `xhigh`/`max`.

---

## 2. How to prompt Opus 5 for maximum value

A strong Opus 5 prompt gives the complete bounded specification up front and then lets the model complete
the loop. It specifies, in order:

1. **TASK** — one exact outcome.
2. **MODE / TASK CLASS** — T3A, T3B, T3C, T3D or T3E.
3. **MODEL / EFFORT** — exact model id and the chosen effort.
4. **MISSION** — the complete bounded outcome, not a vague ambition.
5. **CURRENT STATE TO VERIFY** — the fresh facts that must be proven before mutation.
6. **AUTHORIZED SCOPE** — exact files, maximum changed files, prohibited surfaces.
7. **INVARIANTS** — the properties that must remain true.
8. **TESTS** — targeted, full, wrapper and CI requirements.
9. **PERMISSIONS** — commit, push, PR and merge stated separately.
10. **STOP CONDITIONS** — every state that must halt mutation.
11. **REPORT FORMAT** — compact, structured evidence.
12. **NEXT SAFE ACTION** — with unauthorized continuation explicitly forbidden.

### What NOT to do

- Do not write only "do everything".
- Do not ask for maximum thinking without a bounded objective.
- Do not give conflicting instructions.
- Do not request repeated generic self-checks.
- Do not manually prescribe every reasoning step.
- Do not mix historical state with current facts.
- Do not ask Opus to infer live repository state.
- Do not ask for several competing prompts when one best contract is required.
- Do not hide merge authority inside a general permission.
- Do not use marketing language.
- Do not widen scope with "improve anything else you find".

### Controller formula

```text
GOOD PROMPT =
  complete objective
+ exact state pins
+ bounded scope
+ invariants
+ deterministic gates
+ explicit permissions
+ stop conditions
+ compact report
```

### Behavior calibration to include in Opus mutation prompts

- **Scope:** deliver exactly the authorized task at the intended scope; make routine implementation
  judgements independently; do not widen, narrow or transform the slice; when a materially better
  architecture requires scope expansion, report it and stop before unauthorized mutation.
- **Decision commitment:** select the strongest evidence-supported design and proceed; reopen a settled
  design decision only when new repository or test evidence directly contradicts it.
- **Progress narration:** one concise sentence before the first tool call; afterwards report only material
  findings, blockers, direction changes and phase transitions. Do not narrate routine commands.
- **Self-correction:** correct an earlier statement only when the error changes code, conclusions,
  authorization or the next action; fix non-material slips silently.
- **Verification:** run each deterministic gate once per unchanged head; rerun only after a relevant
  mutation or invalidating evidence. Do not add generic "double-check everything" loops.
- **Subagents:** default 0; bounded one- or two-file work 0; maximum 2 read-only subagents for genuinely
  independent, substantial, parallelizable investigation. Never for routine commands, polling, duplicate
  self-review, small patches, or work finishable with a few direct tool calls. Only one agent mutates a
  branch, and the primary agent independently validates every subagent conclusion.
- **Independence:** a same-model self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT` and never satisfies an
  independent audit. Class C always needs a fresh Codex Sol context.

---

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

## 3. Reusable prompt templates

Placeholders are `<angle-bracketed>`. Use the smallest template that fits; every template lists when NOT to
use it. Opus mutation templates carry the full model/effort block; Sonnet templates stay deliberately short.

### 3.1 `OPUS5_T3A_COMPLEX_IMPLEMENTATION_XHIGH`

Use for difficult multi-file semantic implementation.
Do NOT use for capability-critical cryptographic/readiness/trust-boundary IMPLEMENTATION OR REPAIR; use 3.2.
Review, architecture and prompt architecture remain templates 3.4–3.7. Do NOT use for anything Sonnet can
safely complete (3.10).

```text
MODEL_REQUESTED: Claude Opus 5
MODEL_ID_REQUIRED: claude-opus-5
MODEL_ACTUAL_TO_REPORT: <print from runtime before any mutation>
MODEL_EFFORT_REQUESTED: xhigh
MODEL_EFFORT_ACTUAL_TO_REPORT: <print from runtime>
MODEL_FALLBACK: NONE (fallback -> STOP_WITH_PROOF before mutation)
TASK: <one exact outcome>
MODE: T3A_COMPLEX_IMPLEMENTATION
MISSION: <complete bounded outcome, including what "done" means>
CURRENT STATE TO VERIFY: main @ <sha>; clean worktree; <n> open PRs; <branch absent>; <baseline flags>
PRECHECK: git fetch origin --prune; git switch main; git pull --ff-only; git rev-parse HEAD;
  git status --short --branch; gh pr list --state open --json number,headRefName,url
SEMANTIC_BOUNDARY: <the one contract this closes>; ALLOWED_FILES: <exact files>;
  DEPENDENCY_CLOSURE: <direct dependencies included>; PROTECTED_SURFACES: <exact, must not change>
INVARIANTS: <fail-closed / digest / paper-only / determinism properties that must remain true>
TEST: python -m ruff check <paths>; python -m ruff format --check <paths>;
  python -m pytest -x -q <targeted>; powershell -File scripts/crypto_core/run_full_tests_logged.ps1;
  git diff --check. Require PYTEST_EXIT=0 and WRAPPER_EXIT=0.
COMMIT / PR / MERGE: commit AUTHORIZED; push AUTHORIZED; exactly one PR AUTHORIZED; merge NOT AUTHORIZED.
FORBIDDEN: scope widening; product surfaces outside scope; direct main push; force-push; broad git add;
  self-approval; auto-merge; live/private API; orders; scheduler; BIST.
STOP CONDITIONS: model/effort mismatch; fallback; dirty tree; head mismatch; open-PR collision;
  out-of-scope failure; readiness/connector transition; external-fact dependency; authorization gate.
REPORT FORMAT: AGENT_OS_HANDOFF_V1, compact, failure tails only, exactly one next safe action.
```

### 3.2 `OPUS5_T3B_CAPABILITY_CRITICAL_MAX`

Use for capability-critical **IMPLEMENTATION OR REPAIR** after a named T3B trigger.
Do NOT use for review, architecture or prompt architecture — those remain T3C/T3D/T3E and scale effort
inside their own family. Do NOT use because a task feels important: name the fired T3B trigger, or drop
to 3.1.

```text
MODEL_REQUESTED: Claude Opus 5
MODEL_ID_REQUIRED: claude-opus-5
MODEL_ACTUAL_TO_REPORT: <print first>
MODEL_EFFORT_REQUESTED: max
MODEL_EFFORT_ACTUAL_TO_REPORT: <print first>
MODEL_FALLBACK: NONE
TASK: <one exact outcome>
MODE: T3B_CAPABILITY_CRITICAL
T3B_TRIGGER: <the exact trigger that justifies max>
MISSION: <complete bounded outcome>
CURRENT STATE TO VERIFY: <pins> + readiness/connector baseline captured BEFORE and AFTER
PRECHECK: <as 3.1> + readiness and connector probes
SEMANTIC_BOUNDARY: <the one contract this closes>; ALLOWED_FILES: <exact files>;
  DEPENDENCY_CLOSURE: <direct dependencies included>; PROTECTED_SURFACES: <exact, must not change>
INVARIANTS: fail-closed on malformed/missing/stale input; digest recomputed via the public serializer and
  mismatch rejected before READY/ADMITTED/ACCEPTED; no float in finance paths; no readiness/connector
  transition; all non-overclaim flags remain digest-bound False.
TEST: <full ladder as 3.1>; plus the exact negative tests proving the failure mode, not happy paths only.
COMMIT / PR / MERGE: commit/push/one PR AUTHORIZED; merge NOT AUTHORIZED.
FORBIDDEN: <as 3.1> + any readiness/connector/Stage-4/live transition.
STOP CONDITIONS: <as 3.1> + any protected-trigger ambiguity.
INDEPENDENT AUDIT: Class C — a fresh-context Codex Sol audit is mandatory; this session's self-review is
  SELF_AUDIT_ONLY_NOT_INDEPENDENT.
REPORT FORMAT: AGENT_OS_HANDOFF_V1 + READINESS_BEFORE/AFTER + CONNECTOR_BEFORE/AFTER.
```

### 3.3 `OPUS5_T3B_CONTROLLER_REPAIR_MAX`

Use only for complex **semantic, trust-boundary, protocol/crypto or cross-layer** repair after an
exact-head P1/P2 audit finding.
Do NOT use for a first implementation; do NOT use for a mechanical or obvious audit repair — that stays
T2 (use 3.10). A review finding on its own does not authorize mutation: the repair is a separate,
explicitly created IMPLEMENTATION/REPAIR task.

```text
MODEL_REQUESTED: Claude Opus 5 | MODEL_ID_REQUIRED: claude-opus-5 | MODEL_EFFORT_REQUESTED: max
MODEL_ACTUAL_TO_REPORT / MODEL_EFFORT_ACTUAL_TO_REPORT: <print first> | MODEL_FALLBACK: NONE
TASK: repair <P1/P2 id> on the SAME branch <branch> at head <sha>.
MODE: T3B_CONTROLLER_REPAIR
FINDING (verbatim from the auditor): <exact text + exact file:line evidence>
MISSION: fix the proven defect and prove the failure mode is now asserted. No opportunistic cleanup.
CURRENT STATE TO VERIFY: PR <n> OPEN, head <sha> == local == origin; base <sha>; CI <state>.
SEMANTIC_BOUNDARY: <the frozen contract being repaired>; ALLOWED_FILES: <exact files already in the PR>;
  DEPENDENCY_CLOSURE: <direct dependencies>; PROTECTED_SURFACES: <exact>; no new files unless named.
INVARIANTS: the original slice contract is unchanged except for the defect; no scope widening;
  no thread resolution; no re-litigating accepted design.
TEST: regression test that FAILS before and PASSES after; then the full ladder; PYTEST_EXIT=0, WRAPPER_EXIT=0.
COMMIT / PR / MERGE: one bounded same-branch repair commit AUTHORIZED; push AUTHORIZED; new PR FORBIDDEN;
  merge NOT AUTHORIZED; resolving human review threads FORBIDDEN.
STOP CONDITIONS: the finding is not reproducible; the fix requires files outside the PR; the finding
  disputes accepted design; head moved.
REPORT FORMAT: AGENT_OS_HANDOFF_V1 + before/after evidence for the exact finding.
```

### 3.4 `OPUS5_T3C_FOCUSED_REVIEW_MEDIUM`

Use for one- or two-file review and first-pass bug discovery.
Do NOT use for broad multi-module or security-sensitive review (use 3.5), and never call it an independent
audit if the same model produced the code.

```text
MODEL_REQUESTED: Claude Opus 5 | MODEL_ID_REQUIRED: claude-opus-5 | MODEL_EFFORT_REQUESTED: medium
MODE: T3C_FOCUSED_REVIEW — READ-ONLY. No edits, no commits, no branch.
TARGET: <file(s)> at <exact head sha>
PROCESS: (1) discover every evidence-backed issue with NO severity filtering;
  (2) classify severity only after discovery; (3) separate blocker from non-blocker.
EVIDENCE RULE: every finding cites file:line and a concrete failure scenario (inputs/state -> wrong
  output/crash). Speculation without an evidence path is dropped, not downgraded.
OUT OF SCOPE: style preference; unrelated modules; refactor proposals.
REPORT: P1_BLOCKERS / P2_BLOCKERS / P3_NOTES, most severe first, each with exact evidence.
INDEPENDENCE: if this session wrote the code, label the output SELF_AUDIT_ONLY_NOT_INDEPENDENT.
```

### 3.5 `OPUS5_T3C_BROAD_REVIEW_HIGH`

Use for broad multi-module, subtle-semantic or security-sensitive review, and review after an unexpected
failure. Raise to `xhigh` when the review spans multiple trust boundaries, requires protocol/crypto
reasoning, findings conflict, or behavior must be reconstructed across several layers.
Do NOT use for a two-file diff (use 3.4). Protocol or cryptographic subject matter raises the review
**effort** to `xhigh`; it does **not** change the task class to T3B. A review stays read-only — any fix it
motivates is a separate IMPLEMENTATION/REPAIR task.

```text
MODEL_REQUESTED: Claude Opus 5 | MODEL_ID_REQUIRED: claude-opus-5
MODEL_EFFORT_REQUESTED: high  (xhigh iff: multi-trust-boundary | protocol/crypto | conflicting findings |
  cross-layer reconstruction — state which)
MODE: T3C_BROAD_REVIEW — READ-ONLY.
TARGET: <modules / PR range> at <exact head sha>; DIRECT DEPENDENCIES: <named>
FOCUS: fail-closed behavior; digest/provenance correctness; trust transitions; negative-test coverage;
  denominator/record-set integrity; replay/TOCTOU; determinism; overclaim flags.
PROCESS: discover -> classify -> separate blockers. Reconstruct behavior from source, not from prose.
CONTEXT BUDGET: named modules + immediate dependency interfaces; expand only on an unresolved reference,
  a cross-module invariant, or a test-exposed dependency — and say why.
REPORT: P1/P2/P3 with file:line + failure scenario; UNKNOWN for anything unproven.
```

### 3.6 `OPUS5_T3D_ARCHITECTURE_HIGH_OR_XHIGH`

Use for next-slice selection and architecture comparison.
Do NOT use to implement; this lane produces a decision, not a diff. Readiness/provenance or cryptographic
criticality raises the **effort to `max` inside T3D** — it does not move the task to T3B.

```text
MODEL_REQUESTED: Claude Opus 5 | MODEL_ID_REQUIRED: claude-opus-5
MODEL_EFFORT_REQUESTED: high  (xhigh iff candidate slices interact or architecture spans several modules;
  max ONLY iff the decision controls readiness/provenance, involves cryptographic boundaries, or a wrong
  sequence creates irreversible or high-cost work)
MODE: T3D_ARCHITECTURE — READ-ONLY. No mutation.
OBJECTIVE: <the decision to make>
PINNED STATE: main @ <sha>; merged chain <...>; open blockers <...>
CANDIDATES: <slices, or "derive them">
SCORE EACH ON: edge-to-money value; safety class; downstream unlock; implementation risk; testability;
  token cost; sequencing/irreversibility; roadmap alignment.
OUTPUT: exactly ONE recommended slice + WHY_NOW + FILES_TO_READ + RISKS + STOP_IF + the routing lane and
  effort the implementation should use. No competing recommendations unless explicitly requested.
```

### 3.7 `OPUS5_T3E_COMPLEX_PROMPT_DESIGN_HIGH_OR_XHIGH`

Use to convert a new complex objective into ONE execution prompt.
Do NOT use for a known bounded mechanical task — that prompt is Sonnet 5 / medium. Capability-critical
prompt design (Agent OS or model-routing prompts, prompts governing readiness/provenance promotion or
cryptographic verification, capability-critical controller repair prompts) raises the **effort to `max`
inside T3E** and the work stays T3E — it never becomes T3B.

```text
MODEL_REQUESTED: Claude Opus 5 | MODEL_ID_REQUIRED: claude-opus-5
MODEL_EFFORT_REQUESTED: high  (xhigh iff protocol/crypto/readiness constraints must be synthesized, the
  task follows an audit failure, or several safe implementation paths exist; max ONLY for Agent OS/routing
  architecture or prompts governing readiness/cryptographic implementation)
MODE: T3E_PROMPT_ARCHITECTURE — READ-ONLY. Produce a prompt, not a patch.
OBJECTIVE: <the future task>
REQUIRED ARCHAEOLOGY: <files/PRs to read to pin invariants and prior decisions>
OUTPUT: exactly ONE complete execution contract using section 2 of this playbook (TASK, MODE, MODEL/EFFORT,
  MISSION, CURRENT STATE TO VERIFY, PRECHECK, AUTHORIZED SCOPE, INVARIANTS, TEST, PERMISSIONS, FORBIDDEN,
  STOP CONDITIONS, REPORT FORMAT, NEXT SAFE ACTION), with the selected lane and effort justified in one line.
```

### 3.8 `SONNET5_T0_STATUS_LOW`

Use for status and polling.
Do NOT use when evidence conflicts or the task turns semantic — escalate instead.

```text
MODEL: claude-sonnet-5 | EFFORT: low | READ-ONLY
TASK: report current state. Commands, one at a time:
  git rev-parse HEAD; git status --short --branch;
  gh pr list --state open --json number,title,isDraft,headRefName,headRefOid,url;
  gh pr checks <n>   (snapshot only — never --watch)
REPORT: exact command output, no interpretation beyond the fields asked for. UNKNOWN if unproven.
ESCALATE (stop and say so): evidence conflicts; unexpected ancestry; state cannot be reconciled;
  readiness/connector transition appears; the question becomes semantic.
```

### 3.9 `SONNET5_T1_MERGE_CLOSEOUT_LOW`

Use for an explicitly authorized standard merge and post-merge verification.
Do NOT use without a per-PR human merge authorization naming the PR and command.

```text
MODEL: claude-sonnet-5 | EFFORT: low
AUTHORIZATION: <verbatim human authorization naming PR #<n> and the exact command>
TASK: standard merge of PR #<n> at authorized head <sha>, then post-merge verification.
GUARD: re-prove head == <sha> immediately before merging; if it moved, STOP.
AFTER: git switch main; git pull --ff-only; git rev-parse HEAD; confirm merge commit + parents;
  full suite via scripts/crypto_core/run_full_tests_logged.ps1; git status --short; gh pr list --state open.
FORBIDDEN: squash; rebase; auto-merge; self-approval; branch deletion; any code change.
ESCALATE: merge parents differ; merged scope differs; post-merge validation fails; branch protection
  behaves unexpectedly; readiness or connector state changed.
```

### 3.10 `SONNET5_T2_BOUNDED_WORK_MEDIUM`

Use for narrow docs, config-only changes, mechanical fixtures/tests, and obvious localized repair.
Do NOT use when semantic invariants interact, the trust boundary changes, full-suite failures are
unexpected, architecture is required, or the repair cannot be proven locally — escalate to Opus 5.

```text
MODEL: claude-sonnet-5 | EFFORT: medium (high if moderately complex)
TASK: <one exact change>
ALLOWED_FILES: <exact list> — no other file may change.
PRECHECK: clean tree; on branch <branch>; main @ <sha>.
TEST: python -m ruff check <paths>; python -m ruff format --check <paths>;
  python -m pytest -x -q <targeted>; git diff --check. Full logged suite if any code path changed.
COMMIT / PR: scoped git add of the exact files; one commit; push; one PR. Merge NOT AUTHORIZED.
ESCALATE (stop, do not improvise): interacting invariants; trust-boundary change; unexpected failure;
  architecture needed; scope would widen.
REPORT: RESULT / FILES_CHANGED / VALIDATION / NEXT_SAFE_ACTION.
```

### 3.11 `DEEP_RESEARCH_EXTERNAL_FACT_ROUTER`

Use when a current external fact is load-bearing.
Do NOT use for repository, PR, CI or local test state — those are proven from `git`/`gh`/terminal.

```text
ROUTE: XR — controller-orchestrated Deep Research. No Claude lane may infer this from memory.
TRIGGER: <exchange/venue API | fees | funding/basis | rate limits | order-book semantics | custody |
  regulation | live-readiness criteria | current framework or tool behavior>
EXACT QUESTION: <one answerable question>
WHY IT IS LOAD-BEARING: <what decision changes if the answer differs>
REQUIRED OUTPUT: primary/official sources first, with citations and dates; REPO_EVIDENCE vs
  EXTERNAL_EVIDENCE vs INFERENCE vs UNKNOWN kept separate; advisory only.
FORBIDDEN: implementation; GitHub mutation; merge authority; treating research as a gate waiver.
BLOCKING RULE: the dependent task stays STOPPED with RESULT DEEP_RESEARCH_REQUIRED until answered.
```

---

## 4. `PROMPT_COMPILER_CONTRACT_V1`

**Semantic sizing only.** `MAX_SAFE_PR` is decided by semantic closure (`agent_os_v2.md` section 4). No
serious prompt carries a numeric changed-file cap: `MAX_CHANGED_FILES` is retired as an active field and
must not be reintroduced. Exact `ALLOWED_FILES` remain mandatory for any scoped mutation, together with
`SEMANTIC_BOUNDARY`, `DEPENDENCY_CLOSURE`, `PROTECTED_SURFACES` and the `SPLIT_CONDITIONS` from
`agent_os_v2.md` section 4.


A deterministic contract a ChatGPT or Claude controller uses to generate ONE best prompt.

**Input fields**

```text
TASK_INTENT               TASK_OBJECTIVE            CURRENT_REPO_STATE
TASK_ARCHETYPE            RISK_CLASS                TRUST_BOUNDARY_EFFECT
PROTOCOL_OR_CRYPTO_EFFECT READINESS_EFFECT          EXTERNAL_FACT_REQUIREMENT
ALLOWED_FILES             DEPENDENCY_CLOSURE        TEST_SURFACE
PR_STATE                  MERGE_AUTHORITY
```

`TASK_INTENT` is one of `STATUS | CLOSEOUT | BOUNDED_READ | IMPLEMENTATION | REPAIR | REVIEW |
ARCHITECTURE | PROMPT_ARCHITECTURE | CLASS_C_CROSS_CONTRACT | EXTERNAL_RESEARCH`. It is resolved FIRST and
is never overridden by a risk field.

**Compilation order (mandatory)**

```text
intent family
  -> external / Class-C / human-authorization gates
  -> complexity and risk INSIDE that family
  -> model
  -> effort
  -> context budget
  -> permissions
  -> verification and report profile
```

**Output fields**

```text
SELECTED_TASK_INTENT      SELECTED_TASK_CLASS       SELECTED_MODEL
SELECTED_MODEL_ID         SELECTED_EFFORT           SELECTION_RATIONALE
CONTEXT_BUDGET_CLASS      SUBAGENT_POLICY           ONE_COMPLETE_PROMPT
```

**Rules**

0. Resolve `TASK_INTENT` before consulting any risk field. A risk flag selects the EFFORT inside the
   family; it never changes the family. Review stays T3C, architecture stays T3D, prompt architecture
   stays T3E, however cryptographic, readiness-bearing or trust-boundary-bearing the subject is. If two
   families are implied and no explicit `TASK_INTENT` is given, emit a read-only `UNRESOLVED` analysis
   prompt — never a T3B prompt.
1. Emit exactly one best prompt. No competing alternatives unless explicitly requested.
2. Select the lowest-cost lane that safely proves correctness.
3. Use Opus 5 only when Sonnet 5 is insufficient; state why in one line.
4. Use `max` only when `xhigh` is insufficient, and name the family-specific maximum-effort trigger:
   `T3B` requires a named IMPLEMENTATION/REPAIR trigger (3.2/3.3); `T3D` requires a named ARCHITECTURE
   trigger — readiness/provenance, cryptographic boundary, irreversible/high-cost sequencing, or explicit
   controller designation (3.6); `T3E` requires a named PROMPT_ARCHITECTURE trigger — Agent OS/model-routing
   prompt, a prompt governing readiness/provenance or cryptographic verification, or explicit controller
   designation (3.7). `RISK_CLASS` alone, and the fact that the task follows an audit finding, are never
   sufficient on their own — a mechanical or obvious post-audit repair compiles to the T2 Sonnet template
   (3.10), not to 3.3. **Never convert a `max`-effort T3D or T3E task into T3B**: the family is fixed by
   `TASK_INTENT` (rule 0) before this rule ever runs.
5. Do not ask the user to choose an effort level when the classification is provable from the inputs.
6. `EXTERNAL_FACT_REQUIREMENT` present and load-bearing → emit template 3.11, not an implementation prompt.
7. Unresolved risk → emit a READ-ONLY analysis prompt (Opus 5 `high`/`xhigh`) before any mutation prompt.
8. `MERGE_AUTHORITY` absent or ambiguous → the emitted prompt states merge NOT AUTHORIZED.
9. Apply the routing function in workflow section 24.12 in order; the first matching rule wins.
10. Carry every guardrail through compression: shortening a prompt never drops a stop condition, an
    invariant, a permission boundary, or a validation gate.

---

## 5. Context and token efficiency

**Minimum sufficient context.** Read the authoritative setup files, the directly affected production/test
files, the immediate dependency interfaces, and the relevant current PR/main evidence. Do not automatically
read the whole repository, every historical lesson, unrelated modules, stale archives, old prompts, or
generated output.

**Progressive disclosure.** Start with a narrow search. Expand only when a reference is unresolved, an
invariant crosses modules, a test exposes a dependency, or architecture cannot be proven locally — and say
why the expansion was necessary.

**Context pins.** Use exact values: main SHA, branch, PR head, file paths, profile ids, digests, tests, and
the current open-PR count. Never rely on conversational memory for live repository state.

**Report compression.** Keep full evidence in a temporary handoff file when it is long; return a compact
evidence block. Never repeat identical proof in several prose sections. Failure tails only, never full
success logs.

**Tool-call efficiency.** Run one command at a time when command causality matters; batch only independent
read-only queries. Do not rerun a passed gate unless the relevant files changed, the head changed, or new
evidence invalidated it.

---

## 6. Non-regression

This playbook changes prompt construction only. It does not weaken any gate: one repository writer and one
open PR at a time; no direct `main` push; standard merge only; no self-approval and no auto-merge; explicit
per-PR human merge authorization; pending CI is `NOT_READY`; current valid P1/P2 threads block; Class-C work
always gets a fresh independent Codex Sol audit that no Claude lane may satisfy; the connector final gate is
never waived; post-merge verification precedes the next slice; crypto_core scope only — no BIST, live or
private API, credentials, orders, scheduler/auto-loop, shadow/live execution, or capital mutation.

**Codex lanes are permanent.** Codex GPT-5.6 Sol (protected T4 `CROSS_CONTRACT_DESIGN_OR_AUDIT`), Codex
GPT-5.6 Terra (bounded implementation and ordinary independent audit) and Codex GPT-5.6 Luna (T0 mechanics)
remain durable workflow lanes. Nothing in this playbook narrows, renames, renumbers or absorbs them; the
Claude lanes never take Class-C work, and a Claude self-review never satisfies the Class-C requirement.
ChatGPT GPT-5.6 Thinking remains the controller, auditor and router, and explicit per-PR human merge
authorization remains mandatory.

**Temporary availability is never durable routing.** Model quota, rate limits or short-term unavailability —
for any vendor, Claude or Codex — are transient operational facts. Record them in the controller handoff for
that one task and route around them there. Never write a temporary availability state into this playbook or
into `agent_workflow.md`, and never infer from a quota event that a lane has been retired.
