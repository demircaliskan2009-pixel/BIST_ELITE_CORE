---
name: crypto-phase-runner-high-throughput
description: "Use to execute one bounded crypto_core phase end-to-end from precheck through post-merge verification without scope drift."
agent: agent
---

Execute exactly one bounded phase.
Do not patch outside the phase.
Do not start a new phase.
Do not widen scope.

<PHASE>
<TARGET>
<MAIN_HEAD>
<READ_REQUIRED>
<CREATE_FILES>
<SOURCE_ASSERT>
<ARTIFACT_FIELDS>
<FAIL_CLOSED>
<NEXT_BLOCKER>

Workflow:
1. Confirm branch state and clean scope.
2. Read `<READ_REQUIRED>` and trace the local call chain.
3. Validate the source assertion in `<SOURCE_ASSERT>`.
4. Create or update only the files listed in `<CREATE_FILES>`.
5. Keep the patch bounded and reversible.
6. Run targeted tests for the touched area.
7. Run full `tests/crypto_core`.
8. Run Ruff on the scoped crypto_core paths.
9. Run readiness and connector probes.
10. Check `git diff --check`, `git diff --stat`, and `git diff --name-only`.
11. If the phase is ready, open the PR against `<MAIN_HEAD>`.
12. Wait for CI and CodeQL.
13. Merge only by standard merge.
14. Pull main and verify the merge post-state.

Mandatory gates:
- review threads must be resolved or proven outdated
- CI must be green
- CodeQL must be green when present
- no unresolved safety blocker
- no generated or unrelated files in the PR

Fail-closed rule:
If any required evidence is missing, return `<FAIL_CLOSED>` and stop.

Closeout report fields:
<ARTIFACT_FIELDS>

Next blocker:
<NEXT_BLOCKER>