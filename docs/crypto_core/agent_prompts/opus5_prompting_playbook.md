# Claude Opus 5 Prompting Playbook (crypto_core, v3 — Astra unified audit edition)

How to prompt the one active Claude lane under `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by
`ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1`. Authority:
`docs/crypto_core/agent_workflow.md` section 24 — council 24.3, audit 24.4, prompt shape 24.6, lifecycle and
budget 24.8, runtime proof 24.12. This playbook never overrides it; on any conflict, section 24 and the
stricter safety rule win.

**Claude Opus 5** (`claude-opus-5`) is the primary deep semantic IMPLEMENTATION and REPAIR lane. Claude Sonnet
5 is `NOT_IN_ACTIVE_COUNCIL`, Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5`, and Claude Fable 5 is
`INACTIVE_EXPIRED_RETIRED`; none is a lane, fallback or dependency. Nothing here proves repository state,
grants merge authority, or satisfies an independent or protected audit.

---

## 1. Runtime proof and effort

- **Runtime proof before mutation.** Report `MODEL_REQUESTED`, `MODEL_ID_REQUIRED`, `MODEL_ACTUAL`,
  `MODEL_EFFORT_REQUESTED`, `MODEL_EFFORT_ACTUAL`, `MODEL_FALLBACK`, `THINKING_ACTUAL`,
  `MODEL_IDENTITY_EVIDENCE` and `MODEL_EFFORT_EVIDENCE` from session evidence (runtime metadata, `/model`,
  `/status`, or an equivalent diagnostic). A selector, settings file, default, cache, request text or the bare
  alias `opus` is not execution proof. `MODEL_ACTUAL` must positively be `claude-opus-5` and `THINKING_ACTUAL`
  positively `ENABLED`; either one `UNKNOWN` stops. Only `MODEL_EFFORT_ACTUAL` may be `UNKNOWN` when the host
  exposes no effort telemetry, and it is never restated from the request.
- **Literal host label.** The Opus 5 host effort label is `xhighultracode`. It is recorded verbatim, never
  decomposed, never mapped to an API effort enum, and never equated with `max` or with another model's label.
- **Thinking.** Adaptive thinking stays enabled for implementation and repair. Control cost through scope and
  context, never by suppressing reasoning.
- **Stops.** A wrong or `UNKNOWN` model, `UNKNOWN` or disabled required thinking, or a known prohibited fallback
  is `STOP_WITH_PROOF` before mutation. A human may waive an effort mismatch for one task; the waiver and the
  true actual effort are both recorded.
- **De-escalation.** Effort follows the work: when the remaining work is narrower than expected, the controller
  routes it to a lighter setting or lane rather than finishing at the original one.

---

## 2. How to prompt Opus 5 for maximum value

A strong Opus 5 prompt gives the complete semantic boundary up front and lets the model finish the loop. It
follows the section 24.6 serious prompt shape:

1. **TASK_INTENT** — `IMPLEMENTATION` or `REPAIR`.
2. **SEMANTIC_BOUNDARY** — the one coherent contract to close as the largest safe semantic closure, including
   what "done" means; never a file-count or LOC ceiling.
3. **STATE_PIN** — the fresh facts that must be proven before mutation.
4. **MODEL_RUNTIME_PROOF** — the section 24.12 fields.
5. **ALLOWED_FILES** — the exact files; prohibited surfaces named.
6. **INVARIANTS** — the properties that must remain true.
7. **BLOCKER_INVENTORY** — inherited blocker identities; for a repair, the complete audited P1/P2 set.
8. **VALIDATION_MATRIX** — targeted, full, wrapper and CI requirements.
9. **GITHUB_AUTHORIZATION** — commit, push, PR and merge stated separately.
10. **FORBIDDEN** and **STOP_CONDITIONS** — every state that must halt mutation.
11. **HANDOFF** — `AGENT_OS_HANDOFF_V1`, compact, with the meaningful-prompt count and one next safe action.

