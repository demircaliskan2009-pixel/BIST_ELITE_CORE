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
2. Classify: T0 Luna mechanical; T1 read-only/fast bounded (Luna/Terra/runtime-proven Sonnet 5); T2 bounded
   implementation (Terra/Sonnet 5); T3 complex/repair (Opus 4.8 heavy local or Terra xhigh); T4 Sol
   cross-contract; XR controller-orchestrated Deep Research; controller/connector final evidence gate.
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

- Claude Fable 5 = runtime-proven PREMIUM SURGE lane (workflow §24.10), gated by `FABLE5_JUSTIFICATION_GATE`
  + `MODEL_EXPECTED_VALUE_PER_TOKEN_POLICY`: SURGE_IMPLEMENTER for semantically dense broad-but-bounded T3
  work expected to collapse multiple prompts (protected Class-C code only with explicit controller
  authorization + mandatory separate Sol Class-C audit); CROSS_CONTRACT_CHALLENGE and FULL_REPO_AUDIT are
  read-only. One strong bounded prompt end-to-end, then an IMPLEMENTER handoff — no Fable self-audit claim.
  Unavailable/unjustified → Opus 4.8 (default heavy), without equivalent-quality claims.
- Claude Opus 4.8 owns broad local implementation and long loops by default; runtime-proven Claude Sonnet 5
  owns small/medium bounded slices, docs/tests, and mechanical code (fallback: Terra bounded / Opus broad).
- No Claude session self-satisfies independent review; Class-C protected work (digest/provenance, SM-5/SM-6,
  Stage-4, readiness, finance arithmetic, trust transitions) always gets a fresh pinned-head Codex audit.
- Sol is scarce and never used for mechanics. Luna never performs broad design or feature implementation.
- External/current facts route to controller-orchestrated Deep Research (read-only, advisory) — never local
  web research, never a gate waiver.
- Codex Pursue Goal is a bounded terminal preflight/sync/CI/status/closeout/authorized-postverify loop only.
- One repository writer at a time; one open PR; maximum safe work per prompt, then stop at the gate.
- No BIST, live/order/capital/readiness surface, direct main push, non-standard merge, or unproven claim.
- No plan may DEPEND on Fable availability; Fable prompts always declare their fallback.
