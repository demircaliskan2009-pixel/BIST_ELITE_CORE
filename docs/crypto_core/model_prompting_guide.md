# crypto_core Model Prompting Guide (v2, 2026-07-10 — Agent OS edition)

Durable authoring guide for every active model/tool lane in `CRYPTO_CORE_AGENT_OS_V1`
(`docs/crypto_core/agent_workflow.md` section 24 — the routing authority; this guide teaches how to WRITE
prompts for it and never overrides it). Companion lanes: `token_efficiency_v2.md`; budgets:
`token_efficiency_playbook.md`; research: `deep_research_protocol.md`. On any apparent conflict, section 24
and the stricter safety rule win.

Active lanes covered (eight): ChatGPT GPT-5.6 Thinking (read-only-first controller-auditor,
`CONTROLLER_READONLY_FIRST_POLICY`), GitHub connector, Deep Research, Claude Opus 5 (`claude-opus-5`,
default heavy executor), Claude Sonnet 5 (`claude-sonnet-5`, runtime-proven only), Codex GPT-5.6 Sol,
Codex GPT-5.6 Terra, Codex GPT-5.6 Luna. Claude Opus 4.8 is `SUPERSEDED_BY_OPUS_5` — historical only.
Claude Code local sessions are the primary local execution environment for the Claude lanes; Codex
Sol/Terra/Luna are separate local sessions. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — not an active or
routable lane; pre-v5.2 Fable material lives in `fable_exit_contract_index.md` and workflow sections 20-23
under explicit HISTORICAL/SUPERSEDED/ARCHIVAL labels only. Copilot-specific repository assets are historical
compatibility material and are not an available or routable lane in the current environment.
Nothing in this guide proves repo state, authorizes a merge, or affects the blocker
`secondary_comparison_metrics_hit_fill_slippage_declared_not_enforced_v1` (that closes only through its own
audited SM-5/SM-6 gates).

## 1. Prompt anatomy standard

Every serious prompt carries, in order: `ROLE` (one role — never implementation + independent audit
together), `TASK_CLASS` (T0-T4/XR/CONTROLLER_CONNECTOR_GATE — classify BEFORE picking the model),
`MODEL_REQUESTED`, `REASONING_REQUESTED`, `EXACT_MODEL_REQUIRED`, `MODEL_ACTUAL` + `REASONING_ACTUAL`
(printed FIRST by the executor from runtime proof), `SETUP_REQUESTED` / `SETUP_ACTUAL` / `SETUP_FILES_READ`
/ `SETUP_GAPS` (`SETUP_LOAD_CONTRACT_V1` — never claim setup loading without proof), `PROFILE`
(`CRYPTO_CORE_DOMAIN_OPERATING_PROFILE` — institutional crypto trading systems engineering, never generic
coding), `STATE_PROOF` (pinned main/PR/head; executor re-proves local facts), `SCOPE / ALLOWED_FILES`
(exact), `FORBIDDEN` (task-specific on top of standing rails — never shortened), `VALIDATION` (exact ladder;
full suite only via `run_full_tests_logged.ps1`), `STOP_WITH_PROOF` (enumerated), and
`REPORT: AGENT_OS_HANDOFF_V1` (workflow section 24.6; one next safe action; failure tails only).

## 2. Lane-by-lane rules and skeletons

### 2.1 ChatGPT GPT-5.6 Thinking — controller

- **Identity:** `GPT-5.6 Thinking` — never labeled Codex `GPT-5.6 Sol`; family similarity is not identity.
- **Best tasks:** sequence control; live GitHub evidence comparison; surface mapping; design synthesis;
  prompt/implementation-contract construction; Class-A independent audit; Class-B first-pass triage;
  pre-Codex triage; executor-report verification; connector final gate; Deep Research orchestration and
  verification; next-slice selection; explicitly authorized GitHub actions.
- **Bad tasks:** substituting for local tests or unverified repo state; replacing Class-C Codex audit;
  direct-main implementation; guessing state from memory.
- **Setup:** active doctrine (AGENTS.md + workflow section 24), this guide, live pinned connector evidence,
  task-specific surfaces.
- **Reasoning:** full deliberation for design/triage; mechanics delegated to Luna.
- **Validation:** every executor claim re-checked against live connector evidence; accepted state updated
  only from verified evidence (`CONTROLLER_ACCEPTED_STATE`, conflict precedence in section 24.5).
