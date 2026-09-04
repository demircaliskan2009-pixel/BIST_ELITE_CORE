# Copilot compatibility shim — INACTIVE

<!-- CONTROL_PLANE_ROLE: COPILOT_INACTIVE_SHIM -->

Authority derives from the canonical control plane `docs/crypto_core/agent_os_v2.md`. This file defines no routing, model-selection, PR-sizing or merge authority of its own.

**Copilot status: `INACTIVE_UNAVAILABLE`.** GitHub Copilot is not an active execution lane, not an
execution host for another model, and holds no mutation, merge, readiness, connector, live or capital
authority in this repository. It is inactive unless it is separately reactivated through an audited
workflow change that a human explicitly authorizes.

This file is a thin compatibility shim only. It is not doctrine and it grants nothing.

## Canonical authority

`CRYPTO_CORE_AGENT_OS_V2` — `docs/crypto_core/agent_os_v2.md` — is the single detailed active
control-plane authority. Precedence (`AGENT_OS_V2_PRECEDENCE`): `AGENTS.md` →
`docs/crypto_core/agent_os_v2.md` → the environment adapter
(`.codex/skills/crypto-core-max-safe/SKILL.md`, or `CLAUDE.md` +
`.claude/skills/crypto-core-token-efficient-loop/SKILL.md`) → `docs/crypto_core/agent_lessons.md`.
`docs/crypto_core/agent_workflow.md` is the workflow companion. New sessions bootstrap read-only from
`docs/crypto_core/continuity/CONTINUITY_INDEX.md`.

## What this shim explicitly does not authorize

- No autonomous execution. No agent daemon, scheduler, auto-loop or self-directed run.
- Never grants blanket mutation, blanket GitHub authority, or blanket merge authority. Every mutation
  needs an explicit human instruction naming the exact action and target.
- No active Claude Fable 5 lane — Fable is `INACTIVE_EXPIRED_RETIRED`. Claude Opus 4.8 is
  `SUPERSEDED_BY_OPUS_5`.
- No PR sizing by file count or LOC count. `MAX_SAFE_PR` is decided by semantic closure
  (`agent_os_v2.md` section 4).
- No restart-until-success loop. Blocker closure follows `BLOCKER_ESCAPE_PROTOCOL_V1`
  (`agent_os_v2.md` section 5); a semantic CI failure is repaired, never rerun.
- No direct push to `main`, no force push, no squash or rebase merge, no self-approval, and no merge
  without explicit per-PR human authorization.

## Retired legacy surfaces

The Copilot-era control plane has been removed and must not be reintroduced: `.github/instructions/**`,
`.github/agents/crypto-core-engineer.agent.md`, `.github/agents/crypto-product-auditor.agent.md`,
`.github/agents/crypto-throughput-commander.agent.md`, `.github/prompts/crypto-*.prompt.md`,
`.github/skills/crypto-*`, `.github/skills/_shared/references/contract-schema.md`,
`.github/hooks/hook-engine.md`, and the Copilot-era throughput protocol documents under
`docs/crypto_core/`. The hook JSON rule files `.github/hooks/pre-response.json` and
`.github/hooks/post-response.json` are NOT retired: they are loaded at runtime by
`src/bist_core/hooks/hook_engine.py`. Absence is enforced by
`scripts/crypto_core/validate_agent_os_v2.py` inside the required `tests` CI job.
