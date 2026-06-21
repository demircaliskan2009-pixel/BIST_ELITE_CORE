# crypto_core Deep Research Protocol

> Canonical usage protocol for **Deep Research** in `crypto_core`, especially when Deep Research runs
> inside the **GitHub connector chat** and can combine current external research, official docs/papers,
> and live repo/PR evidence. Companion to `docs/crypto_core/agent_workflow.md` (§19 points here) and
> `docs/crypto_core/agent_lessons.md`. Canonical doctrine precedence is unchanged: `AGENTS.md` →
> `agent_workflow.md` → `.codex/skills/crypto-core-max-safe/SKILL.md` → `CLAUDE.md`; on conflict the
> **stricter safety rule wins**. Deep Research is **strictly read-only / research/advisory only** — it
> never mutates repo or GitHub state (even when the underlying work is authorized), and never authorizes
> a merge, a live/order/scheduler surface, or a weakening of any fail-closed gate. This document contains
> **no secrets, credentials, API keys, or live-trading instructions**.

## 1. Why Deep Research exists here

The build is broad and mature; the dominant risk is **artifact proliferation vs end-to-end wiring**
and **PRD/roadmap drift**, not lack of files. Deep Research is the high-leverage tool for **current /
external / high-stakes facts** that are not provable from the repo, and — when paired with the GitHub
connector — for **combined repo+external architecture review** that keeps PR sequencing honest. The
goal is to move faster **without overengineering, PRD drift, or unnecessary product-code churn**. It is
not a substitute for local proof, Codex P1/P2 audit, or the GitHub-connector source-of-truth state gate.

## 2. Deep Research role (use / do-not-use)

**Use Deep Research for:**

- Current / external / high-stakes facts not derivable from this repo.
- Exchange API docs, Deribit docs, rate limits, fee / funding / margin / liquidation behavior.
- Legal / regulatory / custody / security facts.
- Competitor / benchmark research: Freqtrade, Hummingbot, OctoBot, Jesse, institutional
  execution/risk patterns (architecture lessons only — no blind copy, no license/IP bypass).
- Academic / technical research: backtest implementation risk, safe execution, agentic trading,
  market microstructure, paper/live readiness gates.
- PRD / roadmap alignment using **external benchmarks**.
- Overengineering detection: artifact proliferation vs end-to-end wiring.
- Defining **paper trading DONE**, shadow DONE, and live-readiness gates.

**Do NOT use Deep Research for (these are repo-native or controller-owned):**

- Local repo state (use git / `gh` / the GitHub connector).
- CI polling (Codex Pursue Goal / `gh` one-shot snapshots).
- PR merge / readiness **source-of-truth** (GitHub connector gate + explicit human authorization).
- Local implementation repair or routine unit-test / ruff debugging (Claude executor).
- Branch hygiene.
- Replacing Codex P1/P2 adversarial audit.
- Replacing the GitHub connector final state gate.

## 3. GitHub connector + Deep Research combined protocol

When Deep Research runs in the GitHub connector chat and can inspect the repo, it does **combined
repo+external architecture review** under these rules:

