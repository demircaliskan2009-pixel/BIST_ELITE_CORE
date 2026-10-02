# crypto_core Model Prompting Guide (v5, 2026-10-02 — GPT-6.1 Sol unified audit edition)

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by
`ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` and `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1`
(`docs/crypto_core/agent_workflow.md` section 24 — the authority; this guide teaches how to WRITE prompts for
it and never overrides it). Claude prompt templates: `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`.
Research protocol: `docs/crypto_core/deep_research_protocol.md`. On any conflict, section 24 and the stricter
safety rule win. Nothing in this guide proves repository state or authorizes a merge.

Active council (section 24.3): ChatGPT controller (read-only first, `CONTROLLER_READONLY_FIRST_POLICY`),
Claude Opus 5.5 (`claude-opus-5-5`), GPT-6.1 Sol (`gpt-6.1-sol`, the audit lane), ChatGPT Work, Deep Research.
Not routable, and never an automatic fallback: GPT-6 Astra (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`); Codex
GPT-5.6 Sol (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`); Claude Sonnet 5, Codex GPT-5.6 Terra and Codex GPT-5.6
Luna (`NOT_IN_ACTIVE_COUNCIL`); Claude Opus 5 (`SUPERSEDED_BY_OPUS_5_5`); Claude Opus 4.8
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
- Compact by reference (`PROMPT_COMPACTION_V1`, section 24.6): cite the repository doctrine instead of pasting
  it; keep the stable, reusable instructions first and byte-stable rather than reworded, and put the dynamic state
  — SHAs, PR, changed files, blocker identities, check and thread snapshots — last; never replay conversation
  history; failure tails only, no giant logs. This keeps shared prefixes cache-friendly, but no prompt or report
  claims a cache hit or a measured saving.

## 2. Lane-by-lane rules

### 2.1 ChatGPT controller

- **Owns:** routing; architecture adjudication; serious prompt compilation; evidence judgement and
  contradiction detection against live GitHub/terminal proof; `CONTROLLER_ACCEPTED_STATE`; merge-readiness
  judgement; exactly one next action.
- **Budget duty:** target the fewest specialist prompts (2 clean, 4 repaired, hard maximum 5) and count them
  per PR lifecycle (governance operations — state proof, CI/status
  reads, adjudication, merge-readiness, the authorization request, merge, post-merge verification, fresh-chat
  acceptance — do not count); never issue a specialist sixth; never hide specialist work inside governance; adjudicate a
  disputed severity under `AUDIT_MATERIALITY_BOUNDARY_V1` before applying `FIXED_POINT_STOP`; open a new attempt only through a `TASK_INTENT=ARCHITECTURE` `ROOT_CAUSE_ESCAPE` decision.
- **Audit routing and last-resort fallback:** route every independent audit to GPT-6.1 Sol (section 24.4) with the
  compact `SOL_AUDIT_PREFLIGHT_PACKET`. For a non-protected candidate only, when GPT-6.1 Sol is unavailable,
  quota-blocked or stopped by runtime proof — reason recorded — the controller audits as the last resort: the
  controller, including through ChatGPT Work, neither implemented nor repaired the candidate; fresh pinned-head
  READ_ONLY; complete blocker collection with evidence; zero mutation; never a protected audit. Protected work
  waits for GPT-6.1 Sol on the frozen exact head; GPT-6 Astra and Codex GPT-5.6 Sol are no fallback. No
  independent eligible reviewer → `STOP_WITH_PROOF`. Exception: the change that introduces this routing is
  audited under section 24 and the adapters of its base — the final legacy GPT-6 Astra audit — not its own text
  (section 24.14 `GPT61_SOL_AUDIT_TRANSITION`).
- **Usage duty (`SOL_AUDIT_USAGE_EFFICIENCY_V1`):** spend Sol allowance on independent judgment only — do every
  status read, CI poll, thread enumeration and preflight step around an audit yourself; never inflate an audit
  prompt; never narrow, shorten or fragment an audit to save allowance.
- **Never:** product implementation; any protected audit; an independent audit outside that fallback or of
  its own implementation or repair; a substitute for local tests; memory as repository state; GitHub mutation
  without an exact human action authorization; merge authority.
- **Anti-patterns:** trusting a report because it is detailed; merging on `mergeable` alone; issuing two
  writers at once; accepting one finding at a time from an auditor.

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
- **Templates:** `opus5_prompting_playbook.md` section 3.

### 2.5 GPT-6.1 Sol — primary independent auditor (audit-only lane)

