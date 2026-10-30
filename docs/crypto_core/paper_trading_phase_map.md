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
  `paper_allocator_intent_draft`, `paper_fill_simulator`, `execution/fill_pricer`, `portfolio/fills`,
  `paper_position_state`, `paper_episode_runner`, `paper_session_sequence`, `paper_capacity_gate`,
  `paper_trade_tick`.
- **Reports / replay:** `paper_pnl_report`, `paper_replay_result_report`(`_adapter`),
  `paper_replay_run_plan`, `paper_replay_intake`, `deterministic_replay_executor`,
  `paper_replay_promotion_readiness`, `paper_replay_governance_review_decision`.
- **Governor / promotion (paper-stage):** `audit/portfolio_governor_*`,
  `paper_sleeve_admission_review_readiness`, `paper_sleeve_promotion_candidate`,
  `paper_sleeve_promotion_readiness`, `paper_sleeve_risk_budget_decision`, `paper_sleeve_intent_ledger`.

**Out of scope for the minimum deterministic paper loop (reference-only):**

- `service/paper_shadow_session_controller`, `service/paper_live_service`, and any other shadow/live
  runtime service surface — **explicitly excluded** from the minimum deterministic paper-loop phase and
  from `feature/paper-run-report-pr1`; **not usable** until a separately authorized shadow/live phase
  (see §6). The deterministic paper loop **must not depend on** shadow/live service surfaces.
- `service/readiness` — a **live-readiness** surface (defines `PAPER_LIVE` / `SHADOW_LIVE` /
  `TINY_CAP_LIVE` levels and live-credential / live-data-feed criteria). It is **not** deterministic
  paper-stage substrate: reference-only and **excluded** from the minimum paper loop and from
  `feature/paper-run-report-pr1`. **The paper-run-report PR must not consume readiness/live/shadow
  service surfaces.**
- `execution/paper_adapter` — **non-canonical** for the minimum deterministic loop: it reads wall-clock
  time (`time.time_ns()`), conflicting with the no-hidden-wall-clock rule. **Not part of**
  `feature/paper-run-report-pr1`, and out of the deterministic loop until its timestamp behavior is
  explicitly hardened / injected / made deterministic. Use existing deterministic validation primitives
  (`paper_fill_simulator` + the paper position / realized-PnL chain) instead.

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

## 4. Minimum deterministic paper-loop substrate milestone (NOT PRDV4 Stage 4 completion)

> **Scope:** this is a deterministic *substrate milestone* — it proves a replayable deterministic paper
> loop. It is **not** PRDV4 Stage 4 ("Paper Trading") completion. PRDV4 Stage 4 additionally requires
> **≥ 30 days paper trading**, **paper-vs-backtest metrics** (Sharpe, hit rate, slippage, fill rate),
> and the **paper-Sharpe ≥ 50%-of-backtest** rejection gate (PRDV4 §"Stage 4: Paper Trading"). Those
> remain **later** requirements and are **not** satisfied by this milestone.

One deterministic, replayable loop:

```
strategy / signal output
  -> normalized deterministic paper order intent      (paper_order_intent[_admission])
  -> deterministic paper fill                         (paper_fill_simulator + fill_pricer; existing deterministic validation primitives — NOT execution/paper_adapter, which uses wall-clock)
  -> paper position / realized PnL                     (paper_position_state / paper_realized_pnl[_rollup])
  -> session / aggregate / manifest                    (…_bridge / …_aggregate / …_evidence_manifest)
  -> evidence admission                                (paper_evidence_admission_record)
  -> paper run report / probe                          (paper_pnl_report / new paper run report)
```

Milestone DONE requires: **replayable deterministic digests** end to end (recompute == bound digest at
every seam); **fail-closed** on malformed/stale/insufficient input (typed error or REJECTED reason
codes); no hidden IO/network/persistence/wall-clock/random in product code. **No live/private API. No
real order routing. No scheduler/auto-loop.** (This is the substrate milestone above, not PRDV4 Stage 4.)

## 5. Institutional paper-substrate readiness target (NOT PRDV4 Stage 4/live readiness)

