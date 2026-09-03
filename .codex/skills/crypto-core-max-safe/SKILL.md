---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core implementation, repair, salvage, PR closeout, or setup tasks that require maximum safe throughput with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

Use this skill only for `crypto_core` work in BIST_ELITE_CORE. Canonical precedence
(`AGENT_OS_V2_PRECEDENCE`) is `AGENTS.md` → `docs/crypto_core/agent_os_v2.md`
(`CRYPTO_CORE_AGENT_OS_V2`, the single detailed active control-plane authority) → this skill (the Codex
environment adapter) → `docs/crypto_core/agent_lessons.md`. `docs/crypto_core/agent_workflow.md` (section
24 `CRYPTO_CORE_AGENT_OS_V1`) is the workflow companion and never forks routing truth; the canonical
`ROLE_ROUTING_MATRIX` is `agent_os_v2.md` section 3. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (workflow section 24.2): specialized institutional crypto
trading systems engineering — paper-first, deterministic, fail-closed, audit-first — never generic coding.

Agent OS v2 additions that bind every Codex task: `MAX_SAFE_PR` is sized by semantic closure, never by
file or LOC count; `PR_CLOSURE_CONTRACT_V1` is frozen before implementation;
`BLOCKER_ESCAPE_PROTOCOL_V1` requires the independent audit to collect the COMPLETE P1/P2 set for the
whole frozen contract (never stop at the first blocker, never review only the latest delta, never invent
new closure requirements after each repair), then ONE consolidated same-branch repair, then ONE
whole-contract reaudit, then `FIXED_POINT_STOP`; `BLOCKER_ARTIFACT_MULTIPLICATION_PROHIBITED` forbids a
new module/test/artifact/phase/workflow/PR created solely to restate an unchanged blocker; new sessions
bootstrap from `docs/crypto_core/continuity/CONTINUITY_INDEX.md` and compile an ephemeral
`STATE_MANIFEST_V1`.

## Active routing (Sol / Terra / Luna)

- T0 `LUNA_MECHANICAL` — Luna: git/gh status, bounded CI polling, PR metadata, review-thread state,
  authorized merge mechanics, and postverify running. No design or product-code judgment.
- T1 `READONLY_OR_FAST_BOUNDED` — Luna low or Terra high: bounded proof, docs, direct-dependency audit.
- T2 `BOUNDED_IMPLEMENTATION` — Terra high: exact-file deterministic implementation, tests/docs, small
  same-branch repairs. (Runtime-proven Claude Sonnet 5 may also hold this class per section 24.3.)
- T3 `COMPLEX_IMPLEMENTATION_OR_REPAIR` — Terra xhigh for bounded repair; Claude Opus 5 xhigh when broad
  reads or long local validation loops are needed. (The Claude side of T3 is subdivided T3A-T3E in section
  24.3; Codex classes are unchanged.)
- T4 `CROSS_CONTRACT_DESIGN_OR_AUDIT` — Sol xhigh (`max` only controller-gated): protected trust-boundary,
  digest/provenance, governance/safety, SM-5/SM-6 design/audit, Stage-4 semantics, readiness/Deribit,
  complex security/CodeQL. Sol runs ONLY on a controller-prepared narrow evidence packet — never broad
  discovery, polling, merge mechanics, or routine docs.
- XR — Deep Research, controller-orchestrated, external/current facts, advisory only.
- `CONTROLLER_CONNECTOR_GATE` — ChatGPT GPT-5.6 Thinking + connector/`gh`: read-only-first controller-auditor
  (`CONTROLLER_READONLY_FIRST_POLICY`, workflow §24.10), final evidence comparison, and merge authority.
  ChatGPT now performs most non-Class-C read-only mapping/audit (Class A closeout; Class B first-pass with
  Terra ordinary audit only when evidence requires) — treat its output as advisory/controller input, NEVER
  as an audit premise and never as a substitute for the fresh Sol Class-C audit this skill owns. ChatGPT is
  not a Codex runtime. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — no active upstream Fable input exists.

Every serious prompt/report contains `MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`,
`REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`, declared fallback, and the `SETUP_REQUESTED` / `SETUP_ACTUAL` /
`SETUP_FILES_READ` / `SETUP_GAPS` block. Required exact-model mismatch stops. Never claim
unavailable-model quality.

## Controller input packet (Codex workload reduction)

