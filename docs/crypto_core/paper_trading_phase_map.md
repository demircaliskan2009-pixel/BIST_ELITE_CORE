# crypto_core Paper Trading Phase Map (PRD Addendum)

> Lightweight, action-guiding **PRD addendum / phase map** — *not* a PRD rewrite. Persists the Deep
> Research benchmark decision (advisory input only) into the repo so product work pivots from isolated
> evidence/admission artifacts to **integration-first paper trading**. Companion to
> `docs/PRDV4_MULTI_MARKET_CRYPTO.md` (authority), `docs/crypto_core/deep_research_protocol.md`,
> `docs/crypto_core/agent_workflow.md`, and `docs/crypto_core/agent_lessons.md`. Paper-first,
> deterministic, fail-closed, audit-first. No secrets, credentials, API keys, or live-trading
> instructions. crypto_core only — BIST is historical context.

## 1. Status

- This is a **PRD addendum / phase map**, not a full PRD rewrite.
- **`docs/PRDV4_MULTI_MARKET_CRYPTO.md` remains the product-architecture authority** (6 invariants;
  validation pipeline §1.13 Backtest → Walk-Forward → Stress → Paper Trading → Live Scaled; roadmap §16
  Phase 4 = Paper Trading). Nothing here overrides PRDV4; on conflict the stricter safety rule wins.
- **PR #290** (`paper_evidence_admission_record`, merge `70d2208`) and **PR #291** (Deep Research
  protocol, merge `9e9e86a`) are incorporated as context.
- Deep Research benchmark conclusion (advisory): the build is **broad and mature**; the dominant risk is
  **artifact proliferation vs end-to-end wiring**, not lack of modules.

## 2. Current built substrate (proven from `git ls-files src/crypto_core`)

The realized-PnL → admission chain already exists as discrete, digest-bound modules:

```
paper_realized_pnl
  -> paper_realized_pnl_rollup
  -> paper_session_realized_pnl_bridge
  -> paper_session_realized_pnl_aggregate
  -> paper_session_realized_pnl_evidence_manifest
  -> paper_evidence_admission_record
```

Adjacent substrate that already exists (isolated, not yet proven as one loop):

- **Intent / fill / position / episode:** `paper_order_intent`, `paper_order_intent_admission`,
  `paper_allocator_intent_draft`, `paper_fill_simulator`, `execution/paper_adapter`,
  `execution/fill_pricer`, `portfolio/fills`, `paper_position_state`, `paper_episode_runner`,
  `paper_session_sequence`, `paper_capacity_gate`, `paper_trade_tick`.
- **Reports / replay:** `paper_pnl_report`, `paper_replay_result_report`(`_adapter`),
  `paper_replay_run_plan`, `paper_replay_intake`, `deterministic_replay_executor`,
  `paper_replay_promotion_readiness`, `paper_replay_governance_review_decision`.
- **Governor / readiness / promotion (paper-stage):** `audit/portfolio_governor_*`, `service/readiness`,
  `paper_sleeve_admission_review_readiness`, `paper_sleeve_promotion_candidate`,
  `paper_sleeve_promotion_readiness`, `paper_sleeve_risk_budget_decision`, `paper_sleeve_intent_ledger`.

**Out of scope for the minimum deterministic paper loop (reference-only):**
`service/paper_shadow_session_controller`, `service/paper_live_service`, and any other shadow/live runtime
service surface are **explicitly excluded** from the minimum deterministic paper-loop phase and from
`feature/paper-run-report-pr1`. They are **not usable** until a separately authorized shadow/live phase
(see §6). The deterministic paper loop **must not depend on** shadow/live service surfaces.

**Safety note (deterministic paper substrate):** the minimum deterministic paper loop must use only
deterministic, replayable validation modules — **no shadow/live service surface, no hidden
IO/thread/wall-clock/random runtime, no scheduler/auto-loop, no live/private API, and no real order
routing.** Anything outside that boundary is reference-only here and gated to a separately authorized phase.

**Implication:** the components for a minimum paper loop largely exist. The gap is **wiring + one proven
deterministic end-to-end path**, not more sibling modules.

## 3. Strategic pivot — integration-first

- **Stop** adding isolated evidence/admission/“sibling” artifacts without an integration seam.
- Next product work must **prove one full deterministic paper loop** end to end.
- **Integration-first now has priority** over artifact proliferation. A new artifact PR is justified
  **only** when it binds a real integration seam or closes a named loop gap (see §8).

## 4. Minimum deterministic paper trading — DONE definition

One deterministic, replayable loop:

```
strategy / signal output
  -> normalized deterministic paper order intent      (paper_order_intent[_admission])
  -> deterministic paper fill                         (paper_fill_simulator / execution.paper_adapter + fill_pricer)
  -> paper position / realized PnL                     (paper_position_state / paper_realized_pnl[_rollup])
  -> session / aggregate / manifest                    (…_bridge / …_aggregate / …_evidence_manifest)
  -> evidence admission                                (paper_evidence_admission_record)
  -> paper run report / probe                          (paper_pnl_report / new paper run report)
```

