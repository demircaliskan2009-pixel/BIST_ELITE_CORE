---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core independent audits and re-audits routed to the active Sol auditor (GPT-6.1 Sol, or GPT-6.2 Sol only after its named activation) on the Codex or ChatGPT Work host, including protected T4 audits and the authorized GPT-6.2 Sol qualification, under strict READ_ONLY, paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow (Sol audit lane)

Use this skill only for `crypto_core` work in BIST_ELITE_CORE. Authority: `AGENTS.md` →
`docs/crypto_core/agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`, active content
`MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by the amendments its header lists) → this adapter, which
restates no authority. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2): specialized institutional crypto trading systems
engineering — paper-first, deterministic, fail-closed, audit-first — never generic coding.

## Lane (section 24.3)

- The `ACTIVE_SOL_AUDITOR` (section 24.3) is the PRIMARY independent auditor (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`,
  section 24.4): the fresh-context whole-contract audit and the one whole-contract re-audit of every serious
  candidate, and for protected work the sole protected T4 `CLASS_C_CROSS_CONTRACT` audit in the same execution. Its
  id is the one the controller resolves under section 24.7 `SOL_ROUTE_STATE_RESOLUTION`: **GPT-6.1 Sol**
  (`gpt-6.1-sol`) for `PRE_ACTIVATION_VERIFIED`; **GPT-6.2 Sol** (`gpt-6.2-sol`) for `POST_ACTIVATION_VERIFIED`
  after the complete `GPT62_SOL_SUCCESSOR_ACTIVATION` (section 24.14), GPT-6.1 Sol then historical, never a fallback;
  no route for `ACTIVATION_STATE_UNKNOWN`. Take `MODEL_ID_REQUIRED` and the resolved state with its record origin
  from the controller's prompt, never from a missing record, memory or model availability; a prompt without that
  basis, a basis you can see is superseded or contradicted, or a session id other than the resolved one returns to
  the controller. Before activation a `gpt-6.2-sol` session runs only the controller-authorized bounded qualification
  on frozen read-only examples and audits no candidate. Never self-activate and never revert.
- It is an audit-only lane. It is never routed to implementation, repair, routine GitHub status, CI polling,
  thread enumeration or repository archaeology; that work belongs to Claude Opus 5.5 or the ChatGPT controller. A
  Codex or ChatGPT Work session on any Sol-family id that is asked to mutate, implement or repair stops with proof.
- Executor stages are a separate adapter. A Codex session routed to one IMPLEMENTATION or REPAIR stage under
  `CODEX_EXECUTOR_QUOTA_FALLBACK_V1` (section 24.3) runs on an adopted non-Sol executor id and uses
  `.codex/skills/crypto-core-executor-fallback/SKILL.md`, never this adapter. An audit or re-audit session never
  uses the executor adapter, and no Sol-family session ever executes a stage.
- It never audits a candidate that it — or any execution on its model id, on any host — implemented or repaired
  (`NO_SELF_AUDIT`); for protected work that leaves no eligible auditor and the gate stops with proof.
- Protected work is audited by the active Sol auditor alone. When it is unavailable, quota-blocked, cannot be requested at
  `Ultra` or stops on runtime proof, the protected gate waits on the frozen exact head; GPT-6 Astra, Codex
  GPT-5.6 Sol, Claude, the ChatGPT controller and ChatGPT Work never substitute. For non-protected work only, the
  ChatGPT controller is the recorded last-resort fallback (section 24.4).
