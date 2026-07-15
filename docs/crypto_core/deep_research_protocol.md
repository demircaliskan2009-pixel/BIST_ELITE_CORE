# crypto_core Deep Research Protocol (Agent OS edition, 2026-07-10)

> Canonical, complete usage protocol for **Deep Research** in `crypto_core` under `CRYPTO_CORE_AGENT_OS_V1`
> (`docs/crypto_core/agent_workflow.md` section 24; section 24.9 points here). Deep Research is
> **controller-orchestrated**: ChatGPT GPT-5.6 Thinking decides whether research runs, frames the exact
> question, binds it to pinned GitHub-connector evidence, and verifies the result before anything is acted
> on. Deep Research is **strictly read-only / advisory** — it never mutates repo or GitHub state (even when
> the underlying work is authorized), never authorizes a merge, a live/order/scheduler surface, or a
> weakening of any fail-closed gate. Canonical doctrine precedence is unchanged: `AGENTS.md` →
> `agent_workflow.md` → `.codex/skills/crypto-core-max-safe/SKILL.md` → `CLAUDE.md`; on conflict the
> **stricter safety rule wins**. This document contains **no secrets, credentials, API keys, or
> live-trading instructions**. Fable 5 is not a research lane: its runtime availability is proven locally
> (never researched), and no Deep Research run is required merely to select Fable for a repo-proven task;
> external model-capability comparisons remain Deep Research territory.

## 1. Why Deep Research exists here

The build is broad and mature; the dominant risks are **artifact proliferation vs end-to-end wiring**,
**PRD/roadmap drift**, and **stale external assumptions**. Deep Research is the high-leverage tool for
current / external / high-stakes facts that are not provable from the repo, and — paired with the GitHub
connector — for combined repo+external architecture review that keeps PR sequencing honest against a top-1
external standard. It is never a substitute for local proof, Class-C Codex audit, the connector
source-of-truth gate, or explicit human merge authorization.

## 2. Controller orchestration (who runs research, and how)

ChatGPT GPT-5.6 Thinking owns the research lifecycle end to end:

1. **Trigger decision** — is research REQUIRED / RECOMMENDED / NOT_REQUIRED (section 5)? Executors (Claude/
   Codex/Copilot) never run web research inside repo tasks; they emit `DEEP_RESEARCH_REQUIRED` with the
   exact question and stop.
2. **Packet construction** — every major run starts from a `CONTROLLER_TO_DEEP_RESEARCH` packet (section 6)
   with pinned repo evidence from the GitHub connector. Deep Research never infers repo state from memory.
3. **Execution** — Deep Research runs in the selected XR submode (section 4), read-only, primary-source
   first.
4. **Verification** — the post-research controller gate (section 8) checks every repo claim via the
   connector and every load-bearing citation before anything is accepted.
5. **Conversion** — accepted findings become AT MOST one bounded next-PR proposal, a workflow lesson, or
   no action. Research never triggers automatic implementation and is never merge authorization.

## 3. Use / do-not-use

**Use Deep Research for:** current exchange/Deribit API facts; fees / rate limits / funding / margin /
liquidation behavior; current market microstructure; custody / security / regulatory facts; current
framework and competitor architecture (Hummingbot, Freqtrade, NautilusTrader, QuantConnect LEAN, OctoBot,
Jesse, institutional execution/risk patterns — architecture lessons only, no blind copy, no license/IP
bypass); paper/live parity standards; readiness / shadow / live gate benchmarks; top-1 capability
benchmarking; externally sourced machine-time semantics; current model/tool behavior; academic/technical
research on backtest risk, safe execution, agentic trading.

**Do NOT use Deep Research for (repo-native or controller-owned):** local repo state (git/`gh`/connector);
PR state; CI polling; review threads; branch hygiene; Ruff/pytest failures; ordinary local implementation
or repair; already-documented internal doctrine; internal deterministic module contracts with no external
fact; replacing Class-C Codex audit, the connector final gate, tests/CI, or post-merge verification.

## 4. XR submodes