- **Stops:** insufficient evidence → HANDOFF_UNKNOWN; protected trigger → Class C; external fact → XR.
- **Handoff:** CONTROLLER_TO_IMPLEMENTER / CONTROLLER_TO_AUDITOR / CONTROLLER_TO_DEEP_RESEARCH packets.
- **Anti-patterns:** trusting a report because it is detailed; auditing product trust boundaries alone;
  merging on `mergeable` alone; issuing two writers at once.

```text
LANE:CONTROLLER_DESIGN_SYNTHESIS. STATE: main@<sha>, open PRs [].
EVIDENCE: <pinned files/symbols read via connector>. TASK: produce one bounded PR contract for <objective>:
invariants, fail-closed matrix, raise-vs-REJECTED, allowed files, negative tests, validation ladder, stops,
protected-risk class (A/B/C), CODEX_REQUIRED decision + trigger checklist, implementer lane selection.
FORBIDDEN: implementation, mutation, research execution. OUTPUT: CONTROLLER_TO_IMPLEMENTER packet.
```

Controller read-only-first skeletons (`CONTROLLER_READONLY_FIRST_POLICY`, workflow section 24.10):

```text
LANE:CONTROLLER_REPO_READONLY_AUDIT. STATE: live main@<sha> (connector-proven), open PRs <count>.
TASK: read-only repository/setup/workflow/architecture consistency audit of <areas> via GitHub connector —
tracked-file + dependency surface map, model-routing/lane consistency, stale-state/drift detection, exact
evidence vs inference. SEVERITY: P1/P2/P3. FORBIDDEN: edits, commits, PRs, merge, product implementation,
replacing Class-C Sol, treating memory as repo state. OUTPUT: read-only audit handoff + one next safe action.
```

```text
LANE:CONTROLLER_CLASS_A_AUDIT for PR #<N> (docs/setup/prompt/skill/workflow/low-risk CI/helper-script only):
fresh pinned-head reread, complete patch, exact files == <list>, terminal CI, CodeQL, review/thread state,
no product source, no protected trigger, P1/P2/P3 classification, explicit "why Class A". Connector final
gate + explicit human merge authorization stay separate. OUTPUT: AUDIT_ACCEPTED | REPAIR_REQUIRED | UNKNOWN.
```

```text
LANE:CONTROLLER_CLASS_B_AUDIT for PR #<N> (ordinary bounded product code): source/test + dependency map,
negative-test check, fail-closed first pass, CI/CodeQL, full protected-trigger checklist. Controller-only
closeout only when every no-Codex criterion is proven; else CODEX_REQUIRED: YES → Terra ordinary audit /
escalate to Class C on any uncertainty. FORBIDDEN: implementation, merge, replacing Class-C Sol.
OUTPUT: AUDIT_ACCEPTED | TERRA_AUDIT_REQUIRED | ESCALATE_CLASS_C (+ exact reason + trigger checklist).
```

```text
LANE:CONTROLLER_RESEARCH_VERIFICATION. PACKET: <DEEP_RESEARCH_TO_CONTROLLER handoff>.
TASK: verify every repo claim against live connector evidence, inspect load-bearing citations, separate
facts/inference/UNKNOWN, check stricter-safety override, decide ACCEPT/REPAIR/REJECT/FOLLOWUP, convert
accepted findings into at most ONE bounded next-PR proposal. FORBIDDEN: mutation, merge authority, upgrading
UNKNOWN to fact. OUTPUT: research-verification handoff.
```

### 2.2 GitHub connector — evidence and explicitly authorized actions

- **Best tasks:** pinned-ref reads (files/patches/changed files/commits/runs/jobs/logs/CodeQL/reviews/
  threads/open-PR count/merge commits/search); final-gate verification; post-merge state proof.
- **Mutation boundary:** ONLY after an explicit human instruction naming exact action + target (standard
  merge, metadata, label, reviewer, draft/ready, comment, guarded thread closeout, bounded workflow rerun);
  re-prove state immediately before; only the named action; re-read result; report proof. Never: direct main
  push, force push, squash/rebase, self-approval, blind retry, unauthorized thread resolution or rerun,
  merge + next feature, blanket mutation from connector availability.
