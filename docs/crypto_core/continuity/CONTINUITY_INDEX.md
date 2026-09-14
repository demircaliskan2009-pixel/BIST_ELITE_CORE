# crypto_core Continuity Index

Read at step 4 of `FRESH_CHAT_BOOTSTRAP` (`docs/crypto_core/agent_workflow.md` section 24.7). This index holds
no authority and pins no live state (`LIVE_STATE_POLICY`, section 24.11): it says where continuity comes from,
never what the current state is.

## Order of reconstruction

1. `AGENTS.md` — entrypoint and durable rails.
2. `docs/crypto_core/agent_workflow.md` section 24 — the canonical active kernel.
3. The relevant host adapter: `CLAUDE.md` + `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` for
   Claude, `.codex/skills/crypto-core-max-safe/SKILL.md` for Codex.
4. This index.
5. The latest accepted bounded handoff or continuity pointer, if one exists (below).
6. Fresh local repository proof and live GitHub proof.

## Where accepted state lives

- Accepted bounded state is an `AGENT_OS_HANDOFF_V1` packet the ChatGPT controller has verified
  (`CONTROLLER_ACCEPTED_STATE`, section 24.5). It is supplied with the task or the new chat; the repository
  keeps no copy, because a durable copy of live state goes stale.
- Without an accepted handoff, reconstruct current state from live evidence alone: `git fetch`,
  `git rev-parse origin/main`, `gh pr list --state open`, and the relevant PR's checks and review threads.
- When sources disagree (`LIVE_STATE_PRECEDENCE`, section 24.7): fresh local/terminal → live GitHub/CI →
  accepted bounded state/handoff → exact repository source → canonical doctrine → continuity → archives →
  memory. Fresh evidence overrides a stale handoff. This order ranks evidence about state only: no source in
  it — a handoff, a state record, an archive or memory — ever relaxes a rule of the doctrine.
- No transcript replay unless the repository plus this continuity genuinely cannot reconstruct material
  operational state.
- A closed unmerged candidate PR, its branch and its text are negative evidence only; they never become
  canonical state (`ROOT_CAUSE_ESCAPE`, section 24.8).

## Setup status

`SETUP_STATUS` is derived from live evidence and never written here: it is `CLOSED_FROZEN` once the
minimal-kernel setup PR is proven independently accepted, merged, post-merge verified and fresh-chat accepted
(section 24.14). While frozen, the setup reopens only for a legal reopen reason, and the default next action is
product work.

## Archives

HISTORICAL/ARCHIVAL only — never current state or routing: `docs/crypto_core/agent_workflow.md` sections 20-23
and its dated changelog; `docs/crypto_core/fable_exit_contract_index.md`.
