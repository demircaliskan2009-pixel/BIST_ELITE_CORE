# BIST_ELITE_CORE — PRDV3 FINAL GOD ARCHITECTURE
## Profit-Seeking, Risk-Bounded, Adaptive, Explainable, AI-Agent-Ready BIST-Only Trading OS

**Document purpose:** This is the final architecture constitution for the PRDV3 phase of BIST_ELITE_CORE.  
**Scope:** Borsa İstanbul only. No foreign markets, no multi-asset expansion in the core product.  
**Inheritance:** PRDV3 strictly extends PRDV2. PRDV2 deterministic / fail-closed / test-sealed / audit-first principles remain immutable.

Every implementation prompt, refactor, integration patch, or AI-agent instruction that touches this system must respect this document.

If a future prompt is generated for this repository, it must begin with:

> Follow `docs/PRDV3_FINAL_GOD_ARCHITECTURE.md` as the architecture constitution.

---

# 1. FINAL PRODUCT DEFINITION

The final product is a **BIST-only adaptive trading operating system** that:

1. scans the full BIST universe,
2. detects market regime,
3. ranks opportunities,
4. sizes risk dynamically,
5. executes trades through a deterministic execution model,
6. explains every decision in human-readable language,
7. learns from prior outcomes,
8. supports both semi-automatic and full-automatic operation,
9. is **AI-agent-ready** but does not require agents to function,
10. prioritizes **net profitability, capital preservation, and controllable drawdown** over raw trade count.

The product must behave like a disciplined trading system, not a chatty signal generator.

---

# 2. NON-NEGOTIABLE DESIGN GOALS

The system MUST:

- maximize expected net profit over time,
- minimize avoidable loss,
- remain deterministic in core execution paths,
- be explainable to a human user,
- fail closed when data is missing or inconsistent,
- adapt to market regime,
- learn from historical outcomes,
- remain BIST-only,
- support manual, semi-automatic, and full-automatic modes,
- expose machine-readable audit logs,
- expose human-readable rationale,
- be safe to disable, pause, or de-risk,
- be ready for optional AI-agent augmentation.

The system MUST NOT:

- trade on undefined behavior,
- hide decisions behind opaque templates,
- silently fill missing data with invented defaults,
- require randomization in core trading logic,
- bypass risk controls for the sake of activity,
- become a black box without auditability,
- open trades purely to satisfy arbitrary quotas,
- ignore BIST-specific structural realities.

---

# 3. FINAL PRODUCT CHARACTER

The final product is:

- **profit-seeking**
- **risk-bounded**
- **adaptive**
- **explainable**
- **regime-aware**
- **hybrid timeframe**
- **AI-agent-ready**
- **manual/semi-auto/full-auto compatible**
- **BIST-specific**
- **deterministic at the core**
- **learning at the edges, not the heart**

The core personality of the bot is:

> “Earn aggressively when edge is real; preserve capital when edge is weak; explain every choice.”

---

# 4. PRDV2 INHERITANCE

PRDV2 is the immutable substrate. PRDV3 does **not** replace PRDV2; it sits on top of it.

PRDV2 substrate requirements remain mandatory:

- deterministic behavior,
- fail-closed logic,
- test-sealed modules,
- audit logging,
- stateful portfolio management,
- stateful execution engine,
- validation pipeline,
- data hierarchy and freshness controls,
- current price awareness,
- explainable scoring,
- paper/live simulation safety.

Any PRDV3 feature that weakens PRDV2 correctness is invalid.

---

# 5. TRADING UNIVERSE

## 5.1 Universe
Core universe is BIST equities only.

## 5.2 Universe coverage
The system scans the full eligible BIST equity universe, subject to:
- data availability,
- liquidity,
- trading halts / suspensions,
- corporate actions,
- session validity,
- spread / slippage feasibility,
- risk concentration rules.

## 5.3 Candidate hierarchy
The scanner should support:
- broad scan pool (all eligible BIST symbols),
- review pool (top 10–20 by score / opportunity),
- execution pool (top 3–8 executable candidates depending on regime and risk budget).

Trade count is secondary to net expectancy.

---

# 6. DATA HIERARCHY

The data layer must preserve this priority order:

