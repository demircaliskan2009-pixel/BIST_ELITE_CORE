# crypto_core Model Prompting Guide

Durable authoring guide for the active council of `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by
`ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1`, `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1` and
`CODEX_EXECUTOR_QUOTA_FALLBACK_V1` and `CRYPTO_CORE_AGENT_OS_HOST_AND_WORKFLOW_CLOSURE_V1` (`docs/crypto_core/agent_workflow.md` section 24 — the authority; this guide
teaches how to WRITE prompts for it and never overrides it). Claude prompt templates:
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`. Codex executor adapter:
`.codex/skills/crypto-core-executor-fallback/SKILL.md`. Research protocol:
`docs/crypto_core/deep_research_protocol.md`. On any conflict, section 24 and the stricter safety rule win. Nothing
in this guide proves repository state or authorizes a merge.

Active council (section 24.3): ChatGPT controller (read-only first, `CONTROLLER_READONLY_FIRST_POLICY`),
Claude Opus 5.5 (`claude-opus-5-5`), the conditional Codex executor (`CODEX_EXECUTOR_QUOTA_FALLBACK_V1`, adopted id
`gpt-6.2-astra`, routed only by an explicit controller selection), GPT-6.1 Sol (`gpt-6.1-sol`, the audit lane),
ChatGPT Work, Deep Research. Not routable, and never an automatic fallback: GPT-6 Astra
(`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`); Codex GPT-5.6 Sol (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`); Claude
Sonnet 5, Codex GPT-5.6 Terra and Codex GPT-5.6 Luna (`NOT_IN_ACTIVE_COUNCIL`); Claude Opus 5
(`SUPERSEDED_BY_OPUS_5_5`); Claude Opus 4.8 (`SUPERSEDED_BY_OPUS_5`); Claude Fable 5 (`INACTIVE_EXPIRED_RETIRED`);
Copilot (`INACTIVE_UNAVAILABLE`).
Copilot-era repository files are inactive compatibility material and never enter prompt construction.

## 1. Serious prompt shape

Every serious prompt uses the section 24.6 `SERIOUS_PROMPT_COMPILER` order: `TASK_INTENT`,
`SEMANTIC_BOUNDARY`, `STATE_PIN`, `MODEL_RUNTIME_PROOF`, `ALLOWED_FILES`, `INVARIANTS`, `BLOCKER_INVENTORY`,
`VALIDATION_MATRIX`, `GITHUB_AUTHORIZATION`, `FORBIDDEN`, `STOP_CONDITIONS`, `HANDOFF`. Authoring notes:

- `TASK_INTENT` comes first, one per prompt; never an implementation together with its own independent audit.
- `SEMANTIC_BOUNDARY` names the one contract the PR closes as the largest safe semantic closure (section
  24.8) — never a file-count or LOC target.
- `STATE_PIN` carries exact SHAs, branch, PR and open-PR count; the writer binds its local base/head/tree and clean status to the controller’s remote proof.
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
  it; keep the twelve top-level fields in their canonical order, with every required dynamic value inside its own
  field (state in `STATE_PIN`, runtime requests in `MODEL_RUNTIME_PROOF`, blocker identities in
  `BLOCKER_INVENTORY`); keep each field to the task-specific material it needs — no history replay, no giant logs
  (failure tails only), no redundant prose. Cache friendliness comes from stable doctrine and template references
  and minimal repeated prose, never from moving a required field; no prompt or report claims a cache hit or a
  measured saving.

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
- **Executor routing.** Put the attributable §24.3 A–G decisions in `MODEL_RUNTIME_PROOF` for this stage.
  For F, explain why the named writer can finish this scope and validation. Leave executing-session confirmation
  to the writer before mutation. Preserve the stage boundary, slot and interrupted-stage rules of §24.3.
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
- **Prompt:** name the contract, affected entry points, invariants and negative cases. Give the validation ladder
  and publication authority. Choose an offered Opus 5.5 setting under §24.12. Use the existing Opus playbook for
  implementation or the single consolidated repair.

### 2.5 GPT-6.2 Astra — conditional whole-stage executor

- **Prompt:** name the dependency chain, financial or authority boundary, and the negative case that would
  expose a broken link. For difficult repairs, supply the complete blocker set and require root-cause and
  regression evidence. Supply the same complete contract and validation, plus the §24.3 A–G controller record inside
  `MODEL_RUNTIME_PROOF`. For a CLI writer, name the literal config option and require proof this execution
  accepted it. For desktop, name the actual selector label and the §24.12 evidence path. Ask for the writer's
  separate session and checkout proof, then a scoped commit and exact-head handoff where authorized.
  [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

### 2.6 GPT-6.1 Sol — primary independent auditor (audit-only lane)

- **Best tasks:** the exhaustive fresh-context whole-contract audit and the one whole-contract re-audit of every
  serious candidate (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`); for protected work, including control-plane
  changes, the same execution is the protected T4 `CLASS_C_CROSS_CONTRACT` audit and terminal decision.
- **Bad tasks:** implementation, repair, routine GitHub status, CI polling, thread enumeration, repository
  archaeology and mechanical work — they belong to Claude or the controller and spend the allowance that buys
  independent judgment.
