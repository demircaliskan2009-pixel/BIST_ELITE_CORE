# Token Efficiency Playbook (crypto_core agents)

Purpose: use the lowest capable lane without weakening proof, audit depth, deterministic behavior, or merge
discipline. Token savings are never evidence; research economy never outranks factual accuracy. Active
doctrine: `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`).

## 1. Common task classes and context budgets

| Class | Task type | Active lane | Context budget |
|---|---|---|---|
| T0 `LUNA_MECHANICAL` | git/gh state, bounded CI polling, PR metadata, thread status, authorized merge mechanics, postverify | GPT-5.6 Luna, `none`/`low` | Exact commands; no design inference or source scan unless necessary for stated proof |
| T1 `READONLY_OR_FAST_BOUNDED` | ordinary docs, bounded read-only audit, setup proof | Luna low / Terra high / runtime-proven Sonnet 5 | Named docs and direct dependencies only |
| T2 `BOUNDED_IMPLEMENTATION` | exact-file implementation, tests/docs, small deterministic slice, simple repair | Terra high / runtime-proven Sonnet 5 high | Controller packet first; named files; targeted validation; one PR |
| T3 `COMPLEX_IMPLEMENTATION_OR_REPAIR` | broad-but-bounded implementation, large refactors, complex fail-closed work, forensic debug, P1/P2 repair | Opus 4.8 xhigh (default) / Terra xhigh | Explicit invariants and regression proof; no token shortcut |
| T4 `CROSS_CONTRACT_DESIGN_OR_AUDIT` | protected trust boundary, governance, SM-5/SM-6 design, readiness provenance, complex security | GPT-5.6 Sol xhigh; `max` only controller-gated | Controller-prepared narrow evidence packet only |
| XR `DEEP_RESEARCH_EXTERNAL` | external/current facts, benchmarks, phase gates | Deep Research + connector, advisory only | Connector-bound packet; citations required; unverifiable facts stay `UNPROVEN` |
| `CONTROLLER_CONNECTOR_GATE` | final evidence comparison and merge authority | ChatGPT GPT-5.6 Thinking + connector/`gh` | Fresh head/files/checks/threads proof |

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
expected value per token: Luna for mechanics → runtime-proven Sonnet 5 or Terra for bounded T2 work → Opus
4.8 (default) for broad/complex local T3 work → Sol only for qualifying protected T4 on a narrow packet;
non-Class-C read-only mapping/audit defaults to the ChatGPT read-only-first controller
(`CONTROLLER_READONLY_FIRST_POLICY`). Sonnet 5 requires runtime proof of availability/identity before any
routing (fallback = Terra bounded / Opus broad, no equivalent-quality claim); use measured session/harness
cost, never hard-coded price rankings. If `EXACT_MODEL_REQUIRED=true`, requested/actual mismatch stops. Never
claim unavailable-model quality. Model selection does not prove safety, repo state, or results.
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
