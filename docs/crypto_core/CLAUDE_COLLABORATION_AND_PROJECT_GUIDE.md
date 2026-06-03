# crypto_core — Master Collaboration & Project Guide (for ChatGPT)

> **Audience:** ChatGPT, acting as Controller / Auditor / Prompt-Controller for the `crypto_core`
> project. **Author:** Claude (Claude Code, Opus 4.8), the co-primary implementation/debug engine.
> **Purpose:** Give ChatGPT a complete, accurate, single-source picture of the project, the Claude
> Code setup, Claude's current working mode, and exactly how to design prompts that extract maximum
> work / maximum value / maximum safety / minimum tokens from Claude. After this document, no
> further setup work is planned — we go straight to implementation until we have a top-tier crypto
> trading bot.
>
> **Status of facts in this guide:** Every architectural claim below was verified against the live
> repo on 2026-06-03 (file listings, class definitions, git log, open PRs). Where something is a
> judgment/opinion rather than a verified fact, it is marked **[opinion]**. Where a current external
> fact (exchange API/fees/funding/limits) would be needed, it is marked **[DEEP_RESEARCH]** — Claude
> will not guess these; ChatGPT must supply them or authorize research.

---

## 0. TL;DR for ChatGPT (read this first)

1. **What this is:** an edge-to-money governance pipeline / "edge compiler with a governor" for
   crypto **perpetual-futures + derivatives** trading. Not a naive signal bot — it is a
   *fail-closed, deterministic, audit-first* machine that takes a strategy idea and only lets it
   touch (paper) money after it survives a chain of evidence gates.
2. **Maturity:** large and real. 255 source files, 805 test files, 21 subsystems. The quant
   validation and evidence-chain cores are genuinely sophisticated (PBO, walk-forward, PIT parity,
   leakage/repaint detection, deterministic digests, decision ledger, evidence store).
3. **Current frontier:** the **paper-sleeve activation** stage, gated on sleeve/admission/promotion
   evidence digests. Open work = PR #217 (gate paper-shadow activation on sleeve evidence).
4. **Biggest debt [opinion]:** artifact-factory drift concentrated in `venue/` (80 of 95 files are
   near-identical `deribit_paper_runtime_heartbeat_blocker_chain_continuity_NN.py` iterations) and in
   `docs/` (70 `NEXT_BLOCKER_SUMMARY_*` iteration docs), plus a cluttered repo root. The *core* is
   clean; the *Deribit paper-runtime sub-area + docs* exploded into theater. This is the #1 cleanup
   slice and a cautionary tale for prompt design (see §9, §11).
5. **New working mode (v11.1):** Claude now auto-applies the full setup on every prompt and completes
   the **maximum safe, validated product-value work per turn — no fixed PR cap** (1–3 related PRs is
   only an informal conservative default/example, never a hard ceiling: more when each is
   safe/bounded/reviewable, fewer — or one, or zero-with-proof — when not). You (ChatGPT) no longer
   need to tell Claude which skills to use — only give it a sharp objective + constraints. See §8 and §11.
6. **Hard rails that never bend:** paper-first (no live/order/scheduler/credentials), fail-closed,
   deterministic, no direct push to `main`, no self-approve, no auto-merge, no BIST leakage, scope =
   named files only. Throughput never buys a bypass of these.

---

## 1. System Identity & Mission

- **Project:** `crypto_core`, living inside the `BIST_ELITE_CORE` monorepo. All other top-level
  packages (BIST/KAP/iDeal/Matriks era) are **historical context only** — crypto_core must never
  import or leak BIST logic.
- **Constitution:** `docs/PRDV4_MULTI_MARKET_CRYPTO.md` is the architecture constitution that all
  subsystems follow. (Earlier PRD/PRDV2/PRDV3 files are history.)
- **Declared scope** (from `src/crypto_core/__init__.py`): Binance (primary) + Bybit (secondary) +
  CoinGecko (discovery), with Deribit used for derivatives public-feed evidence.
  **Instrument class: perpetual futures contracts ONLY — no spot, no options, no margin tokens**
  (PRDV4 §0.2). Base currency USD, max leverage 3x, 24/7 operation.
- **Mission [shared goal]:** become a top-tier (the user says "top 1") crypto trading bot that
  *actually makes money* — but only via the disciplined edge-to-money path, paper-first, with every
  promotion earned by evidence.

**Mental model:** think of crypto_core as a *compiler + governor*. A raw edge idea is "source code";
the pipeline is the compiler that refuses to emit a runnable artifact unless it type-checks against
reality (no lookahead, fees/funding modeled, PIT-correct, reproducible). The governor decides how
much capital each compiled artifact (sleeve) may use, and revokes it when health degrades.

