# Token Efficiency Playbook (crypto_core agents)

Purpose: use the lowest capable lane without weakening proof, audit depth, deterministic behavior, or merge
discipline. Token savings are never evidence; research economy never outranks factual accuracy. Active
doctrine: `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`).

## 1. Context budgets per task class

These older class names describe context examples only. Use §24.3 for routing and §24.12 for effort.

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

Use the handoff and runtime fields of `agent_workflow.md` §§24.6–24.7 and 24.12. Include failure tails,
label unknowns and give one next safe action. Apply §§24.3–24.4 for model selection and independent review,
and §24.8 for specialist execution counts. Use observed session usage when available.

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
- Spending a specialist execution on status polling or counting self-review as independent review.
- Requesting an effort label without checking its availability on the selected host.
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