1. **iDeal `.G`** for historical truth,
2. **iDeal `.05`** for live/intraday last price where available,
3. **Matriks** as a fallback / alternate historical or market source,
4. **CSV fallback** only when needed for fail-closed continuity.

## 6.1 Data principles
- No fabricated prices.
- No silent fallback that masks source failure.
- No use of stale or future-dated bars.
- No use of data without freshness validation.
- Binary formats must be parsed as binary, not assumed to be text.
- Every data source must be auditable.

## 6.2 Market reality constraints
The system must respect:
- session hours,
- off-session inactivity,
- tavan/taban behavior,
- liquidity constraints,
- regime-specific spread / slippage,
- corporate action adjustments,
- symbol normalization and mapping.

---

# 7. TIMEFRAME MODEL

The final product is **hybrid**.

## 7.1 Recommended structure
- **Swing-dominant core** (primary)
- **Intraday opportunistic layer** (secondary)
- **Daily structural layer** (context / trend / regime)

Recommended default weighting:

- 70% swing / daily structure
- 30% intraday timing and opportunity capture

## 7.2 Holding logic
A trade can be held:
- until stop,
- until target,
- until regime invalidation,
- until maximum holding time is reached.

Default style:
- intraday trades: same-day / session-based
- swing trades: multi-day, typically up to 5–10 sessions unless logic exits earlier

The system must not hold indefinitely by default.

---

# 8. EDGE DEFINITION

The system must become an **edge-discovery engine**, not a static rule toy.

## 8.1 Initial edge families
The system may begin with multi-factor families such as:
- momentum continuation,
- trend-following,
- pullback in trend,
- volatility expansion,
- controlled mean reversion,
- breakout continuation.

## 8.2 Learning objective
The system must learn:
- which edge works in which regime,
- which symbols / sectors respond best,
- which feature combinations produce positive expectancy,
- which edges decay.

## 8.3 Edge policy
The core bot should:
- test multiple edge hypotheses,
- rank them by realized performance,
- allocate capital toward the best performing edge under the current regime,
- de-emphasize losing edge families.

The system must not assume one universal edge works in all regimes.

---

# 9. LEARNING ARCHITECTURE

Learning is mandatory, but learning must be controlled.

## 9.1 Learning layers
The system should support:
- **feature weight adaptation**
- **regime-conditioned parameter tuning**
- **strategy family selection**
- **edge decay detection**
- **performance attribution**
- **nightly / periodic retraining**
- **walk-forward validation gating**

## 9.2 Safe learning rule
Core live decision logic must remain deterministic and fail-closed.  
Learning may update:
- feature weights,
- thresholds,
- ranking preferences,
- strategy allocation,
- candidate gating heuristics,

but only after validation.

## 9.3 Learning cadence
Preferred:
- daily or nightly update,
- weekly deeper analysis,
- walk-forward promotion gate,
- no uncontrolled online black-box drift.

## 9.4 Model governance
Any learned change must be:
- backtested,
- walk-forward tested,
- paper-tested,
- audit logged,
- promotable only if metrics improve.

---

# 10. AI AGENT ARCHITECTURE

AI agents are **optional capability amplifiers**, not the core execution brain.

## 10.1 Default stance
Core trading must work **without any AI agents**.

## 10.2 Agent roles
Agents may be added later as modular assistants:
- Research Agent
- Diagnostic Agent
- Feature Hypothesis Agent
- Optimization Agent
- Strategy Reviewer
- Explainability Agent
- Regime Analyst
- Anomaly Detector

## 10.3 Agent allowed duties
Agents may:
- analyze logs,
- summarize trade behavior,
- propose new hypotheses,
- suggest parameter changes,
- explain edge behavior,
- detect anomalies,
- support research.

## 10.4 Agent prohibited duties
Agents must not:
- bypass risk controls,
- directly submit live orders without the execution stack’s approval path,
- silently mutate the live system,
- replace the deterministic risk / execution core,
- act as an uncontrolled black box.

## 10.5 Agent-ready protocol
The system must expose clean JSON-serializable contracts so agents can be plugged in later.

Agent input may include:
- symbol,
- current regime,
- feature vector,
- score vector,
- current price,
- stop/target context,
- portfolio state,
- risk budget,
- candidate rank.