- **Stops:** any pin mismatch → NOT_READY/UNKNOWN.

```text
LANE:CONTROLLER_FINAL_GATE for PR #<N>:
[] open+non-draft  [] base main  [] head == <pinned sha>  [] files == <exact list>
[] required checks terminal success (accepted skips only)  [] CodeQL clean
[] no current valid unresolved P1/P2  [] exactly one open PR  [] no forbidden scope  [] audit class done
OUTPUT: READY_FOR_MERGE_AUTHORIZATION | NOT_READY | UNKNOWN (+proof). No mutation; human merge auth separate.
```

### 2.3 Deep Research — external/current facts (controller-orchestrated)

- **Best tasks (submodes):** `XR_FACT_CHECK` (exchange/Deribit APIs, fees, rate limits, funding, margin,
  liquidation, microstructure, custody/security/regulation, current model/tool behavior);
  `XR_ARCHITECTURE_BENCHMARK` (Hummingbot/Freqtrade/NautilusTrader/QuantConnect LEAN/institutional systems —
  capabilities and evidence, never marketing); `XR_PHASE_GATE_REVIEW` (before material phase transitions
  with external assumptions); `XR_OVERENGINEERING_AUDIT` (artifact proliferation vs end-to-end wiring).
- **Bad tasks:** repo/PR/CI state, threads, local tests, branch hygiene, routine implementation, anything
  an `rg` answers.
- **Setup:** CONTROLLER_TO_DEEP_RESEARCH packet (exact question, why external facts are required, pinned
  main/PR heads, repo files/symbols, benchmark set, primary-source requirements, prohibited weak sources,
  evidence buckets, top-1 claim standard, forbidden mutations, expected output, refresh trigger).
- **Validation:** controller post-research gate — every repo claim connector-checked, load-bearing citations
  inspected, facts/inference separated, doctrine compatibility checked; verdict ACCEPT_RESEARCH /
  REPAIR_RESEARCH / REJECT_RESEARCH / DEEP_RESEARCH_FOLLOWUP_NEEDED; at most ONE bounded next-PR proposal.
- **Stops:** citations unavailable → facts stay UNKNOWN; never guessed, never upgraded.
- **Handoff:** DEEP_RESEARCH_TO_CONTROLLER packet (research date, pinned repo state, source quality,
  REPO_EVIDENCE / EXTERNAL_EVIDENCE / INFERENCE / UNKNOWN, stale findings, bounded recommendations, exact
  next PR proposal, refresh trigger).
- **Anti-patterns:** research as merge authority; calendar-driven research; marketing-quality sources;
  research findings implemented without controller triage.

```text
LANE:DEEP_RESEARCH_<FACT_CHECK|ARCHITECTURE_BENCHMARK|PHASE_GATE|OVERENGINEERING>.
PACKET: <controller research packet with pinned repo state>. QUESTION: <exact current question>.
SOURCES: official/primary first; cite with dates/versions; weak sources flagged, never authoritative.
OUTPUT: DEEP_RESEARCH_TO_CONTROLLER packet. READ-ONLY: no mutation, no merge authority, no gate waiver.
```

### 2.4 Claude Sonnet 5 — runtime-proven bounded implementer

- **Doctrine:** availability/identity NEVER assumed — the session must runtime-prove a Sonnet 5 model id
  AND the controller must explicitly route it. No unsupported capability claim; no plan depends on it.
Model id `claude-sonnet-5`. This is the DEFAULT Claude lane for routine work — the existence of Opus 5 does
not weaken it. Stronger reasoning does not materially improve a status snapshot, an authorized merge, a
config edit or a mechanical fixture, and spending Opus there costs latency, tokens and premium requests for
no correctness gain.

- **Best tasks:** T0 status, polling, git/GitHub hygiene, clean-tree and open-PR proof; T1 bounded reads,
  direct-dependency read-only audit, governed mechanical closeout (authorized standard merge, post-merge
  commands, parent/digest verification, clean-main proof); T2 small/medium deterministic implementation,
  narrow docs, config-only changes, mechanical fixtures and tests, obvious localized repair, PR-body
  corrections, bounded governance closeout.
