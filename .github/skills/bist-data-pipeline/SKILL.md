---
name: bist-data-pipeline
description: 'Handle PRDV3 BIST data pipeline tasks: iDeal .G binary inspection, parsing, normalization, validation, timestamp checks, duplicate and gap detection, OHLCV integrity, symbol integrity, structured anomaly reporting, and fail-closed data admission. Use when working on BIST-only raw data intake, parser hardening, normalization, forensic inspection, or determining whether market data is safe for downstream use.'
argument-hint: 'Describe the BIST data task, target files or samples, expected output layer, known invariants, and required validation scope.'
user-invocable: true
---

# BIST Data Pipeline

This skill is the trusted data entry workflow for PRDV3. It handles BIST-only data operations from raw iDeal binary evidence to validated, normalized, inspectable outputs.

## Shared Contract
- Contract reference: [../_shared/references/contract-schema.md](../_shared/references/contract-schema.md)
- All outputs from this skill must comply with the shared PRDV3 contract.
- This skill may emit only a contract-compliant data-stage result.

## Use This Skill When
- Inspecting or hardening iDeal `.G` binary parsing.
- Validating raw or parsed BIST market data before downstream use.
- Normalizing vendor-specific records into deterministic OHLCV tables.
- Investigating duplicates, gaps, corrupt rows, timestamp issues, or symbol mismatches.
- Deciding whether a dataset is safe or unsafe for the rest of the trading pipeline.

## Do Not Use This Skill When
- The task is not about market data intake, parsing, validation, or normalization.
- The task concerns non-BIST markets unless explicitly requested.
- The task requires guessing undocumented binary formats or inferred vendor structures.
- The task can proceed only by tolerating suspicious or incomplete data.

## Non-Negotiable Rules
- Operate strictly on BIST data unless the user explicitly requests otherwise.
- Treat iDeal `.G` files as the primary raw source.
- Start every task with forensic inspection before any transformation.
- Never guess binary formats, field meanings, separators, encodings, or record layouts.
- Keep all parsing, validation, and normalization deterministic.
- Fail closed if data is incomplete, inconsistent, suspicious, or insufficiently evidenced.
- Never allow dirty or ambiguous data into downstream pipeline stages.
- Produce outputs that are inspectable as DataFrames, tables, or structured logs.

## Working Mindset
- Use a Data Wrangler mindset for tabular inspection: inspect columns, nulls, uniqueness, ranges, and anomalies explicitly.
- Use Jupyter-style reasoning: inspect, validate, transform, re-validate.
- Produce Ruff-compatible Python when code is written.
- Preserve Black and isort compatible formatting implicitly.
- Prefer minimal, reviewable diffs over broad rewrites.

## Pipeline Stages
1. Raw evidence.
2. Structural inspection.
3. Parser or decoder evidence.
4. Parsed records.
5. Validation.
6. Normalization.
7. Post-normalization validation.
8. Safety decision for downstream admission.

## Standard Procedure
1. Confirm scope.
Identify the exact BIST source, sample files, symbols, time range, and downstream target layer.

2. Perform forensic inspection first.
Inspect file size, repeating patterns, byte layout cues, record lengths, header or trailer behavior, encoding hints, and consistency across samples.

3. Establish only evidenced structure.
Document what is proven versus unknown. If boundaries, field semantics, or timestamp encoding are unclear, stop and request more evidence.

4. Parse conservatively.
Implement or assess parsing logic only from observed invariants. Keep raw-to-parsed transformations inspectable and reversible where practical.

5. Validate parsed output.
Check timestamp monotonicity, duplicates, gaps, symbol integrity, row counts, corrupt or partial rows, and OHLCV plausibility.

6. Normalize deterministically.
Convert parsed records into clean OHLCV or the explicitly requested canonical format. Standardize timestamps and preserve symbol identity without hidden coercions.

7. Re-validate normalized output.
Confirm the normalized layer did not introduce drift, row loss, duplicate inflation, timestamp distortion, or symbol corruption.

8. Emit the contract-compliant stage result.
Return a shared-schema-compliant data-stage output and block downstream usage on any unsafe result.

## Validation Checklist
- Timestamp order is monotonic for the declared granularity.
- Duplicate rows are identified and classified.
- Gaps are measured, not assumed away.
- OHLCV fields are internally consistent and plausible.
- Symbol values are valid, stable, and match expected BIST identity.
- Corrupt, partial, or truncated entries are surfaced.
- Transformations are deterministic and reproducible.
- Outputs are inspectable in table or structured-log form.

## Decision Rules
- If the binary structure is unclear: stop and request more evidence.
- If multiple plausible layouts exist: do not choose one implicitly; request discriminating evidence.
- If parsed output violates core invariants: mark unsafe and block downstream usage.
- If normalization requires undocumented assumptions: stop rather than coerce.
- If data passes checks with documented evidence: mark safe and state the validated scope.

## Required Output
Every use of this skill should produce a contract-compliant data-stage output plus a short diagnosis, evidence summary, validation results, and anomaly summary.

## Output Style
- Always show validation results.
- Always highlight anomalies.
- Always state the contract-compliant data-stage status.
- Prefer compact tables, DataFrames, or structured logs over narrative prose.
- When code is needed, make it production-ready and inspectable.

## Failure Mode
If data format, field meaning, or structural boundaries are unclear:
- Stop immediately.
- State what is proven and what is not.
- Request the minimum additional evidence needed.

Do not guess.
Do not infer hidden structure without evidence.
Do not pass ambiguous data downstream.

## Completion Criteria
The task is complete only when one of these is true:
- A contract-compliant data-stage output has been produced after forensic inspection and validation.
- The workflow has been stopped with a contract-compliant blocking result and exact anomalies or missing evidence.

This skill is the only trusted data entry point for the PRDV3 trading system.