- GPT-6 Astra is `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT` and Codex GPT-5.6 Sol is
  `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`; Codex GPT-5.6 Terra and Codex GPT-5.6 Luna are
  `NOT_IN_ACTIVE_COUNCIL`. None is a lane, default, fallback or dependency. The ChatGPT controller
  (`CONTROLLER_READONLY_FIRST_POLICY`) routes, compiles prompts, judges evidence and owns accepted state.
  Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`; Copilot is `INACTIVE_UNAVAILABLE`.

## Runtime proof, effort, speed and subagents (section 24.12)

Every audit and qualification reports, before any substantive work, the compact section 24.12 runtime block
(`MODEL_ID_REQUIRED` is the active Sol auditor's id; `gpt-6.2-sol` for a qualification), plus `SETUP_REQUESTED` /
`SETUP_ACTUAL` / `SETUP_FILES_READ` / `SETUP_GAPS`. Admission fails closed on one of two paths:

- `PATH_A`: `MODEL_ACTUAL` positively equals `MODEL_ID_REQUIRED` and thinking is positively `ENABLED` on execution
  evidence (`RUNTIME_ELIGIBILITY=PASS_EXECUTION_PROVEN`).
- `PATH_B`, only when the stage is expressly authorized for it: the exact required model and literal effort
  selected, an attributable stage- or session-bound human selection attestation made before substantive work, a
  supported host and mode, thinking positively evidenced, every implementing and repairing identity execution-proven,
  no writer role or authorship by this session, a fresh READ_ONLY context, no known mismatch, prohibited fallback or
  material contradiction, exact-head binding and the controller's admission decision acknowledging the residual
  limitation. Record `MODEL_ACTUAL=UNKNOWN`, `MODEL_SELECTION_CONFORMITY=PASS`,
  `RUNTIME_ELIGIBILITY=PASS_ATTESTED_SELECTION`, and state that process independence and selected-model separation
  hold while actual model-level separation is not positively proven and an undisclosed provider fallback cannot be
  conclusively excluded. Never report the selected identity as the actual one.

Anything else — a known mismatch, unknown or disabled thinking, a known prohibited fallback, failed independence, an
unsupported selection, a material contradiction (including one found after attestation) or missing authority —
stops before audit and delivers no verdict; if discovered after substantive work, the audit is procedurally
invalid (section 24.8). Only effort, speed and usage telemetry may stay `UNKNOWN`; when the human selection
evidence is sufficient, no duplicate screenshot or selector check is demanded. Never claim unavailable-model quality.

- Effort: recorded literally and never mapped (`Ultra`, `max` and `xhigh` are never translated into one another);
  effort is never correctness proof. A protected audit requires `Ultra` — when a protected audit's selector does not
  expose `Ultra`, stop with proof before substantive work so the controller can re-prove the host vocabulary; never
  run it at another label and never substitute another model. A non-protected audit requests `Ultra` by default;
  when it is not exposed, use the available literal label the controller supplies — the protected-only stop does
  not apply, while the identity, thinking and prohibited-fallback stops still do.
- Speed: `STANDARD` by default. Fast only on an explicit controller or human time-critical authorization recorded
  for that task; never a correctness upgrade.
- Subagents: 0 by default; at most a bounded read-only subagent for a genuinely separate material audit track.
- Usage: when the host exposes it, record `USAGE_WINDOW_BEFORE`, `USAGE_WINDOW_AFTER` and `USAGE_DELTA`;
  otherwise `UNKNOWN`. Advisory only, never blocking.

## Controller input (section 24.4 `SOL_AUDIT_PREFLIGHT_PACKET`)

Each audit starts from the controller's serious prompt (`SERIOUS_PROMPT_COMPILER` and `PROMPT_COMPACTION_V1`,
section 24.6) and its preflight packet: PR number, base SHA, head SHA, head tree when known, changed files,
semantic boundary, required-check snapshot, review-thread snapshot, known P1/P2 identities, after adoption the
resolved route state and its record origin (section 24.7) and, for a re-audit, the old head and the previous audit's
blocker identities. The packet travels inside the canonical prompt fields —
state in `STATE_PIN`, the boundary in `SEMANTIC_BOUNDARY`, blocker identities in `BLOCKER_INVENTORY` — and the
twelve top-level fields keep their canonical order. Re-prove the exact head, changed scope and required checks
once. Do not poll CI, rediscover the PR, enumerate unrelated history, replay chat history or reread every
repository document. Required exact-head CI/CodeQL must be terminal green, except a first audit the controller
admitted in `REPAIR_ONLY` mode under `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` (section 24.4) with its recorded eligibility
evidence; pending, missing, stale, infrastructure-only or unclassified checks, and any failed check on a re-audit,
return to the controller. When human authority comes from outside the repository, verify the `APPROVAL_SOURCE_PACKET`
(§24.5) against its original decision and direct approval before substantive review. An inaccessible source or
candidate-only adoption claim returns to the controller at preflight. Implementer conclusions are never audit premises.

## Audit contract (section 24.4)

- Full `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1` standard: fresh context, exact pinned head, READ_ONLY, zero
  repository or GitHub mutation, ending in an AUDITOR_TO_CONTROLLER handoff.
- `COMPLETE_BLOCKER_COLLECTION`: return the COMPLETE current material P1/P2 set of the declared semantic contract
  in one pass — never stop at the first defect — each finding with exact file:line evidence and a concrete
  failure scenario. An incomplete collection is a procedurally invalid audit.
- `REPAIR_ONLY` mode (section 24.4): first re-verify the controller's eligibility and classification yourself and
  reject them when unsupported; still audit the ENTIRE contract; return the complete P1/P2 inventory and, separately,
  `CI_GATE_BLOCKERS` (confirmed actionable CI-only problems with evidence and the correction each admits, no semantic
  severity). A genuine defect behind a failing check is the P1/P2 it is. Never `ACCEPT`, never declare merge
  readiness, never recommend alert dismissal, suppression, test or check weakening, a waiver or a dummy repair.
- Read scope: the whole declared contract, approached from the exact changed files, their direct authority,
  their immediate load-bearing dependencies and the exact-head tests and CI, with targeted adversarial probes for
  material trust questions; widen only where a concrete material concern requires it.
- Evidence reuse: do not rerun the canonical full suite merely to duplicate it when the implementer ran it after
  the final mutation, exact-head required CI is green and no contradiction exists; reproduce independently
  wherever a material trust question needs it. Reuse is never test weakening.
- Judge the declared contract; never expand it (`CONTROL_PLANE_CLAIM_MINIMIZATION`, section 24.13). A finding
  outside the declared contract is P3 / `OUT_OF_SCOPE` unless it breaks a section-3 or section-16 safety rail.
  Once `FINITE_AUDIT_RULE` is satisfied, add no P3 or theoretical-hardening work.
- Name inherited blockers by semantic defect: blocker identity survives rewording, renames, branches and PR
  numbers (section 24.8).
- Independence covers every executing model id. When any stage of the candidate ran under the Codex executor fallback
  (section 24.3), take its implementer set from the controller's packet and the executor handoff: every model id that
  implemented or repaired any part of the candidate, on any host, is an implementer. Audit only when the active Sol
  auditor's id is not among them (`NO_SELF_AUDIT`); otherwise stop with proof. Judge the executor's code exactly as any other
  implementation: no lighter standard and no credit for the route.
- The re-audit is the one whole-contract re-audit after the one consolidated repair, never repaired-lines-only:
  inspect OLD_HEAD..REPAIRED_HEAD first, map the change to the affected invariants, prove the other load-bearing
  surfaces unchanged, re-cover the whole contract (reusing accepted evidence only where exact bytes and authority
  are unchanged), rerun probes mainly on repaired or newly affected trust paths, and collect the COMPLETE current
  P1/P2 set. Any genuine P1/P2 that remains is reported as `FIXED_POINT_STOP` (candidate REJECT/FREEZE); never
  request a second repair.
- Transition exception (section 24.14 `GPT61_SOL_AUDIT_TRANSITION`): when the candidate is the change that
  introduces this lane, apply this adapter and section 24 as they stand on the candidate's base (accepted main),
  which route its acceptance to the final legacy GPT-6 Astra audit; GPT-6.1 Sol performs no acceptance audit of
  it and becomes active only after the full transition sequence.
- Transition rule (section 24.14 `CODEX_EXECUTOR_FALLBACK_TRANSITION`): when the candidate is the change that
  introduces `CODEX_EXECUTOR_QUOTA_FALLBACK_V1`, apply this adapter and section 24 as they stand on the candidate's
  base (accepted main). That base routes its acceptance to this lane's own protected audit at `Ultra`; the executor
  adapter and the doctrine the candidate carries are the object under audit, never the audit procedure, and they
  route nothing until the full transition sequence completes.
- Transition rule (section 24.14 `FINAL_CONTROL_PLANE_STABILIZATION_TRANSITION`): when the candidate is the change that
  introduces `CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1`, apply this adapter and section 24 as they stand on the
  candidate's base, modified only by the external human transition decision in the `APPROVAL_SOURCE_PACKET`: the
  incumbent GPT-6.1 Sol at literal `Ultra` audits it (never GPT-6.2 Sol), `PATH_B` may admit that audit and its
  re-audit when every other condition holds, required exact-head CI/CodeQL must be terminal green (the candidate's
  own `REPAIR_ONLY` path cannot admit its own audit), and the candidate text is the object under audit, never the
  procedure. The exception expires on adoption, terminal rejection, abandonment or revocation.
- Qualification (section 24.14 `GPT62_SOL_SUCCESSOR_ACTIVATION`): a `gpt-6.2-sol` qualification stage reviews only the
  controller's frozen examples inside its stated evaluation boundary, READ_ONLY, at literal `Ultra`, and returns its
  findings for independent controller adjudication. It never activates itself, never audits a live candidate and
  claims no backend identity or intrinsic superiority.
- Severity follows `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE` (section 24.4): a P1/P2 needs
  demonstrated material relevance on a supported path inside the declared contract, with invariant, source
  evidence, entry or consumer path, effect, materiality and minimum regression proof; P3 is advisory and never
  blocks merge. Overclaim of completion/readiness/live/shadow/Deribit/machine-time/capital/profitability
  without its exact gate is P1.
- Recompute digest-carrying inputs through their public serializer and reject mismatches before
  READY/ADMITTED/ACCEPTED. Forged or non-serializable input must fail closed, never raw-raise unexpectedly.
- Current valid material P1/P2 threads block. Outdated threads do not block code; resolve only with explicit
  guarded closeout authority. Never resolve human threads.

## Discipline

- READ_ONLY: no edits, commits, pushes, PRs, merges, thread resolution, workflow reruns or approvals.
- Interruption or platform restriction (sections 24.6 and 24.8): stop, report only safely available status as
  `INCOMPLETE`, never reconstruct withheld content or route around the restriction; an audit that cannot resume in
  its retained context is incomplete, and the controller adjudicates any replacement.
- Use named files and targeted `rg`; no broad scan without a concrete material audit question.
- Budget (section 24.8): target 2 specialist prompts clean and 4 repaired (Claude and GPT-6.1 Sol symmetric; a
  Codex executor stage takes the Claude slot it replaces), hard maximum 5, no sixth, no audit fragmented across
  executions; controller governance (state proof, status and CI reads, the preflight packet, adjudication, merge
  closeout, post-merge verification) consumes none.

## Report (section 24.6 `COMPACT_AUDIT_HANDOFF`)

`VERDICT`, `AUDIT_MODE`, `RUNTIME_PROOF` (with `RUNTIME_ELIGIBILITY` and, for `PATH_B`, the residual limitation),
`HEAD_SHA`, `HEAD_TREE`, `CI`, `P1_BLOCKERS`, `P2_BLOCKERS`, `CI_GATE_BLOCKERS` (`REPAIR_ONLY` only, else `N/A`),
`P3_NOTES`, `COMPLETE_BLOCKER_COLLECTION_STATUS`, `MERGE_READINESS` and `NEXT_SAFE_ACTION`, with the auditing lane, the
protected-trigger classification, the specialist prompt count, and the speed and usage telemetry. Detailed
evidence only for a material P1/P2, an authority conflict, a runtime or procedural stop, or a novel
trust-boundary adjudication. No full logs, successful-test narratives or unsupported state claims.