- **Bad tasks:** protected trust-boundary work, digest/provenance, SM-5/SM-6, Stage-4 completion,
  readiness/live/order/capital, broad forensic refactors, T4 design, mandatory Class-C audits.
- **Setup:** `CLAUDE.md`, `CLAUDE.local.md`, `.claude/skills/crypto-core-token-efficient-loop/SKILL.md`,
  controller-named task files.
- **Effort:** `low` for T0/T1; `medium` for T2 (`high` only when the bounded slice is moderately complex).
- **Prompt shape:** concise, mechanically explicit, low-context, command-oriented, deterministic, bounded;
  explicit terminal-CI polling; explicit escalation triggers; explicit no-scope-expansion rule. Do NOT add
  architecture speculation, repository archaeology, broad alternative analysis, maximum-thinking language,
  long report formats, or Opus-only subagent instructions.
- **Validation:** scoped ruff/format, targeted pytest, logged full suite for product code, `git diff --check`.
- **Stops / escalation:** model id unproven; task class above T2; protected trigger appears; scope
  expansion; conflicting evidence; unexpected ancestry; state cannot be reconciled; merge parents or merged
  scope differ; post-merge validation fails; branch protection behaves unexpectedly; readiness/connector
  transition; interacting semantic invariants; trust-boundary change; unexpected full-suite failure;
  architecture required; repair not provable locally. Escalate to Sonnet 5 `high` first, then Opus 5
  `high`/`xhigh`.
- **Fallback:** Terra for bounded code; Opus 5 for broad/complex work.
- **Anti-patterns:** silent substitution for a required exact model; assuming Sonnet 5 exists in the
  installed CLI; accepting protected work because the diff "looks small"; improvising past an escalation
  trigger instead of stopping.

```text
ROLE: bounded implementer. TASK_CLASS: T2. MODEL_REQUESTED: Claude Sonnet 5.
MODEL_ID_REQUIRED: claude-sonnet-5. REASONING_REQUESTED: medium (high only if moderately complex).
EXACT_MODEL_REQUIRED: true. VERIFY FIRST: print MODEL_ACTUAL from runtime; if not a proven Sonnet 5 id ->
STOP_WITH_PROOF. PACKET: <CONTROLLER_TO_IMPLEMENTER>. ALLOWED_FILES: <exact>. LANE:VALIDATE-STD; LANE:PR-STD.
ESCALATE, do not improvise: interacting invariants | trust-boundary change | unexpected failure |
architecture needed | scope would widen. No merge; LANE:IMPLEMENTER_HANDOFF.
```

### 2.5 Claude Opus 5 — heavy local executor

Model id `claude-opus-5`. Full effort architecture: `agent_workflow.md` section 24.12. Reusable templates
and the prompt-compiler contract: `docs/crypto_core/agent_prompts/opus5_prompting_playbook.md`.

- **Best tasks:** T3A complex/broad-but-bounded implementation, large local refactors, complex fail-closed
  implementation, forensic debugging, long validation loops, multi-file product integration, same-branch
  P1/P2 repair; T3B capability-critical work; T3C code review and bug finding; T3D architecture and
  next-slice selection; T3E complex prompt architecture.
- **Bad tasks:** PR metadata; CI polling; ordinary docs; generic planning; external research; work
  Sonnet/Terra can safely complete; final connector evidence comparison.
- **Setup:** `CLAUDE.md`, `CLAUDE.local.md`, `.claude` loop skill, controller packet, named
  broad-but-bounded file set.
- **Effort:** `xhigh` is the normal coding/agentic default (T3A). `max` only on an explicit T3B trigger —
  cryptographic verification boundaries, readiness/provenance promotion, protocol ambiguity with safety
  consequences, complex trust-boundary repair, post-audit-failure P1/P2 repair, Agent OS/model-routing
  architecture, materially different candidate architectures, unexpected cross-layer failures, or
  controller-designated capability-critical work. Review: `medium` focused, `high` broad,
  `xhigh` multi-trust-boundary. Architecture and prompt design: `high`, `xhigh` when interacting.
  Adaptive thinking stays enabled; never `thinking: disabled` on a T3 lane or with `xhigh`/`max`.
- **Validation:** full ladder incl. logged full suite; local git/test proof is Opus's own responsibility.
  Each gate runs once per unchanged head — no generic re-verification loops.
