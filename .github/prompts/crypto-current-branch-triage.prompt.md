---
name: crypto-current-branch-triage
description: "Use to audit the current branch for large diffs, dirty trees, generated artifacts, and scope violations before any PR or merge work."
agent: agent
---

You are triaging the current branch for crypto_core workflow safety.

Goal: decide whether the branch can be merged as-is, must be cleaned, or must be split.

Rules:
- crypto_core only.
- No BIST leakage.
- No runtime/source trading logic changes.
- No new implementation phase.
- Stop before PR if scope is unsafe.
- Fail closed on ambiguity.

Checklist:
1. Inspect `git status --short --branch`.
2. Classify every file as one of:
   - intended crypto_core setup change
   - unrelated tracked change
   - generated/cache/artifact file
   - dirty worktree noise
   - scope violation
3. Remove or isolate generated/cache/artifact files.
4. Split unrelated work away from the intended slice.
5. Identify whether the diff is safe for one PR or must be split.
6. If the branch is unsafe, return a blocked report with exact proof.

Decision outputs:
- `SAFE_TO_PR`
- `CLEANUP_REQUIRED`
- `SPLIT_REQUIRED`
- `BLOCKED_WITH_PROOF`

Report format:
- branch state
- file classification
- unsafe files, if any
- cleanup actions needed
- split boundary, if any
- blocker proof, if any