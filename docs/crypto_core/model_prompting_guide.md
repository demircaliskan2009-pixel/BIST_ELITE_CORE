# crypto_core Model Prompting Guide (v1, 2026-07-10)

Durable authoring guide for every model/lane prompt in the crypto_core workflow. Active routing authority
is `docs/crypto_core/agent_workflow.md` section 23 ("Active GPT-5.6 Routing Doctrine"); this guide never
overrides it — it teaches how to WRITE prompts for it. Companion lane shorthands live in
`docs/crypto_core/agent_prompts/token_efficiency_v2.md`; token budgets live in
`docs/crypto_core/token_efficiency_playbook.md`. If this guide and section 23 ever appear to conflict,
section 23 and the stricter safety rule win.

Nothing in this guide is repo-state proof, a merge authorization, or a safety-gate waiver. The blocker
`secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1` is not affected by prompting
style; it closes only through its own audited SM-5/SM-6 gates.

## 1. Prompt anatomy standard

Every serious prompt carries these fields, in this order. Mechanical T0 snapshots may compress, but the
model-verification block is never dropped from a serious prompt.

| Field | Content | Rule |
|---|---|---|
| `ROLE` | One line: what the model IS this turn (implementer / auditor / mechanical executor / researcher) | One role per prompt; never implementation + independent audit together |
| `TASK_CLASS` | `T0`-`T4`, `XR`, or `CONTROLLER_CONNECTOR_GATE` | Classify BEFORE choosing the model, never after |
| `MODEL_REQUESTED` | Exact lane (e.g. `GPT-5.6 Sol`, `Claude Opus 4.8`) | From the section-23 table for the class |
| `REASONING_REQUESTED` | `none`/`low`/`high`/`xhigh`/`max` | `max` only controller-gated (Sol); mechanics never above `low` |
| `EXACT_MODEL_REQUIRED` | `true`/`false` | `true` forces STOP_WITH_PROOF on mismatch; use for T4 and model-sensitive audits |
| `MODEL_ACTUAL` / `REASONING_ACTUAL` | Printed FIRST by the executor from runtime proof | Never claimed from the prompt text; unavailable-model quality is never claimed |
| `STATE_PROOF` | Pinned expected `main` HEAD, clean-tree requirement, expected open-PR set | Executor re-proves with fresh `git`/`gh`; memory is never proof |
| `SCOPE / ALLOWED_FILES` | Exact file list | Executor stops if the change set would exceed it |
| `FORBIDDEN` | Task-specific forbidden actions on top of the standing rails | Never shortened to save tokens |
| `VALIDATION` | Exact commands in order (scoped ruff/format, targeted tests, logged full suite when required, `git diff --check`) | Full suite only via `scripts/crypto_core/run_full_tests_logged.ps1` |
| `STOP_WITH_PROOF` | Enumerated stop conditions | Stopping with proof always beats improvising |
| `REPORT_FORMAT` | Exact field list the reply must return | Verdict first; failure tails only; no full logs |

## 2. Model-specific prompting rules

### 2.1 GPT-5.6 Sol — scarce T4 cross-contract reasoning

- **Best tasks:** trust-boundary design/audit, governance/safety semantics, SM-5/SM-6 design and audit,
  readiness/Deribit provenance, cross-artifact digest/provenance contradictions.
- **Bad tasks:** CI polling, merge mechanics, routine docs, broad local refactors, anything Luna/Terra can do.
- **Required fields:** full anatomy block; a compact READ evidence pack (exact files/symbols, never
  "read the repo"); explicit non-implementation boundary when the task is design/audit-only.
- **Reasoning:** `xhigh` default; `max` only with an explicit controller gate stated in the prompt.
- **Typical validation:** none beyond read-only proof (design/audit produces decisions and P1/P2 findings,
  not diffs); implementation follows in a SEPARATE Terra/Opus prompt.
- **Stop conditions:** evidence pack insufficient; scope forces implementation; governance number missing
  (route to controller); external/current fact needed (route to Deep Research).
