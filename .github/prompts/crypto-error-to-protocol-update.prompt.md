---
name: crypto-error-to-protocol-update
description: "Convert repeated crypto_core workflow failures into safe setup-level prompt/protocol updates with validation, PR, merge, and post-verify requirements."
agent: agent
---

Use one or more failure reports, review threads, or CI incidents to propose a reusable setup improvement.

Rules:
- Patch only workflow/setup files.
- No runtime or trading source changes.
- Require validation, PR, merge, and post-merge verification.
- Never weaken fail-closed, review-thread, CI, or merge gates.

Inputs:
- prior failure reports and thread classifications
- repeated blocker patterns
- affected prompt/agent/instruction/docs files

Process:
1. Classify recurrence (`SINGLE`, `REPEATED`, `SYSTEMIC`).
2. Verify generalizability across more than one incident.
3. Propose exact file-level update(s) and why they prevent recurrence.
4. Produce a scoped patch plan with minimal diff.
5. Define validation and closeout gates.

Outputs:
- recurrence_class
- generalizable (yes/no)
- recommended_change_type
- exact_target_files
- proposed_patch_summary
- validation_plan
- expected_gate_impact
- stop_reason if non-generalizable

Fail-closed:
- If recurrence is not generalizable, stop and return `NO_PROTOCOL_CHANGE`.
- If evidence is insufficient, return `INSUFFICIENT EVIDENCE`.
