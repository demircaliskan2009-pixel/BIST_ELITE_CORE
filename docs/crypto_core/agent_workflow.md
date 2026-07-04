# crypto_core Agent Workflow v4.2

> Canonical, executable operating protocol for `crypto_core` inside `demircaliskan2009-pixel/BIST_ELITE_CORE`.
> Companions (durable rails, not re-pasted into prompts): `AGENTS.md`,
> `.codex/skills/crypto-core-max-safe/SKILL.md`, `CLAUDE.md` / `CLAUDE.local.md`,
> `docs/crypto_core/agent_lessons.md` (evidence-backed lessons), and
> `docs/crypto_core/agent_prompts/token_efficiency_v2.md` (prompt lanes). **Canonical doctrine precedence**
> for active work: `AGENTS.md` + this file + `.codex/skills/crypto-core-max-safe/SKILL.md` (then `CLAUDE.md`).
> Anything under `.github/prompts`, `.github/skills`, `.github/instructions`, `.cursor/rules`, or other legacy
> surfaces is **overridden by this canonical doctrine** wherever they conflict (see §18). On any apparent
> conflict the **stricter safety rule wins**. This document contains **no secrets, credentials, API keys,
> exchange credentials, or live-trading instructions**, and instructs no real order flow.

## 1. Purpose

