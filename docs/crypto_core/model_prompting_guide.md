# crypto_core Model Prompting Guide (v5, 2026-09-26 — protected-only Astra edition)

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended, most
recently by `CODEX_QUOTA_RESILIENCE_V2`
(`docs/crypto_core/agent_workflow.md` section 24 — the authority; this guide teaches how to WRITE prompts for
it and never overrides it). Claude prompt templates: `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`.
Research protocol: `docs/crypto_core/deep_research_protocol.md`. On any conflict, section 24 and the stricter
safety rule win. Nothing in this guide proves repository state or authorizes a merge.

Active council (section 24.3): ChatGPT controller (read-only first, `CONTROLLER_READONLY_FIRST_POLICY`),
Claude Opus 5.5 (`claude-opus-5-5`), Codex GPT-5.6 Sol, GPT-6 Astra, ChatGPT Work, Deep Research. Not
routable, and never an automatic fallback: Claude Sonnet 5, Codex GPT-5.6 Terra and Codex GPT-5.6 Luna
(`NOT_IN_ACTIVE_COUNCIL`); Claude Opus 5 (`SUPERSEDED_BY_OPUS_5_5`); Claude Opus 4.8
(`SUPERSEDED_BY_OPUS_5`); Claude Fable 5 (`INACTIVE_EXPIRED_RETIRED`); Copilot (`INACTIVE_UNAVAILABLE`).
Copilot-era repository files are inactive compatibility material and never enter prompt construction.

## 1. Serious prompt shape

Every serious prompt uses the section 24.6 `SERIOUS_PROMPT_COMPILER` order: `TASK_INTENT`,
`SEMANTIC_BOUNDARY`, `STATE_PIN`, `MODEL_RUNTIME_PROOF`, `ALLOWED_FILES`, `INVARIANTS`, `BLOCKER_INVENTORY`,
`VALIDATION_MATRIX`, `GITHUB_AUTHORIZATION`, `FORBIDDEN`, `STOP_CONDITIONS`, `HANDOFF`. Authoring notes:

- `TASK_INTENT` comes first, one per prompt; never an implementation together with its own independent audit.
- `SEMANTIC_BOUNDARY` names the one contract the PR closes as the largest safe semantic closure (section
  24.8) — never a file-count or LOC target.
- `STATE_PIN` carries exact SHAs, branch, PR and open-PR count; the executor re-proves them locally.
- `MODEL_RUNTIME_PROOF` carries the section 24.12 fields and requirements (`MODEL_ID_REQUIRED`, required
  thinking), with the host label written literally; identity and required thinking fail closed on `UNKNOWN`, and
  only effort may stay `UNKNOWN`.
- `BLOCKER_INVENTORY` names inherited blockers by semantic defect (identity survives renames) and, for a repair
  or re-audit, the complete controller-adjudicated P1/P2 set together with its `REPAIR_ENTRY_MODE` (section 24.8).
- `VALIDATION_MATRIX` is exact; the full crypto_core suite runs only via `run_full_tests_logged.ps1`.
- `GITHUB_AUTHORIZATION` lists authorized and not-authorized actions separately; merge is never implied.
- `HANDOFF` requires `AGENT_OS_HANDOFF_V1` with the ACTUAL meaningful-prompt and challenge counts of the
  lifecycle so far (never a number fixed in a template) and exactly one next safe action.
- Carry the domain profile (`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE`, section 24.2) and every standing rail;
  shortening a prompt never drops a stop condition, invariant, permission boundary or validation gate.

## 2. Lane-by-lane rules

### 2.1 ChatGPT controller

- **Owns:** routing; architecture adjudication; serious prompt compilation; evidence judgement and
  contradiction detection against live GitHub/terminal proof; `CONTROLLER_ACCEPTED_STATE`; merge-readiness
  judgement; exactly one next action.
- **Read-only first (section 24.10):** establish every fact, source reading, GitHub/CI check and read-only
  adjudication yourself before spending a specialist execution, and never ask the human for terminal proof you or
  the routed agent can obtain.
- **Budget duty (section 24.8):** keep the ONE `HARD_FIVE_EXECUTION_BUDGET` — implementation, acceptance audit,
  repair, re-audit and every challenge count; governance counts zero. Target the fewest; dispatch a challenge only
  when its value justifies a slot and `BUDGET_ADMISSION_RULE` admits it; never an execution six; never hide
  specialist work inside governance; adjudicate a disputed severity under `AUDIT_MATERIALITY_BOUNDARY_V1` before
  applying `FIXED_POINT_STOP`; open a new attempt only through a `TASK_INTENT=ARCHITECTURE` `ROOT_CAUSE_ESCAPE`
  decision.