Agent output may include:
- recommendation,
- rationale,
- confidence,
- suggested adjustments,
- anomaly flags,
- alternative scenarios.

## 10.6 Agent operating modes
- **Off**
- **Advisory**
- **Decision-Enhancing**
- **Research-Only**
- **Full Agent Mode** only if validated and explicitly enabled

## 10.7 AI cost control
Agent use must be optional because:
- token cost matters,
- latency matters,
- deterministic continuity matters.

---

# 11. SIGNAL / SCORING DESIGN

## 11.1 Signal model
Scoring must remain explainable and multi-factor.

Typical ingredients:
- momentum,
- trend,
- volatility,
- RSI / overbought-oversold context,
- distance to stop,
- distance to target,
- regime compatibility,
- correlation penalty,
- liquidity penalty,
- current price awareness.

## 11.2 Threshold policy
There should be no static threshold that permanently strangles the system.

Preferred:
- regime-aware threshold,
- confidence-aware threshold,
- dynamic threshold boundaries,
- penalty instead of hard rejection where appropriate.

## 11.3 Ranking policy
Always rank candidates by:
- score,
- confidence,
- risk/reward,
- regime alignment,
- correlation isolation,
- liquidity feasibility.

Ranking should not silently go empty when valid candidates exist.

## 11.4 Trade selection rule
The system should prefer:
- positive expected value,
- acceptable risk/reward,
- regime fit,
- low correlation concentration.

The system may remain idle only when no positive-EV candidate exists after full evaluation.

---

# 12. DECISION ENGINE

The decision engine is the behavioral layer between score and execution.

## 12.1 Required outputs
For every symbol, the decision engine must produce:
- action: enter / wait / skip
- confidence
- reason
- entry_status
- risk context
- price-awareness context

## 12.2 Price-awareness
The engine must know:
- whether entry has been missed,
- whether the market is too extended,
- whether pullback logic applies,
- whether current price is near intended entry.

## 12.3 Decision logic
Decisions must consider:
- momentum alignment,
- trend alignment,
- ATR / volatility,
- stop distance,
- target distance,
- current price relative to entry,
- regime state,
- portfolio state,
- concentration state.

## 12.4 Rationale
Rationale must be:
- data-driven,
- symbol-specific,
- non-template,
- understandable by a human,
- detailed enough for auditing.

Examples of good rationale:
- “EMA20 is above SMA50 by X%; momentum remains positive; ATR is moderate; risk/reward meets threshold.”
- “Price has moved beyond valid entry distance; pullback wait is more prudent than immediate entry.”

## 12.5 Multi-symbol comparison
The decision engine must compare symbols:
- stronger setup versus weaker setup,
- better risk/reward versus lower quality,
- lower correlation versus concentrated exposure,
- regime-aligned candidates versus regime-misaligned ones.

---

# 13. RISK MANAGEMENT

Risk management must protect capital while allowing growth.

## 13.1 Default risk bands
Risk sizing should be able to choose among:
- **0.5%** low risk,
- **1.0%** normal risk,
- **1.5%** medium risk,
- **2.0%** high risk.

These are the allowed practical bands for the final product.

## 13.2 Risk assignment policy
The bot itself should choose risk size according to:
- signal quality,
- confidence,
- regime,
- correlation load,
- portfolio capacity,
- daily drawdown state.

## 13.3 Hard risk constraints
Hard constraints must remain:
- max drawdown target,
- daily loss stop / de-risk threshold,
- max open positions,
- exposure limits,
- correlation limits,
- invalid price / stop / target rejection.

## 13.4 Drawdown policy
Recommended portfolio rules:
- soft de-risk around 10–12% drawdown,
- hard drawdown ceiling around 20%,
- pause / flatten behavior if the system is structurally degraded.

## 13.5 Position count
Default practical regime:
- 5–8 concurrent positions maximum,
- sector cluster concentration limited,
- same-sector overconcentration prohibited.

## 13.6 Correlation control
Highly correlated symbols should not collectively consume the entire risk budget.

Examples:
- multiple banks,
- multiple highly similar index-sensitive names,
- same-sector crowding.

## 13.7 Daily loss logic
The system should:
- keep operating if the edge is still valid,
- but reduce risk or pause when the risk budget is exhausted,
- never continue blindly through structurally adverse conditions.