- **Anti-patterns:** feeding Sol the whole repo; asking Sol to also implement; spending Sol on a question
  a targeted `rg` answers.

### 2.2 GPT-5.6 Terra — bounded Codex workhorse

- **Best tasks:** exact-file T2 implementation, tests/docs, small deterministic slices, T3 same-branch
  P1/P2 repair, fresh-context pinned-head independent audit.
- **Bad tasks:** unbounded multi-file refactors, ambiguous slicing, cross-contract architecture, mechanics.
- **Required fields:** `ALLOWED_FILES` exact; pinned `main` HEAD; branch name (`feature/<scope>-prN` or
  `chore/<scope>-prN`); full validation ladder; "no merge".
- **Reasoning:** `high` for T2; `xhigh` for T3 repair.
- **Typical validation:** scoped ruff + format, targeted pytest, logged full suite for product code,
  `git diff --check`, exact changed-file proof.
- **Stop conditions:** scope expansion, out-of-scope validation failure, ambiguity not cheaply provable.
- **Anti-patterns:** letting the implementation context "also audit" itself; combining two unrelated slices;
  omitting the regression test for a repair.

### 2.3 GPT-5.6 Luna — mechanics only

- **Best tasks:** git/gh state snapshots, bounded CI polling, PR metadata (only explicitly authorized),
  review-thread status, authorized standard merge + postverify command running.
- **Bad tasks:** any design, any feature/test code, any audit judgment, thread resolution decisions.
- **Required fields:** exact PR/head; the exact commands; the authorization line when the task mutates
  anything (metadata/merge).
- **Reasoning:** `none`/`low` — never higher.
- **Typical validation:** the command output itself is the deliverable (terminal-or-pending proof).
- **Stop conditions:** state mismatch vs pinned expectation; missing authorization; non-terminal checks
  when the task requires terminal.
- **Anti-patterns:** watch/poll loops (`--watch`); "while you're there" code edits; treating a pending
  check as green.

### 2.4 Claude Opus 4.8 — heavy local executor

- **Best tasks:** large-but-bounded local implementation/refactor, broad bounded reads, long validation
  loops, forensic debugging — preserving Codex capacity.
- **Bad tasks:** status/CI polling, PR metadata, trivial docs, anything mechanical.
- **Required fields:** full anatomy block; named broad-but-bounded file set; note that a separate
  fresh-context Terra/Sol audit is still required before the connector gate for high-risk work.
- **Reasoning:** `xhigh` for contract/digest/fail-closed work; `high` for ordinary bounded slices.
- **Typical validation:** full ladder including the logged full suite.
- **Stop conditions:** same as Terra plus token/context budget making correctness uncertain.
- **Anti-patterns:** using Opus as a reviewer of its own diff; unbounded "improve the repo" pursuits.

### 2.5 Claude Sonnet 5 — runtime-proven fallback only

- **Doctrine:** availability and capability are NEVER assumed. Use only when the active local setup
  runtime-proves it (the session itself reports the model id) AND the controller explicitly routes it.
  No unsupported quality claim; no plan may depend on it.
- **Best tasks (when proven):** mechanical/low-risk lanes — status proof, bounded read-only checks,
  low-risk docs mechanics — as a declared fallback when Luna-class capacity is unavailable.
- **Bad tasks:** T3/T4 contract, digest, fail-closed, or audit work.
- **Required fields:** full anatomy block with `MODEL_ACTUAL` runtime print; explicit
  `EXACT_MODEL_REQUIRED` decision; declared fallback path.
- **Reasoning:** `low` (mechanical) / `high` at most.
- **Stop conditions:** model id not runtime-proven; task class above T1 without controller authorization.
- **Anti-patterns:** assuming Sonnet 5 exists in the installed CLI; silently substituting it for a
  required exact model.

### 2.6 Claude Fable 5 — opportunistic runtime-proven T4 audit lane

- **Doctrine:** availability is NOT assumed (post-2026-07-07). Use only while the running session
  runtime-proves `claude-fable-5`. Never a contractual dependency: no plan, schedule, or roadmap step may
  require it. When the window closes, nothing may break.
