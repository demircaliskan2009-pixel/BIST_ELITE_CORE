# crypto_core Model Prompting Guide (v5, 2026-09-25 — Codex quota resilience edition)

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by
`ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` and `CODEX_QUOTA_RESILIENCE_V1`
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
  or re-audit, the complete audited P1/P2 set.
- `VALIDATION_MATRIX` is exact; the full crypto_core suite runs only via `run_full_tests_logged.ps1`.
- `GITHUB_AUTHORIZATION` lists authorized and not-authorized actions separately; merge is never implied.
- `HANDOFF` requires `AGENT_OS_HANDOFF_V1` with the meaningful-prompt count and exactly one next safe action.
- Carry the domain profile (`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE`, section 24.2) and every standing rail;
  shortening a prompt never drops a stop condition, invariant, permission boundary or validation gate.

## 2. Lane-by-lane rules

### 2.1 ChatGPT controller

- **Owns:** routing; architecture adjudication; serious prompt compilation; evidence judgement and
  contradiction detection against live GitHub/terminal proof; `CONTROLLER_ACCEPTED_STATE`; merge-readiness
  judgement; exactly one next action.
- **Read-only first (section 24.10):** before spending any specialist quota, do the GitHub state, SHA/tree, CI and
  job proof, diff and patch inspection, thread adjudication, source reading, dependency tracing, static
  consistency, scope/non-claim analysis, architecture reconciliation and severity classification yourself. Never
  ask the human to run a terminal command that the connector or the routed agent can run
  (`USER_MANUAL_WORK_MINIMIZATION`).
- **Budget duty:** target the fewest specialist prompts (2 clean, 4 repaired, hard maximum 5) and count them
  per PR lifecycle (governance operations — state proof, CI/status
  reads, adjudication, protected classification, the preflight review and protected packet, merge-readiness, the
  authorization request, merge, post-merge verification, fresh-chat acceptance — do not count); your own
  non-protected acceptance audit fills the audit slot; count Opus challenges separately (at most two,
  `CHALLENGE_BUDGET`); never issue a specialist sixth; never hide specialist work inside governance; adjudicate a
  disputed severity under `AUDIT_MATERIALITY_BOUNDARY_V1` before applying `FIXED_POINT_STOP`; open a new attempt only through a `TASK_INTENT=ARCHITECTURE` `ROOT_CAUSE_ESCAPE` decision.
- **Audit routing (section 24.4):** classify every candidate against the finite `ASTRA_PROTECTED_TRIGGER_MATRIX_V1`
  (A control plane/governance; B digest/signature/provenance/custody/attestation/anti-replay/trust-root; C
  Machine-Time/trusted time/native-worker admission; D operational connector/readiness/external-trust
  transitions; E live/private API/order routing/scheduler/shadow/live/capital/credential/security; F transitions
  granting READY/ADMITTED/ACCEPTED, Stage advancement or paper-to-live authority; G capital-authorizing risk
  thresholds) and record the letters or `NONE`; classify upward when ambiguity remains, never downward to save
  quota.
  - NON-PROTECTED: perform `CONTROLLER_INDEPENDENT_AUDIT_NONPROTECTED` yourself — fresh exact-head proof, every
    changed file, load-bearing dependencies, CI and threads, supported-path adversarial reasoning, P1/P2/P3
    materiality, scope and non-claims, determinism and fail-closed review, the complete material blocker set —
    provided you, including through ChatGPT Work, neither implemented nor repaired the candidate. Test and CI
    evidence informs it and never replaces it. Route an Opus 5.5 challenge first only for a broad or high-risk
    candidate. When you are ineligible, route Codex Sol as a recorded `SOL_RESERVE_ONLY` gap; never GPT-6 Astra.
  - PROTECTED: run `CONTROLLER_PREFLIGHT_REVIEW` to the same coverage, route an Opus 5.5 challenge when it lowers
    the risk of wasting Astra, repair confirmed material P1/P2 first (the one consolidated repair), then compile
    `PROTECTED_AUDIT_PACKET_V1` and dispatch ONE GPT-6 Astra `Ultra` audit on the stabilized head as the last
    semantic gate. Astra unavailable or quota-blocked → freeze that head, keep only permitted read-only
    preparation going, no protected merge (`ASTRA_QUOTA_BLOCKED_FREEZE`).
  - No independent eligible reviewer → `STOP_WITH_PROOF`. Exception: the change that introduces this routing is
    audited under section 24 and the adapters of its base, not its own text (section 24.14 transition).