DONE requires: **replayable deterministic digests** end to end (recompute == bound digest at every
seam); **fail-closed** on malformed/stale/insufficient input (typed error or REJECTED reason codes);
no hidden IO/network/persistence/wall-clock/random in product code. **No live/private API. No real order
routing. No scheduler/auto-loop.**

## 5. Institutional-grade paper trading — DONE definition

Builds on §4 and additionally requires:

- Multi-episode / multi-session management (`paper_session_sequence`, `paper_episode_runner`).
- Replay / stress / scenario evidence (`deterministic_replay_executor`, `paper_replay_*`).
- Paper-only **governor / risk decision artifact** (`paper_sleeve_risk_budget_decision`,
  `audit/portfolio_governor_*`) — paper-only, no real capital/equity/margin/balance/reservation.
- Operator-facing **report / probe** (readable run report; discrepancy surface).
- Digest-bound **promotion / readiness evidence** (`paper_replay_promotion_readiness`,
  `paper_sleeve_promotion_readiness`, `portfolio_governor_readiness*`) — paper-stage only.
- **Discrepancy detection** (replay vs original; expected vs actual) with fail-closed reporting.
- **Audit export / readability** (journal adapters; deterministic, reviewable evidence).
- **Shadow / live separation remains blocked** (no live promotion path activated here).

## 6. What NOT to build yet (hard blocks)

- Live / private API; credentials / API keys.
- Deribit active readiness / venue transition.
- Real order routing; venue/exchange/client-order-id; route_id / execution_instruction.
- Scheduler / auto-loop / shadow / live execution.
- Real capital / equity / margin / balance / reservation governor (paper-only artifacts only).
- Live reconciliation.
- MCP / AI live mutation of repo or trading state.
- **BIST implementation leakage.**

## 7. Next 5–8 PR sequence (integration-first)

Each is one bounded feature PR, full validation, one open PR at a time, no merge without explicit
authorization. Order holds unless repo evidence proves a step impossible. Several targets already have
isolated modules — these PRs **wire/bind** them, they do not rebuild from scratch.

1. `feature/paper-run-report-pr1` — bind existing episode / session / realized / manifest / admission
   digests into **one deterministic paper run report / probe** (operator-readable; recompute-verified).
2. `feature/strategy-signal-to-paper-intent-pr1` — deterministic fail-closed bridge from
   StrategySpec / signal output to **paper order intent**.
3. `feature/paper-end-to-end-episode-pr1` — one deterministic episode path **intent → fill → position →
   realized PnL** (proves §4 loop body).
4. `feature/paper-admission-ledger-bridge-pr1` — append admission records to an **existing** evidence
   journal / store (no new store proliferation).
5. `feature/paper-governor-decision-pr1` — **paper-only** risk / governor decision artifact; no real
   capital / margin / equity.
6. `feature/deterministic-paper-replay-harness-pr1` — replay the same paper run and **prove digest
   equality** (discrepancy = fail-closed).
7. `feature/paper-stage4-readiness-decision-pr1` — consume run report + admission + replay evidence for
   **paper-stage readiness only**; no live.
8. *(optional, later)* `chore/crypto-core-test-wrapper-venv-python-pr1` — make the full-test wrapper use
   the repo `.venv` interpreter (or deterministic interpreter selection) so optional deps like
   `websocket-client` resolve consistently. (Observed: `run_full_tests_logged.ps1` calls bare `python`;
   on a PATH where that is system Python312 without `websocket-client`, full-suite collection fails on
   `data/ingestion/binance_ws_client.py`. The `.venv` has the dep.)

## 8. Overengineering guardrails

- Evidence / admission artifacts are allowed **only when they bind a real integration seam**.
- **No new “sibling artifact” PR** unless it closes a **named** paper-loop gap from §4/§5/§7.
- Prefer an **operator-readable run report / probe** over yet another internal record type.
- **No product-theater docs** that substitute for code/tests; this addendum guides code, it is not a
  deliverable in place of code.
- Reuse existing service surfaces / journals before adding new modules or stores.

## 9. Deep Research usage for milestone decisions

- Use Deep Research for **milestone / benchmark / current external facts** (paper-DONE vs institutional
  thresholds, framework benchmarks, exchange/readiness facts) per
  `docs/crypto_core/deep_research_protocol.md`.
- **Not** for local proof gates (tests/CI/repo state/merge readiness).
- Always **read-only / advisory** — never an executor lane, never merge authority, never a safety-gate
  waiver.
- Always bucket findings as `REPO_EVIDENCE` / `EXTERNAL_EVIDENCE` / `INFERENCE` / `UNKNOWN`; never infer
  live repo state without GitHub evidence.
