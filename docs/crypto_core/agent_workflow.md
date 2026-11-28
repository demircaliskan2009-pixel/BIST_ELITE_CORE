# crypto_core Agent Workflow v6.1

> Canonical, executable operating protocol for `crypto_core` inside `demircaliskan2009-pixel/BIST_ELITE_CORE`.
> The single canonical active authority is **section 24** (`CRYPTO_CORE_AGENT_OS_V1`, active content
> `MINIMAL_OPERATIONAL_CONTROL_PLANE_KERNEL_V1` as amended by `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1`,
> `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1`, `CODEX_EXECUTOR_QUOTA_FALLBACK_V1`, the host/workflow closure in §24.3
> and the prospective `CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1`, subject to its §24.14 transition); sections 1-19 bind where
> they agree with it and section 24 wins on any conflict; sections 20-23 are HISTORICAL. **Doctrine
> precedence:** `AGENTS.md` (entrypoint and durable rails) → section 24 → host adapters (`CLAUDE.md` /
> `CLAUDE.local.md`, `.claude/skills/crypto-core-token-efficient-loop/SKILL.md`,
> `.codex/skills/crypto-core-max-safe/SKILL.md`, `.codex/skills/crypto-core-executor-fallback/SKILL.md`)
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
| **ChatGPT controller** | Controller and router, architecture adjudication, prompt compiler, evidence judge, live GitHub verification, the Sol audit preflight packet and the CI/status polling around audits, contradiction detection, merge-readiness judgement, exactly one next action; severity adjudication under section 24.4; an independent audit only as the last-resort non-protected fallback of section 24.4. |
| **Claude Opus 5.5** (`claude-opus-5-5`) | Primary deep semantic implementation and repair, with the repo-native navigation, dependency-tracing, mechanical, test and local-validation work of that same task. |
| **Codex executor fallback** (`CODEX_EXECUTOR_QUOTA_FALLBACK_V1`; adopted id `gpt-6.2-astra`) | CONDITIONAL: one whole implementation stage or the one consolidated repair stage, only when the controller routes it after fresh Claude Opus 5.5 quota-block or unavailability evidence and every section 24.3 activation gate holds; never an audit, never a Sol-family model, never an automatic switch. |
| **GPT-6.1 Sol** (`gpt-6.1-sol`) | Incumbent `ACTIVE_SOL_AUDITOR` (section 24.3) while the route state resolves to `PRE_ACTIVATION_VERIFIED` (section 24.7 `SOL_ROUTE_STATE_RESOLUTION`): PRIMARY independent auditor (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`): READ_ONLY exhaustive whole-contract audit and the one whole-contract re-audit, and for protected work the sole protected T4 audit in the same execution; an audit-only lane, never implementation, repair or routine status work. |
| **GPT-6.2 Sol** (`gpt-6.2-sol`) | Named prospective successor auditor: only a separately authorized bounded qualification before activation; the `ACTIVE_SOL_AUDITOR` with the role above only when the route state resolves to `POST_ACTIVATION_VERIFIED` (section 24.7) after the complete section 24.14 `GPT62_SOL_SUCCESSOR_ACTIVATION`. Never an executor. |
| **ChatGPT Work** | Substantial multi-step execution when a cloud browser/computer, many files, apps or evidence collection materially help; never governance authority. |
| **Deep Research** | Current load-bearing external facts only; advisory. |

GPT-6 Astra (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`) and Codex GPT-5.6 Sol
(`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`) are no active lane, default, fallback or dependency (section 24.3).
GPT-6.2 Astra (`gpt-6.2-astra`) is a different model id, routable only as that conditional executor. GPT-6.1 Terra
(`gpt-6.1-terra`) is `EVALUATION_ONLY`.

Every serious prompt/report carries the runtime-proof block of section 24.12. Model strength is never proof.

### 2a. Independent audit rule

An implementation cannot self-satisfy the independent audit gate in the same context. Implementation and
audit are separate fresh-context, pinned-head tasks (section 24.4), and no model audits its own implementation
or repair. Current valid P1/P2 threads block. Outdated threads do not block code, but any resolution needs
explicit guarded closeout; human threads are never self-resolved.

## 3. Hard Rules

- crypto_core only; **no BIST implementation leakage** (BIST is historical context).
- **One open PR at a time.** The controller verifies live (`gh pr list --state open`) at the start of every task.
- **No direct push to `main`.** No force-push. No branch deletion unless the authorized command says so.
- **Standard merge only** (no squash/rebase). **No merge without explicit human authorization naming the PR and the exact command.**
- **CI `pending` / `queued` / `in_progress` / `no checks reported` is NOT_READY** — the ChatGPT controller polls the exact head to terminal or records a bounded-timeout snapshot (section 24.5 `HANDOFF_OWNERSHIP`). Never treat a startup window as green.
- **CI not registered (no run created for a fresh head): diagnose before re-triggering.** Prove it from `gh run list` / commit `check-runs` and classify (`ACTIONS_DELAY_OR_GITHUB_INFRA` vs trigger/path/ref issue). At most **one** empty re-trigger commit (`chore(crypto-core): retrigger …`), and **only** with explicit user/controller authorization. Never loop no-op commits.
- **Branch naming:** feature slices → `feature/<crypto-core-scope>-prN`; setup/docs → `chore/<crypto-core-scope>-prN`; repair stays on the **same branch** for the same PR. (Older `product/*` naming is superseded.)
- **Setup/doctrine changes are never mixed into a feature PR.** Feature PRs touch `src/`/`tests/` product code; setup PRs touch docs/config only (`AGENTS.md`, `docs/crypto_core/**`, `.codex`, `.vscode`, `.cursor`, `.github` docs, `scripts/crypto_core` audit tooling). See §17.
- **The independent audit (section 24.4) is a separate gate**, and automated PR review comments arrive asynchronously — an implementation/repair turn ends at its authorized publication and exact-head handoff (section 24.5 `HANDOFF_OWNERSHIP`); it does not poll CI to terminal, does not block waiting for review, and holds no mutation authority after the handoff. The controller owns remote CI/CodeQL polling, failure classification and the audit preflight.
- Every repo-state claim must be **git/gh/test-verifiable** (never from memory). Unproven → mark `UNKNOWN`.
- **Same-branch repair only**, as the single consolidated repair of the candidate lifecycle (section 24.8), for the
  complete valid blocker inventory of its opening audit: every valid in-scope material P1/P2 and every
  independently confirmed `CI_GATE_BLOCKER` (section 24.4 `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1`); either kind alone
  opens it, with the applicable action authorization. Stop on unsafe scope expansion.
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
2. The routed implementer runs the **Implementation Loop** (§5) → opens one PR → hands off its exact head.
   The controller verifies natural CI, CodeQL and reviews to terminal.
3. One exhaustive fresh-context independent audit — the `ACTIVE_SOL_AUDITOR` (section 24.3;
   `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`), which for protected or control-plane work is also the protected audit;
   for non-protected work only, the recorded section 24.4 fallback — returns the complete material P1/P2 set (§8).
   It is admitted on terminal green exact-head CI, or as a first audit in `REPAIR_ONLY` mode under
   `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` (section 24.4).
4. If it found material P1/P2, or independently confirmed a `CI_GATE_BLOCKER`: at most ONE consolidated repair
   (§6) on the same branch, then — once every required check on the repaired head is terminal green — exactly ONE
   whole-contract re-audit to the same standard. Any genuine material P1/P2 left → `FIXED_POINT_STOP`: the
   candidate is rejected and frozen. P3 never blocks merge.
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
# Controller STATE_PIN must show zero open PRs on the current base. Refresh it if stale or contradicted.

