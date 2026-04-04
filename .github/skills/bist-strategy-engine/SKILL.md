---
name: bist-strategy-engine
description: 'Handle PRDV3 BIST strategy-engine tasks: deterministic feature engineering, ranking, scoring, regime detection, and controlled signal generation from normalized validated BIST data. Use when building or reviewing explainable features, stable rankings, regime logic, or rule-defined signals that must avoid leakage, black-box logic, and unvalidated inputs.'
argument-hint: 'Describe the normalized BIST dataset, target symbols or universe, timeframe, required features or scores, regime objective, signal rules, and validation scope.'
user-invocable: true
---

# BIST Strategy Engine

This skill transforms clean, validated BIST data into deterministic features, rankings, regime labels, and controlled signals for PRDV3.

## Shared Contract
- Contract reference: [../_shared/references/contract-schema.md](../_shared/references/contract-schema.md)
- All outputs from this skill must comply with the shared PRDV3 contract.
- This skill may run only on a contract-compliant upstream data-stage result.

## Use This Skill When
- Engineering technical or statistical features from normalized OHLCV data.
- Ranking or scoring BIST assets using defined, inspectable criteria.
- Detecting market regimes with data-driven, interpretable logic.
- Generating signals only after feature and rule definitions are explicit.
- Reviewing strategy logic for leakage, instability, or unverifiable heuristics.

## Do Not Use This Skill When
- The input data is raw, partially parsed, unnormalized, or unvalidated.
- The task requires non-BIST market logic unless explicitly requested.
- The scoring or signal logic depends on undocumented heuristics or black-box behavior.
- The task expects randomization, implicit tuning, or unexplained signal generation.

## Non-Negotiable Rules
- Operate strictly on normalized, validated BIST data.
- Never use unvalidated data.
- Keep all feature, ranking, scoring, regime, and signal logic deterministic and reproducible.
- Never generate random or heuristic signals without evidence and explicit rules.
- Prevent look-ahead bias and data leakage in all feature and label logic.
- Maintain stable ordering for ranking results under identical inputs.
- Keep outputs explainable, inspectable, and testable.
- Do not use LLM-generated decision logic for trading behavior.

## Upstream Dependency
- Treat [../bist-data-pipeline/SKILL.md](../bist-data-pipeline/SKILL.md) as the trusted upstream gate for data admission.
- If the upstream data-stage output does not comply with the shared contract, stop and request validated normalized input first.

## Working Mindset
- Use pandas-style transformations for deterministic feature pipelines.
- Use DataFrame inspection logic to verify shapes, null behavior, joins, and ordering at each stage.
- Produce Ruff-compatible Python when code is written.
- Preserve Black and isort compatible formatting implicitly.
- Favor minimal, reviewable diffs and directly testable logic.

## Strategy Pipeline Stages
1. Input gate.
2. Feature specification.
3. Feature computation.
4. Feature validation.
5. Ranking and scoring.
6. Regime detection.
7. Signal eligibility check.
8. Controlled signal generation.

## Standard Procedure
1. Confirm input eligibility.
Verify the data is normalized, validated, and in scope for the BIST universe and timeframe requested.

2. Define the exact objective.
State what must be produced: features, ranking, score, regime labels, signals, or a combination.

3. Define features before computing them.
List each feature, formula, lookback, required columns, alignment rule, and leakage guard.

4. Compute features deterministically.
Use explicit transformations only. Keep ordering, grouping, windowing, and missing-data behavior visible.

5. Validate features.
Check null behavior, edge windows, lookback alignment, leakage risk, scale anomalies, and reproducibility.

6. Rank and score explicitly.
Document the ranking criteria, tie-break logic, sorting direction, weighting, and normalization rules.

7. Detect regimes with interpretable logic.
Use data-driven but explainable thresholds, states, or classifiers. Avoid opaque logic and overfitting-oriented complexity.

8. Gate signal generation.
Generate signals only if the full decision rule is explicit, deterministic, and supported by the validated features and regime state.

9. Produce inspectable outputs.
Return feature tables, ranking outputs, regime outputs, and signals in structured, testable form.

## Feature Engineering Checklist
- Inputs are validated normalized OHLCV or other explicitly approved canonical fields.
- Windows and lags are aligned without look-ahead leakage.
- Missing data treatment is explicit.
- Cross-sectional features preserve symbol identity and timestamp consistency.
- Transformations are deterministic and reproducible.
- Output columns are named clearly and remain inspectable.

## Ranking And Scoring Checklist
- Ranking criteria are explicit and evidenced.
- Score components are explainable and reproducible.
- Weighting and normalization rules are documented.
- Tie-breaking is deterministic.
- Ordering remains stable for identical inputs.
- Output includes enough detail to audit why one asset outranks another.

## Regime Detection Checklist
- Regime logic is interpretable and data-driven.
- State transitions are explicit.
- Inputs and thresholds are documented.
- The method avoids unnecessary complexity and overfitting.
- Output is stable under repeated execution with the same input.

## Signal Generation Rules
- Generate signals only when rule definitions are complete.
- No black-box logic.
- No LLM-generated decision paths.
- No randomization.
- If a rule cannot be written clearly enough to test, do not emit a signal.
- If regime, ranking, or feature prerequisites fail, stop before signal generation.

## Decision Rules
- If input data is not validated and normalized: stop.
- If feature definitions are incomplete: stop.
- If scoring logic is unclear or non-explainable: stop.
- If regime logic is too opaque to audit: stop.
- If signal criteria are not fully defined: stop.
- If logic passes these gates, produce deterministic outputs and state the exact assumptions used.

## Required Output
Every use of this skill should produce a contract-compliant strategy-stage output plus a short diagnosis, feature summary, and brief explanation of ranking or regime logic when applicable.

## Output Style
- Always show feature outputs.
- Always explain ranking logic briefly.
- Always provide the contract-compliant strategy-stage result.
- Prefer structured tables, DataFrames, or clearly auditable logs.
- Keep code outputs production-ready and testable.

## Failure Mode
If data is insufficient:
- Stop immediately.
- State which required inputs or validations are missing.

If logic is unclear:
- Stop immediately.
- State which feature, ranking, regime, or signal rule is underdefined.

Do not guess.
Do not emit heuristic signals without explicit evidence.
Do not bypass the validated-data gate.

## Completion Criteria
The task is complete only when one of these is true:
- A contract-compliant strategy-stage output has been produced from validated normalized BIST data.
- The workflow has been explicitly blocked with a contract-compliant blocking result and exact missing data or rule definition.

This skill is responsible for transforming clean BIST data into actionable but controlled signals for PRDV3.