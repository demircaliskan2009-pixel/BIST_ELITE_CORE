# crypto_core Agent Workflow — Model-Agnostic Companion

<!-- CONTROL_PLANE_ROLE: WORKFLOW_COMPANION -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **What this document is.** The executable lifecycle mechanics for `crypto_core` inside
> `demircaliskan2009-pixel/BIST_ELITE_CORE`: git and PR lifecycle, validation mechanics, CI polling,
> post-merge mechanics, evidence and report mechanics, stop conditions, and the generic
> implementation / repair / review lifecycle.
>
> **What this document is NOT.** It is deliberately MODEL-AGNOSTIC. It owns no active model-to-task
> routing, no task-family ownership, no effort selection, no merge authority and no PR-size authority,
> and it names no model as a lifecycle step. Those all live in the canonical control plane,
> `docs/crypto_core/agent_os_v2.md`, which is the single active authority. Where this companion and
> the canonical control plane appear to differ, the canonical control plane wins; between two safety
> rules the stricter wins.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> This document contains no secrets, credentials, API keys, exchange credentials or live-trading
> instructions, and it instructs no real order flow.

## 1. Purpose

Persist one command-level, auditable workflow so every turn does the maximum safe work its
authorization allows, while preserving the crypto_core standard: paper-first, deterministic,
fail-closed, audit-first, derivatives-first, governance-first, risk-bounded. Active scope is
`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core` and `docs/crypto_core` only. BIST is
historical context and is never implemented here.

## 2. Roles by function

Roles here are FUNCTIONS, not models. Which runtime performs a function is decided only by the
canonical routing matrix, and it may change without this document changing.

| Function | Responsibility |
|---|---|
| **Controller** | Sequence owner. Live state proof, evidence comparison, task classification, prompt compilation, conflict resolution, merge-READINESS judgement, and exactly one next action. Read-only first. Never a merge-authority origin. |
| **Implementer** | The single repository writer for one authorized slice. Proves local state, patches only the allowed files, validates, publishes one PR, hands off, and stops at the gate. |
| **Independent reviewer** | Fresh-context, pinned-head adversarial review producing P1/P2/P3 findings with exact source evidence and zero mutation. Never the same context that implemented the work. |
| **Mechanics** | Bounded status, polling, metadata, and already-authorized execution. No semantic readiness or design judgement. |
| **Research** | External and current facts only. Read-only and advisory. Never an executor, never merge authority, never a gate waiver. |
| **Human** | The sole origin of per-PR merge authorization, and the owner of every governance threshold. |
| **Terminal, `git`, `gh`, connector** | Source of truth for state. An editor extension is a helper, never authority. |

An implementation context never satisfies its own independent review. Current valid P1/P2 threads
block. Outdated threads do not block code, but any resolution needs explicit guarded closeout
authority, and a human thread is never self-resolved.

## 3. Hard rules

- crypto_core only; no BIST implementation leakage.
- **One open PR at a time.** Verify it live (`gh pr list --state open`) at the start of every task.
- **One repository writer at a time.** No concurrent patching, no second branch and no worktree
  writer for the same objective.
- **No direct push to `main`.** No force-push, no rebase, no squash, no history rewriting. No branch
  deletion unless the authorized command says so.
- **Standard merge only**, and only under the canonical merge-authority rule. No merge without
  explicit human authorization naming the PR and the exact command, for that exact head.
- **CI `pending` / `queued` / `in_progress` / `no checks reported` is NOT_READY.** Poll to a terminal
  state, or report a bounded-timeout snapshot. A startup window is never green.
- **CI not registered for a fresh head: diagnose before re-triggering.** Prove it from `gh run list`
  or the commit check-runs and classify infrastructure delay against a trigger, path or ref problem.
  At most ONE empty re-trigger commit, and only with explicit authorization. Never loop no-op commits.
- **Branch naming:** feature slices `feature/<crypto-core-scope>-prN`; setup and docs
  `chore/<crypto-core-scope>-prN`. A repair for the same PR stays on the SAME branch.
- **Setup and doctrine changes are never mixed into a feature PR.** Feature PRs touch product code;
  setup PRs touch docs, configuration and setup tooling.
- **Independent review is asynchronous** and is a separate gate. An implementation or repair turn ends
  at terminal CI plus its report; it does not block waiting for review.
- Every repository claim is `git`, `gh` or test verifiable. Never from memory. Unproven is `UNKNOWN`.
- **Same-branch repair only** for a valid in-scope P1/P2. Stop on unsafe scope expansion.
- No live or private API, real orders, order routing, scheduler, auto-loop, connector or readiness
  transition, runtime or orchestrator surface, or shadow and live execution unless explicitly scoped
  and separately designed.
- No hidden IO, environment access, randomness, wall-clock or threading in product code unless
  explicitly scoped.
- No self-approval, ever.
- **Digest-boundary rule (recurring P1 class):** a consumer of a digest-carrying object recomputes the
  upstream digest through the PUBLIC serializer — self-digest field removed, canonical JSON with
  `sort_keys=True`, `separators=(",",":")`, `ensure_ascii=True`, `allow_nan=False`, SHA-256 — and
  rejects a mismatch BEFORE any READY, ADMITTED or ACCEPTED transition. A matching id is never
  sufficient. Forged or non-serializable input must reach the explicit mismatch path, never a raw
  `TypeError`. Tests must include a tampered-field case.

### Dependabot collision prevention

- Scheduled version-update PRs are disabled for all configured ecosystems with
  `open-pull-requests-limit: 0`. This does NOT disable alerts or security-update PRs.
- Ordinary dependency updates are admitted only through a dedicated maintenance slice with zero
  pre-existing open PRs, following normal branch, validation, review and authorization gates.
- Scheduled version updates are never temporarily re-enabled while an active crypto_core PR exists.
- An automatically generated security-update PR is an externally generated urgent input requiring
  triage. It never silently waives one-open-PR and never authorizes concurrent implementation, and no
  security finding is dismissed by this rule.

## 4. Standard PR lifecycle

1. The controller selects one coherent semantic slice, sized by the canonical PR-sizing rule, and
   compiles one implementation prompt with the pinned expected base and the proven open-PR state.
2. The implementer runs the implementation loop (section 5), opens one PR, polls CI to terminal, and
   reports. No merge.
3. Independent review runs asynchronously (section 8).
4. The controller verifies live state and issues a repair, a merge-readiness verdict, or the next
   prompt (section 9).
5. The implementer runs the repair loop (section 6) on the same branch when instructed.
6. The closeout loop (section 7) runs ONLY from an explicit closeout authorization.
7. Post-merge verification (section 12) runs, then the next slice is selected (section 15).

## 5. Implementation loop

```
# precheck on updated main - for base and SHA proof ONLY; main is never edited or committed on
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD                         # MUST equal the prompt's expected SHA
git status --short --branch                # MUST be clean and in sync
gh pr list --repo demircaliskan2009-pixel/BIST_ELITE_CORE --state open --json number,title,headRefName,baseRefName,url   # MUST be []

# create and switch to a topic branch BEFORE any patch, commit or push
git switch -c <topic-branch>               # feature/<crypto-core-scope>-prN or chore/<crypto-core-scope>-prN
git status --short --branch                # confirm: on the topic branch, clean
# patch only after this point
```

**Branch invariant (always holds).** `main` is checked out ONLY for precheck and base-SHA proof —
never edited, never committed on. The topic branch is created before the first edit. All commits and
pushes happen on the topic branch. The PR is opened from the topic branch into `main`
(`gh pr create --base main --head <topic-branch>`).

Then, all on the topic branch: bounded read of the named files → design → the patch that closes the
authorized semantic contract within the exact allowed files → self-check (scope, digest re-proof,
provenance, strict decimal arithmetic, fail-closed behavior, no hidden IO, paper-safety) → targeted
tests → the relevant suite → the logged full suite when the change warrants it → `git diff --check` →
scoped `git add <exact paths>` → commit → push → `gh pr create` → poll CI to terminal → inspect the
review threads that exist → report. **No merge.**

The self-check above is implementation QA. It is never an independent audit and is labelled
`SELF_AUDIT_ONLY_NOT_INDEPENDENT` wherever it is reported.

## 6. Repair loop

- Precheck first: branch, `HEAD` equals the expected SHA, clean tree, exactly one open PR, changed
  files inside scope.
- Pin the PR number and the expected head. Repair ONLY the named blockers, on the SAME branch, bounded
  to the named files.
- Test-only by default. Touch production code only when a new failing test proves a real defect, and
  only inside the named module. If the repair is test-only, prove `git diff <prev> HEAD -- src/` is
  empty.
- Re-validate fully — targeted, then the relevant suite, then the logged full suite with
  `PYTEST_EXIT=0`, then `git diff --check` — scoped add, commit, push the same branch, re-poll CI to
  terminal, report. **No merge.**
- One consolidated repair per audit cycle, then one whole-contract reaudit. A remaining genuine P1/P2
  after that is `FIXED_POINT_NOT_REACHED` and the contract freezes (canonical section 13).

## 7. Closeout loop

Runs ONLY from an explicit closeout authorization that names the PR and the exact authorized command.

- Re-prove freshly, from no memory: `HEAD` equals the authorized SHA; `state == OPEN`;
  `mergeable == MERGEABLE`; `mergeStateStatus == CLEAN`; changed files equal the expected set; CI
  terminal SUCCESS; exactly one open PR; zero unresolved valid review threads.
- Resolve ONLY the review threads the closeout authorization names, and only after proving the fix
  exists in source at the current HEAD with a line citation. Never self-resolve otherwise, and never
  resolve a human thread.
- Merge with the exact authorized command (standard `--merge`, `--delete-branch=false`).
- **On a transient API error, timeout or empty output: do NOT blind-retry.** Verify first with
  `gh pr view <#> --json state,mergedAt,mergeCommit,mergedBy,headRefOid` and
  `git rev-parse origin/main`. If merged, continue to section 12. Otherwise report
  `MERGE_TRANSIENT_NOT_MERGED` and stop.
- If the PR is already merged before the merge command (a stale authorization), do nothing, verify
  `main` contains the merge commit, and continue to section 12.

An authorization is consumed by the merge it authorized. A new head or a new PR needs a new one.

## 8. Independent review protocol

- Review runs asynchronously after a push; findings may not exist when the implementation turn ends.
  The implementer inspects the threads that exist at terminal CI and reports "0 threads (review may
  post later)" when there are none.
- Inspect via GraphQL: `reviewThreads(first:n){ nodes{ id isResolved isOutdated path line comments } }`
  plus `reviews`.
- The review emits the report format in section 10. The controller relays valid findings, with thread
  ids, as a dedicated repair prompt. The implementer does not wait in-turn for review.
- The review collects the COMPLETE current blocker set for the whole contract before any repair
  begins; it does not stop at the first finding (canonical section 13).

## 9. Controller gate

The controller independently re-verifies live state — head SHA, changed files, checks as
`name=conclusion`, threads, and the one-open-PR rule — before any verdict, and issues exactly one next
prompt. A merge-readiness verdict is not a merge authorization: the authorization itself comes from
the human, names the PR and the exact command, and is bound to that exact head.

## 10. Required report formats

**Implementer (every task)** — fixed fields, every repository claim `git`, `gh` or test verifiable:

```
RESULT / PR / HEAD_SHA / BRANCH / FILES_CHANGED / COMMITS / VALIDATION / CHECKS /
REVIEW_THREADS / SCOPE_CONFIRMATION / FINAL_GIT_STATUS / BLOCKERS / NEXT_SAFE_ACTION
```

The LAST element of every implementer message is a single self-contained, copy-paste controller
handoff code block: repo; PR number and state; branch, head SHA, base SHA; files changed; commits;
checks; review threads; validation commands and results; open-PR state; and the exact `gh` and `git`
commands that verify every claim. No full success logs — failure tails only. No uncited state.

**Independent review:**

```
VERDICT / P1_BLOCKERS / P2_BLOCKERS / NON_BLOCKING_NOTES / MERGE_READINESS / REQUIRED_REPAIRS_IF_ANY
```

**Controller verdict:**

```
VERDICT / PROOF / REASON / NEXT_PROMPT
```

## 11. Merge gate

Merge only when ALL of these are true, each freshly proven: `HEAD` equals the authorized SHA; the PR
is `OPEN`; `headRefOid` equals the authorized SHA; the changed files equal the expected set; exactly
one open PR and it is this one; CI checks are terminal SUCCESS - a `skipped`, `neutral` or
`cancelled` load-bearing check is never acceptance (canonical section 17.1) - with no pending,
queued, in-progress or missing checks; zero unresolved valid review threads; the working tree is
clean; any test-only repair is proven to have no product-code change; no forbidden-scope surface
(section 16); no protected-contract weakening; and explicit human authorization naming the PR and the
exact command. Any miss stops with proof and does not merge.

## 12. Post-merge verification (exact commands)

```
git switch main
git pull --ff-only origin main
git rev-parse HEAD                                                   # == merge commit SHA
python -m ruff check  src/crypto_core tests/crypto_core scripts/crypto_core
python -m ruff format --check src/crypto_core tests/crypto_core scripts/crypto_core
python scripts/crypto_core/validate_agent_os_v2.py
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_full_tests_logged.ps1   # require PYTEST_EXIT=0
git diff --check
git status --short --branch
gh pr list --repo demircaliskan2009-pixel/BIST_ELITE_CORE --state open --json number,title,headRefName,baseRefName,url   # expect []
```