- **Stops:** model/effort mismatch or fallback before mutation; scope expansion; out-of-scope failure;
  readiness/connector transition; external-fact dependency; token/context budget making correctness
  uncertain.
- **Fallback:** split scope, or Terra only when genuinely bounded. No unavailable-model quality claim.
- **Subagents:** default 0; maximum 2 read-only for genuinely independent substantial tracks; never for
  polling, routine commands, duplicate self-review, or one- or two-file patches.
- **Anti-patterns:** reviewing its own diff as "the audit"; unbounded improve-the-repo pursuits; duplicate
  broad GitHub discovery already in the packet; routing everything to `max`; narrating routine commands.

```text
ROLE: heavy local implementer. TASK_CLASS: T3A. MODEL_REQUESTED: Claude Opus 5.
MODEL_ID_REQUIRED: claude-opus-5. REASONING_REQUESTED: xhigh (max ONLY with a named T3B trigger).
EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL/REASONING_ACTUAL: <print first from runtime; alias is not
proof; mismatch or fallback -> STOP_WITH_PROOF before mutation>.
PACKET: <CONTROLLER_TO_IMPLEMENTER>. STATE: clean main@<sha>; BRANCH feature/<scope>-prN.
SCOPE: <named broad-but-bounded files>; long validation loops allowed. LANE:VALIDATE-STD; LANE:PR-STD.
Deliver exactly the authorized scope; report-and-stop instead of widening. SUBAGENTS: 0.
Protected (Class-C) work gets a separate fresh independent Codex audit — Sol lane for protected
design/audit; Terra covers only ordinary sub-Class-C review; this session's self-review is
SELF_AUDIT_ONLY_NOT_INDEPENDENT. No merge. LANE:IMPLEMENTER_HANDOFF.
```

### 2.6 Codex GPT-5.6 Sol — protected T4 design/audit

- **Best tasks:** protected cross-contract design; digest/provenance/trust-boundary design; SM-5/SM-6 design
  and audit; Stage-4 semantic review; readiness/Deribit design; complex security/CodeQL reasoning.
- **Bad tasks:** broad discovery, mechanics, polling, merge mechanics, routine docs, bounded implementation.
- **Setup:** `AGENTS.md`, `.codex/skills/crypto-core-max-safe/SKILL.md`, the controller-prepared NARROW
  evidence packet (never "read the repo").
- **Reasoning:** xhigh default; `max` only with an explicit controller gate stated in the prompt.
- **Validation:** none beyond read-only proof in audit mode — output is decisions/P1-P2 findings, not diffs.
- **Stops:** packet insufficient; scope forces implementation; governance number missing (controller-owned);
  external fact needed (XR).
- **Handoff:** AUDITOR_TO_CONTROLLER (P1/P2/P3 + exact evidence + repair requirements + readiness class).
- **Anti-patterns:** Sol on questions Terra/connector already answered; design + implementation in one
  prompt; accepting implementer conclusions as premises.

```text
ROLE: protected designer/auditor. TASK_CLASS: T4. MODEL_REQUESTED: GPT-5.6 Sol. REASONING_REQUESTED: xhigh.
EXACT_MODEL_REQUIRED: <true|false>. MODEL_ACTUAL: <print first>.
PACKET: <CONTROLLER_TO_AUDITOR: pinned head, exact changes, direct dependencies, invariants, protected
triggers, adversarial questions>. FORBIDDEN: implementation, discovery beyond packet, CI polling, merge.
OUTPUT: AUDITOR_TO_CONTROLLER handoff.
```

### 2.7 Codex GPT-5.6 Terra — bounded implementer and ordinary independent auditor

- **Best tasks:** T2 exact-file implementation; small deterministic product slices; exact-file tests; T3
  bounded repair; fresh-context ordinary independent audit; source/test semantic review below Class C.
- **Bad tasks:** unbounded refactors, ambiguous slicing, cross-contract architecture, mechanics, auditing
  its own implementation context.
- **Setup:** `AGENTS.md`, `.codex` max-safe skill, controller packet, exact task files.
- **Reasoning:** high for T2; xhigh for T3 repair.
- **Validation:** scoped ruff + targeted pytest + logged full suite for product code + `git diff --check`.
- **Stops:** scope expansion; out-of-scope validation failure; protected trigger → escalate to Class C.
- **Handoff:** IMPLEMENTER_TO_CONTROLLER or AUDITOR_TO_CONTROLLER as roled.
- **Anti-patterns:** self-satisfying the audit gate; two slices per PR; missing regression proof on repair.

