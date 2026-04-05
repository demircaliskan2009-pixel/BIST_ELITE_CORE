---
name: edge-discovery-validation
description: 'Use when discovering, researching, formalizing, coding, or validating a BIST trading edge. Starts from a hypothesis, uses only primary or authoritative evidence, converts the hypothesis into deterministic strategy code, validates with costs, slippage, walk-forward and regime checks, rejects overfit or unstable edges, preserves BIST-only scope, and never bypasses risk, execution, or validation gates.'
argument-hint: 'Describe the edge hypothesis, BIST scope, available evidence, target strategy files, and required validation depth.'
user-invocable: true
---

# Edge Discovery + Validation

This skill converts a BIST trading hypothesis into deterministic code only if the edge survives evidence and validation.

## Use This Skill When
- Exploring a new BIST trading edge.
- Translating a market hypothesis into deterministic strategy logic.
- Validating whether an existing edge is robust or overfit.
- Hardening backtest, walk-forward, or regime validation around a strategy.

## Non-Negotiable Rules
- Start from an explicit hypothesis.
- Research only with primary or authoritative evidence.
- Keep the scope BIST-only unless the user explicitly changes it.
- Convert accepted hypotheses into deterministic, inspectable strategy code.
- Validate with transaction costs, slippage, walk-forward, and regime checks.
- Reject overfit, unstable, or non-reproducible edges.
- Never bypass risk, execution, or validation gates.
- Never allow presentation logic or agents to generate signal logic.

## Standard Procedure
1. State the edge hypothesis.
2. Collect only authoritative supporting evidence.
3. Define deterministic rules, features, and thresholds.
4. Implement the smallest strategy change needed.
5. Validate with backtest realism: costs, slippage, walk-forward, and regime segmentation.
6. Reject the edge if results are unstable, regime-fragile, or obviously overfit.
7. Keep accepted logic behind existing risk and execution gates.

## Required Output
1. Hypothesis tested.
2. Evidence accepted or rejected.
3. Deterministic rule set.
4. Validation method.
5. Acceptance or rejection decision.
6. Residual risk.

## Completion Criteria
- The hypothesis is either rejected with evidence or implemented as deterministic code.
- Validation includes costs, slippage, walk-forward, and regime checks.
- The result remains inside BIST scope and respects downstream gates.