### What NOT to do

- Do not write only "do everything", or ask for maximum thinking without a bounded objective.
- Do not give conflicting instructions or request repeated generic self-checks.
- Do not mix historical state with current facts, or ask Opus to infer live repository state.
- Do not ask for several competing prompts when one best contract is required.
- Do not hide merge authority inside a general permission.
- Do not split one coherent contract into micro-PRs, and do not feed a repair one finding at a time.
- Do not widen scope with "improve anything else you find".

### Behavior calibration to include in Opus mutation prompts

- **Scope:** close the whole declared semantic boundary; make routine implementation judgements
  independently; do not widen, narrow or transform it; when a materially better architecture requires scope
  expansion, report it and stop before unauthorized mutation.
- **Claim minimization:** add no validator, registry, filesystem or host-discovery layer, schema, dependency or
  process the declared contract does not require (section 24.13).
- **Decision commitment:** select the strongest evidence-supported design and proceed; reopen a settled design
  decision only when new repository or test evidence directly contradicts it.
- **Progress narration:** one concise sentence before the first tool call; afterwards only material findings,
  blockers, direction changes and phase transitions.
- **Verification:** run each deterministic gate once per unchanged head; rerun only after a relevant mutation
  or invalidating evidence.
- **Subagents:** default 0; at most 2 read-only subagents for genuinely independent, substantial,
  parallelizable investigation; only one agent mutates a branch, and the primary agent validates every
  subagent conclusion.
- **Independence:** a same-model self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`; the independent audit is
  GPT-6 Astra as PRIMARY, which for protected work is also the protected audit (section 24.4); Codex GPT-5.6 Sol
  and then the ChatGPT controller are recorded fallbacks for non-protected work only.

---

## 3. Reusable prompt templates

Placeholders are `<angle-bracketed>`.

### 3.1 `OPUS5_IMPLEMENTATION`

Use for the first implementation prompt of a PR lifecycle (meaningful prompt 1).

```text
TASK_INTENT: IMPLEMENTATION
SEMANTIC_BOUNDARY: <one coherent contract, closed as the largest safe semantic closure: dependency closure,
  negative cases, tests, docs/provenance genuinely required, validation>
STATE_PIN: main @ <sha>; clean worktree; <n> open PRs; branch <name> absent
MODEL_RUNTIME_PROOF: MODEL_REQUESTED Claude Opus 5 | MODEL_ID_REQUIRED claude-opus-5 |
  MODEL_EFFORT_REQUESTED <literal host label> | MODEL_FALLBACK NONE | THINKING ENABLED |
  report MODEL_ACTUAL, MODEL_EFFORT_ACTUAL, THINKING_ACTUAL, MODEL_IDENTITY_EVIDENCE, MODEL_EFFORT_EVIDENCE
  before mutation; MODEL_ACTUAL or THINKING_ACTUAL UNKNOWN -> STOP_WITH_PROOF; MODEL_EFFORT_ACTUAL may be UNKNOWN
ALLOWED_FILES: <exact files>
INVARIANTS: <fail-closed / digest / paper-only / determinism properties>
BLOCKER_INVENTORY: <inherited blocker identities, or NONE>
VALIDATION_MATRIX: python -m ruff check <paths>; python -m ruff format --check <paths>;
  targeted tests via scripts/crypto_core/run_logged_command.ps1;
  powershell -File scripts/crypto_core/run_full_tests_logged.ps1 (PYTEST_EXIT=0); git diff --check;
  exact changed-file proof
GITHUB_AUTHORIZATION: branch, exact-path stage, one commit, push, one PR AUTHORIZED; merge NOT AUTHORIZED
FORBIDDEN: scope widening; product surfaces outside scope; direct main push; force-push; broad git add;
  self-approval; auto-merge; live/private API; orders; scheduler; BIST
