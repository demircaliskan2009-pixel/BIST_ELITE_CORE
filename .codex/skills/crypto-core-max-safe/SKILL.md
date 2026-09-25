---
name: crypto-core-max-safe
description: Use only when the ChatGPT controller routes a recorded SOL_RESERVE_ONLY capability or eligibility gap to Codex in BIST_ELITE_CORE crypto_core (reserve engineering, or a reserve non-protected acceptance audit or re-audit), with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

Use this skill only for `crypto_core` work in BIST_ELITE_CORE. Authority: `AGENTS.md` →
`docs/crypto_core/agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`, active content
`MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended, most recently by `CODEX_QUOTA_RESILIENCE_V2`) → this
adapter, which restates no authority. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2): specialized institutional crypto trading systems
engineering — paper-first, deterministic, fail-closed, audit-first — never generic coding.

## Codex lane (section 24.3)

- **Codex GPT-5.6 Sol** is `SOL_RESERVE_ONLY`: not the default auditor, navigator, status checker, reviewer or
  implementation accelerator, and never added for model diversity. A Sol session runs only when the ChatGPT
  controller records a specific capability or eligibility gap that the controller and the routed Claude Opus 5.5
  task cannot legally or safely cover; the serious prompt states that gap. Its host label `Ultra` is recorded
  literally.
- The acceptance audit of a NON-PROTECTED candidate belongs by default to the ChatGPT controller
  (`CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT`, section 24.4). Sol performs it only as the recorded eligibility gap —
  when `NO_SELF_AUDIT` makes the controller ineligible because it or ChatGPT Work implemented or repaired the
  candidate — and only when Sol itself neither implemented nor repaired that lifecycle and passes runtime proof
  (eligibility before availability). With no independent eligible reviewer the gate stops with proof. A Sol
  session that cannot prove its identity or required thinking stops before auditing and delivers no verdict.
- Sol never satisfies a protected audit. Protected acceptance and protected T4 `CLASS_C_CROSS_CONTRACT` are the
  GPT-6 Astra READ_ONLY audit alone; when Astra is unavailable that gate waits and is never reassigned to Sol.
- Sol never audits a candidate it implemented or repaired, in any context.
- Codex GPT-5.6 Terra and Codex GPT-5.6 Luna are `NOT_IN_ACTIVE_COUNCIL`. The ChatGPT controller
  (`CONTROLLER_READONLY_FIRST_POLICY`) routes, compiles prompts, judges evidence and owns accepted state.
  Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`; Copilot is `INACTIVE_UNAVAILABLE`.

Every serious prompt/report carries the runtime-proof block (section 24.12): `MODEL_REQUESTED`,
`MODEL_ID_REQUIRED`, `MODEL_ACTUAL`, `MODEL_EFFORT_REQUESTED`, `MODEL_EFFORT_ACTUAL`, `MODEL_FALLBACK`,
`THINKING_ACTUAL`, `MODEL_IDENTITY_EVIDENCE`, `MODEL_EFFORT_EVIDENCE`, plus `SETUP_REQUESTED` /
`SETUP_ACTUAL` / `SETUP_FILES_READ` / `SETUP_GAPS`. Runtime proof fails closed: `MODEL_ACTUAL` must
positively equal `MODEL_ID_REQUIRED` and required thinking must be positively `ENABLED` on execution evidence;
`UNKNOWN`, a mismatch, disabled required thinking, a known prohibited fallback, or selector, configuration,
default, cache or request text alone stops before any audit or mutation. Only effort may stay `UNKNOWN`. Never
claim unavailable-model quality.

## Controller input

Codex sessions start from the controller's serious prompt (`SERIOUS_PROMPT_COMPILER`, section 24.6): pinned
base/head, the declared semantic boundary, exact changed files, direct dependencies, blocker inventory,
protected-trigger classification, and the required report. Do not re-prove PR metadata the connector already
proved, rediscover changed files, read the whole repository without justification, or poll CI with reasoning
tokens. Implementer conclusions are never audit premises.