- **Audit routing (section 24.4):** classify against `PROTECTED_TRIGGER_MATRIX_V2` and record the letters or
  `NONE`, classifying upward on ambiguity. Non-protected: perform `CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT`
  yourself, provided you (including through ChatGPT Work) neither implemented nor repaired the candidate; route
  Codex Sol only as a recorded eligibility gap; never GPT-6 Astra. Protected: run `CONTROLLER_PROTECTED_PREFLIGHT`;
  if it confirms a complete material P1/P2 set, open the one repair through
  `PROTECTED_CONTROLLER_PREFLIGHT_CONFIRMED_BLOCKER_SET` instead of dispatching Astra; otherwise compile
  `PROTECTED_AUDIT_PACKET_V2` and dispatch ONE GPT-6 Astra `Ultra` audit on the stabilized head. Astra
  quota-blocked or unavailable → `ASTRA_QUOTA_BLOCK_FREEZE`. No independent eligible reviewer → `STOP_WITH_PROOF`.
  Exception: a change to this control plane is governed by the plane of its base, not its own text (section 24.14).
- **Never:** product implementation; any protected audit or protected acceptance; auditing or accepting its own
  (or ChatGPT Work's) implementation or repair; a substitute for local tests; memory as repository state; GitHub
  mutation without an exact human action authorization; merge authority.
- **Anti-patterns:** trusting a report because it is detailed; merging on `mergeable` alone; issuing two
  writers at once; accepting one finding at a time from an auditor; dispatching Astra for a non-protected
  candidate, an unstable head or discovery you can do; dispatching Sol for model diversity.

### 2.2 ChatGPT Work

- **Best tasks:** substantial multi-step execution that genuinely needs a cloud browser/computer, many files,
  apps, or broad evidence collection.
- **Rules:** runs from a serious prompt with the same gates; its output is a claim until the controller
  verifies it; it never holds governance, accepted-state or merge authority.

### 2.3 Deep Research — external/current facts

- **Best tasks:** current exchange/Deribit APIs, fees, rate limits, funding, margin, liquidation,
  microstructure, custody/security/regulation, current framework or model/tool behavior,
  readiness/shadow/live standards, architecture benchmarks.
- **Bad tasks:** repo/PR/CI state, threads, local tests, branch hygiene, routine implementation.
- **Rules:** controller-orchestrated, read-only, advisory, primary sources first with dates;
  REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN kept separate; never a gate waiver.

### 2.4 Claude Opus 5.5 — deep semantic implementation and repair

- **Best tasks:** complex semantic implementation, fail-closed artifact design, cross-module integration,
  forensic debugging with long validation loops, the `ROOT_CAUSE_ESCAPE` implementation and the single
  consolidated repair of a candidate, together with the repo-native navigation, mechanical, static-inspection,
  test-generation, local validation, CI-diagnosis and exhaustive self-audit work of that same task; when routed,
  the optional read-only `OPUS55_READONLY_CHALLENGE` (section 24.4), which is evidence only.
- **Rules:** host effort label recorded literally — `xhigh` for ordinary complex implementation and repair,
  `max` only on an explicitly named capability-critical or hardest-correctness-critical trigger and never as a
  general default; thinking enabled and still proven from runtime evidence; runtime
  proof before mutation; one PR per semantic boundary; its self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`.
- **Templates:** `opus5_prompting_playbook.md` section 3.

### 2.5 Codex GPT-5.6 Sol — reserve only

- **When:** only as `SOL_RESERVE_ONLY` (section 24.3), on a controller-recorded capability or eligibility gap the
  controller and the routed Opus 5.5 task cannot legally or safely cover — typically the non-protected acceptance
  audit when `NO_SELF_AUDIT` makes the controller ineligible.
- **Rules:** host label `Ultra` recorded literally; never the default auditor, navigator, status checker, reviewer
  or implementation accelerator; never added for model diversity; never audits a candidate it implemented or
  repaired; never satisfies a protected audit.

### 2.6 GPT-6 Astra — sole protected acceptance auditor

- **Best tasks:** the protected whole-contract audit and the one protected re-audit of a candidate with at least
  one trigger of `PROTECTED_TRIGGER_MATRIX_V2`, including control-plane changes (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`);
  the same execution is the protected T4 `CLASS_C_CROSS_CONTRACT` audit and terminal decision. Never a
  non-protected candidate and never repository discovery the controller can do.
- **Rules:** `MODEL_ID_REQUIRED=gpt-6-astra`; host labels `Light` / `Medium` / `High` / `Extra High` / `Ultra`
  recorded literally; requested effort `Ultra`; fallback prohibited; thinking enabled; runtime proof before
  substantive audit; never mutates, implements or repairs; complete material P1/P2 collection over the protected
  boundary under `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE`, verifying independently every
  load-bearing fact. Input is a `PROTECTED_AUDIT_PACKET_V2` on a stabilized head. Its first audit's complete set
  opens the one repair; a genuine P1/P2 after the one re-audit rejects the candidate. Unavailability freezes the
  head and makes the gate wait; it never reassigns protected acceptance.

## 3. Lifecycle prompt skeletons