---

## 2. Core Doctrines (the 8 laws that shape every decision)

1. **Fail-closed** — when in doubt, raise; never silently pass.
2. **Deterministic** — canonical JSON, reproducible digests, no float drift.
3. **Audit-first** — every decision logged and traceable; no silent state changes.
4. **Paper-first** — no live / private keys / order routing / scheduler / auto-loop / shadow
   execution against real venues.
5. **Derivatives-first** — funding, basis, carry, mark/index spread semantics are first-class.
6. **Multi-sleeve** — each strategy/sleeve is isolated and independently governed.
7. **Governance-first** — risk-bounded and governor-gated before any allocation.
8. **Validation discipline** — validate at system boundaries, trust internals.

These are not slogans; they are encoded structurally (frozen dataclasses, `__post_init__`
invariants, corrupt-store error types, digest binding between stages).

---

## 3. Architecture Map (verified module inventory)

21 top-level subsystems under `src/crypto_core/`. Grouped by role:

### 3.1 Edge generation & health
- `edge/` — the edge engine, registry, activation, and **families**: `funding.py`,
  `liquidation.py`, `order_flow.py`, `volatility.py`. This is where alpha hypotheses become
  evaluable signals.
- `edge_health/` — tracks live decay/health of edges (`tracker.py`, `models.py`).
- `regime/` — market-regime tracking (`tracker.py`) so edges are scored in-regime.

### 3.2 Data plane (PIT-correct ingestion)
- `data/ingestion/` — Binance + Bybit adapters, snapshot fetchers, WS clients, `data_ingestor.py`,
  `stream_config.py`.
- `data/processing/` — `book_manager.py`, `event_router.py`, `ohlcv_builder.py`,
  `trade_processor.py`.
- `data/validation/` — `data_validator.py`, `rules.py`, `sequence_tracker.py`, `errors.py`.
- `data/recovery/` — `delta_buffer.py`, `recovery_manager.py` (gap recovery).
- `data/public_feed_*` — a full public-feed connector/dialect/ingest/pipeline/policy/simulator stack
  (Deribit-centric), plus `public_network_authorization.py` and `public_data_readiness.py`.
- `data/requirements.py` — **DataRequirement / DataRequirementRegistry / validation** (the PIT data
  contract a StrategySpec must satisfy).
- `data/market_data_journal.py`, `data/order_book.py`.

### 3.3 Strategy contract
- `strategy/spec.py` — **StrategySpec** (frozen dataclass: id/version/family, edge_family,
  instrument_universe, market_type, venue_assumptions, entry/exit/invalidation conditions, risk_caps,
  data_requirements, fee/slippage model requirements, failure_modes, kill_switch_triggers,
  promotion_requirements, telemetry_fields) + `StrategySpecValidationResult` with a fail-closed
  `__post_init__` (cannot be `accepted` while it still needs research). Deterministic digest via
  hashlib + canonical JSON.

### 3.4 Validation stack (this is the real quant core)
- `validation/backtest_replay_admission.py` — **BacktestReplayAdmission** (policy/input/result/status):
  the gate that decides whether a backtested+replayed strategy is admissible.
- `validation/pbo.py` — **Probability of Backtest Overfitting**.
- `validation/walk_forward.py` — walk-forward evaluation.
- `validation/pit_parity.py` — point-in-time parity (backtest vs replay must agree).
- `validation/leakage_bias_repaint.py` — lookahead/leakage/repaint detection.
- `validation/stress_testing.py`, `validation/stage4_comparator.py`, `validation/pipeline.py`.

### 3.5 Evidence chain & governance (the "governor")
- `audit/decision_ledger.py` — **DecisionLedger** (stage/status/record/validation): the append-only
  trace of every governance decision, with `output_digest` binding.
- `service/evidence_store.py` — **EvidenceStore** (config + corrupt-error type): persisted, digest-
  addressed evidence records; fail-closed on corruption.
- `service/sleeve_admission_controller.py` — **SleeveAdmissionController** + EvidencePrecheck + Store +
  Snapshot/History (admits a sleeve only with valid, current evidence).
- `service/promotion_review.py` + `promotion_review_controller.py` — **PromotionReview** pipeline
  (precheck, store, corrupt-error) that governs paper→(future) promotion.
- `service/sleeve_promotion_review_controller.py` — per-sleeve promotion verdicts + portfolio summary.
- `service/escalation_review_controller.py`, `service/campaign*.py`, `service/sleeve_portfolio*.py`,
  `service/summary.py`, `service/readiness.py`, `service/run_state.py`.