## Audit contract (section 24.4)

- Applies only when Sol is the routed `SOL_RESERVE_ONLY` substitute for a non-protected acceptance audit or
  re-audit, to the acceptance-audit standard of section 24.4: fresh context, exact pinned head, READ_ONLY, zero
  mutation, the recorded gap stated, ending in an AUDITOR_TO_CONTROLLER handoff. The audit is a meaningful prompt
  of the one hard-five budget (section 24.8).
- `COMPLETE_BLOCKER_COLLECTION`: return the COMPLETE current material P1/P2 set of the declared semantic contract in
  one pass — never stop at the first defect — each finding with exact file:line evidence and a concrete
  failure scenario.
- Judge the declared contract; never expand it (`CONTROL_PLANE_CLAIM_MINIMIZATION`, section 24.13). A finding
  outside the declared contract is P3 / `OUT_OF_SCOPE` unless it breaks a section-3 or section-16 safety rail.
- Name inherited blockers by semantic defect: blocker identity survives rewording, renames, branches and PR
  numbers (section 24.8).
- A re-audit is the one whole-contract re-audit after the one consolidated repair. Any genuine P1/P2 that
  remains is reported as `FIXED_POINT_STOP` (candidate REJECT/FREEZE); never request a second repair.
- A candidate with any trigger of `PROTECTED_TRIGGER_MATRIX_V2` (section 24.4, A-G, including control-plane
  changes; ambiguity counts as protected) is never audited by Sol: report `PROTECTED_TRIGGER_PRESENT` and stop
  before substantive audit; the GPT-6 Astra audit is required. A change to this control plane is audited under
  section 24 and the adapters as they stand on its base, never its own text (section 24.14).
- Severity follows `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE` (section 24.4): a P1/P2 needs
  demonstrated material relevance on a supported path inside the declared contract, with invariant, source
  evidence, entry or consumer path, effect, materiality and minimum regression proof; P3 is advisory and never
  blocks merge. Overclaim of completion/readiness/live/shadow/Deribit/machine-time/capital/profitability
  without its exact gate is P1.
- Recompute digest-carrying inputs through their public serializer and reject mismatches before
  READY/ADMITTED/ACCEPTED. Forged or non-serializable input must fail closed, never raw-raise unexpectedly.
- Current valid material P1/P2 threads block. Outdated threads do not block code; resolve only with explicit guarded
  closeout authority. Never resolve human threads.

## Engineering contract

Patch only when routed as a recorded `SOL_RESERVE_ONLY` gap and explicitly authorized: exact allowed files, the declared semantic boundary closed as
the largest safe semantic closure (section 24.8), one repository writer at a time, never concurrently with
another writer, never as the reviewer of the same work, and never merge.

## Gate, patch, and validation discipline

- Prove workspace, branch, HEAD, dirty files, and open PRs before editing. Stop if dirt exceeds scope.
- Setup/doctrine work uses a separate `chore/<scope>-prN` PR and never mixes feature code.
- Use named files and targeted `rg`; no broad scans without justification.
- Product patches validate focused Ruff/tests then the logged full suite when required. Docs/setup-only
  changes prove exact scope and run `git diff --check` unless an executable/config surface changed.
- Stage exact paths only. Never push directly to `main`, force-push, self-approve, or merge without exact
  per-PR, exact-head human authorization.
- Budget (section 24.8): target 2 specialist prompts clean and 4 repaired, hard maximum 5, no sixth;
  controller governance (state proof,
  status and CI reads, adjudication, merge closeout, post-merge verification) consumes none.

## Report

Reports are `AGENT_OS_HANDOFF_V1` packets (section 24.6): result, runtime proof, setup fields, proof, changed
files, validation, PR/check/thread state, P1/P2/P3 findings with evidence, protected-audit requirement, the
meaningful-prompt count, and exactly one next safe action. No full logs or unsupported state claims.