- **Best tasks:** full-repo adversarial audit, cross-contract second-opinion design/audit (vendor-diverse
  complement to a Codex audit — it does not REPLACE a required independent Codex audit), setup/workflow
  stress test, final semantic review of hard contracts.
- **Bad tasks:** CI polling, PR metadata, routine bounded implementation, large local refactors (Opus
  lane), mechanics of any kind.
- **Required fields:** full anatomy block with `EXACT_MODEL_REQUIRED: true` and a mandatory
  runtime-proof print of `MODEL_ACTUAL` before any work; STOP_WITH_PROOF on mismatch (no silent
  Opus/Sonnet fallback when exactness is required).
- **Reasoning:** highest available; report as configured without overclaiming what cannot be proven.
- **Stop conditions:** model mismatch; audit would require source edits; uncited external claims needed.
- **Anti-patterns:** "Fable said so" as proof (model strength is never proof); scheduling future work that
  assumes Fable availability; spending the window on anything below T4 value.

### 2.7 ChatGPT controller

- **Role:** sequence owner — final evidence comparison, verdict, next prompt, per-PR merge authorization.
- **Best tasks:** comparing executor reports against live GitHub state, issuing repair/merge/next-slice
  decisions, owning governance numbers.
- **Bad tasks:** direct implementation; trusting any report without connector/`gh` verification.
- **Prompting rule:** executor reports TO the controller must be compact, evidence-first, and end with one
  next safe action — never a menu of options the controller must re-derive.
- **Stop conditions:** none delegated — the controller IS the human-side gate; merge authorization must
  name the PR and the exact command.

### 2.8 GitHub connector / gh — final gate

- **Role:** source-of-truth read-only verification before merge authorization.
- **Checklist (never waived):** PR open/non-draft; head SHA pinned and unchanged; exact changed files;
  checks terminal (pending/queued/in-progress/no-checks = `NOT_READY`); reviews/threads state (current
  valid P1/P2 block); code scanning; one-open-PR rule.
- **Output:** `READY_FOR_MERGE_AUTHORIZATION` or `NOT_READY` with proof. No mutation.
- **Anti-patterns:** substituting an executor's memory of CI for a fresh snapshot; merging on
  `mergeable=MERGEABLE` alone.

### 2.9 Deep Research — external facts only

- **Best tasks:** venue APIs, fees, funding/basis mechanics, rate limits, custody/regulatory facts,
  machine-time source facts — anything not derivable from the repo.
- **Bad tasks:** repo-state questions, design decisions, anything an `rg` answers.
- **Required fields:** the exact current question; required source citations; the
  `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` / `INFERENCE` / `UNKNOWN` separation.
- **Stop conditions:** cited research unavailable → facts stay `UNPROVEN`; never guessed.
- **Anti-patterns:** treating DR output as merge authority or repo proof; implementing directly from an
  uncited claim.

### 2.10 Codex Pursue Goal — bounded terminal loop

- **Best tasks:** single-goal preflight, repo/branch sync, CI/status snapshot loops with terminal
  `PASS`/`FAIL`/`BLOCKED`, closeout, explicitly authorized merge/postverify.
- **Bad tasks:** broad repo pursuit, unscoped design/implementation, ambiguous multi-goal missions.
- **Required fields:** ONE goal; terminal condition; bounded iteration count/timeout; forbidden list.
- **Stop conditions:** goal ambiguity; any need to patch; authorization boundary.
- **Anti-patterns:** "pursue improving the repo"; letting a status loop mutate anything.

## 3. Low-prompt / maximum-work doctrine

- Prefer ONE strong bounded prompt (read + patch + targeted tests + full suite + scope gate + commit/push
  + PR + bounded CI snapshot + report) over many fragment prompts. Stable doctrine lives in docs/skills —
  prompts carry only the task delta.
- **Never combine:** implementation + its own independent audit in one context; merge + next feature in
  one prompt; two unrelated slices in one PR; setup/doctrine changes inside a feature PR.
