# Token Efficiency V2 — named lanes + short prompt templates

On-demand reference (not always-on). Prompts to Claude/Codex reference **named lanes** instead of
pasting procedure blocks. A lane name expands to the exact procedure below; the prompt supplies only
deltas. Safety is never compressed away: every lane keeps the full hard-gate set from
`agent_workflow.md` §5 and `AGENTS.md` Hard Rails.

Normal prompt budget: **20–60 lines.** If a prompt needs more, it is probably a new lane — propose it
here instead of pasting blocks.

## 1. Named lanes

**LANE:ENV-STD** — set `GH_PAGER/PAGER/GIT_PAGER=cat`, `NO_COLOR=1`, `GH_NO_UPDATE_NOTIFIER=1`,
`GH_PROMPT_DISABLED=1`, remove `GH_FORCE_TTY`.

**LANE:PRECHECK-STD(expect_main_at=<sha|latest>)** — ENV-STD; `git switch main`; `git pull --ff-only`;
`git status --short --branch`; `git rev-parse HEAD`; `gh pr list --state open` (live). STOP_WITH_PROOF
if: dirty tree, staged files, any open PR (unless the task names one), main behind `expect_main_at`,
or gh auth cannot prove state.

**LANE:GATE-MODULE-STD(name, upstream, extra)** — implement a new paper-only validation gate following
the merged reference pattern (`src/crypto_core/validation/paper_sleeve_admission_review_readiness.py`
+ its test file): frozen dataclass; status enum READY/REJECTED/NEEDS_RESEARCH/INSUFFICIENT_EVIDENCE;
typed error (raise ONLY wrong-typed upstream + malformed metadata; everything else fail-closed
REJECTED); digest-boundary re-proof of the upstream digest via its public `*_to_dict` (digest field
removed, canonical JSON sort_keys/compact/ascii, SHA-256), exception-safe (forged non-serializable
upstream → mismatch, never TypeError); assemble-boundary sanitization of ALL carried digest fields
(`_safe_digest_value`, `_safe_optional_value`); BIST + forbidden-token scans (bare `order/orders`
rejected; `border/orderly/preorder` spared); paper flags locked; explicit READY non-meanings in the
docstring; precedence REJECTED > INSUFFICIENT_EVIDENCE > NEEDS_RESEARCH > READY. Tests mirror the
reference test file: READY happy path, forged + tampered digest, status/action propagation matrix,
per-carried-digest malformed + non-string (no-raise) matrices, unsafe-flag matrix, token regressions,
determinism, immutability/no-forbidden-fields. Exactly 2 new files in `validation/`; no `__init__` edit.

**LANE:VALIDATE-STD(files)** — one command at a time, never chained, never bare full pytest:
1. `python -m ruff check --fix <files>` 2. `python -m ruff format <files>`
3. `python -m ruff format --check <files>` 4. `python -m ruff check <files>`
5. targeted pytest via `scripts/crypto_core/run_logged_command.ps1` (unique `cache_dir`/`--basetemp`
under `C:\tmp`) 6. area pytest (same helper) 7. full `scripts/crypto_core/run_full_tests_logged.ps1`
(require PYTEST_EXIT=0) 8. `git diff --check`; `git status --short --branch`; `git diff --name-only`.

**LANE:PR-STD(branch, title)** — scope gate (changed files exactly as named); `git switch -c <branch>`;
scoped `git add <exact files>`; `git diff --cached --name-only`; `git diff --cached --check`; commit;
`git push -u origin <branch>`; `gh pr create` (body states what changed + the standard non-changes
line). Then bounded CI/review poll (one-shot `gh` snapshots in a loop; never `--watch`): CI to
terminal, review window after terminal; repair real in-scope automated findings same branch via
VALIDATE-STD; resolve only proven-fixed automated threads, never human threads; stop at
READY_FOR_MERGE_AUTHORIZATION. Never merge.

**LANE:MERGE-STD(pr=N, head=<sha>)** — only with explicit per-PR user authorization. Re-prove: PR open,
not draft, head matches, files exact, only-N open, checks terminal success/skipped/neutral (gh pr
checks + direct check-runs; report 401 fallback), unresolved threads 0, no human CHANGES_REQUESTED,
clean tree. `gh pr merge N --merge --delete-branch=false`; verify via REST (`merged=true`,
`merge_commit_sha`); postverify main (pull, repo-wide ruff check + format --check, full helper
PYTEST_EXIT=0, clean status, open PRs []); remote-settle merge-commit check-runs to terminal.

