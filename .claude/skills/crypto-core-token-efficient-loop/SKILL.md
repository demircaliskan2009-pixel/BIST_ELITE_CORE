---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation and consolidated-repair loops in BIST_ELITE_CORE - kernel lifecycle, validation ladder, and report shape without weakening gates.
---

# Crypto Core Token-Efficient Loop

Authority: `AGENTS.md` and `docs/crypto_core/agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`,
active content `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by the amendments its header lists). This
checklist restates no authority. Token
saving is subordinate to correctness; no gate may be skipped to save tokens. Operate under
`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` (section 24.2).

## Loop

1. Intake the controller's serious prompt (`SERIOUS_PROMPT_COMPILER`, §24.6: task intent, semantic boundary,
   state pin, runtime proof, allowed files, invariants, blocker inventory, validation matrix, GitHub
   authorization, forbidden, stop conditions, handoff). Do NOT repeat broad GitHub discovery the controller
   already proved.
2. Runtime proof before mutation: the compact §24.12 runtime block, admitted on `PATH_A` only (`PATH_B` never
   admits a writer). Fail closed: `MODEL_ACTUAL` must be positively
   `claude-opus-5-5` and thinking positively `ENABLED` on execution evidence; `UNKNOWN`, a mismatch, disabled
   thinking, a known prohibited fallback, or selector/config/default/cache/request text alone →
   `STOP_WITH_PROOF`. Only effort may stay `UNKNOWN`. Report the controller's literal effort selection
   (§24.12 `HOST_SENSITIVE_EFFORT_POLICY`); a proven effort conflict stops unless §24.12 `EFFORT_MISMATCH_WAIVER`
   applies.
3. Prove the local base, HEAD, tree, branch and clean status. Bind them to the controller's current PR snapshot.
4. Read the named set; use symbol search before full files; build one source surface map.
5. Close the whole semantic boundary as the largest safe semantic closure (§24.8) inside the allowed files,
   preserving paper-only, fail-closed and digest-boundary rules. A repair is the single consolidated repair:
   the complete audited P1/P2 set plus any confirmed `CI_GATE_BLOCKER` (§24.4), by root cause, in one change.
6. Validate one command at a time: scoped Ruff/format, targeted tests, logged full suite when code changed,
   `git diff --check`, exact changed-file proof.
7. Publish with scoped `git add`, one commit and one PR. Hand the exact head to the controller for CI and review
   verification; mutation ends there and the writer does not poll CI to terminal (§24.5 `HANDOFF_OWNERSHIP`). On an
   interruption or platform restriction, stop and report safely available state as `INCOMPLETE` (§24.8).
8. End with an `AGENT_OS_HANDOFF_V1` handoff: runtime proof, setup fields (`SETUP_REQUESTED`/`SETUP_ACTUAL`/
   `SETUP_FILES_READ`/`SETUP_GAPS`), exact scope, validation, PR/CI/thread evidence, the meaningful-prompt
   count, `SELF_AUDIT_ONLY_NOT_INDEPENDENT`, and exactly one next safe action.

## Boundaries

- Council (§24.3): ChatGPT controller (`CONTROLLER_READONLY_FIRST_POLICY`); Claude Opus 5.5
  (`claude-opus-5-5`) for deep semantic implementation and repair, including the repo-native navigation,
  dependency-tracing, test and validation work of that same task; the conditional Codex executor
  (`CODEX_EXECUTOR_QUOTA_FALLBACK_V1`), routed only by the controller for a whole stage Claude cannot run (§24.3);
  the `ACTIVE_SOL_AUDITOR` (resolved by the controller under §24.7 `SOL_ROUTE_STATE_RESOLUTION`: GPT-6.1 Sol,
  `gpt-6.1-sol`, before and GPT-6.2 Sol, `gpt-6.2-sol`, after a verified §24.14 activation) as the
  audit-only PRIMARY independent auditor (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`), which for protected work is also the
  protected T4 audit, never reassigned, with the ChatGPT controller as the last-resort non-protected fallback
  (§24.4); ChatGPT Work; Deep Research. GPT-6 Astra is `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT` and Codex GPT-5.6
  Sol `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`, neither a fallback; Claude Sonnet 5, Codex Terra and Codex Luna
  are `NOT_IN_ACTIVE_COUNCIL`; Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`; Claude Opus 5 is
  `SUPERSEDED_BY_OPUS_5_5` and Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5`, neither an automatic fallback;
  Copilot is `INACTIVE_UNAVAILABLE`. Work that needs no independence stays with the Claude task or the controller
  and is never routed to the Sol audit lane (§24.4 `SOL_AUDIT_USAGE_EFFICIENCY_V1`).
- Budget (§24.8): the fewest specialist prompts — target 2 clean, 4 repaired, hard maximum 5, no specialist
  sixth; controller governance closeout consumes none. One exhaustive audit, at most one consolidated repair,
  one whole-contract re-audit. Any genuine material P1/P2 after that → `FIXED_POINT_STOP`; P3 never blocks; no
  mutation of a rejected or frozen candidate.
- No Claude session self-satisfies an independent or protected audit.
- `CONTROL_PLANE_CLAIM_MINIMIZATION` (§24.13): no new validator, registry, filesystem or host-discovery
  layer, schema, dependency or process the declared contract does not require.
- Subagents default 0 (max 2 read-only, genuinely independent substantial tracks only). Run each
  deterministic gate once per unchanged head; no generic re-verification loops. Deliver exactly the
  authorized semantic boundary — report and stop instead of widening.
- External/current facts route to controller-orchestrated Deep Research (read-only, advisory) — never local
  web research, never a gate waiver.
- One repository writer at a time; one open PR; maximum safe work per prompt, then stop at the gate.
- No BIST, live/order/capital/readiness surface, direct main push, non-standard merge, or unproven claim.
