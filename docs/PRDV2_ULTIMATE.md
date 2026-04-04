# BIST_ELITE_CORE — PRD V2 ULTIMATE
Institutional Trading Intelligence Architecture

This document defines the ultimate architecture constitution for the BIST_ELITE_CORE project.

All AI agents and developers must treat this file as the primary architectural source of truth.

Every development prompt must begin with:

Follow docs/PRDV2_ULTIMATE.md as the architecture constitution.

---

# 1. SYSTEM PURPOSE

BIST_ELITE_CORE is designed to become the most advanced **BIST-only trading intelligence platform**.

The system is not only a trading bot.

It is a **quant research lab + trading advisor system**.

Primary capabilities:

• market scanning  
• strategy discovery  
• strategy evaluation  
• signal ranking  
• explainable trade reasoning  
• paper trading simulation  
• continuous learning  

Human traders may manually execute generated strategies.

---

# 2. DESIGN PHILOSOPHY

The system follows these core principles:

### Determinism
Same input must always produce the same output.

### Fail-Closed
Invalid or ambiguous data must result in **NO TRADE**.

### Explainability
Every decision must include reasoning.

### Test-Sealed Development
All modules must include deterministic tests.

### Auditability
All decisions, trades, and events must be recorded.

---

# 3. TRADING SCOPE

Market:

Borsa Istanbul Equity Market

Universe:

All BIST listed equities.

Filtering applied based on:

• liquidity  
• spread  
• volatility  
• trading restrictions  
• corporate events  

---

# 4. TRADING TIMEFRAME STRUCTURE

Primary trading horizon:

Short-term trading.

Main timeframes:

5m  
15m

Context timeframes:

1h  
1d

Structural timeframe:

1w

The system remains **multi-horizon capable**.

---

# 5. STRATEGY MODEL

Unlimited strategy pool.

Active strategy set:

Top 5 strategies selected dynamically.

Selection criteria:

• recent performance  
• alpha stability  
• regime compatibility  

Strategies are continuously evaluated.

Poor performers are replaced.

---

# 6. RISK MODEL

Default risk per trade:

1.5%

Daily loss limit:

5%

Max simultaneous positions:

10

Target active positions:

5

Risk rules must be enforced at all times.

---

# 7. DATA SOURCES

Primary vendor:

Matriks API

Additional sources:

• KAP announcements
• sector classification
• market breadth metrics

All data must pass validation before use.

---

# 8. ARCHITECTURE OVERVIEW

The architecture consists of **45 logical layers**.

These layers represent the full institutional architecture.

Implementation may occur in phases.

---

# 9. CORE LAYER ARCHITECTURE

## 1 Data Ingestion Layer
Vendor adapters, OHLCV ingestion.

## 2 Symbol Registry
Symbol metadata, delist handling.

## 3 Market Session Engine
Session phases and tradability.

## 4 Data Quality Layer
Missing data detection.

## 5 Feature Engine
Technical feature computation.

## 6 Feature Store
Cached feature storage.

## 7 Indicator Library
Deterministic indicator implementations.

## 8 Factor Engine
Risk factor calculation.

## 9 Factor Research Engine
Factor discovery and testing.

## 10 Signal Engine
Feature → signal conversion.

## 11 Strategy Engine
Strategy definitions and logic.

## 12 Strategy Registry
Strategy metadata storage.

## 13 Short-Term Specialization Layer
Microstructure aware rules.

## 14 Market Regime Engine
Market condition classification.

## 15 Adaptive Scan Engine
Universe scanning.

## 16 Multi-Symbol Ranking Engine
Opportunity ranking.

## 17 Comparison Engine
Symbol vs symbol rationale.

## 18 Liquidity Engine
Liquidity scoring.

## 19 Microstructure Engine
Tick/auction modeling.

## 20 Execution Intelligence
Order decision logic.

## 21 Broker Adapter Layer
Broker API integration.

## 22 Order State Machine
Order lifecycle management.

## 23 Paper Trading Engine
Execution simulation.

## 24 Portfolio Intelligence
Portfolio level analysis.

## 25 Position Management
Position tracking.

## 26 Capital Allocation Engine
Position sizing logic.

## 27 Risk Engine
Trade validation.

## 28 Strategy Performance Monitor
Strategy metrics tracking.

## 29 Alpha Decay Monitor
Strategy degradation detection.

## 30 Strategy Discovery Engine
Strategy generation.

## 31 Strategy Optimization Engine
Parameter search.

## 32 Learning Engine
Meta-learning logic.

## 33 Experiment Tracking
Research artifact storage.

## 34 Model Governance
Model approval workflow.

## 35 Event Intelligence
KAP/news events.

## 36 Sector Rotation Engine
Sector based signals.

## 37 Market Breadth Engine
Market wide indicators.

## 38 Correlation Engine
Cross-symbol correlation.

## 39 Explainability Engine
Human readable reasoning.

## 40 Teaching Engine
Trade explanation logic.

## 41 Monitoring Layer
System health metrics.

## 42 Alert Engine
Alert triggers.

## 43 Audit Logger
Append-only decision logs.

## 44 Infrastructure Layer
CI/CD and deployment.

## 45 Research Sandbox
Experimental research environment.

---

# 10. DECISION OBJECT CONTRACT

All signals must return a structured decision object.

Fields:

symbol  
entry  
stop  
target  
side  
confidence  
score  
factors  
reasoning  
timestamp  

This structure must remain stable.

---

# 11. TESTING RULES

Every module must include:

• deterministic tests  
• invalid input tests  
• edge case tests  

Test runner:

pytest

CI must fail if tests fail.

---

# 12. CI PIPELINE

CI must run:

lint  
type checks  
unit tests  
integration tests  

Release requires green CI.

---

# 13. LEARNING MODEL

The system continuously evaluates strategies.

Tracked metrics:

expectancy  
hit rate  
drawdown  
alpha decay  

Strategies may be replaced if performance degrades.

---

# 14. PAPER TRADING

Paper trading must simulate:

• fills  
• slippage  
• costs  

Weekly performance reports must be generated.

---

# 15. GOVERNANCE

Strategies must pass validation before activation.

Validation includes:

• walk-forward testing  
• stability checks  
• risk verification  

---

# 16. FINAL GOAL

Build the most advanced **BIST-only trading intelligence platform** capable of discovering, evaluating and explaining elite trading strategies.