- **Never:** product implementation; any protected audit or protected acceptance; auditing or accepting its own
  implementation or repair (including ChatGPT Work's); a substitute for local tests; memory as repository state;
  GitHub mutation without an exact human action authorization; merge authority.
- **Anti-patterns:** trusting a report because it is detailed; merging on `mergeable` alone; issuing two
  writers at once; accepting one finding at a time from an auditor; dispatching Astra for a candidate with no
  protected trigger or for discovery already proven; dispatching Sol for model diversity.

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
  test-generation, local validation and CI-diagnosis work of that same task.
- **Rules:** host effort label recorded literally — `xhigh` for ordinary complex implementation and repair,
  `max` only on an explicitly named capability-critical or hardest-correctness-critical trigger and never as a
  general default; thinking enabled and still proven from runtime evidence; runtime
  proof before mutation; one PR per semantic boundary; its self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`.
- **Read-only challenge:** `OPUS55_FRESH_READONLY_CHALLENGE` (section 24.4) — deep semantic bug finding,
  adversarial cases, accounting/numeric review, dependency tracing, test gaps and protected-boundary preflight in a
  fresh READ_ONLY context. It is `CHALLENGE_EVIDENCE_ONLY`: it finds blockers for the controller to adjudicate and
  never accepts; on Opus 5.5 work it is also `SELF_AUDIT_OR_SAME_MODEL_CHALLENGE_NOT_INDEPENDENT`.
- **Templates:** `opus5_prompting_playbook.md` section 3.

### 2.5 Codex GPT-5.6 Sol — reserve only

- **When:** only as `SOL_RESERVE_ONLY` (section 24.3) — the controller records a specific remaining capability gap
  that neither its connector/read-only work nor the routed Opus 5.5 task can close, and doctrine permits the
  task; typically the non-protected acceptance audit when the controller is ineligible under `NO_SELF_AUDIT`.
- **Rules:** host label `Ultra` recorded literally; not the default auditor, navigator, status or review lane;
  never dispatched for model diversity; never audits a candidate it implemented or repaired; never satisfies a
  protected audit.

### 2.6 GPT-6 Astra — sole protected auditor

- **Best tasks:** the protected audit and the one whole-contract protected re-audit of a candidate with at least
  one trigger of `ASTRA_PROTECTED_TRIGGER_MATRIX_V1`, including control-plane changes
  (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`); the same execution is the protected T4 `CLASS_C_CROSS_CONTRACT` audit and
  terminal decision. Never a non-protected candidate, never broad discovery already proven.
- **Rules:** `MODEL_ID_REQUIRED=gpt-6-astra`; host labels `Light` / `Medium` / `High` / `Extra High` / `Ultra`
  recorded literally; requested effort `Ultra`; `MODEL_FALLBACK=PROHIBITED`; thinking `ENABLED`; runtime proof on
  current-session evidence before substantive audit; never mutates, implements or repairs; complete material P1/P2
  collection over the protected cross-contract boundary under `AUDIT_MATERIALITY_BOUNDARY_V1` and
  `FINITE_AUDIT_RULE`, verifying independently every fact protected acceptance rests on. Input is a bounded
  `PROTECTED_AUDIT_PACKET_V1` on a stabilized head, never a chat-history recovery prompt. A first-audit P1/P2
  opens the one consolidated repair; a genuine P1/P2 remaining after the one re-audit rejects the candidate.
  Unavailability freezes the protected head and makes the gate wait; it never reassigns protected acceptance.

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
TASK_INTENT: AUDIT (CONTROLLER_INDEPENDENT_AUDIT_NONPROTECTED; controller-performed, not a dispatched prompt)
PRECONDITION: protected classification NONE recorded; controller (incl. ChatGPT Work) neither implemented nor
  repaired the candidate — otherwise route SOL_RESERVE_ONLY with the gap recorded
