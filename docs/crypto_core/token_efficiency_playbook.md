# Token Efficiency Playbook

<!-- CONTROL_PLANE_ROLE: COMPRESSION_GUIDE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **Compression guide, not authority.** Context budgets and economy rules only. This file classifies
> no task, selects no effort, sizes no PR and touches no merge authority — all of that lives in
> `docs/crypto_core/agent_os_v2.md`.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> Token saving is always subordinate to correctness, proof and safety gates. No economy rule below may
> be used to skip a gate, shorten a validation ladder, or soften an authorization boundary.

## 1. Context budget classes

Budgets attach to the lane canonical routing selected; they never redefine it.

- **MINIMAL** — mechanical and fast-bounded work. Exact commands and named files only. No exploration.
- **BOUNDED** — bounded implementation and focused review. Named files plus the immediate dependency
  interfaces.
- **BROAD_BUT_BOUNDED** — heavy implementation, broad review, architecture, prompt architecture and
  protected audit. The authoritative setup files, the directly affected production and test files, the
  immediate dependency interfaces, and the relevant current PR and base evidence.

Never automatically read the whole repository, every historical lesson, unrelated modules, stale
archives, old prompts or generated output. Expand only on progressive disclosure: an unresolved
reference, an invariant that crosses modules, a test-exposed dependency, or architecture that cannot
be proven locally.

Pin exact SHAs, branch, PR head, file paths, digests, tests and the proven open-PR count. Never rely
on conversational memory for live state.

## 2. Controller preprocessing is the primary saver

The single largest token saving is the controller preparing pinned evidence and an exact contract so
the executor does not repeat broad discovery. An executor that re-derives what the controller already
proved pays twice for the same fact and risks disagreeing with it.

So: consume the packet; do not rediscover changed files; do not re-prove PR metadata the connector
proved; do not poll CI with reasoning tokens. But DO independently prove the local facts that safe
mutation requires — working tree, branch, head, and test results. Local proof is never delegated.

## 3. Evidence reuse

Run each expensive deterministic gate ONCE per unchanged evidence key. The key is: head and tree, the
relevant path set, the command and its configuration, the environment and toolchain, and the evidence
id.

Invalidate on a new commit, a relevant configuration change, an environment or toolchain change, a new
failure, or an evidence-integrity problem. Targeted tests during development; the required full ladder
once on the final candidate bytes. Do not run the full suite after every edit, and do not rerun a
successful CI run for ceremony. A semantic failure is repaired, not rerun.

## 4. Report compression

Fixed sections, evidence first: result, proof, files changed, validation, blockers, exactly one next
safe action, and a token-budget assessment. Files read as compact bullets. Failure tails only, never
full success logs. No repeated doctrine, no filler, no uncited repository, PR or CI claim, and no
settlement or confirmation loop.

A compressed report still carries the actual runtime identity and effort with an honest evidence
class, still separates evidence from inference from `UNKNOWN`, and still makes no self-audit claim.

## 5. Model economy

Select the lowest lane that safely proves correctness, per canonical routing. Selection inputs are:
safety class, semantic complexity, required repository breadth, independence requirement, expected
prompt count, expected repair probability, availability, and measured cost in the current harness —
never an unsupported hard-coded price ranking, and never model prestige.

Strong reasoning does not improve a status snapshot, an already-authorized merge, a configuration edit
or a mechanical fixture, and spending it there costs latency and budget for no correctness gain. The
inverse error is worse: a cheap lane on protected work is not economy, it is an unproven gate.

Temporary availability, quota and billing state for any vendor is transient operational information
recorded in a handoff for that task only. It never changes a durable role and is never written into
this playbook.

## 6. Prompt-count economy

Few prompts, maximum completed safe work. One coherent contract is one implementation prompt, then an
independent audit, then at most one consolidated repair before one whole-contract reaudit. Never split
a coherent implementation into micro-prompts unless a stop condition is actually reached, and never
combine an implementation with its own independent audit, a merge with the next feature, unrelated
slices, setup with product code, research with mutation, two implementers, or two PRs.

## 7. Anti-patterns

Broad recursive scans without justification · full log dumps · repeated doctrine in every prompt ·
status or CI polling with expensive reasoning tokens · re-reading unchanged surfaces · duplicate
self-review passes dressed as verification · rerunning a green gate for reassurance · narrating
routine commands · asking the user to confirm what the prompt already authorized · producing an
artifact that proves no new load-bearing fact and removes no repeated future work.

## 8. Non-regression

No budget, compression or economy rule in this file skips a validation gate, weakens a fail-closed
invariant, implies an authorization, substitutes a cheaper lane for a protected audit, or permits a
state claim without proof. Where economy and proof conflict, proof wins.