- **Best tasks:** the exhaustive fresh-context whole-contract audit and the one whole-contract re-audit of every
  serious candidate (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`); for protected work, including control-plane
  changes, the same execution is the protected T4 `CLASS_C_CROSS_CONTRACT` audit and terminal decision.
- **Bad tasks:** implementation, repair, routine GitHub status, CI polling, thread enumeration, repository
  archaeology and mechanical work — they belong to Claude or the controller and spend the allowance that buys
  independent judgment.
- **Rules:** `MODEL_ID_REQUIRED=gpt-6.1-sol` and thinking `ENABLED`; host label `Ultra` written literally and
  mandatory for protected audits — when the selector does not expose `Ultra` the audit stops for the controller to
  re-prove the host vocabulary, and `Ultra` is never written as `max`; `SPEED_MODE_DEFAULT=STANDARD`, Fast only on
  a recorded time-critical authorization and never as a correctness upgrade; `SOL_SUBAGENTS_DEFAULT=0`; runtime
  proof before substantive audit; never mutates; independence by lane and executing model id; complete material
  P1/P2 collection under `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE`. A first-audit P1/P2 opens the one
  consolidated repair; a genuine P1/P2 remaining after the one re-audit rejects the candidate. Unavailability makes
  a protected gate wait on the frozen exact head; it never reassigns T4.
- **Efficiency (`SOL_AUDIT_USAGE_EFFICIENCY_V1`):** the prompt carries the controller's preflight packet; the
  auditor re-proves its head once, reads from the changed files outward, reuses green exact-head evidence instead
  of rerunning the full suite for duplication, runs the one re-audit delta-aware but whole-contract, and returns
  the `COMPACT_AUDIT_HANDOFF` with speed and usage telemetry when the host exposes them (`UNKNOWN` otherwise).

### 2.6 Superseded lanes

GPT-6 Astra (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`) and Codex GPT-5.6 Sol
(`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`) are no crypto_core lane, default, fallback or dependency, and their
dated records are HISTORICAL. The change that introduces GPT-6.1 Sol is accepted by the final legacy GPT-6 Astra
audit under the plane before it (section 24.14 `GPT61_SOL_AUDIT_TRANSITION`); no other Astra or GPT-5.6 Sol prompt
is written.

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
TASK_INTENT: AUDIT (GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1; exhaustive, fresh context, READ_ONLY) — GPT-6.1 Sol
  (gpt-6.1-sol), effort Ultra, speed STANDARD; for non-protected work only, the section 24.4 controller fallback
  with FALLBACK_REASON recorded
SEMANTIC_BOUNDARY: <the declared contract of PR #<n>>; judge it, do not expand it (FINITE_AUDIT_RULE)
STATE_PIN (SOL_AUDIT_PREFLIGHT_PACKET): PR #<n>; base <sha>; head <sha>; tree <sha|UNKNOWN>; changed files;
  required-check snapshot; review-thread snapshot; known P1/P2 identities; PROTECTED yes/no with the trigger
OUTPUT (COMPACT_AUDIT_HANDOFF): the COMPLETE current material P1/P2 set in one pass, each with invariant,
  file:line evidence, supported entry/consumer path, effect, materiality and minimum regression proof
  (AUDIT_MATERIALITY_BOUNDARY_V1); P3 separately; for protected work this one audit is also the protected Class-C
  verdict. Zero mutation.
```

```text
TASK_INTENT: REPAIR (the ONE consolidated repair) — Claude Opus 5.5
BLOCKER_INVENTORY: <the complete audited P1/P2 set, verbatim, with identities>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on the same branch; no new scope
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt
HANDOFF: AGENT_OS_HANDOFF_V1; this is the candidate's only repair
```

```text
TASK_INTENT: REAUDIT (the ONE whole-contract re-audit) — GPT-6.1 Sol, effort Ultra, speed STANDARD; for
  non-protected work only, the section 24.4 controller fallback with FALLBACK_REASON recorded
STATE_PIN (SOL_AUDIT_PREFLIGHT_PACKET): old head <sha>; repaired head <sha>; tree <sha|UNKNOWN>; the previous
  audit's blocker identities; BLOCKER_INVENTORY: <the repaired set>
OUTPUT (COMPACT_AUDIT_HANDOFF): delta-aware but whole-contract — OLD_HEAD..REPAIRED_HEAD first, then the whole
  contract — the COMPLETE current material P1/P2 set, not only the repaired lines. Any genuine material P1/P2 ->
  FIXED_POINT_STOP after controller severity adjudication; P3 never blocks.
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
`NOT_READY`; current valid material P1/P2 threads block; the GPT-6.1 Sol audit for protected work;
post-merge verification; crypto_core-only scope; paper-first/fail-closed/deterministic rails; and the
validity of any open blocker until its own gates close it.