COVERAGE: fresh exact-head proof; every changed file; load-bearing dependencies; CI + review threads;
  supported-path adversarial reasoning; P1/P2/P3 materiality; scope and non-claims; determinism and fail-closed
OUTPUT: the COMPLETE current material P1/P2 set in one pass with evidence; P3 separately; zero mutation
```

```text
TASK_INTENT: CHALLENGE (OPUS55_FRESH_READONLY_CHALLENGE) — Claude Opus 5.5, fresh context, READ_ONLY
STATE_PIN: PR #<n> head <sha>, base <sha>; protected classification <letters|NONE>
FOCUS: <semantic bug finding | adversarial cases | accounting/numeric | dependency tracing | test gaps |
  protected-boundary preflight>
OUTPUT: every material P1/P2 found, with evidence, as CHALLENGE_EVIDENCE_ONLY; never an acceptance verdict;
  SELF_AUDIT_OR_SAME_MODEL_CHALLENGE_NOT_INDEPENDENT when Opus 5.5 implemented or repaired; zero mutation
```

```text
TASK_INTENT: AUDIT (ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1; protected; fresh context, READ_ONLY)
MODEL_RUNTIME_PROOF: MODEL_REQUESTED GPT-6 Astra | MODEL_ID_REQUIRED gpt-6-astra | MODEL_EFFORT_REQUESTED Ultra |
  MODEL_FALLBACK PROHIBITED | THINKING_REQUIRED ENABLED; prove on current-session evidence before auditing
PROTECTED_AUDIT_PACKET_V1: base/head/tree <shas>; changed files <exact>; protected triggers <letters>; critical
  claims needing Astra authority; load-bearing protected dependencies; controller preflight result; Opus
  challenge result or NONE; current CI; current review threads; unresolved P1/P2; exact protected acceptance
  questions. Doctrine and source by repository path and SHA; no chat-history recovery; missing evidence UNKNOWN.
SEMANTIC_BOUNDARY: the complete protected cross-contract boundary of PR #<n>; judge it, do not expand it
  (FINITE_AUDIT_RULE); verify independently every fact protected acceptance rests on; do not redo unrelated
  discovery the packet already proves
OUTPUT: the COMPLETE current material P1/P2 set in one pass, each with invariant, file:line evidence, supported
  entry/consumer path, effect, materiality and minimum regression proof (AUDIT_MATERIALITY_BOUNDARY_V1); P3
  separately; the protected Class-C and terminal verdict. Zero mutation.
```

```text
TASK_INTENT: REPAIR (the ONE consolidated repair) — Claude Opus 5.5
BLOCKER_INVENTORY: <the complete audited P1/P2 set, verbatim, with identities>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on the same branch; no new scope
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt
HANDOFF: AGENT_OS_HANDOFF_V1; this is the candidate's only repair
```

```text
TASK_INTENT: REAUDIT (the ONE whole-contract re-audit) — the same acceptance lane: GPT-6 Astra, effort Ultra, on a
  fresh PROTECTED_AUDIT_PACKET_V1 after the controller preflight for protected work; the controller (or the
  recorded SOL_RESERVE_ONLY substitute) for non-protected work
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
`NOT_READY`; current valid material P1/P2 threads block; the GPT-6 Astra audit as the sole protected acceptance;
post-merge verification; crypto_core-only scope; paper-first/fail-closed/deterministic rails; and the
validity of any open blocker until its own gates close it.
