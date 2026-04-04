# PRDV3 Compliance Matrix

**Authority:** `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md`  
**Purpose:** Map PRDV3 requirements to implementation artifacts and tests.  
**Statuses:** **complete** | **partial** | **missing**

---

## Core invariants (§2–4, §27)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Deterministic core paths | **complete** | `ExecutionEngine.try_fill` (hash-based, no RNG); tests `tests/test_execution_acceptance.py` |
| Fail-closed on bad/missing data | **complete** | `DataValidator`, `live_runner` strict paths; `tests/live/test_data_validator.py`, `tests/module/test_data_hardening.py` |
| No RNG in signals/execution core | **complete** | `bist_core/live/execution_engine.py`; `tests/test_execution_acceptance.py` |
| Audit / structured emission | **partial** | `live_runner._emit_validation_block`, JSON lines; full JSONL trade audit varies by path |
| BIST-only scope | **complete** | Registry/universe loaders; no non-BIST in core paths |

---

## Data hierarchy & timeframe (§6–7)

| Requirement | Status | Evidence |
|------------|--------|----------|
| iDeal-first, binary-as-binary | **complete** | `vendors`/ideal parsers, `tests/vendors/test_ideal_g_parser.py`, `tests/module/test_ideal_01_parser.py` |
| Timeframe-aware reads | **complete** | `IdealDataFeed`, `BIST_IDEAL_TIMEFRAME`; `tests/test_multi_timeframe_data.py` |
| Per-bar / deterministic normalization | **complete** | `normalize_price` in `data_feed.py`; `tests/test_normalization_determinism.py` |
| Fail-closed parse/validation | **complete** | `DataValidator`, `DataHardeningEngine`; module tests |

---

## Brain, edge, ranking, portfolio (§8–12, §15)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Explainable multi-factor scoring | **complete** | `DecisionEngineV2`, `institutional_brain`, feature extractors; `tests/module/test_decision_engine_v2.py`, `tests/module/test_institutional_brain.py` |
| Edge scoring | **complete** | `edge/live_edge_engine.py`, `brain/edge_engine.py`; `tests/test_edge_engine.py`, `tests/module/test_live_edge_engine.py` |
| Ranking by score/edge | **complete** | `brain/ranking_engine.rank_symbols`; `tests/test_portfolio_acceptance.py`, `tests/test_ranking_engine.py` |
| Portfolio limits & ordering | **complete** | `live/portfolio_engine.build_portfolio_payload`; `tests/test_portfolio_acceptance.py`, `tests/module/test_portfolio_engine.py` |
| Action diversity / confidence spread (adaptive) | **partial** | `adaptive_live_controller.py`; `tests/module/test_adaptive_live_controller.py` |

---

## Risk (§13, §19)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Drawdown / pause / kill-switch | **complete** | `live/risk_engine.py` `build_snapshot`; `tests/test_risk_engine.py`, `tests/module/test_risk_engine_module.py` |
| Operational risk FSM (§19 transitions / audit) | **partial** | `live/risk_operational_fsm.py`, `BOOT→…` + `RiskEngine` persistence; full lifecycle audit vs PRDV3 §19 scope **partial** |
| Position / exposure limits | **complete** | `PaperExecution.configure_risk`, portfolio caps; live tests |
| Sector / correlation (PRDV3 depth) | **partial** | `risk/correlation_engine.py`, `sector_mapper.py` — integrated where wired |

---

## Execution (§14)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Deterministic fills + slippage | **complete** | `live/execution_engine.py`, `execution_runtime.py`, realism metrics; `tests/test_execution_acceptance.py`, `tests/module/test_market_realism_metrics.py` |
| Order states / lifecycle (full broker) | **partial** | `execution/order.py`, paper path; not full exchange FSM in paper loop |

---

## Validation & walk-forward (§16)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Train/test split, no leakage | **complete** | `validation/walkforward.walkforward_split`; `tests/test_walkforward.py` |
| Multi-window walk-forward engine | **complete** | `validation/walk_forward.WalkForwardValidator`; `tests/module/test_walk_forward.py` |
| Backtest cost-aware | **complete** | `backtest/backtest_engine.py`; `tests/module/test_backtest.py` |
| Promotion / acceptance gate | **partial** | `validation/validator.py`, `optimizer`; `tools/prdv3_final_acceptance.py` (full E2E with iDeal) |

---

## AI agents (§10, §22)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Optional; core works without agents | **complete** | No agent in decision path; constitution tests |
| JSON-serializable contracts | **partial** | Decision/portfolio payloads; agent modules if present are side paths |

---

## Operating modes (§18)

| Requirement | Status | Evidence |
|------------|--------|----------|
| Advisory / semi / full hooks | **partial** | CLI/advisor services; live runner executes paper — broker live behind config |

---

## Final acceptance (PRDV3 chain)

| Gate | Status | Evidence |
|------|--------|----------|
| Automated constitution smoke | **complete** | `tests/test_prdv3_constitution_smoke.py` |
| PRDV3 pytest bundle | **complete** | `.\proof_pack.ps1 -Mode prdv3` |
| Full repo proof | **complete** | `.\proof_pack.ps1 -Mode baseline` |
| E2E acceptance (requires local `BIST_IDEAL_DATA_PATH`) | **partial** | `python tools/prdv3_final_acceptance.py` — integrity gate only; **does not** mutate realism/portfolio env (see `docs/PRDV3_HONEST_STATUS.md`) |

---

**Honest completion:** Proof harness pass ≠ PRDV3 product completion. See **`docs/PRDV3_HONEST_STATUS.md`**.

*This matrix is maintained with code changes; ambiguous “product” items (e.g. Turkish-first UX defaults) are tracked as partial until explicitly implemented.*