---

# 14. EXECUTION ENGINE

Execution must remain deterministic and stateful.

## 14.1 Default execution behavior
- deterministic order state machine,
- explicit order state tracking,
- slippage model,
- commission/cost awareness,
- no randomness in fill logic.

## 14.2 Order lifecycle
Required states:
- CREATED
- SUBMITTED
- FILLED
- REJECTED
- CLOSED

## 14.3 Execution rules
- invalid orders are rejected,
- invalid prices are rejected,
- stop/target logic must be enforceable,
- session rules must be respected,
- fills must be auditable.

## 14.4 Order types
Primary default:
- market execution model with slippage

Future extensibility:
- limit,
- hybrid,
- partial fills,
- queue-based simulation,
- liquidity-aware execution.

## 14.5 Position lifecycle
Positions must support:
- open,
- hold,
- update,
- partial reduction,
- exit,
- forced close,
- state persistence across cycles.

---

# 15. PORTFOLIO INTELLIGENCE

The portfolio layer must manage:
- capital,
- open positions,
- daily realized PnL,
- daily loss used,
- trade history,
- concentration,
- exposure.

## 15.1 Capital behavior
Capital is the single source of truth for the portfolio.

## 15.2 Compounding
Compounding may be enabled, but only if the system remains validated and the operator chooses it.

## 15.3 Capital safety
The system must never:
- create negative capital without explicit accounting,
- hide losses,
- bypass portfolio constraints,
- silently reset state.

---

# 16. VALIDATION PIPELINE

Validation is mandatory and must remain central.

## 16.1 Backtest
Backtests must be:
- cost-aware,
- slippage-aware,
- commission-aware,
- deterministic,
- repeatable.

## 16.2 Walk-forward
Validation must include:
- train / test segmentation,
- no leakage,
- multiple windows,
- segment aggregation,
- regime-dependent review.

## 16.3 Performance metrics
Must include:
- total return,
- expectancy,
- win rate,
- profit factor,
- max drawdown,
- sharpe / risk-adjusted measure,
- trade count,
- segment-level metrics.

## 16.4 Acceptance gate
A strategy or configuration may only be promoted if it passes:
- deterministic regression,
- backtest acceptance,
- walk-forward acceptance,
- paper validation,
- portfolio safety checks.

## 16.5 Validation philosophy
The system must not be evaluated only by trade count.  
The true measure is **risk-adjusted net profitability**.

---

# 17. OUTPUT / UX

The system must show the user everything important in a way that is understandable.

## 17.1 Human-readable output
The user should see:
- symbol,
- entry,
- stop,
- target,
- time,
- action,
- rationale,
- edge family,
- confidence,
- risk allocation,
- trade result,
- pnl,
- current market regime,
- whether the entry was missed,
- whether the system waited or skipped,
- why that decision was made.

## 17.2 Machine-readable output
The system should also produce audit-friendly structured logs:
- JSONL trade records,
- risk events,
- decision events,
- validation events,
- learning events,
- regime events.

## 17.3 Turkish-first UX
Default explanation language should be Turkish for the user-facing layer, while preserving technical field names in logs if needed.

---

# 18. OPERATING MODES

The final product must support:

## 18.1 Advisory mode
- gives recommendations,
- does not execute orders.

## 18.2 Semi-automatic mode
- proposes trades,
- user confirms or rejects.

## 18.3 Full automatic mode
- applies its own decisions,
- executes via broker connection once enabled,
- still under risk and validation constraints.

The same core engine must support all three modes.

---

# 19. FAILURE / SAFETY STATE MACHINE

The bot must not be emotionally reactive; it must be stateful.

## States
- ACTIVE
- DE-RISK
- PAUSE
- RECOVER

## Transition logic
- Active → De-risk when drawdown rises or regime degrades.
- De-risk → Pause when evidence shows structural failure.
- Pause → Recover only after improvement / validation.
- Recover → Active only when metrics normalize.

The bot should not keep trading aggressively through a broken regime.

---

# 20. BIST-SPECIFIC RULES

The system must be BIST-aware.

## 20.1 Must handle
- session hours,
- off-session behavior,
- tavan / taban constraints,
- illiquid symbols,
- suspended symbols,
- corporate actions,
- adjusted / unadjusted data,
- symbol normalization,
- sector grouping.