```text
ROLE: <implementer|independent auditor - never both>. TASK_CLASS: <T2|T3>.
MODEL_REQUESTED: GPT-5.6 Terra. REASONING_REQUESTED: <high|xhigh>. MODEL_ACTUAL: <print first>.
PACKET: <controller packet>. Implementer: ALLOWED_FILES <exact>; LANE:VALIDATE-STD; LANE:PR-STD; no merge.
Auditor: fresh context, pinned head <sha>, changed files + direct dependencies only; no edits/comments.
OUTPUT: role handoff.
```

### 2.8 Codex GPT-5.6 Luna — mechanics

- **Best tasks:** git/gh snapshots; bounded CI polling; explicitly authorized PR metadata; review-thread
  status; authorized standard merge + postverify command running; Pursue Goal bounded terminal loops
  (preflight/sync/CI/closeout/authorized postverify — single goal, terminal PASS/FAIL/BLOCKED).
- **Bad tasks:** any design, any code, any audit judgment, thread-resolution decisions, broad repo pursuit.
- **Reasoning:** none/low — never higher.
- **Validation:** command output is the deliverable; pending/queued/in-progress/no-checks = NOT_READY.
- **Stops:** state mismatch vs pinned expectation; missing authorization for any mutation.
- **Anti-patterns:** `--watch` loops; "while you're there" edits; treating pending as green.

```text
ROLE: mechanical executor. TASK_CLASS: T0. MODEL_REQUESTED: GPT-5.6 Luna. REASONING_REQUESTED: low.
MODEL_ACTUAL: <print first>. TASK: <exact snapshot|authorized action> for PR #<N> head <sha>.
AUTHORIZATION: <quoted human instruction, if mutating>. No code/design/review/thread resolution.
OUTPUT: terminal-or-pending proof; LANE:HANDOFF-STD.
```

### 2.9 Claude Fable 5 — `INACTIVE_EXPIRED_RETIRED`

Claude Fable 5 (`claude-fable-5`) is retired (workflow section 24.10) and is NOT an active or routable lane:
no `FABLE5_PREMIUM_SURGE_LANE`, no three surge modes, no `FABLE5_JUSTIFICATION_GATE`, no `FABLE5_*` prompt
skeletons or report fields, and no Fable fallback. Author its former work in the surviving lanes instead:
broad-but-bounded T3 implementation → §2.5 Claude Opus 5 (genuinely bounded T2 → §2.4 Sonnet 5 / §2.7
Terra); non-Class-C read-only architecture / contradiction / full-repo consistency analysis → §2.1 ChatGPT
controller read-only-first skeletons (`CONTROLLER_REPO_READONLY_AUDIT`, `CONTROLLER_CLASS_A_AUDIT`,
`CONTROLLER_CLASS_B_AUDIT`); protected Class-C design/audit → §2.6 Codex Sol; external/current facts → §2.3
Deep Research. Pre-v5.2 Fable prompts survive only as HISTORICAL/ARCHIVAL evidence in
`fable_exit_contract_index.md` and are never re-issued as active prompts.

## 3. Low-prompt / maximum-work doctrine

One strong bounded prompt does the whole safe arc (precheck → reads → patch → targeted + logged-full
validation → scoped commit → push → one PR → bounded CI snapshot → handoff), then stops at the gate. Budgets
(`LOW_PROMPT_MAXIMUM_WORK_POLICY`, section 24.8): Class A = 1 executor prompt + controller audit + human
authorization + mechanical merge/postverify; Class B = 1 implementation + 1 controller audit/triage
(+ optional Terra audit; ≤1 consolidated repair before re-audit); Class C = 1 implementation + 1 focused
Codex audit + ≤1 consolidated same-branch repair per cycle + re-audit only on material head change + 1
mechanical merge/postverify. Never combine: implementation + its independent audit; merge + next feature;
unrelated slices; setup + product code; research + mutation; two implementers; two PRs; final gate +
unauthorized merge. Never skip: required independent audit, connector final gate, explicit human merge
authorization, post-merge verification.

