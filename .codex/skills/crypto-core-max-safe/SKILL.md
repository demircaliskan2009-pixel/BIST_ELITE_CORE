---
name: crypto-core-max-safe
description: Use for BIST_ELITE_CORE crypto_core implementation, repair, salvage, PR closeout, or setup tasks that require maximum safe throughput with strict paper-only, deterministic, fail-closed, audit-first rails.
---

# Crypto Core Max-Safe Workflow

<!-- CONTROL_PLANE_ROLE: CODEX_ADAPTER -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

This is the CODEX host adapter. Use it only for `crypto_core` work in BIST_ELITE_CORE. It defines no
routing, no task family, no effort selection, no PR sizing and no merge authority — all of those live
in `docs/crypto_core/agent_os_v2.md`. Execute the lane selected by canonical routing; never
reclassify your own family and never pick your own canonical effort.

MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.

Operate under `CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (canonical section 1): specialized institutional
crypto trading systems engineering — paper-first, deterministic, fail-closed, audit-first — never
generic coding.

## Lane notes for this host

The canonical matrix assigns the classes. What is host-specific is only HOW each lane behaves here:

- **Mechanical lane (Luna).** Git and `gh` status, bounded CI polling, PR metadata, review-thread
  state, already-authorized merge mechanics, postverify execution. No design judgement, no product-code
  judgement, no semantic readiness judgement.
- **Bounded lane (Terra).** Exact-file deterministic implementation, tests and docs, small same-branch
  repairs, and ordinary fresh-context independent review. Never a protected Class-C substitution.
- **Protected frontier lane.** Class-C protected design and audit run on a controller-prepared narrow
  evidence packet — never broad discovery, never polling, never merge mechanics, never routine docs.
  The canonical protected frontier lane is named in canonical section 3.3; if it cannot run, return
  `ASTRA_REQUIRED_BUT_UNAVAILABLE` and stop. Never substitute a cheaper lane for it because of quota
  or availability.

Every serious prompt and report carries the runtime identity fields of canonical section 4.1 with an
honest evidence class from section 4.2, plus `SETUP_REQUESTED` / `SETUP_ACTUAL` / `SETUP_FILES_READ` /
`SETUP_GAPS`. A required exact-model mismatch stops. Never claim the quality of a model that did not
run.

## Setup load contract

Read, and prove you read: `AGENTS.md`, `docs/crypto_core/agent_os_v2.md`, this skill, the controller
evidence packet, and the exact task files. With no packet, bootstrap read-only per canonical section
15.1 and compile an ephemeral state manifest.

## Controller input packet

Start from the controller packet: pinned base and head, exact changed files, exact direct
dependencies, controller risk classification, the protected-trigger list, unresolved semantic
questions, expected adversarial cases and the required report contract. Do not re-prove PR metadata
the connector already proved, rediscover changed files, read the whole repository without
justification, poll CI with reasoning tokens, or re-audit Class-A material the controller already
closed. Implementer conclusions are never audit premises. Capacity is preserved by NARROWING the
question — never by weakening a gate.

## Audit classes

Class A, Class B and Class C are defined in canonical section 12. Two rules bind this host in
particular: `CODEX_REQUIRED: NO` must always carry the exact reason plus the full protected-trigger
checklist, and any uncertainty escalates to Class C. Nothing replaces Class C — not the controller,
not an implementer self-review, not a same-model second pass.

## Role boundaries

This host is an adversarial P1/P2 reviewer, read-only by default. Patch only when explicitly
authorized and scoped. Never patch a PR concurrently with another writer — one repository writer at a
time — and never merge as a reviewer. An implementation cannot self-satisfy the independent audit gate
in the same context: independent audits are fresh-context, pinned-head tasks ending in an
auditor-to-controller handoff with P1/P2/P3 findings, exact source evidence, reproducible failures,
repair requirements, readiness classification and zero mutation.

The bounded single-goal terminal loop (preflight, sync, CI and status, closeout, and explicitly
authorized merge or postverify) is exactly that: bounded. It is not broad repository pursuit, unscoped
design, or unscoped repair.

External and current facts route to the controller-orchestrated research lane (canonical section 8).
Research never mutates state, never approves a governance value, never replaces an audit and never
waives a gate.

## Safety and audit contract

- Stay crypto-only, paper-only, deterministic, fail-closed and audit-first.
- No BIST, live or private API, credentials, orders, scheduler, runtime, readiness or Deribit
  transition, shadow or live execution, or capital work unless separately authorized and designed.
- P1 is a correctness or safety break; P2 is a real defect or a missing negative-path proof; P3 is
  advisory.
- Recompute digest-carrying inputs through their public serializer and reject a mismatch before
  READY, ADMITTED or ACCEPTED. Forged or non-serializable input must fail closed, never raise
  unexpectedly.
- Overclaiming completion, readiness, live or shadow status, Deribit promotion, machine-time, capital
  or profitability without its exact gate is P1.
- Current valid P1/P2 threads block. Outdated threads do not block code; resolve only with explicit
  guarded closeout authority. Never resolve a human thread.

## Gate, patch and validation discipline

- Prove workspace, branch, HEAD, dirty files and open PRs before editing. Stop if dirt exceeds scope.
- Setup and doctrine work uses a separate `chore/<scope>-prN` PR and never mixes feature code.
- Use named files and targeted search; no broad scans without justification.
- Product patches validate focused lint and tests, then the logged full suite when required. Docs and
  setup-only changes prove the exact scope and run `git diff --check` unless an executable or
  configuration surface changed. Control-plane changes must keep
  `python scripts/crypto_core/validate_agent_os_v2.py` at exit 0.
- Stage exact paths only. Never push directly to `main`, force-push, self-approve, or merge without
  exact human authorization for that exact PR and head.

## Report

Report the result, the actual runtime identity and effort, setup fields, proof, changed files,
validation, PR, check and thread state, audit class, blockers, and exactly one next safe action. No
full success logs and no unsupported state claim.