- **`XR_FACT_CHECK`** — one narrow current external question (API behavior, fee schedule, rate limit,
  funding mechanics, margin/liquidation, market-data semantics, official model/tool behavior,
  custody/security/regulatory fact). Official/primary sources first; exact question only; no broad benchmark
  unless necessary; retrieval date + source version included; unresolved facts stay UNKNOWN; no
  implementation during research.
- **`XR_ARCHITECTURE_BENCHMARK`** — comparison with Hummingbot, Freqtrade, NautilusTrader, QuantConnect
  LEAN, and other credible event-driven/institutional systems: paper/live parity patterns, risk/execution
  architecture, multi-strategy isolation, replay/determinism, data-leakage prevention, operational
  resilience, venue abstraction. Compare capabilities and evidence — never stars or marketing; distinguish
  architectural intent from implemented proof; compare against current official documentation; produce
  bounded repo-relevant recommendations; respect license/IP.
- **`XR_PHASE_GATE_REVIEW`** — MANDATORY before material phase transitions involving external/current
  assumptions: declaring paper-trading DONE; machine-time provenance when external time-source semantics
  matter; first venue connector/readiness design; Deribit readiness; shadow-readiness; live-readiness; real
  execution architecture; custody/security design; regulatory-sensitive design; production operational
  resilience; any phase-completion claim dependent on current industry standards. Also triggered after a
  major phase bundle is implemented, before roadmap changes based on external capability assumptions, when
  prior external evidence may be stale, and when official exchange/framework behavior changes.
- **`XR_OVERENGINEERING_AUDIT`** — at milestone boundaries: artifact proliferation vs end-to-end wiring;
  duplicate validation contracts; unused modules; excessive governance layers; missing integration paths;
  freeze-new-artifacts / consolidate / delete decisions; whether the next PR should be integration rather
  than another artifact; whether execution/risk/runtime surfaces are underbuilt; whether tests verify real
  composition rather than isolated artifacts. Advisory until controller triage.

## 5. Trigger policy (event-triggered, never calendar-driven)

**`DEEP_RESEARCH_REQUIRED`** when correctness depends on: current exchange or Deribit facts; fees / rate
limits / funding / margin / liquidation; current market microstructure; custody / security / regulation;
current framework comparison; paper/live parity benchmarks; readiness / live / shadow gate standards;
overengineering-vs-underbuilding external comparison; top-1 capability benchmarking; current model/tool
behavior; externally sourced machine-time semantics.

**`DEEP_RESEARCH_RECOMMENDED`** at: major architecture phase start; major phase closeout; roadmap reorder;
material connector/execution/risk design; every top-level readiness claim; after a substantial group of
merged PRs where architecture drift is plausible; when artifact count grows without clear end-to-end
capability gain.

**`DEEP_RESEARCH_NOT_REQUIRED`** for: local repo state; PR state; CI polling; review threads; branch
hygiene; Ruff/pytest failures; ordinary local implementation; already-documented internal doctrine; direct
deterministic module contracts needing no external facts; SM-5/SM-6 repo-internal semantics unless an
external comparator/venue assumption appears.

Do not use arbitrary calendar frequency; do not research merely because the tool is available.

## 6. Connector-bound research packet (CONTROLLER_TO_DEEP_RESEARCH)

Before every major run, ChatGPT prepares:

```text
RESEARCH_QUESTION:
WHY_CURRENT_EXTERNAL_FACTS_ARE_REQUIRED:
REPO:
PINNED_MAIN_SHA:
PINNED_PR_HEADS:
OPEN_PR_STATE:
REPO_FILES_TO_READ:
REPO_SYMBOLS_TO_INSPECT:
EXTERNAL_BENCHMARK_SET:
PRIMARY_SOURCE_REQUIREMENTS:
PROHIBITED_WEAK_SOURCES:
EVIDENCE_BUCKETS:
TOP1_CLAIM_STANDARD:
FORBIDDEN_MUTATIONS:
EXPECTED_OUTPUT:
CONTROLLER_POST_RESEARCH_CHECKS:
```

GitHub-connector evidence is pinned research input; Deep Research never infers repo state from memory.
Source discipline: official docs / peer-reviewed papers / primary exchange documentation outrank weak
sources (forum posts, undated blogs, marketing) — weak sources are flagged, never authoritative. Every
statement is labeled exactly one of `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` / `INFERENCE` / `UNKNOWN`;
UNKNOWN is fail-closed and never upgraded to fact.

