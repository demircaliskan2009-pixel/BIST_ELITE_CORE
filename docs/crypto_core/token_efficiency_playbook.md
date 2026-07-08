# Token Efficiency Playbook (crypto_core agents)

Purpose: make Claude/Codex spend fewer tokens by default WITHOUT weakening reasoning depth on
high-risk work, safety gates, audit depth, deterministic proof, or CI/Connector/Codex/human merge
discipline. **Token saving is always subordinate to correctness.** No gate may ever be skipped,
no audit shallowed, and no state claimed unproven to save tokens. Stop early with proof rather
than guess. Token savings are never evidence.

## 1. Task classes and context budgets

| Class | Task type | Lane | Context budget |
|---|---|---|---|
| T0 | Status / CI snapshot / hygiene | Sonnet/Fast Auto | Exact status commands only; no source reads unless the status question requires one; compact report |
| T1 | Docs / mechanical setup | Sonnet/Fast (strategic setup design may use the strongest available lane) | Changed docs + directly relevant workflow sections only; open source files only when a doc claim cites them; targeted validation |
| T2 | Normal bounded implementation | Opus 4.8 (Sonnet for low-risk mechanical parts) | Named files first; symbol map (`rg`/Grep) before full-file reads; targeted tests, then full suite where merge doctrine requires |
| T3 | High-risk contract / digest / fail-closed source work | Opus 4.8 xhigh — never lowered to save tokens | Explicit invariant map + exact file scope BEFORE editing; Codex P1/P2 design audit BEFORE implementation; full validation ladder; no token shortcut of any kind |
| T4 | External / current facts | Deep Research (advisory only) | Citations required; nothing becomes a repo rule until converted to a governance contract; unverifiable facts stay `UNPROVEN` |

## 2. Context intake protocol (every Claude/Codex task)

1. Prove repo state first (`git`/`gh` snapshot) — never from memory.
2. List the files you intend to read BEFORE reading; justify anything beyond the named set.
3. Read the current diff before the repo; read symbols (`rg`/Grep with line anchors) before whole files.
4. Summarize the discovered surface ONCE (a "source surface map"); work from the map, not rereads.
5. Do not reread unchanged docs unless HEAD/hash changed since the last proof.
6. If context grows too large, compact into the surface map and continue; if required information
   is missing, STOP_WITH_PROOF instead of expanding the scan blindly.

## 3. Report compression protocol

- Fixed fields only; verdict first; then scope / changed files / validation / CI / PR evidence.
- P1/P2/P3 classification where relevant; exact next safe action once; no settlement loops.
- No long narrative, no transcript dumps, no repeated doctrine unless it changed, no long external
  quotes, failure tails only (never full logs).

## 4. Prompt reuse protocol

- Stable procedure text lives in repo docs/skills — controller prompts send only task deltas plus
  references to stable docs (`AGENTS.md`, `agent_workflow.md` §§, this playbook, contract index).
- Never re-paste full Fable-era contracts; reference `docs/crypto_core/fable_exit_contract_index.md`.
- High-risk slice prompts include the invariant checklist, never the historical transcript.
- Implementation prompts stay strong but bounded: exact files, exact invariants, exact validation.

## 5. Model-lane budget matrix

- Opus/Codex are NEVER used for: CI polling, `git`/`gh` status, ruff/format-only runs, merge
  mechanics, post-merge verification, trivial docs edits.
- Sonnet/Fast owns all mechanical work. Codex reads changed files + direct dependencies only,
  never re-reads the whole repo per audit, and never polls CI with model tokens.
- Bounded one-shot CI snapshots only (never `--watch`); pending/queued/in-progress = NOT_READY.

## 6. Anti-patterns (each is a real observed waste class)

- Full-file reads where a symbol grep answers the question.
- Re-proving unchanged repo state inside one session without a head change.
- Expensive-lane status polling; expensive-lane mechanical merges.
- Reports that restate doctrine or paste full logs/transcripts.
- Prompts that carry the whole workflow doc instead of referencing it.
- Broad recursive scans without a named justification.
- Duplicating instructions across `AGENTS.md` / `CLAUDE.md` / skills (see §8 of the setup PR:
  do not add new duplication; link instead).

## 7. Non-regression checks (bind unchanged; token rules never override)

One open PR; no direct `main` push; no admin/squash/rebase; no merge without explicit human
authorization; pending CI = NOT_READY; Codex P1/P2 design audit before high-risk implementation;
Codex implementation audit before the connector gate on high-risk PRs; GitHub-connector final gate
never waived; full logged test suite where required (`run_full_tests_logged.ps1`); crypto_core-only
scope; no BIST implementation; fail-closed always.

## 8. No-overclaim

Nothing in this playbook proves repo/PR/CI state, Stage-4 completion, machine-time origin,
secondary-metrics enforcement, readiness of any kind, or edge/profitability. Compact reports must
still carry the same proof density — fewer words, identical evidence.