> **Scope:** an institutional-grade *paper-substrate* target — **not** live/shadow readiness and **not**
> PRDV4 Stage 5 / live readiness. It does **not** satisfy the PRDV4 Stage 4 completion gates (≥ 30-day
> paper trading, paper-vs-backtest metrics, Sharpe gate — see §4); those remain later requirements.

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
   a **paper-substrate readiness decision only**; no live. (This is a paper-substrate readiness
   artifact — **NOT** PRDV4 Stage 4 completion, which still requires the §4 ≥30-day / paper-vs-backtest /
   Sharpe gates.)
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

## 10. Post-§7 checkpoint — paper-metrics phase (recorded after PR #299, `main` @ `fb800ab`)

> Planning checkpoint only. This is a **docs-only** phase decision — it adds **no** code, **no** test, and
> **no** runtime artifact, and authorizes none. It records the state after the §7 integration-first sequence
> and sequences the next bounded slices; each future slice still needs its own explicit authorization, full
> validation, one open PR, and merge only on explicit per-PR authorization (workflow §3/§7).

### 10.1 §7 completion (proven from `git log` / merged PRs)

The §7 integration-first **deterministic paper-substrate** sequence is complete (PRs #293–#299, all merged):

```
strategy signal → paper order intent (#294) → end-to-end episode: intent→fill→position→realized PnL (#295)
  → evidence admission ledger bridge into the existing journal (#296) → paper governor decision (#297)
  → deterministic paper replay-equality harness (#298) → paper-substrate readiness decision (#299)
  (+ operator-readable paper run report, #293)
```

This is a **deterministic paper substrate**, recompute-verified and digest-bound at every seam, fail-closed,
with no hidden IO/wall-clock/random. It is **not** operational paper trading.

### 10.2 Substrate-complete vs product-incomplete (explicit)

- Deterministic paper substrate = **COMPLETE** (the §7 chain above).
- Paper trading **product** = **NOT complete** (no multi-session/30-day operational paper run system).
- PRDV4 **Stage 4** ("Paper Trading") = **NOT complete** — PRDV4 §"Stage 4: Paper Trading" still requires
  **≥30 days** paper trading, **paper-vs-backtest** metrics (Sharpe, hit rate, slippage, fill rate), and the
  **paper-Sharpe ≥ 50%-of-backtest** rejection gate. None are satisfied.
- Live / shadow / Deribit / operational readiness = **NOT started** (and remain hard-blocked, §6).
- Profitability / edge = **NOT proven**.

### 10.3 The deterministic-vs-time-series fork (the real next decision)

The §7 substrate is **single-run / episode-oriented, gross/count/provenance-oriented, deterministic, and
digest-bound** — it carries **no wall-clock and no return series**. PRDV4 Stage 4 evidence is **time-series /
multi-session**: a ≥30-day period, a paper-vs-backtest comparison, and annualized risk metrics (Sharpe / hit
rate / slippage / fill rate). The existing `src/crypto_core/validation/stage4_comparator.py` already encodes
this gate (`Stage4BacktestBaseline`, `Stage4PaperSummary`, `compare_stage4`) but its `Stage4PaperSummary`
requires a **computable `paper_sharpe`** and **`started_at_ns` / `stopped_at_ns`** (a session duration) — it
fails closed with `stage4:paper_sharpe_not_computable` / `stage4:paper_time_invalid` otherwise. The §7
substrate cannot produce these today, so feeding the comparator now is **premature/blocked**.

Decision rule for the post-§7 path: **no real wall-clock may be smuggled into deterministic validation
artifacts.** Any time / return-window evidence must come from **injected deterministic timestamps** or
explicitly bounded evidence packages — never `time`/`datetime.now`/`perf_counter`. The time/methodology model
is an explicit design decision, not an automatic continuation.

### 10.4 Proposed post-§7 product sequence (paper-metrics path)

One bounded feature PR each, integration-first (wire/bind existing artifacts; do **not** rebuild), paper-only,
deterministic, fail-closed, digest-bound, one open PR at a time, no merge without explicit authorization.
Order holds unless repo evidence proves a step impossible.

1. `feature/paper-session-metrics-summary-pr1` — a **deterministic, paper-only, time-free** session metrics
   summary: gross / count / session-aggregate descriptors (episode count, closed-units / realized-PnL gross
   totals, win/loss/flat counts) bound by digest from the **existing** session realized-PnL aggregate and the
   §7.7 readiness decision. **No Sharpe yet** (no time model). PRECHECK MUST first prove this is **not** already
   covered by `paper_session_realized_pnl_aggregate` — if it is, narrow or skip (§8 anti-proliferation).
2. `feature/paper-deterministic-time-window-adapter-pr1` — a deterministic **time/methodology adapter** using
   **injected timestamps only** (no wall-clock); defines return windows and sample-eligibility for metrics.
3. `feature/paper-vs-backtest-comparator-bridge-pr1` — a fail-closed **bridge that safely feeds the existing
   `stage4_comparator.py`** from the deterministic metrics + injected-time evidence; no live/shadow/readiness.
4. `feature/paper-30day-evidence-gate-pr1` — a deterministic **≥30-day paper-evidence gate** — only **after**
   deterministic time-series/session evidence exists; **may require Deep Research** for the gate methodology.
5. `feature/paper-stage4-review-package-pr1` — a **review-package artifact only** (operator-reviewable Stage-4
   evidence dossier). Still **no** live/shadow/Deribit activation; live/shadow remains a separately authorized
   phase (§6).

### 10.5 Optional §7.8 chore (deferred)

`chore/crypto-core-test-wrapper-venv-python-pr1` (§7 item 8) remains **optional and deferred** — it is test
wrapper interpreter **hygiene**, not product progression. It may be done opportunistically as a standalone
`chore/*` setup PR (docs/config/scripts only), never mixed into a feature PR.

### 10.6 Deep Research rule (this checkpoint)

- **Not required** for this planning checkpoint (it is repo-internal phase reconciliation).
- **Required later** if external / current methodology facts are needed for: Sharpe annualization convention,
  paper-vs-backtest methodology, the 30-day paper-gate design (§10.4.4), or any Deribit / live / shadow
  readiness or exchange-microstructure / current-venue facts. Deep Research stays read-only / advisory
  (`docs/crypto_core/deep_research_protocol.md`), never an executor lane or safety-gate waiver.

### 10.7 GitHub connector rule

- The GitHub connector remains the **read-only source-of-truth final PR gate** (PR/CI/threads/reviews/
  mergeability). **Not needed** for phase design unless the question is GitHub-state-specific.
- Every future §10.4 implementation PR still needs the connector final gate (or proven `gh` state) before any
  explicit per-PR merge authorization.

### 10.8 Guardrails reaffirmed (unchanged from §6/§8)

No `service/readiness`; no `execution/paper_adapter`; no venue / Deribit / live / shadow surfaces; no
scheduler / auto-loop; no real orders / order routing; no real capital / equity / margin / balance /
reservation; no BIST; no hidden IO / wall-clock / random; no PRDV4 Stage 4 completion claim; no
profitability / edge claim; no live / shadow / operational readiness claim.

### 10.9 Stop conditions for future §10.4 code

A future §10.4 feature PR must **stop with proof** if it would: require live / Deribit / readiness / service /
adapter surfaces; require real wall-clock; duplicate an existing aggregate / artifact; fail to prove public
digest binding (recompute == stored == anchor); blur a paper-substrate candidate with actual Stage-4
completion; or claim live / shadow / readiness / edge / profitability.

## 11. Stage-4 methodology chain status (post-PR #319, recorded 2026-07-07)

The §10.4 sequence is complete and the Stage-4 methodology chain continued past it. Merged (all standard
head-pinned merges; `main` @ `e278293cd5537cfa7174db79a1238a686199275a` after #319):

- #310 `paper_sharpe_evidence` → #311 `paper_vs_backtest_methodology` → #312 `paper_edge_identity_evidence`
  → #313 `paper_stage4_backtest_baseline_evidence` → #316 `PaperStage4ComparisonEvidence` (first authorized
  `compare_stage4` call; Decimal-authoritative retention verdict) → #317 `PaperStage4CompletionDecision` v1
  (**BLOCKED completion** — `prdv4_stage4_complete=False` structural, four digest-bound blockers) →
  #318 `PaperAttestedOperationalDayEvidence` → #319 `PaperAttestedOperationalThirtyDayGateDecision`.
- The #318/#319 attested chain is **operator-attested, not machine-proven**
  (`attestation_source="operator_attested_not_machine_proven.v1"`; all five machine-proof flags structurally
  False). A satisfied attested gate is **not** operational readiness, not machine-time proof, and not
  Stage-4 completion.
- **Next technical PR:** `PaperStage4CompletionDecisionV2` — Path A conservative
  (`docs/crypto_core/agent_workflow.md` §21.6): consumes the comparison/Sharpe/30-day chain, the attested
  30-day gate, and the predecessor v1 decision; proves selected UTC day-index alignment; keeps
  `prdv4_stage4_complete=False`; narrows blockers (drop stale `operational_day_evidence_source_unavailable`;
  add `operator_attested_only_machine_time_origin_unproven`; keep
  `timestamp_origin_not_proven_injected_deterministic_time_only` and the secondary-metrics blocker).
- **Remaining before any completion=True (v3, separately authorized):** machine-time origin proof (design
  first; Deep Research likely) and enforced hit/fill/slippage secondary metrics. §10.8 guardrails and §10.9
  stop conditions bind unchanged.
- **Canonical execution queue (ROADMAP ONLY — not current implementation state; every step needs its own
  authorization and fresh state proof):** PR #320 merge → `PaperStage4CompletionDecisionV2` → docs-sync →
  completion review dossier → design-doc chores `[SM-1, MT-1, EF-1, RG-1, RF-1]` → combined Deep Research
  `[PRM-07 + PRM-16]` → governance threshold approvals → SM-2..6 → EF-2..8 → RG-2..8 → RF-2..7 → MT-2..6 →
  funding pilot slices → completion decision **v3 only if all required proofs exist** (machine-proven
  30-day gate + enforced secondary metrics + explicit human authorization). Contract details:
  `docs/crypto_core/fable_exit_contract_index.md` (archived design doctrine, never current-state proof).

## 12. Governed paper execution (recorded 2026-10-16)

`GOVERNED_PAPER_TYPED_PROVENANCE_V2` connects the authenticated EF-7 v2 admitted variant to governed, sealed, paper-only
days on the one economics engine (design: `multi_sleeve_risk_governance_design.md` §7):

- built (SYNTHETIC CONSTRUCTION ONLY): the engine's two refuse-only admission hooks and governed outcome, the typed
  identity module, the genesis and per-cycle authority, the day seal and the lineage evidence;
- the generic paper chain is a verified pass-through projection of the engine, never a second economics; RG-3 consumes
  exactly the sealed projected history;
- REAL_PAPER_EXECUTION stays BLOCKED until the human commitments C1-C9 and the Deep Research result D1 exist
  (`governance_decision_framework.md` §6a); every test value is synthetic and every test approval a fixture;
- non-claims: no order, capital, venue fill, scheduler, live or shadow path, readiness or Stage-4 completion, and the
  `E_k` instants are injected UTC coordinates, not machine-time proof.

Entry safety (`S1_PAPER_ENTRY_SAFETY_CLOSURE_V1`, `governed_paper_entry_safety.py`):

- every S1 entry decision is evaluated against all 26 NO-TRADE ids that PRDV4 §1.21 enumerates (its heading says 23)
  and the seven §1.9 Family B gates; the first non-admitting check refuses the entry, and the engine refuses only that
  entry, never an exit;
- on the selected data contract (final funding, mark, L2 depth-50 book) NT-D01 and 21 further NO-TRADE conditions
  are BLOCKED_ON_MISSING_INPUT, three are enforced (NT-D02, NT-X01, NT-T01), NT-M04 is not applicable to a
  one-sleeve portfolio, and the §1.9 24-hour holding exit, 1.5 x ATR_4h stop and stop tightening are
  BLOCKED_PROTECTION_UNREPRESENTABLE. EVERY S1 paper entry is therefore refused: the governed path opens no position
  until those measurements and protections exist, which needs a separate design and authorization;
- this is fail-closed construction, not activation, a qualified source, Stage-4 completion or a profitability claim.
  The downstream fill mechanics are exercised only under an explicit test-only permissive rule table.

Protective position lifecycle (`PROTECTIVE_POSITION_LIFECYCLE_V1`, recorded 2026-10-24):

- the one economics engine applies an optional position-management policy (result schema v2): the 24 h maximum hold
  from the first opening fill, and the 1.5 x ATR_4h stop on PIT-visible marks with Wilder ATR(14) (DEC-7) over an
  authenticated offline OHLC bar archive. Each is a close-only standing obligation filled through the engine's own
  book, latency, spread, depth and fee model; an unfilled close stays an OUTSTANDING obligation with its breach
  duration, and a price gap never guarantees the stop price;
- governed paper uses the same engine semantics. A digest-bound, human-governed protective authority (DEC-1) lets a
  close-only protective action bypass the cycle direction ceilings, the cycle window and the post-invalidation entry
  ban. It never opens, increases or reverses a position, and a missing, expired or revoked authority refuses the
  attempt and leaves explicit breach evidence. Day seal v3 and lineage evidence v3 carry the excursion's deciding
  cycle and the pending protective attempt across day boundaries; legacy v1/v2 artifacts are byte-identical;
- entry gate rule set v2 passes FB-MAX-HOLD and FB-STOP only when the protective window covers the holding horizon
  (and, for FB-STOP, the ATR_4h reading exists). FB-STOP-TIGHTENING stays BLOCKED: the DEC-9 tightening reading needs
  a human approval no one has given, and it runs only under test-only synthetic approvals. Every S1 entry is still
  refused, first by NT-D01: the 22 missing NO-TRADE inputs and the other Family B gates are unchanged;
- REAL_PAPER_EXECUTION stays BLOCKED: no qualified OHLC source (M1), no accepted venue facts (D1) and no C1-C9
  decisions exist. Every bar, policy value and approval in the tests is synthetic.

Native NO-TRADE portfolio measurement (`S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1`, recorded 2026-10-26, repaired
2026-10-27 after its independent audit):

- the lineage re-runs under the information-time admission schedule v4: the settlement ledger still books a funding
  settlement at its liability instant from its final rate, but every admission, at a decision and at a fill alike,
  reads the publication-visible equity, which excludes each settlement whose final rate is not yet published. A
  final rate therefore reaches no intent, fill, position, protective record or snapshot before its publication;
- the governed re-run records, at each decision instant and before its admission, the exact governed portfolio then
  known (decision portfolio v1): the position, any order in flight, the fresh visible mark, the NAV and the NAV at the
  UTC midnight that starts the decision's day (both publication-visible; the unknown amounts are recorded nowhere),
  and the decision's candidate, the position its intent targets. A partial first day, or a decision at the midnight
  itself, has no day-start NAV, and none is substituted (no genesis or other baseline);
- entry gate rule set v3 evaluates that snapshot: NT-R02 FAILS strictly below -2% of the day-start NAV (equality does
  not trigger). NT-R04 FAILS strictly above 25% of NAV for the current position and for an entry candidate at the mark
  net of its own taker fee, and the engine refuses any exposure-increasing fill strictly above 25% of its exact
  post-fill publication-visible equity. NT-R03 measures zero current risk only with no position and no order in
  flight, and is BLOCKED for an open position and for every prospective entry (no position risk measure is defined),
  so it refuses every entry. Each is BLOCKED wherever the snapshot cannot support a reading, and only a one-sleeve
  paper portfolio is measured;
- admission is sequential: each entry is evaluated on the portfolio its admitted predecessors produce (the unique
  fixed point, never a neutral replay). Day seal v4 and lineage evidence v4 bind it for a lineage that opts in from
  day 0; v1-v3 artifacts, schedules v2/v3 and rule sets v1/v2 are byte-identical;
- every S1 entry is still refused first by NT-D01. The NT-R02 reading (current UTC day, day-start NAV) and the NT-R04
  readings are engineering adjudications, not governance values, and the engine's initial equity implies no C1-C9
  decision (C5 included). REAL_PAPER_EXECUTION stays BLOCKED. Every value and approval in the tests is synthetic.

Native market-data integrity measurement (`S1_MARKET_DATA_INTEGRITY_NATIVE_MEASUREMENT_CLOSURE_V1`, recorded
2026-10-28):

- the authenticated ingress (evidence v2) also takes source-neutral trades and index prices into the registered
  LAST_TRADE and INDEX_PRICE series with their unchanged registry 1.0 semantics (no sequence policy, so no continuity
  is ever inferred). A trade is identified by its native trade id; a capture may DECLARE the `contiguous_trade_id.v1`
  profile, under which ids and event times never regress, a native gap opens a new contiguous run and every record
  names its run. An index price is identified by its native event time; a capture may DECLARE the
  `index_one_per_utc_second.v1` profile (at most one value per UTC second). Conflicts reject, identical redeliveries are
  idempotent, and nothing is visible before its receipt. A capture without those streams keeps its v1 evidence and
  dataset byte-identical;
- an OHLC source may DECLARE its bar origin (archive schema v2): `exchange_kline` (the exchange's own kline feed) or
  `trade_derived`. A source of undeclared origin keeps its v1 payload and digest, and is never an exchange kline feed;
- entry gate rule set v4 measures, on the archive's own series at the decision instant: NT-D01 (the largest observed
  trade gap strictly above 60 s, or 1-minute exchange-kline gap strictly above 5 minutes, over the span from the open of
  the latest completed UTC 5-minute window; a PASS needs both feeds observed back to that open and one contiguous run of
  the declared trade profile), NT-D03 (|latest trade event time - latest L2 event time| strictly above 5 s), NT-D04
  (|latest trade price - index| / index strictly above 2%, only while the trade is within the 60 s trade bound and the
  index inside its declared UTC second; no index freshness bound is invented) and NT-D05 (the latest completed UTC
  5-minute base-asset volume strictly below 5% of the mean of the 8640 completed windows before it, only when one
  contiguous declared run proves every window covered and the mean is positive). Every unproven reading is BLOCKED with
  its reason, never a PASS and never a substitute series; day seal v5 and lineage evidence v5 bind it for a portfolio
  lineage that opts in from day 0, and every v1-v4 artifact, schedule and rule set is byte-identical;
- the accepted synthetic governed worlds declare no trade or index series in their genesis data contract, so each
  reading there is BLOCKED with exactly that reason and every S1 entry is still refused first by NT-D01; a measured
  PASS of the whole Data family is proven on authentic synthetic captures and still stops at NT-R01. M1 source
  qualification, D1 venue facts, source rights and C1-C9 stay open, a declared capture profile is documented, never
  qualified, and REAL_PAPER_EXECUTION stays BLOCKED. Every value in the tests is synthetic.

Proven kill-switch escalation (`S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1`, recorded 2026-10-30):

- a market-data lineage that opts in from day 0 (day seal v6, lineage evidence v6) evaluates entry gate rule set v5. Each
  sequential-admission round derives the proven LOWER BOUND of the PRDV4 §1.19 level (`governed_paper_kill_switch.py`)
  from the decision portfolio and the governed outcome of one engine re-run (one read-only engine API returns both), the
  archive's final funding series and the governed latency. Only triggers proven TRUE are read: T1 intraday drawdown (the
  NT-R02 intraday base), T2 and T11 drawdown from the running peak since G, T5 five closed trades known losing (gross and
  net strictly negative, every settled funding record visible), T6 four consecutive final rates strictly beyond 0.1% on
  an approved 8 h grid, and T7 the governed latency strictly above 10 x the T1 budget for more than 60 s. T4 is not
  applicable on the one-sleeve portfolio. T3 (CVaR), T8 (liquidity), T9 (exchange-API health), T10 (no authenticated
  BTC identity), T12 (no defined critical-feed membership), KS-4 and the §1.26 DTL input are never read TRUE or FALSE;
- the bound is the level of the triggers proven at each instant, and KS-3 from the instant it is proven (absorbing: no
  governed recovery approval exists). No persistence below KS-3 is claimed, because §1.19's cool-down reads from the
  clearing or from the level's entry and the two disagree after an earlier unproven entry. NT-R01 FAILs exactly on a
  proven KS-2 or more and is otherwise BLOCKED, naming every unproven trigger; it never passes. NT-T02 stays BLOCKED, and
  no cool-down is claimed or denied. A refusal still reaches entries only, never a protective close-only exit;
- the seal binds the ladder digest and its run-independent prefix before `E_k` and `E_k+1`, and the prefix before `E_k`
  must equal the previous seal's (X1 for the ladder). Every v1-v5 artifact, rule sets v1-v4 and every accepted economic
  outcome stay byte-identical;
- every S1 entry is still refused (first by NT-D01 on the accepted worlds, by NT-R01 after a Data PASS). A PASS-capable
  NT-R01 stays blocked on H1-H6: an exchange-API health reading on the paper path, the CVaR and liquidity
  methodologies, the margin and DTL model, the KS-1 actions and the KS-2/KS-3 position mechanics. REAL_PAPER_EXECUTION
  stays BLOCKED. Every value in the tests is synthetic.
