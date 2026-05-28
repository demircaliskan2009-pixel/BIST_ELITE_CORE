---
name: crypto-model-escalation-policy
description: "Model and agent escalation policy for Setup v2 and future crypto_core high-throughput work."
agent: agent
---

Use this policy to choose the safest model and agent for a crypto_core request.

## Model and Agent Mapping

### Copilot Auto
Use for:
- setup docs, prompts, and agent specs
- bounded deterministic phases
- PR closeout
- review-thread repair when the fix is local and obvious
- telemetry or artifact doc updates
- test/proof/reporting phases

### Crypto Throughput Commander
Use as the default high-throughput agent for:
- crypto_core PR execution
- closeout
- triage
- review-thread repair
- phase dispatch

### Crypto Core Engineer
Use for:
- source/runtime bounded patches
- narrow implementation work
- exact-file fixes with full validation

### Forensic Debugger
Use for:
- read-only root cause analysis
- failing tests
- dirty diffs
- broad unknowns
- CI failures that need evidence-based tracing

### PRD Compliance Auditor
Use for:
- read-only scope audits
- protocol audits
- PRD conformance checks
- deterministic behavior audits

### Codex
Use when:
- the task is high-risk and multi-file
- runtime/service/execution/risk/allocator logic is involved
- Copilot failed to produce a safe bounded answer
- repeated review blockers need a broader repair
- the task is explicitly `HIGH_REASONING_REQUIRED`

### Deep Research
Use when:
- external or current venue facts are needed
- API/fees/rate limits/microstructure/regulation data is needed
- the repository cannot prove the answer
- a research gap blocks safe planning

## Escalation Rules

- Default to the smallest model/agent that can finish safely.
- Escalate only when proof cannot be obtained safely with the current lane.
- Do not use a larger model to hide missing evidence.
- Do not use Codex for work that is already safely bounded for Auto.
- Do not use Deep Research for questions the repository already answers.

## Exit Codes

If the current lane is insufficient, stop and report one of:
- `HIGH_REASONING_REQUIRED`
- `CODEX_REQUIRED`
- `DEEP_RESEARCH_REQUIRED`
- `INSUFFICIENT EVIDENCE`

## Default Rule

If the task can be proven locally, keep it local.
If the task cannot be proven locally, do not guess.
