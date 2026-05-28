---
name: crypto-next-phase-planner
description: "Use to inspect the latest blocker and produce the smallest safe next phase prompt without patching."
agent: agent
---

Plan the next crypto_core phase, but do not patch anything.

Rules:
- crypto_core only.
- No BIST leakage.
- No code edits.
- No phase execution.
- No broad scan unless needed to classify the blocker.
- Fail closed when the blocker is not proven.

Workflow:
1. Inspect the latest blocker, open PR state, and recent closeout evidence.
2. Determine the smallest Copilot-safe next slice and whether split escalation is required.
3. Decide whether Deep Research is required.
4. Identify the smallest safe next phase.
5. Output a minimal next-phase prompt with bounded files and validation.

Decision guide:
- Use Copilot for bounded local follow-up work.
- For cross-file, review-thread-heavy, or multi-step repair phases, split into smaller Copilot-safe PR slices.
- Require Deep Research when the next step depends on external evidence or architectural confirmation not provable from the repository.

Output:
- blocker summary
- recommended agent
- Deep Research yes/no
- smallest safe phase
- seam split plan and PR order when one phase is unsafe
- files likely in scope
- required validation
- exact next-phase prompt