# create + switch to a topic branch BEFORE any patch/commit/push (never edit/commit on main)
git switch -c <topic-branch>               # feature/<crypto-core-scope>-prN (feature) or chore/<crypto-core-scope>-prN (setup/docs)
git status --short --branch                # confirm: on the topic branch, clean
# patch only after this point
```

**Branch invariant (implementation mode — always holds):**
- `main` is checked out **only** for precheck / base-SHA proof — never edited, never committed on.
- The routed executor (Claude Opus 5.5, or a section 24.3 Codex executor) **creates and switches to a topic
  branch** (`git switch -c <topic-branch>`) before the first edit.
- **All commits and pushes happen on the topic branch**; never `git commit` on `main`, never push to `origin/main`.
- The PR is opened **from the topic branch into `main`** (`gh pr create --base main --head <topic-branch>`).

Then (all on the **topic branch**): bounded read (named files only, no broad scan) → design → the largest
safe semantic closure inside the allowed files (section 24.8) → self-audit (scope / digest re-proof /
provenance / strict-Decimal / fail-closed / no hidden IO / paper-safety triple) → targeted tests →
relevant suite → **full helper after meaningful changes** → `git diff --check` → scoped `git add <paths>` →
commit (on the topic branch) → push (the topic branch) → `gh pr create --base main --head <topic-branch>` →
report the local evidence (§10). The controller polls CI to terminal (§3) and collects threads (§8). **No merge.**

## 6. Consolidated Repair Loop

- This is the single consolidated repair of the candidate lifecycle (section 24.8): it repairs the COMPLETE
  audit blocker set by root cause in one change — never finding-by-finding, never a second repair, never on a
  rejected or frozen candidate.
- Precheck first (branch + `HEAD == expected SHA` + clean tree + exactly one open PR + changed files ⊆ scope).
- Pin PR number and expected head; repair **only the named blockers**, **same branch only**, bounded to named files.
- **Test-only by default**; touch production only if a **new failing test proves a real defect**, and only inside the named module. If test-only, prove `git diff <prev> HEAD -- src/` is **empty**. A confirmed `CI_GATE_BLOCKER` (section 24.4) is corrected only by the authorized change its confirmation names, inside the allowed files, proven by the existing tests plus any targeted test the contract needs and by the required check turning green; never by alert dismissal, suppression, test or check weakening, waiver or a dummy change.
- Re-validate fully (targeted → relevant suite → full helper `PYTEST_EXIT=0` → `git diff --check`) → scoped add → commit → push same branch → hand off the repaired head for controller CI verification. **No merge.**

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

- The independent audit (GPT-6.1 Sol by default, section 24.4) is exhaustive and materiality-aware
  (`COMPLETE_BLOCKER_COLLECTION`, `AUDIT_MATERIALITY_BOUNDARY_V1`): it returns the complete current material P1/P2
  set of the declared contract in one pass, never one finding at a time.
- Automated Codex PR review comments run **asynchronously** after a push and are review threads for controller adjudication, not the routed independent audit; findings may not exist when the executor's turn ends. The controller collects reviews and threads at terminal CI, records their exact-head status, and refreshes them at merge preflight.
- Inspect via GraphQL: `reviewThreads(first:n){ nodes{ id isResolved isOutdated path line comments } }` + `reviews`.
- The auditor emits the report in §10. ChatGPT relays the complete valid material finding set (with thread IDs) and every confirmed `CI_GATE_BLOCKER` in the single consolidated repair prompt (section 24.8); the executor does not wait in-turn for review.

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
VERDICT / AUDIT_MODE / P1_BLOCKERS / P2_BLOCKERS / CI_GATE_BLOCKERS / NON_BLOCKING_NOTES / MERGE_READINESS /
REQUIRED_REPAIRS_IF_ANY
```
(`AUDIT_MODE` and `CI_GATE_BLOCKERS` follow section 24.6 `COMPACT_AUDIT_HANDOFF`.) The implementer's `CHECKS` field is
the publication-time snapshot only; terminal CI belongs to the controller (section 24.5).

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
`.codex/skills/crypto-core-max-safe/SKILL.md`, `.codex/skills/crypto-core-executor-fallback/SKILL.md`) → the
prompting guides**, with
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
  fact; GPT-6.1 Sol stays the primary independent audit and the sole protected audit
  (section 24.4); the GitHub connector stays the source-of-truth state gate; Deep Research is research/advisory, **never an
  executor lane and not merge authority** — any authorized mutation is routed by the controller to
  Claude/`gh` or the GitHub connector, never executed by Deep Research.
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
routing function and prompt policy, as amended by `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` (the unified audit,
materiality, fixed-point and lifecycle rules of 24.4, 24.5 and 24.8 and the transition rule of 24.14; its audit
lane is superseded), by `CLAUDE_OPUS_5_5_CONTROL_PLANE_UPGRADE_V1` (the Claude lane identity of 24.3, its effort
policy in 24.12 and the transition rule of 24.14) and by `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1` (the GPT-6.1
Sol audit lane of 24.3 and 24.4, `SOL_AUDIT_USAGE_EFFICIENCY_V1`, the prompt compaction and compact audit handoff
of 24.6, the Sol effort, speed, subagent and telemetry policies of 24.12 and the transition rule of 24.14) and by
`CODEX_EXECUTOR_QUOTA_FALLBACK_V1` (the conditional Codex executor lane, adopted ids, activation gates, stage and
interrupted-stage rules of 24.3, the independence sentence of 24.4, the executor handoff fields of 24.6, the executor
adapter of 24.7, the budget wording of 24.8, `CODEX_EXECUTOR_EFFORT_POLICY` of 24.12 and the transition rule of
24.14), and by `CRYPTO_CORE_AGENT_OS_HOST_AND_WORKFLOW_CLOSURE_V1` (stage authorization and host evidence in
24.3 and 24.12, controller and writer responsibilities in 24.5, prospective adoption in 24.14). The prospective
`CRYPTO_CORE_AGENT_OS_FINAL_EFFICIENCY_AND_MODEL_ROUTING_V1` amendment covers stage selection (24.3), approval
provenance and remote closeout (24.4–24.6), subject to its own 24.14 transition. The prospective
`CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1` amendment covers runtime admission and literal effort (24.12),
Claude availability evidence, `ACTIVE_SOL_AUDITOR` and the named GPT-6.2 Sol successor (24.3, 24.14), audit
admission and `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` (24.4), handoff ownership and approval sources (section 3, 24.5),
prompt safety and handoff fields (24.6), route recovery (24.7), execution accounting, interruption and
`ADMINISTRATIVE_CLOSURE` (24.8), and the policy hierarchy and operational flexibility (24.13), subject to its own
24.14 transition. This section governs how crypto_core
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
  `.codex/skills/crypto-core-max-safe/SKILL.md`, `.codex/skills/crypto-core-executor-fallback/SKILL.md`) → the
  prompting guides (`model_prompting_guide.md`,
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
| **ChatGPT controller** | Controller and router; architecture adjudication; prompt compiler (24.6); evidence judge; severity adjudication under `AUDIT_MATERIALITY_BOUNDARY_V1` (24.4); live GitHub verification through the connector/`gh`; the compact `SOL_AUDIT_PREFLIGHT_PACKET` and the CI/status polling around every audit (24.4); contradiction detection; merge-readiness judgement; exactly one next action; an independent audit only as the last resort of `NON_PROTECTED_AUDIT_FALLBACK` (24.4) | Product implementation; any independent audit outside that fallback; auditing a candidate it implemented or repaired; any protected audit; a substitute for local tests or unverified repository state; GitHub mutation without an exact human action authorization; merge authority |
| **Claude Opus 5.5** (`claude-opus-5-5`) | Primary deep semantic IMPLEMENTATION and REPAIR, including the single consolidated repair of a candidate (24.8) and the `ROOT_CAUSE_ESCAPE` implementation (24.8), together with the repo-native navigation, dependency-tracing, mechanical, static-inspection, test-generation, local validation and CI-diagnosis work that belongs to that same task | Any independent audit of its own work; any protected audit; controller, governance or merge authority |
| **Codex executor fallback** (`CODEX_EXECUTOR_QUOTA_FALLBACK_V1`; the adopted executor id `gpt-6.2-astra`, GPT-6.2 Astra, on a Codex host) | CONDITIONAL implementation and repair executor for ONE whole specialist stage — an IMPLEMENTATION, including a `ROOT_CAUSE_ESCAPE` implementation, or the candidate's `ONE_CONSOLIDATED_REPAIR` (24.8) — only when the ChatGPT controller explicitly routes that stage to it because the Claude lane cannot run it and every activation gate below holds, under the same prompt shape, validation ladder, budget slot and gates as the Claude stage it replaces | Any audit or re-audit; any Sol-family model id; a route without its recorded activation; switching or being switched mid-stage; mutation concurrent with any other writer; automatic or self-selected routing; controller, governance or merge authority |
| **GPT-6.1 Sol** (`gpt-6.1-sol`, on the ChatGPT Work/Codex host) | The incumbent `ACTIVE_SOL_AUDITOR` (below) while the route state is `PRE_ACTIVATION_VERIFIED`, as the PRIMARY independent auditor (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`, 24.4): the READ_ONLY fresh-context exhaustive whole-contract audit and the one whole-contract re-audit of serious candidates, and for protected work the sole protected T4 `CLASS_C_CROSS_CONTRACT` audit in the same execution, run under `SOL_AUDIT_USAGE_EFFICIENCY_V1` (24.4). Requested effort `Ultra`, mandatory for protected audits; speed `STANDARD`; subagents 0 by default (24.12) | Mutation; implementation or repair; routine GitHub status, CI polling, thread enumeration, repository archaeology or mechanical work that belongs to the controller or Claude; auditing a candidate that it, or any execution on its model id, implemented or repaired; any reassignment of protected T4 to another lane; an automatic fallback after the successor activation |
| **GPT-6.2 Sol** (`gpt-6.2-sol`) | Named prospective successor auditor (`GPT62_SOL_SUCCESSOR_ACTIVATION`, 24.14). Before activation: only the separately authorized bounded read-only qualification of 24.14, outside any candidate lifecycle. When the route state is `POST_ACTIVATION_VERIFIED` after the complete activation: the `ACTIVE_SOL_AUDITOR`, with the GPT-6.1 Sol role above (requested effort `Ultra`, mandatory for protected audits; speed `STANDARD`; subagents 0 by default) | Any production audit, protected audit or route before activation; implementation, repair or any executor role; mutation; self-activation; auditing a candidate that any execution on its model id implemented or repaired |
| **ChatGPT Work** | Substantial multi-step execution when a cloud browser/computer, many files, apps or evidence collection materially help, under the same prompt shape (24.6) and gates | Governance authority; accepted state; merge authority |
| **Deep Research** | Current load-bearing external facts only (24.9) | Repository/PR/CI state; implementation; mutation; gate waivers |

`ACTIVE_SOL_AUDITOR` — exactly one model id holds the primary independent and exclusive protected audit route at
any time. After canonical adoption that id is determined only by the route state that `SOL_ROUTE_STATE_RESOLUTION`
(24.7) resolves from positive current evidence — never from the absence of a record, memory, preference, model
availability or a guess:
- `PRE_ACTIVATION_VERIFIED` → `gpt-6.1-sol` (GPT-6.1 Sol, the incumbent).
- `POST_ACTIVATION_VERIFIED` → `gpt-6.2-sol` (GPT-6.2 Sol). `gpt-6.1-sol` is then HISTORICAL for the active route and
  is no automatic fallback, default or dependency.
- `ACTIVATION_STATE_UNKNOWN` (including its `CONTRADICTORY` subtype) → `UNRESOLVED`: no audit route is selected, and
  every stage that needs one holds for controller recovery (24.7). It never silently activates the successor and
  never reverts an effective activation.
- A failed, stopped or incomplete qualification changes no route state: the incumbent stays eligible only while
  `PRE_ACTIVATION_VERIFIED` holds. Before adoption the introducing lifecycle names literal `gpt-6.1-sol` under its
  accepted-base procedure (24.14) and consults no route state.
- Wherever an active rule of this section, sections 1–19, the host adapters or the prompting guides names GPT-6.1
  Sol, `gpt-6.1-sol` or a `GPT61_SOL_*` rule as the auditor of a candidate, it names the `ACTIVE_SOL_AUDITOR` and
  that id's literal `MODEL_ID_REQUIRED` (none while `UNRESOLVED`). Dated records, completed transitions and the
  introducing transition of `CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1` (24.14) name the literal model they
  state. Distinct Sol ids confer no rights on one another.

`GPT61_SOL_T4_EXCLUSIVE` — protected T4 belongs to the `ACTIVE_SOL_AUDITOR` alone. When it is unavailable,
quota-blocked, cannot be requested at its required effort label, is stopped by runtime admission (24.12) or is
`UNRESOLVED` (24.7), the protected gate waits on the frozen exact head (`CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE`);
nothing reassigns or silently substitutes T4 — not the other Sol id, GPT-6 Astra, Codex GPT-5.6 Sol, Claude Opus 5.5,
GPT-6.2 Astra, the ChatGPT controller, ChatGPT Work or any other lane. A retired or permanently unavailable protected
auditor with no authorized eligible successor is a `MATERIAL_CAPABILITY_CHANGE` (24.13), never permission for
arbitrary substitution. Non-protected work continues under 24.4.

`HOST_UI_LABELS_ARE_LITERAL` — record the selected host control and the executing session's values verbatim.
Keep the provider, model ID and client surface attached to each observation. Never translate an effort across
providers, model families or client surfaces, or infer a selector label from an API enum. Section 24.12 governs
each lane. Protected audits by the `ACTIVE_SOL_AUDITOR` require the literal selector `Ultra`.

Outside the council — none is routable, a fallback or a dependency: **Copilot `INACTIVE_UNAVAILABLE`** (24.13);
**GPT-6 Astra `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`**; **Codex GPT-5.6 Sol
`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`**; **Claude Fable 5 `INACTIVE_EXPIRED_RETIRED`**; **Claude Opus 5
`SUPERSEDED_BY_OPUS_5_5`**; **Claude Opus 4.8 `SUPERSEDED_BY_OPUS_5`**; **Claude Sonnet 5, Codex GPT-5.6 Terra and
Codex GPT-5.6 Luna `NOT_IN_ACTIVE_COUNCIL`**. A superseded lane is never an automatic fallback:
`MODEL_FALLBACK=PROHIBITED` holds for every serious routed crypto_core task (24.12). Their former roles moved:
status, polling and mechanics to the ChatGPT controller's live verification or the routed session's own terminal
proof; repo-native, bounded and clear-spec engineering to the Claude Opus 5.5 task that needs it; independent
review, including protected T4, to the `ACTIVE_SOL_AUDITOR` (24.4); deep semantic implementation to Claude Opus 5.5. Earlier
definitions survive only in the HISTORICAL sections and the dated changelog. Activating any of them is a
`MATERIAL_CAPABILITY_CHANGE` (24.13).

`CODEX_EXECUTOR_QUOTA_FALLBACK_V1` — Claude Opus 5.5 stays the primary implementation and repair executor. A Codex
executor is a conditional route for ONE whole specialist stage that the Claude lane cannot run, selected by the
ChatGPT controller. It is never a default, never an automatic or self-selected switch, never an audit, and never a
`MODEL_FALLBACK`: the route is decided before the stage starts and compiled into that stage's own serious prompt,
whose `MODEL_ID_REQUIRED` is the selected executor id, and inside that execution `MODEL_FALLBACK=PROHIBITED` holds as
everywhere (24.12).

- `CODEX_EXECUTOR_ADOPTED_IDS` — exactly one id is adopted: `gpt-6.2-astra` (GPT-6.2 Astra), eligible for every
  executor stage. A host that lists a model never adopts it; adopting, retiring or re-scoping an executor id is a
  `MATERIAL_CAPABILITY_CHANGE` (24.13) proven on host evidence. No lower-cost executor is adopted: a bounded
  mechanical stage routes to `gpt-6.2-astra` or waits for Claude until a lower-cost id is adopted on evidence that it
  can close a complete bounded stage and its validation. No Sol-family model id (`gpt-6.1-sol` or any other GPT Sol
  id) is ever a Codex executor. GPT-6.2 Astra is a different model id from GPT-6 Astra (`gpt-6-astra`), which stays
  `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT` and outside the council.

**Controller stage selection.** Apply these decisions in order at the stage boundary. Record the decision in
the existing prompt fields (24.6).

1. Identify the semantic contract, task intent, protected triggers (24.4), exact pin, approvals and allowed
   actions. Keep GitHub evidence collection with the controller. Bind every prospective audit to the set of
   model IDs that implemented or repaired this candidate. An unresolved classification or missing authority
   stops the dependent stage.
2. For an audit, apply independence before availability (24.4). Route protected work only to the
   `ACTIVE_SOL_AUDITOR` at literal `Ultra`, admitted under 24.12. If unavailable, hold the protected audit on its
   exact head. For non-protected work use
   the existing primary and recorded last-resort path in 24.4. Distinct Sol IDs confer no rights on one another.
3. For implementation or the one repair, use Claude when available and feasible. Only gate A evidence for
   this stage permits consideration of the adopted Codex executor. Unknown Claude availability goes back to
   the controller. Price, a host listing or a preference cannot trigger fallback.
4. Match the entire stage to an adopted role. Check its dependencies, trust boundaries, host, validation
   access, known quota/context constraints and separate eligible auditor against A–G as applicable. A bounded
   edit still has to pass the complete validation ladder for its scope. A known shortfall blocks dispatch.
   Among equally qualified, authorized choices within the same routing priority, prefer the one with better
   observed usage per independently accepted comparable contract, including interruptions, repairs and
   re-audits. Keep API price, subscription allowance, credits and observed usage separate. With no comparable
   evidence, retain the accepted priority and record usage benefit as unproven. An unresolved tie with no
   adopted order returns to the controller before dispatch.
5. The controller fixes one exact ID before substantive execution. The executing host confirms 24.12 and its
   local preconditions. An unmet gate returns to the controller. An interruption after work starts follows
   `INTERRUPTED_STAGE` below and retains the consumed slot.

**Prospective roles.** `gpt-6.2-sol` as an implementation or repair executor is `REJECTED`: no Sol-family id is
ever an executor. `gpt-6.2-sol` as independent and protected auditor is the named successor of
`GPT62_SOL_SUCCESSOR_ACTIVATION` (24.14): `ADOPTED_PROSPECTIVE_CONDITIONAL`, with no dispatch authority before
activation except its bounded qualification. The `gpt-6.1-terra` mechanical/visual profile is `EVALUATION_ONLY`: a
question for separately authorized evaluation on fixed examples outside a candidate lifecycle. `REJECTED`
excludes a role from consideration on the evidence reviewed. `ADOPTED_PROSPECTIVE` describes a role expressly
approved for future stages, routable only after the complete 24.14 transition and subject to every stage gate.
These labels grant no permissions.

Changing an executor or audit role — other than the named conditional activation that
`GPT62_SOL_SUCCESSOR_ACTIVATION` already defines — requires a separate prospective controller adoption decision and
protected control-plane amendment. For the exact proposed ID and role, supply attributable host selection, supported
effort and speed, actual runtime and thinking, and a representative whole-stage result with independent
correctness and validation evidence. Compare end-to-end usage and completion risk against the accepted lane.
For an audit role, test detection of known material defects and false findings. Evaluate family-correlated
errors separately from the absolute same-ID exclusion. Any future Sol executor requires an explicit bounded
exception to the Sol-family prohibition; no amendment proposes one.

- `EXECUTOR_EVIDENCE_KINDS` — the host supplies selection and capability (`HOST_CAPABILITY_EVIDENCE`). The
  executing session supplies raw model, thinking and effort (`EXECUTION_IDENTITY_EVIDENCE`). The controller
  authorizes one stage prospectively (`CONTROLLER_AUTHORIZATION`). The assigned writer confirms runtime,
  checkout and ability to finish before its first mutation. Each record retains its own source.
- `ACTIVATION_GATES` — **controller pre-dispatch**. In `MODEL_RUNTIME_PROOF`, record the decision and basis for
  each of A–G against the named stage and `STATE_PIN`. Identify the controller prompt or accepted supplement,
  its time, and the source and time of volatile evidence. The controller may authorize the stage conditional on
  the writer's D/E and local confirmations. Until then only read-only preflight can run. A preflight-only
  request grants no write authority. A missing controller decision requires a prospective controller supplement.
  - **A · Claude availability.** Supply `CLAUDE_UNAVAILABILITY_EVIDENCE` with
    `CLAUDE_OPUS_5_5_QUOTA_BLOCKED` or `CLAUDE_OPUS_5_5_UNAVAILABLE` (the host cannot select or start the required
    id, or executes another id). Either of these suffices: Claude's own limit or error message, or a current
    attributable firsthand human statement that Claude is quota-blocked or unavailable. No screenshot, provider
    error reproduction or specialist quota-check execution is required solely to duplicate that statement. Record
    the observation source, the applicable host and model, the scope and the reset when known; never invent an
    unknown reset. The same still-current evidence is reused across applicable unstarted stages and refreshed only
    on a passed reset or expiry, a material change of applicability or a contradiction; with an unknown reset, a
    brief current-status confirmation is obtained only when genuinely necessary. A preference for Astra, price, a
    host listing or a correctable setup error is never availability evidence. Ordinary availability changes are
    operational decisions under this gate and never reopen governance (24.13).
  - **B · Selection.** Explicitly select `EXECUTOR_ROUTE=CODEX_EXECUTOR_QUOTA_FALLBACK_V1`, the executor id,
    fallback reason and the whole implementation or consolidated repair. Only the controller selects a route.
  - **C · Adoption.** Match the exact id to `CODEX_EXECUTOR_ADOPTED_IDS`.
  - **D · Host capability.** Identify the host/client, model, supported effort selection under 24.12, shell/edit
    tools, isolated writer checkout and the tools and permissions needed for the whole validation ladder.
  - **E · Runtime.** Specify the required executing id, thinking enabled and the diagnostic needed to confirm both.
    Cite current-session evidence when available. When the session does not yet exist, record the condition
    explicitly. The writer confirms D and E in the actual session before any substantive work.
  - **F · Whole stage.** The controller explicitly judges whether this executor can deliver the complete semantic
    boundary or blocker inventory and its validation. Give the basis (scope, dependencies, capacity constraints)
    before dispatch. Known shortfalls block. Unavailable usage figures stay `UNKNOWN`. An executor estimate, a
    successful handoff or a decision made after substantive work cannot fill a missing controller judgement.
  - **G · Independence.** Name the separate later `ACTIVE_SOL_AUDITOR` audit and check its id against every
    implementing or repairing id in the candidate lifecycle. Protected T4 remains exclusive to that auditor at
    literal `Ultra`.
  - Gates B–G, the sole writer, writer-local validation and publication authority stay mandatory whatever evidence
    satisfies A. A route selected here before its stage is a controller route, never a provider's unapproved
    internal model substitution (`MODEL_FALLBACK`, 24.12).
- **Executor pre-mutation.** Bind the controller's complete record to this stage, base and host. Confirm D and E
  from the actual selection and executing session. Check the isolated checkout, clean status, base/head/tree,
  sole writer, current open-PR proof (zero for implementation, exactly the candidate for repair), and feasibility
  of the whole scope and its local validation. Reject a wrong base, dirty checkout, concurrent writer, expired
  evidence, known quota/context shortfall or unmet condition. Report both records in the handoff. All A–G must
  pass before branch creation, editing or any other candidate mutation. A preflight stop consumes no specialist
  slot. Only the controller can supply a missing pre-dispatch decision, prospectively while the stage is unstarted.
- `EXECUTOR_STAGE_RULES` —
  - Stage boundary: a stage's executor is fixed before its first substantive work, and the executing provider changes
    only between stages. A Claude execution stopped by quota before any substantive work was no meaningful prompt
    (24.8) and consumed no slot, so its stage is still at its boundary.
  - One writer: the routed executor is the candidate's only writer for that stage — no Claude or other session
    mutates the candidate concurrently — and one open PR holds.
  - One lifecycle: the executor stage takes the slot of the Claude stage it replaces, inside the unchanged 2 / 4 /
    hard-5 budget (24.8). A change of executor model or provider never resets the count or adds a slot; the one
    consolidated repair stays one; `FIXED_POINT_STOP`, `ROOT_CAUSE_ESCAPE`, exact-head binding, exact-head required CI
    and the human's exact-head merge authority are unchanged.
  - Independence: every model id that implemented or repaired any part of the candidate, on any host, is an
    implementer of it (`NO_SELF_AUDIT`, 24.4). A Codex executor never audits, and its self-review is
    `SELF_AUDIT_ONLY_NOT_INDEPENDENT`. Protected work is still audited by GPT-6.1 Sol at `Ultra` alone and otherwise
    waits frozen on its exact head (`GPT61_SOL_T4_EXCLUSIVE`).
- `INTERRUPTED_STAGE` — an executor, Claude or Codex, that loses its quota or availability after substantive work
  stops mutating, and nothing restarts or continues its stage under another executor silently. The controller
  assembles from live evidence the progress, the candidate state (local changes, commits, pushed head, PR) and the
  consumed slot, and adjudicates under 24.8 unchanged: the slot stays consumed; the same execution resuming in its
  retained context, under the same serious prompt and model id once its provider recovers, is one execution that
  waited and consumes no new slot, re-proving local and live state before its next mutation; any other continuation —
  a fresh-context restart or another executor — is a new specialist execution that starts from a controller-named
  exact state and counts against the same hard maximum. The controller records which later stages the remaining
  budget still admits; it never creates a slot, never uses the fifth slot outside its 24.8 purpose, never grants a
  second repair and never lets an unfinished stage bypass a protected gate. When no continuation fits, the stage waits
  for its own execution to resume or the candidate stops with proof. `OPERATIONAL_INTERRUPTION` (24.8) applies the
  same rules to every specialist execution, audits and qualifications included.

### 24.4 Independent audit (GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1), protected Class C, complete blocker collection and Sol usage efficiency

- `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1` — the `ACTIVE_SOL_AUDITOR` (24.3; the id resolved by 24.7
  `SOL_ROUTE_STATE_RESOLUTION`) is the PRIMARY independent auditor of
  every serious crypto_core PR candidate; requested effort `Ultra` (recorded literally, 24.3; mandatory for
  protected audits, 24.12) at `STANDARD` speed. An audit under this rule is: fresh context; pinned to the exact
  head; READ_ONLY with zero repository or GitHub mutation; runtime-admitted (24.12 `PATH_A`, or `PATH_B` where
  expressly authorized) before any substantive audit work; performed by a lane — and an executing model — that neither implemented nor repaired any part of this
  candidate lifecycle; exhaustive over the declared semantic boundary (`COMPLETE_BLOCKER_COLLECTION`);
  materiality-aware (`AUDIT_MATERIALITY_BOUNDARY_V1`); evidence-backed; and run under
  `SOL_AUDIT_USAGE_EFFICIENCY_V1`, which removes duplicated work and never audit scope. The one whole-contract
  re-audit after the one consolidated repair meets the same standard.
- `PROTECTED_UNIFIED_AUDIT` — a candidate is protected when it touches any protected trigger: digest
  recomputation/consumption, expected-digest anchors, canonical serialization, reseal/provenance,
  mutable/stateful/TOCTOU behavior, denominator or record-set integrity, duplicate/replay defense, Decimal/Fraction
  financial arithmetic, governance thresholds, fail-closed trust transitions, READY/ADMITTED/ACCEPTED transitions,
  SM-5/SM-6, Stage-4 completion, machine-time provenance, readiness/Deribit, connector-ready transitions,
  live/private API, orders/order routing, scheduler/auto-loop, shadow/live, capital mutation, edge/profitability
  claims, complex CodeQL/security, or a change to this control plane and its adapters. Uncertainty whether a
  trigger applies counts as protected. For a protected candidate ONE GPT-6.1 Sol audit execution satisfies
  together the independent audit, complete blocker collection, the protected Class-C cross-contract audit and the
  terminal audit decision, provided every requirement of `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1` holds; the one
  whole-contract GPT-6.1 Sol re-audit does the same for a repaired head. The same exact head is never audited twice
  merely because ordinary and protected review were once separate lanes. Protected work is audited by GPT-6.1 Sol
  alone: when GPT-6.1 Sol is unavailable, quota-blocked, cannot be requested at `Ultra` or stops on runtime proof,
  the protected gate WAITS on the frozen exact head (`CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE`); GPT-6 Astra, Codex
  GPT-5.6 Sol, Claude Opus 5.5, the ChatGPT controller, ChatGPT Work and any self-review never satisfy a protected
  audit, and none silently substitutes for it.
- `NON_PROTECTED_AUDIT_FALLBACK` — for a candidate with NO protected trigger only. When GPT-6.1 Sol cannot legally
  perform the audit for a reason recorded in the task handoff (never as durable model state) —
  `GPT61_SOL_UNAVAILABLE`, `GPT61_SOL_QUOTA_BLOCKED` or `GPT61_SOL_RUNTIME_PROOF_STOPPED_BEFORE_SUBSTANTIVE_AUDIT` —
  the ChatGPT controller may perform it, as the last resilience mechanism and never as default routing, provided
  it (including through ChatGPT Work) neither implemented nor repaired the candidate. A fallback audit meets every
  requirement of `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1` except the lane, records its fallback reason, and never
  satisfies a protected audit. GPT-6 Astra and Codex GPT-5.6 Sol are no fallback lane. No independent eligible
  reviewer → `STOP_WITH_PROOF`; no other reviewer lane is added.
- `NO_SELF_AUDIT` — independence eligibility is decided BEFORE operational availability, for the audit and the
  re-audit alike: a lane that implemented or repaired any part of this candidate lifecycle is ineligible, and so is
  any execution on the same model id (`MODEL_ACTUAL`). Implementation or repair by ChatGPT Work counts as the
  ChatGPT controller's own and as its executing model's own, so a ChatGPT Work or Codex execution on
  `gpt-6.1-sol` that implemented or repaired any part of a candidate makes GPT-6.1 Sol ineligible to audit it and,
  for protected work, leaves no eligible auditor (`STOP_WITH_PROOF`). GPT-6.1 Sol is READ_ONLY in this workflow
  and is routed to no implementation or repair (24.3). No model audits its own implementation or repair; a Claude
  implementer's self-review, like any same-model review of its own work, is `SELF_AUDIT_ONLY_NOT_INDEPENDENT` and
  satisfies no audit. A Codex executor stage under `CODEX_EXECUTOR_QUOTA_FALLBACK_V1` (24.3) counts as its executing
  model id's own on every host, and no Sol-family id ever runs one, so that route never consumes GPT-6.1 Sol's
  independence.
- `INDEPENDENCE_ASSURANCE` — independence is judged on the actual identities of every implementing and repairing
  execution, which are always execution-proven (24.12 `PATH_A`; `PATH_B` never admits a writer). An audit admitted
  on `PATH_A` positively proves model-level separation. An audit admitted on `PATH_B` establishes process
  independence (a fresh READ_ONLY context with no writer role or authorship) and selected-model separation; actual
  model-level separation is NOT positively proven, and an undisclosed provider fallback cannot be conclusively
  excluded. The controller's admission decision and the audit handoff record that residual limitation; no report
  claims assurance equivalent to `PATH_A`.
- `RUNTIME_PROOF_BEFORE_AUDIT` — an auditor establishes runtime admission (24.12) before any substantive audit work.
  A failed admission stops before auditing, delivers no verdict and consumes no specialist slot (24.8). An audit that
  did substantive work and is then found runtime-ineligible (a known wrong model, a prohibited fallback, required
  thinking `UNKNOWN` or `DISABLED`, an unsupported selection or a missing governing authority) is procedurally
  invalid: it consumed its slot, delivers no usable verdict, and only the 24.8 replacement rule applies.
- `COMPLETE_BLOCKER_COLLECTION` — an audit never stops at the first defect. It returns the COMPLETE current
  material P1/P2 set of the declared semantic contract in one exhaustive pass, to the practical limit of that
  bounded contract, each finding with exact evidence. One-finding-at-a-time auditing, and the loop finding →
  repair → finding → repair, are forbidden: one exhaustive audit, one consolidated root-cause repair, one
  whole-contract re-audit (24.8). A verdict without complete blocker collection is procedurally invalid (24.8) and
  can neither accept a candidate nor open the repair.
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
- `SOL_AUDIT_USAGE_EFFICIENCY_V1` — GPT-6.1 Sol allowance buys independent judgment, never mechanical work: the
  controller and Claude absorb every task that needs no independence. Audit completeness is never traded for
  allowance — an audit is never narrowed, shortened or fragmented to save usage — and a prompt is never inflated to
  consume it.
  - `SOL_AUDIT_PREFLIGHT_PACKET` — before every Sol audit or re-audit the controller supplies, as governance (24.8):
    the applicable external decision and approval evidence under `APPROVAL_SOURCE_PACKET` (24.5),
    the PR number, base SHA, head SHA, head tree when known, changed files, the semantic boundary, the
    required-check snapshot, the review-thread snapshot, the known P1/P2 identities and, for a re-audit, the old
    head and the previous audit's blocker identities. These values travel inside the canonical serious-prompt
    fields (24.6) — the PR, SHAs, tree, changed files and check and thread snapshots in `STATE_PIN`, the boundary in
    `SEMANTIC_BOUNDARY`, the known and previous blocker identities in `BLOCKER_INVENTORY` — never as a separate,
    reordered block. The auditor re-proves its exact head, changed scope and required checks once; it does not poll
    CI, rediscover the PR, enumerate unrelated history, replay chat history or reread every repository document.
    A stale base/head or missing, pending or failed required exact-head CI/CodeQL returns to the controller
    before substantive audit. The only exception is a first audit admitted in `REPAIR_ONLY` mode under
    `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` below; nothing admits a stale head or a pending, missing, stale,
    infrastructure-only or unclassified check, and nothing admits a failed check to a re-audit. After adoption the
    packet carries the resolved route state and its record origin (24.7) in `MODEL_RUNTIME_PROOF`. For a `PATH_B`
    admission the packet also carries the attributable human selection attestation and the controller's admission
    decision (24.12). A verdict missing the complete material P1/P2 inventory cannot support
    acceptance or dispatch of the one consolidated repair.
  - Read scope — the whole declared semantic contract, approached from the exact changed files, their direct
    authority, their immediate load-bearing dependencies and the exact-head tests and CI, with targeted
    adversarial probes for material trust questions. It widens only where a concrete material concern requires it,
    never by a broad repository scan without a concrete material audit question.
  - Evidence reuse — the auditor does not rerun the canonical full suite merely to duplicate it when the
    implementer ran it after the final mutation, exact-head required CI is green and no contradiction exists, and
    it does not repeat an accepted expensive probe whose exact code and authority are unchanged. Scratch or
    adversarial probes reproduce independently wherever a material trust question needs it; a contradiction, a
    missing or failed gate, or a trust question the evidence does not settle is investigated. Reuse is never test
    weakening.
  - Re-audit — the one re-audit stays whole-contract, never repaired-lines-only. It inspects
    OLD_HEAD..REPAIRED_HEAD first, maps the change to the affected invariants, proves the other load-bearing
    surfaces unchanged, re-covers the entire contract through source, test and CI evidence (reusing accepted
    evidence only where exact bytes and authority are unchanged), reruns adversarial probes mainly on repaired or
    newly affected trust paths, investigates any concrete new concern wherever it lies, and collects the COMPLETE
    current material P1/P2 set. Any material P1/P2 after the one repair still triggers `FIXED_POINT_STOP`.
  - Once `FINITE_AUDIT_RULE` is satisfied, the auditor adds no P3 or theoretical-hardening work.
  - Effort, speed, subagents and usage telemetry follow 24.12, and the compact audit handoff 24.6. The objective is
    several substantive Sol audits per allowance window through removed duplication alone; no prompt count, quota
    size, credit amount or price is doctrine (24.11).
- `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` — closes the first-audit deadlock in which a failed required check blocked the
  only audit that could open the one consolidated repair. It waives no check and adds no stage, audit, repair or
  slot. An eligible terminal candidate-caused required-check failure may admit the FIRST independent whole-contract
  audit in `REPAIR_ONLY` mode; never a re-audit.
  - Failure classes, decided by the controller on source-grounded evidence and confirmed or rejected by the auditor:
    `CANDIDATE_SEMANTIC_DEFECT` — a genuine supported-path defect, classified P1 or P2 under
    `AUDIT_MATERIALITY_BOUNDARY_V1`; `CI_GATE_BLOCKER` — an independently confirmed actionable CI-only problem that
    requires correction (for example a reproducible static-analysis false positive with a feasible authorized
    correction), carrying no manufactured semantic severity; `INFRASTRUCTURE_FAILURE` — a service or status problem
    for controller-managed recovery under section 3 and the applicable action authorization, never a candidate
    repair; `UNCONFIRMED_OR_UNCLASSIFIED` — anything else, which opens nothing. A genuine security issue is never
    classified as a harmless false positive.
  - `ELIGIBILITY` — every condition holds on fresh evidence, or the audit is not dispatched; unknown, contradictory
    or stale evidence stops:
    1. the candidate lifecycle is governed by this adopted policy;
    2. the implementation handoff (24.6) is complete and the head is frozen — no pre-audit patch;
    3. the controller has proven the exact base, head and tree, the required-check configuration, each required run's
       identity and attempt, the relevant code-scanning analysis revision and the failure provenance;
    4. every required check is terminal — none pending, queued, missing, stale or unclassified;
    5. every failing required check is specifically classified, and none is `INFRASTRUCTURE_FAILURE` or
       `UNCONFIRMED_OR_UNCLASSIFIED`;
    6. each failure has source-grounded evidence of a candidate-caused defect or a reproducible static-analysis false
       positive, with a feasible correction inside the authorized files and semantic boundary;
    7. the writer's applicable local validation (24.5) for that exact tree is complete, and no known required local
       validation failure was published as a compliant implementation;
    8. no unresolved security issue is classified as a harmless false positive, no unrelated legacy failure is
       attributed to the candidate, and the correction needs no unsupported scope expansion;
    9. an eligible independent whole-contract auditor exists under 24.3, 24.4 and 24.12, exactly as for an ordinary
       audit (protected work: the `ACTIVE_SOL_AUDITOR` at literal `Ultra` alone);
    10. the controller records the eligibility decision and the evidence for 1–9 in the `SOL_AUDIT_PREFLIGHT_PACKET`
        before dispatch.
  - `REPAIR_ONLY` audit mode — the audit meets every requirement of `GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1` and covers
    the ENTIRE declared contract under `COMPLETE_BLOCKER_COLLECTION`; it is never a CI-only review. The auditor first
    re-verifies eligibility and may reject the controller's classification. It returns the complete material P1/P2
    inventory and, separately, `CI_GATE_BLOCKERS` (each confirmed failing check or alert by identity, with evidence
    and the correction it admits). A candidate-caused failure that is a genuine defect is reported as the P1/P2 it
    is, never as a `CI_GATE_BLOCKER`. `REPAIR_ONLY` never produces `ACCEPT` or merge readiness and never dismisses an
    alert, suppresses a check, weakens a test, waives CI or requests a dummy repair.
  - Repair opening — a valid complete P1/P2 inventory with at least one P1/P2, or at least one confirmed
    `CI_GATE_BLOCKER` even with an empty P1/P2 inventory, opens the one consolidated repair (24.8) with the applicable
    action authorization. When no meaningful authorized repair remains, the candidate stops for controller terminal
    disposition (24.8).
  - Changed check state — eligibility binds the exact head, run identities and attempts and analysis revision
    recorded at preflight. A change before substantive audit work invalidates the preflight, not the budget: the
    controller re-preflights (a check now terminal green restores the ordinary path). A change after substantive
    work never converts `REPAIR_ONLY` into `ACCEPT`, never creates a free additional audit and never restores an
    allowance. Head movement stays governed by `VERDICTS_BIND_EXACT_HEAD` (24.8).
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

A merge requires, each freshly proven on the exact head: the independent audit clean under 24.4 — the GPT-6.1
Sol audit, which for protected work is also the protected audit, or for non-protected work only a recorded
`NON_PROTECTED_AUDIT_FALLBACK` audit — after the one whole-contract re-audit when a repair ran; no current valid
material P1/P2; exact-head CI terminal green, including the required tests and CodeQL; controller live-state
proof; and the human's explicit authorization naming the PR, the exact head and the merge command. Then standard merge, post-merge verification (section 12) and the next action. These closeout
steps are controller governance and consume no specialist prompt (24.8).

`HANDOFF_OWNERSHIP` — responsibilities do not overlap:
- WRITER (Claude Opus 5.5, or the routed Codex executor): the whole-stage implementation or repair, its self-review
  (`SELF_AUDIT_ONLY_NOT_INDEPENDENT`), the stage's local validation, the authorized publication (scoped commit,
  normal push and, for an implementation, the one PR) and the exact-head handoff with clean isolated checkout proof.
  Writer mutation ends at that publication handoff: the handoff grants no further mutation, and the writer does no
  terminal CI polling. A later candidate mutation needs a new controller-routed stage.
- CONTROLLER: architecture, authority, dependency closure, live GitHub state, CI and CodeQL polling to terminal,
  failure classification (24.4), review and thread adjudication, the audit preflight, routing, authorized closeout
  and remote post-merge verification.
- AUDITOR: the independent complete semantic review, supported-path material adversarial probes and the complete
  blocker inventory (24.4). It re-proves exact head, scope and checks once — no routine polling and no unrelated
  repository archaeology.
- Attributable final-tree validation and unchanged accepted evidence are reused where 24.4 permits; revalidation
  follows a change of relevant bytes, authority, environment assumptions or a material trust question. No
  duplicate full-suite run exists solely for audit formality, and reuse never reduces independent verification.

The writer proves its local checkout, changed scope, validation, commit/tree and clean status at handoff.
The controller supplies the live GitHub state, polls CI and CodeQL to terminal, collects reviews and threads,
and refreshes the exact-head merge preflight (section 7). After the authorized mechanical standard merge,
it verifies the merged PR, the merge commit's ordered parents against the authorized base/head and its
tree against the accepted head tree at that base. Verify the resulting main SHA/tree, required post-merge
checks on that SHA, source-branch preservation where required, and open-PR count. Incomplete proof keeps
closeout pending. Use the existing GitHub connector or `gh` for the exact evidence, including pagination or
check runs the available connector view omits. Bind an authorized merge to the expected head. Ready-for-review,
merge and administrative closure (24.8 `ADMINISTRATIVE_CLOSURE`) each require authority for that action; after a
closure the controller verifies the remote closed-unmerged state, unchanged main and source-branch preservation. A tool's Always Allow setting grants no publication,
merge, capital or governance authority.

Keep local validation and checkout hygiene attributable to the executing host. For a Markdown-only stage,
the local ladder in sections 5–6 uses exact changed paths, `git diff --check`, applicable existing setup
checks and semantic checks of touched rules, references and negative cases. Product implementation and
repair keep the full validation obligations in sections 5–6. Required remote CI and CodeQL still apply. A writer may diagnose a named failure
from the controller's evidence. The auditor independently re-proves its head, scope and checks once (24.4).

**`APPROVAL_SOURCE_PACKET`.** When a task depends on an external human decision, the controller puts the
complete exact decision text or an authenticated, revision-bound source accessible to the recipient in
`STATE_PIN`. Include revision, scope, source type and provenance, the direct approval statement, attributable
human actor and the exact scope approved. Give observation and approval times when known. Mark unavailable
times, signatures and historical digests `UNKNOWN`. An unknown optional historical detail does not invalidate
an otherwise attributable decision unless that detail is required for the gate. In `GITHUB_AUTHORIZATION`
state only the actions actually granted. A methodology approval grants no publication or merge permission.

Keep the human statement distinct from controller interpretation, attributed host observations, fresh runtime
proof, GitHub/CI evidence, accepted repository authority and implementer claims. Three human operational statements
are evidence classes of their own, never governance approvals and never runtime telemetry: a human availability
statement (24.3 gate A), a human selection attestation (24.12 `PATH_B`) and a human confirmation of the governance
decision state (24.7 `SOL_ROUTE_STATE_RESOLUTION`). Each records its actor, scope, applicable host and model (or the
route state it confirms), and stage or session binding, and is never relabelled as execution evidence. Carry the
same source into the existing handoff and the independent audit preflight (24.4). A candidate may cite its
authority but cannot supply that authority by asserting its own adoption. If the original decision or direct
approval is missing, inaccessible, superseded or inconsistent with the requested scope, stop before dependent
mutation or substantive audit. The controller resolves the source and revision before resumption.

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

`PROMPT_COMPACTION_V1` — compaction optimizes within `SERIOUS_PROMPT_COMPILER`, never against it. Stable policy
lives in this repository, and a serious prompt references it instead of reproducing it. The twelve top-level
fields keep their canonical order exactly — `STATE_PIN` third, `BLOCKER_INVENTORY` seventh — and every required
dynamic value stays inside its own field: PR, SHAs, tree, changed files and check and thread snapshots in
`STATE_PIN`, runtime requests in `MODEL_RUNTIME_PROOF`, blocker identities in `BLOCKER_INVENTORY`. Each field
carries only the task-specific material it needs: large volatile logs (failure tails only), repeated history,
redundant prose and non-schema material are omitted or summarized, and genuinely needed supplemental volatile
material sits compactly inside the appropriate field or as explicitly subordinate material, never reordering the
top-level fields. Cache friendliness comes from stable doctrine and template references and minimal repeated
prose, never from relocating a required field. No prompt or report claims a cache hit or a measured saving;
compaction never drops a stop condition, invariant, permission boundary or validation gate, and compact
presentation never permits omission of mandatory `AGENT_OS_HANDOFF_V1` fields.

`CONTROLLER_PROMPT_SAFETY_AND_SCOPE_V1` — the controller compiles clear, legitimate engineering tasks with explicit
scope, authority, expected result, relevant evidence and supported operations, using stable authority references
plus the task-specific scope, state, blockers, permissions, acceptance criteria and validation; it does not preload
irrelevant history or demand broad repeated source scans. Prompts respect every platform and system safeguard and
tool restriction; they never request hidden reasoning content, credentials, unrelated session data or unnecessary
sensitive records, and they ask only for minimal supported diagnostic metadata. When a platform restriction
withholds a response or interrupts work, the affected operation stops; only safely reportable status, repository
mutation state, completed validation and available handoff evidence are collected; the execution history and
consumed budget are preserved (24.8 `OPERATIONAL_INTERRUPTION`); incomplete work is marked `INCOMPLETE`; withheld
content is never reconstructed; the restriction is never circumvented through obfuscation, repeated rephrasing or
alternate models; and work resumes only through a supported authorized path consistent with the restriction.
Platform restriction, quota exhaustion, repository governance failure and an actual engineering defect are
recorded as distinct causes. No prompt is claimed to guarantee the absence of platform intervention.

`AGENT_OS_HANDOFF_V1` — every serious task ends with one handoff: result; the runtime-proof block (24.12);
setup fields (24.7); state proof (base, branch, head, PR, open PRs); files changed; validation and CI with exact
results; review threads; P1/P2/P3 findings or the self-audit label; for an audit, the auditing lane, the
protected-trigger classification, and whether it ran as PRIMARY (GPT-6.1 Sol) or as the recorded
`NON_PROTECTED_AUDIT_FALLBACK` with its reason (24.4); for an implementation or repair routed under
`CODEX_EXECUTOR_QUOTA_FALLBACK_V1` (24.3), the executor route, the fallback reason with its Claude-unavailability
evidence, the attributable A–G controller record, the pre-mutation host/runtime/local proof and every executing model id of the candidate; the specialist prompt count of
the PR lifecycle (24.8), with any invalid or interrupted execution and the remaining legal stages; any
`EFFORT_MISMATCH_WAIVER` (24.12) with its binding, the controller's sufficiency judgement and the true actual; for a
`PATH_B` admission, the residual assurance limitation (24.4); after adoption, in every controller-accepted handoff,
the `SOL_ROUTE_STATE` record (24.7); and exactly one next safe action. Missing facts are `UNKNOWN`, never
invented; failure tails only; a handoff never authorizes mutation. Runtime fields that do not apply to the stage
are `N/A`; optional unavailable telemetry is `UNKNOWN`.

`COMPACT_AUDIT_HANDOFF` — an audit's handoff is compact by default: `VERDICT`, `AUDIT_MODE` (`ORDINARY`, or
`REPAIR_ONLY` with the auditor's own eligibility finding, 24.4), `RUNTIME_PROOF` (including `RUNTIME_ELIGIBILITY`
and, for `PATH_B`, the residual assurance limitation), `HEAD_SHA`, `HEAD_TREE`, `CI`, `P1_BLOCKERS`, `P2_BLOCKERS`,
`CI_GATE_BLOCKERS` (`REPAIR_ONLY` only; otherwise `N/A`), `P3_NOTES`, `COMPLETE_BLOCKER_COLLECTION_STATUS`,
`MERGE_READINESS` and `NEXT_SAFE_ACTION`, together with the auditing lane, the protected-trigger classification,
the specialist prompt count and, for a Sol audit, the speed and usage telemetry of 24.12. Detailed narrative is
added only for a material P1/P2, an authority conflict, a runtime or procedural stop, or a novel trust-boundary
adjudication; successful-test narratives are omitted.

### 24.7 SETUP_LOAD_CONTRACT_V1, FRESH_CHAT_BOOTSTRAP and LIVE_STATE_PRECEDENCE

`FRESH_CHAT_BOOTSTRAP` — a new chat or session without an accepted packet reads, in order:

1. `AGENTS.md`;
2. this section (`docs/crypto_core/agent_workflow.md` section 24);
3. the relevant host adapter — `CLAUDE.md` and `.claude/skills/crypto-core-token-efficient-loop/SKILL.md` for
   Claude, `.codex/skills/crypto-core-max-safe/SKILL.md` for a Codex audit, and
   `.codex/skills/crypto-core-executor-fallback/SKILL.md` for a Codex executor stage (24.3);
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

`EFFECTIVE_ROUTE_RECOVERY` — the governing authority is this section as accepted on main; the external ChatGPT
Project Instructions and the adapters apply it and never redefine it. A fresh context reconstructs the effective
model routes from that authority plus attributable accepted evidence; the `ACTIVE_SOL_AUDITOR` (24.3) is resolved
only by `SOL_ROUTE_STATE_RESOLUTION` below. No local flag, memory note or new registry records a route. A conflict
between Project Instructions, an adapter and this section is resolved in favour of this section and reported as
drift. Context compaction or loss is recovered the same way and never resets a lifecycle count or authority.

`SOL_ROUTE_STATE_RESOLUTION` — the one procedure that resolves the `ACTIVE_SOL_AUDITOR` after canonical adoption. The
controller applies it; adapters, guides, prompts and the Project Instructions carry its result and never resolve the
route themselves. Git and GitHub prove repository state only (the accepted policy revision, branches, PRs, checks).
An activation decision is external to them, so the same repository state follows both a successor that was never
activated and an activation whose evidence was lost; repository evidence, `LIVE_STATE_PRECEDENCE` included, never
stands in for a route-state record.
- Record. Every controller-accepted handoff after adoption carries `SOL_ROUTE_STATE`: the state, its origin and the
  accepted policy revision (an unresolved state is carried as `ACTIVATION_STATE_UNKNOWN` with its reason). The
  `PRE_ACTIVATION` origin is the fresh-context verification of the adopted policy (24.14
  `GPT62_SOL_SUCCESSOR_ACTIVATION` step 4), when no activation can exist yet because qualification follows it, or a
  human confirmation under Recovery below. The `POST_ACTIVATION` origin is the complete activation record (24.14),
  which names the pre-activation record it supersedes. Each later accepted handoff carries the entry forward with
  its origin until an activation record supersedes it. The Project Instructions name the same effective state and
  identify its record (24.14) without granting any authority.
- Currentness. A record is current only when the controller establishes all of: (1) it comes from the designated
  current accepted state — the controller's own retained accepted state, the handoff that the human or the previous
  controller supplies with the task or new chat as current, or the record that handoff or the Project Instructions
  identify — not merely from an accessible older record; (2) its origin is present and every later accepted handoff
  in hand carries the same state; (3) the canonical policy on main still defines this successor route (unrelated
  later commits leave it applicable; a later adopted role change governs under its own authority); (4) the Project
  Instructions name the same effective state; and (5) no conflicting record is known, and no activation decision
  whose 24.14 publication (step 8) is unfinished. A timestamp, a recent conversation, a matching Git SHA or the
  absence of a newer record never establishes currentness alone.
- States. `PRE_ACTIVATION_VERIFIED`: a current `PRE_ACTIVATION` record. `POST_ACTIVATION_VERIFIED`: a current
  `POST_ACTIVATION` record whose complete activation record is accessible, whose 24.14 publication (step 8) is
  complete and whose effectiveness is verified from a fresh controller context (24.14 step 9; the first fresh context
  to resolve it performs and records that verification). Anything else is `ACTIVATION_STATE_UNKNOWN`, recorded with
  its reason: `MISSING` (no record), `STALE` (currentness not established, or superseded), `INACCESSIBLE` (a
  referenced record cannot be retrieved), `CONTRADICTORY` (conflicting records, or Project Instructions or an adapter
  inconsistent with the accepted record) or `PUBLICATION_INCOMPLETE` (an activation decision whose 24.14 publication
  or fresh-context verification is unfinished). A missing activation record is never evidence of `PRE_ACTIVATION`,
  and a missing pre-activation record is never evidence of activation.
- Reuse. A current record is reused across stages, hosts, quota resets and context compaction without new human
  confirmation while it stays uncontradicted; it is re-established only after a fresh or lost controller context, a
  change of 24.3 or 24.14 on main, a known activation decision or a conflict.
- Recovery. For `ACTIVATION_STATE_UNKNOWN` the controller makes one bounded recovery attempt: it retrieves the
  designated record through the accepted handoff chain or the continuity pointer that the latest handoff or the
  Project Instructions identify and, only where that cannot establish currentness or a positive pre-activation
  state, obtains one focused current human confirmation of the governance decision state (24.5). That confirmation
  can establish which record is current and, consistent with the Project Instructions and canonical policy, that no
  activation decision was made — it is then the origin of `PRE_ACTIVATION_VERIFIED`. It never supplies qualification
  evidence, an activation record, execution identity or backend independence, so it never establishes
  `POST_ACTIVATION_VERIFIED` and never overrides a complete accepted activation record. For `PUBLICATION_INCOMPLETE`
  the recovery is completing 24.14 steps 8 and 9 of the recorded decision. While the state stays unresolved, every
  stage that needs the `ACTIVE_SOL_AUDITOR` — an audit, re-audit or protected gate, and 24.14 steps 5–7 — holds,
  and it is never a `NON_PROTECTED_AUDIT_FALLBACK` reason (24.4). A writer stage is not held, because gate G
  independence (24.3) holds for every Sol id, but its audit waits.
- Supersession. A pre-activation statement that an activation record supersedes is stale and never authorizes
  incumbent dispatch. A verified post-activation state is never reverted by a stale or inconsistent pre-activation
  statement: the conflict is resolved on evidence or the dependent stage holds. Nothing here creates a deactivation
  or reverse transition; an unrelated retirement or role change follows its own canonical authority (24.3, 24.13).
- Dispatch. An audit prompt carries the resolved state and its record origin in `MODEL_RUNTIME_PROOF` (24.4, 24.6),
  compiled at dispatch; a prompt compiled before an activation took effect is never dispatched after it. An agent
  never resolves the route itself: a prompt without that basis, or one whose basis the agent can see is superseded
  or contradicted, returns to the controller. No resolution changes the model of a stage already started.

### 24.8 LOW_PROMPT_MAXIMUM_WORK_POLICY — PR sizing, prompt budget and the fixed-point lifecycle

`PR_SIZING_AUTHORITY=SEMANTIC_CLOSURE_ONLY`; default `LARGEST_SAFE_SEMANTIC_CLOSURE`. One PR closes one
coherent semantic contract together with its dependency closure, negative cases, tests, the docs/provenance
genuinely required, and its validation. There is no file-count, LOC or module-count ceiling and no preference
for small PRs. Split only for: unrelated contracts; different authorization; a protected boundary that cannot
be audited together; inability to validate the whole result; or a real context/correctness risk.

`MEANINGFUL_PROMPT` — a SPECIALIST model execution that materially implements, independently audits, repairs,
or re-audits the whole contract (24.4). Only specialist executions consume the
prompt budget. An execution that stops on runtime, state or authority grounds (24.12) before any substantive work
consumed no slot; an execution that did substantive work consumed its slot whatever its verdict or validity. No
relabelling, splitting, re-routing or change of executor model or provider resets the count, and no historical
budget is ever reset or transferred.

`CONTROLLER_GOVERNANCE_OPERATIONS` never consume the specialist budget: live repository/GitHub state proof; CI,
status and check reads; the `SOL_AUDIT_PREFLIGHT_PACKET` (24.4); adjudication of executor and auditor evidence;
contradiction synthesis; merge-readiness judgement; asking the human for exact-head merge authorization; an
authorized mechanical merge; post-merge verification; and fresh-chat acceptance. A governance operation never
contains or dispatches an implementation, repair or audit execution, and specialist work relabelled as
"controller closeout" is still specialist work that counts. A `NON_PROTECTED_AUDIT_FALLBACK` audit by the
controller (24.4) is specialist work: it fills, and consumes, an audit slot.

`PROMPT_BUDGET` — the target is the FEWEST specialist executions the lifecycle needs; the hard maximum is **5**
per PR lifecycle, an emergency ceiling only, and there is no specialist prompt 6. No meaningless prompt is ever
created to reach a count, and no audit is fragmented across executions.

- Clean (protected or not): 1 `IMPLEMENTATION` (Claude Opus 5.5) → 2 `INDEPENDENT_AUDIT` (GPT-6.1 Sol, 24.4; for
  protected work the one unified audit) → controller governance closeout. Target: **2** specialist prompts.
- Repaired: 1 `IMPLEMENTATION` (Claude Opus 5.5) → 2 `INDEPENDENT_AUDIT` (GPT-6.1 Sol; the complete material
  P1/P2 set) → 3 `ONE_CONSOLIDATED_REPAIR` (Claude Opus 5.5) → 4 `ONE_WHOLE_CONTRACT_REAUDIT` (GPT-6.1 Sol) →
  controller governance closeout. Target: **4** specialist prompts. Claude and GPT-6.1 Sol specialist work stays
  symmetric: one execution each for a clean candidate, two each for a repaired one; for non-protected work only,
  a recorded 24.4 fallback audit takes the Sol slot; and a recorded 24.3 Codex executor stage
  (`CODEX_EXECUTOR_QUOTA_FALLBACK_V1`) takes the Claude slot of the implementation or repair stage it replaces, never
  an extra slot.
- The fifth slot exists only for one replacement audit or re-audit execution when the ChatGPT controller rejects
  an executed one as procedurally invalid (wrong head, not fresh context, lost required independence, repository or
  GitHub mutation or other unauthorized mutation, incomplete blocker collection, or substantive work while
  runtime-ineligible, 24.4), with the reason recorded — never because of its findings or verdict. It never
  authorizes a second repair, a second valid re-audit of the same repaired head, a writing continuation or a sixth
  prompt. A procedurally invalid replacement authorizes no further replacement: the candidate then has no legal
  acceptance path and goes to controller terminal disposition.
- `CONTINUATION_BUDGET_CHECK` — before routing any continuation or replacement, the controller counts the consumed
  slots and the legitimate stages still required and records whether the remaining budget admits them. Slots 1–4
  serve ordinary stages and the fifth only the replacement above, so it is never counted as available for an
  ordinary stage. A writing continuation is admissible only when at least one ordinary slot then remains for the
  required independent audit, and the
  controller records whether the repaired path (repair plus re-audit) still fits; when it no longer fits, a first
  audit with any material P1/P2 or `CI_GATE_BLOCKER` leads to `REJECT/FREEZE`. The protected audit opportunity is
  never consumed merely to continue writing.
- After the final specialist prompt, controller governance closeout (24.5) completes the lifecycle outside the
  count. There is no specialist prompt 6.
- Waiting consumes nothing: CI still pending after the final audit, a delayed human authorization, post-merge
  verification and fresh-chat acceptance are governance. `VERDICTS_BIND_EXACT_HEAD` — every audit verdict and CI
  result binds the exact head it judged. After the implementation, only the one consolidated repair may move the
  head, and the section-3 authorized empty re-trigger commit keeps the verdicts only when its tree is identical, proven
  by tree id, and required CI is refreshed on the new head — stale CI success is never carried forward; any other
  head movement voids the verdicts bound to the old head and stops the candidate (`REJECT/FREEZE`).

`OPERATIONAL_INTERRUPTION` — for any specialist execution (implementation, repair, audit, re-audit, qualification),
the controller distinguishes, from live evidence:
- BEFORE SUBSTANCE: correct the permitted operational prerequisite (runtime, state, authority, checkout); no slot is
  consumed.
- SAME EXECUTION RESUMES in its retained context under the same prompt and model id: re-prove local and live state
  and authority before the next action; it keeps its one existing slot.
- FRESH-CONTEXT RESTART OR CHANGED EXECUTOR: a new execution, which requires an explicit controller adjudication of
  state, ownership and budget (`CONTINUATION_BUDGET_CHECK`); an interrupted audit that cannot resume in its retained
  context is an incomplete blocker collection, so only the fifth-slot replacement rule can follow it.
- UNAVAILABLE REQUIRED CAPACITY with no authorized continuation: hold on the exact state, or terminal stop.

A platform restriction (24.6 `CONTROLLER_PROMPT_SAFETY_AND_SCOPE_V1`) is handled the same way with the work marked
`INCOMPLETE`. A model or provider change never resets history, never creates a second repair and never repurposes
the fifth slot. A connector or tool interruption that loses no specialist work is governance and consumes nothing.

`ONE_CONSOLIDATED_REPAIR` — at most one repair per candidate lifecycle. It repairs the COMPLETE valid blocker
inventory — every material P1/P2 and every independently confirmed `CI_GATE_BLOCKER` (24.4) — by root cause in one
change, including the affected consumers and regressions, never only the reported lines. No pre-audit patch, no
micro-patching, no finding-by-finding repair, no repair → audit → repair chains, and never a second repair.

`ONE_WHOLE_CONTRACT_REAUDIT` — after that repair, exactly one fresh re-audit of the repaired exact head to the
same 24.4 standard (GPT-6.1 Sol; for protected work no other lane): READ_ONLY and covering the whole semantic
contract, never only the repaired lines. Its delta-aware method is `SOL_AUDIT_USAGE_EFFICIENCY_V1` (24.4). Every
required CI and CodeQL check on the repaired exact head is terminal green before substantive re-audit;
`PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` never applies to a re-audit. A pending check waits; a required check that cannot
turn terminal green on that exact head without a further candidate mutation leaves the candidate `REJECT/FREEZE`.

`FIXED_POINT_STOP` — the first independent audit's complete material P1/P2 set opens the one consolidated repair;
under `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` (24.4) at least one independently confirmed `CI_GATE_BLOCKER` opens it
too, even with an empty P1/P2 set. A `REPAIR_ONLY` first audit never yields `ACCEPT`, and an unconfirmed CI failure
opens nothing. After that repair and its one whole-contract re-audit: material P1/P2 = NONE → the candidate proceeds to controller
governance closeout (24.5); any genuine material P1/P2 remaining → the candidate is `REJECT/FREEZE`, receives no
further mutation, and closes without merge. P3 / `OUT_OF_SCOPE` / theoretical-hardening observations NEVER trigger
`FIXED_POINT_STOP` and never block merge. Before freezing a candidate on a disputed finding, the ChatGPT controller
adjudicates its severity against the declared semantic boundary and `AUDIT_MATERIALITY_BOUNDARY_V1` with evidence;
a candidate is never frozen merely because an auditor can imagine additional robustness, and adjudication never
downgrades a supported-path correctness or safety defect for throughput. The decision is ACCEPT or REJECT, never
another loop.

`ROOT_CAUSE_ESCAPE` — `REJECT/FREEZE` stops patching the failed candidate; it does not abandon the underlying
product or setup problem. A future attempt requires an explicit new ChatGPT controller `TASK_INTENT=ARCHITECTURE`
decision that: reconstructs the root cause; inherits every blocker identity; changes the architecture or
boundary rather than renaming the same repair; defines a new bounded semantic closure; starts from accepted
main; states the new lifecycle and its budget treatment explicitly while every historical count, finding, branch,
commit and repair allowance stays historical and unchanged; and prohibits rejected candidate history (commits,
branches, text) from silently becoming canonical or lending its authority.
There is no automatic replacement PR chain: a new branch or PR number never authorizes a replacement cycle. A
bounded clean replacement exists only under such a decision.

`BLOCKER_IDENTITY_SURVIVES_RENAME` — a blocker is its semantic defect. The same defect stays the same blocker
across new wording, new function names, new branches, new PRs, new phase labels and a "clean replacement"
label. Renaming never restores a repair allowance and never resets the prompt budget.

`ADMINISTRATIVE_CLOSURE` — the evidence-preserving exit for a candidate that cannot legally proceed (a governance
deadlock, no meaningful authorized repair, an exhausted budget, a `REJECT/FREEZE`, or abandonment):
- it requires the human's explicit action authorization naming the PR, its exact head and closure without merge; no
  controller decision, audit verdict or tool permission setting is that authorization;
- the controller re-proves the head; the PR is closed unmerged on that exact head, and a moved head stops the
  closure;
- the source branch, commits, findings, blocker identities, consumed executions and all evidence are preserved: no
  branch deletion, alert dismissal, thread resolution, rebase or count reset;
- the controller verifies the remote closed-unmerged state, unchanged main and source-branch preservation (24.5), and
  its handoff records the reason, exact head and tree, audit status (`NOT_EXECUTED` when none ran), preserved
  blockers and consumed count;
- it grants no verdict, acceptance, merge readiness, canonical adoption or automatic replacement; a later attempt
  needs `ROOT_CAUSE_ESCAPE`.

### 24.9 Deep Research

Deep Research answers current load-bearing external facts only: exchange/Deribit APIs, fees, rate limits,
funding, margin, liquidation, microstructure, custody/security/regulation, current framework or model/tool
behavior, and readiness/shadow/live standards. It is read-only and advisory — primary sources first, cited and
dated, with REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN kept separate — and it is never repository,
PR or CI state, implementation, GitHub mutation, merge authority or a gate waiver. The controller decides when
it is required and verifies its output before any use. Full protocol: `docs/crypto_core/deep_research_protocol.md`,
subordinate to this section.

### 24.10 CONTROLLER_READONLY_FIRST_POLICY

The ChatGPT controller works read-only first: it proves live state, verifies every executor and auditor claim
against evidence, detects contradictions and stale state, compiles the next serious prompt, and judges merge
readiness. It owns the `SOL_AUDIT_PREFLIGHT_PACKET` and the CI/status polling around every audit, so Sol allowance
is never spent on them (24.4). It never replaces local tests, never treats memory as repository state, never implements product
code, never satisfies the protected Class-C audit, performs an independent audit only as the last resort of
`NON_PROTECTED_AUDIT_FALLBACK` (24.4), never mutates GitHub without an exact human action
authorization, and never grants merge, readiness, live or capital authority.
Claude Fable 5 stays `INACTIVE_EXPIRED_RETIRED`: no active surface routes to it.

### 24.11 LIVE_STATE_POLICY and non-regression

`LIVE_STATE_POLICY` — durable doctrine pins no current `main` SHA, merged-PR number, open-PR count, blocker
position, capacity reading or setup-status value. Live state is re-proven from `git`/`gh` at the start of every
task (24.7) and lives in controller handoffs; dated history appears only in HISTORICAL sections and the
changelog. Every section-3 hard rule and section-16 forbidden scope binds unchanged: one open PR, no direct main
push, no force-push, standard merge only, explicit per-PR human merge authorization, pending CI = `NOT_READY`,
current valid material P1/P2 threads block, post-merge verification before next work, the digest-boundary rule, and no
BIST/live/private-API/order/scheduler/readiness/shadow/capital surface without separate authorization. Durable doctrine
and the external Project Instructions likewise pin no quota or availability reading, transient blocker, activation
in progress or effort telemetry. Hard-rule consistency: pending CI = `NOT_READY` is the controller's verdict
(section 3, 24.5 `HANDOFF_OWNERSHIP`); repair permission covers exactly the 24.8 blocker inventory; a `REPAIR_ONLY`
audit never satisfies the 24.5 merge requirement.

### 24.12 RUNTIME_PROOF and effort

`RUNTIME_ADMISSION_POLICY` — this section is the one authoritative runtime policy. Every serious routed execution —
implementation, repair, audit, re-audit (including the unified protected audit of 24.4) and auditor qualification
— reports, before mutation or substantive work, one compact runtime block:

```text
MODEL_REQUESTED / MODEL_ID_REQUIRED / MODEL_SELECTED / MODEL_ACTUAL / MODEL_SELECTION_EVIDENCE /
MODEL_EXECUTION_EVIDENCE / MODEL_SELECTION_CONFORMITY / RUNTIME_ELIGIBILITY / THINKING_ACTUAL / THINKING_EVIDENCE /
MODEL_EFFORT_REQUESTED / MODEL_EFFORT_ACTUAL / MODEL_EFFORT_EVIDENCE / MODEL_FALLBACK /
SPEED_MODE_REQUESTED / SPEED_MODE_ACTUAL
```

`MODEL_REQUESTED` is the controller's request; `MODEL_ID_REQUIRED` the exact id the route needs; `MODEL_SELECTED`
the id actually selected on the host (`MODEL_SELECTION_EVIDENCE`: the visible selector, session-bound configuration
or an attributable human selection attestation); `MODEL_ACTUAL` the id the running session executes
(`MODEL_EXECUTION_EVIDENCE`); `MODEL_SELECTION_CONFORMITY` whether the selection matches the requirement;
`RUNTIME_ELIGIBILITY` the admission verdict (`PASS_EXECUTION_PROVEN`, `PASS_ATTESTED_SELECTION` or `STOP`). Earlier
handoffs' `MODEL_IDENTITY_EVIDENCE` is `MODEL_EXECUTION_EVIDENCE`. Fields that do not apply are `N/A`, missing
optional telemetry is `UNKNOWN`; no schema or infrastructure is added for them.

`FAIL_CLOSED_RUNTIME_PROOF` — identity and required thinking are load-bearing. Admission is by exactly one path:

- `PATH_A = EXECUTION_PROVEN` — positive execution evidence that `MODEL_ACTUAL` equals `MODEL_ID_REQUIRED`, positive
  required thinking, and the applicable supported host and role evidence. `RUNTIME_ELIGIBILITY=PASS_EXECUTION_PROVEN`.
  Every implementation and repair writer (Claude Opus 5.5 and any Codex executor) is admitted only on `PATH_A`.
- `PATH_B = HUMAN_ATTESTED_AUDIT_SELECTION` — available only to an expressly authorized Sol audit, re-audit or
  auditor-qualification stage under this adopted policy or under the introducing external transition (24.14), and
  never to a mutation-capable writer. It requires all of: the exact required model selected; the required supported
  literal effort selected; an attributable stage- or session-bound human selection attestation made before
  substantive work; a supported host and the requested mode; required thinking positively evidenced; the actual
  identities of every implementing and repairing execution established on `PATH_A`; no writer role or authorship by
  the auditing session; a fresh independent READ_ONLY context; no known actual-model mismatch, prohibited fallback or
  contradictory material evidence; exact-head binding where applicable; the complete required semantic scope; and
  an explicit controller admission decision that acknowledges the residual assurance limitation. It records
  `MODEL_ACTUAL=UNKNOWN`, `MODEL_SELECTION_CONFORMITY=PASS`, `RUNTIME_ELIGIBILITY=PASS_ATTESTED_SELECTION`. A selected
  identity is never represented as the actual execution identity, and the 24.4 `INDEPENDENCE_ASSURANCE` limitation is
  recorded: `PATH_B` does not claim assurance equivalent to `PATH_A`.

| Runtime fact | Verdict |
|---|---|
| `PATH_A`: `MODEL_ACTUAL` equals `MODEL_ID_REQUIRED` on execution evidence; thinking required and positively `ENABLED`; effort known or `UNKNOWN` because the host exposes no execution-effort telemetry | PASS |
| `PATH_B`: every `PATH_B` condition holds for an authorized Sol audit, re-audit or qualification stage | PASS (attested selection) |
| `MODEL_ACTUAL` = `UNKNOWN` outside `PATH_B` | `STOP_WITH_PROOF` |
| Identity shown only by a selector, configuration, default, cache, alias or request text outside `PATH_B` | `STOP_WITH_PROOF` |
| `PATH_B` without an attributable attestation, or attested only after substantive work | `STOP_WITH_PROOF` |
| `MODEL_ACTUAL` known and different from `MODEL_ID_REQUIRED` (on any path, including a contradiction found after attestation) | `STOP_WITH_PROOF` |
| Thinking required and `THINKING_ACTUAL` = `UNKNOWN` or `DISABLED` | `STOP_WITH_PROOF` |
| A known prohibited fallback, failed independence, an unsupported selection, a material contradiction or missing governing authority | `STOP_WITH_PROOF` |
| Writer identity `UNKNOWN` (no `PATH_A` proof for an implementing or repairing execution) | `STOP_WITH_PROOF` |

An optional unknown (effort, speed or usage telemetry) is not a proven violation. An unavailable mandatory
prerequisite is never PASS. A stop before substantive work consumes no slot; a stage found ineligible after
substantive work is procedurally invalid (24.4, 24.8).

- Execution evidence is produced by the running session itself: runtime metadata naming the exact model,
  `/model`, `/status` or an equivalent diagnostic. A selector, configuration file, default, cache, alias or
  request text states intent, never the executing model, thinking mode or effort. Under `PATH_B` the human
  selection attestation is selection evidence only. When human selection evidence is sufficient, duplicate
  screenshots or selector checks are not demanded, and unavailable telemetry is not searched for repeatedly.
- Implementation, repair and audit executions require thinking (`THINKING_REQUIRED=ENABLED`, stated in the
  serious prompt's `MODEL_RUNTIME_PROOF`).
- When the exact required `MODEL_ACTUAL` is independently proven on execution evidence, the absence of a separate
  fallback telemetry field is not a second proof requirement; a known prohibited fallback still stops.
- Record `HOST_UI_LABEL` from the visible selected control and `HOST_CONFIG_SELECTION` from the explicit
  configuration bound to this session. Use `N/A` for an unused surface and `UNKNOWN` for missing evidence.
  Record `MODEL_ACTUAL`, `THINKING_ACTUAL` and `MODEL_EFFORT_ACTUAL` from the running session. Preserve the
  literal values and their sources in the runtime block. Absent effort telemetry stays `UNKNOWN`; it can pass
  identity/thinking but cannot establish a host relationship that requires an observed raw value.
- `HOST_SENSITIVE_EFFORT_POLICY` — effort is an operational selection, never correctness proof. Before substantive
  work the controller fixes one suitable supported literal for the stage on the actual host and records it with
  its source. When the actual supported host offers a different permitted literal than the default named below,
  the controller may explicitly select that native literal as suitable for the task; no cross-host or
  cross-spelling equivalence claim is required to approve an appropriate native selection, none is inferred (for
  example, `Extra High` is never asserted to equal `xhigh`), and no unsupported effort mapping is made. A spelling
  difference without established semantics is not by itself proof of a mismatch. A proven execution-effort conflict
  with the approved selection stops the stage unless `EFFORT_MISMATCH_WAIVER` below applies. Session-bound selection
  or configuration acceptance, actual writer identity, thinking, host capability and known-contradiction checks are
  preserved.
- `EFFORT_MISMATCH_WAIVER` — the one effort-waiver rule for every routed stage and lane, the Codex executor included;
  no other rule, adapter or guide defines another. A conflict is proven only when the running session's raw execution
  effort is established and its conflict with the approved selection rests on the same host vocabulary or on host
  documentation linking both values for that client and model. A spelling difference without established semantics
  is recorded with both literals and no claimed relationship: it needs no waiver, and the raw value is never itself
  acceptance evidence. A stage with a proven conflict may proceed only when all hold: (1) the requested and selected
  settings are supported on that host and model; (2) the actual conflicting effort is established and is not
  prohibited; (3) the conflict is the only condition waived; (4) the human grants an explicit attributable one-task
  waiver before any dependent mutation or substantive work; (5) the waiver binds the exact route and model id, stage,
  session, requested and selected literals and the true reported actual; (6) the controller judges, before that
  work (for the Codex executor in its gate F record), that the actual effort suffices for the whole authorized stage;
  and (7) every other A–G, host, runtime, thinking, independence, state, capability and authority condition passes.
  No waiver covers: a wrong or unknown actual writer identity; unknown or disabled required thinking; an unsupported
  selection; missing mandatory host configuration or selection acceptance (24.3 gate D and its paths below); missing
  edit, shell or validation capability; a known prohibited model fallback; executor `Ultra` or `ultra` requested,
  selected, configured or observed; unauthorized speed, delegation or repository mutation; or any unresolved
  material contradiction other than the established waived conflict. A waiver is not execution or host-acceptance
  evidence, never replaces a required selection (such as protected `Ultra`), binds no other task, session or stage,
  and authorizes nothing retroactively: work done before it stays ineligible (24.8). It is recorded in the handoff with
  the true actual, which is never restated as the requested value, and it applies only to stages that start after
  canonical adoption (24.14).
- `CLAUDE_EFFORT_POLICY` — use `xhigh` where the actual Opus 5.5 host offers it and it is appropriate; otherwise
  the controller selects an adequate supported host-native literal and records why it suffices. Use `max` only when
  offered and a named capability-critical implementation or hardest correctness-critical consolidated repair
  requires it. Stop if no supported setting suffices. Prove model and thinking on execution evidence (`PATH_A`).
- `CODEX_EXECUTOR_EFFORT_POLICY` — prefer `xhigh` for complex ordinary executor work, and `max` only on the same
  named critical triggers; a different supported native literal follows `HOST_SENSITIVE_EFFORT_POLICY`. Record the
  literal host selection alongside the request. Gate D uses one of these paths for the exact adopted executor id:
  - **CLI/config:** require the selected literal on this invocation or in a session-bound loaded setting.
    Cite `HOST_CONFIG_ACCEPTANCE_EVIDENCE` showing this execution accepted that value. For example, the matching CLI process invocation
    and same-session turn metadata reporting the selected effort establish acceptance. A suggested launch command, a default
    config file, a catalog or a raw turn value alone is insufficient. No desktop control is required.
  - **Visible selector:** cite the selected literal on this host and model; the controller's recorded selection of
    that literal (requested or native) establishes the selection. Record the source and the literal; a raw
    execution value, when exposed, is recorded beside it.
  - In either path reject unsupported selections, contradictory evidence other than a conflict waived under
    `EFFORT_MISMATCH_WAIVER`, and executor `Ultra` or `ultra` requested, selected, configured or observed; no waiver
    permits these cases or automatic delegation. A proven raw execution-effort conflict with the approved selection
    stops unless `EFFORT_MISMATCH_WAIVER` applies, and that waiver is available only once the path's selection or
    acceptance evidence above is independently established: a raw value that conflicts with the selection is never
    acceptance evidence, and a waiver never supplies it. Gate E independently requires the adopted runtime id,
    thinking enabled and no model fallback. Speed is `STANDARD` (Fast requires explicit time-critical authorization)
    and subagents are 0. Host approval or sandbox settings confer no action authority.
- `SOL_AUDIT_EFFORT_POLICY` — every audit or re-audit by the `ACTIVE_SOL_AUDITOR` requires `MODEL_ID_REQUIRED` set to
  that auditor's id (the id resolved under 24.7 `SOL_ROUTE_STATE_RESOLUTION`; a qualification stage names
  `gpt-6.2-sol`) and thinking `ENABLED`, admitted under `FAIL_CLOSED_RUNTIME_PROOF` above (`PATH_A`, or `PATH_B` where
  authorized); effort is recorded literally (24.3), is never
  correctness proof, and no host label is ever mapped onto another (`Ultra`, `max` and `xhigh` are never
  translated into one another).
  - Protected audit or re-audit (any protected trigger of 24.4, including protected T4 `CLASS_C_CROSS_CONTRACT`):
    `PROTECTED_AUDIT_EFFORT_REQUESTED=Ultra`, the exact current host literal. When the protected execution's
    selector does not expose `Ultra`, the audit stops with proof before substantive work and returns to the
    controller to re-prove the host effort vocabulary; it never runs at another label, is never normalized to
    `max`, and no other model substitutes (`GPT61_SOL_T4_EXCLUSIVE`, 24.3). An auditor qualification at protected
    standard likewise requires literal `Ultra`.
  - Non-protected audit or re-audit: `Ultra` is the default request; when the selector does not expose it, the
    controller supplies another available literal label appropriate to that bounded audit, recorded literally. The
    protected-only `Ultra` availability stop does not apply, while identity, required thinking and a known
    prohibited fallback still stop exactly as in the table above, and `MODEL_EFFORT_ACTUAL` may stay `UNKNOWN` only
    as stated above.
- `SOL_SPEED_MODE_POLICY` — `SPEED_MODE_DEFAULT=STANDARD` for every Sol audit and qualification. Fast is never the default
  and never a correctness upgrade; it runs only on an explicit controller or human time-critical authorization
  recorded for that task. The audit reports `SPEED_MODE_REQUESTED` and `SPEED_MODE_ACTUAL`; missing speed
  telemetry is `UNKNOWN`, never invented, and does not block.
- `SOL_SUBAGENTS_DEFAULT=0` — a Sol audit adds a bounded read-only subagent only for a genuinely separate material
  audit track, inside the limit below, never because the host or effort level supports agents.
- `SOL_USAGE_TELEMETRY` — when the host exposes allowance or usage status, a Sol audit records
  `USAGE_WINDOW_BEFORE`, `USAGE_WINDOW_AFTER` and `USAGE_DELTA`; missing telemetry is `UNKNOWN` and never blocks an
  audit. The values are advisory input for prompt tuning only — never a gate, a quota, a price or a prompt-count
  guarantee — and are never written into durable doctrine (24.11).
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

`POLICY_HIERARCHY` — four classes; a lower class never overrides a higher one:
1. `HARD_INVARIANT` — product safety, deterministic and PIT-safe behavior, action authority, independent
   verification, exact-head binding, validation, one writer, one open PR, explicit merge authorization and lifecycle
   limits.
2. `ADAPTIVE_OPERATIONAL_POLICY` — host capability, current availability, the supported effort vocabulary, the
   permissible evidence methods, evidence reuse and bounded interruption handling.
3. `TASK_BOUND_DECISION` — the controller-selected model, effort, semantic contract, supported paths, validation
   scope, current authority and applicable operational route.
4. `ADVISORY_DEFAULT` — optional telemetry, prompt compaction, context efficiency, usage measurement and
   presentation preferences.

This section is the single canonical source of normative authority; adapters and the external Project
Instructions apply it and never independently redefine it.

`OPERATIONAL_FLEXIBILITY` — ordinary variation inside an adopted policy is a controller decision and needs no
governance amendment: current availability and quota changes; supported task-sensitive effort selection; reuse of
attributable evidence; authorized isolated checkout selection; context compaction and fresh-context reconstruction;
bounded CI and infrastructure recovery; supported stage continuation (24.8); existing conditional executor routes;
and the named adopted successor activation (24.14). No durable rule is added merely because a host changes its
presentation or optional telemetry is missing; only material stale or contradictory evidence is refreshed. A missing
mandatory capability or authority receives an explicit stop or recovery disposition. Fail-closed product behavior
stays separate from ordinary operational resilience.

`PERFORMANCE_AND_LEARNING` — from existing handoffs and optional available usage telemetry the controller evaluates
independently accepted semantic closures, first-audit acceptance, clean first whole-contract re-audit after the
consolidated repair, specialist executions per accepted contract, invalid or interrupted execution frequency, and
total lifecycle time and comparable usage where available; it uses recurring material root causes to improve
architecture, implementation prompts, validation and repair completeness. An 80–90% clean re-audit rate is a desired
engineering outcome, never an asserted current rate or a guarantee. Metrics never influence severity, audit scope or
reported results, never reopen governance outside the 24.14 reopen reasons, and no analytics platform or persistent
measurement infrastructure exists for them.

Further non-claims: `PATH_B` (24.12) never claims assurance equivalent to `PATH_A`; one qualification result never
proves global or intrinsic model superiority or backend identity; no prompt guarantees the absence of platform
intervention; and nothing here claims perfect reliability, profitability, readiness or a measured efficiency gain.

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

The reopening reason for `CRYPTO_CORE_AGENT_OS_FINAL_EFFICIENCY_AND_MODEL_ROUTING_V1` is
`MATERIAL_CAPABILITY_CHANGE`. Its introduction is governed by
accepted-base section 24 and its host adapters. Its rules apply only to later stages after independent
protected `gpt-6.1-sol` acceptance at literal `Ultra`, terminal required CI and CodeQL at the accepted head,
human authorization naming that PR, exact head and standard merge, the standard merge, and controller
verification of its remote result (24.5). The controller then synchronizes the external ChatGPT Project
Instructions with the merged routing, candidate-role limits, approval-source and closeout rules, and
verifies their use from a fresh context. Only after all these gates may the controller record
`CLOSED_FROZEN` in the handoff. This transition activates neither candidate model.

`CRYPTO_CORE_AGENT_OS_HOST_AND_WORKFLOW_CLOSURE_V1` applies prospectively after independent protected acceptance
under accepted-main rules, terminal exact-head CI and CodeQL, explicit exact-head human authorization, standard
merge, remote post-merge proof, the corresponding external Project instruction update and fresh-chat acceptance.
Its own implementation and audit use the base policy. It grants no retroactive stage authority and adopts no model.

`SETUP_STATUS=CLOSED_FROZEN` holds once this kernel's setup PR is independently accepted, merged, post-merge
verified and fresh-chat accepted. The status is proven from that live evidence (24.11) and never written into a
durable file. From then on the setup/workflow reopens ONLY for `REAL_SAFETY_DEFECT`, `BROKEN_CONTINUITY`,
`MATERIAL_CAPABILITY_CHANGE` or `MEASURED_REPEATED_WORK_REDUCTION`, each named with its evidence in the
reopening prompt. Forbidden reopen reasons: wording polish; a P3 nit; style preference; "could be more
complete"; a new theoretical edge case outside the active contract; the desire for a stronger validator;
generic architecture improvement. A reopening change follows the same lifecycle (24.8) as any other PR.

`PRODUCT_DEFAULT` — after `SETUP_STATUS=CLOSED_FROZEN` the default next action is PRODUCT work, and ordinary
product PRs never redesign the workflow. Product PRs use `LARGEST_SAFE_SEMANTIC_CLOSURE`, the fewest-prompt
budget (target 2 clean / 4 repaired, hard maximum 5, no prompt 6), one complete GPT-6.1 Sol-primary audit, at
most one consolidated repair and one whole-contract re-audit (24.4, 24.8).

`CLAUDE_LANE_UPGRADE_TRANSITION` (completed; a HISTORICAL record of an accepted transition that routes nothing) —
`CLAUDE_OPUS_5_5_CONTROL_PLANE_UPGRADE_V1` (the Claude lane identity of 24.3,
its effort policy in 24.12 and the adapters that apply them) is a reopening under `MATERIAL_CAPABILITY_CHANGE`
alone: it replaces the model identity of the existing Claude lane and changes no role, authority, budget,
lifecycle or gate. The change that introduces it grants itself no exemption. Its own acceptance is governed by
the control plane accepted before it, so the superseded Claude lane implements it and GPT-6 Astra audits it, and
Claude Opus 5.5 becomes the routable Claude lane only once that change is independently accepted, merged,
post-merge verified and fresh-chat accepted. A model may never accept its own successor.

`ASTRA_UNIFIED_AUDIT_TRANSITION` (completed; a HISTORICAL record of an accepted transition that routes nothing; its
audit lane is superseded by `GPT61_SOL_AUDIT_TRANSITION` below) — `ASTRA_UNIFIED_AUDIT_CONTROL_PLANE_V1` (the audit, fixed-point and lifecycle
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

`GPT61_SOL_AUDIT_TRANSITION` — `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1` (the GPT-6.1 Sol audit lane of 24.3 and
24.4, `SOL_AUDIT_USAGE_EFFICIENCY_V1`, the prompt compaction and compact audit handoff of 24.6, the budget wording
of 24.8, the Sol effort, speed, subagent and telemetry policies of 24.12, and the adapters and guides that apply
them) is a reopening under `MATERIAL_CAPABILITY_CHANGE` (GPT-6.1 Sol as the independent and protected audit lane)
and `MEASURED_REPEATED_WORK_REDUCTION` (audit allowance spent on status, polling, rediscovery and duplicated
re-verification). It weakens no gate, lifecycle, budget or authority boundary. The change that introduces it
grants itself no exemption: its own acceptance is governed by the control plane accepted before it, so its
independent and protected acceptance audit is the final legacy GPT-6 Astra audit under that plane, and no model
accepts the change that makes it the protected auditor. While that change is under acceptance audit, every auditor
and the ChatGPT controller apply this section and the host adapters as they stand on its base (accepted main),
never the candidate's own text. GPT-6.1 Sol becomes the active independent and protected audit lane only once that
change is accepted by that GPT-6 Astra audit, explicitly authorized by the human on its exact head, merged by
standard merge, post-merge verified, matched by the externally maintained ChatGPT Project instruction, and
fresh-chat accepted; its rules bind only candidate lifecycles that start after all of that. From then on GPT-6
Astra (`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT`) and Codex GPT-5.6 Sol
(`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`) are no crypto_core lane, default, fallback or dependency, and
`SETUP_STATUS=CLOSED_FROZEN` holds again under the reopen rules above — proven from live evidence, never written
into a durable file.

`CODEX_EXECUTOR_FALLBACK_TRANSITION` — `CODEX_EXECUTOR_QUOTA_FALLBACK_V1` (the conditional Codex executor lane, its
adopted ids, evidence kinds, activation gates, stage rules and `INTERRUPTED_STAGE` of 24.3, the independence sentence
of 24.4, the executor handoff fields of 24.6, the executor adapter of 24.7, the budget wording of 24.8,
`CODEX_EXECUTOR_EFFORT_POLICY` of 24.12, and the adapters and guides that apply them) is a reopening under
`MATERIAL_CAPABILITY_CHANGE`: the Codex host offers an executor-capable non-Sol model id while Claude Opus 5.5, until
this change the only implementation and repair lane, can be quota-blocked or unavailable, which stalled every stage
only it could run. It weakens no gate, budget, lifecycle or authority boundary and changes no audit lane. The change
that introduces it grants itself no exemption: its own acceptance is governed by the control plane accepted before it,
so Claude Opus 5.5 implements it and any repair of it, the GPT-6.1 Sol protected audit at `Ultra` accepts it, and no
Codex executor implements, repairs or accepts it. While that change is under acceptance audit, every auditor and the
ChatGPT controller apply this section and the host adapters as they stand on its base (accepted main), never the
candidate's own text — the executor adapter it carries is the object under audit, not the audit procedure. The Codex
executor fallback becomes routable only once that change is accepted by that audit, explicitly authorized by the human
on its exact head, merged by standard merge, post-merge verified, matched by the externally maintained ChatGPT Project
instruction, and fresh-chat accepted; its rules bind only stages that start after all of that and never apply
retroactively to an earlier lifecycle. From then on `SETUP_STATUS=CLOSED_FROZEN` holds again under the reopen rules
above — proven from live evidence, never written into a durable file.

`FINAL_CONTROL_PLANE_STABILIZATION_TRANSITION` — `CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1` (runtime
admission and literal effort of 24.12; Claude availability evidence, `ACTIVE_SOL_AUDITOR`, the removal of Sol-family
executor candidacy and the named successor of 24.3; audit admission, `INDEPENDENCE_ASSURANCE` and
`PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` of 24.4; `HANDOFF_OWNERSHIP` and approval sources of section 3 and 24.5; prompt
safety and handoff fields of 24.6; `EFFECTIVE_ROUTE_RECOVERY` and `SOL_ROUTE_STATE_RESOLUTION` of 24.7; execution
accounting, `OPERATIONAL_INTERRUPTION` and `ADMINISTRATIVE_CLOSURE` of 24.8; the hierarchy, flexibility and learning
rules of 24.13; this transition and `GPT62_SOL_SUCCESSOR_ACTIVATION`; the aligned sections 2, 4, 6, 8 and 10; and
the adapters and guides that apply them) is a reopening under `BROKEN_CONTINUITY` and `MATERIAL_CAPABILITY_CHANGE`.
Lifecycles reached states with no legal next stage: a failed required check blocked the only audit that could open
the repair, section 3 allowed repair for P1/P2 alone, writer and controller both owned terminal CI, and no rule
closed a candidate that could not proceed. The protected auditor's host does not expose execution identity, so
accepted-base 24.12 could not admit any Sol audit, and the base's prior-plane acceptance rule therefore could not
accept this change.
- Introducing authority: the introducing transition is governed by a narrowly scoped external human governance
  decision, carried in the lifecycle's `APPROVAL_SOURCE_PACKET` (24.5), which authorizes a bounded external transition
  policy in place of the accepted-base 24.12 runtime-admission and prior-plane acceptance provisions that block it.
  That decision — never this text — is the authority; it is not compliance with the unchanged accepted-base rules,
  and the candidate authorizes nothing by asserting it.
- For the introducing lifecycle, accepted-base rules apply except that expressly authorized Sol audit-admission and
  corresponding prior-plane acceptance exception. The introducing writer is execution-proven (`PATH_A`). The incumbent
  GPT-6.1 Sol at literal `Ultra` performs the independent protected acceptance — never its proposed successor.
  `PATH_B` may be considered for that audit and its re-audit, with required thinking and every other admission
  condition mandatory. Acceptance requires terminal green exact-head CI and CodeQL; the candidate's own unmerged
  `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1` cannot admit its own audit. Any repair requires a valid complete inventory and
  applicable separate authority; merge requires the human's separate exact-PR, exact-head standard-merge
  authorization. While it is under acceptance audit, auditors and the controller apply section 24 and the adapters as
  they stand on its base, modified only by that external decision, never the candidate's own text.
- The exception is bound to this contract, its accepted base, this candidate lifecycle, the exact audit head and the
  applicable stage. It expires on adoption, terminal rejection, abandonment or revocation, and allows no recursive
  recovery, retrospective credit or additional model substitution. When no eligible independent acceptance route
  exists, the transition stops rather than asserting liveness.
- The amendment's rules become available only after independent acceptance, terminal required CI and CodeQL on the
  accepted head, the human's exact-head merge authorization, the standard merge, remote post-merge verification
  (24.5), synchronization of the external ChatGPT Project Instructions to the accepted conditional policy (which
  activates no unqualified model), and verification of that policy from a fresh controller context. They bind only
  stages and lifecycles that start afterwards and never apply retroactively: no earlier candidate is reopened,
  relabelled, repaired, re-audited or re-budgeted under them, and every historical count, finding, blocker identity
  and consumed execution is preserved. The new 24.3 gate A applies after adoption only. Later recoveries use the
  adopted bounded operational policies; a permanent capability change outside them needs its own separately
  authorized prospective decision, never a broad discretionary bypass.

`GPT62_SOL_SUCCESSOR_ACTIVATION` — the one named conditional successor activation this amendment defines. It needs no
further governance amendment when its predicates are met; any unrelated future model promotion needs its own
independent prospective adoption. The sequence, each step on attributable evidence:
1. independent acceptance and merge of this amendment under its introducing transition (above);
2. remote post-merge verification;
3. synchronization of the external Project Instructions to the accepted conditional policy, naming the route state
   `PRE_ACTIVATION`;
4. verification of that policy from a fresh controller context, whose accepted handoff records the initial
   `SOL_ROUTE_STATE=PRE_ACTIVATION` with that verification as its origin (24.7);
5. a controller-authorized bounded GPT-6.2 Sol qualification at literal `Ultra` under the adopted runtime policy;
6. independent controller adjudication of the qualification evidence;
7. when every condition below holds, an explicit named prospective activation decision, recorded at once in the
   controller's accepted handoff with the route state `ACTIVATION_STATE_UNKNOWN` (`PUBLICATION_INCOMPLETE`);
8. publication: the complete activation record enters the accepted handoff chain, and the external Project
   Instructions are synchronized to name `POST_ACTIVATION` and identify that record;
9. a fresh controller context resolves `POST_ACTIVATION_VERIFIED` (24.7) from those published sources alone and records
   that verification; the record of step 9 is the effective future-stage boundary.

- Activation status: until step 7 the activation is at most proposed and changes no route state (a complete valid
  qualification alone dispatches nothing to `gpt-6.2-sol`); from step 7 until step 9 is recorded it is incomplete and
  no new audit stage is dispatched under either Sol id; after step 9 it is effective for audit stages dispatched from
  then on. No step needs a further governance amendment or an already-activated GPT-6.2 Sol, and no step depends on
  a later one.
- Qualification: frozen, read-only, representative examples outside any candidate lifecycle, including at least one
  whole-contract review, known material-defect detection, negative controls and false-positive adjudication, within a
  task-specific evaluation boundary against a source-grounded controller reference inventory withheld from the model.
  It depends on no already-activated GPT-6.2 Sol and on no premature freeze. Earlier incomplete qualification
  attempts supply no credit. Under `PATH_B` it evaluates the attributable selected route and the observed review
  performance, never proven backend identity or intrinsic superiority; comparable lifecycle usage and completion
  evidence are used where available and missing optional usage stays `UNKNOWN`. A platform interruption follows
  24.8 `OPERATIONAL_INTERRUPTION`; there is no unbounded evaluation loop.
- Activation requires all of: this adopted canonical successor policy; a complete attributable qualification; no
  unresolved material qualification defect; independently adjudicated material detection and false positives;
  runtime admission, positive thinking, host capability and supported literal `Ultra`; the explicit prospective
  controller activation decision; and the existing human successor authorization (the human governance decision that
  approved this successor's qualification and prospective adoption).
- The activation record binds the accepted policy revision, the exact model id and role, the qualification evidence
  and its independent adjudication, the existing human successor authorization, the explicit prospective controller
  activation decision, the effective future-stage boundary (step 9), the pre-activation record it supersedes and its
  attributable continuity source (the accepted handoff that carries it). It is preserved through the accepted
  controller handoff and continuity mechanisms (24.7), accessible to fresh controllers and agents — no new registry
  and no undocumented mutable local flag. It never applies to a stage already started.
- After the effective activation `gpt-6.2-sol` is the primary and exclusive protected auditor (`ACTIVE_SOL_AUDITOR`,
  24.3) and `gpt-6.1-sol` is historical for the active route, never an automatic fallback. When qualification fails,
  stops or stays incomplete, no route state changes: the incumbent stays eligible only while
  `PRE_ACTIVATION_VERIFIED` holds, and the requested upgrade is reported incomplete. After adoption the route state is
  resolved only under 24.7 `SOL_ROUTE_STATE_RESOLUTION`.

`STABILIZATION_ADOPTION_STATUS` — human decision, construction, independent acceptance, CI, merge authorization,
merge, remote verification, Project Instructions synchronization, fresh-context acceptance, qualification and
successor activation are separate facts, never collapsed into one acceptance claim. The general operational policy
is used only after canonical adoption. Core setup status and the requested successor-upgrade status are recorded
separately: product work under the incumbent auditor is possible once its actual canonical prerequisites hold, and
the full requested stabilization is never reported finished while a material applicable adoption requirement
remains. The Project Instructions name the effective route state (`PRE_ACTIVATION` from adoption, `POST_ACTIVATION`
from the activation publication) and identify its accepted record; they apply the policy and grant no activation
authority (24.7). After activation, the controller verifies that the external instructions and fresh-context routing
apply the effective accepted role. The final Project Instructions are complete and at most 8,000 characters including
spaces and line breaks, checked computationally by the controller, and carry no volatile PR, SHA, quota or transient
blocker state; they preserve the controller responsibilities, the exact authority hierarchy, independent
verification, evidence discipline, routing, recovery, lifecycle and product safety. `CLOSED_FROZEN` is derived from
live accepted evidence and never asserted by a candidate; the default next action then returns to `PRODUCT_DEFAULT`.

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

*v6.3 (2026-10-02): `GPT61_SOL_UNIFIED_AUDIT_CONTROL_PLANE_V1` — a setup reopening under
`MATERIAL_CAPABILITY_CHANGE` (GPT-6.1 Sol, `gpt-6.1-sol`, as the independent and protected audit lane on the
ChatGPT Work/Codex host) and `MEASURED_REPEATED_WORK_REDUCTION` (audit allowance spent on status, polling,
rediscovery and duplicated re-verification). GPT-6.1 Sol replaces GPT-6 Astra as the PRIMARY independent auditor
and the sole protected T4 `CLASS_C_CROSS_CONTRACT` auditor (`GPT61_SOL_UNIFIED_INDEPENDENT_AUDIT_V1`,
`GPT61_SOL_T4_EXCLUSIVE`); GPT-6 Astra becomes `SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_AUDIT` and Codex GPT-5.6 Sol
`SUPERSEDED_FOR_ACTIVE_CRYPTO_CORE_ROUTING`, and neither is a fallback; the non-protected audit fallback is the
ChatGPT controller alone, and protected work waits on the frozen exact head when GPT-6.1 Sol cannot audit. GPT-6.1
Sol is an audit-only lane: repo-native engineering moves to the Claude task that needs it, and status and polling
to the controller. Independence is now also decided by executing model id, so a ChatGPT Work or Codex execution on
`gpt-6.1-sol` that implemented or repaired a candidate disqualifies GPT-6.1 Sol from auditing it. Added
`SOL_AUDIT_USAGE_EFFICIENCY_V1` (the controller's preflight packet, changed-files-outward read scope, evidence
reuse, and the delta-aware whole-contract re-audit), `PROMPT_COMPACTION_V1` and `COMPACT_AUDIT_HANDOFF` (24.6),
and the Sol effort (`Ultra`, mandatory for protected audits, which stop when the selector does not expose it),
`STANDARD` speed, subagent and usage-telemetry policies (24.12). No price, credit amount, quota size or prompt
count is doctrine. Unchanged: `COMPLETE_BLOCKER_COLLECTION`, `AUDIT_MATERIALITY_BOUNDARY_V1`, `FINITE_AUDIT_RULE`,
the whole-contract audit and re-audit, the protected T4 requirement, exact-head binding, runtime identity and
thinking proof, one consolidated repair, `FIXED_POINT_STOP`, the 2 / 4 / hard-5 specialist budget, one open PR,
terminal CI, explicit human exact-head merge authority, standard merge, post-merge verification and every paper,
live, capital and security boundary. The completed Claude and Astra transition rules are labelled HISTORICAL. The
transition rule (24.14 `GPT61_SOL_AUDIT_TRANSITION`) keeps this change governed by the plane accepted before it:
its acceptance audit is the final legacy GPT-6 Astra audit, and GPT-6.1 Sol becomes active only after that
acceptance, human exact-head authorization, merge, post-merge verification, the external ChatGPT Project
instruction update and fresh-chat acceptance. Docs/setup only: no product code, tests, scripts, workflows or
dependencies touched.*

*v6.3 same-PR consolidated repair (2026-10-02): the one consolidated repair closed the two P2 blockers of the final
legacy GPT-6 Astra audit by one root cause — efficiency rules may optimize within canonical contracts, never
reorder, replace or broaden them. (1) `PROMPT_COMPACTION_REQUIRED_FIELD_ORDER_CONFLICT`: `PROMPT_COMPACTION_V1`
no longer places dynamic state in a late suffix; the twelve `SERIOUS_PROMPT_COMPILER` fields keep their canonical
order, required dynamic values stay inside their own fields (`STATE_PIN`, `MODEL_RUNTIME_PROOF`,
`BLOCKER_INVENTORY`), the Sol preflight packet travels inside those fields, and cache friendliness comes from
stable doctrine and template references only. The prompting-guide skeletons and the Opus repair template now
follow the canonical field order. (2) `PROTECTED_ULTRA_STOP_LEAKS_TO_NONPROTECTED_AUDIT`: the stop on an unexposed
`Ultra` applies to protected audits only; a non-protected Sol audit keeps `Ultra` as its default and otherwise
uses the available literal label the controller supplies, while identity, thinking and prohibited-fallback stops
are unchanged. The speed and usage telemetry rules are unchanged, and no gate, lane or lifecycle rule changed.
Docs/setup only.*

*v6.4 (2026-11-18): `CODEX_EXECUTOR_QUOTA_FALLBACK_V1` — a setup reopening under `MATERIAL_CAPABILITY_CHANGE`: the
Codex host offers an executor-capable non-Sol model id while Claude Opus 5.5, until then the only implementation and
repair lane, can be quota-blocked or unavailable, which stalled every lifecycle stage only it could run. Section 24.3
adds a conditional Codex executor lane for one whole implementation stage or the one consolidated repair stage, routed
only by an explicit controller selection when seven activation gates hold: fresh Claude quota-block or unavailability
evidence for that stage, the controller's recorded selection, an adopted id, fresh host-capability evidence, positive
runtime identity and thinking proof, a whole-stage executor, and a preserved independent GPT-6.1 Sol audit. It keeps
`HOST_CAPABILITY_EVIDENCE`, `EXECUTION_IDENTITY_EVIDENCE` and `CONTROLLER_AUTHORIZATION` apart. The one adopted id is
`gpt-6.2-astra` (GPT-6.2 Astra), adopted on host-capability evidence observed on 2026-11-18: the Codex host's model
catalog listed it with code-edit and shell tools and the effort levels `low`, `medium`, `high`, `xhigh`, `max` and
`ultra`, while the ChatGPT Work host's catalog cached on 2026-11-07 did not list it. No execution-identity evidence
for it existed at adoption, so every stage proves identity at runtime. No lower-cost executor is adopted, and no
Sol-family id is ever a Codex executor. The executing provider changes only at a stage boundary; an executor stage
takes the replaced Claude stage's slot inside the unchanged 2 / 4 / hard-5 budget; `INTERRUPTED_STAGE` sends an
interrupted stage to controller adjudication under unchanged 24.8 rules, never to a silent restart. Section 24.4
counts every executing model id as an implementer of the candidate; 24.6 adds the executor route to the handoff; 24.7
names the executor adapter; 24.8 states that a change of executor never resets the count; 24.12 adds
`CODEX_EXECUTOR_EFFORT_POLICY` (`xhigh`, `max` only on a named trigger, never `ultra`, which the host describes as
automatic task delegation; `STANDARD` speed; subagents 0; host approval layers are never authorization); 24.14 adds
`CODEX_EXECUTOR_FALLBACK_TRANSITION`. Sections 2, 5, 8 and 18 were aligned. The new adapter
`.codex/skills/crypto-core-executor-fallback/SKILL.md` applies the lane; the GPT-6.1 Sol adapter stays audit-only and
sends executor sessions to it. Unchanged: the Claude lane and its effort policy, the GPT-6.1 Sol audit lane and its
exclusive protected Class-C authority at `Ultra`, `NON_PROTECTED_AUDIT_FALLBACK`, `COMPLETE_BLOCKER_COLLECTION`,
`AUDIT_MATERIALITY_BOUNDARY_V1`, one consolidated repair, `FIXED_POINT_STOP`, `ROOT_CAUSE_ESCAPE`, one writer and one
open PR, exact-head CI, the human's exact-head merge authority, standard merge, post-merge verification and every
paper, live, capital and security boundary. Its own acceptance follows the plane before it: Claude Opus 5.5
implemented it, the GPT-6.1 Sol protected audit accepts it, and it routes nothing before the full transition sequence.
Docs/setup only: no product code, tests, scripts, workflows or dependencies touched.*

*v6.5 (2026-11-27): `CRYPTO_CORE_FINAL_CONTROL_PLANE_STABILIZATION_V1` — a prospective reopening under
`BROKEN_CONTINUITY` and `MATERIAL_CAPABILITY_CHANGE`, built from accepted main under a controller `ROOT_CAUSE_ESCAPE`
architecture decision. It is not a revival of the closed, unmerged PR #454 candidate (which inherited the PR #453
`GOVERNANCE_DEADLOCK`); both keep their histories, findings, blocker identities and consumed counts, and neither lends
authority. Blockers closed by root cause: `GOV-RUNTIME-IDENTITY-PROVENANCE` (24.12 now has one admission policy with
`PATH_A` execution-proven and `PATH_B` human-attested audit selection for authorized Sol audit and qualification
stages only, with the residual assurance limitation recorded in 24.4 `INDEPENDENCE_ASSURANCE`);
`PROSPECTIVE_ACCEPTANCE_AUTHORITY` (24.14 `FINAL_CONTROL_PLANE_STABILIZATION_TRANSITION` names the external human
decision as the bounded introducing authority, accepted by the incumbent GPT-6.1 Sol at `Ultra`);
`P2-GOV-CI-ONLY-REPAIR-AUTHORITY-CONFLICT` (section 3 now permits the repair for P1/P2 or a confirmed
`CI_GATE_BLOCKER`); `GOV-PRE-AUDIT-CI-DEADLOCK` (24.4 `PRE_AUDIT_CI_FAILURE_RESOLUTION_V1`: four failure classes, ten
eligibility conditions, the whole-contract `REPAIR_ONLY` first audit, changed-check-state rules, and the 24.8 repair
opener and green-CI re-audit gate); `GOV-CI-HANDOFF-OWNERSHIP` (section 3 and 24.5 `HANDOFF_OWNERSHIP`); and
`GOV-ADMINISTRATIVE-CLOSURE-STATE` (24.8 `ADMINISTRATIVE_CLOSURE`). Also added: the human-statement gate A for Claude
availability (24.3); `ACTIVE_SOL_AUDITOR` with the named conditional `GPT62_SOL_SUCCESSOR_ACTIVATION` (24.3, 24.14)
and the removal of GPT-6.2 Sol executor candidacy; `HOST_SENSITIVE_EFFORT_POLICY` with native literals and no
cross-host equivalence claims (24.12); execution accounting, `CONTINUATION_BUDGET_CHECK` and
`OPERATIONAL_INTERRUPTION` (24.8); `CONTROLLER_PROMPT_SAFETY_AND_SCOPE_V1` (24.6); `EFFECTIVE_ROUTE_RECOVERY` (24.7);
and `POLICY_HIERARCHY`, `OPERATIONAL_FLEXIBILITY` and `PERFORMANCE_AND_LEARNING` (24.13). The one consolidated repair
after the independent replacement audit closes by root cause `P2-GOV-EXECUTOR-EFFORT-WAIVER-AUTHORITY-CONFLICT` (24.12
`EFFORT_MISMATCH_WAIVER` is the single effort-waiver rule that `HOST_SENSITIVE_EFFORT_POLICY`,
`CODEX_EXECUTOR_EFFORT_POLICY` and every adapter reference) and `P2-GOV-SOL-ACTIVATION-STATE-RECOVERY-AMBIGUITY` (24.7
`SOL_ROUTE_STATE_RESOLUTION`: three route states from positive current evidence, currentness, supersession and
bounded recovery through the accepted handoff chain and the Project Instructions; the 24.14 activation publication
boundary; `CONTINUITY_INDEX.md` separates repository state from external governance decisions). Historical findings
`CI-CODEQL-665`, `CODEQL-666`, `OWN-HISTORY-C2-BOOST`, `OWN-HISTORY-FA4-COVERAGE-RESTART` and
`SETUP-INJECTED-CLAUDE-DRIFT` are preserved and not claimed fixed by this governance change. Unchanged: every
product, paper, PIT, live, capital and security boundary; one writer; one open PR; the 2 / 4 / hard-5 budget; one
consolidated repair; `FIXED_POINT_STOP`; exact-head CI; independent protected audit at `Ultra`; and the human's
exact-head merge authority. Docs/setup only: no product code, tests, scripts, workflows, hooks, validators, schemas or
dependencies touched.*