## 7. Output contract (DEEP_RESEARCH_TO_CONTROLLER)

Every major report returns exactly:

```text
RESULT:
VERDICT:
RESEARCH_MODE:
RESEARCH_DATE:
SOURCE_QUALITY:
PINNED_REPO_STATE:
REPO_EVIDENCE:
EXTERNAL_EVIDENCE:
WHAT_IS_PROVEN:
WHAT_IS_INFERRED:
WHAT_IS_UNKNOWN:
STALE_PRIOR_FINDINGS:
OVERENGINEERING_AUDIT:
PRD_ALIGNMENT:
TOP1_IMPLICATION:
RISKS:
BOUNDED_RECOMMENDATIONS:
EXACT_NEXT_PR_PROPOSAL:
WHAT_MUST_NOT_CHANGE:
REFRESH_TRIGGER:
CONTROLLER_VERIFICATION_REQUIRED:
DEEP_RESEARCH_FOLLOWUP_NEEDED:
```

## 8. Post-research controller gate

ChatGPT must: (1) verify every repo claim through the GitHub connector; (2) inspect load-bearing external
citations; (3) separate facts from inference; (4) reject unsupported or marketing-style claims; (5) check
doctrine compatibility; (6) check whether stricter safety rules override recommendations; (7) decide
`ACCEPT_RESEARCH` / `REPAIR_RESEARCH` / `REJECT_RESEARCH` / `DEEP_RESEARCH_FOLLOWUP_NEEDED`; (8) convert
accepted findings into no more than ONE next bounded PR proposal; (9) never treat research as merge
authorization. External "best practices" that conflict with repo safety doctrine are recorded as proposals
only — the stricter safety rule wins.

## 9. Freshness and reuse

A prior result may be reused only when: the exact question is materially unchanged; relevant repo state is
unchanged or differences are accounted for; source versions are still current; the research date remains
acceptable for the fact class; no official documentation update is known; no conflicting repo or external
evidence appeared. Refresh immediately when: exchange/API docs changed; pricing/fees/rate limits changed;
regulation/security guidance changed; framework architecture materially changed; the repo phase or design
question changed; the prior report contains UNKNOWN on a load-bearing fact; a current external decision is
being authorized. Output always states: research date; repo commit/PR head used; source versions/update
dates where available; reusable findings; stale findings; UNKNOWN findings; exact refresh trigger.

## 10. Mandatory upcoming checkpoints (event-triggered; they authorize research only, never implementation)

1. **After the Agent OS PR is independently audited, merged, and postverified:** top-1 external
   architecture + overengineering benchmark (`XR_ARCHITECTURE_BENCHMARK` + `XR_OVERENGINEERING_AUDIT`).
2. **After SM-5/SM-6 enforcement is merged and postverified:** focused paper/backtest equivalence and
   secondary-metrics benchmark review.
3. **Before machine-time provenance implementation** where external time-source or operational evidence
   semantics matter: targeted current-fact research.
4. **Before any Deribit/readiness connector design:** official Deribit API, testnet, rate-limit,
   authentication, operational-risk, and readiness research.
5. **Before shadow/live/readiness design:** institutional operational-resilience, custody, security, and
   live-promotion benchmark research.

Each checkpoint's downstream work still requires controller selection and bounded implementation
authorization through the normal Agent OS chain.

## 11. Misuse prevention (hard limits)

Deep Research must never: mutate repo or GitHub state (no branch/file/commit/push/PR-open/PR-close/comment/
review/thread-resolve/workflow-rerun/merge/auto-merge — even when the underlying work is authorized);
justify skipping tests/CI/audit; replace the connector final gate, Class-C Codex audit, tests/CI, or local
post-merge verification; authorize live/private API/order routing or any forbidden surface; weaken a
fail-closed gate; replace explicit per-PR merge authorization; produce broad PRD rewrites unless the
controller explicitly asks; or claim readiness/live/order/capital authority. It may recommend a mutation
task; the controller routes any authorized mutation to the correct executor lane. On any conflict the
stricter safety rule wins.