STOP_CONDITIONS: runtime-proof failure; dirty tree; head mismatch; open-PR collision; out-of-scope failure;
  readiness/connector transition; external-fact dependency; authorization gate
HANDOFF: AGENT_OS_HANDOFF_V1; MEANINGFUL_PROMPT_COUNT_THIS_PR: 1; one next safe action
```

### 3.2 `OPUS5_ONE_CONSOLIDATED_REPAIR`

Use only for the single consolidated repair after an exhaustive independent audit (meaningful prompt 3).
Never for a candidate under `FIXED_POINT_STOP`, never for a second repair, never for one finding at a time.

```text
TASK_INTENT: REPAIR (the ONE consolidated repair of this candidate)
BLOCKER_INVENTORY: <the COMPLETE audited P1/P2 set, verbatim, with blocker identities and evidence>
SEMANTIC_BOUNDARY: repair the complete set by root cause in one change on branch <branch> at head <sha>;
  the original contract is unchanged except for the defects; no opportunistic cleanup
STATE_PIN: PR <n> OPEN; head <sha> == local == origin; base <sha>
MODEL_RUNTIME_PROOF: <as 3.1>
ALLOWED_FILES: <exact files>; no new files unless named
VALIDATION_MATRIX: a regression proof for every blocker that fails before and passes after; then the full
  ladder of 3.1
GITHUB_AUTHORIZATION: one normal same-branch commit and push AUTHORIZED; new PR FORBIDDEN; amend/force
  FORBIDDEN; merge NOT AUTHORIZED; resolving review threads FORBIDDEN
STOP_CONDITIONS: a blocker cannot be reproduced; the repair needs files or authority outside the prompt; the
  finding disputes accepted design; head moved
HANDOFF: AGENT_OS_HANDOFF_V1 with before/after evidence per blocker; MEANINGFUL_PROMPT_COUNT_THIS_PR: 3;
  next = the ONE whole-contract re-audit
```

---

## 4. Context and token efficiency

**Minimum sufficient context.** Read the authoritative setup files, the directly affected production/test
files, the immediate dependency interfaces, and the relevant current PR/main evidence. Do not automatically
read the whole repository, every historical lesson, unrelated modules, stale archives, old prompts, or
generated output.

**Progressive disclosure.** Start with a narrow search. Expand only when a reference is unresolved, an
invariant crosses modules, a test exposes a dependency, or architecture cannot be proven locally — and say why
the expansion was necessary.

**Context pins.** Use exact values: main SHA, branch, PR head, file paths, profile ids, digests, tests, and the
current open-PR count. Never rely on conversational memory for live repository state.

**Report compression.** Keep full evidence in a temporary handoff file when it is long; return a compact
evidence block. Failure tails only, never full success logs.

**Tool-call efficiency.** Run one command at a time when command causality matters; batch only independent
read-only queries. Do not rerun a passed gate unless the relevant files changed, the head changed, or new
evidence invalidated it.

---

## 5. Non-regression

This playbook changes prompt construction only. It does not weaken any gate: one repository writer and one
open PR at a time; no direct `main` push; standard merge only; no self-approval and no auto-merge; explicit
per-PR, exact-head human merge authorization; pending CI is `NOT_READY`; current valid material P1/P2 threads
block; protected work always gets the GPT-6 Astra audit, which no Claude lane, Sol review, controller review or
self-review satisfies; post-merge verification precedes the next action; crypto_core scope only — no BIST, live or private
API, credentials, orders, scheduler/auto-loop, shadow/live execution, or capital mutation.

**Temporary availability is never durable routing.** Model quota, rate limits or short-term unavailability are
transient operational facts: record them in the controller handoff for that one task, where a GPT-6 Astra
outage may justify the section 24.4 non-protected audit fallback for that task only. Never write a temporary
availability state into this playbook or into `agent_workflow.md`, and never infer from a quota event that a
lane has been retired. When GPT-6 Astra is unavailable, the protected gate waits.