The committed CI workflow invokes the control-plane validator and the independent contract-oracle
anchor. That the file SAYS so is not proof that the steps RAN: no repository can establish its own
CI execution from its own bytes. Before merge readiness the controller re-proves, from live GitHub
evidence at the exact head, the run and its source workflow, the `tests` job conclusion, and the
actual conclusion of those two steps; `skipped`, `neutral` and `cancelled` are never acceptance.
The full protocol and the authority split are canonical section 17.1.

The full-suite log is UTF-16 and may not carry the `N passed` line; the authoritative success signal
is `PYTEST_EXIT=0`. Full crypto_core tests run ONLY via `run_full_tests_logged.ps1`, never a bare full
pytest; targeted runs go through `run_logged_command.ps1`; commands run one at a time; staging is
scoped to exact paths.

## 13. Stop conditions (hard — stop with proof, no mutation)

Wrong repository · non-crypto_core scope · unexpected PR or head (`HEAD` not equal to the expected
SHA) · more than one open PR when creating a PR · dirty overlapping files the task does not own ·
a requested repair outside the allowed files · live, private, order, scheduler, connector, runtime,
shadow or live leakage · hidden IO, environment, randomness or subprocess not scoped · a failing
required validation or full-suite helper · an unresolved valid review thread at the merge gate ·
pending CI at the merge gate · a direct `main` push · a force-push · self-approval · a merge without
exact human authorization · an external or current fact required · the required runtime identity
cannot be proven, a fallback occurred, or the proof is contradicted · the protected frontier lane is
required but unavailable.

## 14. Warning-not-stop conditions (proceed, but note)

A transient API error or timeout — verify state once and continue · CI reporting no checks
immediately after a push, which is the startup window, so keep polling · a non-zero exit from
`gh pr checks` while checks are pending, which is not a failure · `mergeStateStatus: BLOCKED` caused
solely by unresolved threads on an otherwise green PR, which is expected pre-merge · a formatter
reformatting your own new files, or an unused-import finding — format, then check, then continue ·
unrelated dirty files the task does not own — do not stage or revert them; report and scope around ·
the UTF-16 full-suite log, where `PYTEST_EXIT` is authoritative.

## 15. Next-slice selection rule

The controller selects exactly one coherent semantic slice that maximizes edge-to-money product value
along the chain `StrategySpec → LBR → PIT/DataRequirement → DecisionLedger → EvidenceStore →
BacktestAdmission → Replay → PaperSleeve → Promotion → Allocator → ExecutionSim`, with: one coherent
theme; bounded named files; independent-safe boundaries; testability; proven current state; no
hard-gate violation; and paper-first staging with no live, order or scheduler stage.

The slice is sized by semantic closure (canonical section 2.2) — the largest change that closes one
coherent contract together with its dependency closure, negative cases, permanent tests, validation
and rollback. It is never sized by file count, and it is never split merely to make a PR look small.
One open PR only. The integration-first slice sequence and its guardrails live in the addendum
`docs/crypto_core/paper_trading_phase_map.md`; PRDV4 remains the product authority.

### 15.1 Waiting on an unavailable gate

A frozen head waiting only on a gate that cannot currently run is not a reason to idle, and not a
reason to churn. The mechanics, all binding together:

- The frozen head is immutable while waiting, and is never mutated merely to look busy.
- No merge without its required gate.
- One repository writer and one open PR remain absolute. A second PR is NOT opened while the frozen
  PR is open.
- Genuinely dependency-safe next work MAY be implemented on a prepared implementation branch, with
  its base and provenance recorded, when the pending verdict cannot make that work semantically
  invalid. Such a branch is prepared, not reviewable, until the preceding PR or gate resolves.
- On resolution, re-prove ancestry, base and dependencies before opening a PR for prepared work. If
  the preceding work was rejected or changed materially, the prepared work is stale and is never
  silently promoted.
- Never manufacture work to appear busy. An empty queue is an honest answer, and so is a genuine
  stop.

The full policy, including which lane picks up the continued work, is canonical section 10.4.

## 16. Forbidden scope

Forbidden unless explicitly authorized and separately designed: live or private API; credentials,
secrets or API keys; real orders; order routing; scheduler; auto-loop; connector or readiness
transition; runtime or orchestrator surface; shadow or live execution; fills; PnL; positions; venue
or order-id surface; persistence, file, network or environment IO added to product code; a backtest or
replay engine unless that is the objective; an evidence store or persistence layer unless that is the
objective; and any BIST behavior. No document and no future prompt may include account tokens,
credentials, exchange keys, private local machine configuration, or live-trading and real-order
instructions.

## 17. Controlled self-improvement loop

Lessons are persisted, not improvised. The full procedure and the running ledger live in
`docs/crypto_core/agent_lessons.md`. Summary:

- Each real P1/P2 — a review finding, a CI failure, or a post-merge defect — emits a
  `LESSON_CANDIDATE` in the handoff block, citing the PR, the commit and the failure mode or the
  asserting test.
- The controller triages durability, generalizability and proof. Transient branch, CI or commit state
  is never a durable lesson.
- Accepted lessons are added to the ledger ONLY in a separate setup PR, never mixed into a feature PR.
- No lesson may weaken a safety gate (sections 3 and 16). No automatic self-modification during a
  feature PR. Stale or conflicting instructions are removed or repointed to canonical doctrine.

## 18. Doctrine precedence and legacy surfaces

Active doctrine precedence is defined in the canonical control plane, which also holds the exact
registry of every active surface, every host adapter and every retired path. This companion is
subordinate to it.

A path that is not registered as an active doctrine surface carries NO active authority, whatever it
says about itself. Legacy material under `.github/prompts`, `.github/skills`, `.github/instructions`,
`.github/agents`, `.cursor/rules`, and any BIST or PRDV3 content is historical or assistant-specific
and is overridden by canonical doctrine wherever it conflicts. In particular, a legacy name that
implies a scheduler, deployment, live or order-routing surface authorizes no such behavior here:
crypto_core is paper-first, with no scheduler, no auto-loop and no live or order routing.

MCP is opt-in and manual, and none is enabled by default (`.vscode/mcp.json` declares no servers). Any
future server must be pinned, read-only or local, and explicitly approved. The terminal, `git`, `gh`,
pytest and the linter are the source of truth; editor extensions are helpers
(`.vscode/extensions.json` lists recommendations only and installs nothing).

## 19. Research protocol pointer

External and current facts are governed by canonical section 8, with the full protocol in
`docs/crypto_core/deep_research_protocol.md`. Two mechanics matter for this workflow: research is
strictly read-only and never mutates repository or GitHub state even when the underlying work is
authorized; and a research result never justifies skipping a test, a CI gate, an independent audit or
an explicit human merge authorization. External best practice that conflicts with repository safety
doctrine is a proposal only — the stricter safety rule wins.

---

Everything below this line is a dated HISTORICAL RECORD of superseded operating regimes, preserved
verbatim as evidence. It is bounded by explicit structural markers and is NOT active routing, NOT
current state and NOT current authority. It is never read as an instruction, and it is never
rewritten to name different tooling than it originally named.

<!-- HISTORICAL_RECORD_BEGIN -->

## 20. HISTORICAL / SUPERSEDED BY GPT-5.6 ROUTING DOCTRINE - Fable 5 era

Fable 5 (`claude-fable-5`) is available as a model tier for the local Claude agent. **Model strength is not
proof**: no lane — however strong — replaces evidence, tests, CI, Codex review, the GitHub-connector final
gate, or explicit per-PR merge authorization. Official Fable 5 limits / quota / safety-routing / pricing are
**UNPROVEN** in this repo — treat availability limits as a user-reported operational constraint and never
state official policy without proof.

**As of 2026-07-07, Fable 5 availability is NO LONGER ASSUMED.** §20 applies only opportunistically when
Fable 5 happens to be present; no plan, prompt, schedule, or roadmap step may depend on it. Whenever Fable 5
is absent, **§21 (Post-Fable Operating Model) governs routing** — same hard gates, re-routed lanes.

### 20.1 Lane routing — Fable 5 / Opus 4.8 / Fast Auto / Codex / Connector / Deep Research

- **Fable 5 — premium high-reasoning lane (use FIRST when available).** Route to Fable 5: repo-wide
  reasoning/design; Stage-4 governance and design (especially `PaperStage4ComparisonEvidence` design and the
  first authorized `compare_stage4` use planning); Decimal-vs-float correctness; fail-closed semantics;
  digest/provenance correctness; adversarial P1/P2 audits; reasoning about CodeQL/Codex findings;
  readiness/live/Deribit overclaim audits; artifact-boundary reviews; cross-document contradiction
  detection; phase-order decisions; high-risk prompt generation; workflow/router redesign; final semantic
  review before the connector gate. Deliberately spend Fable 5 budget on this class of work.
  **Never spend Fable 5 on:** `git status` / `gh pr view` / `gh pr checks` / CI polling; ruff/format-only
  runs; simple pytest loops; standard merge / post-merge verification; trivial typo fixes; mechanical docs
  edits; routine file search; output formatting. The scarce-window spirit of `LANE:FABLE-ARCH`
  (`agent_prompts/token_efficiency_v2.md`) carries over unchanged; this section **supersedes its
  consult-only framing** — when routed here, Fable 5 may run as the full local executor (tools, patches,
  PRs) under all existing gates.
- **Opus 4.8 (xhigh) — implementation / repair / fallback lane.** Bounded validation-module implementation;
  complex repair after Fable/Codex/CodeQL findings; **fallback whenever Fable 5 is unavailable, blocked, or
  quota-exhausted**; long implementation loops where Fable 5 would be too expensive; same-turn same-branch
  repair loops within one PR.
- **Fast Auto / Sonnet — mechanical lane.** Git hygiene; CI polling (bounded one-shot snapshots, never
  `--watch`); `gh` checks / review-thread proof; ruff/format/test execution; standard merge and post-merge
  verification; status reports; branch closeout; non-semantic docs mechanics.
- **Codex — independent audit / second-opinion lane.** Read-only adversarial P1/P2 audit and second opinion
  on Claude-authored PRs; workflow/prompt consistency audit; repair suggestions only after evidence.
  **Never** patches the same PR concurrently with Claude; Claude prompt grammar and Codex prompt grammar are
  **never mixed** in one prompt; Codex is not the primary implementation lane while Fable/Opus is available;
  Codex never merges (§2, §2a, §8 bind unchanged).
- **GitHub connector — source-of-truth FINAL merge-readiness gate.** Mandatory before merge authorization —
  **never waived**: re-verifies PR metadata, head, files, checks, reviews, threads, and code scanning. If
  the connector app itself is unavailable, the **same** final gate runs via `gh`-native commands (the §2
  "GitHub connector / gh-native fallback" role) — a fallback of **mechanism**, never a waiver of the gate.
  Required even when a PR touches no connector/readiness code. It is separate from readiness/connector
  **probes**, which may remain `NOT_RUN_UNPROVEN_NO_SAFE_SCRIPT_FOUND` when no safe offline script exists.
- **Deep Research — external/current-fact lane (§19 binds).** Only for external / current / high-stakes
  facts: exchange APIs, Deribit docs, fees, rate limits, funding/basis/carry, microstructure, regulation,
  custody/security, live readiness, current tool behavior, official model/tool policy. Never for
  repo-internal deterministic implementation where the repo already defines the contract.

### 20.2 Claude and Codex Setup Auto-Use Doctrine

- **Claude** sessions in this repo auto-load `CLAUDE.md` and the untracked `CLAUDE.local.md` at session
  start (locally proven by session context); `.claude/settings.local.json` + `.claude/hooks/**` are
  untracked local defense-in-depth. Workflow docs are **not** auto-loaded — prompts must still name them.
- **Codex** bootstraps from `AGENTS.md` and `.codex/skills/crypto-core-max-safe/SKILL.md` (read-only audit
  default, no concurrent patching with Claude, no merge, P1/P2/P3 classification, forbidden-surface audit,
  one-open-PR + connector-final-gate discipline all live there and here).
- **AUTO_SETUP_LOADING_PROOF: PARTIAL.** Repo-local files are the enforceable mechanism; app-global
  automatic loading is not claimed beyond the evidence above. Every serious prompt therefore includes an
  explicit READ list (`AGENTS.md` + the relevant sections of this file + task files); the §20.5 templates
  encode this.

### 20.3 PR lifecycle (lane-annotated; all gates unchanged)

Design (Fable 5) → implementation PR (Opus 4.8; Fable 5 for the hardest contract work) → adversarial audit
(Fable 5; Codex where useful or requested) → **GitHub-connector final gate** → explicit per-PR user merge
authorization → standard head-pinned merge + post-merge verification (Fast lane). One open PR at a time; CI
`pending` is NOT_READY — poll to terminal with bounded snapshots (never `--watch`); §3 / §11 / §13 / §16
bind unchanged for every lane.

### 20.4 Next-slice routing (SUPERSEDED 2026-07-07 — see §21.6)

