---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation/audit loops in BIST_ELITE_CORE - common task classes, validation ladder, and report shape without weakening gates.
---

# Crypto Core Token-Efficient Loop

Full doctrine: `docs/crypto_core/agent_os_v2.md` (`CRYPTO_CORE_AGENT_OS_V2`, the single detailed active
control-plane authority and the canonical `ROLE_ROUTING_MATRIX` in its section 3) plus
`docs/crypto_core/token_efficiency_playbook.md`; `agent_workflow.md` section 24
(`CRYPTO_CORE_AGENT_OS_V1`) is the superseded workflow companion for class/effort detail only and never
forks routing truth. Token saving is subordinate to correctness; no gate may be skipped to save tokens.
Operate under `CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (workflow section 24.2).

## Loop

0. New session with no packet: bootstrap read-only from `AGENTS.md`, `docs/crypto_core/agent_os_v2.md`
   and `docs/crypto_core/continuity/CONTINUITY_INDEX.md` (`CONTEXT_CONTINUITY_PROTOCOL_V1`), re-prove
   repo/branch/base/head/tree/worktree/open-PR state, and compile an ephemeral `STATE_MANIFEST_V1`
   (`docs/crypto_core/continuity/state_manifest.schema.json`). Never trust cached volatile state.
1. Intake the controller packet first (CONTROLLER_TO_IMPLEMENTER: pinned state, exact read set, allowed
   files, invariants, protected-risk class, validation ladder, stops). Do NOT repeat broad GitHub discovery
   the controller already proved.
2. Classify against the canonical `ROLE_ROUTING_MATRIX` (`docs/crypto_core/agent_os_v2.md` section 3;
   this skill is the Claude host adapter and never a routing authority): T0 mechanical (Luna preferred;
   Sonnet 5 low only as an explicitly routed bounded local fallback); T1 read-only, fast-bounded and
   governed closeout (Luna preferred; Sonnet 5 low optional bounded local fallback; Terra) — closeout
   still requires exact authorization; T2 bounded implementation (Sonnet 5 medium / Terra); T3A complex
   implementation (Opus 5 xhigh, default heavy local); T3B capability-critical IMPLEMENTATION or REPAIR
   only, on a named trigger (Opus 5 max) — it never absorbs REVIEW, ARCHITECTURE or PROMPT_ARCHITECTURE;
   T3C review (Opus 5 medium/high/xhigh by breadth); T3D architecture and T3E prompt architecture (Opus 5
   high/xhigh); T4 Sol
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
- `MAX_SAFE_PR` is sized by semantic closure — one coherent contract plus its dependency closure,
  negative cases, permanent tests, validation and rollback — never by file or LOC count. Blocker closure
  follows `BLOCKER_ESCAPE_PROTOCOL_V1`: complete whole-contract audit → ONE consolidated same-branch
  repair → ONE whole-contract reaudit → `FIXED_POINT_STOP`; genuinely new P1/P2 after that is
  `FIXED_POINT_NOT_REACHED` and returns to the controller. `BLOCKER_ARTIFACT_MULTIPLICATION_PROHIBITED`:
  never create a module, test, artifact, phase, workflow or PR solely to restate an unchanged blocker.
- Serious prompts are compiled per `PROMPT_COMPILER_V2` (`agent_os_v2.md` section 8); stable doctrine is
  loaded from the repo, not pasted, and no prompt carries restart-until-success or blanket authority.
- Control-plane edits keep `python scripts/crypto_core/validate_agent_os_v2.py` at exit 0 — it runs in
  the required `tests` CI job.
- One repository writer at a time; one open PR; maximum safe work per prompt, then stop at the gate.
- No BIST, live/order/capital/readiness surface, direct main push, non-standard merge, or unproven claim.
- ChatGPT is the read-only-first controller-auditor (`CONTROLLER_READONLY_FIRST_POLICY`) for non-Class-C
  work; it never replaces local tests or the Class-C Sol audit. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`.
