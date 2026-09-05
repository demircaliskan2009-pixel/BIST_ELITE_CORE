# crypto_core Research Protocol

<!-- CONTROL_PLANE_ROLE: RESEARCH_ADAPTER -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

> **Research adapter, not authority.** This file describes how the external-fact research lane is run.
> It classifies no task family, selects no effort, sizes no PR and holds no merge authority. The
> canonical authority is `docs/crypto_core/agent_os_v2.md`, section 8.
>
> MERGE_AUTHORITY_REF: canonical section 2.1. PR_SIZING_AUTHORITY_REF: canonical section 2.2.
> TASK_FAMILY_AUTHORITY_REF: canonical section 3. EFFORT_AUTHORITY_REF: canonical section 3.2.
>
> Research is READ-ONLY and ADVISORY. It never mutates repository or GitHub state — not a branch, a
> file, a commit, a push, a PR, a comment, a thread resolution, a workflow rerun, a merge or an
> auto-merge — even when the underlying work is authorized. It is never an executor lane, never merge
> authority, and never a safety-gate waiver.

## 1. Why this lane exists

Some decisions depend on facts that are external to this repository and change over time. Guessing
them is worse than not answering: a confidently wrong venue fee, rate limit or protocol parameter
propagates silently into design. This lane exists to answer exactly those questions, with citations,
and to mark everything it could not verify as `UNKNOWN`.

It does not exist to explain difficult repository code. Repository questions are answered by reading
the repository.

## 2. Orchestration

The controller decides whether research is needed, writes the research packet, and verifies the
result. A research result never triggers implementation on its own: it flows back to the controller,
which decides the next task through normal routing.

Choose the cheapest lane that actually answers the question. A few straightforward official facts are
answered by ordinary controller web research. The persistent-workspace lane is preferred only when
multi-source synthesis, a persistent artifact, and browser or environment interaction together add
material value. Never duplicate research that is already complete and still fresh.

## 3. Use and do-not-use

**Use for:** exchange, venue and provider API behavior; fee schedules, maker and taker structures;
rate limits; funding, basis, carry, margin and liquidation mechanics; order-book and execution
semantics; current microstructure facts; custody, security and regulatory requirements; provider
cryptographic parameters; deployed versions and current framework or tool behavior where official
documentation conflicts; externally sourced machine-time semantics; live-readiness standards defined
outside this repository; and architecture or benchmark comparison against credible external systems —
as lessons only, never as code to copy and never as a licence or intellectual-property bypass.

**Do NOT use for:** local repository state; CI polling; PR or merge readiness as a source of truth;
local implementation repair; routine unit-test or lint debugging; branch hygiene; replacing an
independent audit; or replacing the connector state gate.

## 4. Submodes

- `XR_FACT_CHECK` — one narrow current external question; official and primary sources first.
- `XR_ARCHITECTURE_BENCHMARK` — capability and evidence comparison against credible external systems.
  Capabilities and evidence, never popularity or marketing.
- `XR_PHASE_GATE_REVIEW` — run before a material phase transition that depends on external or current
  assumptions.
- `XR_OVERENGINEERING_AUDIT` — artifact proliferation against end-to-end capability, at a milestone
  boundary.

## 5. Trigger policy

Event-triggered, never calendar-driven and never mechanically per-PR.

**Required** when a decision materially depends on: current exchange or venue facts; fees, rate
limits, funding, margin or liquidation; current microstructure; custody, security or regulation;
current external framework or tool behavior; paper-to-live parity standards; readiness, shadow or live
promotion standards defined externally; externally sourced machine-time semantics; or a top-tier
external benchmark.

**Recommended** at a major phase start or closeout, on a roadmap reorder, before a significant
execution, risk or connector design, after a substantial PR bundle, when artifacts grow without
capability growing, and before any major readiness claim.

**Not required** for repository state, PR state, CI, threads, local tests, branch hygiene, routine
implementation, or an internal deterministic contract with no external fact in it.

## 6. Research packet

The controller supplies: the exact question, narrowly stated; why the answer is load-bearing and what
decision it changes; the pinned repository revisions and the exact repository files that provide
internal context; the source quality requirement, official and primary first; what would falsify the
answer; the freshness requirement; the required output contract; and the explicit statement that the
lane is read-only.

Pin source revisions. A snapshot of a repository taken elsewhere is never current remote state, and a
research result that assumes otherwise is invalid regardless of how well sourced its external claims
are.

## 7. Output contract

Every research return separates, explicitly and per claim:

```text
RESULT / VERDICT / SOURCE_QUALITY / REPO_EVIDENCE / EXTERNAL_EVIDENCE /
WHAT_IS_PROVEN / WHAT_IS_INFERRED / WHAT_IS_UNKNOWN / OVERENGINEERING_AUDIT /
PRD_ALIGNMENT / NEXT_PR_RECOMMENDATIONS / RISKS_TO_AVOID / RESEARCH_FOLLOWUP_NEEDED
```

Every statement is labelled as exactly one of verified repository evidence, verified external
evidence, inference, or `UNKNOWN`. Live repository state is never inferred without live evidence.
Official documentation and primary sources are distinguished from weak ones. Recommendations are
bounded and PR-level, never vague strategy.

## 8. Post-research gate

The controller verifies the sources, checks that nothing load-bearing was inferred, and decides the
next task. A research finding authorizes research conclusions only — never downstream implementation,
never a readiness or connector transition, and never a governance value.

## 9. Freshness and reuse

A research answer carries the date and the source revision it was verified against. Reuse it while it
is fresh and while nothing it depended on changed. Re-run it when the external surface changes, when a
source is superseded, or when a decision now depends on a detail the original question did not cover.

## 10. Misuse prevention

Research must never justify skipping a test, a CI gate or an independent audit; authorize a live or
private API, order routing, a scheduler, shadow or live execution, or any forbidden surface; weaken a
fail-closed gate; replace explicit per-PR human merge authorization; or produce a broad product
rewrite that nobody asked for. External best practice that conflicts with repository safety doctrine
is a proposal only — the stricter safety rule wins.
