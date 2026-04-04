# BIST_ELITE_CORE — PRD V2
Short-Term Alpha Research & Trading Intelligence Platform

This document is the architecture constitution for the BIST_ELITE_CORE repository.

All implementation decisions must follow this document.

Agents working in this repository must begin prompts with:

Follow docs/PRDV2.md as the architecture constitution.

---------------------------------------------------------------------

SYSTEM PURPOSE

The system is designed to become the most advanced BIST-only trading intelligence system.

Primary objective:

Discover, generate and continuously improve high-quality trading strategies for Borsa Istanbul.

The system produces:

• explainable trade plans
• ranked trading opportunities
• strategy discovery
• strategy evaluation
• paper trading simulations

Human traders may manually execute strategies produced by the system.

---------------------------------------------------------------------

PRIMARY TRADING FOCUS

Short-term trading.

Primary timeframe:

5m
15m

Context timeframe:

1h
1d

Structural timeframe:

1w

The system must remain multi-horizon capable.

---------------------------------------------------------------------

UNIVERSE

All BIST equities are monitored.

Tradeability filtering applies based on:

• liquidity
• spread
• volatility
• trading restrictions
• event filters

---------------------------------------------------------------------

STRATEGY MODEL

Unlimited strategy pool.

Active strategy set:

Top 5 strategies selected dynamically.

Selection criteria:

• recent performance
• regime compatibility
• alpha stability

---------------------------------------------------------------------

RISK MODEL

Default risk per trade:

1.5%

Daily loss limit:

5%

Max simultaneous positions:

10

Target active positions:

5

---------------------------------------------------------------------

DATA SOURCES

Primary vendor:

Matriks API

Additional sources:

KAP announcements
sector classification
market breadth metrics

---------------------------------------------------------------------

ARCHITECTURE LAYERS (30)

1 Data Layer
2 Symbol Registry
3 Market Session Engine
4 Data Quality Layer
5 Feature Engine
6 Feature Store
7 Factor Engine
8 Factor Research
9 Signal Engine
10 Strategy Engine
11 Short-Term Specialization Layer
12 Market Regime Engine
13 Adaptive Scan Engine
14 Multi Symbol Ranking Engine
15 Liquidity Engine
16 Microstructure Engine
17 Execution Intelligence
18 Broker Adapter Layer
19 Paper Trading Engine
20 Portfolio Intelligence
21 Position Management
22 Strategy Performance Monitor
23 Alpha Decay Monitor
24 Strategy Discovery Engine
25 Learning Engine
26 Experiment Tracking
27 Event Intelligence
28 Market Breadth Engine
29 Explainability Engine
30 Infrastructure Layer

---------------------------------------------------------------------

CORE DESIGN PRINCIPLES

Deterministic outputs

Same input must produce same output.

Fail-closed behavior

Invalid data must not produce trades.

Explainability

Every trade must include reasoning.

Test-sealed architecture

Every module must have tests.

Auditability

All decisions logged via append-only logs.

---------------------------------------------------------------------

DECISION OBJECT

Every signal must produce the following structure:

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

---------------------------------------------------------------------

LEARNING MODEL

System evaluates strategies daily.

Metrics tracked:

• expectancy
• hit rate
• drawdown
• alpha decay

Strategies may be replaced automatically after validation.

---------------------------------------------------------------------

EXECUTION MODEL

PRD V2 supports:

Advisor
Paper trading

Real trading execution remains optional.

---------------------------------------------------------------------

CI RULES

Every module must include tests.

pytest must pass before merge.

CI pipeline must include:

lint
tests
build

---------------------------------------------------------------------

FINAL GOAL

Create the most advanced BIST-only trading intelligence platform capable of discovering and refining elite trading strategies.

---------------------------------------------------------------------