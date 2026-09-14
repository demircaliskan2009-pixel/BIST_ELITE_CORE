# crypto_core Model Prompting Guide (v3, 2026-09-14 — minimal kernel edition)

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1`
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
- `MODEL_RUNTIME_PROOF` carries the section 24.12 fields, with the host label written literally.
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
- **Budget duty:** count meaningful prompts per PR lifecycle (status reads do not count); never issue a sixth;
  apply `FIXED_POINT_STOP`; open a new attempt only through a `TASK_INTENT=ARCHITECTURE` `ROOT_CAUSE_ESCAPE`
  decision.
- **Never:** product implementation; an ordinary or protected independent audit; a substitute for local
  tests; memory as repository state; GitHub mutation without an exact human action authorization; merge
  authority.
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

### 2.5 Codex GPT-5.6 Sol — engineering accelerator and ordinary independent reviewer

- **Best tasks:** repo navigation, code search, dependency tracing, clear-spec implementation where routed,
  mechanical refactor, test generation, static inspection, debugging, CI analysis, and ordinary independent
  large-codebase review — including the exhaustive audit and the one whole-contract re-audit.
- **Rules:** host label `Ultra` recorded literally; never audits work it implemented in the same context; an
  ordinary Sol review never satisfies protected Class C.

### 2.6 GPT-6 Astra — protected T4 terminal audit

- **Best tasks:** protected T4 `CLASS_C_CROSS_CONTRACT` READ_ONLY terminal frontier audit on the section 24.4
  protected triggers, including control-plane changes.
- **Rules:** host labels `Light` / `Medium` / `High` / `Extra High` / `Ultra` recorded literally; default
  protected effort `Extra High` or `Ultra` per controller task, `Ultra` for setup/control-plane terminal
  audits; never mutates; a genuine P1/P2 it finds rejects the candidate. Unavailability makes the gate wait;
  it never reassigns T4.

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
TASK_INTENT: AUDIT (exhaustive, fresh context, READ_ONLY) — Codex GPT-5.6 Sol
SEMANTIC_BOUNDARY: <the declared contract of PR #<n>>; judge it, do not expand it
STATE_PIN: PR #<n> head <sha>, base <sha>
OUTPUT: the COMPLETE current P1/P2 set in one pass, each with file:line evidence and a failure scenario;
  P3 separately; PROTECTED_CLASS_C_REQUIRED yes/no with the trigger. Zero mutation.
```

```text
TASK_INTENT: REPAIR (the ONE consolidated repair) — Claude Opus 5
BLOCKER_INVENTORY: <the complete audited P1/P2 set, verbatim, with identities>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on the same branch; no new scope
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt
HANDOFF: AGENT_OS_HANDOFF_V1; this is the candidate's only repair
```

```text
TASK_INTENT: REAUDIT (the ONE whole-contract re-audit) — Codex GPT-5.6 Sol
STATE_PIN: repaired head <sha>; BLOCKER_INVENTORY: <the repaired set>
OUTPUT: the COMPLETE current P1/P2 set of the whole contract. Any genuine P1/P2 -> FIXED_POINT_STOP.
```

```text
TASK_INTENT: TERMINAL_AUDIT (protected T4 CLASS_C_CROSS_CONTRACT, READ_ONLY) — GPT-6 Astra, effort <literal>
STATE_PIN: PR #<n> head <sha>; prior audit verdicts <...>
OUTPUT: ACCEPT or REJECT with the complete P1/P2 set; a genuine P1/P2 rejects the candidate (no repair).
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
`NOT_READY`; current valid P1/P2 threads block; the protected Astra terminal audit for protected work;
post-merge verification; crypto_core-only scope; paper-first/fail-closed/deterministic rails; and the
validity of any open blocker until its own gates close it.
