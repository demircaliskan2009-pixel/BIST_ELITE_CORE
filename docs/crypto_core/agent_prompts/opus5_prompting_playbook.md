# Heavy Local Implementation Prompting Playbook (Claude Opus 5)

<!-- CONTROL_PLANE_ROLE: AUTHORING_GUIDE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **Authoring guide, not authority.** This playbook is how to WRITE a prompt for the heavy local
> implementation lane once canonical routing has already selected it. It does not classify tasks into
> families, does not choose an effort, does not restate the routing matrix, and does not define PR
> sizing or merge authority. All of that lives in `docs/crypto_core/agent_os_v2.md`.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> The single top-level template is `PROMPT_COMPILER_V2_1` (canonical section 5): twelve fields, in
> order, for every serious prompt. The skeletons below are FILLINGS for those twelve fields. They are
> not an alternative template, and none of them may be used to argue a task into a different class.

## 1. What this lane is good at

The heavy local lane earns its cost on work with a real closure boundary: a multi-file semantic
feature, protocol semantics, a deterministic state machine, a fail-closed artifact, provenance logic,
a complex cross-module repair, or a long validation loop. It does not earn its cost on status,
polling, closeout mechanics, formatting, routine tests or simple documentation — canonical routing
sends those elsewhere, and a prompt that drags them here is a routing error, not a prompt style.

Write the prompt so that ONE turn can close the whole contract: precheck, bounded reads, the patch,
targeted validation, the final ladder, scoped commit, push, one PR, a bounded CI snapshot, and the
handoff — then a stop at the audit or authorization gate.

## 2. How to get maximum value

- **Close the contract up front.** Give the complete dependency closure and the negative cases in the
  prompt. The most common way this lane underperforms is being handed half a contract and having to
  stop and ask for the rest.
- **Name the exact allowed files.** `ALLOWED_FILES` is a mutation authorization boundary. Needing a
  path outside it is a stop-and-rescope, never a licence to widen and never a reason to shrink a
  coherent contract into pieces.
- **State the invariants as invariants.** Fail-closed conditions, digest boundaries, decimal
  arithmetic rules, paper-only flags, provenance requirements — written as things that must hold, with
  the exact failure path each one must take.
- **Give the validation ladder literally.** Exact commands, in order, and which run during development
  versus once on the final candidate bytes. Say explicitly that the full suite does not run after
  every edit.
- **State the authorization boundary.** What may be created, committed, pushed, opened. What may not.
  Where the turn must stop. Branch, commit, push and PR authorization is never merge authority.
- **Set the subagent policy explicitly.** Default 0. At most 2 read-only, and only for genuinely
  independent substantial investigation tracks, with no recursion and only the primary session
  mutating.
- **Ask for evidence, not reassurance.** Require proven state, exact changed files, command results,
  and `UNKNOWN` where a fact was not proven.

### What NOT to put in the prompt

- Vague repetition: "verify everything repeatedly", "double-check every step", "keep reviewing until
  it is perfect". Name the deterministic gates once instead.
- Ceremonial self-review loops. A local self-check is implementation QA and is labelled
  `SELF_AUDIT_ONLY_NOT_INDEPENDENT`; it never satisfies an independent audit, and asking for more of
  it does not change that.
- Authority-widening language: continue until done; keep fixing forever; retry until green; do
  everything automatically; approve your own work; merge when ready; ignore scope if necessary.
- Any request for hidden chain of thought.
- Pasted doctrine the agent can load from the repository.
- Any numeric change-size instruction. Sizing is semantic closure, decided by the controller before
  the prompt exists.

## 3. Behavior calibration to include in a mutation prompt

Include these as explicit expectations, because they change what the turn actually does:

- **Scope.** Deliver exactly the authorized task at the intended scope. Make routine implementation
  judgements independently. Never widen, narrow or transform the slice. When a materially better
  design would need scope expansion, report it and stop before mutating.
- **Decision commitment.** Select the strongest evidence-supported design and proceed. Reopen a
  settled decision only when new repository or test evidence directly contradicts it.
- **Narration.** One concise sentence before the first tool call, then only material findings,
  blockers, direction changes and phase transitions. No routine-command narration.
- **Self-correction.** Correct an earlier statement only when the error changes code, conclusions,
  authorization or the next action. Fix non-material slips silently.
- **Verification.** Run each deterministic gate once per unchanged evidence key. Rerun only after a
  relevant mutation or invalidating evidence.
- **Output.** Compact and evidence-dense: decisions, evidence, commands and results, blockers.