- **Never skip:** the fresh-context independent audit for high-risk work; the connector final gate;
  explicit per-PR human merge authorization; post-merge verification with zero-open-PR proof.
- Batch by theme, stop at gates: push-and-stop or stop-with-proof beats widening scope.

## 4. Independent audit doctrine

- An implementation context CANNOT self-satisfy the independent audit gate — audit prompts are
  fresh-context and pinned-head (PR head SHA named in the prompt).
- P1/P2-sensitive PRs (digest/provenance, fail-closed, trust-boundary, governance) require the audit
  BEFORE the connector gate. Current valid P1/P2 threads block; human threads are never self-resolved.
- A Fable 5 second opinion (while runtime-proven) ADDS vendor diversity; it never replaces a required
  independent Codex audit.

## 5. Example prompt skeletons

Copy, then fill. Every skeleton implicitly starts with the section-1 anatomy block; only deltas shown.

### 5.1 Sol — SM-5 design

```text
ROLE: independent T4 designer. TASK_CLASS: T4 SOL_CROSS_CONTRACT.
MODEL_REQUESTED: GPT-5.6 Sol. REASONING_REQUESTED: xhigh. EXACT_MODEL_REQUIRED: true.
STATE_PROOF: main @ <sha>, clean, open PRs [].
READ: docs/crypto_core/secondary_metrics_enforcement_design.md;
  src/crypto_core/validation/{secondary_metrics_policy,trade_record_evidence,
  paper_secondary_metrics_evidence,paper_secondary_metrics_substrate_reconciliation,
  paper_secondary_metrics_enforcement_precondition}.py; paper_vs_backtest_methodology.py.
TASK: design paper_vs_backtest_methodology_v2 (enforced=True) consuming the #328 precondition anchor
  (READY + digest re-proof required); define fail-closed matrix, SM-2 threshold binding, SM-6 contract.
FORBIDDEN: implementation, comparator invocation, governance numbers (controller-owned), merge/CI work.
REPORT: decisions, invariants, P1/P2 risks, exact next implementation slice.
```

### 5.2 Terra — bounded implementation

```text
ROLE: implementer. TASK_CLASS: T2 TERRA_BOUNDED_CODE.
MODEL_REQUESTED: GPT-5.6 Terra. REASONING_REQUESTED: high. EXACT_MODEL_REQUIRED: false (fallback: Opus, declared).
STATE_PROOF: main @ <sha>, clean, open PRs []. BRANCH: feature/<scope>-prN.
ALLOWED_FILES: src/crypto_core/validation/<module>.py; tests/crypto_core/validation/test_<module>.py.
IMPLEMENT: <exact artifact + invariants + digest-boundary + raise-vs-REJECTED split + structural-False flags>.
VALIDATION: scoped ruff check+format; targeted pytest; run_full_tests_logged.ps1 (PYTEST_EXIT=0); git diff --check.
STOP_WITH_PROOF: scope expansion; out-of-scope failure; invented semantics.
No merge. Report per REPORT-STD.
```

### 5.3 Terra — independent audit

```text
ROLE: independent auditor (fresh context — MUST NOT be the implementation session).
TASK_CLASS: T1/T3. MODEL_REQUESTED: GPT-5.6 Terra. REASONING_REQUESTED: high. EXACT_MODEL_REQUIRED: false.
PINNED: PR #<N> head <sha>; changed files + direct dependencies only.
AUDIT: digest/reseal/provenance; forbidden-surface AST; overclaim flags; fail-closed negative paths; test gaps.
FORBIDDEN: edits, comments, thread resolution, merge.
REPORT: P1/P2/P3 with file:line, readiness verdict, actual model.
```

### 5.4 Luna — CI/status snapshot

```text
ROLE: mechanical executor. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna.
REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: false (fallback: terminal/gh).
TASK: one-shot snapshot of PR #<N> (head <sha>): statusCheckRollup + run-level cross-check.
RULE: pending/queued/in_progress/no-checks = NOT_READY; never --watch; no code/design/merge.
REPORT: terminal-or-pending proof only.
```