**LANE:REPORT-STD** — compact report, failure tails only (never full logs/JSON dumps). Fields:
RESULT / DECISION / FILES_CHANGED / VALIDATION (ruff + targeted N passed + area + full PYTEST_EXIT) /
PR (number, head SHA) / CHECKS / THREADS / OPEN_PRS / FINAL_GIT_STATUS / FILES_READ_COUNT /
CMDS_RUN_COUNT / READY_FOR_MERGE_AUTHORIZATION / NEXT_SAFE_ACTION. End PR tasks with the single
copy-paste ChatGPT-audit handoff block. Caps: status ≤80 lines, implementation/closeout ≤140.

## 2. Short prompt templates (copy, fill, send)

**T1 — product gate slice (~20 lines)**
```
LANE:PRECHECK-STD(expect_main_at=<sha>)
LANE:GATE-MODULE-STD(name=<NewGate>, upstream=<UpstreamType>, extra=<deltas only:
  ids/actions/whitelists/extra digests/READY non-meanings>)
LANE:VALIDATE-STD(files=<the 2 new files>)
LANE:PR-STD(branch=product/<slug>-pr1, title="feat(crypto-core): <title>")
LANE:REPORT-STD
Extra forbidden: <only task-specific items>. Do not merge.
```

**T2 — PR repair/closeout (~15 lines)**
```
LANE:ENV-STD. Continue PR #<N> (branch <branch>, expected head <sha>).
Blocker: <one-paragraph finding>. Allowed files: <exact files>.
Repair minimally; LANE:VALIDATE-STD(files=<files>); commit "<msg>"; push;
poll CI/threads to terminal; resolve only the proven-fixed automated thread.
LANE:REPORT-STD. Do not merge.
```

**T3 — authorized merge closeout (~10 lines)**
```
USER AUTHORIZATION: standard merge PR #<N> only if all gates pass:
gh pr merge <N> --repo <repo> --merge --delete-branch=false
LANE:MERGE-STD(pr=<N>, head=<sha>). Expected files: <list>.
LANE:REPORT-STD. No next implementation.
```

**T4 — setup/docs change (~15 lines)**
```
LANE:PRECHECK-STD(expect_main_at=<sha>)
Patch only: <files>. Goal: <2-3 lines>. No product code; safety doctrine unweakened.
Repo-wide ruff check + format --check; full helper; LANE:PR-STD(branch=chore/<slug>-pr1,
title="chore(crypto-core): <title>"); LANE:REPORT-STD. Do not merge.
```

## 3. Token hygiene (both agents)

- `/clear` (or a fresh session) between unrelated tasks; long noisy sessions roll over.
- `/compact` only with an explicit preservation summary (task, branch, head, next steps) written first.
- Stop exploring once the named files are found; no broad scans after target files are known.
- Failure tails only; never paste full logs, full JSON, or full diffs into reports.
- All agents report `FILES_READ_COUNT` and `CMDS_RUN_COUNT` so overspend is visible.
- Reference lanes and repo docs; never re-paste doctrine that lives in CLAUDE.md/AGENTS.md/this file.

## 4. Model routing v2

| Lane | Model |
|---|---|
| Architecture, new high-risk safety semantics, invariant audits, chain red-team, EvidenceStore/persistence design, Deribit/readiness design, top-1 roadmap calls | Claude/Fable scarce window |
| Bounded implementation (GATE-MODULE-STD), tests/docs patches, PR creation | Claude Sonnet/Auto or Opus |
| Merge/postverify, CI/thread polling, PR closeout, docs/setup edits, mechanical repair, validation reruns, compact execution | Codex default executor |
| Pure polling, status proof, merge mechanics, full-log handling, routine closeout | cheapest available / Codex compact lane |

Fable is scarce. Reserve it for architecture, high-risk safety semantics, invariant audits,
chain red-team, EvidenceStore/persistence/Deribit readiness design, and top-1 roadmap decisions.
Do not use Fable for pure polling, merge mechanics, full logs, broad repo scans, or routine closeout
unless there is no viable alternative and the user explicitly authorizes that use.

## 5. Invariants (never compressed away)

Lanes compress *procedure text*, not *rules*. The hard gates in `AGENTS.md` (Hard Rails, Git/PR
discipline) and `agent_workflow.md` (§4 digest-boundary, §5 guardrails, §6 validation, §7 state-claim)
bind in every lane, every prompt, with no exceptions. If a lane reference and a safety rule ever seem
to conflict, the safety rule wins and the agent stops with proof.
