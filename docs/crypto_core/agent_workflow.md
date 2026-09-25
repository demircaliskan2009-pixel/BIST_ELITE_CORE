# crypto_core Agent Workflow v6.1

> Canonical, executable operating protocol for `crypto_core` inside `demircaliskan2009-pixel/BIST_ELITE_CORE`.
> The single canonical active authority is **section 24** (`CRYPTO_CORE_AGENT_OS_V1`, active content
> `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended, most recently by `CODEX_QUOTA_RESILIENCE_V2`); sections
> 1-19 bind where they agree with it and section 24
> wins on any conflict; sections 20-23 are HISTORICAL. **Doctrine precedence:** `AGENTS.md` (entrypoint and
> durable rails) → section 24 → host adapters (`CLAUDE.md` / `CLAUDE.local.md`,
> `.claude/skills/crypto-core-token-efficient-loop/SKILL.md`, `.codex/skills/crypto-core-max-safe/SKILL.md`)
> → prompting guides → companion procedure docs (`docs/crypto_core/agent_lessons.md`,
> `docs/crypto_core/agent_prompts/token_efficiency_v2.md`), which carry no routing, sizing, budget or merge
> authority.
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

Role summary only. The single `AUTHORITATIVE_ROUTING_MATRIX` — the active model/tool council — is section
24.3; audit tiers are section 24.4; runtime proof and effort are section 24.12. On any conflict, section 24
wins.

| Council member | Responsibility |
|---|---|
| **ChatGPT controller** | Controller and router, architecture adjudication, prompt compiler, evidence judge, live GitHub verification, contradiction detection, merge-readiness judgement, exactly one next action; severity adjudication and protected classification under section 24.4; the DEFAULT independent acceptance auditor of non-protected candidates; the protected preflight and protected audit packet; never protected acceptance. |
| **Claude Opus 5.5** (`claude-opus-5-5`) | Primary deep semantic implementation and repair with its exhaustive self-audit; an optional fresh read-only semantic challenge that is evidence only, never acceptance. |
| **Codex GPT-5.6 Sol** | Reserve only (`SOL_RESERVE_ONLY`, section 24.3): used on a controller-recorded capability or eligibility gap; never a protected audit. |
| **GPT-6 Astra** | SOLE protected acceptance auditor (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`), dispatched only for a candidate with a protected trigger (section 24.4); the last semantic specialist gate; never the default auditor of a non-protected candidate. |
| **ChatGPT Work** | Substantial multi-step execution when a cloud browser/computer, many files, apps or evidence collection materially help; never governance authority. |
| **Deep Research** | Current load-bearing external facts only; advisory. |

Every serious prompt/report carries the runtime-proof block of section 24.12. Model strength is never proof.

### 2a. Independent audit rule

An implementation cannot self-satisfy the independent audit gate in the same context. Implementation and
audit are separate fresh-context, pinned-head tasks (section 24.4), and no model audits its own implementation
or repair. Current valid P1/P2 threads block. Outdated threads do not block code, but any resolution needs
explicit guarded closeout; human threads are never self-resolved.

## 3. Hard Rules

- crypto_core only; **no BIST implementation leakage** (BIST is historical context).
- **One open PR at a time.** Verify live (`gh pr list --state open`) at the start of every task.
- **No direct push to `main`.** No force-push. No branch deletion unless the authorized command says so.
- **Standard merge only** (no squash/rebase). **No merge without explicit human authorization naming the PR and the exact command.**
- **CI `pending` / `queued` / `in_progress` / `no checks reported` is NOT_READY** — keep polling to terminal, or report a bounded-timeout snapshot. Never treat a startup window as green.
- **CI not registered (no run created for a fresh head): diagnose before re-triggering.** Prove it from `gh run list` / commit `check-runs` and classify (`ACTIONS_DELAY_OR_GITHUB_INFRA` vs trigger/path/ref issue). At most **one** empty re-trigger commit (`chore(crypto-core): retrigger …`), and **only** with explicit user/controller authorization. Never loop no-op commits.
- **Branch naming:** feature slices → `feature/<crypto-core-scope>-prN`; setup/docs → `chore/<crypto-core-scope>-prN`; repair stays on the **same branch** for the same PR. (Older `product/*` naming is superseded.)
- **Setup/doctrine changes are never mixed into a feature PR.** Feature PRs touch `src/`/`tests/` product code; setup PRs touch docs/config only (`AGENTS.md`, `docs/crypto_core/**`, `.codex`, `.vscode`, `.cursor`, `.github` docs, `scripts/crypto_core` audit tooling). See §17.
- **The independent audit (section 24.4) is a separate gate**, and automated PR review comments arrive asynchronously — an implementation/repair turn ends at terminal CI + report; it does not block waiting for review.
- Every repo-state claim must be **git/gh/test-verifiable** (never from memory). Unproven → mark `UNKNOWN`.
- **Same-branch repair only** for valid in-scope P1/P2, as the single consolidated repair of the candidate
  lifecycle (section 24.8); stop on unsafe scope expansion.
- No live/private API, real orders, order routing, scheduler, auto-loop, connector/readiness, runtime/orchestrator, or shadow/live unless **explicitly scoped and separately designed**.
- No hidden IO/env/random/wall-clock/threading/subprocess in product code unless explicitly scoped.
- No `gh pr review --approve` (self-approval) ever.
- **Digest-boundary rule (recurring P1 class):** any consumer of a digest-carrying object must recompute the upstream digest via the **public serializer** (remove the self-digest field, canonical JSON `sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False`, SHA-256) and **reject mismatch before READY/ADMITTED/ACCEPTED**. A matching id is never sufficient; a forged/non-serializable upstream must hit the `*_mismatch` path, never a raw `TypeError`. Tests must include a tampered-field case.

### Dependabot collision prevention

- Scheduled Dependabot version-update PRs are disabled for all currently configured ecosystems using
  `open-pull-requests-limit: 0`.
- This does not disable Dependabot alerts or security-update PRs.
- Normal dependency version updates are admitted only through a dedicated controller-selected maintenance
  slice.
- Dependency maintenance requires zero pre-existing open PRs and follows normal topic-branch, validation,
  audit and explicit merge-authorization gates.
- Scheduled version updates must not be temporarily re-enabled while an active crypto_core PR exists.
- An automatically generated security-update PR is treated as an externally generated urgent input requiring
  controller triage.
- A security-update PR does not silently waive one-open-PR and does not authorize concurrent implementation.
- No dependency update is performed by this governance PR.
- No security finding is being dismissed or ignored.

## 4. Standard PR Lifecycle

The lifecycle, prompt budget and fixed-point stop are section 24.8. The sequence:

1. The ChatGPT controller compiles one serious prompt (section 24.6) for one semantic boundary (pinned
   expected `main` HEAD, "open PRs: none").
2. The routed implementer runs the **Implementation Loop** (§5) → opens one PR → natural CI to terminal →
   handoff. No merge.
3. One exhaustive fresh-context acceptance audit returns the complete material P1/P2 set (§8). The lane follows
   the protected classification of section 24.4: the ChatGPT controller for a non-protected candidate; GPT-6
   Astra, after the controller's zero-slot protected preflight and a bounded protected audit packet, for a
   protected or control-plane candidate.
4. When a complete material P1/P2 set is confirmed — by the acceptance audit, or for a protected candidate by the
   controller preflight before any Astra dispatch (section 24.8 `REPAIR_ENTRY_MODE`) — at most ONE consolidated
   repair (§6) on the same branch, then exactly ONE whole-contract re-audit by the acceptance lane. Any genuine
   material P1/P2 left → `FIXED_POINT_STOP`: the candidate is rejected and frozen. P3 never blocks merge.
5. Controller governance closeout, outside the specialist prompt budget (section 24.8): the controller verifies
   live state; the human gives exact-head merge authorization; the **Closeout/Merge Loop** (§7) runs only from
   that authorization.
6. **Post-Merge Verification** (§12), then the next action (§15).

## 5. Implementation Loop

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

Then (all on the **topic branch**): bounded read (named files only, no broad scan) → design → the largest
safe semantic closure inside the allowed files (section 24.8) → self-audit (scope / digest re-proof /
provenance / strict-Decimal / fail-closed / no hidden IO / paper-safety triple) → targeted tests →
relevant suite → **full helper after meaningful changes** → `git diff --check` → scoped `git add <paths>` →
commit (on the topic branch) → push (the topic branch) → `gh pr create --base main --head <topic-branch>` →
**poll CI to terminal** (§ CI rule in §3) → inspect threads that exist (§8) → report (§10). **No merge.**

## 6. Consolidated Repair Loop

- This is the single consolidated repair of the candidate lifecycle (section 24.8): it repairs, by root cause in
  one change, the COMPLETE controller-adjudicated blocker set of its `REPAIR_ENTRY_MODE` — never
  finding-by-finding, never a second repair, never on a rejected or frozen candidate.
- Precheck first (branch + `HEAD == expected SHA` + clean tree + exactly one open PR + changed files ⊆ scope).
- Pin PR number and expected head; repair **only the named blockers**, **same branch only**, bounded to named files.
- **Test-only by default**; touch production only if a **new failing test proves a real defect**, and only inside the named module. If test-only, prove `git diff <prev> HEAD -- src/` is **empty**.
- Re-validate fully (targeted → relevant suite → full helper `PYTEST_EXIT=0` → `git diff --check`) → scoped add → commit → push same branch → **re-poll CI to terminal** → report. **No merge.**

