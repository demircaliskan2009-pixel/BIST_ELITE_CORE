# Token Efficiency Playbook (crypto_core agents)

Purpose: spend the fewest and cheapest capable executions without weakening proof, audit depth, deterministic
behavior, or merge discipline. Token savings are never evidence; research economy never outranks factual
accuracy. Active doctrine: `agent_workflow.md` section 24 (`CRYPTO_CORE_AGENT_OS_V1`). This companion holds no
routing, sizing, budget or merge authority: the council is section 24.3, audit routing and the protected-trigger
matrix are section 24.4, the lifecycle and prompt budget are section 24.8, and runtime proof and effort are
section 24.12. A lane, budget or rule named here that disagrees with section 24 is not active.

## 1. Context budget per task intent

| Task intent (section 24.6) | Context budget |
|---|---|
| Controller governance (state proof, CI, threads, merge readiness, post-merge) | `MINIMAL` — live connector/`gh` evidence only; no specialist quota |
| `IMPLEMENTATION` / `REPAIR` (Claude Opus 5.5) | `BROAD_BUT_BOUNDED` — authoritative setup files, affected production/test files, immediate dependency interfaces, current PR/main evidence; explicit invariants and regression proof |
| `CHALLENGE` (`OPUS55_FRESH_READONLY_CHALLENGE`) | `BOUNDED` — pinned diff, changed files, load-bearing dependencies, the named focus; no rediscovery the controller proved |
| `AUDIT` / `REAUDIT`, non-protected (controller) | `BOUNDED` — every changed file plus load-bearing dependencies, CI, threads |
| `AUDIT` / `REAUDIT`, protected (GPT-6 Astra) | `PROTECTED_AUDIT_PACKET_V1` only — pinned references plus the complete protected cross-contract boundary Astra must verify itself |
| `ARCHITECTURE` | `BROAD_BUT_BOUNDED` — pinned state, candidate slices, their direct dependencies; no repository-wide sweep |
| External research (Deep Research) | Connector-bound packet; citations required; unverifiable facts stay `UNPROVEN` |

Expand a budget only on progressive disclosure — an unresolved reference, an invariant crossing modules, a
test-exposed dependency, or architecture that cannot be proven locally — and state why. Never automatically
read the whole repository, every historical lesson, unrelated modules, stale archives, old prompts, or
generated output.

## 2. Controller preprocessing (primary token saver)

1. ChatGPT proves repo state via connector ONCE and pins it into the packet; executors do not repeat broad
   GitHub discovery (`CONTROLLER_READONLY_FIRST_POLICY`, section 24.10).
2. The serious prompt (section 24.6) carries the exact read set, symbol map, allowed files, invariants,
   protected classification, validation ladder, and stops — implementers start from it.
3. Pre-Astra triage: the controller finishes state, metadata, CI, thread, scope and ordinary semantic review
   itself (`CONTROLLER_PREFLIGHT_REVIEW`) and sends GPT-6 Astra only a bounded `PROTECTED_AUDIT_PACKET_V1` on a
   stabilized head — never a chat-history recovery prompt and never discovery already proven (section 24.4).
4. Handoff reuse: downstream lanes consume the prior `AGENT_OS_HANDOFF_V1` packet instead of re-deriving it;
   accepted state lives with the controller, never re-proved by memory.
5. Executors still prove their own LOCAL facts (git state, clean tree, tests) — controller packets never
   replace local proof. The human is never asked to run a command the connector or routed agent can run
   (`USER_MANUAL_WORK_MINIMIZATION`, section 24.10).

## 3. Context intake protocol (executors)

1. Prove local repo state first with one `git`/`gh` snapshot; never from memory.
2. Name the intended read set before reading and justify any expansion.
3. Read changed files and symbols before whole repositories; build one source surface map.
4. Do not reread unchanged docs after a stable head proof; do not duplicate reads the packet already proves.
5. Stop with proof rather than broadening a scan to compensate for missing information.

## 4. Report compression

Reports are `AGENT_OS_HANDOFF_V1` packets (section 24.6): fixed fields, verdict first, failure tails only,
evidence vs inference separated, missing facts `UNKNOWN`/`N/A`, exactly one next safe action. Always include the
section 24.12 runtime-proof block and the `SETUP_*` block.

## 5. Model selection and proof

Selection is section 24 routing, never restated here: the controller does all read-only work it can first;
Claude Opus 5.5 carries implementation, repair and the repo-native work of that task; the controller accepts
non-protected candidates; GPT-6 Astra is spent only on protected acceptance; Codex GPT-5.6 Sol runs only on a
recorded reserve gap. Effort follows section 24.12: `xhigh` is the normal Opus 5.5 coding default and `max` only
on a named trigger. Runtime identity and required thinking fail closed; only effort may stay `UNKNOWN`. Use
measured session/harness cost, never hard-coded price rankings. Never claim unavailable-model quality. Model
selection does not prove safety, repo state, or results. Claude Fable 5 is `INACTIVE_EXPIRED_RETIRED` — never a
lane or fallback; pre-v5.2 Fable-era contracts stay archived in `fable_exit_contract_index.md` and are never
routing.

## 6. Codex quota economy

The shared Codex quota is spent on protected acceptance and nothing else by default (`CODEX_QUOTA_RESILIENCE_V1`,
section 24.4). Non-protected candidates get zero Codex executions: the controller audits them. Protected
candidates get one compact GPT-6 Astra `Ultra` audit — at most one whole-contract re-audit after the one
consolidated repair — on a stabilized head, preceded by the controller preflight and, when useful, an Opus 5.5
challenge. Codex capacity is preserved by classifying precisely (ambiguity still classifies upward), preparing
the packet and stabilizing the head, never by weakening the gate. An Astra quota block freezes the protected
head and waits; it never reroutes protected acceptance.

## 7. Prompt-count budgets

Section 24.8 alone: target 2 specialist prompts clean and 4 repaired, hard maximum 5, no sixth; at most two
read-only Opus challenges per lifecycle outside the five slots. Never split coherent work into micro-prompts
unless a stop condition fires; never combine implementation with its own audit, merge with next feature,
research with mutation, or two PRs/implementers.

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
- Specialist status polling, implementer self-review presented as acceptance, unavailable-model claims.
- Dispatching GPT-6 Astra for a candidate with no protected trigger, for broad discovery, or on an unstable
  head; dispatching Codex Sol for model diversity or for work the controller or Opus 5.5 can absorb.
- Every Opus task at `max`; `max` without a named trigger.
- Generic re-verification loops ("double-check everything") in place of the deterministic gate ladder;
  rerunning a passed gate on an unchanged head; subagents for polling, routine commands or small patches.
- Asking the human to run terminal commands the connector or routed agent can run.
- Broad scans, full logs, duplicate doctrine, `product/*` branch templates, per-PR reflex research.

## 10. Non-regression checks

One open PR; one repository writer at a time; no direct `main` push; standard merge only; no merge without
explicit human authorization; pending CI = `NOT_READY`; current valid P1/P2 threads block; GPT-6 Astra is the
sole protected acceptance and is never reassigned; postmerge verification before next work; crypto_core-only; no
BIST, live/private API, orders, scheduler, readiness transition, shadow/live, or capital mutation.

## 11. No-overclaim

Nothing in this playbook proves repo/PR/CI state, Stage-4 completion, machine-time origin, secondary-metrics
enforcement, readiness, or edge/profitability. Compact reports retain identical proof density.
