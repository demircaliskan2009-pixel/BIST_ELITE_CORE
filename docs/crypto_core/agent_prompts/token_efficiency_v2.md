# Token Efficiency — Compact Prompt Lanes

<!-- CONTROL_PLANE_ROLE: COMPRESSION_GUIDE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **Compression guide, not authority.** This file compresses PROCEDURE TEXT. It never weakens a safety
> rule, never classifies a task, never selects an effort, never sizes a PR and never touches merge
> authority. All of those live in `docs/crypto_core/agent_os_v2.md`.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> The only top-level prompt template is `PROMPT_COMPILER_V2_1` (canonical section 5). Everything below
> is a compact way to FILL those twelve fields, never a replacement for them.

## 1. The compression rule

A prompt carries the TASK DELTA. Stable doctrine is loaded from the repository by the receiving agent.
Compressing a prompt means removing what the agent can read from a committed file — never removing a
guardrail, a stop condition, an invariant, an authorization boundary or a validation step.

If a compression would make an authority, an invariant or a stop condition less explicit, it is not a
compression. Stop and write the longer prompt.

## 2. What is always kept, at any length

- `TASK_INTENT` and `SEMANTIC_BOUNDARY` — what family, and what one contract closes.
- `STATE_PIN` — what the world must look like before mutation.
- `MODEL_RUNTIME_PROOF` — required identity and effort, and the stop on mismatch or fallback.
- `ALLOWED_FILES` — the exact mutation authorization boundary.
- `INVARIANTS` — paper-only, fail-closed, digest boundary, exact arithmetic, no hidden IO, no BIST.
- `VALIDATION_MATRIX` — the exact commands and when each runs.
- `GITHUB_AUTHORIZATION` — what is authorized, and explicitly what is not.
- `FORBIDDEN` and `STOP_CONDITIONS`.
- `HANDOFF` — the exact report packet expected back.

`BLOCKER_INVENTORY` may be `NONE`, but the field is still present. A field is never dropped to save
tokens; it is filled with `NONE` or `UNKNOWN`.

## 3. What is always dropped

- Repeated doctrine the agent loads from the repository.
- Greetings, apologies, filler, and "if you want I can continue" endings.
- Restated routing, restated family definitions and restated effort ladders — those are canonical.
- Full success logs. Failure tails only.
- Duplicate state the controller already proved and pinned, re-derived by the executor.
- Narration of routine commands.

## 4. Compact lane shapes

These are the shortest honest fillings for a lane that canonical routing already selected.

**Status.** Exact commands; expected output shape; terminal states only; the answer is the proven
state or `UNKNOWN`. No design latitude.

**Bounded read or closeout.** Exact read set or exact authorized command; the freshly re-proven
preconditions; the exact stop. A closeout prompt names the PR, the authorized head and the exact
command, and states that the authorization is spent once used.

**Bounded implementation.** Exact files, exact tests, explicit escalation triggers, explicit
no-scope-expansion. No architecture speculation, no repository archaeology, no long report format.

**Heavy implementation.** The complete dependency closure and negative cases up front; one writer;
default 0 subagents; the full validation ladder; the authorization gate to stop at. Detail:
`opus5_prompting_playbook.md`.

**Review.** Read-only, authorization explicitly none, exact source evidence per finding, severity
classified after discovery, any fix is a separate task.

**Architecture.** Read-only, produces a decision with candidates, trust boundaries, failure modes,
proven versus inferred versus `UNKNOWN`, and what would falsify the recommendation.

**Protected independent audit.** A controller-prepared narrow evidence packet: pinned base and head,
exact changes, direct dependencies, contract and invariants, protected risks, adversarial questions,
required report. Never the implementer's conclusions as premises.

**Preparation.** Read-only, pinned source revisions, the Work return contract verbatim, and an
explicit `WORK_PREPARED_NOT_AUTHORIZED` statement.

**Research.** One narrow current-fact question, primary sources first, every claim labelled as
verified external, verified repository, inference or `UNKNOWN`, and the result explicitly advisory.

## 5. Report compression

Fixed sections, evidence first: `RESULT`, proof, `FILES_CHANGED`, `VALIDATION`, blockers,
`NEXT_SAFE_ACTION`, and a token-budget assessment. Files read as compact bullets. Failure tails only.
No repeated doctrine, no filler, no uncited repository, PR or CI claim, and exactly one next safe
action stated once.

A compressed report still states the actual runtime identity and effort with an honest evidence class,
still separates evidence from inference from `UNKNOWN`, and still makes no self-audit claim.

## 6. Invariants

Token saving never outranks correctness, proof or a safety gate. Research economy never outranks
factual accuracy. No gate is skipped, no authorization is implied, no state is claimed from memory,
and no field of the canonical template is silently omitted.
