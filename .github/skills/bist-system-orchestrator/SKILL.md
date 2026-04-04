---
name: bist-system-orchestrator
description: 'Coordinate PRDV3 workflow across bist-data-pipeline, bist-strategy-engine, bist-risk-execution-gate, and bist-toolchain-optimizer using a single deterministic stage contract and strict execution order. Use when a BIST task spans multiple pipeline stages or requires stage validation, transition control, contract enforcement, or fail-closed orchestration.'
argument-hint: 'Describe the current PRDV3 stage, available upstream outputs, target outcome, files in scope, and any evidence showing which stages have already been completed.'
user-invocable: true
---

# BIST System Orchestrator

This skill is the central nervous system of PRDV3. It coordinates the BIST pipeline from data admission to strategy output to downstream risk gating using a shared contract, strict stage order, and fail-closed transitions.

## Shared Contract
- Contract reference: [../_shared/references/contract-schema.md](../_shared/references/contract-schema.md)
- Every stage output must comply with the shared PRDV3 contract before the pipeline can transition.
- The orchestrator must block the pipeline immediately on any contract mismatch.

## Use This Skill When
- A task spans more than one PRDV3 stage.
- You need to confirm whether a stage transition is valid.
- You need to enforce shared contracts across data, strategy, and risk outputs.
- You need to prevent redundant re-processing or invalid downstream execution.
- You need a single deterministic workflow view of the current pipeline state.

## Do Not Use This Skill When
- The task is confined to one stage and does not require cross-stage validation.
- The task depends on skipping stages or bypassing contract checks.
- The current stage cannot be evidenced at all.

## Managed Skills
- [../bist-toolchain-optimizer/SKILL.md](../bist-toolchain-optimizer/SKILL.md) shapes the minimal correct workflow and validation path.
- [../bist-data-pipeline/SKILL.md](../bist-data-pipeline/SKILL.md) is stage 1 and the only trusted data entry gate.
- [../bist-strategy-engine/SKILL.md](../bist-strategy-engine/SKILL.md) is stage 2 and the only trusted feature, ranking, regime, and signal gate.
- [../bist-risk-execution-gate/SKILL.md](../bist-risk-execution-gate/SKILL.md) is stage 3 and the only trusted downstream risk and execution gate.

## Strict Execution Order
1. `bist-data-pipeline`
2. `bist-strategy-engine`
3. `bist-risk-execution-gate`

No stage may be skipped.
No downstream stage may run on missing, stale, invalid, or mismatched upstream output.

## Non-Negotiable Rules
- Enforce strict stage order at all times.
- Never allow skipping stages.
- Ensure outputs from one stage are valid inputs for the next.
- Enforce a shared data contract across all stages.
- Track the current pipeline stage explicitly.
- Avoid redundant re-processing when a valid upstream result already exists.
- Fail closed if any stage fails, is missing, or is contract-invalid.
- Never propagate invalid outputs downstream.

## Transition Rules
- Transition from data to strategy is valid only when the upstream data-stage output is contract-compliant and eligible for downstream use.
- Transition from strategy to risk is valid only when the upstream strategy-stage output is contract-compliant and eligible for downstream risk gating.
- If any required field is missing from an upstream contract, stop.
- If any stage status, scope field, or validation field mismatches the shared contract, stop.
- If stage outputs refer to conflicting symbols, timeframes, universes, or assumptions, stop.
- If there is uncertainty about current stage state, stop and request the minimum evidence needed.

## Standard Procedure
1. Identify current stage.
Determine whether the task is currently at data, strategy, or risk stage, or whether it is missing valid stage evidence entirely.

2. Validate upstream evidence.
Confirm that every prior stage has completed with a valid contract-compliant output.

3. Check transition validity.
Verify that the next requested step is reachable without skipping any required stage.

4. Normalize the contract view.
Restate the current pipeline state using the shared contract and verify all required fields, statuses, and scope values.

5. Route to the correct stage.
Use the matching PRDV3 skill only after the orchestrator confirms the transition is valid.

6. Prevent redundant work.
If a valid upstream result already exists and still matches scope, do not repeat that stage.

7. Stop the full pipeline on failure.
If any stage fails, mismatches contract, or produces uncertainty, stop the pipeline and name the blocking stage.

## Workflow Enforcement Checklist
- Current stage is explicitly named.
- Prior required stages are present and valid.
- No stage has been skipped.
- Requested next action matches the allowed transition.
- Downstream work is blocked on any upstream failure.

## Consistency Control Checklist
- All stages use the same symbols or universe assumptions.
- All stages use compatible time scope and granularity.
- Output formats do not conflict across stage boundaries.
- Status values and required fields match the shared contract.
- Explanations and decisions remain deterministic and auditable.

## Pipeline Awareness Rules
- Track current stage as one of: `data`, `strategy`, `risk`.
- Treat missing upstream proof as `unknown`, which is not a valid transition state.
- Avoid rerunning a completed stage unless scope changed or upstream validity was invalidated.
- If scope changes after a stage completed, require revalidation from the earliest affected stage.

## Tool Usage Rules
- Use minimal steps.
- Prefer deterministic transitions.
- Avoid redundant calls.
- Use the toolchain optimizer mindset when multiple valid routes exist.
- Prefer stage-specific skills for domain work once orchestration validity is established.

## Required Output
Every use of this skill should produce:
1. Current stage.
2. Pipeline validity statement.
3. Transition decision.
4. Contract validation status for each relevant completed stage.
5. Exact blocking stage and reason if the pipeline cannot proceed.
6. Single best next action.

## Output Style
- Always show current stage.
- Always show transition decision.
- Always confirm pipeline validity.
- Keep the response concise, explicit, and contract-driven.

## Failure Mode
If stage mismatch is detected:
- Stop immediately.
- State the invalid transition and the earliest stage that must be completed or repeated.

If contract mismatch is detected:
- Stop immediately.
- State the missing or conflicting contract field.

If data inconsistency is detected anywhere in the chain:
- Stop immediately.
- Block the full pipeline until the inconsistency is resolved.

## Completion Criteria
The task is complete only when one of these is true:
- The current PRDV3 stage has been identified, all upstream contracts are valid, and the next transition has been approved or executed correctly.
- The pipeline has been explicitly stopped with the exact stage, contract mismatch, or inconsistency preventing safe continuation.

This skill coordinates the PRDV3 pipeline as a single deterministic system.