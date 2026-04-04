---
name: bist-risk-execution-gate
description: 'Handle PRDV3 downstream risk, execution, order safety, auditability, and blocked-path enforcement for BIST-only trading flows. Use when evaluating whether a trade path is allowed or blocked, enforcing risk limits and session rules, hardening deterministic execution logic, or validating auditable order handling from approved strategy outputs.'
argument-hint: 'Describe the approved BIST input, trade intent, order semantics, current risk state, session context, target files, and required validation scope.'
user-invocable: true
---

# BIST Risk Execution Gate

This skill is the downstream control gate for PRDV3. It decides whether a BIST trade path is allowed or blocked, enforces risk and session constraints, and preserves deterministic auditability for every execution decision.

## Shared Contract
- Contract reference: [../_shared/references/contract-schema.md](../_shared/references/contract-schema.md)
- All outputs from this skill must comply with the shared PRDV3 contract.
- This skill may run only on a contract-compliant upstream strategy-stage result.

## Use This Skill When
- Enforcing downstream risk controls on approved BIST trade intents.
- Reviewing or implementing execution safety, order lifecycle rules, or blocked-path handling.
- Validating session rules, market constraints, exposure limits, or idempotency behavior.
- Hardening order creation, submission, modification, cancellation, fill handling, or rejection logging.
- Verifying that live-path changes have sufficient local validation evidence.

## Do Not Use This Skill When
- The input is not validated, normalized, and strategy-approved.
- The trade intent, order semantics, or risk state is ambiguous.
- The task requires bypassing risk controls, session rules, exposure limits, or audit logging.
- The logic depends on guessed execution behavior or undocumented broker semantics.

## Non-Negotiable Rules
- Operate strictly on validated, normalized, strategy-approved BIST inputs.
- Fail closed on any uncertainty, missing state, malformed order, or rule violation.
- Never bypass risk controls, session rules, exposure limits, or idempotency checks.
- Never create or send orders from unvalidated or ambiguous logic.
- Preserve auditability for every decision, rejection, execution attempt, and resulting state transition.
- Treat unclear execution semantics as a hard stop.
- Keep all gate decisions deterministic and reproducible.

## Upstream Dependency
- Treat [../bist-data-pipeline/SKILL.md](../bist-data-pipeline/SKILL.md) as the trusted data admission gate.
- Treat [../bist-strategy-engine/SKILL.md](../bist-strategy-engine/SKILL.md) as the trusted signal-generation gate.
- If input has not already passed both gates with contract-compliant outputs, stop and request validated, strategy-approved BIST inputs first.

## Working Mindset
- Use read, search, edit, todo, and execute for targeted repo-local work.
- Use execute for local validation when needed instead of delegating validation steps.
- Keep outputs concise, explicit, auditable, and testable.
- Prefer minimal diffs and deterministic code paths over broad refactors.
- Treat allowed and blocked paths as equally important implementation targets.

## Control Pipeline Stages
1. Input gate.
2. Risk-state validation.
3. Order-semantics validation.
4. Session and market-rule gate.
5. Execution-path decision.
6. Idempotency and traceability checks.
7. Validation evidence.
8. Final allowed or blocked outcome.

## Standard Procedure
1. Confirm input eligibility.
Verify the request is based on validated, normalized, strategy-approved BIST inputs.

2. Confirm trade intent and state.
Identify symbol, side, quantity, price semantics, order type, portfolio context, existing positions, and current risk state.

3. Enforce the risk gate.
Check position sizing, exposure, stop-loss, portfolio constraints, concentration limits, and any other explicit safety rules.

4. Validate order semantics.
Confirm order fields are complete, well-formed, deterministic, and compatible with the execution path.

5. Enforce session and market rules.
Respect BIST session timing, market-state constraints, and any repo-defined execution restrictions. If rule interpretation is uncertain, stop.

6. Decide allowed or blocked path.
Return an explicit decision and name the exact rule or constraint that allowed or blocked the path.

7. Preserve execution safety.
Ensure create, submit, modify, cancel, fill, and rejection paths are auditable and idempotent where practical.

8. Validate implementation evidence.
Require tests for both allowed and blocked paths when behavior changes, and prefer repository-native proof commands when appropriate.

## Risk Gate Checklist
- Position sizing logic is explicit.
- Exposure and concentration checks are enforced.
- Stop-loss or protective constraints are applied where required.
- Unsafe or incomplete trade requests are rejected.
- Rejection paths are explicit and testable.

## Execution Safety Checklist
- Order creation is deterministic and auditable.
- Submission, modification, and cancellation behavior is explicit.
- Idempotency is preserved where practical.
- Fill, rejection, and decision outcomes are traceable.
- Live-path changes are blocked without validation evidence.

## Session And Market Rules Checklist
- BIST session timing is respected.
- Market-state constraints are enforced.
- Execution outside allowed conditions is prevented.
- Rule uncertainty is treated as a hard stop.

## Validation Checklist
- Allowed and blocked paths are both covered by tests when feasible.
- Repository-native proof commands are preferred when they fit the scope.
- Validation is stated explicitly, including when it was not run.
- No live-path change is accepted without clear validation evidence.

## Decision Rules
- If risk state is unclear: stop.
- If execution semantics are unclear: stop.
- If order fields are malformed or incomplete: block.
- If any risk, session, or market rule is violated: block.
- If idempotency or auditability cannot be preserved: block.
- If all gates pass with explicit evidence: allow the path and state the exact enforced rules.

## Required Output
Every use of this skill should produce a contract-compliant risk-stage output plus a short diagnosis, exact enforced rule or constraint, and auditability statement.

## Output Style
- Always state the contract-compliant risk-stage status.
- Always name the exact rule or constraint being enforced.
- Always show validation or explicitly state it was not run.
- Prefer structured, testable outputs over narrative prose.
- Keep code and patches minimal, auditable, and production-ready.

## Failure Mode
If risk state is unclear:
- Stop immediately.
- State the missing or ambiguous risk inputs.

If execution semantics are unclear:
- Stop immediately.
- State which order or broker behavior is underdefined.

Do not assume order safety.
Do not guess execution behavior.
Do not bypass blocked-path enforcement.

## Completion Criteria
The task is complete only when one of these is true:
- A contract-compliant risk-stage output has been produced with deterministic downstream decision details.
- The workflow has been explicitly stopped with a contract-compliant blocking result and exact missing state, malformed input, or rule ambiguity.

This skill is responsible for downstream risk enforcement, execution safety, and auditability for PRDV3 BIST trade paths.