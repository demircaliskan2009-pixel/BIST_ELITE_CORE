# Token Efficiency Playbook (crypto_core agents)

Purpose: use the lowest capable lane without weakening proof, audit depth, deterministic behavior, or merge
discipline. Token savings are never evidence; research economy never outranks factual accuracy. Active
doctrine: `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`).

## 1. Context budgets per task class

Lane and effort selection is NOT restated here. The single `AUTHORITATIVE_ROUTING_MATRIX` (class → lane →
model id → effort) is `agent_workflow.md` section 24.3, and the effort/thinking architecture is section
24.12. This table adds only the context budget for each class.

| Class | Context budget |
|---|---|
| T0 `LUNA_MECHANICAL` | `MINIMAL` — exact commands; no design inference or source scan unless necessary for the stated proof |
| T1 `READONLY_OR_FAST_BOUNDED` | `MINIMAL` — named docs and direct dependencies only |
| T2 `BOUNDED_IMPLEMENTATION` | `BOUNDED` — controller packet first; named files plus immediate dependency interfaces; targeted validation; one PR |
| T3A `COMPLEX_IMPLEMENTATION` | `BROAD_BUT_BOUNDED` — authoritative setup files, affected production/test files, immediate dependency interfaces, current PR/main evidence; explicit invariants and regression proof; no token shortcut |
| T3B `CAPABILITY_CRITICAL_IMPLEMENTATION_OR_REPAIR` | `BROAD_BUT_BOUNDED` — as T3A plus the exact protected-trigger evidence and readiness/connector baseline before and after |
| T3C `CODE_REVIEW_AND_BUG_FINDING` | `BOUNDED` when focused (<= 2 files); `BROAD_BUT_BOUNDED` for broad/security review — named modules plus immediate dependency interfaces |
| T3D `ARCHITECTURE_AND_NEXT_SLICE` | `BROAD_BUT_BOUNDED` — pinned state, candidate slices, their direct dependencies; no repository-wide sweep |
| T3E `COMPLEX_PROMPT_ARCHITECTURE` | `BROAD_BUT_BOUNDED` — only the archaeology needed to pin invariants and prior decisions |
| T4 `CROSS_CONTRACT_DESIGN_OR_AUDIT` | Controller-prepared narrow evidence packet only |
| XR `DEEP_RESEARCH_EXTERNAL` | Connector-bound packet; citations required; unverifiable facts stay `UNPROVEN` |
| `CONTROLLER_CONNECTOR_GATE` | Fresh head/files/checks/threads proof |

Expand a budget only on progressive disclosure — an unresolved reference, an invariant crossing modules, a
test-exposed dependency, or architecture that cannot be proven locally — and state why. Never automatically
read the whole repository, every historical lesson, unrelated modules, stale archives, old prompts, or
generated output.

## 2. Controller preprocessing (primary token saver)

1. ChatGPT proves repo state via connector ONCE and pins it into the packet; executors do not repeat broad
   GitHub discovery.
2. The CONTROLLER_TO_IMPLEMENTER packet carries the exact read set, symbol map, allowed files, invariants,
   protected-risk class, validation ladder, and stops — implementers start from it.
3. Pre-Astra triage: the controller finishes all safely controller-owned work in its zero-count protected
   preflight and sends GPT-6 Astra only a `PROTECTED_AUDIT_PACKET_V2` on a stabilized head (section 24.4) — never
   chat-history recovery and never discovery the controller can do.
4. Handoff reuse: downstream lanes consume the prior `AGENT_OS_HANDOFF_V1` packet instead of re-deriving it;
   accepted state lives with the controller, never re-proved by memory.
5. Executors still prove their own LOCAL facts (git state, clean tree, tests) — controller packets never
   replace local proof.

## 3. Context intake protocol (executors)

1. Prove local repo state first with one `git`/`gh` snapshot; never from memory.
2. Name the intended read set before reading and justify any expansion.
3. Read changed files and symbols before whole repositories; build one source surface map.
4. Do not reread unchanged docs after a stable head proof; do not duplicate reads the packet already proves.
5. Stop with proof rather than broadening a scan to compensate for missing information.

## 4. Report compression

Reports are `AGENT_OS_HANDOFF_V1` packets: fixed fields, verdict first, failure tails only, evidence vs
inference separated, missing facts `UNKNOWN`/`N/A`, exactly one next safe action. Always include
`MODEL_REQUESTED`, `MODEL_ACTUAL`, `REASONING_REQUESTED`, `REASONING_ACTUAL`, `EXACT_MODEL_REQUIRED`,
fallback, and the `SETUP_*` block.