### 5.5 Opus 4.8 — heavy local implementation

```text
ROLE: heavy local implementer. TASK_CLASS: T3 TERRA_REPAIR_OR_OPUS_HEAVY.
MODEL_REQUESTED: Claude Opus 4.8. REASONING_REQUESTED: xhigh. EXACT_MODEL_REQUIRED: false.
STATE_PROOF: main @ <sha>, clean, open PRs []. BRANCH: feature/<scope>-prN.
SCOPE: named broad-but-bounded file set <paths>; long validation loops allowed.
VALIDATION: full ladder incl. run_full_tests_logged.ps1.
NOTE: separate fresh-context Terra/Sol audit still required before connector gate. No merge.
```

### 5.6 Fable 5 — full-repo audit (runtime-proven window)

```text
ROLE: full-repo adversarial auditor. TASK_CLASS: T4.
MODEL_REQUESTED: Claude Fable 5. REASONING_REQUESTED: highest available. EXACT_MODEL_REQUIRED: true.
VERIFY FIRST: print MODEL_ACTUAL from runtime; if not claude-fable-5 → STOP_WITH_PROOF (no fallback).
TASK: read-only audit of <areas>; severity P1/P2/P3; no edits/commits/PRs/merge.
REPORT: per-area verdicts, blockers, single recommended next PR + lane.
```

### 5.7 Fable 5 — second-opinion audit

```text
ROLE: second-opinion auditor (vendor-diverse; does NOT replace the required Codex audit).
TASK_CLASS: T4. MODEL_REQUESTED: Claude Fable 5. EXACT_MODEL_REQUIRED: true (verify runtime first).
PINNED: design doc / PR head <sha>. READ: <exact evidence pack>.
TASK: challenge the primary design/audit — missing invariants, digest/provenance holes, overclaim risk.
FORBIDDEN: implementation, merge, availability assumptions beyond this session.
REPORT: AGREE/DISAGREE per finding + new P1/P2 + exact evidence.
```

### 5.8 Sonnet 5 — mechanical fallback (only if runtime-proven)

```text
ROLE: mechanical executor (fallback lane). TASK_CLASS: T0/T1.
MODEL_REQUESTED: Claude Sonnet 5. REASONING_REQUESTED: low. EXACT_MODEL_REQUIRED: true.
VERIFY FIRST: print MODEL_ACTUAL from runtime; if not a proven Sonnet 5 id → STOP_WITH_PROOF.
TASK: <status proof | bounded read-only check | low-risk docs mechanics>.
RULE: no T2+ work; no capability claims beyond what this session proves.
```

### 5.9 Codex Pursue Goal — bounded preflight

```text
GOAL (single): prove repo preflight for <task> — fetch/prune, main == origin/main, clean tree,
open PRs [], expected head <sha>. TERMINAL: PASS (all proven) | FAIL (mismatch, with output) |
BLOCKED (needs authorization). BOUNDS: <=N iterations, no patching, no design, no merge, read-only
git/gh only.
```

### 5.10 GitHub connector — final gate checklist

```text
LANE:CONNECTOR_FINAL_GATE for PR #<N>:
[] open + non-draft        [] head == <pinned sha>      [] changed files == <exact list>
[] checks ALL terminal-success (slow-tests SKIPPED-by-schedule acceptable; pending = NOT_READY)
[] reviews/threads: zero current valid P1/P2 unresolved   [] code scanning clean
[] exactly one open PR     [] base == main
OUTPUT: READY_FOR_MERGE_AUTHORIZATION | NOT_READY (+proof). No mutation. Human merge auth still required.
```

## 6. Non-regression

This guide changes prompting ergonomics only. It does not alter: one open PR; no direct `main` push;
standard merge only; explicit per-PR human merge authorization; pending CI = `NOT_READY`; current valid
P1/P2 threads block; independent audit requirements; connector final gate; post-merge verification;
crypto_core-only scope; paper-first/fail-closed/deterministic rails; and every non-claim in
`agent_workflow.md` section 23.4.