## 7. Closeout / Merge Loop

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

- The acceptance audit (section 24.4: the ChatGPT controller for a non-protected candidate, GPT-6 Astra for a
  protected one) is exhaustive and materiality-aware
  (`COMPLETE_BLOCKER_COLLECTION`, `AUDIT_MATERIALITY_BOUNDARY_V1`): it returns the complete current material P1/P2
  set of the declared contract in one pass, never one finding at a time.
- Automated Codex PR review comments run **asynchronously** after a push and are review threads for controller adjudication, not the routed independent audit; findings may not exist when Claude's turn ends. Claude inspects threads that exist at terminal CI and reports `0 threads (review may post later)` if none.
- Inspect via GraphQL: `reviewThreads(first:n){ nodes{ id isResolved isOutdated path line comments } }` + `reviews`.
- The auditor emits the report in §10. ChatGPT relays the complete valid material finding set (with thread IDs) in the single consolidated repair prompt (section 24.8); Claude does not wait in-turn for review.

## 9. ChatGPT Controller Gate

ChatGPT independently re-verifies live GitHub state (head SHA, files, checks `name=conclusion`, threads,
open-PR rule) before any verdict, and issues exactly one next prompt. Merge authorization must name the PR
and the exact standard-merge command. ChatGPT emits the verdict format in §10.

## 10. Required Report Formats

**Implementer (every task) — fixed fields, all repo claims git/gh/test-verifiable:**
```
RESULT / PR / HEAD_SHA / BRANCH / FILES_CHANGED / COMMITS / VALIDATION / CHECKS /
REVIEW_THREADS / SCOPE_CONFIRMATION / FINAL_GIT_STATUS / BLOCKERS / NEXT_SAFE_ACTION
```
The **last** element of every implementer task message is a single self-contained, copy-paste **ChatGPT handoff
code block** (repo; PR number/state; branch/head SHA/base SHA; files changed; commits; checks; review
threads; validation commands+results; open-PR state; exact `gh`/`git` verification commands). No full logs
(failure tails only); no uncited state.

**Independent auditor (review):**
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
live/order/scheduler stage). Prefer the largest safe semantic closure that unlocks the next bridge (section 24.8);
one open PR only. Current integration-first slice sequence (paper-trading DONE definitions + next-PR order +
overengineering guardrails) is the addendum `docs/crypto_core/paper_trading_phase_map.md` (PRDV4 remains
the authority). After `SETUP_STATUS=CLOSED_FROZEN` the default next action is product work (section 24.14).

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
  never mixed into a feature PR, and after `SETUP_STATUS=CLOSED_FROZEN` only under a legal reopen reason
  (section 24.14).
- **No lesson may weaken a safety gate (§3, §16).** No automatic self-modification during feature PRs. Stale
  or conflicting instructions are removed or repointed to canonical doctrine.

## 18. Doctrine Precedence & Legacy Surfaces

Active-work doctrine precedence: **`AGENTS.md` → section 24 of this file → the host adapters (`CLAUDE.md` +
untracked local `CLAUDE.local.md`, `.claude/skills/crypto-core-token-efficient-loop/SKILL.md`,
`.codex/skills/crypto-core-max-safe/SKILL.md`) → the prompting guides**, with
`docs/crypto_core/agent_lessons.md` as a lessons companion that holds no authority. On conflict section 24
wins, and between safety rules the **stricter safety rule wins**.

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
  implementation repair, routine unit-test/ruff debugging, branch hygiene, replacing the independent P1/P2
  audit, or replacing the GitHub-connector final gate.
- **Combined repo+external review (connector chat):** cite both external sources and repo evidence;
  label every statement as exactly one of `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` / `INFERENCE` /
  `UNKNOWN`; never infer live repo state without GitHub evidence; **Deep Research is strictly read-only
  — it never mutates repo/GitHub state (branch/file/commit/push/PR/comment/thread-resolve/workflow-rerun/
  merge/auto-merge), even when the underlying work is authorized**; connector repo evidence is read-only
  research input only; distinguish official docs/papers from weak sources; output bounded PR-level
  recommendations, not vague strategy.
- **Routing:** ChatGPT decides whether Deep Research is needed; Claude does not call it but may
  **recommend** it (`DEEP_RESEARCH_REQUIRED` + the exact question) when blocked by a current/external
  fact; the section 24.4 acceptance audit stays separate (GPT-6 Astra is the sole protected acceptance
  auditor); the GitHub connector stays the source-of-truth state gate; Deep Research is research/advisory, **never an
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

## 22. HISTORICAL / SUPERSEDED - Token Economy Doctrine (pre-kernel lane budget)

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

## 24. Active Crypto Core Agent OS — MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1

`CRYPTO_CORE_AGENT_OS_V1` is this section's identifier; its active content is
`MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` (2026-09-14), which replaces the earlier v1 lane set, taxonomy,
routing function and prompt policy, as amended by `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` (24.3, 24.4, 24.5,
24.8 and the transition rule of 24.14), by `CLAUDE_OPUS_5_5_CONTROL_PLANE_UPGRADE_V1` (the Claude lane
identity of 24.3, its effort policy in 24.12 and the transition rule of 24.14) and by `CODEX_QUOTA_RESILIENCE_V2`
(audit routing and execution accounting in 24.3, 24.4, 24.5, 24.6, 24.8, 24.10 and 24.12, and its transition rule
in 24.14). It is the single canonical active authority for how crypto_core
development work is routed, sized, audited, repaired, stopped and resumed. Sections 1-19 bind where they agree
with it; on any conflict this section wins, and between safety rules the stricter rule wins. Sections 20-23 are
HISTORICAL/SUPERSEDED. The kernel governs only the operational workflow needed to develop crypto_core safely
and quickly (24.13).

### 24.1 Scope, authority and identity

- `ACTIVE_SCOPE`: crypto_core only — `src/crypto_core`, `tests/crypto_core`, `scripts/crypto_core`, and
  explicitly authorized `docs/crypto_core`. BIST is historical/reference context and is never implemented.
- `CONTROLLER_AUTHORITY`: the ChatGPT controller owns sequencing, routing, architecture adjudication, prompt
  compilation, evidence judgement, accepted state and the next action (24.3, 24.5). No executor, auditor or
  tool report becomes accepted state or authorization on its own.
- `MERGE_AUTHORITY`: the human alone grants a merge, by exact per-PR, exact-head authorization. No model,
  tool, audit verdict or green CI grants, implies or widens it. Standard merge only.
- `DOCTRINE_PRECEDENCE`: `AGENTS.md` (entrypoint and durable rails) → this section → the host adapters
  (`CLAUDE.md`, `.claude/skills/crypto-core-token-efficient-loop/SKILL.md`,
  `.codex/skills/crypto-core-max-safe/SKILL.md`) → the prompting guides (`model_prompting_guide.md`,
  `agent_prompts/opus5_prompting_playbook.md`) → companion procedure docs. Adapters and guides apply this
  section and never restate it as authority. Companion procedure docs (`token_efficiency_playbook.md`,
  `agent_prompts/token_efficiency_v2.md`, `deep_research_protocol.md`, `agent_lessons.md`) carry no routing,
  sizing, budget or merge authority; a lane, budget or rule they name that disagrees with this section is not
  active.
- `MODEL_IDENTITY`: a model's identity is its runtime identity (24.12), never its family name, host, alias or
  settings file. Model strength is never proof.

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

### 24.3 AUTHORITATIVE_ROUTING_MATRIX — the active model/tool council

This table is the single active routing authority for crypto_core. Every other surface references it and none
restates it as authority. The council is closed: a model or tool not listed here receives no routed work.