- **Rules:** `MODEL_ID_REQUIRED=gpt-6.1-sol` and thinking `ENABLED`; host labels written literally and never mapped
  (`Ultra` is never written as `max`). A protected audit requires `Ultra`, and an unexposed `Ultra` stops it for the
  controller to re-prove the host vocabulary; a non-protected audit requests `Ultra` by default and otherwise the
  available literal label the controller supplies, without that stop; `SPEED_MODE_DEFAULT=STANDARD`, Fast only on
  a recorded time-critical authorization and never as a correctness upgrade; `SOL_SUBAGENTS_DEFAULT=0`; runtime
  proof before substantive audit; never mutates; independence by lane and executing model id; complete material
  P1/P2 collection under `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE`. A first-audit P1/P2 opens the one
  consolidated repair, as does a `CI_GATE_BLOCKER` that a `REPAIR_ONLY` first audit independently confirms under
  `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` (§24.4; that mode never returns `ACCEPT`); a genuine P1/P2 remaining after the one re-audit rejects the candidate. Unavailability makes
  a protected gate wait on the frozen exact head; it never reassigns T4.
- **Efficiency (`SOL_AUDIT_USAGE_EFFICIENCY_V1`):** the prompt carries the controller's preflight packet inside its
  canonical fields; the
  auditor re-proves its head once, reads from the changed files outward, reuses green exact-head evidence instead
  of rerunning the full suite for duplication, runs the one re-audit delta-aware but whole-contract, and returns
  the `COMPACT_AUDIT_HANDOFF` with speed and usage telemetry when the host exposes them (`UNKNOWN` otherwise).

### Evaluation profiles outside the council

The controller may use these profiles to design a separate evaluation under §24.3. Each uses the same twelve
fields. Name fixed inputs, a verifiable outcome and allowed tools. These examples grant no candidate role.
Effort and speed for an evaluation must be supported on the exact host, with the selected literals and
runtime/thinking evidence reported separately. A prospective profile cannot authorize an evaluation run.

| Model and question | What to put in the prompt |
|---|---|
| GPT-6.2 Sol (`gpt-6.2-sol`), bounded implementation or repair | Use a non-protected historical fixture, explicit acceptance criteria, finite dependencies and a complete validation ladder. Ask for the smallest sufficient tool reads and one checked result. Compare total work through independent acceptance with the usual writer. Exclude open-ended architecture and financial trust boundaries. |
| GPT-6.2 Sol, independent non-protected audit | Use a different fixture with independently established material defects and clean paths. Withhold the answer key. Request one fresh-context, read-only whole-contract verdict with evidence for every blocker. Score misses and false findings, exclude every implementing/repairing ID, and examine shared-family misses. The production audit remains with §24.4. |
| GPT-6.1 Terra (`gpt-6.1-terra`), mechanical or visual evidence | Supply an exact image or UI state, permitted observations/actions, expected output and independently checkable reference. Require a stop on ambiguous or missing inputs. Keep ordinary GitHub verification with the controller. Exclude repository writing, governance and audit. |

### 2.7 Superseded lanes

GPT-6 Astra (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`) and Codex GPT-5.6 Sol
(`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`) are no crypto_core lane, default, fallback or dependency, and their
dated records are HISTORICAL. GPT-6.2 Astra (`gpt-6.2-astra`) is a different model id, routable only as the
conditional executor of section 2.5. The change that introduces GPT-6.1 Sol is accepted by the final legacy GPT-6
Astra audit under its accepted base (section 24.14 `GPT61_SOL_AUDIT_TRANSITION`). Neither superseded model ID
receives a new audit prompt.

## 3. Shared serious prompt

Use one instance of this template. Put stage-specific inputs in their existing fields.

```text
TASK_INTENT: <one routed stage>
SEMANTIC_BOUNDARY: <contract, supported paths and completion condition>
STATE_PIN: <repository, base, head/tree, PR state and source of the snapshot>
MODEL_RUNTIME_PROOF: <route, host selection, required id/thinking, execution proof per §24.12>
ALLOWED_FILES: <exact scope or READ_ONLY>
INVARIANTS: <task-specific invariants and standing rails by reference>
BLOCKER_INVENTORY: <inherited identities and exact evidence, or NONE>
VALIDATION_MATRIX: <required local checks, remote gates and owners>
GITHUB_AUTHORIZATION: <exact actions and limits>
FORBIDDEN: <standing rails and stage-specific exclusions>
STOP_CONDITIONS: <evidence failures, scope and authority boundaries>
HANDOFF: <§24.6 packet, specialist count and one next safe action>
```

- **Conditional implementation or repair:** under `MODEL_RUNTIME_PROOF` give the stage-specific A–G record,
  including F's basis. Ask for both that source and the actual pre-mutation proof in `HANDOFF`.
- **External decision:** put the §24.5 `APPROVAL_SOURCE_PACKET` in `STATE_PIN` and carry it into `HANDOFF`.
  Keep the direct grant and its limits in `GITHUB_AUTHORIZATION`. Link the exact accessible source to avoid
  replaying the surrounding conversation.
- **Audit:** place the §24.4 packet's check/thread snapshot in `STATE_PIN` and known findings in
  `BLOCKER_INVENTORY`. Request the complete material P1/P2 set in one read-only pass.
- **Consolidated repair:** supply that entire blocker set with the expected regression proof per defect.
- **Whole-contract re-audit:** supply both heads and inherited identities. Inspect the delta first, then the
  whole contract. Apply §24.8 to the result.
- **Root-cause escape:** the controller's architecture decision names the failed invariant, changed boundary
  and accepted starting point before a replacement implementation is routed.

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
validity of any open blocker until its own gates close it. The conditional Codex executor changes none of these:
it takes the replaced Claude stage's slot, never adds a slot or a repair, and never audits.