### 3.6 Paper execution & runtime
- `execution/` — a rich execution-simulation stack: `engine.py`, `paper_adapter.py`, `fill_pricer.py`,
  `lifecycle.py`, `state_machine.py`, `markout.py`, `tca.py` + `tca_loop.py` + `tca_store.py`
  (transaction-cost analysis), `venue_scoring.py`, `venue_metadata.py`, `route_binding.py`,
  `attribution.py`, `recovery.py`, `regime_contracts.py`, `authorization.py`, `store.py`.
- `service/paper_shadow_session_controller.py`, `service/paper_live_service.py` — the paper-shadow
  session layer (current frontier).
- `venue/` — Deribit paper venue: `deribit_paper_feed.py`, `deribit_paper_fill_model.py`,
  `deribit_paper_ledger.py`, `deribit_paper_order_intent.py`, `deribit_order_book_replay.py`,
  `deribit_paper_run_harness.py`, `deribit_bounded_paper_campaign.py`,
  `deribit_hard_capped_paper_session.py`, plus promotion/runtime/heartbeat controllers.
  **(⚠ also the location of the artifact drift — see §9.)**

### 3.7 Risk, portfolio, capital
- `risk/` — `engine.py`, `kill_switch.py`, `contracts.py`, `models.py`.
- `cvar/` — `engine.py`, `models.py` (CVaR / tail-risk).
- `portfolio/` — `tracker.py`, `store.py`, `fills.py`, `models.py`.

### 3.8 Orchestration, service, observability
- `service/service_orchestrator.py` — top-level wiring of the pipeline.
- `orchestrator/`, `runtime/` (`assembler.py`, `bridge.py`, `runner.py`, `models.py`),
  `session/`, `state/`.
- `telemetry/`, `temporal/`, `guard/`, `audit/`, `service/health.py`, `service/metrics.py`,
  `service/artifact_export.py`.

---

## 4. The Edge-to-Money Pipeline (stage-by-stage state)

Canonical chain (paper-first; live stages intentionally absent):

```
StrategySpec → LBR (Live Backtest Replay) → PIT/DataRequirement → DecisionLedger →
EvidenceStore → BacktestAdmission → Replay → PaperSleeve → Promotion → Allocator → ExecutionSim
```

| Stage | Status [verified] | Where |
|---|---|---|
| StrategySpec | **Built, mature** | `strategy/spec.py` |
| PIT / DataRequirement | **Built** | `data/requirements.py`, `validation/pit_parity.py` |
| Backtest / Replay / Admission | **Built** | `validation/backtest_replay_admission.py`, `walk_forward.py`, `pbo.py`, `leakage_bias_repaint.py` |
| DecisionLedger | **Built** | `audit/decision_ledger.py` |
| EvidenceStore | **Built** | `service/evidence_store.py` |
| Sleeve Admission (evidence-gated) | **Built + recently hardened** | `service/sleeve_admission_controller.py` |
| Promotion (evidence-gated) | **Built + recently hardened** | `service/promotion_review*.py`, `sleeve_promotion_review_controller.py` |
| Paper Sleeve / Execution Sim | **Built** | `execution/*`, `venue/deribit_paper_*` |
| **Paper-shadow activation (evidence-gated)** | **In progress — current frontier** | `service/paper_shadow_session_controller.py`, PR #217 |
| Allocator ↔ risk bridge | **Partial** | `risk/engine.py`, `portfolio/*`, `cvar/*` |
| Governor integration | **Partial / ongoing** | `service/service_orchestrator.py` |
| Live execution | **Intentionally NOT built** (paper-first doctrine) | — |

**Recent PR train (git log, newest first):** a very consistent "evidence-currentness" hardening
campaign — each PR makes one stage *prove the current result* via `output_digest`, not just identity:
- #217 gate paper-shadow activation on sleeve evidence (open)
- #216 persist sleeve admission outcome evidence
- #215 require promotion evidence for sleeve admission
- #214 bind promotion outcome digest
- #213 persist promotion outcome evidence
- #212 promotion admission evidence gate
- #211 admission evidence store
- #210 backtest replay admission

**[opinion] This is exactly the right backbone** — you are wiring an unforgeable evidence chain
before letting capital flow. The discipline (feat then fix-to-refresh-snapshots, fail-closed on
persistence failure) is textbook. Keep going stage-by-stage to Allocator and Governor.

---

## 5. Current Position (verified 2026-06-03)

- **Branch:** `product/paper-shadow-activation-evidence-gate-pr1`
- **Open PR:** #217 — "gate paper shadow activation on sleeve evidence" (the only open PR;
  one-open-PR discipline is being honored).
- **Tree:** clean.
- **Next logical slice [opinion]:** evidence → paper-shadow-session bridge (carry the activation
  gate into the session lifecycle), then the Allocator-risk bridge, then Governor integration.