## 20.2 Must avoid
- trading when data quality is unreliable,
- ignoring obvious market structure constraints,
- overexposure to a single correlated cluster,
- pretending BIST behaves like US markets.

---

# 21. LEARNING / ADAPTATION POLICY

The system should learn in a controlled way:

- from trade outcomes,
- from regime behavior,
- from feature attribution,
- from error analysis,
- from edge decay,
- from strategy comparison.

The learning layer may adapt:
- feature weights,
- threshold policy,
- candidate ranking bias,
- regime-specific allocations,
- strategy family emphasis.

The learning layer must never:
- silently override core safety rules,
- mutate execution logic without validation,
- bypass audit logs,
- violate PRDV2 fail-closed design.

---

# 22. AI AGENT FUTURE-PROOFING

The architecture must be “agent-ready”.

## 22.1 Agent integration principle
Agents are optional.  
The system must remain fully functional without them.

## 22.2 Agent extension points
Agents may attach to:
- research,
- diagnostics,
- explanation,
- optimization,
- anomaly detection,
- simulation analysis,
- strategy proposal.

## 22.3 Agent safety
Agents must not:
- directly bypass risk/execution,
- introduce non-deterministic control into the core,
- obscure decision traces,
- create hidden dependencies.

## 22.4 Agent protocols
Agent interfaces should be:
- JSON serializable,
- auditable,
- versioned,
- disable-able,
- testable.

---

# 23. LOGGING, AUDIT, AND GOVERNANCE

Every important action must be logged.

Log:
- raw data source state,
- model inputs,
- scores,
- decision outputs,
- execution events,
- portfolio changes,
- risk rejections,
- fallback usage,
- learning updates,
- validation results.

Logs must support:
- post-trade analysis,
- debug,
- audit,
- performance review,
- productization.

---

# 24. IMPLEMENTATION SEQUENCE

The implementation order for future development should be:

1. data integrity,
2. feature integrity,
3. scoring / ranking,
4. decision engine,
5. risk engine,
6. execution engine,
7. portfolio persistence,
8. validation,
9. learning loop,
10. AI-agent connectors,
11. product UX and reporting.

---

# 25. DEFAULT FINAL CONFIGURATION

Unless later validated changes prove better, PRDV3 defaults should be:

- BIST-only
- hybrid swing-dominant
- adaptive regime-aware ranking
- dynamic risk bands: 0.5 / 1.0 / 1.5 / 2.0
- max drawdown soft around 10–12%
- hard drawdown ceiling around 20%
- open positions default 5–8
- same-sector concentration max 2
- top 3–8 executable ideas in active regimes
- no fixed daily trade quota
- no forced losing trades
- explainable outputs always on
- AI agents optional and modular
- core engine deterministic and fail-closed

---

# 26. FINAL ACCEPTANCE CRITERIA

PRDV3 Final is acceptable only if the system:

- is BIST-only,
- scans the universe,
- ranks candidates,
- adapts to regime,
- manages risk dynamically,
- executes deterministically,
- explains every decision,
- logs everything,
- supports manual and automatic modes,
- supports AI-agent attachment later,
- validates improvements before promotion,
- remains profitable or de-risks when not profitable.

The system’s mission is:

> **Maximize net profit, preserve capital, learn from outcomes, and remain explainable and controllable.**

---

# 27. CURSOR CONSTITUTION (FOR REPOSITORY RULES)

Use the following as the core repository behavior rules:

- follow PRDV3 Final as the top-level constitution,
- do not weaken PRDV2 invariants,
- no hidden shortcuts,
- no silent defaults for missing data,
- no direct execution bypassing risk/execution state,
- no black-box learning in the live core,
- always preserve auditability,
- always preserve BIST-only scope,
- always preserve explainability,
- always preserve deterministic behavior where safety matters,
- always validate before promotion,
- always favor capital preservation over fragile activity.

---

# 28. SHORT VERSION FOR OPERATORS

If you need the one-line summary of this document:

> Build a BIST-only, hybrid, adaptive, explainable, learning-capable, AI-agent-ready trading OS that seeks net profit, controls drawdown, and only acts when the edge is real.

