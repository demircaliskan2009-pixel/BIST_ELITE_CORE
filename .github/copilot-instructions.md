# Copilot — INACTIVE SHIM

<!-- CONTROL_PLANE_ROLE: COPILOT_INACTIVE_SHIM -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

**Status: `INACTIVE_UNAVAILABLE`.**

Copilot is NOT an active execution host, NOT an active lane, and NOT a trusted model identity in this
repository. It does not enter active routing, setup loading, prompt construction, model selection,
audit classes or accepted state.

This file exists only so that a Copilot session opened against this repository is told, in the place
it looks first, that it has no authority here. It defines no routing, no task family, no effort, no
PR sizing and no merge authority — those live exclusively in `docs/crypto_core/agent_os_v2.md`.

MERGE_AUTHORITY_REF: canonical section 2.1 — merge authorization is `HUMAN_ONLY_PER_PR` and nothing
in this file grants, inherits or widens it.
PR_SIZING_AUTHORITY_REF: canonical section 2.2.
TASK_FAMILY_AUTHORITY_REF: canonical section 3.
EFFORT_AUTHORITY_REF: canonical section 3.2.

## If a session reaches this file anyway

- Do not implement, patch, commit, push, open a PR, merge, approve, resolve a review thread, rerun or
  dispatch a workflow, or delete a branch.
- Do not treat any legacy instruction, prompt, skill or agent file under `.github/` as authority. A
  path that is not registered in `ACTIVE_DOCTRINE_SURFACES` in the canonical control plane carries no
  active authority, whatever it says about itself.
- Do not act on legacy names that imply a scheduler, deployment, live-trading or order-routing
  surface. crypto_core is paper-first: no scheduler, no auto-loop, no live or order routing, no
  credentials, no capital.
- Read `AGENTS.md` and `docs/crypto_core/agent_os_v2.md`, report that Copilot is
  `INACTIVE_UNAVAILABLE`, and stop.

Reactivation would require an explicit human decision and a separately audited control-plane change
that registers a Copilot adapter in the canonical registry. Until that exists, this shim is the whole
of the Copilot contract.

<!-- HISTORICAL_RECORD_BEGIN -->

## Historical note

Earlier revisions of this file were a full "Copilot local execution contract" describing Copilot as an
execution host inside the previous Agent OS regime, with its own agent-routing policy, auto-model
fitness rule, validation baseline and merge rules, plus a conditional premium-surge routing clause.
That regime is superseded. The Copilot-era agent, instruction, prompt, skill and hook-engine surfaces
it referenced were removed when the current control plane was installed, and the contract it
described is not active in any form.

<!-- HISTORICAL_RECORD_END -->