---

## 6. The Claude Code Setup We Built Together (full inventory)

This is a deliberately maximalist, defense-in-depth Claude Code customization, all **user-level
(global)** but scoped to fire only inside `BIST_ELITE_CORE` / `crypto_core`. It is the "weapon"
the user refers to. Layers:

### 6.1 Doctrine file — `CLAUDE.local.md` (not git-tracked)
The project constitution Claude loads every session. 23 numbered doctrine sections covering: system
identity, language policy (Turkish for chat, English for all code/docs/commits), project boundary &
BIST-leakage blocker, the 8 core doctrines, absolute no-go rules, tool role map, model/effort
routing, branch/PR discipline, allowed-files discipline, validation discipline, git discipline,
reporting contract, deep-research triggers, product-layer priority, token economy, co-brain protocol,
evidence-chain law, product-value radar, alpha-killer doctrine, failure taxonomy, MCP policy, report
compression, workspace boundary, external-setup quarantine, evidence-currentness law, no-product-
theater, prompt compression, OSS teardown, edge-to-money roadmap, alpha market intelligence, VS Code
gate, token lifecycle, ICC prompt intake, advanced-ops gate, and **§23 auto-orchestration / max-
throughput (new, v11)**.

### 6.2 Skills (35) — `~/.claude/skills/<name>/SKILL.md`
Procedures Claude invokes implicitly. Grouped:
- **Token/cost:** `token-governor` (classify T0–T4), `model-router`, `session-lifecycle-manager`,
  `performance-complexity-guard`, `prompt-compressor`, `report-compressor`, `prompt-intake-gate`.
- **Safety/scope:** `workspace-boundary`, `patch-readiness-gate`, `security-red-team`,
  `mcp-security-policy`, `vscode-extension-gate`, `advanced-ops-gate`, `third-party-quarantine`,
  `skill-miner`, `setup-acceptance-gate`, `hook-selftest`.
- **Evidence/quality:** `evidence-chain-validator`, `evidence-currentness-auditor`,
  `test-gap-finder`, `docs-api-sync-auditor`, `review-output-scorer`, `review-thread-classifier`,
  `failure-taxonomy`, `self-improvement-gate`.
- **Product/edge:** `product-value-radar`, `no-product-theater`, `edge-to-money-roadmap`,
  `alpha-killer`, `alpha-market-intelligence-gate`, `research-to-spec-compiler`,
  `open-source-bot-teardown`, `deep-research-decision-gate`, `adversarial-cobrain`,
  `internal-council-review`.

### 6.3 Commands (8) — invoked as `/crypto-core-*`
`status-proof`, `readonly-audit`, `bounded-patch`, `review-repair`, `pr-closeout-prep`,
`protocol-retro`, `deep-research-gate`, `context-rollover`.

### 6.4 Agents (11, read-only/advisory unless noted) — spawned only on explicit request
`contract-auditor`, `forensic-debugger`, `surgical-patcher` (writes), `review-blocker-surgeon`
(writes), `product-slice-planner`, `token-economist`, `adversarial-architect`,
`evidence-chain-auditor`, `edge-killer`, `protocol-evolver`, `setup-quarantine-auditor`.

### 6.5 Hooks (2) — defense-in-depth, never edit files
- `crypto-core-guard.ps1` (PreToolUse/Bash): blocks force-push, broad `git add`, `--approve`,
  `--watch`, `rm -rf`, package installs (exit 2). Fail-open on script error.
- `crypto-core-report-check.ps1` (Stop): non-blocking reminder if the final report omits required
  fields.

### 6.6 Memory — `~/.claude/.../memory/`
Per-session-loaded fact store (index = `MEMORY.md`). Currently holds PR-#217 state and the new
auto-orchestration working-mode fact.

### 6.7 MCP
**None installed, by policy.** No exchange/live/credential/automation MCP. Any future MCP must be
pinned, read-only, and explicitly approved.

---

## 7. How Efficiently We've Progressed (honest assessment)