## 4. Skeletons

Each skeleton fills the twelve canonical fields. `TASK_INTENT` is copied from the controller's
classification — the skeleton never chooses it. Effort is likewise copied from canonical routing and
is never argued for inside the prompt.

### 4.1 Implementation skeleton

```text
TASK_INTENT:        <copied from the controller's classification>
SEMANTIC_BOUNDARY:  <the one coherent contract this PR closes, named>
STATE_PIN:          repo; expected base SHA and tree; expected open-PR count; branch to create
MODEL_RUNTIME_PROOF: required identity and effort; evidence class; fallback not allowed; stop on mismatch
ALLOWED_FILES:      <exact create / modify / delete inventory>
INVARIANTS:         paper-only; fail-closed with explicit reason; digest recompute through the public
                    serializer before READY/ADMITTED/ACCEPTED; exact decimal arithmetic; no hidden IO,
                    env, randomness, clock or threading; no BIST; protected surfaces byte-unchanged
BLOCKER_INVENTORY:  <known blockers this task must close, with their stable ids; or NONE>
VALIDATION_MATRIX:  targeted during development; then once on the final bytes: <exact ordered commands>
GITHUB_AUTHORIZATION: create the named branch; modify only the allowed scope; scoped add; one commit;
                    normal push; create exactly one PR; poll natural CI to terminal.
                    NOT authorized: merge, auto-merge, branch deletion, force push, rebase, squash,
                    workflow rerun or dispatch, review approval, thread mutation.
FORBIDDEN:          <the explicit non-goals for this slice>
STOP_CONDITIONS:    state moved; open PR exists; pre-existing tracked dirt; runtime contract failed;
                    scope exceeds allowed files; product or BIST mutation required; new dependency or
                    workflow required; unrelated suite failure needing out-of-scope repair;
                    authorization gate reached
HANDOFF:            <the exact report packet expected back>
```

### 4.2 Repair skeleton

Same twelve fields, with these differences: `SEMANTIC_BOUNDARY` is the blocker set being closed, by
stable id; `BLOCKER_INVENTORY` is the COMPLETE current set from one whole-contract audit, not the
first finding; the branch is the SAME branch as the PR under repair; and the contract is ONE
consolidated repair followed by ONE whole-contract reaudit. State that a remaining genuine P1/P2
after that reaudit is `FIXED_POINT_NOT_REACHED` and freezes the contract, and that renaming a blocker
does not reset its repair counter.

Default to test-only. If production code must change, require a new failing test that proves the
defect first, and require proof that a test-only repair left product code untouched.

### 4.3 Review skeleton

Read-only. `GITHUB_AUTHORIZATION` is explicitly none, and the prompt says so. Require every finding to
carry exact source evidence and a reproducible failure, severity classified AFTER discovery rather
than filtered during it, and blockers separated from non-blockers. State that any resulting fix is a
separate, explicitly created task — a review turn never patches.

### 4.4 Architecture skeleton

Read-only, and it produces a DECISION, not a diff. Require: the candidates actually considered; the
trust boundaries and the producer/consumer graph each one implies; the failure modes; what is proven
versus inferred versus `UNKNOWN`; the recommended option with its reason; and what would falsify the
recommendation. State that the controller owns the decision.

### 4.5 Prompt-architecture skeleton

The output is one compiled prompt in canonical `PROMPT_COMPILER_V2_1` form and nothing else. Require
that it carries all twelve fields in order, invents no authority, pastes no doctrine the target can
load, requests no hidden reasoning, and ends at an explicit stop. State that the controller owns the
compiler and the final prompt.

## 5. Context and token efficiency

- Name the read set. Expand only on progressive disclosure: an unresolved reference, an invariant that
  crosses modules, a test-exposed dependency, or architecture that cannot be proven locally.
- Never instruct a broad repository read by default. Never ask for every historical lesson, unrelated
  modules, stale archives, old prompts or generated output.
- Pin exact SHAs, branch, PR head, file paths, digests, tests and the proven open-PR count in the
  prompt rather than relying on conversational memory.
- Summarize successful logs; retain failure tails.
- Require exactly one next safe action at the end. No settlement or confirmation loops.

## 6. Non-regression

Nothing in this playbook narrows, renames, renumbers or absorbs a canonical lane; classifies a task;
selects a canonical effort; grants any authority; weakens a gate; or introduces a second top-level
prompt template. Protected Class-C work always goes to the protected frontier lane named in canonical
section 3.3, and no local session and no same-model second pass satisfies it.