Codex sessions start from the CONTROLLER_TO_AUDITOR / CONTROLLER_TO_IMPLEMENTER packet: pinned PR base/head,
exact changed files, exact direct dependencies, controller risk classification, protected-trigger list,
unresolved semantic questions, expected adversarial cases, and the required report contract. Do not re-prove
PR metadata the connector already proved, rediscover changed files, read the whole repository without
justification, poll CI with reasoning tokens, or re-audit Class-A docs/setup the controller already closed.
Implementer conclusions are never audit premises. Codex capacity is preserved by NARROWING the question —
never by weakening the gate.

## Audit classes

- **Class A (controller-sufficient):** docs/setup/prompt/skill/workflow-doc/low-risk CI config/deterministic
  helper scripts — audited by ChatGPT + connector with fresh pinned-head reread; Codex not required.
- **Class B (controller-first):** ordinary bounded product code — controller maps scope/dependencies/tests/
  triggers first; Terra fresh independent audit added when risk or evidence requires; `CODEX_REQUIRED: NO`
  needs the exact reason plus the protected-trigger checklist; any uncertainty escalates to Class C.
- **Class C (Codex REQUIRED, never replaceable):** digest recomputation/consumption, expected-digest
  anchors, canonical serialization, reseal/provenance, mutable/stateful/TOCTOU, denominator integrity,
  record-set completeness, duplicate/replay defense, Decimal/Fraction financial arithmetic, governance
  thresholds, fail-closed trust transitions, READY/ADMITTED/ACCEPTED, SM-5/SM-6, Stage-4 completion,
  machine-time provenance, readiness/Deribit, connector-ready transitions, live/private API, orders/order
  routing, scheduler/auto-loop, shadow/live, capital mutation, edge/profitability claims, complex
  CodeQL/security, current P1/P2 source findings, insufficient controller evidence.

## Role boundaries

Codex is an adversarial P1/P2 reviewer, read-only by default. Patch only when explicitly authorized and
scoped; never patch a PR concurrently with another writer (one repository writer at a time) or merge as a
reviewer. An implementation cannot self-satisfy the independent audit gate in the same context; independent
audits are fresh-context, pinned-head tasks ending in an AUDITOR_TO_CONTROLLER handoff (P1/P2/P3 with exact
source evidence, reproducible failures, repair requirements, readiness classification, zero mutation).

Codex Pursue Goal is a bounded single-goal terminal loop for preflight, sync, CI/status, closeout, and
explicitly authorized merge/postverify. It is not broad repo pursuit, unscoped design, or unscoped repair.

Deep Research is controller-orchestrated external/current-fact advisory only. It never mutates repo or
GitHub state, approves a governance value, replaces a Codex audit, or waives a safety gate.

## Safety and audit contract

- Stay crypto-only, paper-only, deterministic, fail-closed, and audit-first.
- No BIST, live/private API, credentials, orders, scheduler, runtime/readiness/Deribit transition,
  shadow/live, or capital work unless separately authorized and designed.
- P1 is a correctness/safety break; P2 is a real defect or missing negative-path proof; P3 is advisory.
- Recompute digest-carrying inputs through their public serializer and reject mismatches before
  READY/ADMITTED/ACCEPTED. Forged or non-serializable input must fail closed, never raw-raise unexpectedly.
- Overclaim of completion/readiness/live/shadow/Deribit/machine-time/capital/profitability without its exact
  gate is P1.
- Current valid P1/P2 threads block. Outdated threads do not block code; resolve only with explicit guarded
  closeout authority. Never resolve human threads.

## Gate, patch, and validation discipline

- Prove workspace, branch, HEAD, dirty files, and open PRs before editing. Stop if dirt exceeds scope.
- Setup/doctrine work uses a separate `chore/<scope>-prN` PR and never mixes feature code.
- Use named files and targeted `rg`; no broad scans without justification.
- Product patches validate focused Ruff/tests then logged full suite when required. Docs/setup-only changes
  prove exact scope and run `git diff --check` unless an executable/config surface changed.
- Stage exact paths only. Never push directly to `main`, force-push, self-approve, or merge without exact
  human authorization.

## Report

Reports are `AGENT_OS_HANDOFF_V1` packets (workflow section 24.6): result, actual model/effort, setup
fields, proof, changed files, validation, PR/check/thread state, audit class, blockers, and exactly one next
safe action. No full logs or unsupported state claims.