## 4. Independent audit doctrine

An implementation context CANNOT self-satisfy the independent audit gate. Audit prompts are fresh-context
and pinned-head. Under `CONTROLLER_READONLY_FIRST_POLICY` (section 24.10) Class A closes with the ChatGPT
controller and Class B is controller-first (ChatGPT read-only audit; Terra ordinary audit added only when
evidence is incomplete, semantic independence is materially useful, or controller uncertainty remains);
Class C (protected list in section 24.4) always gets a fresh independent Codex Sol audit BEFORE the connector
gate — neither ChatGPT, Claude, nor implementer self-review may replace it. Current valid P1/P2 threads
block; human threads are never self-resolved.

## 5. Audit class decision tree

1. Docs/setup/prompt/skill/workflow/low-risk CI config/helper script only? → **Class A** (controller audit).
2. Product code touched → any protected trigger (digest/serialization/anchors, reseal/provenance,
   mutable/TOCTOU, denominator/record-set, replay defense, Decimal/Fraction finance, governance thresholds,
   trust transitions, READY/ADMITTED/ACCEPTED, SM-5/SM-6, Stage-4, machine-time, readiness/Deribit,
   live/orders/scheduler/shadow/capital, edge/profitability, complex security, current P1/P2 findings)?
   → **Class C** (Codex mandatory).
3. No trigger + controller evidence sufficient? → **Class B** (controller-first; Terra audit if needed;
   `CODEX_REQUIRED: NO` must carry the exact reason + full trigger checklist).
4. Any uncertainty anywhere? → **Class C**.

## 6. Research packet, output contract, freshness

CONTROLLER_TO_DEEP_RESEARCH packet fields: RESEARCH_QUESTION, WHY_CURRENT_EXTERNAL_FACTS_ARE_REQUIRED, REPO,
PINNED_MAIN_SHA, PINNED_PR_HEADS, OPEN_PR_STATE, REPO_FILES_TO_READ, REPO_SYMBOLS_TO_INSPECT,
EXTERNAL_BENCHMARK_SET, PRIMARY_SOURCE_REQUIREMENTS, PROHIBITED_WEAK_SOURCES, EVIDENCE_BUCKETS,
TOP1_CLAIM_STANDARD, FORBIDDEN_MUTATIONS, EXPECTED_OUTPUT, CONTROLLER_POST_RESEARCH_CHECKS.
DEEP_RESEARCH_TO_CONTROLLER output: RESULT, VERDICT, RESEARCH_MODE, RESEARCH_DATE, SOURCE_QUALITY,
PINNED_REPO_STATE, REPO_EVIDENCE, EXTERNAL_EVIDENCE, WHAT_IS_PROVEN, WHAT_IS_INFERRED, WHAT_IS_UNKNOWN,
STALE_PRIOR_FINDINGS, OVERENGINEERING_AUDIT, PRD_ALIGNMENT, TOP1_IMPLICATION, RISKS,
BOUNDED_RECOMMENDATIONS, EXACT_NEXT_PR_PROPOSAL, WHAT_MUST_NOT_CHANGE, REFRESH_TRIGGER,
CONTROLLER_VERIFICATION_REQUIRED, DEEP_RESEARCH_FOLLOWUP_NEEDED. Freshness: reuse only when the question,
relevant repo state, and source versions are materially unchanged and the research date fits the fact class;
refresh immediately on API/pricing/regulation/framework changes, phase/question changes, load-bearing
UNKNOWNs, or before authorizing a current external decision. Post-research controller gate: verify repo
claims via connector, inspect load-bearing citations, separate facts from inference, reject unsupported
claims, check stricter-safety override, decide ACCEPT/REPAIR/REJECT/FOLLOWUP, convert accepted findings into
at most ONE bounded next-PR proposal — never merge authorization.

## 7. Non-regression

This guide changes prompting ergonomics only. It does not alter: one open PR; one repository writer; no
direct `main` push; standard merge only; explicit per-PR human merge authorization; pending CI = NOT_READY;
current valid P1/P2 threads block; Class-C Codex audit; connector final gate; post-merge verification;
crypto_core-only scope; paper-first/fail-closed/deterministic rails; every non-claim in workflow section
24.11; and the validity of the SM blocker until its own gates close it.