Persist one command-level, auditable workflow so every Claude / Codex / ChatGPT turn does the **maximum
safe bounded work per prompt** while preserving the crypto_core standard: **paper-first, deterministic,
fail-closed, audit-first, derivatives-first, governance-first, risk-bounded**. Active scope is
`src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, `docs/crypto_core` only. BIST is historical
context — never implemented here.

## 2. Model / Tool Roles

| Role | Responsibility |
|---|---|
| **ChatGPT** (controller) | **Sequence owner** — authors prompts; verifies live head/files/checks/threads/open-PR state; issues verdicts `ACCEPT / REPAIR / REJECT / CODEX_REQUIRED / GITHUB_CONNECTOR_REQUIRED / MERGE_AUTH_REQUIRED`; decides **when** to use Claude, Codex, Codex Pursue Goal, the GitHub connector, and Deep Research. Owns merge authorization (per-PR, exact command). |
| **Claude** (local agent — Fable 5 / Opus 4.8 / Fast Auto–Sonnet model lanes, §20) | Implementation / repair / closeout **executor**. Bounded feature slices, multi-file patching, full local validation loops, commit/push/PR creation, same-turn same-branch repair after a local validation failure, CI diagnosis when implementation context is needed, standard merge **only on explicit per-PR authorization**, post-merge verify. The model tier for each Claude task is picked by the §20 routing doctrine (Fable 5 = premium reasoning; Opus 4.8 = implementation/repair/fallback; Fast Auto/Sonnet = mechanical). |
| **Codex** | **Adversarial P1/P2 reviewer** — hidden-bug / exploit hunting, digest/schema/API-contract review, provenance/evidence-chain audit. **Read-only by default**; patches only when patching is **explicitly authorized and scoped**. Runs **asynchronously**; never merges. |
| **Codex Pursue Goal** | **Bounded single-goal terminal loop** for mechanical GitHub/CI state. Use **only** for the cases in §2a. |
| **GitHub connector / gh-native fallback** | **Source-of-truth GitHub state gate** — PR/CI/thread/review/final merge-readiness audit. **Read-only** unless an action is explicitly authorized. |
| **Deep Research** | **External / current-fact + architecture-benchmark research** (and, in the GitHub connector chat, combined repo+external review). **Strictly read-only / advisory** — never an executor lane, never merge authority, never a safety-gate waiver; it may recommend a mutation task but never executes one (the controller routes authorized mutations to Claude/`gh`, the connector, or Codex). ChatGPT decides when it is used; full protocol in §19 / `docs/crypto_core/deep_research_protocol.md`. |

Model-tier routing is §20 (Fable 5 era): **Fable 5** is the premium high-reasoning lane (use first, when
available, for design/governance/adversarial/correctness work), **Opus 4.8 xhigh** the
implementation/repair/fallback lane for contract/digest/fail-closed/review-blocker work, and **Fast
Auto/Sonnet** the mechanical lane; status/polling/mechanical steps always use the cheapest sufficient lane.

### 2a. Codex Pursue Goal — scope

**Use Pursue Goal for:** CI polling to terminal; repo/branch sync; PR closeout / status loops;
review-thread disposition **planning**; GitHub/`gh` state loops; merge / post-merge verification **when
explicitly authorized**; any one-goal task needing a terminal `PASS / FAIL / BLOCKED`.

**Do NOT use Pursue Goal for:** complex implementation; big design decisions; digest/provenance architecture;
ambiguous product slicing; multi-file repair (unless explicitly scoped and authorized). Those route to
Claude (executor) under ChatGPT's direction.

## 3. Hard Rules

- crypto_core only; **no BIST implementation leakage** (BIST is historical context).
- **One open PR at a time.** Verify live (`gh pr list --state open`) at the start of every task.
- **No direct push to `main`.** No force-push. No branch deletion unless the authorized command says so.
- **Standard merge only** (no squash/rebase). **No merge without explicit human authorization naming the PR and the exact command.**
- **CI `pending` / `queued` / `in_progress` / `no checks reported` is NOT_READY** — keep polling to terminal, or report a bounded-timeout snapshot. Never treat a startup window as green.
- **CI not registered (no run created for a fresh head): diagnose before re-triggering.** Prove it from `gh run list` / commit `check-runs` and classify (`ACTIONS_DELAY_OR_GITHUB_INFRA` vs trigger/path/ref issue). At most **one** empty re-trigger commit (`chore(crypto-core): retrigger …`), and **only** with explicit user/controller authorization. Never loop no-op commits.
- **Branch naming:** feature slices → `feature/<crypto-core-scope>-prN`; setup/docs → `chore/<crypto-core-scope>-prN`; repair stays on the **same branch** for the same PR. (Older `product/*` naming is superseded.)
- **Setup/doctrine changes are never mixed into a feature PR.** Feature PRs touch `src/`/`tests/` product code; setup PRs touch docs/config only (`AGENTS.md`, `docs/crypto_core/**`, `.codex`, `.vscode`, `.cursor`, `.github` docs, `scripts/crypto_core` audit tooling). See §17.
- **Codex review is asynchronous** and is a **separate gate** — an implementation/repair turn ends at terminal CI + report; it does not block waiting for review.
- Every repo-state claim must be **git/gh/test-verifiable** (never from memory). Unproven → mark `UNKNOWN`.
- **Same-branch repair only** for valid in-scope P1/P2; stop on unsafe scope expansion.
- No live/private API, real orders, order routing, scheduler, auto-loop, connector/readiness, runtime/orchestrator, or shadow/live unless **explicitly scoped and separately designed**.
- No hidden IO/env/random/wall-clock/threading/subprocess in product code unless explicitly scoped.
- No `gh pr review --approve` (self-approval) ever.
- **Digest-boundary rule (recurring P1 class):** any consumer of a digest-carrying object must recompute the upstream digest via the **public serializer** (remove the self-digest field, canonical JSON `sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False`, SHA-256) and **reject mismatch before READY/ADMITTED/ACCEPTED**. A matching id is never sufficient; a forged/non-serializable upstream must hit the `*_mismatch` path, never a raw `TypeError`. Tests must include a tampered-field case.

## 4. Standard PR Lifecycle

1. ChatGPT selects one bounded slice → one Claude implementation prompt (pinned expected `main` HEAD, "open PRs: none").
2. Claude executes the **Implementation Loop** (§5) → opens one PR → polls CI to terminal → reports. No merge.
3. Codex performs adversarial P1/P2 review **asynchronously** (§8).
4. ChatGPT verifies live GitHub state and issues a repair / merge / next prompt (§9).
5. Claude runs the **Repair Loop** (§6) on the same branch if instructed.
6. Claude runs the **Closeout/Merge Loop** (§7) **only** from an explicit closeout authorization.
7. Claude runs **Post-Merge Verification** (§12) and stops. ChatGPT selects the next slice (§15).

## 5. Claude Implementation Loop

```
# precheck on updated main — for base / SHA proof ONLY; main is never edited or committed on
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD                         # MUST equal the prompt's expected SHA
git status --short --branch                # MUST be clean + in sync
gh pr list --repo demircaliskan2009-pixel/BIST_ELITE_CORE --state open --json number,title,headRefName,baseRefName,url   # MUST be []

# create + switch to a topic branch BEFORE any patch/commit/push (never edit/commit on main)
git switch -c <topic-branch>               # feature/<crypto-core-scope>-prN (feature) or chore/<crypto-core-scope>-prN (setup/docs)
git status --short --branch                # confirm: on the topic branch, clean
# patch only after this point
```

**Branch invariant (implementation mode — always holds):**
- `main` is checked out **only** for precheck / base-SHA proof — never edited, never committed on.
- Claude **creates and switches to a topic branch** (`git switch -c <topic-branch>`) before the first edit.
- **All commits and pushes happen on the topic branch**; never `git commit` on `main`, never push to `origin/main`.
- The PR is opened **from the topic branch into `main`** (`gh pr create --base main --head <topic-branch>`).

Then (all on the **topic branch**): bounded read (named files only, no broad scan) → design → smallest
additive patch (enforce allowed-files + max-changed-files) → self-audit (scope / digest re-proof /
provenance / strict-Decimal / fail-closed / no hidden IO / paper-safety triple) → targeted tests →
relevant suite → **full helper after meaningful changes** → `git diff --check` → scoped `git add <paths>` →
commit (on the topic branch) → push (the topic branch) → `gh pr create --base main --head <topic-branch>` →
**poll CI to terminal** (§ CI rule in §3) → inspect threads that exist (§8) → report (§10). **No merge.**

## 6. Claude Repair Loop

- Precheck first (branch + `HEAD == expected SHA` + clean tree + exactly one open PR + changed files ⊆ scope).
- Pin PR number and expected head; repair **only the named blockers**, **same branch only**, bounded to named files.
- **Test-only by default**; touch production only if a **new failing test proves a real defect**, and only inside the named module. If test-only, prove `git diff <prev> HEAD -- src/` is **empty**.
- Re-validate fully (targeted → relevant suite → full helper `PYTEST_EXIT=0` → `git diff --check`) → scoped add → commit → push same branch → **re-poll CI to terminal** → report. **No merge.**

## 7. Claude Closeout / Merge Loop

Run **only** from an explicit closeout prompt that names the PR and the exact authorized command.

- Re-prove freshly (no memory): `HEAD == authorized SHA`; `state == OPEN`; `mergeable == MERGEABLE`;
  `mergeStateStatus == CLEAN`; changed files == expected set; CI terminal green/skip; exactly one open PR;
  zero unresolved valid review threads.
- Resolve **only** review threads explicitly named in the closeout prompt, and **only after** proving the
  fix exists in source at the current HEAD (line-cited). Never self-resolve otherwise.
- Merge with the exact authorized command (standard `--merge`, `--delete-branch=false`).
- **On 502/timeout/empty output: do NOT blind-retry.** Verify first:
  `gh pr view <#> --json state,mergedAt,mergeCommit,mergedBy,headRefOid` and `git rev-parse origin/main`.
  If `MERGED` → continue to §12. Else report `MERGE_TRANSIENT_NOT_MERGED` and stop.
- If the PR is **already MERGED** before the merge command (stale prompt) → no-op, verify main contains the merge commit, continue to §12.

## 8. Codex Review Protocol

- Codex runs **asynchronously** after a push; findings may not exist when Claude's turn ends. Claude inspects threads that exist at terminal CI and reports `0 threads (review may post later)` if none.
- Inspect via GraphQL: `reviewThreads(first:n){ nodes{ id isResolved isOutdated path line comments } }` + `reviews`.
- Codex emits the report in §10. ChatGPT relays valid findings (with thread IDs) as a dedicated Claude repair prompt; Claude does not wait in-turn for review.

## 9. ChatGPT Controller Gate

ChatGPT independently re-verifies live GitHub state (head SHA, files, checks `name=conclusion`, threads,
open-PR rule) before any verdict, and issues exactly one next prompt. Merge authorization must name the PR
and the exact standard-merge command. ChatGPT emits the verdict format in §10.

## 10. Required Report Formats

**Claude (every task) — fixed fields, all repo claims git/gh/test-verifiable:**
```
RESULT / PR / HEAD_SHA / BRANCH / FILES_CHANGED / COMMITS / VALIDATION / CHECKS /
REVIEW_THREADS / SCOPE_CONFIRMATION / FINAL_GIT_STATUS / BLOCKERS / NEXT_SAFE_ACTION
```
The **last** element of every Claude task message is a single self-contained, copy-paste **ChatGPT handoff
code block** (repo; PR number/state; branch/head SHA/base SHA; files changed; commits; checks; review
threads; validation commands+results; open-PR state; exact `gh`/`git` verification commands). No full logs
(failure tails only); no uncited state.

**Codex (review):**
```
VERDICT / P1_BLOCKERS / P2_BLOCKERS / NON_BLOCKING_NOTES / MERGE_READINESS / REQUIRED_REPAIRS_IF_ANY
```

**ChatGPT (controller verdict):**
```
VERDICT / PROOF / REASON / NEXT_PROMPT
```

## 11. Merge Gate

Merge only if **all** are true (each freshly proven):
HEAD == authorized SHA · PR `state == OPEN` · `headRefOid == authorized SHA` · changed files == expected
set · exactly one open PR (this one) · CI checks terminal **green or accepted skip only** (no
pending/queued/in_progress/no-checks) · zero unresolved valid review threads · working tree clean · any
test-only repair proven to have no `src/` change · no forbidden-scope surface (§16) · no protected-contract
weakening · explicit human authorization with PR + exact command. Any miss → stop with proof, do not merge.

## 12. Post-Merge Verification (exact commands)

```
git switch main
git pull --ff-only origin main
git rev-parse HEAD                                                   # == merge commit SHA
python -m ruff check  src/crypto_core tests/crypto_core scripts/crypto_core
python -m ruff format --check src/crypto_core tests/crypto_core scripts/crypto_core
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/crypto_core/run_full_tests_logged.ps1   # require PYTEST_EXIT=0
git diff --check
git status --short --branch
gh pr list --repo demircaliskan2009-pixel/BIST_ELITE_CORE --state open --json number,title,headRefName,baseRefName,url   # expect []
```
The full-suite log is UTF-16 and may not carry the `N passed` line; the authoritative success signal is
**`PYTEST_EXIT=0`**. Full crypto_core tests run **only** via `run_full_tests_logged.ps1` (never bare full
pytest); targeted runs via `scripts/crypto_core/run_logged_command.ps1`; commands one at a time; scoped
`git add` only.

## 13. Stop Conditions (hard — stop with proof, no mutation)

Wrong repo · non-crypto_core scope · unexpected PR/head (HEAD ≠ expected SHA) · more than one open PR when
creating a PR · dirty overlapping files not owned by the task · requested repair outside allowed files ·
live/private/order/scheduler/connector/runtime/shadow/live leakage · hidden IO/env/random/subprocess not
scoped · failing required validation / full helper · unresolved valid review thread at the merge gate ·
pending CI at the merge gate · direct main push · force push · self-approval · merge without exact human
authorization · external/current fact required (→ `DEEP_RESEARCH_REQUIRED`).

## 14. Warning-Not-Stop Conditions (proceed, but note)

Transient `gh`/API 502/timeout (verify state once, continue) · CI `no checks reported` immediately after
push (startup window — keep polling) · `gh pr checks` non-zero exit while checks pending (not a failure) ·
`mergeStateStatus: BLOCKED` solely from unresolved threads on an otherwise green PR (expected pre-merge) ·
ruff auto-reformat of your own new files / `F401` (format-then-check, continue) · unrelated dirty files not
owned by the task (do not stage/revert; report and scope around) · UTF-16 full-suite log (rely on
`PYTEST_EXIT`).

## 15. Next-Slice Selection Rule

ChatGPT selects exactly one bounded slice that maximizes edge-to-money product value along the chain
`StrategySpec → LBR → PIT/DataRequirement → DecisionLedger → EvidenceStore → BacktestAdmission → Replay →
PaperSleeve → Promotion → Allocator → ExecutionSim`, with: one coherent theme · bounded named files ·
independent-safe · testable · current repo/PR state proven · no hard-gate violation · paper-first (no
live/order/scheduler stage). Prefer the smallest additive change that unlocks the next bridge; one open PR
only. Current integration-first slice sequence (paper-trading DONE definitions + next-PR order +
overengineering guardrails) is the addendum `docs/crypto_core/paper_trading_phase_map.md` (PRDV4 remains
the authority).

## 16. Forbidden Scope

Forbidden unless explicitly authorized and separately designed: live/private API; credentials/secrets/API
keys; real orders; order routing; scheduler; auto-loop; connector/readiness; runtime/orchestrator;
shadow/live execution; fills; PnL; positions; venue/order-id surface; persistence/file/network/env IO added
to product code; backtest/replay engine unless that is the objective; EvidenceStore/persistence unless that
is the objective; **any BIST behavior**. This document and any future prompt must never include account
tokens, credentials, exchange keys, private local machine configuration, or live-trading/real-order
instructions.

## 17. Controlled Self-Improvement Loop

Lessons are persisted, not improvised. Full procedure + the running ledger live in
`docs/crypto_core/agent_lessons.md`. Summary:

- Each real **P1/P2** (Codex finding, CI failure, post-merge defect) emits a `LESSON_CANDIDATE` in the
  ChatGPT handoff block, citing `PR #<n>` + `commit <sha>` + the failure mode / asserting test.
- ChatGPT **triages** durability/generalizability/proof; transient branch/CI/commit state is never a lesson.
- Accepted lessons are added to `agent_lessons.md` **only in a separate setup PR** (`chore/<scope>-prN`),
  never mixed into a feature PR.
- **No lesson may weaken a safety gate (§3, §16).** No automatic self-modification during feature PRs. Stale
  or conflicting instructions are removed or repointed to canonical doctrine.

## 18. Doctrine Precedence & Legacy Surfaces

Active-work doctrine precedence: **`AGENTS.md` → this file → `.codex/skills/crypto-core-max-safe/SKILL.md`
→ `CLAUDE.md`** (+ untracked local `CLAUDE.local.md`), with `docs/crypto_core/agent_lessons.md` as the
lessons companion. On conflict the **stricter safety rule wins**.

Legacy / secondary surfaces — `.github/prompts/*`, `.github/skills/*`, `.github/instructions/*`,
`.github/agents/*`, `.cursor/rules/*`, and any BIST/PRDV3 material — are **historical or assistant-specific
and are overridden by the canonical doctrine above wherever they conflict**. In particular, legacy names that
imply scheduler/deployment/live/order-routing surfaces do **not** authorize any such behavior in crypto_core
(paper-first, no scheduler/auto-loop, no live/order routing — §3, §16). MCP is opt-in/manual and **none** is
enabled by default (`.vscode/mcp.json` declares no servers); any future server must be pinned, read-only/local,
and explicitly approved. Terminal/git/`gh`/pytest/ruff are the source of truth; editor extensions are helpers
(`.vscode/extensions.json` lists recommendations only and installs/uninstalls nothing).

## 19. Deep Research & GitHub Connector Protocol

Deep Research is the **external / current-fact + architecture-benchmark** tool; full protocol in
`docs/crypto_core/deep_research_protocol.md`. Summary (the doc binds on conflict):

- **Use for:** exchange/API/Deribit docs, rate limits, fee/funding/margin/liquidation behavior;
  legal/regulatory/custody/security facts; competitor/benchmark research (Freqtrade, Hummingbot,
  OctoBot, Jesse, institutional patterns — lessons only, no blind copy); academic/microstructure /
  safe-execution / readiness-gate research; PRD/roadmap alignment vs external benchmarks;
  overengineering detection (artifact proliferation vs end-to-end wiring); defining paper-trading DONE
  / shadow DONE / live-readiness gates.
- **Do NOT use for:** local repo state, CI polling, PR merge/readiness source-of-truth, local
  implementation repair, routine unit-test/ruff debugging, branch hygiene, replacing Codex P1/P2
  review, or replacing the GitHub-connector final gate.
- **Combined repo+external review (connector chat):** cite both external sources and repo evidence;
  label every statement as exactly one of `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` / `INFERENCE` /
  `UNKNOWN`; never infer live repo state without GitHub evidence; **Deep Research is strictly read-only
  — it never mutates repo/GitHub state (branch/file/commit/push/PR/comment/thread-resolve/workflow-rerun/
  merge/auto-merge), even when the underlying work is authorized**; connector repo evidence is read-only
  research input only; distinguish official docs/papers from weak sources; output bounded PR-level
  recommendations, not vague strategy.
- **Routing:** ChatGPT decides whether Deep Research is needed; Claude does not call it but may
  **recommend** it (`DEEP_RESEARCH_REQUIRED` + the exact question) when blocked by a current/external
  fact; Codex stays adversarial repo audit; Codex Pursue Goal stays the terminal `gh`/CI loop; the
  GitHub connector stays the source-of-truth state gate; Deep Research is research/advisory, **never an
  executor lane and not merge authority** — any authorized mutation is routed by the controller to
  Claude/`gh`, the GitHub connector, or Codex, never executed by Deep Research.
- **Triggers:** `DEEP_RESEARCH_REQUIRED` for exchange/API/funding/fees/limits/microstructure/
  custody/regulation/security, Deribit/readiness/live/shadow decisions, PRD/roadmap-vs-external-
  benchmark questions, overengineering-vs-underbuilding decisions, top-bot/framework comparison, and
  defining paper/shadow/live DONE gates. `DEEP_RESEARCH_NOT_REQUIRED` for pure local implementation,
  tests/ruff/CI, PR/check/thread status, repo-only state, and already-documented internal doctrine.
- **Output contract:** `RESULT / VERDICT / SOURCE_QUALITY / REPO_EVIDENCE / EXTERNAL_EVIDENCE /
  WHAT_IS_PROVEN / WHAT_IS_INFERRED / WHAT_IS_UNKNOWN / OVERENGINEERING_AUDIT / PRD_ALIGNMENT /
  NEXT_PR_RECOMMENDATIONS / RISKS_TO_AVOID / DEEP_RESEARCH_FOLLOWUP_NEEDED`.
- **Misuse prevention (hard):** Deep Research must never justify skipping tests/CI/audit, authorize
  live/private API/order routing or any §16 forbidden surface, weaken a §3 fail-closed gate, replace
  explicit per-PR merge authorization, or produce broad PRD rewrites unless the controller asks.
  External best practices that conflict with repo safety doctrine are **proposals only** — the stricter
  safety rule wins.

## 20. Multi-Model Routing Doctrine (Fable 5 era)

Fable 5 (`claude-fable-5`) is available as a model tier for the local Claude agent. **Model strength is not
proof**: no lane — however strong — replaces evidence, tests, CI, Codex review, the GitHub-connector final
gate, or explicit per-PR merge authorization. Official Fable 5 limits / quota / safety-routing / pricing are
**UNPROVEN** in this repo — treat availability limits as a user-reported operational constraint and never
state official policy without proof.

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

### 20.4 Current next-slice routing (after PR #314)

- **Next:** `PaperStage4ComparisonEvidence` — route governance/design to **Fable 5 first**. It is the first
  artifact allowed to call `compare_stage4`, and it **must recompute the Sharpe-retention verdict in
  Decimal** from the digest-bound inputs — `compare_stage4` is float-based, so its float retention output is
  advisory echo only, never the verdict source. It consumes the merged #310 Sharpe / #311 methodology /
  #312 edge-identity / #313 baseline-evidence artifacts at their digest boundaries.
- **Then:** `PaperStage4CompletionDecision` — the only artifact that may set `prdv4_stage4_complete=True`.
- **Deferred:** operational-day evidence → operational-30-day gate, until a multi-session per-UTC-day
  operational source exists (otherwise it duplicates the merged return-series 30-day gate or overclaims
  operational readiness).
- No live/shadow/Deribit/Stage-4 completion without separate authorization.

### 20.5 Future Prompt Templates

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

*v4.4 (2026-07-04): added §20 Multi-Model Routing Doctrine (Fable 5 era) — Fable 5 as the premium
high-reasoning lane (with explicit non-use cases), Opus 4.8 as implementation/repair/fallback, Fast
Auto/Sonnet as the mechanical lane, Codex/connector/Deep Research roles restated, the Claude/Codex setup
auto-use doctrine (`AUTO_SETUP_LOADING_PROOF: PARTIAL`), the lane-annotated PR lifecycle with the
GitHub-connector final gate, current next-slice routing (`PaperStage4ComparisonEvidence` → Fable 5 design
first; Decimal Sharpe-retention recompute; `PaperStage4CompletionDecision` after; operational-day gate
deferred), and six future prompt templates. Updated the §2 Claude role row and routing summary to the
Fable 5 era. §20 supersedes the consult-only framing of `LANE:FABLE-ARCH` (the lane file's token-discipline
spirit carries over unchanged). No safety gate weakened; docs only; no product code touched.*
