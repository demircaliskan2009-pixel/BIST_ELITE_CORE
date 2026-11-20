# Token Efficiency Playbook (crypto_core agents)

## 1. Context intake

Use the controller packet and the changed files to bound context. Widen the read set for a concrete dependency,
a failing test or an unresolved invariant. Section 24.4 determines audit coverage. The complete material
blocker set and every mandatory gate still apply.

## 2. Controller preprocessing

1. ChatGPT proves repo state via connector ONCE and pins it into the packet; executors do not repeat broad
   GitHub discovery.
2. The CONTROLLER_TO_IMPLEMENTER packet carries the exact read set, symbol map, allowed files, invariants,
   protected-risk class, validation ladder, and stops — implementers start from it.
3. Pre-Codex triage: the controller removes state/metadata/mechanical questions before an audit prompt and
   supplies the §24.4 packet with the exact changes and unresolved semantic questions.
4. Handoff reuse: downstream lanes consume the prior `AGENT_OS_HANDOFF_V1` packet instead of re-deriving it;
   accepted state lives with the controller, never re-proved by memory.
5. Executors still prove their own LOCAL facts (git state, clean tree, tests) — controller packets never
   replace local proof.

## 3. Context intake protocol (executors)

1. Prove local repo state first with `git` against the controller’s pinned remote snapshot; never from memory.
2. Name the intended read set before reading and justify any expansion.
3. Read changed files and symbols before whole repositories; build one source surface map.
4. Do not reread unchanged docs after a stable head proof; do not duplicate reads the packet already proves.
5. Stop with proof rather than broadening a scan to compensate for missing information.

## 4. Report compression

Reports are `AGENT_OS_HANDOFF_V1` packets: fixed fields, verdict first, failure tails only, evidence vs
inference separated, missing facts `UNKNOWN`/`N/A`, exactly one next safe action. Use the runtime and setup fields
in workflow §§24.12 and 24.7.
The controller uses §24.3 for routing, §24.4 for the independent audit and §24.8 for specialist accounting.

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
- Requesting `max` without the technical trigger required by §24.12.
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
