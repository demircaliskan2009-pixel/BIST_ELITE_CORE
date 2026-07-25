---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation/audit loops in BIST_ELITE_CORE - common task classes, validation ladder, and report shape without weakening gates.
---

# Crypto Core Token-Efficient Loop

Full doctrine: `docs/crypto_core/token_efficiency_playbook.md` and `agent_workflow.md` section 24
(`CRYPTO_CORE_AGENT_OS_V1`). Token saving is subordinate to correctness; no gate may be skipped to save
tokens. Operate under `CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2).

## Loop

1. Intake the controller packet first (CONTROLLER_TO_IMPLEMENTER: pinned state, exact read set, allowed
   files, invariants, protected-risk class, validation ladder, stops). Do NOT repeat broad GitHub discovery
   the controller already proved.
2. Classify against the single authoritative routing matrix (`agent_workflow.md` §24.3): T0 mechanical
   (Sonnet 5 low / Luna); T1 read-only, fast-bounded and governed closeout (Sonnet 5 low / Luna / Terra);
   T2 bounded implementation (Sonnet 5 medium / Terra); T3A complex implementation (Opus 5 xhigh, default
   heavy local) ; T3B capability-critical (Opus 5 max, explicit trigger only); T3C review (Opus 5
   medium/high/xhigh by breadth); T3D architecture and T3E prompt architecture (Opus 5 high/xhigh); T4 Sol
   cross-contract; XR controller-orchestrated Deep Research; controller/connector final evidence gate.
   Effort selection: §24.12. Prove `MODEL_ACTUAL` and `MODEL_EFFORT_ACTUAL` from session runtime evidence
   before mutating — an unresolved alias is not proof; mismatch or fallback is `STOP_WITH_PROOF`.
3. Prove LOCAL state once with `git`/`gh`: HEAD, clean tree, open PRs, and checks when relevant — local
   proof stays Claude's own responsibility even with a controller packet.
4. Read the named set; use symbol search before full files; build one source surface map.
5. Patch only named files, preserving paper-only, fail-closed, and digest-boundary rules.
6. Validate one command at a time: scoped Ruff/format, targeted tests, logged full suite when required,
   then `git diff --check`.
7. Publish with scoped `git add`, one PR, and bounded CI snapshots. Pending is `NOT_READY`.
8. End with an IMPLEMENTER_TO_CONTROLLER handoff (`AGENT_OS_HANDOFF_V1`): actual model/reasoning, setup
   fields (`SETUP_REQUESTED`/`SETUP_ACTUAL`/`SETUP_FILES_READ`/`SETUP_GAPS`), exact scope, validation,
   PR/CI evidence, no self-audit claim, exactly one next safe action.

## Boundaries

- Claude Fable 5 = `INACTIVE_EXPIRED_RETIRED` (workflow §24.10) — not an active lane, fallback, or
  dependency. Former surge work routes to Opus 5 (broad-but-bounded T3) or Sonnet 5 / Terra (bounded T2);
  former read-only challenge/full-repo audit routes to the ChatGPT read-only-first controller
  (`CONTROLLER_READONLY_FIRST_POLICY`) or Codex Sol for protected Class-C. Archived Fable material in
  `fable_exit_contract_index.md` is HISTORICAL/ARCHIVAL only.
- Claude Opus 5 (`claude-opus-5`) owns broad local implementation, long loops, review, architecture and
  complex prompt design; runtime-proven Claude Sonnet 5 (`claude-sonnet-5`) is the DEFAULT lane for status,
  polling, governed closeout, small/medium bounded slices, docs/tests and mechanical code (fallback: Terra
  bounded / Opus 5 broad). Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5` — historical evidence only.
- Effort: Opus 5 `xhigh` is the normal coding default; `max` only on an explicit T3B trigger, never for
  polling, closeout, formatting, routine tests, simple docs or one-line repair. Keep adaptive thinking
  enabled — never `thinking: disabled` on a T3 lane or with `xhigh`/`max`.
- Subagents default 0 (max 2 read-only, genuinely independent substantial tracks only). Run each
  deterministic gate once per unchanged head; no generic re-verification loops. Deliver exactly the
  authorized scope — report and stop instead of widening. `ultracode`, if exposed, is an orchestration mode,
  never an effort level and never a default.
- No Claude session self-satisfies independent review; Class-C protected work (digest/provenance, SM-5/SM-6,
  Stage-4, readiness, finance arithmetic, trust transitions) always gets a fresh pinned-head Codex audit.
- Sol is scarce and never used for mechanics. Luna never performs broad design or feature implementation.
- External/current facts route to controller-orchestrated Deep Research (read-only, advisory) — never local
  web research, never a gate waiver.
- Codex Pursue Goal is a bounded terminal preflight/sync/CI/status/closeout/authorized-postverify loop only.
- One repository writer at a time; one open PR; maximum safe work per prompt, then stop at the gate.
- No BIST, live/order/capital/readiness surface, direct main push, non-standard merge, or unproven claim.
- ChatGPT is the read-only-first controller-auditor (`CONTROLLER_READONLY_FIRST_POLICY`) for non-Class-C
  work; it never replaces local tests or the Class-C Sol audit. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`.