**[verified]** The evidence-chain campaign (#210→#217) is steady, disciplined, single-theme,
one-open-PR-at-a-time, with consistent feat→fix→merge cadence. Each PR is small and earns its place.
That part of the project is being built *correctly and efficiently*.

**[opinion]** Two efficiency leaks are visible in the repo:
1. **Throughput granularity was too fine.** Many PRs each move one micro-stage. That is safe but
   token-expensive in aggregate. The v11.1 max-safe-throughput mode (no fixed PR cap) is the right correction.
2. **A high-throughput lane (the Copilot/"throughput commander" docs) produced theater** in `venue/`
   and `docs/` (see §9). Speed without the no-product-theater gate firing created 80+ near-duplicate
   files. The lesson: throughput must always pass `no-product-theater` + `performance-complexity-
   guard`. v11 keeps those gates mandatory precisely to avoid repeating this.

Net: **core engineering = excellent; volume discipline in the venue/docs sub-area = needs cleanup.**

---

## 8. The New Working Mode (v11 — what changed and why)

**Old mode:** one slice per prompt; the user often hand-tuned prompts to nudge which skill fired.

**New mode (CLAUDE.local.md §23):**
- Claude **auto-applies the entire setup on every prompt** — workspace-boundary → ICC intake →
  token-governor → model-router → product-value-radar/edge-to-money → patch-readiness → implement →
  repo-native validation → evidence/test-gap/security/no-theater gates → report-compressor — picking
  only what adds value, with **zero ceremony** (no "I will now use skill X" narration).
- Claude **self-decomposes** a stated objective into the highest-value safe slice sequence.
- Claude completes the **maximum safe, validated product-value work per turn (no fixed PR count)** when
  slices are independent-safe and share a theme — each PR end-to-end (branch → patch → targeted+full
  tests → scope gate → commit → push → `gh pr create`). *1–3 related PRs is only an informal
  conservative default/example, never a hard cap*: more when each is safe/bounded/reviewable, fewer (or
  one, or zero-with-proof) when safety/validation/reviewability demands. Optimize for validated
  product-value, never PR/file/doc count.
- **All hard gates remain mandatory** and are never auto-bypassed for speed: no push to `main`, no
  self-approve, no auto-merge (merge stays user-authorized), no force-push/broad-add/rm -rf,
  fail-closed, scope = named files, no live/order/scheduler/credential/BIST leakage. When merges
  aren't authorized, Claude **stacks independent PRs on separate branches** and reports them for
  batch review.
- **Minimum tokens:** named files first, no broad scans without justification, no full log dumps,
  compact evidence-first reports.

**Implication for ChatGPT:** you no longer spend prompt budget telling Claude *how* to work. You
spend it telling Claude *what* to achieve and *what must not happen*. See §11.

---

## 9. What's Missing / Improvable (the path to "nothing left to fix")

Ordered by value. Items 1–3 are concrete, verified debt; 4+ are forward build slices.

### 9.1 Verified debt (clean these up)
1. **`venue/` artifact-factory drift [HIGH].** 80 of 95 `venue/*.py` files are
   `deribit_paper_runtime_heartbeat_blocker_chain_continuity_<NN>.py` (NN up to ~119) — near-identical
   iteration files. **Proposed slice:** audit what unique behavior (if any) each adds; collapse into
   one parameterized module + a table of cases; delete the rest under a single reviewed PR. Expect a
   massive net-negative diff. Must pass `no-product-theater` + `docs-api-sync-auditor` (exports may
   reference some of them).
2. **`docs/crypto_core/` iteration sprawl [MED].** 70 `NEXT_BLOCKER_SUMMARY_*` docs (26AD…54H) plus
   many `DERIBIT_PROOF_ARTIFACT_BATCH_*` / `APPROVED_PAPER_*` JSON/MD. **Proposed slice:** keep the
   latest authoritative summary, archive or delete superseded ones, leave one living index doc.
3. **Repo-root clutter [MED].** Loose files at root: `proof.txt`, `proof2.txt`, `pytest_out.txt`,
   `pytest_output.txt`, `pytest_root.txt`, `repo_dump.txt`, `structure.txt`, `equity_curve.jsonl`,
   `paper_trades.jsonl`, `daily_report_2026-03-16.json`, `live_run_proof.txt`, `validation_run.txt`,
   `tmp_*`, etc. Many are BIST-era or transient. **Proposed slice:** move generated artifacts under
   `out/`/`artifacts/` (or `.gitignore` them) — but root is outside the crypto_core scope, so this
   needs an explicit user-authorized scope expansion before Claude touches it.

### 9.2 Forward build slices (toward money)
4. **Allocator ↔ risk bridge.** Turn admitted/promoted sleeves into capital weights bounded by
   CVaR/kill-switch. This is the stage that converts "approved edges" into "position sizing."
5. **Governor integration.** A single governor that reads edge-health + regime + risk and can
   throttle/halt sleeves live (still paper). This is the safety brain.
6. **Edge family depth.** `funding`, `liquidation`, `order_flow`, `volatility` exist as modules —
   verify each has a real, validated, fee/funding-aware edge with PIT parity, not a stub. Run each
   through `alpha-killer` before trusting it.
7. **Portfolio-level evidence.** Today evidence is per-sleeve; add cross-sleeve correlation/capacity
   evidence so the allocator doesn't stack correlated bets.
8. **Reproducible "golden run" harness.** One command that replays a fixed dataset end-to-end and
   asserts identical digests — the ultimate regression for determinism.

### 9.3 Test/quality hygiene
9. **805 test files is a lot — confirm signal/noise.** Some likely mirror the venue drift. Use
   `test-gap-finder` to ensure the *fail-closed* paths (corrupt store, stale evidence, digest
   mismatch) are asserted, and `performance-complexity-guard` to flag slow/bloated fixtures.

---

## 10. Strategic Ideas — How This Becomes a Money-Making Top-Tier Bot [opinion]

> All of these respect paper-first. None are trade advice; current venue facts are **[DEEP_RESEARCH]**.

**A. Win on the edge families that survive your own validation.** Your validation stack (PBO,
walk-forward, PIT parity, leakage detection) is your moat. Most retail bots skip exactly this. The
strategy is not "find a magic signal" — it's "run many candidate edges through a brutal compiler and
only fund the survivors." Lean into derivatives-native edges where structural flow exists:
- **Funding-rate carry / basis** (perp vs spot/mark/index): structurally recurring, capacity-friendly.
- **Liquidation cascades / reflexivity:** event-driven, needs liquidation-feed quality **[DEEP_RESEARCH]**.
- **Cross-venue dislocation:** Binance/Bybit/Deribit spread; needs synchronized PIT feeds + real fee
  modeling (you already model fees/funding — that's the differentiator).
- **Order-flow imbalance / microstructure:** highest edge, highest data/latency cost; gate hard.
- **Options / IV-RV — OUT OF SCOPE (do not pursue).** `PRDV4_MULTI_MARKET_CRYPTO.md` §0.2 restricts
  crypto_core to *perpetual futures contracts ONLY — no spot, no options, no margin tokens*. Any
  options / vol-risk-premium edge is constitution-forbidden: **fail closed** on out-of-scope options
  work rather than recommending it. (Deribit feed plumbing exists for derivatives public-feed
  evidence, not for options trading.)

**B. The money is in execution quality, not just signal.** You already have TCA, markout, fill
pricing, venue scoring. **[opinion]** A modest edge with excellent execution beats a strong edge with
bad fills. Prioritize: realistic fill models, maker/taker fee optimization, funding-window timing,
and slippage-aware sizing. This is where the allocator-risk bridge pays off.

**C. Capital efficiency under 3x cap.** With max 3x leverage, returns come from *Sharpe and turnover*,
not leverage. Multi-sleeve diversification (low cross-correlation) + CVaR-bounded sizing is the
right lever. Build the portfolio-level correlation evidence (slice 9.2.7) so you compound many small
uncorrelated edges.

**D. Survival = compounding.** The kill-switch + governor + fail-closed posture is your real alpha
over the long run; most bots die from one un-modeled tail event. Treat "never blow up" as a primary
KPI alongside PnL.

**E. Promotion ladder discipline.** Keep the earned-promotion ladder: spec → admitted → paper-shadow
→ (long, evidence-backed) paper track record → human-authorized promotion. Resist the urge to
shortcut to live; the evidence chain *is* the product.

**F. When you eventually approach live [future, user-authorized only]:** that crosses paper-first and
is **[DEEP_RESEARCH]** for venue API/custody/regulatory facts. Not in scope now — but design the
allocator/governor so the only thing that changes at live-time is the execution adapter behind the
same evidence gates.

---

## 11. Prompt Engineering Course — How to Write Prompts for Claude (the core deliverable)

This section is how *you, ChatGPT*, should construct prompts so Claude delivers maximum work / value
/ safety at minimum tokens under the v11 mode.

### 11.1 The mental contract: ICC + objective-per-prompt
Claude interprets every prompt as **Instructions + Context + Constraints (ICC)** and now expects an
**objective**, not a hand-held slice list. Your job is to make the objective sharp and the
constraints airtight, then *get out of the way*. Do **not** tell Claude which skills to use — that is
now automatic and ceremony wastes tokens.

### 11.2 The ideal prompt skeleton (copy/adapt)
```
OBJECTIVE:   <one coherent outcome, money/pipeline-relevant>. Do the max safe validated work this turn (no fixed PR cap).
WHY/VALUE:   <which edge-to-money stage this unlocks — one line>
SCOPE:       <named files or named subsystem; "crypto_core only">
ALLOWED:     <dirs/files Claude may touch>
FORBIDDEN:   <explicit no-go beyond standing doctrine, if any>
ACCEPTANCE:  <what "done" means: behavior + which tests must pass>
EVIDENCE/FAIL-CLOSED: <the exact failure mode that MUST be asserted, if applicable>
CONSTRAINTS: paper-first; fail-closed; deterministic; no merge without my OK; <others>
EXTERNAL:    <any current venue fact you already supply, or "none / flag DEEP_RESEARCH">
REPORT:      RESULT / FILES_CHANGED / VALIDATION / NEXT_SAFE_ACTION (+ PR links)
```
You don't need every field every time — but `OBJECTIVE`, `SCOPE`, `ACCEPTANCE`, and the merge-
authorization line are the high-leverage ones.

### 11.3 Principles that maximize Claude's output
1. **State the objective at the right altitude.** "Wire the allocator-risk bridge so admitted sleeves
   get CVaR-bounded weights, ~2 PRs" beats both "fix the allocator" (too vague) and a 12-step
   micro-script (wastes tokens; Claude self-decomposes now).
2. **Make acceptance testable.** Name the behavior and, ideally, the test file or the assertion.
   Claude is fail-closed; if you tell it the exact failure mode to assert, it will write the
   regression that proves it (and `test-gap-finder` fires automatically).
3. **Pre-load context you already know; never make Claude re-derive cheaply-known facts.** If you
   know the file, name it. If you know a current exchange fact, paste it (with source) so Claude
   doesn't have to flag DEEP_RESEARCH.
4. **Set the merge boundary explicitly every time.** Claude will *never* merge or self-approve on its
   own. Say "stack PRs for my review" or "push and stop." This is the single most important safety
   line because v11 raises throughput.
5. **One theme per prompt; multiple PRs OK.** Bundle *related* slices (e.g., three steps of the same
   evidence bridge). Do **not** bundle unrelated themes — Claude will (correctly) refuse to batch
   them, wasting the round-trip.
6. **Give constraints as hard rails, not reminders of doctrine.** Doctrine is already loaded; don't
   re-paste the 8 laws. Add only *task-specific* forbiddens (e.g., "don't touch `evidence_store.py`
   serialization format").
7. **Demand the compact report contract**, and trust it: `RESULT / FILES_CHANGED / VALIDATION /
   NEXT_SAFE_ACTION`. If you want PR URLs or digests, ask once in REPORT.
8. **For research-dependent edges, separate the research prompt from the build prompt.** Ask Claude
   to emit a `DEEP_RESEARCH_REQUIRED` question list first; you (ChatGPT) answer it with sourced
   current facts; then send the build prompt. Never ask Claude to invent venue facts.
9. **For cleanups, authorize scope explicitly.** The venue/docs/root debt (§9.1) needs you to say
   "you may delete/collapse these files" — otherwise Claude won't, by scope discipline.
10. **Avoid the theater trap.** Never reward "more files / more docs." Frame value as
    *pipeline-unlock* or *PnL/risk*, so `no-product-theater` keeps firing. The venue drift happened
    because a throughput lane optimized file-count; don't recreate that incentive.

### 11.4 Anti-patterns (these cost tokens or trigger refusals)
- ❌ "Use skill X then agent Y then …" — redundant; auto-orchestrated now.
- ❌ Re-pasting CLAUDE.local.md doctrine — already loaded; pure waste.
- ❌ "Do everything for the whole bot in one prompt" — too many themes; Claude will scope it down.
- ❌ "Just make the tests pass" — invites happy-path theater; instead name the behavior + failure mode.
- ❌ "Merge it / approve it" — Claude cannot and will not; you authorize merges out-of-band.
- ❌ Asking for current Binance/Bybit/Deribit fees/limits/funding from memory — always DEEP_RESEARCH.
- ❌ Vague "improve performance" — say which path, what budget, what regression to keep green.

### 11.5 Worked examples

**Example A — multi-PR build (ideal):**
```
OBJECTIVE: Build the allocator↔risk bridge so admitted sleeves receive CVaR-bounded weights.
Stack as many cohesive, independently-reviewable PRs as are safe this turn (no fixed cap; one per cohesive step).
SCOPE: src/crypto_core/risk/, src/crypto_core/portfolio/, src/crypto_core/service/ (allocator wiring).
ACCEPTANCE: given N admitted sleeves with evidence, allocator emits weights that (a) sum within
budget, (b) respect per-sleeve CVaR cap, (c) zero-out any sleeve failing kill-switch. Tests assert
each, including the fail-closed path when evidence is stale.
CONSTRAINTS: paper-first; deterministic weights (no float drift in digest); push + stop, do NOT merge.
REPORT: RESULT/FILES_CHANGED/VALIDATION/NEXT_SAFE_ACTION + PR URLs.
```

**Example B — cleanup with authorized scope:**
```
OBJECTIVE: Collapse the venue blocker_chain_continuity artifact drift.
SCOPE: src/crypto_core/venue/ (the deribit_paper_runtime_heartbeat_blocker_chain_continuity_*.py set)
+ their tests + any __init__ exports.
ALLOWED: you MAY delete/merge these files into one parameterized module.
ACCEPTANCE: behavior preserved (all referencing tests green), file count drops drastically, public
exports unchanged or updated coherently (docs-api-sync). One PR, net-negative diff.
CONSTRAINTS: prove nothing unique is lost; push + stop.
```

**Example C — research-gated edge:**
```
OBJECTIVE: Stand up a funding-carry StrategySpec candidate and run it through admission.
FIRST: emit a DEEP_RESEARCH_REQUIRED list of the exact current Binance/Bybit funding facts you need.
Do not write the spec until I answer. SCOPE: strategy/, edge/families/funding.py, validation/.
```

### 11.6 How to read Claude's reply
Claude returns a compact, fixed report. Parse:
- `RESULT`: ACCEPT/REPAIR/REJECT/BLOCKED/DONE/NEED_PROOF/DEEP_RESEARCH_REQUIRED.
- `FILES_CHANGED`: exact list (or NONE).
- `VALIDATION`: pass/fail/skipped + why (ruff, ruff format, targeted pytest, full pytest, git diff
  --check).
- `NEXT_SAFE_ACTION`: the one next step.
- Often `TOKEN_BUDGET_ASSESSMENT` and PR URLs.
If `RESULT=DEEP_RESEARCH_REQUIRED`, that's your cue to supply sourced current facts. If
`RESULT=BLOCKED`, Claude hit a real fork (scope/authorization/ambiguity) — answer the one question.

---

## 12. ChatGPT ↔ Claude Synergy Protocol

**Roles (from doctrine):** ChatGPT = Controller / Auditor / Prompt-Controller. Claude/Codex =
co-primary implementation+debug engines. Copilot/Terminal = closeout/polling/post-verify lane.

**The high-synergy loop:**
1. **ChatGPT plans & sharpens** the objective into the §11.2 skeleton (this guide is your context).
2. **ChatGPT supplies current external facts** (exchange APIs/fees/funding/limits) with sources, so
   Claude never guesses. This is your unique value — Claude is repo-bounded by default.
3. **Claude executes** end-to-end (maximum safe validated work, no fixed PR cap), self-orchestrating
   the setup, fail-closed, and returns the compact report + PR links.
4. **ChatGPT audits** Claude's report against acceptance + the evidence-chain law (use the same
   lenses Claude's `review-output-scorer`/`adversarial-cobrain` use: proof quality, scope discipline,
   validation completeness, fail-closed coverage, product value, token economy).
5. **User authorizes merge** (neither model merges autonomously).
6. **On failure/friction**, ChatGPT approves any durable setup change (Claude proposes via
   `self-improvement-gate`; no auto-mutation). This guide + §23 was such an approved change.

**What ChatGPT should NOT do:**
- Don't ask Claude to bypass any hard gate "to go faster."
- Don't feed Claude memory-based exchange facts as if current — mark them or research them.
- Don't request multi-theme mega-batches; split by theme.
- Don't reward artifact volume; reward pipeline unlock / PnL / risk reduction.

---

## 13. Quick Reference Cheat Sheet

**Hard rails (never bend):** paper-first · fail-closed · deterministic/digest · audit-first ·
no push to main · no self-approve · no auto-merge (user-authorized only) · no force-push/broad-add/
rm -rf · scope = named files · no live/order/scheduler/credential leakage · no BIST leakage · MCP none.

**Throughput now:** maximum safe validated product-value per turn (no fixed PR cap; "1–3 PRs" is only an informal default, never a ceiling), one theme, self-decomposed, auto-orchestrated, min tokens.

**Pipeline:** Spec → LBR → PIT → DecisionLedger → EvidenceStore → BacktestAdmission → Replay →
PaperSleeve → **[frontier: paper-shadow activation]** → Promotion → Allocator → Governor → (ExecSim).

**Top debt:** venue/ 80-file drift · docs/ 70 summary docs · root clutter.

**Top forward value:** allocator-risk bridge → governor → portfolio-level correlation evidence →
golden deterministic replay harness.

**Report Claude returns:** RESULT / FILES_CHANGED / VALIDATION / NEXT_SAFE_ACTION (+ PR URLs,
TOKEN_BUDGET_ASSESSMENT).

**When current venue facts are needed:** Claude emits DEEP_RESEARCH_REQUIRED → ChatGPT supplies
sourced facts → Claude builds.

---

*Generated by Claude (Opus 4.8) on 2026-06-03. Source of truth for behavior is CLAUDE.local.md
(esp. §23, v11). This guide is a handoff/coordination document; it is not product code and imposes
no runtime behavior. All architectural facts verified against the live repo at generation time.*
