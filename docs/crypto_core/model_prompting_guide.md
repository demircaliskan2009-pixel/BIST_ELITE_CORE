# crypto_core Model Prompting Guide (v4, 2026-09-15 — Astra unified audit edition)

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by
`ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1`
(`docs/crypto_core/agent_workflow.md` section 24 — the authority; this guide teaches how to WRITE prompts for
it and never overrides it). Claude prompt templates: `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`.
Research protocol: `docs/crypto_core/deep_research_protocol.md`. On any conflict, section 24 and the stricter
safety rule win. Nothing in this guide proves repository state or authorizes a merge.

Active council (section 24.3): ChatGPT controller (read-only first, `CONTROLLER_READONLY_FIRST_POLICY`),
Claude Opus 5 (`claude-opus-5`), Codex GPT-5.6 Sol, GPT-6 Astra, ChatGPT Work, Deep Research. Not routable:
Claude Sonnet 5, Codex GPT-5.6 Terra and Codex GPT-5.6 Luna (`NOT_IN_ACTIVE_COUNCIL`); Claude Opus 4.8
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
- **Budget duty:** target the fewest specialist prompts (2 clean, 4 repaired, hard maximum 5) and count them
  per PR lifecycle (governance operations — state proof, CI/status
  reads, adjudication, merge-readiness, the authorization request, merge, post-merge verification, fresh-chat
  acceptance — do not count); never issue a specialist sixth; never hide specialist work inside governance; adjudicate a
  disputed severity under `AUDIT_MATERIALITY_BOUNDARY_V1` before applying `FIXED_POINT_STOP`; open a new attempt only through a `TASK_INTENT=ARCHITECTURE` `ROOT_CAUSE_ESCAPE` decision.
- **Audit routing and last-resort fallback:** route every independent audit to GPT-6 Astra (section 24.4). For
  a non-protected candidate only, route it to Codex Sol when Astra is unavailable, quota-blocked or stopped by
  runtime proof, or by explicit selection, recording the reason; the controller audits only as the last resort
  when Sol cannot legally audit — reason recorded; the controller, including through ChatGPT Work, neither
  implemented nor repaired the candidate; fresh pinned-head READ_ONLY; complete blocker collection with evidence;
  zero mutation; never a protected audit. Protected work waits for Astra. No independent eligible reviewer →
  `STOP_WITH_PROOF`. Exception: the change that introduces this routing is audited under section 24 and the
  adapters of its base, not its own text (section 24.14 transition).
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

### 2.4 Claude Opus 5 — deep semantic implementation and repair

- **Best tasks:** complex semantic implementation, fail-closed artifact design, cross-module integration,
  forensic debugging with long validation loops, and the single consolidated repair of a candidate.
- **Rules:** host effort label recorded literally (`xhighultracode`); adaptive thinking enabled; runtime
  proof before mutation; one PR per semantic boundary; its self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`.
- **Templates:** `opus5_prompting_playbook.md` section 3.

### 2.5 Codex GPT-5.6 Sol — engineering accelerator and non-protected audit fallback

- **Best tasks:** repo navigation, code search, dependency tracing, static inspection, clear-spec implementation
  when specifically routed, mechanical refactor, test generation, debugging, CI analysis and large-codebase
  inspection; an audit or re-audit only as the recorded `NON_PROTECTED_AUDIT_FALLBACK` (section 24.4).
- **Rules:** host label `Ultra` recorded literally; not the default independent auditor; never audits a candidate
  it implemented or repaired; never satisfies a protected audit.

### 2.6 GPT-6 Astra — primary independent auditor

- **Best tasks:** the exhaustive independent audit and the one whole-contract re-audit of every serious candidate
  (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`); for protected work, including control-plane changes, the same execution
  is the protected T4 `CLASS_C_CROSS_CONTRACT` audit and terminal decision.
- **Rules:** host labels `Light` / `Medium` / `High` / `Extra High` / `Ultra` recorded literally; default requested
  effort `Ultra`; runtime proof before substantive audit; never mutates, implements or repairs; complete material
  P1/P2 collection under `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE`. A first-audit P1/P2 opens the one
  consolidated repair; a genuine P1/P2 remaining after the one re-audit rejects the candidate. Unavailability makes
  a protected gate wait; it never reassigns T4.

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
TASK_INTENT: AUDIT (ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1; exhaustive, fresh context, READ_ONLY) — GPT-6 Astra,
  effort Ultra; for non-protected work only, the section 24.4 fallback lane with FALLBACK_REASON recorded
SEMANTIC_BOUNDARY: <the declared contract of PR #<n>>; judge it, do not expand it (FINITE_AUDIT_RULE)
STATE_PIN: PR #<n> head <sha>, base <sha>; PROTECTED yes/no with the trigger
OUTPUT: the COMPLETE current material P1/P2 set in one pass, each with invariant, file:line evidence, supported
  entry/consumer path, effect, materiality and minimum regression proof (AUDIT_MATERIALITY_BOUNDARY_V1); P3
  separately; for protected work this one audit is also the protected Class-C verdict. Zero mutation.
```

```text
TASK_INTENT: REPAIR (the ONE consolidated repair) — Claude Opus 5
BLOCKER_INVENTORY: <the complete audited P1/P2 set, verbatim, with identities>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on the same branch; no new scope
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt
HANDOFF: AGENT_OS_HANDOFF_V1; this is the candidate's only repair
```

```text
TASK_INTENT: REAUDIT (the ONE whole-contract re-audit) — GPT-6 Astra, effort Ultra; for non-protected work only,
  the section 24.4 fallback lane with FALLBACK_REASON recorded
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