| Council member | Active role | Never |
|---|---|---|
| **ChatGPT controller** | Controller and router; architecture adjudication; prompt compiler (24.6); evidence judge; severity adjudication under `AUDIT_MATERIALITY_BOUNDARY_V1` and protected classification under `PROTECTED_TRIGGER_MATRIX_V2` (24.4); live GitHub verification through the connector/`gh`; contradiction detection; merge-readiness judgement; exactly one next action; maximum read-only preprocessing (`CONTROLLER_READONLY_FIRST_POLICY`, 24.10); the DEFAULT independent acceptance audit and re-audit of a non-protected candidate (`CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT`, 24.4); the zero-slot `CONTROLLER_PROTECTED_PREFLIGHT` and `PROTECTED_AUDIT_PACKET_V2` of a protected candidate (24.4) | Product implementation; auditing or accepting a candidate it (or ChatGPT Work) implemented or repaired; any protected audit or protected acceptance; a substitute for local tests or unverified repository state; GitHub mutation without an exact human action authorization; merge authority |
| **Claude Opus 5.5** (`claude-opus-5-5`) | Primary deep semantic IMPLEMENTATION and REPAIR, including the single consolidated repair of a candidate (24.8) and the `ROOT_CAUSE_ESCAPE` implementation (24.8), together with the repo-native navigation, mechanical, static-inspection, test-generation, local validation, CI-diagnosis and exhaustive self-audit work that belongs to that same task; the optional fresh READ_ONLY `OPUS55_READONLY_CHALLENGE` (24.4), which is evidence only | Accepting any candidate; any independent, acceptance or protected audit; controller, governance or merge authority |
| **Codex GPT-5.6 Sol** | `SOL_RESERVE_ONLY`: used only when the ChatGPT controller records a specific capability or eligibility gap that neither the controller nor the routed Claude Opus 5.5 task can legally or safely cover — for example the non-protected acceptance audit when `NO_SELF_AUDIT` makes the controller ineligible (24.4) | The default auditor, navigator, status checker, reviewer or implementation accelerator; dispatch merely for model diversity; any protected audit or protected acceptance; auditing a candidate it implemented or repaired |
| **GPT-6 Astra** | SOLE protected acceptance auditor (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`, 24.4): the READ_ONLY protected whole-contract audit and the one protected re-audit of a candidate with at least one trigger of `PROTECTED_TRIGGER_MATRIX_V2`, on a `PROTECTED_AUDIT_PACKET_V2`; in the same execution the protected T4 `CLASS_C_CROSS_CONTRACT` audit and terminal decision; the last semantic specialist gate. Model id `gpt-6-astra`, effort `Ultra` (24.12) | The default auditor of a non-protected candidate; repository discovery labor the controller can do; mutation; implementation or repair; auditing a candidate it implemented or repaired; any reassignment of protected acceptance to another lane |
| **ChatGPT Work** | Substantial multi-step execution when a cloud browser/computer, many files, apps or evidence collection materially help, under the same prompt shape (24.6) and gates | Governance authority; accepted state; merge authority |
| **Deep Research** | Current load-bearing external facts only (24.9) | Repository/PR/CI state; implementation; mutation; gate waivers |

`ASTRA_T4_EXCLUSIVE` — protected T4 and protected acceptance belong to GPT-6 Astra alone. When Astra is
unavailable, quota-blocked or stopped by runtime proof, the protected gate waits
(`CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE`, `ASTRA_QUOTA_BLOCK_FREEZE` in 24.4); nothing reassigns it to Codex GPT-5.6
Sol, Claude Opus 5.5, the ChatGPT controller, ChatGPT Work or any other lane. Non-protected acceptance never
depends on Astra.

`HOST_UI_LABELS_ARE_LITERAL` — a host's effort or mode label is recorded verbatim and never mapped across model
families, to an API effort enum, or to `max`. Current literal labels: Claude Opus 5.5 `xhigh` and `max`; Codex
GPT-5.6 Sol `Ultra`; GPT-6 Astra `Light`, `Medium`, `High`, `Extra High`, `Ultra`. The retired Opus 5 literal
`xhighultracode` belongs to that superseded lane and is never carried onto Claude Opus 5.5.

Outside the council — none is routable, a fallback or a dependency: **Copilot `INACTIVE_UNAVAILABLE`** (24.13);
**Claude Fable 5 `INACTIVE_EXPIRED_RETIRED`**; **Claude Opus 5 `SUPERSEDED_BY_OPUS_5_5`**; **Claude Opus 4.8
`SUPERSEDED_BY_OPUS_5`**; **Claude Sonnet 5, Codex GPT-5.6 Terra and Codex GPT-5.6 Luna
`NOT_IN_ACTIVE_COUNCIL`**. A superseded Claude lane is never an automatic fallback: `MODEL_FALLBACK=PROHIBITED`
holds for every serious routed crypto_core task (24.12). Their former roles moved: status, polling
and mechanics to the ChatGPT controller's live verification or the routed session's own terminal proof;
bounded, clear-spec and deep semantic implementation to Claude Opus 5.5; non-protected independent review to the
ChatGPT controller and protected review to GPT-6 Astra (24.4). Earlier definitions survive only in the HISTORICAL sections and the dated changelog. Activating
any of them is a `MATERIAL_CAPABILITY_CHANGE` (24.13).

### 24.4 Audit routing (CODEX_QUOTA_RESILIENCE_V2), protected Class C and complete blocker collection

Every candidate receives exactly one ACCEPTANCE LANE, fixed by its protected classification and nothing else —
not by size, difficulty or seriousness. Every acceptance audit and whole-contract re-audit, whatever its lane, is:
fresh context; pinned to the exact head; READ_ONLY with zero repository or GitHub mutation; performed by a lane
that neither implemented nor repaired any part of this candidate lifecycle; exhaustive over the declared semantic
boundary (`COMPLETE_BLOCKER_COLLECTION`); materiality-aware (`AUDIT_MATERIALITY_BOUNDARY_V1`); evidence-backed; and,
for a specialist model lane, runtime-proven (24.12) before any substantive work.

- `PROTECTED_TRIGGER_MATRIX_V2` — a candidate is PROTECTED when, and only when, it changes, grants or relies on at
  least one of these authorities:
  - A. control-plane, governance, audit, acceptance, merge or human-authorization authority (including this
    section and the adapters and guides that apply it);
  - B. cryptographic digest, signature, provenance, custody, attestation, anti-replay or trust-root authority;
  - C. Machine-Time or trusted-time qualification, or native-worker admission;
  - D. a connector, readiness or external-trust transition that grants operational authority;
  - E. live/private API, credential, order-routing, scheduler/auto-loop, shadow/live, capital or security
    authority;
  - F. a cross-contract transition that itself grants or changes READY / ADMITTED / ACCEPTED, Stage advancement
    or paper-to-live authority;
  - G. a risk or capital threshold whose output may authorize capital-bearing behavior.

  Nothing outside A-G makes a candidate protected. Historical analytics, deterministic validators, tests,
  refactors, non-authorizing paper-only metrics and ordinary bug fixes are NON-PROTECTED unless an A-G authority
  actually applies. The ChatGPT controller records the trigger letters, or `NONE`, before any audit dispatch, and
  classifies UPWARD to protected whenever ambiguity remains.
- `CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT` — the acceptance lane of a NON-PROTECTED candidate is the ChatGPT
  controller, provided neither it nor ChatGPT Work implemented or repaired the candidate. The audit covers fresh
  exact-head proof, every changed file, the load-bearing dependencies, CI and review threads, supported-path
  adversarial reasoning, P1/P2/P3 materiality, scope and non-claims, determinism and fail-closed behavior, and the
  complete material blocker set. Implementation tests and CI inform it and never constitute acceptance by
  themselves. GPT-6 Astra is never dispatched for a non-protected candidate, and Codex GPT-5.6 Sol is never added
  for model diversity. When `NO_SELF_AUDIT` makes the controller ineligible, the audit goes to Codex GPT-5.6 Sol
  as a recorded eligibility gap (`SOL_RESERVE_ONLY`, 24.3), if Sol is itself eligible and runtime-proven; with no
  independent eligible reviewer → `STOP_WITH_PROOF`.
- `ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1` — the acceptance lane of a PROTECTED candidate is GPT-6 Astra alone
  (`gpt-6-astra`, `Ultra`, `MODEL_FALLBACK=PROHIBITED`, thinking `ENABLED`, 24.12). One Astra execution is at once
  the protected acceptance audit, complete blocker collection over the protected cross-contract boundary, the
  protected Class-C cross-contract audit and the terminal decision; the one Astra re-audit does the same for a
  repaired head. Astra is the last semantic specialist gate: it receives only a stabilized head with a
  `PROTECTED_AUDIT_PACKET_V2`, independently verifies every load-bearing fact its protected verdict rests on, is
  never used as repository-discovery labor the controller can do, and reports any material P1/P2 it finds. Codex
  GPT-5.6 Sol, Claude Opus 5.5, the ChatGPT controller, ChatGPT Work, any self-review and any challenge never
  satisfy protected acceptance.
- `CONTROLLER_PROTECTED_PREFLIGHT` — before every Astra dispatch the controller performs, read-only and at zero
  specialist slots (24.8), all safely controller-owned work: SHA, tree and state proof; diff and patch
  inspection; CI and check proof; review-thread adjudication; changed-file enumeration; load-bearing dependency
  mapping; scope and non-claim review; materiality triage; and deterministic and fail-closed consistency review.
  It delivers no acceptance verdict. When it — optionally informed by an Opus challenge — confirms a COMPLETE
  material P1/P2 set, Astra is not dispatched on that head and the set opens the candidate's one repair
  (`PROTECTED_CONTROLLER_PREFLIGHT_CONFIRMED_BLOCKER_SET`, 24.8). Rejecting a known-defective candidate is
  controller authority; accepting a protected one never is.
- `OPUS55_READONLY_CHALLENGE` — an OPTIONAL fresh-context READ_ONLY Claude Opus 5.5 execution for deep semantic
  bug finding, adversarial cases, accounting and numeric review, dependency tracing, test-gap review and
  protected-boundary preflight. The default is NOT to run one: the controller routes one only when its expected
  defect-finding value exceeds the cost of one of the five execution slots, and only when the budget admits it
  (`HARD_FIVE_EXECUTION_BUDGET`, 24.8). It returns every material P1/P2 it finds with evidence, for the controller
  to adjudicate; it is evidence only — it never accepts, never mutates, and never opens a repair by itself. Run on
  Opus 5.5 work it is also `SELF_AUDIT_OR_SAME_MODEL_CHALLENGE_NOT_INDEPENDENT`.
- `PROTECTED_AUDIT_PACKET_V2` — every Astra dispatch carries one controller-compiled packet with exactly:
  `BASE_SHA`, `HEAD_SHA`, `HEAD_TREE`, `CHANGED_FILES`, `PROTECTED_TRIGGER_LETTERS`, `CRITICAL_PROTECTED_CLAIMS`,
  `LOAD_BEARING_PROTECTED_DEPENDENCIES`, `CONTROLLER_PREFLIGHT_RESULT`, `OPUS_CHALLENGE_RESULT_IF_ANY`, `CI_STATE`,
  `REVIEW_THREADS`, `UNRESOLVED_MATERIAL_P1_P2` and `EXACT_PROTECTED_ACCEPTANCE_QUESTIONS`. Stable doctrine is
  referenced in the repository by path, never recovered from chat history. The packet pins evidence and never
  substitutes a summary for a fact Astra must verify itself; a missing fact stays `UNKNOWN`. Astra does not redo
  unrelated discovery merely to duplicate the packet, but its protected verdict rests only on what it verified.
- `ASTRA_QUOTA_BLOCK_FREEZE` — when a stabilized protected candidate needs GPT-6 Astra and Astra is quota-blocked,
  unavailable or stopped by runtime proof: the exact head is frozen and not mutated; the protected gate WAITS
  (`CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE`); no protected merge happens; only permitted highest-value read-only
  work continues; and no other model substitutes for protected acceptance. The block is recorded in the task
  handoff, never as durable model state.
- `NO_SELF_AUDIT` — independence eligibility is decided BEFORE operational availability, for the audit and the
  re-audit alike: a lane that implemented or repaired any part of this candidate lifecycle is ineligible, and
  implementation or repair by ChatGPT Work counts as the ChatGPT controller's own. GPT-6 Astra is READ_ONLY and
  never implements or repairs; were it ever to, it would be ineligible for that candidate. No model audits its own
  implementation or repair; a Claude implementer's self-review, like any same-model review of its own work, is
  `SELF_AUDIT_ONLY_NOT_INDEPENDENT` and satisfies no audit.
- `RUNTIME_PROOF_BEFORE_AUDIT` — an auditor or challenger proves identity and required thinking (24.12) before any
  substantive work. A failed proof stops before it, delivers no verdict or finding and consumes no execution slot
  (24.8); a substantive execution is never followed by a retroactive no-credit label.
- `COMPLETE_BLOCKER_COLLECTION` — an audit never stops at the first defect. It returns the COMPLETE current
  material P1/P2 set of the declared semantic contract in one exhaustive pass, to the practical limit of that
  bounded contract, each finding with exact evidence. One-finding-at-a-time auditing, and the loop finding →
  repair → finding → repair, are forbidden: one exhaustive audit, one consolidated root-cause repair, one
  whole-contract re-audit (24.8).
- `AUDIT_MATERIALITY_BOUNDARY_V1` — a finding blocks merge as P1/P2 only when the auditor demonstrates MATERIAL
  relevance inside the CURRENT declared contract.
  - P1: a concrete correctness, safety or trust failure on a supported path that can accept invalid evidence or
    state, advance an invalid gate, authorize an invalid trust transition, violate provenance, authority or
    governance integrity, violate a hard safety rail, or materially break a capital, readiness or security
    boundary in scope.
  - P2: a concrete material correctness, determinism or fail-closed defect inside the declared supported semantic
    contract that blocks acceptance but does not rise to P1.
  - Every P1/P2 names the exact invariant, the exact source evidence, the supported or public entry or consumer
    path, the resulting semantic or trust effect, why it is material, and the minimum regression proof.
  - A theoretically stronger implementation is not automatically required. A finding is P3 /
    `OUT_OF_SCOPE_HARDENING` by default when its only reproduction needs `object.__new__` or bypassed
    initialization, direct mutation or corruption of frozen internals, direct misuse of a private helper no
    supported consumer reaches, monkeypatching or interpreter corruption, an object state no supported builder,
    parser or consumer can produce, hypothetical future API behavior, a naming/style/refactor preference, generic
    extra defensive hardening, or "another negative test would be nice" without a demonstrated material defect.
  - Such a finding is promoted to P1/P2 only when evidence proves that a supported entry path reaches it, that a
    current consumer accepts such input, that an explicit public verifier contract promises that behavior for
    arbitrary objects and the promise is load-bearing, or that a hard safety or trust rail is actually violated.
  - Materiality never downgrades a defect that a supported entry path or current consumer can reach, and
    throughput is never a reason to reclassify a real correctness or safety defect. The auditor never enlarges the
    semantic contract to manufacture a blocker (24.13).
- `FINITE_AUDIT_RULE` — the audit question is "is the DECLARED supported semantic contract correct and safe?",
  never "can any imaginable object or theoretical universe produce another hardening opportunity?". The audit
  ends when the bounded contract has been exhaustively covered, its material authority and trust transitions have
  been checked, and the complete current material P1/P2 set is collected; remaining observations are P3 /
  `OUT_OF_SCOPE`, and further P3 observations never keep an audit open.
- Severity and threads: P3 is advisory, never blocks merge and never triggers `FIXED_POINT_STOP`. Current valid
  material P1/P2 review threads block; the ChatGPT controller adjudicates a disputed severity against the declared
  contract and this boundary with evidence (24.8). A same-model self-review is `SELF_AUDIT_ONLY_NOT_INDEPENDENT`
  and satisfies no audit.

### 24.5 Controller-mediated chain and CONTROLLER_ACCEPTED_STATE

Controller-mediated and sequential: no autonomous scheduler, no auto-loop, no direct model-to-model runtime
messaging, one repository writer at a time, one open PR, no concurrent patching; every stage ends with exactly
one next safe action. Reports are claims until the controller verifies them, and only verified evidence enters
`CONTROLLER_ACCEPTED_STATE`. Never vote or average model answers: resolve a disputed claim with controlling
evidence (`LIVE_STATE_PRECEDENCE`, 24.7); an unresolved load-bearing dispute stays `UNKNOWN` and blocks merge.

A merge requires, each freshly proven on the exact head: the acceptance audit clean under 24.4 — for a protected
candidate the GPT-6 Astra audit, and for a non-protected candidate `CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT` or
its recorded `SOL_RESERVE_ONLY` substitute — after the one whole-contract re-audit when a repair ran; no current valid
material P1/P2; exact-head CI terminal green, including the required tests and CodeQL; controller live-state
proof; and the human's explicit authorization naming the PR, the exact head and the merge command. Then standard merge, post-merge verification (section 12) and the next action. These closeout
steps are controller governance and consume no specialist prompt (24.8).

### 24.6 SERIOUS_PROMPT_COMPILER and AGENT_OS_HANDOFF_V1

`SERIOUS_PROMPT_COMPILER` — the controller compiles every serious prompt in this shape and order:

```text
TASK_INTENT / SEMANTIC_BOUNDARY / STATE_PIN / MODEL_RUNTIME_PROOF / ALLOWED_FILES / INVARIANTS /
BLOCKER_INVENTORY / VALIDATION_MATRIX / GITHUB_AUTHORIZATION / FORBIDDEN / STOP_CONDITIONS / HANDOFF
```

`TASK_INTENT` is one explicit intent (for example `IMPLEMENTATION`, `REPAIR`, `AUDIT`, `REAUDIT`,
`ARCHITECTURE`, `CLOSEOUT`) fixed before anything else; `SEMANTIC_BOUNDARY` names the one
contract the PR closes (24.8); `BLOCKER_INVENTORY` carries the inherited blocker identities (24.8). Shortening
a prompt never drops a stop condition, invariant, permission boundary or validation gate. Status reads and
polling need no serious prompt.

`AGENT_OS_HANDOFF_V1` — every serious task ends with one handoff: result; the runtime-proof block (24.12);
setup fields (24.7); state proof (base, branch, head, PR, open PRs); files changed; validation and CI with exact
results; review threads; P1/P2/P3 findings or the self-audit label; for an audit or challenge, its lane, the
protected classification (trigger letters or `NONE`, 24.4) and, for a Sol execution, the recorded gap; for a
repair, its `REPAIR_ENTRY_MODE` (24.8); the actual meaningful-execution count and challenge count of the PR
lifecycle (24.8); and exactly one next safe action. Missing facts are `UNKNOWN`, never invented; failure tails
only; a handoff never authorizes mutation.

### 24.7 SETUP_LOAD_CONTRACT_V1, FRESH_CHAT_BOOTSTRAP and LIVE_STATE_PRECEDENCE

`FRESH_CHAT_BOOTSTRAP` — a new chat or session without an accepted packet reads, in order:

1. `AGENTS.md`;
2. this section (`docs/crypto_core/agent_workflow.md` section 24);
3. the relevant host adapter — `CLAUDE.md` and `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` for
   Claude, `.codex/skills/crypto-core-max-safe/SKILL.md` for Codex;
4. `docs/crypto_core/continuity/CONTINUITY_INDEX.md`;
5. the latest accepted bounded handoff or continuity pointer, if one exists;
6. fresh local repository proof and live GitHub proof.

`SETUP_LOAD_CONTRACT_V1` — every serious report states `SETUP_REQUESTED`, `SETUP_ACTUAL`, `SETUP_FILES_READ`
and `SETUP_GAPS`; setup loading is never claimed without proof. A controller-supplied prompt replaces broad
rediscovery, never the executor's own local proof. No transcript replay unless the repository plus continuity
genuinely cannot reconstruct material operational state.

`LIVE_STATE_PRECEDENCE` — for facts about current operational state, highest first: fresh local/terminal
evidence → live GitHub/CI → the accepted bounded state/handoff → exact repository source → canonical doctrine →
continuity → archives → memory. Fresh evidence overrides a stale handoff. This order ranks evidence about state
only: no handoff, state record, archive or memory ever relaxes a rule of this doctrine.

### 24.8 LOW_PROMPT_MAXIMUM_WORK_POLICY — PR sizing, prompt budget and the fixed-point lifecycle

`PR_SIZING_AUTHORITY=SEMANTIC_CLOSURE_ONLY`; default `LARGEST_SAFE_SEMANTIC_CLOSURE`. One PR closes one
coherent semantic contract together with its dependency closure, negative cases, tests, the docs/provenance
genuinely required, and its validation. There is no file-count, LOC or module-count ceiling and no preference
for small PRs. Split only for: unrelated contracts; different authorization; a protected boundary that cannot
be audited together; inability to validate the whole result; or a real context/correctness risk.

`MEANINGFUL_PROMPT` — a SPECIALIST execution that does substantive work of one of five kinds: implementation,
acceptance audit, consolidated repair, whole-contract re-audit, or `OPUS55_READONLY_CHALLENGE` (24.4). A PR lifecycle
has exactly ONE specialist execution budget and every meaningful prompt draws on it: no kind, lane or quota concern
has a separate pool. An execution that stops on runtime proof (24.12) before any substantive work consumed
nothing; one that did substantive work consumed its place whatever its verdict. No relabelling, splitting or
re-routing resets the count.

`CONTROLLER_GOVERNANCE_OPERATIONS` consume nothing: live repository/GitHub state proof; CI, status and check reads;
adjudication of executor and auditor evidence; contradiction synthesis; the protected classification,
`CONTROLLER_PROTECTED_PREFLIGHT` and compilation of `PROTECTED_AUDIT_PACKET_V2` (24.4); merge-readiness judgement;
asking the human for exact-head merge authorization; an authorized mechanical merge; post-merge verification; and
fresh-chat acceptance. None of them delivers an acceptance verdict, and none contains or dispatches an
implementation, repair, audit or challenge; specialist work relabelled as governance is still specialist work
that counts. `CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT` and a `SOL_RESERVE_ONLY` substitute audit deliver an
acceptance verdict and are meaningful prompts.

`HARD_FIVE_EXECUTION_BUDGET` — at most **5** meaningful prompts per PR lifecycle and no sixth, by any route. The
target is the FEWEST the lifecycle needs; no meaningless execution is created to reach a count, and no execution is
created merely to use available model quota. The budget is a count, not a set of positions: no place in it is
reserved for any kind of execution. It is spent by two rules:

- `STILL_REQUIRED` — the executions the lifecycle may still need, by state: after implementation, before any
  acceptance audit or repair — **3** (acceptance audit, repair, re-audit); once a confirmed blocker set has opened
  the repair — **2** (repair, re-audit); after the repair — **1** (the re-audit); after a clean acceptance audit or
  after the re-audit — **0**.
- `BUDGET_ADMISSION_RULE` — an OPTIONAL execution (an `OPUS55_READONLY_CHALLENGE`) is dispatched only when
  `USED + 1 + STILL_REQUIRED <= 5`, where `USED` counts the meaningful prompts already run; otherwise it is skipped.
  Required executions — implementation, acceptance audit, repair, re-audit — need no admission and run while
  `USED < 5`. An admitted optional execution therefore can never displace a required one.

Challenge positions: at most one before the first acceptance audit or Astra dispatch, and at most one after the
repair, before the re-audit (on the preflight-entry path, before the one Astra audit) — at most two per lifecycle,
each under the admission rule, and zero by default. A challenge that takes the fifth place leaves no room for a
`PROCEDURAL_REPLACEMENT`; the controller weighs that before admitting it.

`PROCEDURAL_REPLACEMENT` — when the ChatGPT controller rejects an executed audit or re-audit as procedurally invalid
(wrong head, not fresh context, repository or GitHub mutation, or incomplete blocker collection), with the reason
recorded and never because of its findings or verdict, one replacement of that execution may run — at most one per
lifecycle — and it is a meaningful prompt like any other. When the next required execution would be the sixth, the
lifecycle stops at the ceiling with proof (`STOP_WITH_PROOF`) and closes without merge; there is no execution 6. A
replacement never authorizes a second repair or a second valid re-audit of the same repaired head.

Canonical paths, derived from these rules. The count is the number of meaningful prompts actually run; bracketed
steps are zero-count governance.

| Path | Actual execution order | Count |
|---|---|---|
| Non-protected, clean | implementation → controller acceptance audit | 2 |
| Non-protected, clean, one challenge | implementation → challenge → controller acceptance audit | 3 |
| Non-protected, repaired | implementation → controller acceptance audit → repair → controller re-audit | 4 |
| Non-protected, repaired, one challenge | implementation → challenge → controller acceptance audit → repair → controller re-audit, or implementation → controller acceptance audit → repair → challenge → controller re-audit | 5 |
| Protected, clean | implementation → [preflight, packet] → Astra audit | 2 |
| Protected, clean, one challenge | implementation → challenge → [preflight, packet] → Astra audit | 3 |
| Protected, repair opened by the Astra audit | implementation → [preflight, packet] → Astra audit → repair → [preflight, packet] → Astra re-audit | 4, or 5 with one admitted challenge |
| Protected, repair opened by the preflight | implementation → [preflight confirms the complete set] → repair → [preflight, packet] → Astra audit, which is the whole-contract re-audit and terminal decision | 3, or 4-5 with one or two admitted challenges |

After the final meaningful prompt, controller governance closeout (24.5) completes the lifecycle at zero count.

- Waiting consumes nothing: CI still pending after the final audit, a delayed human authorization, post-merge
  verification and fresh-chat acceptance are governance. `VERDICTS_BIND_EXACT_HEAD` — every audit verdict and CI
  result binds the exact head it judged. After the implementation, only the one consolidated repair may move the
  head, and the section-3 authorized empty re-trigger commit keeps the verdicts only when its tree is identical; any
  other head movement voids the verdicts bound to the old head and stops the candidate (`REJECT/FREEZE`).

`REPAIR_ENTRY_MODE` — the one repair opens through exactly one of two modes, and through no other:

1. `ACCEPTANCE_AUDIT_CONFIRMED_BLOCKER_SET` — the complete material P1/P2 set returned by the candidate's acceptance
   audit (24.4);
2. `PROTECTED_CONTROLLER_PREFLIGHT_CONFIRMED_BLOCKER_SET` — for a PROTECTED candidate only and only BEFORE its Astra
   dispatch, the complete material P1/P2 set the controller confirms in `CONTROLLER_PROTECTED_PREFLIGHT`,
   optionally informed by an Opus challenge.

Both modes require complete blocker collection, controller materiality adjudication, exact blocker identities,
one root-cause consolidated repair and no second repair. A challenge or automated-review finding reaches a repair
only through the controller's adjudication inside one of these modes. Every repair prompt carries
`REPAIR_ENTRY_MODE`, `BLOCKER_INVENTORY`, `ACTUAL_MEANINGFUL_EXECUTION_COUNT` (including the repair itself) and
`CHALLENGE_COUNT`; no template fixes a count.

`ONE_CONSOLIDATED_REPAIR` — at most one repair per candidate lifecycle, opened only through `REPAIR_ENTRY_MODE`. It
repairs that complete set by root cause in one change. No micro-patching, no finding-by-finding repair, no repair
→ audit → repair chains.

`ONE_WHOLE_CONTRACT_REAUDIT` — after that repair, exactly one fresh re-audit of the repaired exact head to the
same 24.4 standard by the acceptance lane: the controller for a non-protected candidate; GPT-6 Astra for a
protected one, after the controller preflight runs again. When the preflight opened the repair, the one Astra audit
of the repaired head IS this re-audit. It is READ_ONLY and covers the whole semantic contract, never only the
repaired lines.

`FIXED_POINT_STOP` — the first complete material P1/P2 set confirmed through `REPAIR_ENTRY_MODE` opens the one
consolidated repair. After that repair and its one whole-contract re-audit: material P1/P2 = NONE → the candidate
proceeds to controller governance closeout (24.5); any genuine material P1/P2 remaining → the candidate is
`REJECT/FREEZE`, receives no further mutation, and closes without merge — never a second repair. When the preflight
of a repaired protected head confirms that a genuine material P1/P2 remains, the controller rejects and freezes the
candidate without dispatching Astra: rejecting a known-defective candidate is controller authority and is not
protected acceptance. P3 / `OUT_OF_SCOPE` / theoretical-hardening observations NEVER trigger
`FIXED_POINT_STOP` and never block merge. Before freezing a candidate on a disputed finding, the ChatGPT controller
adjudicates its severity against the declared semantic boundary and `AUDIT_MATERIALITY_BOUNDARY_V1` with evidence;
a candidate is never frozen merely because an auditor can imagine additional robustness, and adjudication never
downgrades a supported-path correctness or safety defect for throughput. The decision is ACCEPT or REJECT, never
another loop.

`ROOT_CAUSE_ESCAPE` — `REJECT/FREEZE` stops patching the failed candidate; it does not abandon the underlying
product or setup problem. A future attempt requires an explicit new ChatGPT controller `TASK_INTENT=ARCHITECTURE`
decision that: reconstructs the root cause; inherits every blocker identity; changes the architecture or
boundary rather than renaming the same repair; defines a new bounded semantic closure; starts from accepted
main; and prohibits rejected candidate history (commits, branches, text) from silently becoming canonical.
There is no automatic replacement PR chain: a new branch or PR number never authorizes a replacement cycle. A
bounded clean replacement exists only under such a decision.

`BLOCKER_IDENTITY_SURVIVES_RENAME` — a blocker is its semantic defect. The same defect stays the same blocker
across new wording, new function names, new branches, new PRs, new phase labels and a "clean replacement"
label. Renaming never restores a repair allowance and never resets the prompt budget.

### 24.9 Deep Research

Deep Research answers current load-bearing external facts only: exchange/Deribit APIs, fees, rate limits,
funding, margin, liquidation, microstructure, custody/security/regulation, current framework or model/tool
behavior, and readiness/shadow/live standards. It is read-only and advisory — primary sources first, cited and
dated, with REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN kept separate — and it is never repository,
PR or CI state, implementation, GitHub mutation, merge authority or a gate waiver. The controller decides when
it is required and verifies its output before any use. Full protocol: `docs/crypto_core/deep_research_protocol.md`,
subordinate to this section.

### 24.10 CONTROLLER_READONLY_FIRST_POLICY

The ChatGPT controller works read-only first: whenever its connector and read-only capabilities can establish a
fact, inspect source, verify GitHub or CI state, or perform read-only adjudication, it does so BEFORE any specialist
execution is spent. It proves live state, verifies every executor and auditor claim against evidence, detects
contradictions and stale state, classifies protection (24.4), compiles the next serious prompt, performs the
non-protected acceptance audit and the protected preflight (24.4), and judges merge readiness. It never replaces
local tests, never treats memory as repository state, never implements product code, never audits or accepts a
candidate it or ChatGPT Work implemented or repaired, never audits or accepts a protected candidate, never mutates
GitHub without an exact human action authorization, and never grants merge, readiness, live or capital authority.

`USER_MANUAL_WORK_MINIMIZATION` — the human is never asked to run a terminal command or fetch a fact that the
controller or the routed agent can obtain itself. Human manual work is reserved for explicit per-PR merge
authorization, the protected approvals this doctrine reserves to the human, production/live/capital/security
authority, and facts or actions genuinely inaccessible to the tools and agents.

`QUOTA_ROUTING_IS_ADAPTIVE` / `QUALITY_BAR_IS_CONSTANT` — work goes to the lane that can safely own it, so abundant
controller and Claude Opus 5.5 capacity carries all work those lanes may legally do and GPT-6 Astra is reserved
for protected authority. Account or session quota readings are transient controller state: no percentage, limit
or availability assumption is ever written into durable doctrine, no quota telemetry, registry or scheduler exists,
and no work is manufactured to consume quota. The objective is maximum safe product progress; quota never changes
a gate, a standard or a verdict.
Claude Fable 5 stays `INACTIVE_EXPIRED_RETIRED`: no active surface routes to it.

### 24.11 LIVE_STATE_POLICY and non-regression

`LIVE_STATE_POLICY` — durable doctrine pins no current `main` SHA, merged-PR number, open-PR count, blocker
position, capacity reading or setup-status value. Live state is re-proven from `git`/`gh` at the start of every
task (24.7) and lives in controller handoffs; dated history appears only in HISTORICAL sections and the
changelog. Every section-3 hard rule and section-16 forbidden scope binds unchanged: one open PR, no direct main
push, no force-push, standard merge only, explicit per-PR human merge authorization, pending CI = `NOT_READY`,
current valid material P1/P2 threads block, post-merge verification before next work, the digest-boundary rule, and no
BIST/live/private-API/order/scheduler/readiness/shadow/capital surface without separate authorization.

### 24.12 RUNTIME_PROOF and effort

Every serious routed execution — implementation, repair, audit, re-audit (including the protected GPT-6 Astra
audit of 24.4) and challenge — reports, before mutation, audit or challenge:

```text
MODEL_REQUESTED / MODEL_ID_REQUIRED / MODEL_ACTUAL / MODEL_EFFORT_REQUESTED / MODEL_EFFORT_ACTUAL /
MODEL_FALLBACK / THINKING_ACTUAL / MODEL_IDENTITY_EVIDENCE / MODEL_EFFORT_EVIDENCE
```

`FAIL_CLOSED_RUNTIME_PROOF` — model identity and required thinking are load-bearing: they are proven positively,
or the execution stops before any mutation or audit. Effort telemetry is not load-bearing.

| Runtime fact | Verdict |
|---|---|
| `MODEL_ACTUAL` equals `MODEL_ID_REQUIRED` on execution evidence; thinking required and positively `ENABLED`; effort known | PASS |
| As above, with `MODEL_EFFORT_ACTUAL` = `UNKNOWN` because the host exposes no execution-effort telemetry | PASS |
| `MODEL_ACTUAL` = `UNKNOWN` | `STOP_WITH_PROOF` |
| `MODEL_ACTUAL` differs from `MODEL_ID_REQUIRED` | `STOP_WITH_PROOF` |
| Identity shown only by a selector, configuration, default, cache, alias or request text | `STOP_WITH_PROOF` |
| Thinking required and `THINKING_ACTUAL` = `UNKNOWN` | `STOP_WITH_PROOF` |
| Thinking required and `THINKING_ACTUAL` = `DISABLED` | `STOP_WITH_PROOF` |
| A known prohibited fallback | `STOP_WITH_PROOF` |

- Execution evidence is produced by the running session itself: runtime metadata naming the exact model,
  `/model`, `/status` or an equivalent diagnostic. A selector, configuration file, default, cache, alias or
  request text states intent, never the executing model, thinking mode or effort.
- Implementation, repair, audit and challenge executions require thinking (`THINKING_REQUIRED=ENABLED`, stated in
  the serious prompt's `MODEL_RUNTIME_PROOF`).
- A protected GPT-6 Astra audit or re-audit requests `MODEL_REQUESTED=GPT-6 Astra`, `MODEL_ID_REQUIRED=gpt-6-astra`,
  `MODEL_EFFORT_REQUESTED=Ultra`, `MODEL_FALLBACK=PROHIBITED` and `THINKING_REQUIRED=ENABLED`, proven on
  current-session execution evidence. No substitute model satisfies protected acceptance; a failed proof leaves the
  protected gate waiting (`ASTRA_QUOTA_BLOCK_FREEZE`, 24.4).
- When the exact required `MODEL_ACTUAL` is independently proven on execution evidence, the absence of a separate
  fallback telemetry field is not a second proof requirement; a known prohibited fallback still stops.
- `MODEL_EFFORT_ACTUAL` may be `UNKNOWN` when exact execution-effort telemetry is unavailable. That is
  non-blocking once identity and required thinking are proven, and the actual is never restated from the request.
  Effort and `HOST_SETTING_RAW` are recorded literally under `HOST_UI_LABELS_ARE_LITERAL` (24.3) and never mapped
  to an API effort enum. A human may waive an effort mismatch for one task; the waiver and the true actual effort
  are recorded. Identity and required thinking have no waiver: a different model is a different routed task.
- Effort is chosen from the work itself; de-escalate as soon as the remaining work is simpler.
- `CLAUDE_EFFORT_POLICY` — the Claude lane requests `xhigh` for ordinary complex semantic implementation and
  repair: that is the default heavy coding lane. It requests `max` only for capability-critical implementation
  or the hardest correctness-critical consolidated repair, on an explicitly named trigger; `max` is never the
  general default and never a reward for a project mattering. Thinking is always enabled on Claude Opus 5.5, and
  `THINKING_ACTUAL` is still reported from runtime evidence rather than assumed from this rule. Routine status
  and read-only evidence work stays controller-owned instead of spending the Claude lane.
- Subagents default to 0 (at most 2 read-only, for genuinely independent substantial tracks); only one agent
  mutates a branch.

### 24.13 CONTROL_PLANE_CLAIM_MINIMIZATION, explicit non-claims and MATERIAL_CAPABILITY_CHANGE

`CONTROL_PLANE_CLAIM_MINIMIZATION` — the setup enforces only properties materially necessary to operate the
crypto_core development workflow. It never introduces a persistent validator, registry, abstraction, filesystem
layer, host-discovery layer, schema, dependency or process merely because it can be modelled. A new durable
mechanism is legal only when at least one is proven: (1) it closes a real safety/correctness gap inside the
ACTIVE declared workflow contract; (2) it repairs broken fresh-chat continuity; (3) it handles a material
capability or tool change; (4) it measurably removes repeated operational work. Otherwise it is
`OUT_OF_SCOPE` / P3 / `NOT_REQUIRED`. Audits judge the declared semantic contract and never continuously expand
it (`FINITE_AUDIT_RULE`, 24.4).

`EXPLICIT_NON_CLAIMS` — this kernel does NOT claim: a repository-global host auto-discovery closed world; a
universal GitHub configuration inventory; a universal filesystem observation authority; path-grammar totality;
a symlink/junction security framework; case-folding filesystem equivalence; a Unicode/device-name portability
framework; or the validity of arbitrary host configuration. No machinery exists or may be built for these unless
a future ACTIVE capability actually depends on one, through a change that passes the test above.

`COPILOT_STATUS=INACTIVE_UNAVAILABLE` — Copilot receives no routing, prompts, setup loading or accepted state.
Copilot-era repository files (`.github/copilot-instructions.md`, `.github/prompts/**`,
`.github/instructions/**`, `.github/hooks/**`) are inactive compatibility material outside this contract: this
kernel neither edits, validates nor inventories them. `MATERIAL_CAPABILITY_CHANGE` — any future Copilot
activation, and any new host auto-discovery integration, requires a separate audited control-plane change BEFORE
use.

`scripts/crypto_core/audit_agent_setup.ps1` is advisory local tooling (its exit code is always 0 and it is not
a CI gate) and holds no authority. Its lane-set and role-keyword assertions predate this kernel; a message from
it never overrides this section.

### 24.14 SETUP_FREEZE and PRODUCT_DEFAULT

`SETUP_STATUS=CLOSED_FROZEN` holds once this kernel's setup PR is independently accepted, merged, post-merge
verified and fresh-chat accepted. The status is proven from that live evidence (24.11) and never written into a
durable file. From then on the setup/workflow reopens ONLY for `REAL_SAFETY_DEFECT`, `BROKEN_CONTINUITY`,
`MATERIAL_CAPABILITY_CHANGE` or `MEASURED_REPEATED_WORK_REDUCTION`, each named with its evidence in the
reopening prompt. Forbidden reopen reasons: wording polish; a P3 nit; style preference; "could be more
complete"; a new theoretical edge case outside the active contract; the desire for a stronger validator;
generic architecture improvement. A reopening change follows the same lifecycle (24.8) as any other PR.

`PRODUCT_DEFAULT` — after `SETUP_STATUS=CLOSED_FROZEN` the default next action is PRODUCT work, and ordinary
product PRs never redesign the workflow. Product PRs use `LARGEST_SAFE_SEMANTIC_CLOSURE`, the fewest-prompt
budget (target 2 clean / 4 repaired, hard maximum 5 counting every challenge, no execution 6), one complete
acceptance audit by the lane of 24.4 — the ChatGPT controller for a non-protected candidate, GPT-6 Astra for a
protected one — at most one consolidated repair and one whole-contract re-audit (24.4, 24.8).

`CLAUDE_LANE_UPGRADE_TRANSITION` — `CLAUDE_OPUS_5_5_CONTROL_PLANE_UPGRADE_V1` (the Claude lane identity of 24.3,
its effort policy in 24.12 and the adapters that apply them) is a reopening under `MATERIAL_CAPABILITY_CHANGE`
alone: it replaces the model identity of the existing Claude lane and changes no role, authority, budget,
lifecycle or gate. The change that introduces it grants itself no exemption. Its own acceptance is governed by
the control plane accepted before it, so the superseded Claude lane implements it and GPT-6 Astra audits it, and
Claude Opus 5.5 becomes the routable Claude lane only once that change is independently accepted, merged,
post-merge verified and fresh-chat accepted. A model may never accept its own successor.

`ASTRA_UNIFIED_AUDIT_TRANSITION` — `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` (the audit, fixed-point and lifecycle
rules of 24.3, 24.4, 24.5 and 24.8) is a reopening under `MATERIAL_CAPABILITY_CHANGE` (GPT-6 Astra as the preferred
frontier audit lane) and `MEASURED_REPEATED_WORK_REDUCTION` (duplicated ordinary-then-protected review of the same
head). The change that introduces it grants itself no exemption and no retroactive credit: its own acceptance is
governed by the control plane accepted before it, and these rules become authoritative only once that change is
independently accepted under the prior plane, merged, post-merge verified and fresh-chat accepted. While that
change is under acceptance audit, every auditor and the ChatGPT controller apply this section and the host
adapters as they stand on its base (accepted main), never the candidate's own text: the candidate's text is the
object under audit, not the audit procedure, so the prior plane's ordinary independent audit and protected GPT-6
Astra terminal audit remain performable. The amendment's own rules, including the Sol protected-trigger stop,
bind only candidate lifecycles that start after it is merged and post-merge verified. From then on
`SETUP_STATUS=CLOSED_FROZEN` holds again under the reopen rules above — proven from live evidence, never written
into a durable file — and the default next action is product work.

`CODEX_QUOTA_RESILIENCE_V2_TRANSITION` — `CODEX_QUOTA_RESILIENCE_V2` (the audit routing and execution accounting of
24.3, 24.4, 24.5, 24.6, 24.8, 24.10 and 24.12 and the surfaces that apply them) is a reopening under
`MATERIAL_CAPABILITY_CHANGE`: routing a GPT-6 Astra `Ultra` audit to every serious candidate draws on the shared
Codex quota faster than protected acceptance needs, while controller and Claude capacity sit idle. It is a
`ROOT_CAUSE_ESCAPE` from accepted main: the closed, unmerged V1 candidate is negative evidence only, and its
blocker identities — `PRE_ASTRA_REPAIR_TEMPLATE_INCONSISTENCY`, `HARD5_CHALLENGE_BUDGET_ESCAPE`,
`FIFTH_SLOT_RESERVATION_CONTRADICTION` and `LIFECYCLE_EXAMPLE_MISNUMBERING` — are closed here by the architecture of
24.8 (one budget with no reserved place, the admission rule, count-derived paths, and `REPAIR_ENTRY_MODE` with
mandatory repair-prompt fields). The change that introduces V2 is NOT governed by V2: it is a trigger-A candidate
governed exclusively by the plane accepted before it, so its own lifecycle is its implementation → ONE GPT-6 Astra
`Ultra` independent and protected whole-contract audit → only if that audit returns a complete material P1/P2 set,
ONE consolidated Claude Opus 5.5 repair → exactly ONE Astra whole-contract re-audit → any remaining genuine
P1/P2 → `REJECT/FREEZE`. For that change, controller preflight and an Opus challenge cannot open its repair, the
pre-Astra entry mode of 24.8 does not apply to it, and it is not mutated between implementation and its first Astra
audit on controller, automated-review or same-model findings — those are evidence for Astra and for adjudication
under the base lifecycle. Every auditor and the controller apply this section and the host adapters as they stand
on its base (accepted main), never the candidate's own text. V2's rules bind only candidate lifecycles that start
after it is merged, post-merge verified and fresh-chat accepted; a lifecycle already open finishes under the plane
it started under. From then on `SETUP_STATUS=CLOSED_FROZEN` holds again under the reopen rules above — proven from
live evidence, never written into a durable file — and the default next action is product work.

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

*v6.0 (2026-09-14): `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` — a controller-authorized architecture rescue
built directly from accepted main. It is not a repair of the closed, unmerged PR #383 or PR #384 candidates:
their repository-wide host-discovery and filesystem-totality mechanisms were never merged and are not adopted;
their lesson is not to make unnecessary global claims. Section 24 now holds a small operational kernel in place
of the v1 lane set, taxonomy and routing function: crypto_core-only scope and ChatGPT controller authority;
the active model/tool council (ChatGPT controller, Claude Opus 5, Codex GPT-5.6 Sol as engineering accelerator
and ordinary independent reviewer, GPT-6 Astra as the sole protected T4 terminal auditor, ChatGPT Work, Deep
Research), with Claude Sonnet 5 and Codex Terra/Luna moved to `NOT_IN_ACTIVE_COUNCIL`; literal host effort
labels; `PR_SIZING_AUTHORITY=SEMANTIC_CLOSURE_ONLY` with `LARGEST_SAFE_SEMANTIC_CLOSURE`; the ~3 / hard-5
meaningful-prompt budget; complete blocker collection; one consolidated repair; one whole-contract re-audit;
`FIXED_POINT_STOP`; `ROOT_CAUSE_ESCAPE`; blocker identity across renames; the serious prompt compiler; the
runtime-proof block; fresh-chat bootstrap with live-state precedence and the new
`docs/crypto_core/continuity/CONTINUITY_INDEX.md`; `CONTROL_PLANE_CLAIM_MINIMIZATION` with explicit non-claims;
Copilot `INACTIVE_UNAVAILABLE` with activation as a material capability change; `SETUP_FREEZE`; and the product
default. Sections 1-19 were aligned (role table, lifecycle, repair loop, PR sizing, precedence) and section 22
is labelled historical; `AGENTS.md`, `CLAUDE.md`, both skills, the model prompting guide and the Opus 5
playbook were rewritten to apply the kernel. Docs/setup only: no product code, tests, scripts, workflows, hooks,
dependencies or executable validators touched; no safety gate weakened.*

*v6.0 same-PR consolidated repair (2026-09-14): the one consolidated repair of this setup PR closed three
blockers as one operational-governance closure. (1) Bounded specialist prompt accounting: `MEANINGFUL_PROMPT`
now counts only specialist executions (implementation, independent audit, repair, whole-contract re-audit,
protected terminal audit). Controller governance - state proof, CI reads, evidence adjudication,
merge-readiness, the authorization request, merge, post-merge verification, fresh-chat acceptance - sits outside
the budget and may not hide specialist work, so a repaired protected candidate completes at five specialist
prompts with no sixth; verdicts bind the exact head. (2) Fail-closed runtime proof: `MODEL_ACTUAL` and required
`THINKING_ACTUAL` must be positively proven on execution evidence and `UNKNOWN` stops; only effort telemetry may
stay `UNKNOWN`. (3) Independent-audit availability resilience: Codex GPT-5.6 Sol stays the PRIMARY ordinary
independent auditor. The ChatGPT controller is a narrow `ORDINARY_INDEPENDENT_AUDIT_FALLBACK` only when Sol is
unavailable, quota-blocked or stopped by runtime proof before substantive audit, the reason is recorded, and the
controller neither implemented nor repaired the candidate. The fallback never satisfies protected T4, and GPT-6
Astra exclusivity is unchanged. Docs/setup only; no scripts, tests, workflows, hooks, validators or dependencies
touched.*

*v6.0 final known-blocker closeout (2026-09-14): closed `ORDINARY_AUDIT_SOL_AUTHORED_DEADLOCK`. Section 24.4
now decides independence eligibility before operational availability: Codex GPT-5.6 Sol audits only a
candidate it neither implemented nor repaired, and only when available and runtime-proven; a Sol-authored
candidate goes to the ChatGPT controller fallback; a ChatGPT- or ChatGPT Work-authored candidate goes to Sol;
with no independent eligible reviewer the gate stops with proof. Docs only.*

*v6.1 (2026-09-15): `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` — a bounded control-plane convergence justified by a
material routing capability change (GPT-6 Astra as the preferred frontier audit lane) and measured repeated-work
reduction (the ordinary audit → repair → re-audit → protected terminal audit chain reviewed protected heads twice).
GPT-6 Astra becomes the PRIMARY independent auditor (`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1`, default effort
`Ultra`), and one Astra audit satisfies the independent, complete-blocker, protected Class-C and terminal audits of
a protected candidate together. Codex GPT-5.6 Sol stays the repo-native engineering accelerator and becomes the
first `NON_PROTECTED_AUDIT_FALLBACK`, with the ChatGPT controller as the last resort; neither ever satisfies a
protected audit. Added `AUDIT_MATERIALITY_BOUNDARY_V1` and `FINITE_AUDIT_RULE`. The specialist-prompt target is 2
clean and 4 repaired, with the hard maximum 5 kept as an emergency ceiling and no prompt 6. One consolidated repair
and one whole-contract re-audit are unchanged; P3 never triggers `FIXED_POINT_STOP`; runtime proof, human exact-head
merge authority, CI gates and `ROOT_CAUSE_ESCAPE` are unchanged. Sections 2, 3, 4, 8, 10 and 19 were aligned. The
transition rule (24.14) keeps the introducing change governed by the previously accepted plane. Docs/setup only: no
product code, tests, scripts, workflows or dependencies touched.*

*v6.2 (2026-09-24): `CLAUDE_OPUS_5_5_CONTROL_PLANE_UPGRADE_V1` — a bounded `MATERIAL_CAPABILITY_CHANGE` that
replaces the ACTIVE Claude lane **Claude Opus 5** (`claude-opus-5`) with **Claude Opus 5.5**
(`claude-opus-5-5`, released 2026-09-22, supported in Claude Code) across every active surface: the section 2
role table, the 24.3 routing matrix, `ASTRA_T4_EXCLUSIVE`, `HOST_UI_LABELS_ARE_LITERAL`, the outside-council
list, 24.4, `AGENTS.md`, `CLAUDE.md`, the token-efficient-loop skill, the model prompting guide, the Opus
prompting playbook, both token-efficiency companions and the advisory setup audit script. Claude Opus 5 becomes
`SUPERSEDED_BY_OPUS_5_5` and is NOT an automatic fallback. The Claude role is unchanged — primary deep semantic
implementation and repair, the single consolidated repair, `ROOT_CAUSE_ESCAPE` implementation and the
repo-native work of that same task, with self-audit only — and it never becomes an independent or protected
auditor, controller, governance or merge authority. The effort policy is restated in current literal labels
(24.12 `CLAUDE_EFFORT_POLICY`): `xhigh` as the default heavy coding lane, `max` only on an explicitly named
capability-critical or hardest-correctness-critical trigger, and the retired Opus 5 literal `xhighultracode` is
never carried onto Opus 5.5; thinking is always enabled on Opus 5.5 and `THINKING_ACTUAL` is still proven from
runtime evidence. Unchanged: the domain operating profile, `CONTROLLER_READONLY_FIRST_POLICY`,
`ASTRA_UNIFIED_INDEPENDENT_AUDIT_V1` and sole protected Astra Class-C authority, `AUDIT_MATERIALITY_BOUNDARY_V1`,
`FINITE_AUDIT_RULE`, `COMPLETE_BLOCKER_COLLECTION`, PR sizing, the specialist prompt budget, one consolidated
repair, `FIXED_POINT_STOP`, `ROOT_CAUSE_ESCAPE`, human exact-head merge authorization, one open PR and one
writer, standard merge only, subagent limits, Deep Research triggers and every product, paper, live, capital and
security gate. The transition rule (24.14 `CLAUDE_LANE_UPGRADE_TRANSITION`) keeps this change governed by the
plane accepted before it: the superseded lane implements it, GPT-6 Astra audits it, and no model accepts its own
successor. Docs/setup only: no product code, tests, workflows or dependencies touched.*

*v6.3 (2026-09-26): `CODEX_QUOTA_RESILIENCE_V2` — a `MATERIAL_CAPABILITY_CHANGE` and controller-authorized
`ROOT_CAUSE_ESCAPE` built from accepted main. It is not a repair of the closed, unmerged PR #394
(`CODEX_QUOTA_RESILIENCE_V1`): that candidate's commits and text were not adopted; its four blocker identities were
inherited and closed by architecture. Audit ROUTING changes; the acceptance standard does not. The acceptance lane
of every candidate is fixed by the finite `PROTECTED_TRIGGER_MATRIX_V2` (A-G, ambiguity classified upward): the
ChatGPT controller is the default independent acceptance auditor of non-protected candidates
(`CONTROLLER_NONPROTECTED_ACCEPTANCE_AUDIT`), and GPT-6 Astra (`gpt-6-astra`, `Ultra`, fallback prohibited, thinking
enabled) is the sole protected acceptance auditor, dispatched only on a stabilized head with a
`PROTECTED_AUDIT_PACKET_V2` after the zero-count `CONTROLLER_PROTECTED_PREFLIGHT`. Claude Opus 5.5 adds an optional,
default-off `OPUS55_READONLY_CHALLENGE` that is evidence only. Codex GPT-5.6 Sol becomes `SOL_RESERVE_ONLY`;
`NON_PROTECTED_AUDIT_FALLBACK` is retired. Section 24.8 now has one specialist execution budget of at most five in
which every kind — including the challenge — counts, with no reserved place, a `STILL_REQUIRED` /
`BUDGET_ADMISSION_RULE` pair that keeps optional executions from displacing required ones, a
`PROCEDURAL_REPLACEMENT` that consumes the same budget, canonical paths whose counts are the executions actually
run, and `REPAIR_ENTRY_MODE` (acceptance-audit or, for future protected candidates before Astra, controller
preflight) with mandatory repair-prompt fields. Added `ASTRA_QUOTA_BLOCK_FREEZE`, `USER_MANUAL_WORK_MINIMIZATION`
and `QUOTA_ROUTING_IS_ADAPTIVE` / `QUALITY_BAR_IS_CONSTANT`; strengthened `CONTROLLER_READONLY_FIRST_POLICY`. The
companion token-efficiency docs replace their stale lane and routing matrices with references to this section.
Unchanged: PR sizing, `COMPLETE_BLOCKER_COLLECTION`, `AUDIT_MATERIALITY_BOUNDARY_V1`, `FINITE_AUDIT_RULE`,
`NO_SELF_AUDIT`, one consolidated repair, one whole-contract re-audit, `FIXED_POINT_STOP`, `ROOT_CAUSE_ESCAPE`, one
open PR and one writer, human exact-head merge authorization, standard merge only, Astra as sole protected
acceptance, and every paper-first, fail-closed, deterministic, live, capital and security gate.
`CODEX_QUOTA_RESILIENCE_V2_TRANSITION` (24.14) governs this change itself under the prior plane: one Astra `Ultra`
audit, and a repair only from that audit's complete set. Docs/setup only: no product code, tests, scripts,
workflows or dependencies touched.*