```text
TASK_INTENT: IMPLEMENTATION
SEMANTIC_BOUNDARY: <one coherent contract closed as the largest safe semantic closure>
STATE_PIN: main @ <sha>; open PRs <n>; branch <name> absent
MODEL_RUNTIME_PROOF: <section 24.12 fields; host label literal>
ALLOWED_FILES: <exact>   INVARIANTS: <exact>   BLOCKER_INVENTORY: <inherited blocker identities or NONE>
VALIDATION_MATRIX: <exact ladder>   GITHUB_AUTHORIZATION: branch/commit/push/one PR; merge NOT AUTHORIZED
FORBIDDEN: <task-specific + standing rails>   STOP_CONDITIONS: <enumerated>
HANDOFF: AGENT_OS_HANDOFF_V1; MEANINGFUL_PROMPT_COUNT_THIS_PR: 1
```

```text
TASK_INTENT: AUDIT (ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1; protected; fresh context, READ_ONLY) — GPT-6 Astra
MODEL_RUNTIME_PROOF: gpt-6-astra | effort Ultra | fallback PROHIBITED | thinking ENABLED; proven before auditing
PROTECTED_AUDIT_PACKET_V2: BASE_SHA / HEAD_SHA / HEAD_TREE / CHANGED_FILES / PROTECTED_TRIGGER_LETTERS /
  CRITICAL_PROTECTED_CLAIMS / LOAD_BEARING_PROTECTED_DEPENDENCIES / CONTROLLER_PREFLIGHT_RESULT /
  OPUS_CHALLENGE_RESULT_IF_ANY / CI_STATE / REVIEW_THREADS / UNRESOLVED_MATERIAL_P1_P2 /
  EXACT_PROTECTED_ACCEPTANCE_QUESTIONS — doctrine by repository path, no chat-history recovery, missing facts UNKNOWN
SEMANTIC_BOUNDARY: <the declared contract of PR #<n>>; judge it, do not expand it (FINITE_AUDIT_RULE); verify
  every load-bearing protected fact yourself; do not redo unrelated discovery the packet already pins
OUTPUT: the COMPLETE current material P1/P2 set in one pass, each with invariant, file:line evidence, supported
  entry/consumer path, effect, materiality and minimum regression proof (AUDIT_MATERIALITY_BOUNDARY_V1); P3
  separately; the protected Class-C and terminal verdict. Zero mutation.
```

A non-protected acceptance audit is the controller's own work (`CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT`), to the
same OUTPUT standard; a recorded `SOL_RESERVE_ONLY` substitute uses the same skeleton with its gap stated.

```text
TASK_INTENT: REPAIR (the ONE consolidated repair) — Claude Opus 5.5
REPAIR_ENTRY_MODE: <ACCEPTANCE_AUDIT_CONFIRMED_BLOCKER_SET | PROTECTED_CONTROLLER_PREFLIGHT_CONFIRMED_BLOCKER_SET>
BLOCKER_INVENTORY: <the complete controller-adjudicated P1/P2 set of that mode, verbatim, with identities>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on the same branch; no new scope
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt
HANDOFF: AGENT_OS_HANDOFF_V1; this is the candidate's only repair; ACTUAL_MEANINGFUL_EXECUTION_COUNT: <executions
  run so far, including this repair>; CHALLENGE_COUNT: <actual>
```

```text
TASK_INTENT: REAUDIT (the ONE whole-contract re-audit) — the acceptance lane: GPT-6 Astra on a fresh
  PROTECTED_AUDIT_PACKET_V2 after the preflight runs again (protected), or the controller (non-protected)
STATE_PIN: repaired head <sha>; BLOCKER_INVENTORY: <the repaired set>
OUTPUT: the COMPLETE current material P1/P2 set of the whole contract, not only the repaired lines. Any genuine
  material P1/P2 -> FIXED_POINT_STOP after controller severity adjudication; P3 never blocks.
```

```text
TASK_INTENT: ARCHITECTURE (ROOT_CAUSE_ESCAPE decision) — ChatGPT controller
INPUT: the rejected candidate's blocker identities and evidence
OUTPUT: the reconstructed root cause; the changed architecture or boundary; one new bounded semantic
  closure starting from accepted main; the inherited blocker identities; what rejected history must never
  become canonical. No automatic replacement PR.
```

## 4. Research packet and freshness

A CONTROLLER_TO_DEEP_RESEARCH packet carries the exact question, why current external facts are required, the
pinned repository state and files, primary-source requirements, prohibited weak sources, evidence buckets,
forbidden mutations and the expected output. Research is reused only while the question, the relevant
repository state and the source versions are materially unchanged; it is refreshed on API/pricing/regulation/
framework changes or before authorizing a current external decision. The controller verifies repository
claims, inspects load-bearing citations, separates facts from inference, and converts accepted findings into
at most one bounded next-PR proposal — never merge authorization.

## 5. Non-regression

This guide changes prompting ergonomics only. It does not alter: one open PR; one repository writer; no
direct `main` push; standard merge only; explicit per-PR, exact-head human merge authorization; pending CI =
`NOT_READY`; current valid material P1/P2 threads block; the GPT-6 Astra audit for protected work;
post-merge verification; crypto_core-only scope; paper-first/fail-closed/deterministic rails; and the
validity of any open blocker until its own gates close it.