This subsection's roadmap ("after PR #314") is complete and historical: #316 (`PaperStage4ComparisonEvidence`,
Decimal-authoritative retention verdict), #317 (`PaperStage4CompletionDecision` v1 — BLOCKED completion,
`prdv4_stage4_complete=False` structural), #318 (`PaperAttestedOperationalDayEvidence`), and #319
(`PaperAttestedOperationalThirtyDayGateDecision`) are all MERGED. The current roadmap lives in **§21.6**
(next: `PaperStage4CompletionDecisionV2`, Path A conservative). No live/shadow/Deribit/Stage-4 completion
without separate authorization — unchanged.

### 20.5 Future Prompt Templates (Fable-era; historical, superseded by §21.7 post-Fable skeletons)

**Fable 5 (high-reasoning design/audit/governance):**
`TASK` (design/audit/governance objective) · `MODEL: Fable 5 — STOP_WITH_PROOF if not; report actual model`
· `STATE_TO_VERIFY` (main SHA, merged PRs, open-PR count) · `READ` (setup files first: `AGENTS.md`,
`agent_workflow.md` §§ relevant, named task files) · ask for broad repo scan **with justification**,
contradiction detection, model/tool routing decision, P1/P2 classification, exact next action ·
`FORBIDDEN: implementation unless explicitly authorized` · report includes `FABLE5_CONFIRMED`.

**Opus 4.8 (implementation/repair):**
`TASK` (bounded slice) · branch + PR named · exact allowed files · implementation contract (digest/
fail-closed/non-overclaim invariants) · tests required · validation ladder (targeted → full helper →
`git diff --check`) · CI poll to terminal · same-branch repair loop allowed within scope · **no merge** ·
fixed report fields (§10).

**Fast Auto / Sonnet (mechanical):**
`TASK` (status / CI / merge / post-verify) · exact PR number + pinned head SHA · **no code edits** · stop
conditions (stale head, non-terminal CI, unresolved threads, CHANGES_REQUESTED) · bounded terminal polling
· fixed report fields.

**Codex (independent audit):**
read-only · no edits/comments unless explicitly authorized · P1/P2 adversarial audit of the named PR at the
pinned head · scope + forbidden-surface audit · verdict `READY / NOT_READY` with §10 Codex fields · never
mixed with Claude prompt grammar.

**GitHub connector (final gate):**
source-of-truth gate for the named PR · verify head/base/files/checks/reviews/threads/code-scanning ·
**no mutation** · output `PASS / BLOCK / UNKNOWN` with evidence lines.

**Deep Research (external facts):**
official/current external-source audit for a named question · cite sources; separate
`REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN` · no repo-state claims without repo evidence ·
advisory only (§19 misuse-prevention binds).

### 20.6 Non-overclaim

Better reasoning is not proof. No lane may claim live/private-API/orders/readiness/Deribit/capital/
scheduler behavior, edge/profitability, or Stage-4 completion without artifacts and separate authorization;
no BIST leakage; no official Fable 5 limit/pricing/quota claims unless proven (status as of v4.4:
UNPROVEN). "Fable 5 can replace audits / the connector gate / CI" is a forbidden claim.

## 21. HISTORICAL / SUPERSEDED BY GPT-5.6 ROUTING DOCTRINE - Post-Fable model

Fable 5 (`claude-fable-5`) is **no longer assumed available** after 2026-07-07. Everything Fable 5 previously
did is re-routed below. **Model strength is never proof** — every lane still runs under §3 / §11 / §13 / §16,
CI-to-terminal, Codex review where required, the GitHub-connector final gate, and explicit per-PR user merge
authorization, all unchanged. Doctrine unchanged: paper-first, deterministic, fail-closed, audit-first,
derivatives-first, governance-first, risk-bounded.

### 21.1 Lane table (post-Fable)

| Lane | Use for | Never for |
|---|---|---|
| **Opus 4.8 xhigh** | Bounded high-risk implementation; repo-internal semantic design **first draft** when Fable is absent; same-branch repair; forensic debug; hard contract/digest/fail-closed work | CI polling; git hygiene; mechanical merge/post-verify; status |
| **Codex GPT-5.5 extra-high thinking** | Independent **read-only** P1/P2 audit after design AND after implementation; second opinion on overclaim / digest / reseal / alignment / provenance / unsafe flags / AST forbidden surface; routing-decision and prompt/workflow consistency audit | Patching concurrently with Claude; merging; CI polling with model tokens |
| **GitHub Connector** | Mandatory source-of-truth **FINAL merge-readiness gate**: PR metadata, head, files, checks, reviews, threads, code scanning. **Never waived** — if the connector app is unavailable, the same gate runs via `gh`-native commands (mechanism fallback, never a gate waiver) | Design; implementation; anything beyond state proof |
| **Sonnet / Fast Auto** | Mechanical `git`/`gh` state; CI polling (bounded one-shot snapshots, never `--watch`); standard head-pinned merge + post-merge verification; low-risk mechanical docs edits | High-risk design, implementation, or adversarial audit |
| **Deep Research** | External / current / high-stakes facts ONLY: exchange APIs, Deribit docs, fees, rate limits, funding/basis/carry, microstructure, regulation, custody/security, current tool behavior (§19 binds) | Repo-internal artifacts; repo/CI/merge state; replacing Codex or the connector gate |

### 21.2 Fable replacement rules

- Task was Fable-level **repo-internal design** → **Opus 4.8 xhigh first design draft + mandatory Codex
  GPT-5.5 design audit BEFORE implementation.**
- Task was Fable-level **adversarial review** → **Codex GPT-5.5 extra-high FIRST.**
- Task involves **current external facts** → **Deep Research BEFORE implementation** (§19).
- Task is **mechanical** → **Sonnet/Fast Auto.**
- **No expensive lane (Opus/Codex) is ever used for CI polling, git hygiene, or mechanical
  merge/post-verify.**

### 21.3 Codex increased-use policy

Codex GPT-5.5 runs **more frequently than in the Fable era** — it inherits Fable 5's adversarial-reasoning
share. Run a Codex read-only audit:

- after EVERY high-risk design, before implementation;
- after EVERY high-risk implementation, before the connector final gate;
- whenever a claim could overreach: completion, readiness, live/shadow/Deribit, machine-time proof,
  real orders/capital, profitability/edge;
- for P1/P2 classification;
- for digest / reseal / provenance / AST-forbidden-surface audit;
- for prompt/workflow consistency audit.

Codex remains **read-only** unless explicitly rerouted as implementation fallback; it never patches a PR
concurrently with Claude and never merges (§2 / §2a / §8 bind unchanged).

### 21.4 Mandatory PR loop (gates unchanged; post-Fable lanes)

1. State proof on clean synced `main` (Sonnet/Fast). 2. 0-open-PR check. 3a. Design draft for the named
slice (Opus 4.8 xhigh) — pin the contract; no implementation yet. 3b. **Codex P1/P2 design audit BEFORE
implementation** — mandatory whenever the slice is high-risk or contract-defining (§21.2/§21.3); proceed
only once CLEAN or all P1/P2 findings are repaired; skip only for mechanical/low-risk docs-only work;
**Fable/Claude self-review never satisfies this gate.** 3c. Implementation (Opus 4.8 xhigh), only after
3a/3b and after the user/controller has selected the exact next slice and the one-open-PR rule is
satisfied. 4. Local validation (ruff check/format, targeted pytest, logged full suite, `git diff
--check`). 5. PR. 6. CI poll to terminal — pending/queued/in-progress/no-checks = **NOT_READY**
(Sonnet/Fast, bounded snapshots). 7. Codex P1/P2 implementation audit for high-risk PRs, before the
connector gate. 8. Same-branch repair if needed (Opus 4.8 xhigh). 9. **GitHub-connector final gate — never
waived.** 10. **Explicit per-PR user merge authorization.** 11. Standard head-pinned merge (Sonnet/Fast;
never squash/rebase/admin). 12. Post-merge `main` verification. 13. 0 open PRs. 14. Next slice. One open PR
at a time; no direct `main` push; no force push. Codex never merges or patches concurrently with Claude
unless explicitly rerouted (§2/§2a/§8 bind unchanged).

### 21.5 Non-overclaim doctrine (attestation is NEVER machine proof)

Never claim `prdv4_stage4_complete=True`, operational readiness, live readiness, shadow readiness, Deribit
readiness, machine-time proof, real orders/capital/equity/margin/balance, production execution, private-API
readiness, or connector readiness **unless the exact current gate proves it**. Hard rule for all future
agents: **attestation-only evidence is never machine proof.** `PaperAttestedOperationalDayEvidence` and
`PaperAttestedOperationalThirtyDayGateDecision` carry
`attestation_source="operator_attested_not_machine_proven.v1"` and keep all five machine-proof flags
(`operational_day_machine_proven`, `machine_time_origin_proven`, `timestamp_origin_proven`,
`real_wall_clock_used`, `real_time_paper_operation_proven`) structurally False. A satisfied attested gate
(`attested_operational_thirty_day_gate_satisfied=True`) proves internal consistency of operator-attested
UTC days only — never that real time elapsed, never that real paper operation occurred, never Stage-4
completion.

### 21.6 Post-PR #319 roadmap (recorded 2026-07-07)

- `main` after #319: `e278293cd5537cfa7174db79a1238a686199275a`. Merged Stage-4 methodology chain:
  #310 Sharpe, #311 methodology, #312 edge identity, #313 baseline binding, #316 comparison evidence,
  #317 completion decision v1 (BLOCKED), #318 attested operational day, #319 attested 30-day gate.