- **Cite both sides.** Every claim cites either external sources or concrete repo evidence (path /
  PR# / commit / check name) — preferably both where relevant.
- **Four-bucket separation is mandatory.** Label every statement as exactly one of:
  1. `REPO_EVIDENCE` — proven from repo/PR/CI via the connector.
  2. `EXTERNAL_EVIDENCE` — proven from external docs/papers/market facts (with source quality).
  3. `INFERENCE` — reasoned conclusion drawn from 1 and/or 2 (explicitly marked as inference).
  4. `UNKNOWN` — not provable from either side (fail-closed; never upgraded to a fact).
- **Never infer live repo state without GitHub evidence.** No repo/PR/CI claim from memory or from
  external reasoning alone.
- **Strictly read-only / advisory — no repo or GitHub mutation, ever.** Deep Research must never create
  branches, edit files, commit, push, open PRs, close/reopen PRs, comment on PRs, resolve threads,
  rerun workflows, merge, enable auto-merge, or otherwise mutate repo/GitHub state — **even when a human
  or controller authorizes the underlying work.** It may *recommend* a mutation task or produce a
  proposed slice; it must not execute it. Authorization to implement or mutate repo state is routed
  **outside Deep Research** by the ChatGPT controller to the appropriate executor lane (Claude local
  agent / `gh` for implementation / repair / closeout / merge / post-merge verify; GitHub connector for
  source-of-truth audits or explicitly controller-authorized connector actions; Codex for adversarial
  P1/P2 audit). This holds even when Deep Research is paired with GitHub connector repo evidence — that
  evidence is **read-only research input only**.
- **Source discipline.** Distinguish official docs / peer-reviewed papers / primary exchange
  documentation from weak sources (forum posts, undated blogs, marketing); weak sources are flagged,
  never treated as authoritative.
- **Actionable output.** Produce **PR-level, bounded, sequenced recommendations** (smallest safe slice
  first), not vague strategy. Recommendations are proposals for the controller, not implementation
  instructions.

## 4. Routing doctrine

| Role | Deep Research relationship |
|---|---|
| **ChatGPT (controller)** | **Decides whether Deep Research is needed** and frames the question; owns the verdict and merge authorization. Deep Research never overrides the controller. |
| **Claude (executor)** | Does **not** call Deep Research itself. May **recommend** it (emit `DEEP_RESEARCH_REQUIRED` with the exact question) when blocked by a current/external fact; otherwise proceeds with repo-native proof. |
| **Codex** | Remains the **adversarial repo P1/P2 reviewer**. Deep Research does not replace Codex review. |
| **Codex Pursue Goal** | Remains the **bounded terminal `gh`/CI/status loop** tool. Deep Research does not poll CI. |
| **GitHub connector** | Remains the **source-of-truth repo-state gate**. Deep Research consumes connector evidence; it is not the merge authority. |
| **Deep Research** | **Architecture / external-current research + combined repo+external review.** **Strictly read-only / advisory** — never an executor lane, never merge authority, never a safety-gate waiver. It may recommend a mutation task; any authorized mutation is routed by the controller to Claude/`gh`, the GitHub connector, or Codex — never executed by Deep Research. |

## 5. Triggers

Mark **`DEEP_RESEARCH_REQUIRED`** when:

- Exchange / API / funding / fees / rate limits / microstructure / custody / regulation / security
  facts are involved.
- Deribit / readiness / live / shadow decisions are involved.
- PRD / roadmap correctness depends on **current external benchmarks**.
- Deciding whether we are **overengineering vs underbuilding**.
- Comparing with top crypto bots / frameworks.
- Defining **paper trading DONE / shadow DONE / live-readiness** gates.

Mark **`DEEP_RESEARCH_NOT_REQUIRED`** when:

- Pure local module implementation.
- tests / ruff / CI.
- GitHub PR / check / thread status.
- Repo-only current state.
- Known internal doctrine already documented (read it instead).

## 6. Deep Research output contract

A Deep Research report (especially in the connector chat) returns exactly these fields:

```
RESULT:
VERDICT:
SOURCE_QUALITY:
REPO_EVIDENCE:
EXTERNAL_EVIDENCE:
WHAT_IS_PROVEN:
WHAT_IS_INFERRED:
WHAT_IS_UNKNOWN:
OVERENGINEERING_AUDIT:
PRD_ALIGNMENT:
NEXT_PR_RECOMMENDATIONS:
RISKS_TO_AVOID:
DEEP_RESEARCH_FOLLOWUP_NEEDED:
```

## 7. Misuse prevention (hard limits)

Deep Research must never:

- **Mutate repo or GitHub state** — no branch/file/commit/push/PR-open/PR-close/PR-comment/
  thread-resolve/workflow-rerun/merge/auto-merge or any other repo or GitHub action — **even when a
  human or controller authorizes the underlying work.** It may recommend a mutation task; the
  controller routes any authorized mutation to the correct executor lane (Claude/`gh`, GitHub
  connector, or Codex). Deep Research is never itself an executor lane.
- Justify **skipping tests / CI / audit**.
- Replace the **GitHub connector final gate**, **Codex P1/P2 audit**, **tests/CI**, or **local
  post-merge verification**.
- Authorize **live / private API / order routing** or any forbidden surface (`agent_workflow.md` §16).
- Weaken a **fail-closed gate** (`agent_workflow.md` §3).
- Replace **explicit per-PR merge authorization**.
- Produce **broad PRD rewrites** unless the controller explicitly asks.

If Deep Research surfaces external "best practices" that **conflict with repo safety doctrine**, they
are recorded as a **proposal only** (for controller triage), never as a direct implementation
instruction. On any conflict the **stricter safety rule wins**.
