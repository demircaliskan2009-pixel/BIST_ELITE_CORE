---
name: crypto-core-token-efficient-loop
description: Compact execution checklist for crypto_core implementation/audit loops in BIST_ELITE_CORE - common task classes, validation ladder, and report shape without weakening gates.
---

# Crypto Core Token-Efficient Loop

<!-- CONTROL_PLANE_ROLE: CLAUDE_ADAPTER -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

This is the CLAUDE host adapter loop. It compresses procedure only. It defines no routing, no task
family, no effort selection, no PR sizing and no merge authority — all of those live in
`docs/crypto_core/agent_os_v2.md`. Execute the lane selected by canonical routing; never reclassify
your own family and never pick your own canonical effort. Token saving is subordinate to correctness:
no gate may be skipped to save tokens.

MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.

## Loop

0. **Cold start.** With no controller packet, bootstrap read-only per canonical section 15.1:
   `AGENTS.md` → `docs/crypto_core/agent_os_v2.md` → this adapter →
   `docs/crypto_core/continuity/CONTINUITY_INDEX.md` → the current ephemeral manifest/handoff. Then
   re-prove repo, branch, base, head, tree, worktree and open-PR state, and compile an ephemeral
   state manifest (`docs/crypto_core/continuity/state_manifest.schema.json`). Never trust cached
   volatile state.
1. **Intake.** Consume the controller packet first: pinned state, exact read set, allowed files,
   invariants, protected-risk class, validation ladder, stop conditions. Do not repeat broad remote
   discovery the controller already proved.
2. **Prove runtime identity.** Before any mutation, prove and report the model and effort fields with
   an honest evidence class (canonical section 4.2). An unresolved alias is not proof. A mismatch, a
   fallback, or contradictory runtime proof is `STOP_WITH_PROOF` before mutation.
3. **Prove local state.** Once, with `git`/`gh`: HEAD, clean tree, open PRs, and checks when
   relevant. Local proof stays this session's own responsibility even with a controller packet.
4. **Read.** The named set only. Symbol search before whole files. Build one source-surface map.
5. **Patch.** Only the exact allowed files, preserving paper-only, fail-closed and digest-boundary
   rules. `ALLOWED_FILES` is an authorization boundary, not a sizing ceiling — needing a path outside
   it is a stop-and-rescope, never a reason to shrink a coherent contract.
6. **Validate.** One command at a time: scoped lint and format, targeted tests, the logged full suite
   when required, `python scripts/crypto_core/validate_agent_os_v2.py` for any control-plane change,
   then `git diff --check`. Run each deterministic gate once per unchanged evidence key; targeted
   first during development, the full ladder once on the final candidate bytes.
7. **Publish.** Scoped `git add` of exact paths, one commit, one PR, bounded CI snapshots. Pending is
   `NOT_READY`.
8. **Hand off.** End with the implementer-to-controller packet: actual model and effort with evidence
   class, setup fields (`SETUP_REQUESTED` / `SETUP_ACTUAL` / `SETUP_FILES_READ` / `SETUP_GAPS`), exact
   scope, validation, PR and CI evidence, no self-audit claim, and exactly one next safe action.

## Boundaries

- Capacity: prefer this lane for nonprotected work it can do at the required quality, because the
  frontier audit lane, the bounded Codex lane and Work share one provider pool (canonical section
  10.3). An exhausted provider changes routing, never a gate: with the shared pool exhausted the mode
  is `CLAUDE_CONTINUITY` for nonprotected work, while a gate that requires the protected frontier
  lane still waits. Record the capacity reading, or `UNKNOWN`, in the handoff; never guess it and
  never write it into a durable file.
- Effort is chosen per task from the work itself (canonical section 3.2), never from file count,
  project importance or a previous audit failure. De-escalate when the remaining work gets simpler.
  `max` legality is per family — see `MAX_EFFORT_FAMILY_TRIGGERS` in canonical section 20 — so never
  restate a single family restriction as a rule about the effort itself.
- One repository writer at a time; one open PR; maximum safe work per prompt, then stop at the gate.
- Subagents default 0, maximum 2 read-only for genuinely independent substantial tracks, no
  recursion, only the primary session mutates. A same-model self-review is
  `SELF_AUDIT_ONLY_NOT_INDEPENDENT`.
- No Claude session satisfies an independent audit. Protected Class-C work always gets a fresh-context
  audit from the protected frontier lane (canonical sections 3.3 and 12), and an unavailable frontier
  lane is `ASTRA_REQUIRED_BUT_UNAVAILABLE` — never a silent downgrade.
- External or current facts route to the controller, never to local web research, and never as a gate
  waiver.
- No BIST, live, order, capital or readiness surface; no direct `main` push; no non-standard merge;
  no unproven claim.
- Stop rather than continue when the context budget would make correctness uncertain, validation
  turns ambiguous, a failure needs unrelated repair, scope would widen, an authorization gate is
  reached, or provenance is unclear.

## Report shape

`RESULT` / `FILES_CHANGED` / `VALIDATION` / `NEXT_SAFE_ACTION`, plus state proof, blockers and the
handoff packet. Failure tails only — never full success logs, never repeated doctrine, never an
uncited repository claim.