## 5. Model selection and proof

Lane selection is section 24.3 and 24.4, never restated here: the controller does every read-only task it safely
can and accepts non-protected candidates; Claude Opus 5.5 carries implementation, repair and the repo-native work
of that task; GPT-6 Astra is spent on protected acceptance only; Codex GPT-5.6 Sol runs only on a recorded reserve
gap (`QUOTA_ROUTING_IS_ADAPTIVE` / `QUALITY_BAR_IS_CONSTANT`, §24.10). Effort is chosen per workflow §24.12: `xhigh` is the normal
Opus 5.5 coding default, `max` only on an explicit T3B trigger, review at `medium`/`high`/`xhigh` by breadth.
Claude Sonnet 5 is `NOT_IN_ACTIVE_COUNCIL` (§24.3) and is neither a lane nor a fallback, and no superseded
Claude lane is one either; use measured session/harness cost, never hard-coded price
rankings. The Claude mutation lane requires the exact model id (`claude-opus-5-5`) — an
unresolved alias is not proof — plus session-level proof of the actual effort; if
`EXACT_MODEL_REQUIRED=true`, requested/actual mismatch stops before mutation, and a human effort waiver is
recorded with the TRUE actual value. Never claim unavailable-model quality. Model selection does not prove
safety, repo state, or results.
Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a lane or fallback; pre-v5.2 Fable-era contracts stay
archived in `fable_exit_contract_index.md` and are never routing.

## 6. Codex quota economy

The shared Codex quota is spent on protected acceptance and on recorded reserve gaps only. Which candidates are
protected is the finite `PROTECTED_TRIGGER_MATRIX_V2` of section 24.4 alone — not restated here. A non-protected
candidate costs zero Astra executions; a protected one costs one compact Astra audit (and at most one re-audit),
prepared by the controller preflight so Astra never spends quota on discovery or on a head already known to be
defective. Codex capacity is preserved by classifying, preparing and stabilizing, never by weakening the gate.

## 7. Execution budget

Section 24.8 alone (`HARD_FIVE_EXECUTION_BUDGET`): one budget of at most five meaningful prompts, in which every
implementation, acceptance audit, repair, re-audit and challenge counts, and no execution six. Never split
coherent work into micro-prompts unless a stop condition fires;
never combine implementation with its own audit, merge with next feature, research with mutation, or two
PRs/implementers.

## 8. Deep Research economy and freshness

Event-triggered only (triggers in `deep_research_protocol.md`); never mechanical per-PR or calendar-driven
research; never for repo-native facts. Reuse a prior result only when the question is materially unchanged,
relevant repo state is unchanged or accounted for, source versions are current, the research date is
acceptable for the fact class, and no conflicting evidence appeared. Refresh immediately on API/pricing/
regulation/framework changes, phase or question changes, load-bearing `UNKNOWN`s, or before authorizing a
current external decision. Research output pins its date, repo state, source versions, reusable vs stale vs
UNKNOWN findings, and its refresh trigger. Research savings never outrank factual accuracy.

## 9. Anti-patterns

- Full-file reads where a symbol search answers the question; duplicate discovery already in the packet.
- Sol/Opus status polling, implementer self-review, unavailable-model claims, unproven Sonnet 5 routing.
- Routing everything to Opus 5.5, or every Opus task to `max`; `max` without a named T3B trigger.
- Generic re-verification loops ("double-check everything") in place of the deterministic gate ladder;
  rerunning a passed gate on an unchanged head; subagents for polling, routine commands or small patches.
- Spending Codex on questions the connector already answered; broad Codex repo reads without justification;
  dispatching Astra for a non-protected candidate, an unstable head or discovery; a challenge by reflex.
- Broad scans, full logs, duplicate doctrine, `product/*` branch templates, per-PR reflex research.

## 10. Non-regression checks

One open PR; one repository writer at a time; no direct `main` push; standard merge only; no merge without
explicit human authorization; pending CI = `NOT_READY`; current valid P1/P2 threads block; GPT-6 Astra as the
sole protected acceptance, never reassigned; connector final gate never waived; postmerge verification before
next work; crypto_core-only; no BIST, live/private API, orders, scheduler, readiness transition,
shadow/live, or capital mutation.

## 11. No-overclaim

Nothing in this playbook proves repo/PR/CI state, Stage-4 completion, machine-time origin, secondary-metrics
enforcement, readiness, or edge/profitability. Compact reports retain identical proof density.