- **Next technical PR: `PaperStage4CompletionDecisionV2` — Path A (conservative), Fable-designed
  2026-07-07.** v2 consumes `PaperStage4ComparisonEvidence`, the return-series/Sharpe/30-day evidence
  chain, `PaperAttestedOperationalThirtyDayGateDecision`, and the predecessor v1 completion decision
  (chain-continuity check on v1's `verified_*` digests); proves selected UTC day-index alignment
  (`gate_used_first/last_bucket_*_ns // 86_400_000_000_000` vs `selected_utc_day_indices`, with
  day-alignment re-pin before division); keeps **`prdv4_stage4_complete=False` structural**. Blocker
  narrowing: drop stale `operational_day_evidence_source_unavailable`; replace
  `prdv4_minimum_30_day_live_paper_trading_unproven` with
  `operator_attested_only_machine_time_origin_unproven`; keep
  `timestamp_origin_not_proven_injected_deterministic_time_only` and
  `secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1`. v2 must NOT claim completion,
  readiness, or machine proof.
- **After v2 (each its own authorization):** docs phase-map update; `paper_stage4_completion_review_package`
  dossier; machine-time provenance DESIGN (Deep Research likely required); hit/fill/slippage trade-record
  enforcement phase (design first, then slices); methodology v2 (secondary metrics enforced); **completion
  decision v3 only after machine-time proof + enforced secondary metrics** — the only future artifact that
  may set `prdv4_stage4_complete=True`, under its own design and explicit authorization.
- **Full Fable exit contract set + canonical queue:** indexed in
  `docs/crypto_core/fable_exit_contract_index.md` (Stage4 v2, MT machine-time, SM secondary metrics,
  EF edge factory, RG multi-sleeve risk governance, RF regime/vol filter, funding pilot; prompt index
  PRM-01..32; governance-required decisions; Deep Research batches). That file is archived design
  doctrine — **never repo current-state proof**; implement only via a scoped PR with fresh `git`/`gh`
  state proof.

### 21.7 Prompt skeletons (post-Fable)

- **Opus implementation:** "Opus 4.8 xhigh. Branch `feature/<scope>-prN` from proven clean `main` @ `<SHA>`.
  Exactly `<N named files>`. Implement `<contract reference>`. Validate: ruff check/format, targeted pytest,
  related tests, `run_full_tests_logged.ps1` PYTEST_EXIT=0, `git diff --check`. Scoped `git add`. Open PR.
  No merge without explicit authorization. Report: RESULT / FILES_CHANGED / VALIDATION / NEXT_SAFE_ACTION."
- **Codex P1/P2 audit:** "Read-only adversarial P1/P2 audit of PR `<N>`. Focus: digest-resealed exact-typed
  inputs reaching READY; overclaim/unsafe flags; alignment arithmetic edge cases; AST forbidden surface;
  raise-vs-REJECTED boundaries. No patching. Report P1/P2 with file:line."
- **GitHub Connector final gate:** "Read-only final gate for PR `<N>`: verify state OPEN/non-draft, head
  `<SHA>`, exact changed files, all checks SUCCESS (pending = NOT_READY), review threads resolved, no human
  CHANGES_REQUESTED, code scanning clear. Verdict: READY_FOR_MERGE_AUTHORIZATION | NOT_READY, with proof."
- **Sonnet merge/post-verify:** "Authorized merge of PR `<N>` ONLY: re-verify head/files/checks/threads;
  `gh pr merge <N> --merge --match-head-commit <SHA>`; post-merge: ff-only pull of `main`, ruff + format
  check, targeted + related tests, logged full suite PYTEST_EXIT=0, 0 open PRs, clean `git status`. No other
  PR, no code edits, no next slice."
- **Deep Research trigger:** "DEEP_RESEARCH_REQUIRED: `<exact external/current question>`. Reason: the repo
  cannot prove this fact internally. Constraints: read-only advisory, §19 output contract, stricter repo
  safety rule wins on conflict."

### 21.8 Fable 5 exit note

Fable 5's final contributions (2026-07-07): this post-Fable operating model plus the exit contract
set — Stage-4 completion v2 (Path A, §21.6), machine-time provenance (MT), hit/fill/slippage
secondary-metrics enforcement (SM), edge-factory gate pipeline (EF), multi-sleeve risk governance
(RG), regime/vol filter evidence (RF), the funding/basis/carry pilot design, and the CTO council
pack — all indexed in `docs/crypto_core/fable_exit_contract_index.md`. **Fable outputs are archived
design contracts, never repo current-state proof**, and Fable self-review never replaced (and never
replaces) the independent Codex audit or the connector gate. Do not assume Fable 5 availability in
any future task. If Fable 5 reappears, §20 applies opportunistically again — but no plan may depend
on it; section 21 remains a historical record only.

## 22. Token Economy Doctrine

The common taxonomy and lane budget live in `docs/crypto_core/token_efficiency_playbook.md`. Token saving
never outranks correctness, evidence, tests, terminal CI, independent audit, connector final gate, explicit
merge authorization, or postmerge verification. Use Luna for mechanics, Terra for bounded work, Sol only for
qualifying T4 reasoning, and Opus for heavy local loops. Stable procedure text stays in docs/skills; prompts
carry task deltas, exact scope, validation, stops, and model-actual fields.

## 23. GPT-5.6 Routing Doctrine (2026-07-10; SUPERSEDED BY SECTION 24 for active routing)

This section superseded sections 20-21 and is itself superseded by section 24 (Crypto Core Agent OS v1) for
active routing, taxonomy labels, and controller/research orchestration. Its safety rules carry forward
unchanged into section 24. Historical Fable/GPT-5.5/Sonnet/Fast text remains archived context only and is
never an active default.

### 23.1 Common taxonomy

| Class | Active lane | Use |
|---|---|---|
| T0 `LUNA_MECHANICAL` | GPT-5.6 Luna `none`/`low` | git/gh status, CI polling, PR metadata, thread state, postverify runner |
| T1 `LUNA_OR_TERRA_READONLY` | Luna low or Terra high | bounded docs, proof, direct-dependency read-only audit |
| T2 `TERRA_BOUNDED_CODE` | GPT-5.6 Terra high | exact-file implementation, tests/docs, deterministic small slice |
| T3 `TERRA_REPAIR_OR_OPUS_HEAVY` | Terra xhigh or Opus 4.8 xhigh | current P1/P2 repair, fail-closed work, forensic debug, broad/long-loop execution |
| T4 `SOL_CROSS_CONTRACT` | GPT-5.6 Sol xhigh; max controller-gated | trust boundary, governance/safety, SM-5/SM-6 design/audit, readiness/Deribit provenance |
| XR `DEEP_RESEARCH_EXTERNAL` | Deep Research | cited external/current facts only |
| `CONTROLLER_CONNECTOR_GATE` | ChatGPT plus connector/gh | final evidence comparison and merge authority |

### 23.2 Model and fallback policy

Luna does mechanics only. Terra is the bounded Codex workhorse. Sol is scarce and is never used for polling,
merge mechanics, broad local refactors, or routine docs. Opus preserves Codex capacity for broad local work
and long validation loops. Deep Research precedes implementation whenever current external facts are needed.

If `EXACT_MODEL_REQUIRED=true`, requested/actual mismatch stops with proof. Otherwise fallback is declared:
Sol unavailable -> Opus design draft plus independent available-Codex audit; Terra unavailable -> Opus bounded
implementation; Luna unavailable -> terminal/gh or available mechanical lane; Opus unavailable -> split broad
work or use Terra only when scope is genuinely bounded. No fallback may claim the unavailable model's quality.

### 23.3 Mandatory PR lifecycle

1. Prove clean synced `main`, expected head, and zero open PRs. 2. Classify task and report actual model.
3. For T4, run Sol design/audit; for XR, Deep Research first. 4. Implement with Terra when bounded or Opus
when heavy. 5. Validate by scope. 6. Open one PR. 7. Luna runs bounded CI/status snapshots; pending is
`NOT_READY`. 8. Run fresh-context pinned-head independent audit for high-risk work. 9. Connector/gh final
gate. 10. Explicit human authorization. 11. Standard head-pinned merge only. 12. Postmerge verification and
zero-open-PR proof before next work.

### 23.4 Safety and non-claims

All rails in section 3 bind unchanged: crypto-only, paper-first, deterministic, fail-closed, audit-first, no
BIST, live/private API, real orders/order routing, scheduler/auto-loop, readiness/Deribit transition without
provenance, shadow/live, capital mutation, direct main push, force push, self-approval, or unproven claim.
Pending CI is `NOT_READY`; current valid P1/P2 threads block; standard merge and explicit human authorization
remain required.

### 23.5 Current state and next gated work

**HISTORICAL / SUPERSEDED (dated 2026-07-10 snapshot):** the pins below are a historical record only; current
live state is re-proven per task under `LIVE_STATE_POLICY` (section 24.11), never read from here.
PRs #326, #327, #328, and #329 are merged. `main` contained the #329 merge commit
`167c508825a8ac55bb207107a7e2b4fee94860d5` (GPT-5.6 routing doctrine sync) at that date. Expected open PRs
between slices: none. The blocker
`secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1` remains valid. Any next
SM-5/SM-6 work starts with a separately authorized T4 design/audit consuming the #328 precondition;
setup/doctrine changes do not implement it.

### 23.6 Active prompt policy

Active templates cover Sol workflow/cross-contract audit; Terra bounded implementation; Terra fresh independent
audit; Terra emergency repair; Luna CI/status; Luna explicitly authorized metadata update; Luna merge/postverify;
Opus heavy local implementation; Deep Research; connector final gate; bounded Pursue Goal preflight; and model
fallback. Each carries model requested/actual/reasoning/exactness fields, exact scope, validation, stop
conditions, and report fields. The durable per-model authoring guide is
`docs/crypto_core/model_prompting_guide.md` (active lanes per section 24).

## 24. Active Crypto Core Agent OS v1 (2026-07-10)

`CRYPTO_CORE_AGENT_OS_V1` — the active, durable, controller-mediated operating protocol. Supersedes section
23 for routing/taxonomy/orchestration; every section-3 hard rule and section-23.4 non-claim binds unchanged.

### 24.1 Final durable model/tool set and identity rules

Active set (exactly eight lanes): **ChatGPT GPT-5.6 Thinking** (controller / read-only-first controller-auditor,
`CONTROLLER_READONLY_FIRST_POLICY`, section 24.10); **GitHub connector** (evidence + explicitly authorized
actions); **Deep Research + GitHub connector** (external/current facts, advisory); **Claude Opus 5**
(`claude-opus-5`, default heavy local executor); **Claude Sonnet 5** (`claude-sonnet-5`, runtime-proven
only); **Codex GPT-5.6 Sol / Terra / Luna**. Claude Code local sessions are the primary local execution
environment for Claude Opus 5 and Claude Sonnet 5 tasks — this is a runtime description, not an
independently trusted audit authority. **Claude Opus 4.8 status: `SUPERSEDED_BY_OPUS_5`** — it is not an
active lane, fallback, or dependency; dated Opus 4.8 execution records, archived prompts, and changelog
entries remain HISTORICAL evidence and never re-enter active routing. **Copilot
status: `INACTIVE_UNAVAILABLE`** — VS Code Copilot Pro local Agent is currently unavailable and does not enter
active routing, setup loading, prompt construction, or accepted state; it is not part of the active model/tool
set until a future explicit human decision reactivates it through a separately audited workflow change.
**Claude Fable 5 status: `INACTIVE_EXPIRED_RETIRED`** — the former premium-surge lane is retired and does NOT
enter active routing, setup loading, prompt construction, fallback tables, model selection, or accepted state;
its former responsibilities are redistributed (section 24.10). Pre-v5.2 Fable material survives only as dated
HISTORICAL/SUPERSEDED/ARCHIVAL evidence (`fable_exit_contract_index.md`, sections 20-23) and never affects
current routing.

Identity rules: ChatGPT is `GPT-5.6 Thinking` and is NEVER labeled Codex `GPT-5.6 Sol`; Sol/Terra/Luna are
distinct Codex runtimes; Opus 5 and Sonnet 5 are distinct Claude runtimes; Sonnet 5 availability/identity
must be runtime-proven before routing; every Claude Code session reports its actual runtime model — model
identity is attached to the actual Claude runtime, never to the local host; model-family similarity is not
runtime identity; model strength is never proof. Every serious executor prints `MODEL_REQUESTED` /
`MODEL_ACTUAL` / `REASONING_REQUESTED` / `REASONING_ACTUAL` / `EXACT_MODEL_REQUIRED` before work; required
exact-model mismatch stops with proof.

`CLAUDE_EXACT_MODEL_ID_RULE` — a Claude mutation lane is selected by exact model id, never by an unresolved
convenience alias. `claude-opus-5` and `claude-sonnet-5` are the only ids that satisfy the active Claude
lanes; the bare strings `opus` / `sonnet` are aliases and are insufficient evidence on their own. Runtime
proof means session-level evidence of the resolved model AND the resolved effort (for example the Claude
Code runtime banner, `/model`, `/status`, or an equivalent local diagnostic), not a settings file alone —
a settings pin states an intent, the session states the fact. Requested/actual mismatch on model, effort,
or fallback is `STOP_WITH_PROOF` before mutation; a human may waive an effort-level mismatch for a specific
task, and the waiver plus the true `MODEL_EFFORT_ACTUAL` is then recorded in the handoff — the actual
effort is never restated as the requested one. Effort/thinking architecture: section 24.12.

**Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED`** (section 24.10): the former `FABLE5_PREMIUM_SURGE_LANE` is
retired and is never selected, never a fallback, and never a dependency. Its former responsibilities are
redistributed to the optimal remaining lanes: broad-but-bounded T3 implementation → Claude Opus 5 xhigh
(genuinely bounded T2 → Sonnet 5/Terra); non-Class-C read-only architecture / contradiction / cross-contract
analysis → the ChatGPT controller (`CONTROLLER_READONLY_FIRST_POLICY`), with a Terra ordinary independent
audit only when controller evidence requires it; rare milestone read-only full-repo audit → ChatGPT + GitHub
connector (protected disputed questions split into narrow Sol packets; external/current facts to Deep
Research). No lane claims Fable-equivalent quality. Pre-v5.2 Fable-era material stays archived under
HISTORICAL/SUPERSEDED/ARCHIVAL labels (`fable_exit_contract_index.md`, sections 20-23).

### 24.2 CRYPTO_CORE_DOMAIN_OPERATING_PROFILE

Every serious model prompt inherits or explicitly reads this profile. Each model operates as a specialized
institutional crypto trading systems engineer within its lane — never a generic coding assistant:
crypto_core only; no BIST implementation leakage; institutional crypto trading operating system;
derivatives-first; paper-first; deterministic; event-driven; point-in-time data; fail-closed; audit-first;
governance-first; risk-bounded; multi-strategy/multi-sleeve isolation; exchange/venue abstraction; fees,
funding, slippage, fills and latency realism; order-book and derivatives microstructure awareness; immutable
provenance; replay/OOS/stress expectations; human-owned governance thresholds; no unsupported
edge/profitability claim; no unsupported paper/shadow/live/readiness claim; no private API, credentials,
real orders, scheduler, auto-loop, or capital mutation unless separately authorized.

### 24.3 Common taxonomy and optimal routing matrix

**`AUTHORITATIVE_ROUTING_MATRIX` — this table is the single active routing authority for crypto_core.** No
other file may restate it as authority; every other active surface (`AGENTS.md`, `CLAUDE.md`,
`model_prompting_guide.md`, `token_efficiency_playbook.md`, `token_efficiency_v2.md`, the Claude and Codex
skills) references this section instead of duplicating it. Effort/thinking selection, the deterministic
routing function, and Claude behavior calibration live in section 24.12; Claude prompt construction and
reusable templates live in `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`. Pick the LOWEST
lane that safely proves correctness — model prestige is never a selection reason.

| Class | Label | Primary lane(s) | Model id | Default effort | Use |
|---|---|---|---|---|---|
| T0 | `LUNA_MECHANICAL` | Luna `none`/`low` — or Claude Sonnet 5 low in a Claude Code session | `claude-sonnet-5` (Claude lane) | low | **STATUS family only**: git/gh state, bounded CI polling, PR metadata, review/thread status, open-PR counts, branch and clean-tree checks, deterministic status reporting. T0 owns no merge or postverify scope — see T1 |
| T1 | `READONLY_OR_FAST_BOUNDED` | Luna low / Terra high / Sonnet 5 (runtime-proven) | `claude-sonnet-5` (Claude lane) | low | bounded reads, proof, docs, direct-dependency read-only audit, and the sole governed CLOSEOUT family — authorized standard merge, branch-protection-required auto-merge only when separately authorized by doctrine, post-merge commands, parent/digest verification, clean-main proof, and postverify. **A merge is a mutation and stays T1** when it is fully authorized, mechanically bounded, free of semantic anomaly and free of any readiness/connector transition |
| T2 | `BOUNDED_IMPLEMENTATION` | Terra high / Sonnet 5 (runtime-proven) | `claude-sonnet-5` (Claude lane) | medium (high when moderately complex) | exact-file deterministic slices, narrow docs, config-only changes, mechanical fixtures/tests, obvious localized repair, PR-body corrections, bounded governance closeout |
| T3A | `COMPLEX_IMPLEMENTATION` | Claude Opus 5 (default) / Terra xhigh | `claude-opus-5` | xhigh | complex production implementation, multi-file semantic features, protocol semantics, deterministic state machines, fail-closed artifacts, provenance logic, complex cross-module repair, long-horizon agentic coding. Complexity is proven by evidence (interacting invariants, novel semantic contract, fail-closed artifact design, cross-module behavior, substantial validation loop, in-scope architectural choice, complex repair) — **never by file count**; a two-file production+test protocol-semantic slice is correctly T3A |
| T3B | `CAPABILITY_CRITICAL_IMPLEMENTATION_OR_REPAIR` | Claude Opus 5 | `claude-opus-5` | max | **IMPLEMENTATION or REPAIR intent + mutation only** — T3B never accepts REVIEW, ARCHITECTURE or PROMPT_ARCHITECTURE work, whatever risk flags are set. Requires an explicitly NAMED trigger: cryptographic verification boundary implementation; readiness/provenance promotion implementation; protocol ambiguity with safety consequences inside an implementation; complex trust-boundary repair; **complex semantic** controller P1/P2 repair after a failed audit; unexpected cross-layer implementation failure; controller-designated capability-critical implementation/repair. A bare risk flag and a bare audit origin are both insufficient — a mechanical or obvious post-audit repair stays T2 |
| T3C | `CODE_REVIEW_AND_BUG_FINDING` | Claude Opus 5 | `claude-opus-5` | medium (focused) / high (broad) / xhigh (protocol-crypto or multi-trust-boundary) | **REVIEW intent, read-only.** Focused one- or two-file review and first-pass bug discovery at medium; broad multi-module, subtle-semantic, security-sensitive or post-failure review at high; protocol/crypto, multi-trust-boundary, conflicting-findings or cross-layer reconstruction at xhigh. Protocol or cryptographic subject matter raises the EFFORT to xhigh — it never changes the class to T3B. Any resulting fix is a separate, explicitly created task |
| T3D | `ARCHITECTURE_AND_NEXT_SLICE` | Claude Opus 5 | `claude-opus-5` | high / xhigh (interacting or multi-module) / max (readiness, crypto, irreversible) | **ARCHITECTURE intent, read-only — produces a decision, not a diff.** Next-slice selection, architecture comparison, sequencing. `max` when the decision controls readiness/provenance, involves cryptographic boundaries, a wrong sequence creates irreversible or high-cost work, or the controller designates it critical. Readiness or cryptographic subject matter raises the EFFORT to max inside T3D — it never changes the class to T3B |
| T3E | `COMPLEX_PROMPT_ARCHITECTURE` | Claude Opus 5 | `claude-opus-5` | high / xhigh (synthesis) / max (capability-critical) | **PROMPT_ARCHITECTURE intent.** Converting a new complex objective into one complete execution contract; prompts needing repository archaeology; many interacting gates. `max` for Agent OS or model-routing prompts, prompts governing readiness/provenance promotion, prompts governing cryptographic verification, capability-critical controller repair prompts, and controller-designated critical prompts — capability-criticality raises the EFFORT to max inside T3E and the work stays T3E. Known bounded mechanical prompt generation stays Sonnet 5 medium |
| T4 | `CROSS_CONTRACT_DESIGN_OR_AUDIT` | Sol xhigh (`max` controller-gated) | — (Codex) | xhigh | protected cross-contract design, digest/provenance/trust boundaries, SM-5/SM-6, Stage-4 semantics, readiness/Deribit design, complex security/CodeQL. Class C is never satisfied by a Claude lane |
| XR | `DEEP_RESEARCH_EXTERNAL` | Deep Research + connector | — | — | cited external/current facts, benchmarks, phase gates (submodes in 24.9). Claude execution alone is insufficient; no Claude lane may infer load-bearing current external facts from memory |
| — | `CONTROLLER_CONNECTOR_GATE` | ChatGPT + connector/gh, then the human | — | — | final evidence comparison, merge-readiness judgement, and explicit per-PR human merge authorization. No Claude or Codex lane replaces either authority |

Label reconciliation (durable): a request phrased as "T3" without a suffix means T3A. A request phrased as
"T4 = current external facts" means `XR`; a request phrased as "T5 = controller and human authority" means
`CONTROLLER_CONNECTOR_GATE`. The numbered class `T4` in this repository is and stays
`CROSS_CONTRACT_DESIGN_OR_AUDIT` (Codex Sol) — Codex doctrine is not renumbered.

ChatGPT GPT-5.6 Thinking additionally owns, read-only-first (`CONTROLLER_READONLY_FIRST_POLICY`, section
24.10): sequence control, live GitHub evidence comparison, repository surface and dependency mapping, design
synthesis, prompt/implementation-contract construction, full PR patch and exact-scope audit,
setup/workflow/model-routing consistency audits, Class-A independent audit, Class-B first-pass and
controller-only closeout when every no-Codex criterion is proven, pre-Codex risk triage, fail-closed and
negative-test coverage analysis, architecture-drift and stale-state detection, executor-report verification,
connector final gate, Deep Research orchestration and verification, next-slice and model selection, and
explicit-authority GitHub actions. ChatGPT is never an unverified substitute for local tests or repo state,
never a Class-C Codex audit substitute, never a product-implementation or direct-main lane, and never grants
merge/readiness/live/capital authority. GitHub connector mutation happens only after an explicit human
instruction naming the exact action and target, with state re-proof immediately before, only the named
action, and result re-read after. Do not route to Sonnet 5: protected trust-boundary work, digest/provenance,
SM-5/SM-6, Stage-4 completion, readiness/live/order/capital, broad forensic refactors, T4 design, or mandatory
Class-C audits; Sonnet 5 fallback when unavailable: Terra (bounded) / Opus 5 (broad). Do not spend Opus 5 on
metadata, CI polling, ordinary docs, generic planning, external research, or work Sonnet/Terra can safely
complete. Sol runs only on a controller-prepared narrow evidence packet, never broad discovery or mechanics.

Sonnet 5 is the DEFAULT Claude lane for T0/T1/T2 and is not weakened by the existence of Opus 5: stronger
reasoning does not materially improve a `gh pr view`, an authorized standard merge, a config edit, or a
mechanical fixture, and spending Opus there costs latency, tokens and premium requests for no correctness
gain. Escalate T0/T1 out of Sonnet when evidence conflicts, ancestry is unexpected, state cannot be
reconciled, merge parents or merged scope differ, post-merge validation fails, branch protection behaves
unexpectedly, a readiness/connector transition appears, or the task turns semantic. Escalate T2 first to
Sonnet 5 high; move to Opus 5 high/xhigh only when semantic invariants interact, the trust boundary changes,
full-suite failures are unexpected, architecture is required, or the repair cannot be proven locally.

### 24.4 Audit class matrix

- **AUDIT_CLASS_A_CONTROLLER_SUFFICIENT** — ChatGPT + connector may independently audit: docs-only,
  setup/doctrine, prompt/skill changes, workflow documents, low-risk CI configuration, deterministic
  helper/test-runner scripts, metadata/non-claim/state-pin consistency, exact-scope/configuration changes.
  Required: fresh pinned-head reread, complete patch, exact files, terminal CI, review/thread state, no
  product source, no protected trigger, P1/P2/P3 classification; the connector final gate and explicit human
  merge authorization remain separate; the report states why Class A applies.
- **AUDIT_CLASS_B_CONTROLLER_FIRST** — ordinary bounded product code: under
  `CONTROLLER_READONLY_FIRST_POLICY` (section 24.10) ChatGPT performs the default read-only independent
  audit — source/test mapping, dependency mapping, negative-test check, fail-closed first pass, CI/CodeQL
  check, protected-trigger check, and exact unresolved-question extraction — and may close Class B alone
  when every no-Codex criterion is proven. A fresh Terra ordinary independent audit is added only when
  evidence is incomplete, semantic independence is materially useful, or controller uncertainty remains.
  `CODEX_REQUIRED: NO` must still carry the exact reason plus the full protected-trigger checklist. Any
  uncertainty escalates to Class C.
- **AUDIT_CLASS_C_CODEX_REQUIRED** — mandatory fresh-context independent Codex audit for: digest
  recomputation/consumption, expected-digest anchors, canonical serialization, reseal/provenance,
  mutable/stateful/TOCTOU behavior, denominator integrity, record-set completeness, duplicate/replay
  defenses, Decimal/Fraction financial arithmetic, governance thresholds, fail-closed trust transitions,
  READY/ADMITTED/ACCEPTED transitions, SM-5/SM-6, Stage-4 completion, machine-time provenance,
  readiness/Deribit, connector-ready transitions, live/private API, orders/order routing,
  scheduler/auto-loop, shadow/live, capital mutation, edge/profitability claims, complex CodeQL/security
  issues, current P1/P2 source findings, or insufficient controller evidence. Neither ChatGPT, Claude, nor
  implementer self-review may replace Class C.

### 24.5 Agent OS protocol and CONTROLLER_ACCEPTED_STATE

Controller-mediated, sequential, deterministic: no autonomous scheduler, no auto-loop, no direct
model-to-model runtime messaging, one repository writer at a time, one open PR, no concurrent patching;
reports transfer through standardized handoff packets; ChatGPT owns accepted state; GitHub/terminal evidence
outranks model memory; every stage ends with exactly one next safe action.

Normal chain: CONTROLLER_STATE_PROOF → CONTROLLER_DESIGN_SYNTHESIS → MODEL_SELECTION_WITH_TOKEN_GATE
(section 24.10 expected-value policy) → ONE_SELECTED_IMPLEMENTER → IMPLEMENTER_HANDOFF →
CONTROLLER_REPORT_VERIFICATION → CONTROLLER_PROTECTED_RISK_TRIAGE →
CODEX_SOL_CLASS_C_AUDIT_IF_REQUIRED → AUDITOR_HANDOFF → CONSOLIDATED_SAME_BRANCH_REPAIR →
REAUDIT_ONLY_IF_HEAD_CHANGED_MATERIALLY → CONTROLLER_CONNECTOR_FINAL_GATE →
EXPLICIT_HUMAN_MERGE_AUTHORIZATION → STANDARD_MERGE → POST_MERGE_VERIFY → NEXT_SLICE. Research chain:
CONTROLLER_RESEARCH_PACKET → DEEP_RESEARCH → RESEARCH_HANDOFF → CONTROLLER_RESEARCH_VERIFICATION →
DESIGN_SYNTHESIS → normal chain. Research never triggers automatic implementation.

`CONTROLLER_ACCEPTED_STATE`: only evidence verified through the GitHub connector, current terminal output,
pinned repository files, terminal CI/CodeQL, or an accepted independent audit enters accepted state; agent
reports never update it automatically. Handoff statuses: `HANDOFF_ACCEPTED` / `HANDOFF_REPAIR_REQUIRED` /
`HANDOFF_REJECTED` / `HANDOFF_UNKNOWN`. Conflict precedence (highest first): current pinned GitHub/terminal
evidence → current CI/CodeQL → current pinned file contents → active doctrine → fresh independent audit →
implementer report → earlier handoff → conversation memory. Never vote or average model answers; resolve the
exact disputed claim with controlling evidence; unresolved load-bearing disputes stay `UNKNOWN` and block
merge.

### 24.6 AGENT_OS_HANDOFF_V1 and role packets

Canonical handoff fields: HANDOFF_SCHEMA, HANDOFF_ID, PARENT_HANDOFF_ID, TASK_ID, ROLE, TASK_CLASS,
MODEL_REQUESTED, MODEL_ACTUAL, REASONING_REQUESTED, REASONING_ACTUAL, EXACT_MODEL_REQUIRED, REPO,
ACTIVE_SCOPE, MAIN_SHA, BASE_SHA, PR_NUMBER, PR_STATE, BRANCH, HEAD_SHA, OPEN_PRS, FILES_READ, FILES_CHANGED,
COMMITS, COMMANDS_RUN, VALIDATION_RESULTS, CI_STATE, CODEQL_STATE, REVIEWS, REVIEW_THREADS,
SCOPE_CONFIRMATION, SAFETY_CONFIRMATION, PROTECTED_RISK_TRIGGERS, AUDIT_CLASS, CODEX_REQUIRED, REPO_EVIDENCE,
EXTERNAL_EVIDENCE, INFERENCES, UNKNOWN, P1_BLOCKERS, P2_BLOCKERS, P3_NOTES,
CLAIMS_REQUIRING_CONTROLLER_VERIFICATION, NEXT_SAFE_ACTION, STOP_CONDITIONS_HIT, FINAL_GIT_STATUS. Rules:
missing facts are `UNKNOWN`/`N/A`, never invented; no full success logs (failing tails only);
evidence/inference separated; exactly one next safe action; a handoff never authorizes mutation.

Role packets: CONTROLLER_TO_IMPLEMENTER (pinned state, exact read set, symbol map, exact allowed files,
invariants, forbidden surfaces, protected-risk classification, exact tests, validation ladder,
branch/commit/PR contract, stop conditions); IMPLEMENTER_TO_CONTROLLER (actual files/head/commits, local
tests, full-suite result, CI snapshot, unresolved issues, no self-audit claim, one next action);
CONTROLLER_TO_AUDITOR (pinned base/head, exact changes, direct dependencies, contract/invariants, protected
risks, adversarial questions, required report — never implementer conclusions as audit premises);
AUDITOR_TO_CONTROLLER (P1/P2/P3 with exact source evidence, reproducible failures, repair requirements,
readiness classification, zero mutation); CONTROLLER_TO_DEEP_RESEARCH and DEEP_RESEARCH_TO_CONTROLLER
(section 24.9 / `deep_research_protocol.md`); POST_MERGE_HANDOFF (PR, merge commit, local/origin main, Ruff,
format, full suite, setup audit, diff check, open PRs, clean tree, residual blockers, one next action).

### 24.7 SETUP_LOAD_CONTRACT_V1

Claude sessions (Opus/Sonnet) load/read: `CLAUDE.md`, `CLAUDE.local.md`,
`.claude/skills/crypto-core-token-efficient-loop/SKILL.md`, plus controller-named task files. Codex sessions:
`AGENTS.md`, `.codex/skills/crypto-core-max-safe/SKILL.md`, the controller evidence packet, exact task files.
ChatGPT controller: active doctrine, `model_prompting_guide.md`, live pinned GitHub evidence,
task-specific surfaces. Deep Research: the connector-bound research packet with pinned repo state, exact repo
files, and external-source requirements. Copilot-specific files (`.github/copilot-instructions.md`,
`.github/prompts/**`, `.github/instructions/**`) are historical compatibility material only while Copilot is
`INACTIVE_UNAVAILABLE`; they do not enter active routing, setup loading, prompt construction, or accepted
state. Every serious agent report states `SETUP_REQUESTED`,
`SETUP_ACTUAL`, `SETUP_FILES_READ`, `SETUP_GAPS`; if automatic loading cannot be proven, the files are
explicitly READ — setup loading is never claimed without proof.

### 24.8 LOW_PROMPT_MAXIMUM_WORK_POLICY

Few prompts, maximum completed safe work. Class A docs/setup PR: ONE executor prompt (precheck → reads →
patch → validation → commit → push → PR → CI snapshot → handoff), then controller connector audit → explicit
human merge authorization → mechanical merge/postverify. Class B ordinary product PR: one implementation
prompt + one controller audit/triage; Terra audit only when risk/evidence requires; at most one consolidated
repair prompt before re-audit. Class C protected PR: one implementation prompt + one focused Codex
independent audit prompt; at most one consolidated same-branch repair prompt per audit cycle; one re-audit
only when the head changed materially; one mechanical merge/postverify prompt after authorization. Never
split a coherent implementation into micro-prompts unless a stop condition is reached. Never combine:
implementation + its independent audit; merge + next feature; unrelated slices; setup + product code;
research + mutation; two implementers; two PRs; final gate + unauthorized merge.

### 24.9 Deep Research operating system

Full active protocol: `docs/crypto_core/deep_research_protocol.md`. XR submodes: `XR_FACT_CHECK` (narrow
current external question, official/primary sources first); `XR_ARCHITECTURE_BENCHMARK` (Hummingbot /
Freqtrade / NautilusTrader / QuantConnect LEAN / credible institutional systems — capabilities and evidence,
never stars/marketing); `XR_PHASE_GATE_REVIEW` (mandatory before material phase transitions involving
external/current assumptions); `XR_OVERENGINEERING_AUDIT` (artifact proliferation vs end-to-end wiring at
milestone boundaries). REQUIRED triggers: current exchange/Deribit facts; fees/rate limits/funding/margin/
liquidation; current microstructure; custody/security/regulation; current framework behavior; paper/live
parity; readiness/shadow/live standards; top-1 benchmark; externally sourced machine-time semantics; current
model/tool behavior. RECOMMENDED: major phase start/closeout, roadmap reorder, significant
execution/risk/connector design, after substantial PR bundles, artifact growth without capability growth,
before major readiness claims. NOT required: repo state, PR state, CI, threads, local tests, branch hygiene,
routine implementation, internal deterministic contracts with no external fact. Event-triggered, never
arbitrary-calendar. Freshness/reuse and the connector-bound research packet + output contract live in the
protocol doc; research stays read-only, advisory, primary-source-first, citation-driven, evidence/inference/
UNKNOWN-separated — no implementation, no GitHub mutation, no merge authority. Mandatory checkpoints:
(1) after this Agent OS PR is audited/merged/postverified → top-1 external architecture + overengineering
benchmark; (2) after SM-5/SM-6 → paper/backtest equivalence + secondary-metrics benchmark; (3) before
external machine-time semantics → targeted fact research; (4) before Deribit/readiness → official Deribit
API/testnet/auth/rate-limit/operational-risk research; (5) before shadow/live → resilience/custody/security/
promotion-gate research. Checkpoints authorize research findings only, never downstream implementation.

### 24.10 CONTROLLER_READONLY_FIRST_POLICY, FABLE5 retirement, and MODEL_EXPECTED_VALUE_PER_TOKEN_POLICY

`CONTROLLER_READONLY_FIRST_POLICY` — ChatGPT GPT-5.6 Thinking is the default connector-backed
read-only-first controller/auditor for all non-Class-C work. It owns by default: live repository/PR/SHA/
open-PR evidence synthesis; tracked-file and dependency surface mapping; full PR patch and exact-scope audit;
setup/workflow/model-routing consistency audits; Class-A independent audit; Class-B first-pass and
controller-only closeout when every no-Codex criterion is proven; the protected-trigger checklist;
fail-closed and negative-test coverage analysis; CI/CodeQL/review-thread final-gate synthesis;
architecture-drift and stale-state detection; Deep Research verification; executor-report verification;
narrow CONTROLLER_TO_IMPLEMENTER and CONTROLLER_TO_AUDITOR packet construction; and next-slice and model
selection. Preserved boundaries (never relaxed): ChatGPT never replaces local tests; never treats memory as
repo state; never performs product implementation; never replaces the Class-C Codex Sol audit; never mutates
GitHub without an exact human action authorization; never grants merge/readiness/live/capital authority.

`FABLE5` retirement — Claude Fable 5 (`claude-fable-5`) is `INACTIVE_EXPIRED_RETIRED`. The former
`FABLE5_PREMIUM_SURGE_LANE` (three modes) and `FABLE5_JUSTIFICATION_GATE` are retired: no active model set,
routing matrix, prompt skeleton, setup-load contract, fallback table, model-selection rule, active handoff
requirement, Deep Research orchestration, or execution plan may reference Fable as an active lane. Former
responsibilities are redistributed: former SURGE_IMPLEMENTER work → Claude Opus 5 xhigh for broad-but-bounded
T3 (Sonnet 5 or Terra for genuinely bounded T2), with no Fable-equivalent quality claim; former
CROSS_CONTRACT_CHALLENGE work → protected Class-C questions to Codex Sol, non-Class-C read-only architecture
and contradiction analysis to the ChatGPT controller (Terra ordinary audit only when controller evidence
requires it); former FULL_REPO_AUDIT work → ChatGPT + GitHub connector as a rare connector-backed read-only
milestone audit (protected disputed questions split into narrow Sol packets; external/current facts to Deep
Research; never a broad milestone audit per PR). Historical Fable evidence (dated changelog, PR history,
`fable_exit_contract_index.md`, sections 20-23) is preserved as HISTORICAL/SUPERSEDED/ARCHIVAL only and never
re-enters active routing.

`MODEL_EXPECTED_VALUE_PER_TOKEN_POLICY` — every serious task selects its model by: safety class, semantic
complexity, required repository breadth, independence requirement, expected prompt count, expected repair
probability, model availability, measured usage/cost in the current harness (never unsupported hard-coded
price rankings), fallback quality, and deadline/throughput. Required prompt fields: `TOKEN_CLASS`,
`TOKEN_BUDGET_ASSESSMENT`, `EXPECTED_VALUE_PER_TOKEN`, `EXPECTED_PROMPTS`, `MAX_REPAIR_CYCLES`,
`CONTEXT_REUSE_PACKET`, `WHY_THIS_MODEL`, `CHEAPER_SAFE_ALTERNATIVE`, `STOP_IF_BUDGET_INSUFFICIENT`.
Rules: Opus 5 = default heavy local executor for broad-but-bounded T3; Sonnet/Terra = bounded economical
work; Luna = mechanics; Sol = protected scarce reasoning (Class C); ChatGPT = read-only-first controller-auditor
that prepares evidence to shrink all executor context and independently audits non-Class-C work; Deep Research
only for external/current questions; correctness is never sacrificed to save tokens. Context economy: consume `AGENT_OS_HANDOFF_V1`
packets; do not reread unchanged broad surfaces; reread pinned changed files + direct dependencies;
invalidate cached context on material head change; summarize successful logs, retain failure tails; exactly
one next safe action.

### 24.11 Live-state policy and non-regression

`LIVE_STATE_POLICY` — this durable routing doctrine pins NO current `main` SHA, latest-merged-PR number, or
open-PR count. Live GitHub/terminal state (current `main` head, merged-PR history, open-PR count, current
blockers, next gated slice) must be re-proven from `git`/`gh`/connector at the start of every task and lives
only in controller handoffs and `CONTROLLER_ACCEPTED_STATE` — never in this durable section. Dated historical
state may appear only in the changelog/history sections below and in archival indexes, explicitly labelled and
never read as current. The secondary-metrics blocker
(`secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1`) and any SM/MT sequence position
are proven from the live repository, not from a pin here. All section-3 hard rules bind unchanged: one open
PR, no direct main push, standard merge only, explicit per-PR human merge authorization, pending CI =
`NOT_READY`, current valid P1/P2 threads block, connector final gate never waived, post-merge verification
before next work, digest-boundary rule, no BIST/live/private-API/order/scheduler/readiness/shadow/capital
surface without separate authorization.

### 24.12 CLAUDE_MODEL_EFFORT_ARCHITECTURE_V1

Effort/thinking architecture for the Claude lanes. The routing matrix (24.3) selects the CLASS and MODEL;
this section selects the EFFORT, the context budget, the subagent and verification policy, and the
escalation/de-escalation rules. Prompt construction and reusable templates live in
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md` — the durable Claude prompting authority.

**Effort ladder.** The user-facing phrase "thinking level" maps operationally to Claude's `effort` setting
(`low`, `medium`, `high`, `xhigh`, `max`). `low` — extremely narrow read-only classification, cheap
high-volume review subtasks, concise extraction where an Opus-specific capability is still required; prefer
Sonnet 5 instead; never for mutation across a trust boundary. `medium` — focused code review, bounded bug
discovery, narrow read-only audit, prompt refinement, constrained architecture comparison, cost-sensitive
Opus work proven sufficient by repository evidence. `high` — nuanced review, architecture selection, complex
prompt design, difficult read-only analysis, moderate multi-step reasoning where long-horizon coding is not
required. `xhigh` — the NORMAL Opus 5 coding/agentic starting point: difficult implementation, multi-file
work, protocol semantics, long-running tool use, complex repair, deep repository exploration, interacting
invariants. `max` — capability-critical only, per the T3B trigger list in 24.3.

Indiscriminate `max` is inefficient, not merely expensive: it lengthens reasoning and latency, multiplies
tool calls and tokens, and invites overthinking and unnecessary scope exploration. `max` is never justified
by a task merely being important. Never `max` for polling, merge closeout, formatting, routine tests, simple
documentation, or ordinary one-line repair. Audit origin is likewise not an effort input on its own: the
fact that work follows a P1/P2 finding says nothing about its complexity, so a mechanical or obvious
post-audit repair stays in the bounded Sonnet lane (T2) and only a complex, semantic, trust-boundary,
protocol/crypto or cross-layer post-audit repair reaches T3B/`max`.

**Codex lane non-regression.** Codex GPT-5.6 Sol (protected T4 `CROSS_CONTRACT_DESIGN_OR_AUDIT`), Terra
(bounded implementation and ordinary independent audit) and Luna (T0 mechanics) are permanent workflow
lanes; nothing in the Claude effort architecture narrows, renames, renumbers or absorbs them, and Class C
always requires a fresh-context independent Codex Sol audit that no Claude lane and no Claude self-review
can satisfy. Temporary model availability or quota state — for any vendor — is transient operational
information, never durable routing: it is recorded in a controller handoff for that task only and never
written into this doctrine.

**Thinking policy.** Adaptive thinking stays enabled. Never request or set `thinking: disabled` for a T3
mutation lane, and never combine disabled thinking with `xhigh` or `max`. Control cost through effort
selection, scope and context — never by suppressing reasoning.

**`TASK_INTENT` — the input contract.** Routing is intent-first. Every task carries exactly one explicit
task family:

```text
TASK_INTENT ∈ { STATUS | CLOSEOUT | BOUNDED_READ | IMPLEMENTATION | REPAIR | REVIEW |
                ARCHITECTURE | PROMPT_ARCHITECTURE | CLASS_C_CROSS_CONTRACT | EXTERNAL_RESEARCH }
```

The family is chosen BEFORE any risk or complexity flag is consulted. Risk and complexity determine the
effort, the context budget, the audit class and the escalation path — they never overwrite the family. A
cryptographic review is still a review. A readiness architecture decision is still architecture. A
capability-critical prompt design is still prompt architecture.

Intent resolution when `TASK_INTENT` is not stated explicitly: derive it from the legacy booleans, but if
more than one of `review_intent` / `architecture_intent` / `prompt_architecture_intent` is set, the task is
`AMBIGUOUS` and routes to `UNRESOLVED`. Never resolve a conflict by falling through to T3B.

**Deterministic routing function.** Evaluate in order; the first matching rule wins. Ordering is
load-bearing: gates first, then family, then effort inside that family.

```text
route(task) -> {TASK_CLASS, MODEL, MODEL_ID, EFFORT, THINKING_POLICY, TOKEN_CLASS,
                CONTEXT_BUDGET_CLASS, SUBAGENT_POLICY, EXTERNAL_RESEARCH_POLICY,
                MUTATION_AUTHORITY, VERIFICATION_PROFILE, STOP_CONDITIONS, REPORT_PROFILE}

inputs: TASK_INTENT; read_only|mutation; mechanical|semantic; known|novel; bounded; file_count;
        module_count; status_or_polling_or_git_hygiene; governed_closeout; review_intent;
        architecture_intent; prompt_architecture_intent; trust_boundary_change; protocol_involved;
        crypto_involved; readiness_or_provenance_effect; class_c_cross_contract;
        interacting_invariants; novel_semantic_contract; fail_closed_artifact_design;
        cross_module_behavior; substantial_validation_loop; architectural_choice_in_scope;
        complex_repair; candidates_interact; multi_module_architecture;
        irreversible_or_high_cost_sequencing; prompt_complex_synthesis;
        prompt_explicit_critical_trigger; prompt_governs_agent_os_or_routing; prior_audit_failure;
        audit_repair_is_mechanical; unexpected_cross_layer_failure;
        controller_designated_capability_critical; external_fact_dependency;
        human_authorization_required; authorization_present; semantic_anomaly;
        readiness_or_connector_transition

--- gates: evaluated before any family ---
 1 external_fact_dependency == load_bearing
   or TASK_INTENT == EXTERNAL_RESEARCH             -> XR   Deep Research (no Claude mutation)
 2 human_authorization_required and not authorization_present
                                                   -> STOP (controller/human)
 3 class_c_cross_contract
   or TASK_INTENT == CLASS_C_CROSS_CONTRACT        -> T4   Codex GPT-5.6 Sol   xhigh
                                                          (controller-gated max; never a Claude lane)
 3b TASK_INTENT == AMBIGUOUS                        -> UNRESOLVED (fail closed, never T3B)

--- mechanical families ---
 4 TASK_INTENT == STATUS and read_only             -> T0   claude-sonnet-5 low
 5 TASK_INTENT == CLOSEOUT and mutation
   and governed_closeout and authorization_present
   and not semantic_anomaly
   and not readiness_or_connector_transition       -> T1   claude-sonnet-5 low
                                                          (a merge IS a mutation and still T1 when
                                                           fully authorized and mechanically bounded)
 6 TASK_INTENT == BOUNDED_READ and read_only
   and (mechanical or bounded)                     -> T1   claude-sonnet-5 low

--- read-only reasoning families: chosen BEFORE any risk escalation ---
 7 TASK_INTENT == REVIEW                           -> T3C  claude-opus-5
      protocol / crypto / trust-boundary / multi-trust-boundary /
      conflicting findings / cross-layer                        -> xhigh
      broad / security-sensitive / post-failure                 -> high
      focused (<= 2 files), no such complexity                  -> medium
      A review NEVER becomes T3B because crypto_involved,
      readiness_or_provenance_effect, trust_boundary_change or
      prior_audit_failure is set. Review stays read-only; any
      resulting mutation is a SEPARATE, explicitly created task.
 8 TASK_INTENT == ARCHITECTURE                     -> T3D  claude-opus-5
      readiness/provenance, cryptographic boundary,
      irreversible/high-cost sequencing, controller-designated     -> max
      interacting candidate slices or several modules             -> xhigh
      ordinary bounded architecture                               -> high
      Architecture NEVER becomes T3B merely because its SUBJECT is
      readiness, provenance or cryptography. T3D stays read-only
      and produces a decision, not a diff.
 9 TASK_INTENT == PROMPT_ARCHITECTURE
      known and mechanical and bounded and no critical trigger    -> T2  claude-sonnet-5 medium
      Agent OS / model-routing prompt, prompt governing readiness
      or provenance promotion, prompt governing cryptographic
      verification, capability-critical controller repair prompt,
      controller-designated critical prompt                       -> T3E claude-opus-5 max
      protocol/crypto/readiness synthesis, several safe paths,
      post-audit-failure synthesis                                -> T3E claude-opus-5 xhigh
      ordinary complex prompt architecture                        -> T3E claude-opus-5 high

--- implementation / repair family only ---
10 TASK_INTENT ∈ {IMPLEMENTATION, REPAIR} and mutation
   and named_capability_critical_trigger != none   -> T3B  claude-opus-5   max
      named triggers (explicit, exhaustive):
        cryptographic verification boundary implementation
        readiness/provenance promotion implementation
        protocol ambiguity with safety consequences inside an implementation
        complex trust-boundary repair
        complex semantic P1/P2 repair after a failed audit
              (prior_audit_failure and not audit_repair_is_mechanical
               and (semantic or trust_boundary_change or protocol_involved or complex_repair))
        unexpected cross-layer implementation failure
        explicit controller-designated capability-critical implementation/repair
      T3B requires mutation AND implementation/repair intent. It can never accept
      REVIEW, ARCHITECTURE or PROMPT_ARCHITECTURE. A bare risk flag and a bare
      audit origin both remain insufficient.
11 TASK_INTENT ∈ {IMPLEMENTATION, REPAIR} and mutation
   and (semantic or protocol_involved)
   and complexity_evidence(task) != none
   and named_capability_critical_trigger == none   -> T3A  claude-opus-5   xhigh
      complexity_evidence (any one suffices):
        interacting_invariants | novel_semantic_contract | fail_closed_artifact_design |
        cross_module_behavior | substantial_validation_loop | architectural_choice_in_scope |
        complex_repair
      file_count/module_count are NOT complexity criteria. A two-file
      production+test protocol-semantic slice is correctly T3A/xhigh.
12 mutation and known and bounded and mechanical
   and not trust_boundary_change and not protocol_involved
   and not crypto_involved
   and not readiness_or_provenance_effect          -> T2   claude-sonnet-5 medium (high if moderate)
                                                          (prior_audit_failure alone never overrides
                                                           this rule)
13 otherwise                                       -> UNRESOLVED
```

Fail-closed behavior. `UNRESOLVED` classification → perform read-only Opus 5 `high`/`xhigh` analysis and do
NOT mutate until the controller selects the lane. Conflicting task families without an explicit
`TASK_INTENT` → `UNRESOLVED`, never a silent T3B. Current external facts required → route to Deep Research.
Merge authorization required and absent or ambiguous → stop. Actual model or effort mismatched against the
requirement → stop before mutation (a human may waive an effort mismatch for a specific task; record the
waiver and the true actual). Fallback occurred → stop before mutation. Active PR collision → stop.
Readiness or connector transition detected → stop and escalate — and note that rule 5 is void whenever such
a transition is present, so a closeout that would move readiness or connector state can never stay T1.

Precedence guarantees. The ordering above exists to prevent ten specific failures: current external facts
being inferred locally (rule 1 first); Class-C cross-contract work being absorbed by a Claude lane (rule 3
precedes every Claude rule); conflicting intent silently resolving to a capability-critical lane (rule 3b);
T0 being shadowed by the generic read-only rule (rule 4 precedes rule 6); an explicitly authorized merge
closeout falling through to T2 (rule 5 precedes rule 12); **a review being consumed by T3B because its
subject is cryptographic or trust-boundary (rule 7 precedes rule 10)**; **an architecture decision being
consumed by T3B because its subject is readiness, provenance or cryptography (rule 8 precedes rule 10)**;
**a capability-critical prompt design being consumed by T3B instead of reaching the T3E `max` branch (rule 9
precedes rule 10)**; a simple mechanical post-audit repair jumping to `max` (rule 10 requires a named
trigger and excludes mechanical audit repair); and bounded two-file protocol-semantic work becoming
`UNRESOLVED` (rule 11 uses complexity evidence, not file count).

De-escalation is mandatory, not optional: when the proven scope turns out narrower than classified (fewer
files, no trust boundary, mechanical repair), drop to the lowest lane that still proves correctness for the
REMAINING work rather than finishing at the original lane. Escalation requires a stated reason recorded in
the handoff; `max` additionally requires naming which T3B trigger fired.

**Context budget classes.** `MINIMAL` (T0/T1) — exact commands and named files only. `BOUNDED` (T2/T3C
focused) — named files plus immediate dependency interfaces. `BROAD_BUT_BOUNDED` (T3A/T3B/T3C broad/T3D/T3E)
— authoritative setup files, directly affected production/test files, immediate dependency interfaces, and
relevant current PR/main evidence. Never automatically read the whole repository, every historical lesson,
unrelated modules, stale archives, old prompts, or generated output. Expand only on progressive disclosure:
an unresolved reference, an invariant crossing modules, a test-exposed dependency, or architecture that
cannot be proven locally. Pin exact SHAs, branch, PR head, file paths, profile ids, digests, tests and the
current open-PR count — never rely on conversational memory for live repository state.

**Subagent policy.** Default `0`. Bounded one- or two-file work: `0`. Maximum: `2` read-only subagents, only
for genuinely independent, substantial, parallelizable investigation tracks. Never for routine commands,
polling, duplicate self-review, one- or two-file patches, or work finishable through a few direct tool
calls. Only one agent may mutate a branch or worktree, and the primary agent independently validates every
subagent conclusion.

**Verification calibration.** Keep every explicit deterministic gate (scoped Ruff/format, targeted pytest,
logged full suite via `run_full_tests_logged.ps1`, `git diff --check`, exact-scope diff proof, terminal CI
and CodeQL to a terminal state). Remove vague repetition — "verify everything repeatedly", "double-check
every step several times", "continue reviewing until perfect". Run each relevant gate once per unchanged
head; rerun only after a relevant mutation or invalidating evidence.

**Behavior calibration (active prompt guidance for the Claude lanes).** Scope: deliver exactly the
authorized task at the intended scope; make routine implementation judgements independently; never widen,
narrow or transform the slice; when a materially better architecture requires scope expansion, report it and
stop before unauthorized mutation. Decision commitment: select the strongest evidence-supported design and
proceed; reopen a settled decision only when new repository or test evidence directly contradicts it.
Progress narration: one concise sentence before the first tool call, then only material findings, blockers,
direction changes and phase transitions — never routine-command narration. Self-correction: correct an
earlier statement only when the error changes code, conclusions, authorization or the next action; fix
non-material slips silently. Review independence: a same-model self-review is labelled
`SELF_AUDIT_ONLY_NOT_INDEPENDENT` and never satisfies an independent audit — Class C always needs a fresh
Codex Sol context. Review process: discover every evidence-backed issue without severity filtering, classify
severity after discovery, then separate blocker from non-blocker. Visible output stays compact and
evidence-dense: decisions, evidence, commands and results, blockers — never internal chain of thought.

**Sonnet 5 prompt shape.** Sonnet prompts stay concise, mechanically explicit, low-context,
command-oriented, deterministic and bounded, with explicit terminal-CI polling, explicit escalation
triggers, and an explicit no-scope-expansion rule. Do not burden them with architecture speculation,
repository archaeology, broad alternative analysis, maximum-thinking language, long report formats, or
Opus-only subagent instructions. Sonnet remains the fastest safe lane for T0/T1/T2.

**`ULTRACODE_POLICY`.** If a Claude Code build exposes `ultracode`, it is an ORCHESTRATION MODE, not an API
effort level (the effort levels are exactly `low`, `medium`, `high`, `xhigh`, `max`). It is never a routing
default and is never persisted. Use it only when runtime-proven in the active local setup, explicitly
controller-authorized, and justified by genuinely independent substantial parallel work with isolated
ownership, no overlapping mutations, and primary-agent verification of every result. Otherwise use normal
single-agent `xhigh`/`max` execution.

---

*v4.1 (2026-06-15): rewrote the model-role model to the current three-role protocol — Claude =
implementation/repair/closeout executor, Codex = asynchronous adversarial P1/P2 reviewer, ChatGPT = live
GitHub controller. Preserved the durable digest-boundary rule, validation policy (`run_full_tests_logged.ps1`),
and state-claim policy. Companion prompt lanes remain in `docs/crypto_core/agent_prompts/token_efficiency_v2.md`.*

*v4.2 (2026-06-21): converged agent-workflow setup after PR #288 merged. Added Codex Pursue Goal (§2a,
scoped to mechanical GitHub/CI loops) and GitHub-connector roles to §2; CI-not-registered diagnosis +
single-authorized-retrigger, branch-naming reconciliation (`feature/*`, `chore/*`; `product/*` superseded),
and setup-PR-separation hard rules (§3); the controlled self-improvement loop (§17) + lessons ledger
(`docs/crypto_core/agent_lessons.md`); and doctrine precedence / legacy-surface override (§18). Companion
setup changes (this PR, docs/config only): neutralized `.vscode/mcp.json` (no servers), added
`.vscode/extensions.json`, made `.cursor/rules/prdv3-constitution.mdc` historical/non-applying, and added the
read-only `scripts/crypto_core/audit_agent_setup.ps1`. No product code touched.*

*v4.3 (2026-06-21): added the Deep Research & GitHub Connector protocol — a Deep Research role row in §2,
a new §19 summary, and the full companion `docs/crypto_core/deep_research_protocol.md` (role, combined
repo+external review with the `REPO_EVIDENCE`/`EXTERNAL_EVIDENCE`/`INFERENCE`/`UNKNOWN` separation,
routing, triggers, output contract, and misuse prevention). Deep Research is **strictly read-only /
advisory** — never an executor lane, never merge authority, never a safety-gate waiver; it may recommend
a mutation task but never executes one (the controller routes authorized mutations to Claude/`gh`, the
GitHub connector, or Codex). Docs/config only; no product code touched.*

*v4.4 (2026-07-04; HISTORICAL / SUPERSEDED for active model routing): added §20 Multi-Model Routing Doctrine (Fable 5 era) — Fable 5 as the premium
high-reasoning lane (with explicit non-use cases), Opus 4.8 as implementation/repair/fallback, Fast
Auto/Sonnet as the mechanical lane, Codex/connector/Deep Research roles restated, the Claude/Codex setup
auto-use doctrine (`AUTO_SETUP_LOADING_PROOF: PARTIAL`), the lane-annotated PR lifecycle with the
GitHub-connector final gate, current next-slice routing (`PaperStage4ComparisonEvidence` → Fable 5 design
first; Decimal Sharpe-retention recompute; `PaperStage4CompletionDecision` after; operational-day gate
deferred), and six future prompt templates. Updated the §2 Claude role row and routing summary to the
Fable 5 era. §20 supersedes the consult-only framing of `LANE:FABLE-ARCH` (the lane file's token-discipline
spirit carries over unchanged). No safety gate weakened; docs only; no product code touched.*

*v4.5 (2026-07-10): synchronized active GPT-5.6 Sol/Terra/Luna + Claude Opus 4.8 routing. Added common T0-T4 plus XR taxonomy, actual-model/fallback fields, fresh-context independent audit rule, bounded Pursue Goal, emergency/stale-metadata sublanes, post-#328 state, and active prompt policy. Sections 20-21 and Fable ownership remain historical. Docs/setup only; no product code touched.*

*v5.0 (2026-07-10): one-time final Agent OS migration (executed by Claude Fable 5 as migration-only agent).
Added section 24 `CRYPTO_CORE_AGENT_OS_V1`: final durable model set (ChatGPT GPT-5.6 Thinking controller +
GitHub connector + Deep Research, Claude Opus 4.8, runtime-proven Claude Sonnet 5, Codex Sol/Terra/Luna,
Copilot Pro local Agent as execution host), identity rules, `CRYPTO_CORE_DOMAIN_OPERATING_PROFILE`,
model-neutral T0-T4 taxonomy labels, optimal routing matrix, audit Class A/B/C,
`CONTROLLER_ACCEPTED_STATE` + conflict precedence, `AGENT_OS_HANDOFF_V1` + role packets,
`SETUP_LOAD_CONTRACT_V1`, `LOW_PROMPT_MAXIMUM_WORK_POLICY`, Deep Research OS (four XR submodes,
event-triggered checkpoints), and post-#330 state pins. Fable 5 removed from all active routing, prompts,
fallbacks, and roadmaps at that date (historical/archival references only; superseded by v5.1's conditional
reintroduction). Section 23 marked superseded. Docs/setup only; no product code touched; no gate weakened.*

*v5.1 (2026-07-10): Fable 5 premium-surge calibration (same PR, same branch; runtime availability
re-proven). Reintroduced Claude Fable 5 as an ACTIVE but CONDITIONAL lane: `FABLE5_PREMIUM_SURGE_LANE`
(three mutually exclusive modes — SURGE_IMPLEMENTER T3, CROSS_CONTRACT_CHALLENGE T4 read-only,
FULL_REPO_AUDIT rare read-only), `FABLE5_JUSTIFICATION_GATE` (mandatory pre-spend justification + fallback
declaration), and `MODEL_EXPECTED_VALUE_PER_TOKEN_POLICY` (evidence-based model selection; measured harness
cost, never hard-coded price rankings). Calibrated from repo evidence (PR #315-#318, #330-#331, 2026-07-10
full-repo audit). No dependency, no fixed expiry, runtime proof + gate required per prompt; Opus 4.8 stays
default heavy executor; Sol Class-C audit untouched and never replaceable by Fable; chain updated with
MODEL_SELECTION_WITH_TOKEN_GATE and FABLE_SECOND_OPINION_IF_JUSTIFIED. Docs/setup only; no gate weakened.*

*v5.2 (2026-07-20): Fable retirement + controller read-only-first expansion. Claude Fable 5 moved to
`INACTIVE_EXPIRED_RETIRED` and removed from every ACTIVE surface — the active set is now exactly eight lanes
(ChatGPT GPT-5.6 Thinking, GitHub connector, Deep Research, Claude Opus 4.8, Claude Sonnet 5, Codex Sol/Terra/
Luna); the `FABLE5_PREMIUM_SURGE_LANE`, its three modes, `FABLE5_JUSTIFICATION_GATE`, the
`FABLE_SECOND_OPINION_IF_JUSTIFIED` chain step, and Fable session/handoff fields are retired (§24.1, §24.3,
§24.5, §24.7, §24.8, §24.10). Former Fable responsibilities redistributed: SURGE_IMPLEMENTER → Opus 4.8
(bounded T2 → Sonnet 5/Terra); CROSS_CONTRACT_CHALLENGE → Sol (Class C) / ChatGPT controller (non-Class-C
read-only) with Terra only when evidence requires; FULL_REPO_AUDIT → ChatGPT + connector rare read-only
milestone audit. Introduced `CONTROLLER_READONLY_FIRST_POLICY` (§24.10) — ChatGPT is the default
connector-backed read-only-first controller/auditor for non-Class-C work, with preserved boundaries (never
replaces local tests, memory-as-state, product implementation, Class-C Sol, unauthorized GitHub mutation, or
merge/readiness/live/capital authority). Class B restated as controller-first (Terra conditional); Class C /
mandatory fresh Sol audit unchanged; Opus default-heavy, Sonnet/Terra/Luna preserved; Copilot stays
`INACTIVE_UNAVAILABLE`. Replaced the hardcoded current-state pins in §24.11 with `LIVE_STATE_POLICY` (live
GitHub/terminal state re-proven per task; no durable SHA/PR pins; dated history stays in changelog only).
Historical Fable material (sections 20-23, `fable_exit_contract_index.md`, dated changelog) preserved as
HISTORICAL/SUPERSEDED/ARCHIVAL. Docs/setup only; no product code touched; no safety gate weakened.*

*v5.3 (2026-07-25): Claude Opus 5 Agent OS migration. Claude Opus 4.8 replaced by **Claude Opus 5**
(`claude-opus-5`) in every ACTIVE routing surface and marked `SUPERSEDED_BY_OPUS_5`; dated Opus 4.8
execution records, archived prompts, design docs and changelog entries are preserved untouched as
HISTORICAL evidence. The active set stays exactly eight lanes and Copilot stays `INACTIVE_UNAVAILABLE`;
Fable stays `INACTIVE_EXPIRED_RETIRED` with no routing change; Codex Sol/Terra/Luna doctrine, audit classes
A/B/C, the Class-C requirement, the connector gate and explicit human merge authorization are unchanged.
§24.3 is now the single `AUTHORITATIVE_ROUTING_MATRIX` — every other active surface references it instead of
restating it — and subdivides the Claude heavy class into T3A complex implementation (xhigh default), T3B
capability-critical (max, explicit narrow triggers), T3C review (medium focused / high broad / xhigh
multi-trust-boundary), T3D architecture and next-slice (high, xhigh when slices interact), and T3E complex
prompt architecture (high, xhigh on synthesis); Sonnet 5 is restated as the DEFAULT Claude lane for T0/T1
(low) and T2 (medium) with explicit escalation triggers. Added `CLAUDE_EXACT_MODEL_ID_RULE` (§24.1: exact
model id, session-level model AND effort proof, aliases insufficient, recorded human waiver never restated
as the requested value) and §24.12 `CLAUDE_MODEL_EFFORT_ARCHITECTURE_V1` (effort ladder low→max with
anti-`max` economics, adaptive-thinking-always-on rule, an ordered deterministic routing function with
fail-closed and mandatory de-escalation behavior, context-budget classes with progressive disclosure,
subagent policy default 0 / max 2 read-only, verification calibration that keeps deterministic gates and
deletes generic re-verification loops, behavior calibration for scope/decision-commitment/narration/
self-correction/review-independence, Sonnet prompt shape, and `ULTRACODE_POLICY` classifying `ultracode` as
a non-default orchestration mode, never an effort level). Added the durable
`docs/crypto_core/agent_prompts/opus5_prompting_playbook.md` (effort-selection guide, user prompting guide,
eleven reusable templates, and the `PROMPT_COMPILER_CONTRACT_V1` that emits exactly one best prompt).
Label reconciliation is explicit: unsuffixed "T3" means T3A, "external facts" means `XR`, "controller and
human authority" means `CONTROLLER_CONNECTOR_GATE`; the numbered `T4` stays
`CROSS_CONTRACT_DESIGN_OR_AUDIT` so Codex doctrine is not renumbered. Docs/setup only; one assertion string
updated in the read-only advisory `scripts/crypto_core/audit_agent_setup.ps1` so its expected-lane check
tracks the renamed lane; no product code, tests, dependencies or CI workflows touched; no readiness or
connector transition; no safety gate weakened.
Same-PR controller repair (2026-07-25): the section 24.12 routing function was rewritten after a controller
audit found four deterministic contradictions against the 24.3 matrix — T0 shadowed by the generic
read-only rule, an explicitly authorized merge closeout falling through to T2 because it is a mutation, a
bare `prior_audit_failure` escalating every post-audit repair to `max`, and bounded two-file
protocol-semantic work becoming `UNRESOLVED` because complexity was gated on file count. The function now
orders specific rules before generic ones, adds an explicit Class-C rule so Codex Sol work is never absorbed
by a Claude lane, requires a NAMED capability-critical trigger for T3B, proves T3A complexity by evidence
rather than file count, and keeps an authorized mechanically bounded merge in T1. Sixteen deterministic
routing cases pass. Codex Sol/Terra/Luna lanes, the Class-C requirement, T4, the XR boundary, controller and
human merge authority are all unchanged, and no temporary model-availability state is persisted.
Second same-PR controller repair (2026-07-25): a further exact-head audit found that the generic T3B
capability-critical rule preceded the intent-specific T3C/T3D/T3E rules and carried no intent guard, so a
read-only cryptographic review, a readiness/provenance architecture decision and a capability-critical
prompt design were all consumed by T3B/`max` — executed against the previous function, all four reported
scenarios misrouted, which also made the documented T3E `max` branch unreachable. Routing is now
INTENT-FIRST: an explicit `TASK_INTENT` field (`STATUS`, `CLOSEOUT`, `BOUNDED_READ`, `IMPLEMENTATION`,
`REPAIR`, `REVIEW`, `ARCHITECTURE`, `PROMPT_ARCHITECTURE`, `CLASS_C_CROSS_CONTRACT`, `EXTERNAL_RESEARCH`)
selects the family before any risk flag is read; risk and complexity now choose only the effort inside that
family; T3B requires mutation plus IMPLEMENTATION/REPAIR intent and explicitly cannot accept review,
architecture or prompt-architecture work; T3C reaches `xhigh`, T3D `max` and T3E `max` inside their own
families; and conflicting families without an explicit `TASK_INTENT` fail closed to `UNRESOLVED` rather
than to T3B. Twenty-five deterministic routing cases pass. Codex Sol/Terra/Luna, Class C, T4, XR,
controller and human merge authority remain unchanged; no temporary model-availability state is persisted.
Third same-PR controller repair (2026-07-25, T2 bounded doctrine alignment): fixed three residual textual
contradictions left over from the intent-first rewrite. (1) The playbook's top-level T3B trigger inventory
still listed architecture-family concepts (Agent OS architecture, model-routing migration, several
plausible architectures with materially different safety outcomes) even though the function itself had
already scoped T3B to implementation/repair only; the inventory is now implementation/repair-scoped and
states explicitly that those three concepts route to T3D or T3E, never T3B, unless the actual authorized
task is an implementation/repair mutation that also fires a named T3B trigger. (2) The prompt-compiler's
`max`-effort rule required a T3B trigger for every `max` selection, which would have forced a `max`-effort
T3D or T3E task to be misdescribed as T3B; it now requires a family-specific named trigger (T3B
implementation/repair, T3D architecture, T3E prompt-architecture) and states that `TASK_INTENT` fixes the
family before this rule runs. (3) The 24.3 matrix's T0 row still listed "authorized merge mechanics,
postverify" in its Use column, overlapping T1's governed-closeout family; T0 is now STATUS-only (git/gh
state, CI polling, PR metadata, thread status, open-PR counts, clean-tree checks, status reporting) and T1
is stated as the sole owner of governed closeout including postverify. Template 3.1 and the T3B/T3D/T3E
templates were reworded to match. Twenty-nine deterministic routing cases pass, including four new cases
proving an Agent-OS architecture decision stays T3D/max, a model-routing prompt stays T3E/max, a named
capability-critical implementation reaches T3B/max, and an authorized merge stays T1/low with no T0 overlap.
No routing architecture, task-intent family or Codex doctrine changed; docs only, two files.*

<!-- HISTORICAL_RECORD_END -->
