# Token Efficiency Playbook (crypto_core agents)

Purpose: use the lowest capable lane without weakening proof, audit depth, deterministic behavior, or merge
discipline. Token savings are never evidence; research economy never outranks factual accuracy. Active
doctrine: `docs/crypto_core/agent_os_v2.md` (`CRYPTO_CORE_AGENT_OS_V2`; token and context efficiency rules
in its section 10), with `agent_workflow.md` section 24 as the inherited class/effort companion.

Agent OS v2 token rules that bind here: do not re-paste stable doctrine into every prompt (load it from the
repository and send only the task delta); do not make downstream lanes redo controller GitHub discovery
unless it is locally required; reuse one closure packet across implementation and audit while still giving
the audit fresh exact-head state; show failure tails, never whole logs; use `CHATGPT_WORK_LANE` when a
persistent workspace, browser or artifact capability materially reduces repeated context reconstruction;
never add a Sonnet, Terra or Luna prompt merely to satisfy a council ceremony; and never sacrifice
correctness to save tokens.

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
3. Pre-Codex triage: the controller removes state/metadata/mechanical questions before any Codex prompt and
   sends only pinned head + exact changes + direct dependencies + unresolved semantic questions.
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

Selection follows `MODEL_EXPECTED_VALUE_PER_TOKEN_POLICY` (workflow §24.10) — lowest capable lane by
expected value per token: Luna or Sonnet 5 `low` for mechanics → runtime-proven Sonnet 5 `medium` or Terra
for bounded T2 work → Opus 5 (default) for broad/complex local T3 work → Sol only for qualifying protected
T4 on a narrow packet; non-Class-C read-only mapping/audit defaults to the ChatGPT read-only-first
controller (`CONTROLLER_READONLY_FIRST_POLICY`). Effort is chosen per workflow §24.12: `xhigh` is the normal
Opus 5 coding default, `max` only on an explicit T3B trigger, review at `medium`/`high`/`xhigh` by breadth.
Sonnet 5 requires runtime proof of availability/identity before any routing (fallback = Terra bounded /
Opus 5 broad, no equivalent-quality claim); use measured session/harness cost, never hard-coded price
rankings. Claude mutation lanes require the exact model id (`claude-opus-5` / `claude-sonnet-5`) — an
unresolved alias is not proof — plus session-level proof of the actual effort; if
`EXACT_MODEL_REQUIRED=true`, requested/actual mismatch stops before mutation, and a human effort waiver is
recorded with the TRUE actual value. Never claim unavailable-model quality. Model selection does not prove
safety, repo state, or results.
Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a lane or fallback; pre-v5.2 Fable-era contracts stay
archived in `fable_exit_contract_index.md` and are never routing.

## 6. Codex reduction matrix

Shifted AWAY from Codex (controller-owned): Class-A docs/setup/config audits; PR metadata and state proof;
workflow/prompt consistency; routine CI state; broad repository discovery; already-proven scope/non-claim
checks; mechanical low-risk audits. RETAINED by Codex (Class C, mandatory, never replaceable): digest/
provenance/serialization/anchors, mutable/TOCTOU, denominator and record-set integrity, replay defense,
Decimal/Fraction finance, governance thresholds, fail-closed trust transitions, READY/ADMITTED/ACCEPTED,
SM-5/SM-6, Stage-4, machine-time, readiness/Deribit, live/order/scheduler/shadow/capital semantics,
edge/profitability claims, complex security, current P1/P2 source findings. Codex capacity is preserved by
narrowing the question, never by weakening the gate.

## 7. Prompt-count budgets (LOW_PROMPT_MAXIMUM_WORK_POLICY)

Class A: 1 executor prompt end-to-end, then controller audit → human merge authorization → mechanical
merge/postverify. Class B: 1 implementation prompt + 1 controller audit/triage (+ Terra audit only when
required; at most 1 consolidated repair prompt before re-audit). Class C: 1 implementation + 1 focused Codex
audit + at most 1 consolidated same-branch repair per audit cycle + re-audit only on material head change +
1 mechanical merge/postverify. Never split coherent work into micro-prompts unless a stop condition fires;
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
- Routing everything to Opus 5, or every Opus task to `max`; `max` without a named T3B trigger.
- Generic re-verification loops ("double-check everything") in place of the deterministic gate ladder;
  rerunning a passed gate on an unchanged head; subagents for polling, routine commands or small patches.
- Spending Codex on questions the connector already answered; broad Codex repo reads without justification.
- Broad scans, full logs, duplicate doctrine, `product/*` branch templates, per-PR reflex research.

## 10. Non-regression checks

One open PR; one repository writer at a time; no direct `main` push; standard merge only; no merge without
explicit human authorization; pending CI = `NOT_READY`; current valid P1/P2 threads block; Class-C
independent Codex audits where required; connector final gate never waived; postmerge verification before
next work; crypto_core-only; no BIST, live/private API, orders, scheduler, readiness transition,
shadow/live, or capital mutation.

## 11. No-overclaim

Nothing in this playbook proves repo/PR/CI state, Stage-4 completion, machine-time origin, secondary-metrics
enforcement, readiness, or edge/profitability. Compact reports retain identical proof density.
